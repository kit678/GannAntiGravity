"""
Fetch bars once, keep them on disk, and stamp each with the Sun and Moon.

Dhan access tokens expire every 24 hours and the data API is capped, so a
corpus build must never depend on refetching. The ephemeris is computed here
rather than at run time so a rebuilt corpus is reproducible from the cache
alone, with no ephemeris dependency and no clock involved.
"""

import os
from pathlib import Path
from typing import Callable, Optional, Union

import pandas as pd

from study_tool.ephemeris import sun_moon_longitudes

BAR_COLUMNS = ["open", "high", "low", "close", "volume", "timestamp"]


def _default_fetcher(symbol: str, from_date: str, to_date: str,
                     interval: str) -> pd.DataFrame:
    from dhan_client import DhanClient
    return DhanClient().fetch_data(symbol, from_date, to_date, interval=interval)


def _cache_path(cache_dir: Path, symbol: str, from_date: str,
                to_date: str, interval: str) -> Path:
    name = f"{symbol}_{interval}_{from_date}_{to_date}.parquet"
    return Path(cache_dir) / name


def load_bars(
    symbol: str,
    from_date: str,
    to_date: str,
    interval: str,
    cache_dir: Union[str, Path],
    fetcher: Optional[Callable[..., pd.DataFrame]] = None,
) -> pd.DataFrame:
    """
    Bars for one symbol and window, with `sun_degree` and `moon_degree` added.

    Reads the on-disk cache if present. Otherwise fetches, enriches, sorts,
    deduplicates and writes the cache.

    Raises:
        ValueError: if the fetch returned nothing. An expired token looks
            exactly like a quiet market, and caching an empty frame would
            silently produce a zero-event corpus later.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, symbol, from_date, to_date, interval)

    if path.exists():
        return pd.read_parquet(path)

    fetch = fetcher or _default_fetcher
    frame = fetch(symbol, from_date, to_date, interval)

    if frame is None or len(frame) == 0:
        raise ValueError(
            f"no bars returned for {symbol} {interval} {from_date}..{to_date} "
            "- check the Dhan access token has not expired"
        )

    frame = frame.loc[:, [c for c in BAR_COLUMNS if c in frame.columns]].copy()
    frame = (frame
             .drop_duplicates(subset="timestamp")
             .sort_values("timestamp")
             .reset_index(drop=True))

    longitudes = [sun_moon_longitudes(t) for t in frame["timestamp"]]
    frame["sun_degree"] = [s for s, _ in longitudes]
    frame["moon_degree"] = [m for _, m in longitudes]

    # Write to a temp file first and rename into place. A corpus build can run
    # for a long time and get killed mid-write; without this, a partial file
    # would sit at `path`, so the next run's `path.exists()` check would trust
    # it and hand back a broken cache instead of refetching. os.replace() is
    # atomic on both POSIX and Windows.
    tmp_path = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    frame.to_parquet(tmp_path, index=False)
    os.replace(tmp_path, path)
    return frame
