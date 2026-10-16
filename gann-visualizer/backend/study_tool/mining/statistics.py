"""
The questions asked of the corpus, each a pure function of an events frame.

Some are factories rather than plain functions: `reach_rate_for` and
`timeout_share_for` bind to one outcome column, so a sweep over stop depths
and race windows gets a statistic per column without duplicating any logic.
`reach_next_rate` and `timeout_share` stay bound to `reach_outcome` - the
confirmed holdout result was measured under those names on that column, and
neither may quietly change meaning.

Every one returns Stat(value, n), and returns None rather than 0.0 when its
denominator is empty. A zero denominator means 'this group cannot answer', and
printing 0.0 would read as a strong negative finding.

Touch density is a fairness check, not a finding. Real and shadow ladders
should be touched at similar rates; a large gap means the two get different
exposure and every other comparison in the report is suspect. Read it first.
"""

import json
from typing import Callable, Optional

import numpy as np
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


def reach_rate_for(column: str) -> StatisticFn:
    """
    REACHED / (REACHED + STOPPED) on one outcome column.

    Timeouts are excluded: a race that ran out of window is neither a win nor
    a loss, and folding it into either side would move the rate for a reason
    that has nothing to do with the levels. `timeout_share_for` reports them.
    """
    def reach_rate(events: pd.DataFrame) -> Stat:
        if column not in events.columns:
            return Stat(None, 0)
        decided = events[events[column].isin(("REACHED", "STOPPED"))]
        if decided.empty:
            return Stat(None, 0)
        reached = int((decided[column] == "REACHED").sum())
        return Stat(reached / len(decided), len(decided))

    return reach_rate


def timeout_share_for(column: str) -> StatisticFn:
    """TIMEOUT / all raced breaches, for one outcome column."""
    def timeout_share_of(events: pd.DataFrame) -> Stat:
        if column not in events.columns:
            return Stat(None, 0)
        raced = events[events[column].isin(("REACHED", "STOPPED", "TIMEOUT"))]
        if raced.empty:
            return Stat(None, 0)
        timeouts = int((raced[column] == "TIMEOUT").sum())
        return Stat(timeouts / len(raced), len(raced))

    return timeout_share_of


def already_hit_share(events: pd.DataFrame) -> Stat:
    """
    Share of raced breaches whose target was already touched at confirmation.

    A breach confirms after two closes beyond the level, which can carry price
    past the target before the race even starts. This measures exactly that:
    the confirmation bar's own high (or low) had already reached the target.

    It does **not** mean those rows are free wins. The race starts at the bar
    after confirmation, so a row flagged here can still end STOPPED or
    TIMEOUT. Read it as 'the target was touched before the race began'.

    If this share is large the headline reach rate is partly measuring
    confirmation lag rather than progression, so it is reported rather than
    left implicit.
    """
    if "target_already_hit" not in events.columns:
        return Stat(None, 0)
    flags = events["target_already_hit"].dropna()
    if flags.empty:
        return Stat(None, 0)
    return Stat(float(flags.astype(bool).mean()), len(flags))


LAG_FREE_COLUMNS = ("target_hit_before_entry", "entry_beyond_level")


def _is(flags: pd.Series, value: bool) -> pd.Series:
    """
    Rows whose flag is exactly `value`.

    None and NaN match neither True nor False: a row with no target has no
    lag-free answer, and must be neither kept nor counted as dropped.
    """
    return flags.map(
        lambda v: isinstance(v, (bool, np.bool_)) and bool(v) is value)


def _has_lag_free_columns(events: pd.DataFrame) -> bool:
    return all(column in events.columns for column in LAG_FREE_COLUMNS)


def lag_free_reach_rate_for(column: str) -> StatisticFn:
    """
    REACHED / (REACHED + STOPPED) over the breaches a trader could take.

    Kept: the target was not touched on any bar from the cross to the
    confirmation (target_hit_before_entry False) and the confirmation bar
    closed beyond the level (entry_beyond_level True). Only bars up to the
    confirmation decide inclusion, so the filter adds no lookahead.
    """
    rate = reach_rate_for(column)

    def lag_free_reach_rate(events: pd.DataFrame) -> Stat:
        if not _has_lag_free_columns(events):
            return Stat(None, 0)
        kept = (_is(events["target_hit_before_entry"], False)
                & _is(events["entry_beyond_level"], True))
        return rate(events[kept])

    return lag_free_reach_rate


def dropped_share(events: pd.DataFrame) -> Stat:
    """
    Rows removed by either lag-free filter / targeted rows.

    Targeted rows are confirmed breaches that had a target
    (target_hit_before_entry not null), whatever their race outcome,
    timeouts included. Compared real against shadow: if the filter removes
    a different share of real rows than of shadow rows, the filtered sets
    are not like-for-like.
    """
    if not _has_lag_free_columns(events):
        return Stat(None, 0)
    hit = events["target_hit_before_entry"]
    targeted = _is(hit, True) | _is(hit, False)
    n = int(targeted.sum())
    if n == 0:
        return Stat(None, 0)
    dropped = targeted & (_is(hit, True)
                          | _is(events["entry_beyond_level"], False))
    return Stat(int(dropped.sum()) / n, n)


def entry_dropped_share(events: pd.DataFrame) -> Stat:
    """
    Targeted rows whose confirmation bar closed back (entry_beyond_level
    False) / targeted rows, whether or not the target filter also drops
    them. Zero for every close rule; only a wick rule can be non-zero.
    """
    if not _has_lag_free_columns(events):
        return Stat(None, 0)
    hit = events["target_hit_before_entry"]
    targeted = _is(hit, True) | _is(hit, False)
    n = int(targeted.sum())
    if n == 0:
        return Stat(None, 0)
    dropped = targeted & _is(events["entry_beyond_level"], False)
    return Stat(int(dropped.sum()) / n, n)


# The original names, bound to the strict column, so existing callers and the
# confirmed holdout definition are untouched.
reach_next_rate = reach_rate_for("reach_outcome")
timeout_share = timeout_share_for("reach_outcome")

# The lag-free statistic of the 2026-10-16 breach sweep, on the strict column.
lag_free_reach_rate = lag_free_reach_rate_for("reach_outcome")
