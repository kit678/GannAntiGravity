"""
Rebuilding the ladder at a bar, and racing the next level against the stop.

The corpus stores each bar's ladder as the three integers it is a pure
function of, not as a snapshot - a snapshot per rebuild would be tens of
millions of rows. So 'the next level beyond L' means rebuilding.

Two things keep that affordable:

  Only prices are cached, not level dicts. 14,641 distinct keys times ~363
  levels is 5.3 million dicts; one sorted float array per (key, source) is
  about 42 MB.

  Shadows never rebuild. A shadow ladder is the real ladder plus a constant,
  so a shadow's next level is the real next level plus that same constant.
  Subtract the offset, look up, add it back. This is exactly why the corpus
  had to start recording its offsets.
"""

import bisect
import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from study_tool.mining.corpus_meta import CorpusMeta
from study_tool.run_ladder_study import build_all_ladders

CONFIRMED = "LADDER_BREACH_CONFIRMED"
REACHED, STOPPED, TIMEOUT = "REACHED", "STOPPED", "TIMEOUT"

# A tolerance below one paise. Level prices round-trip through Parquet, so an
# exact float match cannot be relied on.
_PRICE_EPSILON = 1e-6


class LadderCache:
    """
    Level prices per bar, rebuilt once per distinct ladder key.

    build_all_ladders reads `price` only as int(round(price * price_scale)),
    which is exactly the `price_square` stored in ladder_keys. Dividing it back
    out therefore reproduces the build's ladder exactly, not approximately.
    """

    def __init__(self, ladder_keys: pd.DataFrame, price_scale: int):
        self.price_scale = price_scale
        self._key_by_bar: Dict[int, Tuple[int, int, int]] = {
            int(row.bar_index): (int(row.price_square), int(row.sun_square),
                                 int(row.moon_square))
            for row in ladder_keys.itertuples()
        }
        self._cache: Dict[Tuple[int, int, int], Dict[str, List[float]]] = {}

    def _ladder(self, key: Tuple[int, int, int]) -> Dict[str, List[float]]:
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        price_square, sun_square, moon_square = key
        levels = build_all_ladders(price_square / self.price_scale,
                                   self.price_scale, sun_square, moon_square)

        by_source: Dict[str, List[float]] = {}
        for level in levels:
            by_source.setdefault(level["source"], []).append(level["price"])
        for prices in by_source.values():
            prices.sort()

        self._cache[key] = by_source
        return by_source

    def prices(self, bar_index: int, source: str) -> List[float]:
        """Sorted level prices for one cross at one bar. Empty if unknown."""
        key = self._key_by_bar.get(int(bar_index))
        if key is None:
            return []
        return self._ladder(key).get(source, [])

    def next_level(self, bar_index: int, source: str, level_price: float,
                   direction: str, offset: float) -> Optional[float]:
        """
        The next level beyond `level_price` along `direction`, same cross.

        Args:
            offset: this shadow's price shift, 0.0 for real events. The lookup
                happens on the unshifted ladder and the shift is added back,
                so no shadow ladder is ever built.

        Returns None at the end of the ladder: it is finite, and beyond its
        last level there is no next level to reach.

        Same cross because the ladder is per-cross and the hypothesis is about
        progression along one cross.
        """
        prices = self.prices(bar_index, source)
        if not prices:
            return None

        unshifted = level_price - offset

        if direction == "up":
            index = bisect.bisect_right(prices, unshifted + _PRICE_EPSILON)
            if index >= len(prices):
                return None
            return prices[index] + offset

        index = bisect.bisect_left(prices, unshifted - _PRICE_EPSILON) - 1
        if index < 0:
            return None
        return prices[index] + offset

    def _index_of(self, prices: List[float], unshifted: float) -> Optional[int]:
        """
        Position of `unshifted` in the sorted ladder, or None if it is not a
        ladder price. `_PRICE_EPSILON` absorbs the Parquet float round-trip,
        exactly as next_level does.
        """
        index = bisect.bisect_left(prices, unshifted - _PRICE_EPSILON)
        if index < len(prices) and \
                abs(prices[index] - unshifted) <= _PRICE_EPSILON:
            return index
        return None

    def level_steps_away(self, bar_index: int, source: str, level_price: float,
                         direction: str, offset: float,
                         steps: float) -> Optional[float]:
        """
        The price `steps` ladder positions from `level_price` along `direction`.

        Positive steps go with the breach (the target side), negative steps go
        against it (the stop side). `steps=1` is exactly `next_level`.

        Fractional steps interpolate between the two bracketing levels, so a
        half step is half of the *real local gap*. That matters: spacing is
        uneven on off-centre crosses, so half of `median_sub_gap` would be the
        wrong distance nearly everywhere.

        Returns None when the walk runs off the end of the finite ladder.
        """
        prices = self.prices(bar_index, source)
        if not prices:
            return None

        unshifted = level_price - offset
        base = self._index_of(prices, unshifted)
        if base is None:
            return None

        # Ladder prices ascend, so walking "down" means walking left.
        signed = steps if direction == "up" else -steps
        lower = math.floor(signed)
        upper = math.ceil(signed)

        # lower <= upper always, so bounding the pair bounds both ends.
        if not (0 <= base + lower and base + upper < len(prices)):
            return None

        low_price = prices[base + lower]
        if lower == upper:
            return low_price + offset

        high_price = prices[base + upper]
        fraction = signed - lower
        return low_price + (high_price - low_price) * fraction + offset


def race_with_stop(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
                   start: int, stop_price: float, target: float,
                   direction: str, window: int) -> str:
    """
    Does price reach `target` before closing through `stop_price`?

    Returns REACHED, STOPPED or TIMEOUT. A race truncated by the end of the
    data is a TIMEOUT, not a loss.

    The stop is a **strict** close beyond `stop_price`, so a bar that merely
    touches it - or wicks through and closes back - keeps the race alive. That
    is deliberate: the move being tested is 'breach, dip back, retest, then
    carry on', and a retest that holds must not read as a failure.

    Within a single bar the target wins. The target is tested against the
    bar's high or low, which occur during the bar; the stop is tested against
    the close, which is the bar's last price. So if both conditions hold, the
    target came first.
    """
    last = min(start + 1 + window, len(closes))
    for i in range(start + 1, last):
        if direction == "up":
            if highs[i] >= target:
                return REACHED
            if closes[i] < stop_price:
                return STOPPED
        else:
            if lows[i] <= target:
                return REACHED
            if closes[i] > stop_price:
                return STOPPED
    return TIMEOUT


def race_to_next_level(highs: np.ndarray, lows: np.ndarray,
                       closes: np.ndarray, start: int, level_price: float,
                       target: float, direction: str, window: int) -> str:
    """
    The strict race: the stop sits on the breached level itself.

    Kept as a named function because the confirmed holdout result was measured
    with exactly this definition. It is the zero-depth case of race_with_stop.
    """
    return race_with_stop(highs, lows, closes, start=start,
                          stop_price=level_price, target=target,
                          direction=direction, window=window)


def depth_label(depth: float) -> str:
    """`0.5` -> `0p5`. Column names cannot carry a dot without pain."""
    text = f"{depth:g}"
    return text.replace(".", "p").replace("-", "m")


def outcome_column(depth: float, window: int) -> str:
    return f"reach_d{depth_label(depth)}_w{window}"


def add_reach_outcomes(events: pd.DataFrame, bars: pd.DataFrame,
                       cache: LadderCache, meta: CorpusMeta,
                       stop_depths: Sequence[float] = (0.0,),
                       windows: Optional[Sequence[int]] = None) -> pd.DataFrame:
    """
    Add one REACHED/STOPPED/TIMEOUT column per (stop depth, window) pair.

    `stop_depths` is in ladder steps behind the breached level. 0.0 is the
    strict test: the stop sits on the level itself. 1.0 puts it one level
    behind, so a dip back that retests the level and holds stays alive.

    Also adds:
      reach_outcome       - alias of the (0.0, corpus window) column, because
                            the confirmed holdout result was measured on that
                            name and must not change meaning.
      target_already_hit  - True when the breach's own confirmation bar had
                            already reached the target. Those wins cost no
                            travel; their share must be visible.

    None means the row was not raced: not a confirmed breach, no direction, or
    the ladder ran out before the target or the stop. None is not a loss.

    The ladder is queried once per row per distinct depth, then every window
    reuses those prices - the lookup is the expensive half over ~560k rows.
    """
    highs = bars["high"].to_numpy(dtype=float)
    lows = bars["low"].to_numpy(dtype=float)
    closes = bars["close"].to_numpy(dtype=float)

    if windows is None:
        windows = (meta.resolution_window_bars,)
    depths = tuple(stop_depths)
    windows = tuple(windows)

    frame = events.reset_index(drop=True)
    columns = {(d, w): [None] * len(frame) for d in depths for w in windows}
    already_hit: List[Optional[bool]] = [None] * len(frame)

    is_confirmed = (frame["event_type"] == CONFIRMED).to_numpy()
    bar_indices = frame["bar_index"].to_numpy()
    level_prices = frame["level_price"].to_numpy()
    directions = frame["direction"].to_numpy()
    sources = frame["level_source"].to_numpy()
    shadow_ids = frame["shadow_id"].to_numpy()

    for position in range(len(frame)):
        if not is_confirmed[position]:
            continue
        direction = directions[position]
        if direction not in ("up", "down"):
            continue

        bar = int(bar_indices[position])
        source = sources[position]
        level_price = float(level_prices[position])
        offset = meta.offset_for(shadow_ids[position])

        # next_level, not level_steps_away, deliberately. level_steps_away
        # requires level_price to BE a ladder price within 1e-6 and returns
        # None otherwise, while next_level brackets any price. Swapping it in
        # here could silently drop rows the confirmed result raced, which
        # would change what reach_outcome means. The target keeps its
        # original lookup; only the stop uses the new step arithmetic.
        target = cache.next_level(bar, source, level_price, direction, offset)
        if target is None:
            continue

        already_hit[position] = bool(
            highs[bar] >= target if direction == "up" else lows[bar] <= target)

        for depth in depths:
            if depth == 0:
                # The strict case: the stop is the breached level itself,
                # taken directly rather than via a ladder lookup, so depth 0
                # cannot drift from the confirmed definition.
                stop_price = level_price
            else:
                stop_price = cache.level_steps_away(
                    bar, source, level_price, direction, offset, -float(depth))
            if stop_price is None:
                continue
            for window in windows:
                columns[(depth, window)][position] = race_with_stop(
                    highs, lows, closes, start=bar, stop_price=stop_price,
                    target=target, direction=direction, window=window)

    for (depth, window), values in columns.items():
        frame[outcome_column(depth, window)] = values
    frame["target_already_hit"] = already_hit

    legacy = outcome_column(0.0, meta.resolution_window_bars)
    if legacy in frame.columns:
        frame["reach_outcome"] = frame[legacy]

    return frame
