"""
Run a Gann ladder study over a list of bars.

Bars are supplied by the caller - fetching and caching are out of scope for
this phase. Each bar is a dict with open, high, low, close and an epoch
`timestamp` in seconds.

Usage:
    from study_tool.run_ladder_study import run_study
    events = run_study(bars, instrument="RELIANCE", timeframe="5",
                       price_scale=1, sun_degrees=[...], moon_degrees=[...])
"""

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from study_tool.event_logger import Event, EventLogger
from study_tool.gann_ladder import build_gann_square, build_ladder
from study_tool.gann_ladder_analyzer import GannLadderAnalyzer

# Bodies whose ladders move as the walk advances.
MOVING_BODIES = ("sun", "moon")


def degree_to_square(degree: float, zero_offset: int = 1) -> int:
    """
    Map an ecliptic longitude to a grid square.

    zero_offset 1 places 0 degrees on square 361 = 19^2, which lies on the
    odd-square diagonal - the project's default zero-degree line.
    """
    wrapped = int(round(degree)) % 360
    base = 360 if wrapped == 0 else wrapped
    shifted = base + zero_offset
    return shifted + 360 if shifted < 1 else shifted


def build_all_ladders(price: float, price_scale: int,
                      sun_square: Optional[int],
                      moon_square: Optional[int],
                      count: int = 8) -> List[Dict]:
    """Build the centre, Sun and Moon ladders for one price."""
    target = int(round(price * price_scale))
    levels: List[Dict] = []

    centre_grid = build_gann_square(target, 1)
    if centre_grid["too_large"] or not centre_grid["target_found"]:
        return levels

    levels.extend(build_ladder(
        grid=centre_grid,
        cross_centre=centre_grid["body_position"],
        source="center",
        scale=price_scale,
        count=count,
    ))

    for source, square in zip(MOVING_BODIES, (sun_square, moon_square)):
        if square is None:
            continue
        grid = build_gann_square(target, square)
        if grid["too_large"] or not grid["target_found"] or not grid["body_found"]:
            continue
        levels.extend(build_ladder(
            grid=grid,
            cross_centre=grid["body_position"],
            source=source,
            scale=price_scale,
            count=count,
        ))

    return levels


def run_study_chunk(
    bars: Sequence[Dict],
    instrument: str,
    timeframe: str,
    price_scale: int,
    sun_degrees: Sequence[float],
    moon_degrees: Sequence[float],
    config: Optional[Dict[str, Any]] = None,
    state: Optional[Dict[str, Any]] = None,
    start_index: int = 0,
    finalize: bool = True,
) -> Tuple[List[Event], Dict[str, Any]]:
    """
    Walk one chunk of a longer study, returning (events, resumable state).

    A long walk is fed in chunks - typically a day at a time - so breaches and
    pending crosses that are still open when a chunk ends carry over into the
    next one. Pass the returned state back in as `state`, and set
    `start_index` to the absolute index of this chunk's first bar so bar
    indices stay continuous across the whole walk.

    `finalize` closes out anything still open. Leave it False for every chunk
    but the last, otherwise each chunk boundary would be misreported as the
    end of the data.

    sun_degrees and moon_degrees are per-bar ecliptic longitudes for THIS
    chunk, the same length as `bars`. Ladders are rebuilt only when a body's
    rounded square changes or the price moves to a different grid square -
    rebuilding every bar is wasteful, rebuilding once per run is wrong.
    """
    if not (len(bars) == len(sun_degrees) == len(moon_degrees)):
        raise ValueError(
            "bars, sun_degrees and moon_degrees must be the same length; got "
            f"{len(bars)}, {len(sun_degrees)}, {len(moon_degrees)}"
        )

    settings: Dict[str, Any] = {
        "breach_mode": "close",
        "confirmation_closes": 2,
        "touch_tolerance_sublevels": 0.1,
        "resolution_window_bars": 50,
        "retest_window_bars": 50,
        "instrument": instrument,
        "timeframe": timeframe,
        "price_scale": price_scale,
    }
    if config:
        settings.update(config)

    analyzer = GannLadderAnalyzer(settings)
    carried_degrees: Dict[int, Tuple[float, float]] = {}
    if state is not None:
        analyzer.restore_state(state)
        carried_degrees = dict(state.get("degrees", {}))

    events: List[Event] = []

    cached_key = None
    levels: List[Dict] = []

    for offset, bar in enumerate(bars):
        index = start_index + offset
        sun_square = degree_to_square(sun_degrees[offset])
        moon_square = degree_to_square(moon_degrees[offset])
        target = int(round(bar["close"] * price_scale))
        key = (target, sun_square, moon_square)

        if key != cached_key:
            levels = build_all_ladders(
                bar["close"], price_scale, sun_square, moon_square
            )
            cached_key = key

        events.extend(analyzer.process_bar(bar, index, levels))

    if finalize:
        events.extend(analyzer.finalize())

    # Stamp each Sun/Moon event with the body's actual degree at the bar it
    # fired on - process_bar only ever sees the level's grid square, never
    # the raw longitude, so this can't be filled in any earlier.
    #
    # An event can point at a bar from an earlier chunk: a breach that opened
    # days ago and only resolves now is stamped with its OPENING bar. This
    # call was never handed that bar's degrees, so they come from the carried
    # map instead. Without it, exactly the long-lived breaches Phase 3 cares
    # about would lose their celestial degree.
    for event in events:
        source_index = event.bar_index
        if event.level_source not in ("sun", "moon") or source_index is None:
            continue
        offset = source_index - start_index
        if 0 <= offset < len(bars):
            pair = (sun_degrees[offset], moon_degrees[offset])
        elif source_index in carried_degrees:
            pair = carried_degrees[source_index]
        else:
            continue
        degree = pair[0] if event.level_source == "sun" else pair[1]
        event.body_degree = degree
        event.body_square = degree_to_square(degree)

    next_state = analyzer.get_state()
    next_state["degrees"] = _degrees_still_needed(
        next_state, carried_degrees, sun_degrees, moon_degrees, start_index, len(bars)
    )
    return events, next_state


def _degrees_still_needed(
    state: Dict[str, Any],
    carried: Dict[int, Tuple[float, float]],
    sun_degrees: Sequence[float],
    moon_degrees: Sequence[float],
    start_index: int,
    chunk_len: int,
) -> Dict[int, Tuple[float, float]]:
    """
    Keep the Sun/Moon degrees for bars a future chunk will still name.

    Only two pieces of open state carry a bar index forward - a pending
    cross's `first_bar` and an open breach's `bar` - so only those bars'
    degrees need to survive. Keeping the whole walk's degrees instead would
    grow without bound over a long study.
    """
    wanted = set()
    for pending in state.get("pending", {}).values():
        if pending.get("first_bar") is not None:
            wanted.add(pending["first_bar"])
    for breach in state.get("open_breaches", {}).values():
        if breach.get("bar") is not None:
            wanted.add(breach["bar"])

    kept: Dict[int, Tuple[float, float]] = {}
    for index in wanted:
        offset = index - start_index
        if 0 <= offset < chunk_len:
            kept[index] = (sun_degrees[offset], moon_degrees[offset])
        elif index in carried:
            kept[index] = carried[index]
    return kept


def run_study(
    bars: Sequence[Dict],
    instrument: str,
    timeframe: str,
    price_scale: int,
    sun_degrees: Sequence[float],
    moon_degrees: Sequence[float],
    config: Optional[Dict[str, Any]] = None,
) -> List[Event]:
    """
    Walk every bar in one pass, producing ladder interaction events.

    The single-shot entry point. For a walk long enough to checkpoint, use
    run_study_chunk directly.
    """
    events, _ = run_study_chunk(
        bars, instrument=instrument, timeframe=timeframe,
        price_scale=price_scale, sun_degrees=sun_degrees,
        moon_degrees=moon_degrees, config=config,
    )
    return events


def summarise(events: Sequence[Event]) -> Dict[str, int]:
    """Count events by type - a quick sanity check on a walk."""
    counts: Dict[str, int] = {}
    for event in events:
        name = event.event_type.value
        counts[name] = counts.get(name, 0) + 1
    return counts
