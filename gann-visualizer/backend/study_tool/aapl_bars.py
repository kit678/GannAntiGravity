"""
AAPL 1-minute regular-hours bars, resampled into the 5-minute bar cache.

AAPL is the fresh holdout for the Square-of-9 ladder (spec:
docs/superpowers/specs/2026-10-16-gann-breach-definition-sweep-design.md).
The source is Alpaca 1-minute bars filtered to 09:30-16:00 New York
(`data_local/aapl_rth_1m.json` in the main checkout; key `time` = UTC epoch
seconds of the minute's start).

Sessions are New York calendar dates, so DST needs no special case: each
bucket start is computed from the minute's own epoch, never from a fixed UTC
offset. Buckets are 5 minutes from 09:30 and never span two sessions, because
a session never crosses midnight.

Early closes: the source keeps 13:00-16:00 minutes on NYSE half-days. Those
are extended-hours prints (median 1-minute volume about 1,000 against about
50,000 before 13:00 on the same days, checked 2026-10-16), so they are
dropped and counted.
"""

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, Tuple, Union

import pandas as pd

from study_tool.bar_cache import cache_path, load_bars

NEW_YORK = "America/New_York"
SESSION_OPEN_MINUTE = 9 * 60 + 30     # 09:30
SESSION_MINUTES = 390                 # 09:30-16:00
EARLY_CLOSE_MINUTES = 210             # 09:30-13:00
BUCKET_MINUTES = 5
MINUTE_COLUMNS = ["time", "open", "high", "low", "close", "volume"]
BAR_COLUMNS = ["open", "high", "low", "close", "volume", "timestamp"]

# NYSE 1 p.m. closes inside 2024-09-02..2026-09-01. 2026-07-02 traded a full
# day in the source and is not one.
NYSE_EARLY_CLOSES: FrozenSet[str] = frozenset({
    "2024-11-29", "2024-12-24", "2025-07-03", "2025-11-28", "2025-12-24",
})


@dataclass(frozen=True)
class Resampled:
    bars: pd.DataFrame
    sessions: int
    early_close_minutes_dropped: int
    # bars in a session -> how many sessions had that many (78 on a normal
    # day, 42 on an early close). Missing minutes are acceptable, so this is
    # reported, never enforced.
    bars_per_session: Dict[int, int] = field(default_factory=dict)


def read_minute_json(path: Union[str, Path]) -> pd.DataFrame:
    """The `candles` list of the Alpaca JSON as a frame."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    candles = data.get("candles") if isinstance(data, dict) else None
    if not candles:
        raise ValueError(f"{path} has no 'candles' list")
    frame = pd.DataFrame(candles)
    missing = [c for c in MINUTE_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"{path} candles are missing {missing}")
    return frame.loc[:, MINUTE_COLUMNS]


def _new_york(minutes: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    """(New York date as YYYY-MM-DD, minutes since 09:30) for every row."""
    local = (pd.to_datetime(minutes["time"], unit="s", utc=True)
             .dt.tz_convert(NEW_YORK))
    dates = local.dt.strftime("%Y-%m-%d")
    offsets = local.dt.hour * 60 + local.dt.minute - SESSION_OPEN_MINUTE
    return dates, offsets


def resample_to_5m(minutes: pd.DataFrame, from_date: str, to_date: str,
                   early_closes: FrozenSet[str] = NYSE_EARLY_CLOSES) -> Resampled:
    """
    5-minute bars for New York dates from_date..to_date inclusive.

    Bar timestamp = bucket start as UTC epoch seconds, float (the corpus
    convention, as in the RELIANCE cache). open first, high max, low min,
    close last, volume sum.

    Raises:
        ValueError: on two minutes with the same `time`, a minute not on a
            whole minute, or one outside 09:30-16:00 New York. The source is meant to be regular hours only; a stray
            premarket print would open a bucket before 09:30.
    """
    frame = minutes.sort_values("time", kind="stable").reset_index(drop=True)
    dates, offsets = _new_york(frame)

    in_window = (dates >= from_date) & (dates <= to_date)
    frame, dates, offsets = frame[in_window], dates[in_window], offsets[in_window]
    if frame.empty:
        raise ValueError(f"no minutes between {from_date} and {to_date}")
    repeated = frame["time"].duplicated()
    if repeated.any():
        raise ValueError(
            f"{int(repeated.sum())} duplicate minute(s), the first at epoch "
            f"{int(frame.loc[repeated, 'time'].iloc[0])}")
    if (frame["time"] % 60 != 0).any():
        raise ValueError("a minute timestamp is not on a whole minute")

    outside = (offsets < 0) | (offsets >= SESSION_MINUTES)
    if outside.any():
        first = int(frame.loc[outside, "time"].iloc[0])
        raise ValueError(
            f"minute at epoch {first} is outside 09:30-16:00 New York")

    late = dates.isin(early_closes) & (offsets >= EARLY_CLOSE_MINUTES)
    dropped = int(late.sum())
    frame, dates, offsets = frame[~late], dates[~late], offsets[~late]

    bucket_start = frame["time"] - (offsets % BUCKET_MINUTES) * 60
    grouped = frame.assign(bucket=bucket_start).groupby("bucket", sort=True)
    bars = pd.DataFrame({
        "open": grouped["open"].first(),
        "high": grouped["high"].max(),
        "low": grouped["low"].min(),
        "close": grouped["close"].last(),
        "volume": grouped["volume"].sum(),
    }).reset_index().rename(columns={"bucket": "timestamp"})
    bars = bars.astype(float)

    bar_dates, _ = _new_york(bars.rename(columns={"timestamp": "time"}))
    per_session = bar_dates.value_counts().value_counts()
    histogram = {int(n): int(per_session[n])
                 for n in sorted(per_session.index, reverse=True)}

    return Resampled(bars=bars.loc[:, BAR_COLUMNS].reset_index(drop=True),
                     sessions=int(dates.nunique()),
                     early_close_minutes_dropped=dropped,
                     bars_per_session=histogram)


def session_close(minutes: pd.DataFrame, date: str,
                  early_closes: FrozenSet[str] = NYSE_EARLY_CLOSES) -> float:
    """
    The last 1-minute close on one New York date, regular session only: on a
    listed early-close day the minutes from 13:00 on are extended-hours
    prints and are ignored, as in resample_to_5m.
    """
    dates, offsets = _new_york(minutes)
    on_day = dates == date
    if date in early_closes:
        on_day = on_day & (offsets < EARLY_CLOSE_MINUTES)
    day = minutes[on_day]
    if day.empty:
        raise ValueError(f"no minutes on {date}")
    return float(day.sort_values("time")["close"].iloc[-1])


def last_close_before(minutes: pd.DataFrame,
                      from_date: str) -> Tuple[str, float]:
    """
    (New York date, close) of the last minute before `from_date`.

    The x6 scale is fixed from this, data before the window, never from the
    window itself.
    """
    dates, _ = _new_york(minutes)
    before = minutes[dates < from_date]
    if before.empty:
        raise ValueError(f"no minutes before {from_date}")
    last = before["time"].idxmax()
    return str(dates[last]), float(before.loc[last, "close"])


def write_bar_cache(bars: pd.DataFrame, symbol: str, from_date: str,
                    to_date: str, interval: str,
                    cache_dir: Union[str, Path],
                    overwrite: bool = False) -> pd.DataFrame:
    """
    Put the bars where build_gann_corpus looks for them.

    Goes through bar_cache.load_bars with a fetcher that returns these bars,
    so the existing code adds sun_degree / moon_degree and writes the file
    atomically, and a later build is a plain cache hit that never calls Dhan.
    """
    path = cache_path(cache_dir, symbol, from_date, to_date, interval)
    if not path.exists():
        return load_bars(symbol, from_date, to_date, interval,
                         cache_dir=cache_dir, fetcher=lambda *_: bars)
    if not overwrite:
        raise FileExistsError(
            f"{path} already exists; pass overwrite=True to replace it")

    # Build beside the old file and swap it in only once the build worked, so
    # a failure leaves the old cache untouched.
    staging = Path(cache_dir) / f".staging.{os.getpid()}"
    try:
        built = load_bars(symbol, from_date, to_date, interval,
                          cache_dir=staging, fetcher=lambda *_: bars)
        os.replace(cache_path(staging, symbol, from_date, to_date, interval),
                   path)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return built
