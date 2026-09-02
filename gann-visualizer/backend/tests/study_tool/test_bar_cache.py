"""
Bar fetching and caching.

The network is never touched in these tests. A fake fetcher is injected so the
cache's behaviour - fetch once, reuse forever, append the ephemeris - is
tested without a live Dhan token.
"""
import sys
import os

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.bar_cache import load_bars

NSE_OPEN_EPOCH = 1787629500


def fake_frame(n=5):
    return pd.DataFrame({
        "open": [1300.0 + i for i in range(n)],
        "high": [1301.0 + i for i in range(n)],
        "low": [1299.0 + i for i in range(n)],
        "close": [1300.5 + i for i in range(n)],
        "volume": [1000.0] * n,
        "timestamp": [float(NSE_OPEN_EPOCH + i * 300) for i in range(n)],
    })


class CountingFetcher:
    def __init__(self):
        self.calls = 0

    def __call__(self, symbol, from_date, to_date, interval):
        self.calls += 1
        return fake_frame()


def test_returns_bars_with_sun_and_moon_columns(tmp_path):
    bars = load_bars(
        "RELIANCE", "2026-08-25", "2026-08-26", "5",
        cache_dir=tmp_path, fetcher=CountingFetcher(),
    )
    for column in ("open", "high", "low", "close", "timestamp",
                   "sun_degree", "moon_degree"):
        assert column in bars.columns, f"missing {column}"
    assert len(bars) == 5


def test_second_call_does_not_refetch(tmp_path):
    fetcher = CountingFetcher()
    args = ("RELIANCE", "2026-08-25", "2026-08-26", "5")

    first = load_bars(*args, cache_dir=tmp_path, fetcher=fetcher)
    second = load_bars(*args, cache_dir=tmp_path, fetcher=fetcher)

    assert fetcher.calls == 1, "the cache refetched instead of reading disk"
    pd.testing.assert_frame_equal(first, second)


def test_bars_come_back_sorted_and_deduplicated(tmp_path):
    """Chunked fetches can overlap at the seams; the analyzer needs strict order."""
    def messy(symbol, from_date, to_date, interval):
        frame = fake_frame()
        return pd.concat([frame.iloc[2:], frame]).reset_index(drop=True)

    bars = load_bars(
        "RELIANCE", "2026-08-25", "2026-08-26", "5",
        cache_dir=tmp_path, fetcher=messy,
    )
    assert bars["timestamp"].is_monotonic_increasing
    assert not bars["timestamp"].duplicated().any()


def test_empty_fetch_raises_rather_than_caching_nothing(tmp_path):
    """
    An expired token returns an empty frame. Caching that would poison every
    later run with a silent zero-bar corpus.
    """
    with pytest.raises(ValueError, match="no bars"):
        load_bars(
            "RELIANCE", "2026-08-25", "2026-08-26", "5",
            cache_dir=tmp_path, fetcher=lambda *a, **k: pd.DataFrame(),
        )
    assert list(tmp_path.iterdir()) == [], (
        "a failed fetch must leave no file behind - a stray file at the cache "
        "path would look like a valid cache on the next run"
    )


def test_successful_write_leaves_only_the_final_cache_file(tmp_path):
    """
    The cache file is written via a temp file + rename so a process killed
    mid-write never leaves a partial .parquet sitting at the real cache path.
    A successful run should leave exactly that one file behind, no .tmp litter.
    """
    load_bars(
        "RELIANCE", "2026-08-25", "2026-08-26", "5",
        cache_dir=tmp_path, fetcher=CountingFetcher(),
    )
    written = list(tmp_path.iterdir())
    assert len(written) == 1
    assert written[0].suffix == ".parquet"
