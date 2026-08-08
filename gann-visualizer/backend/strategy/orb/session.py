"""
Pure session maths for the ORB test.

No I/O, no strategy rules. Everything here operates on a bars DataFrame with a
``timestamp`` column of Unix seconds and the usual OHLCV columns.

Bars are timestamped at bar OPEN, matching yfinance and Dhan. A 5-minute bar
stamped 09:15 covers 09:15 to 09:20, so the first fifteen minutes of an NSE
session is the three bars stamped 09:15, 09:20 and 09:25.
"""

from datetime import date, time
from typing import Dict, List, Tuple

import pandas as pd
import pytz

IST = pytz.timezone("Asia/Kolkata")
SESSION_START = time(9, 15)
FLAT_BY = time(15, 15)


def add_bar_index(bars: pd.DataFrame) -> pd.DataFrame:
    """Sort by timestamp and attach a unique, globally monotonic ``bar_index``.

    The index must be global rather than per-session because the trade simulator
    selects future bars by index across the whole frame.
    """
    if "timestamp" not in bars.columns:
        raise ValueError("bars must have a 'timestamp' column")
    if bars.empty:
        raise ValueError("bars must not be empty")

    out = bars.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
    out["bar_index"] = range(len(out))
    return out


def _attach_ist(bars: pd.DataFrame) -> pd.DataFrame:
    out = bars.copy()
    out["ist"] = pd.to_datetime(out["timestamp"], unit="s", utc=True).dt.tz_convert(IST)
    out["session_date"] = out["ist"].dt.date
    out["ist_time"] = out["ist"].dt.time
    return out


def split_sessions(bars: pd.DataFrame) -> Dict[date, pd.DataFrame]:
    """Group bars into one DataFrame per IST trading date, ordered by date.

    Each session keeps its global ``bar_index`` and gains ``ist``,
    ``session_date`` and ``ist_time`` columns.
    """
    if "bar_index" not in bars.columns:
        raise ValueError("call add_bar_index before split_sessions")

    enriched = _attach_ist(bars)
    sessions: Dict[date, pd.DataFrame] = {}
    for session_date, group in enriched.groupby("session_date", sort=True):
        sessions[session_date] = group.sort_values("bar_index").reset_index(drop=True)
    return sessions


def _minutes_from(reference: time, value: time) -> int:
    return (value.hour * 60 + value.minute) - (reference.hour * 60 + reference.minute)


def opening_range_bars(
    session: pd.DataFrame,
    or_minutes: int,
    session_start: time = SESSION_START,
) -> pd.DataFrame:
    """Bars whose open time falls in [session_start, session_start + or_minutes)."""
    offsets = session["ist_time"].apply(lambda t: _minutes_from(session_start, t))
    mask = (offsets >= 0) & (offsets < or_minutes)
    return session[mask].reset_index(drop=True)


def post_range_bars(
    session: pd.DataFrame,
    or_minutes: int,
    session_start: time = SESSION_START,
    flat_by: time = FLAT_BY,
) -> pd.DataFrame:
    """Tradable bars: after the opening range, at or before the flat-by time.

    ``flat_by`` names the last bar we are allowed to still be holding through;
    that bar's close is the forced exit.
    """
    offsets = session["ist_time"].apply(lambda t: _minutes_from(session_start, t))
    flat_offset = _minutes_from(session_start, flat_by)
    mask = (offsets >= or_minutes) & (offsets <= flat_offset)
    return session[mask].reset_index(drop=True)


def bars_until_flat(
    session: pd.DataFrame,
    bar_index: int,
    session_start: time = SESSION_START,
    flat_by: time = FLAT_BY,
) -> int:
    """How many bars after ``bar_index`` remain holdable in this session."""
    offsets = session["ist_time"].apply(lambda t: _minutes_from(session_start, t))
    flat_offset = _minutes_from(session_start, flat_by)
    mask = (session["bar_index"] > bar_index) & (offsets <= flat_offset)
    return int(mask.sum())


def split_dates_in_half(dates: List[date]) -> Tuple[List[date], List[date]]:
    """Chronological halves. An odd extra date goes to train, never to test.

    Nothing is fitted on the train half — the split exists only to check the
    result holds up over time.
    """
    if len(dates) < 2:
        raise ValueError("need at least 2 dates to split")
    ordered = sorted(dates)
    cut = (len(ordered) + 1) // 2
    return ordered[:cut], ordered[cut:]
