"""
The five questions asked of the corpus, each a pure function of an events
frame.

Every one returns Stat(value, n), and returns None rather than 0.0 when its
denominator is empty. A zero denominator means 'this group cannot answer', and
printing 0.0 would read as a strong negative finding.

Touch density is a fairness check, not a finding. Real and shadow ladders
should be touched at similar rates; a large gap means the two get different
exposure and every other comparison in the report is suspect. Read it first.
"""

import json
from typing import Callable, Optional

import pandas as pd

from study_tool.mining.shadow_compare import Stat

RETESTED = ("RETEST_HELD", "RETEST_FAILED")
RESOLVED_OUTCOMES = ("RETEST_HELD", "RETEST_FAILED", "NEVER_RETESTED",
                     "NEVER_CONFIRMED")

StatisticFn = Callable[[pd.DataFrame], Stat]


def _resolved(events: pd.DataFrame) -> pd.DataFrame:
    if "outcome" not in events.columns:
        return events.iloc[0:0]
    return events[events["outcome"].isin(RESOLVED_OUTCOMES)]


def hold_rate(events: pd.DataFrame) -> Stat:
    """
    RETEST_HELD / (RETEST_HELD + RETEST_FAILED).

    Of the breaches that came back to the level, how many held. Breaches that
    never came back are excluded: they answer a different question.
    """
    retested = _resolved(events)
    retested = retested[retested["outcome"].isin(RETESTED)]
    if retested.empty:
        return Stat(None, 0)
    held = int((retested["outcome"] == "RETEST_HELD").sum())
    return Stat(held / len(retested), len(retested))


def rejection_rate(events: pd.DataFrame) -> Stat:
    """
    NEVER_CONFIRMED / all resolved breaches.

    How often price crossed a level but could not hold past it. Breaches still
    open when the data ended carry outcome None and are excluded - they are
    neither a rejection nor a confirmation.
    """
    resolved = _resolved(events)
    if resolved.empty:
        return Stat(None, 0)
    rejected = int((resolved["outcome"] == "NEVER_CONFIRMED").sum())
    return Stat(rejected / len(resolved), len(resolved))


def _depth(details: object) -> Optional[float]:
    """
    depth_in_sublevels out of the details JSON string.

    It is not a column. The analyzer writes it into `details`
    (gann_ladder_analyzer.py:343) and build_gann_corpus stores that dict as a
    JSON string, so it has to be parsed back out here.
    """
    if not isinstance(details, str):
        return None
    try:
        parsed = json.loads(details)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    value = parsed.get("depth_in_sublevels")
    return float(value) if isinstance(value, (int, float)) else None


def mean_retest_depth(events: pd.DataFrame) -> Stat:
    """Mean `depth_in_sublevels` over LADDER_RETEST events."""
    if "details" not in events.columns:
        return Stat(None, 0)
    retests = events[events["event_type"] == "LADDER_RETEST"]
    depths = [d for d in (_depth(v) for v in retests["details"]) if d is not None]
    if not depths:
        return Stat(None, 0)
    return Stat(sum(depths) / len(depths), len(depths))


def touch_density_fn(bar_count: int) -> StatisticFn:
    """
    Touches per bar, as a statistic bound to a bar count.

    Bound rather than passed, so compare() only ever sees frame -> Stat.

    This is the fairness check. If the real ladder and the shadows are touched
    at very different rates they are not comparable twins, and every other
    number in the report is suspect. Read it before anything else.
    """
    def touch_density(events: pd.DataFrame) -> Stat:
        touches = int((events["event_type"] == "LADDER_TOUCH").sum())
        if bar_count <= 0 or touches == 0:
            return Stat(None, touches)
        return Stat(touches / bar_count, touches)

    return touch_density


def reach_next_rate(events: pd.DataFrame) -> Stat:
    """
    REACHED / (REACHED + STOPPED). The headline hypothesis.

    Timeouts are excluded: a race that ran out of window is neither a win nor
    a loss, and folding it into either side would move the rate for a reason
    that has nothing to do with the levels. `timeout_share` reports them.

    Reads the `reach_outcome` column written by ladder_rebuild.
    """
    if "reach_outcome" not in events.columns:
        return Stat(None, 0)
    decided = events[events["reach_outcome"].isin(("REACHED", "STOPPED"))]
    if decided.empty:
        return Stat(None, 0)
    reached = int((decided["reach_outcome"] == "REACHED").sum())
    return Stat(reached / len(decided), len(decided))


def timeout_share(events: pd.DataFrame) -> Stat:
    """
    TIMEOUT / all raced breaches.

    Reported beside reach_next_rate so the excluded races are visible. A group
    whose races nearly all time out has a reach rate built on very little.
    """
    if "reach_outcome" not in events.columns:
        return Stat(None, 0)
    raced = events[events["reach_outcome"].isin(
        ("REACHED", "STOPPED", "TIMEOUT"))]
    if raced.empty:
        return Stat(None, 0)
    timeouts = int((raced["reach_outcome"] == "TIMEOUT").sum())
    return Stat(timeouts / len(raced), len(raced))
