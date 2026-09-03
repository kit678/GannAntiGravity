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
from typing import Dict, List, Optional, Tuple

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


def add_reach_outcomes(events: pd.DataFrame, bars: pd.DataFrame,
                       cache: LadderCache, meta: CorpusMeta) -> pd.DataFrame:
    """
    Add a `reach_outcome` column: REACHED / STOPPED / TIMEOUT, or None.

    None means the row was not raced - it is not a confirmed breach, or its
    cross had no next level beyond the breached one. None is not a loss and
    the statistics treat it as absent.

    Run before compare(), so every statistic stays a pure frame -> Stat.
    """
    highs = bars["high"].to_numpy(dtype=float)
    lows = bars["low"].to_numpy(dtype=float)
    closes = bars["close"].to_numpy(dtype=float)
    window = meta.resolution_window_bars

    frame = events.reset_index(drop=True)
    outcomes: List[Optional[str]] = [None] * len(frame)

    # Positional rather than label-based: the frame arrives from a filtered
    # slice, and iterating positions keeps the outcome list aligned with it.
    is_confirmed = (frame["event_type"] == CONFIRMED).to_numpy()

    for position in range(len(frame)):
        if not is_confirmed[position]:
            continue

        row = frame.iloc[position]
        direction = row["direction"]
        if direction not in ("up", "down"):
            continue

        level_price = float(row["level_price"])
        target = cache.next_level(
            bar_index=int(row["bar_index"]), source=row["level_source"],
            level_price=level_price, direction=direction,
            offset=meta.offset_for(row["shadow_id"]))
        if target is None:
            continue

        outcomes[position] = race_to_next_level(
            highs, lows, closes, start=int(row["bar_index"]),
            level_price=level_price, target=target,
            direction=direction, window=window)

    frame["reach_outcome"] = outcomes
    return frame
