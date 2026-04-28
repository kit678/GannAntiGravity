"""Multi-timeframe analysis helpers.

Key concept: bar_close_time
    Events fire at bar CLOSE but the engine emits bar OPEN as the timestamp.
    bar_close_time = bar_open + timeframe_seconds prevents look-ahead leakage
    when joining HTF events to LTF events.
"""
from __future__ import annotations

import pandas as pd
from typing import Optional


_TF_SECONDS = {
    "1": 60, "2": 120, "3": 180, "5": 300, "15": 900,
    "30": 1800, "60": 3600, "240": 14400,
    "D": 86400, "1D": 86400,
}

_COLUMN_ALIASES = {"Type": "htf_event_type"}


def timeframe_seconds(tf: str) -> int:
    """Convert '5', '5m', '60', '1D' etc. to seconds."""
    key = tf.rstrip("mM")
    if key in _TF_SECONDS:
        return _TF_SECONDS[key]
    raise ValueError(f"Unknown timeframe: {tf!r}")


def compute_bar_close_time(
    df: pd.DataFrame,
    tf_col: str = "Timeframe",
    ts_col: str = "Raw_Timestamp",
) -> pd.DataFrame:
    """Return a copy of df with a 'bar_close_time' column added.

    bar_close_time = bar_open_timestamp + timeframe_seconds(timeframe)
    """
    if tf_col not in df.columns:
        raise KeyError(f"Column {tf_col!r} not in DataFrame")
    if ts_col not in df.columns:
        raise KeyError(f"Column {ts_col!r} not in DataFrame")

    out = df.copy()
    out["bar_close_time"] = out.apply(
        lambda r: int(r[ts_col]) + timeframe_seconds(str(r[tf_col])),
        axis=1,
    )
    return out


def merge_asof_htf_to_ltf(
    ltf: pd.DataFrame,
    htf: pd.DataFrame,
    by: Optional[str] = None,
) -> pd.DataFrame:
    """Join each LTF row to the most recent HTF event whose bar has already CLOSED.

    Both DataFrames must have 'bar_close_time' (call compute_bar_close_time first).
    HTF columns are prefixed with 'htf_' to avoid name collisions.
    Note: the HTF `Type` column is renamed to `htf_event_type` for clarity.

    Parameters
    ----------
    ltf : DataFrame  — LTF events with 'bar_close_time'
    htf : DataFrame  — HTF events with 'bar_close_time'
    by  : str, optional — join key (e.g. 'Instrument') to prevent cross-instrument pollution
    """
    if "bar_close_time" not in ltf.columns:
        raise KeyError("ltf must have 'bar_close_time' — call compute_bar_close_time first")
    if "bar_close_time" not in htf.columns:
        raise KeyError("htf must have 'bar_close_time' — call compute_bar_close_time first")

    # Set bar_close_time as index so merge_asof uses it cleanly.
    # We keep it as a column in the output by resetting afterward.
    ltf_sorted = ltf.sort_values("bar_close_time").reset_index(drop=True)
    htf_sorted = htf.sort_values("bar_close_time").reset_index(drop=True)

    # Rename HTF columns (except join keys) with htf_ prefix.
    # bar_close_time is excluded from keep_as_is so it gets renamed here;
    # it becomes htf_bar_close_time (right index post-merge). We need it
    # also as a column for the time_gap filter, so save it before renaming.
    # "Type" is aliased to "htf_event_type" for clarity at join sites.
    keep_as_is = set()
    if by is not None:
        keep_as_is.add(by)

    # Save bar_close_time values before the rename consumes the column.
    _bct_values = htf_sorted["bar_close_time"].values.copy()

    rename_map = {}
    for c in htf_sorted.columns:
        if c in keep_as_is:
            continue
        if c in _COLUMN_ALIASES:
            rename_map[c] = _COLUMN_ALIASES[c]
        elif c == "bar_close_time":
            rename_map[c] = "htf_bar_close_time"
        else:
            rename_map[c] = f"htf_{c.lower()}"
    htf_renamed = htf_sorted.rename(columns=rename_map)

    # Re-attach bar_close_time values as a named column so they survive set_index.
    htf_renamed["htf_bar_close_time"] = _bct_values

    # Use index-based merge_asof. Left index is bar_close_time (LTF close).
    # Right index is htf_bar_close_time (HTF close). The merge is an
    # asof join: for each LTF close, find the most recent HTF close ≤ it.
    # drop=False keeps htf_bar_close_time as both an index and a column.
    return pd.merge_asof(
        ltf_sorted.set_index("bar_close_time"),
        htf_renamed.set_index("htf_bar_close_time", drop=False),
        left_index=True,
        right_index=True,
        by=by,
        direction="backward",
        allow_exact_matches=True,
    )
