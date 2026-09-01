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
from typing import Any, Dict, List, Optional, Sequence

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

    for source, square in (("sun", sun_square), ("moon", moon_square)):
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
    Walk the bars, producing ladder interaction events.

    sun_degrees and moon_degrees are per-bar ecliptic longitudes, the same
    length as bars. Ladders are rebuilt only when a body's rounded square
    changes or the price moves to a different grid square - rebuilding every
    bar is wasteful, rebuilding once per run is wrong.
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
    events: List[Event] = []

    cached_key = None
    levels: List[Dict] = []

    for index, bar in enumerate(bars):
        sun_square = degree_to_square(sun_degrees[index])
        moon_square = degree_to_square(moon_degrees[index])
        target = int(round(bar["close"] * price_scale))
        key = (target, sun_square, moon_square)

        if key != cached_key:
            levels = build_all_ladders(
                bar["close"], price_scale, sun_square, moon_square
            )
            cached_key = key

        events.extend(analyzer.process_bar(bar, index, levels))

    events.extend(analyzer.finalize())
    return events


def summarise(events: Sequence[Event]) -> Dict[str, int]:
    """Count events by type - a quick sanity check on a walk."""
    counts: Dict[str, int] = {}
    for event in events:
        name = event.event_type.value
        counts[name] = counts.get(name, 0) + 1
    return counts
