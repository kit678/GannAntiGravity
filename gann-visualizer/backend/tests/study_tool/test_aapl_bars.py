"""
AAPL 1-minute regular-hours bars resampled to the 5-minute corpus cache.

Small synthetic minutes only - never the 105 MB source file.
"""
import sys
import os
import json

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend/scripts'))

from study_tool.aapl_bars import (
    NYSE_EARLY_CLOSES, last_close_before, read_minute_json, resample_to_5m,
    session_close, write_bar_cache,
)
from study_tool.bar_cache import load_bars, no_fetch

FROM, TO = "2024-09-02", "2026-09-01"


def epoch(date, hm):
    """UTC epoch seconds of a New York wall-clock minute."""
    return int(pd.Timestamp(f"{date} {hm}", tz="America/New_York").timestamp())


def minutes(date, start_hm, count, base=100.0):
    start = epoch(date, start_hm)
    return [{"time": start + 60 * i, "open": base + i,
             "high": base + i + 0.5, "low": base + i - 0.5,
             "close": base + i + 0.25, "volume": 10.0 + i}
            for i in range(count)]


def frame(*chunks):
    return pd.DataFrame([row for chunk in chunks for row in chunk])


def test_buckets_start_at_0930_and_aggregate_ohlcv():
    result = resample_to_5m(frame(minutes("2025-03-07", "09:30", 10)), FROM, TO)
    bars = result.bars

    assert list(bars["timestamp"]) == [float(epoch("2025-03-07", "09:30")),
                                       float(epoch("2025-03-07", "09:35"))]
    assert list(bars["open"]) == [100.0, 105.0]
    assert list(bars["high"]) == [104.5, 109.5]
    assert list(bars["low"]) == [99.5, 104.5]
    assert list(bars["close"]) == [104.25, 109.25]
    assert list(bars["volume"]) == [60.0, 85.0]          # 10..14, 15..19
    assert list(bars.columns) == ["open", "high", "low", "close", "volume",
                                  "timestamp"]


def test_dst_moves_the_utc_timestamp_not_the_new_york_alignment():
    """2025-03-07 is EST (UTC-5), 2025-03-10 is EDT (UTC-4)."""
    result = resample_to_5m(frame(minutes("2025-03-07", "09:30", 5),
                                  minutes("2025-03-10", "09:30", 5)), FROM, TO)

    assert list(result.bars["timestamp"]) == [1741357800.0, 1741613400.0]


def test_a_bucket_never_spans_two_sessions():
    result = resample_to_5m(frame(minutes("2025-03-07", "15:57", 3),
                                  minutes("2025-03-10", "09:30", 2, base=200.0)),
                            FROM, TO)
    bars = result.bars

    assert list(bars["timestamp"]) == [float(epoch("2025-03-07", "15:55")),
                                       float(epoch("2025-03-10", "09:30"))]
    assert list(bars["volume"]) == [33.0, 21.0]
    assert list(bars["open"]) == [100.0, 200.0]
    assert result.sessions == 2


def test_an_early_close_day_drops_the_minutes_after_1300():
    assert "2024-12-24" in NYSE_EARLY_CLOSES

    result = resample_to_5m(frame(minutes("2024-12-24", "12:55", 15),
                                  minutes("2025-03-07", "13:00", 5)), FROM, TO)

    assert list(result.bars["timestamp"]) == [
        float(epoch("2024-12-24", "12:55")), float(epoch("2025-03-07", "13:00"))]
    assert result.early_close_minutes_dropped == 10


def test_the_window_is_inclusive_of_both_dates():
    result = resample_to_5m(frame(minutes("2024-08-30", "09:30", 1),
                                  minutes("2024-09-03", "09:30", 1),
                                  minutes("2026-09-01", "09:30", 1),
                                  minutes("2026-09-02", "09:30", 1)), FROM, TO)

    assert list(result.bars["timestamp"]) == [
        float(epoch("2024-09-03", "09:30")), float(epoch("2026-09-01", "09:30"))]
    assert result.sessions == 2


@pytest.mark.parametrize("hm", ["09:29", "16:00"])
def test_a_minute_outside_regular_hours_is_refused(hm):
    with pytest.raises(ValueError, match="outside 09:30-16:00"):
        resample_to_5m(frame(minutes("2025-03-07", hm, 1)), FROM, TO)


def test_the_closes_before_the_window_come_from_the_last_session():
    minutes_frame = frame(minutes("2024-08-30", "15:58", 2, base=228.0),
                          minutes("2024-09-03", "09:30", 1, base=230.0))

    assert last_close_before(minutes_frame, FROM) == ("2024-08-30", 229.25)
    assert session_close(minutes_frame, "2024-08-30") == 229.25


def test_read_minute_json_reads_the_candles_list(tmp_path):
    path = tmp_path / "aapl.json"
    path.write_text(json.dumps({"symbol": "AAPL", "source": "test",
                                "candles": minutes("2025-03-07", "09:30", 3)}))

    loaded = read_minute_json(path)

    assert list(loaded.columns) == ["time", "open", "high", "low", "close",
                                    "volume"]
    assert len(loaded) == 3


def test_read_minute_json_refuses_a_file_without_candles(tmp_path):
    path = tmp_path / "aapl.json"
    path.write_text(json.dumps({"symbol": "AAPL"}))

    with pytest.raises(ValueError, match="candles"):
        read_minute_json(path)


def test_the_cache_file_is_a_hit_for_load_bars(tmp_path):
    bars = resample_to_5m(frame(minutes("2025-03-07", "09:30", 10)),
                          FROM, TO).bars
    write_bar_cache(bars, "AAPL", FROM, TO, "5", tmp_path)

    cached = load_bars("AAPL", FROM, TO, "5", cache_dir=tmp_path,
                       fetcher=no_fetch)

    assert len(cached) == 2
    assert list(cached["timestamp"]) == list(bars["timestamp"])
    for column in ("sun_degree", "moon_degree"):
        assert cached[column].notna().all()


def test_write_bar_cache_refuses_to_replace_without_overwrite(tmp_path):
    bars = resample_to_5m(frame(minutes("2025-03-07", "09:30", 5)),
                          FROM, TO).bars
    write_bar_cache(bars, "AAPL", FROM, TO, "5", tmp_path)

    with pytest.raises(FileExistsError, match="overwrite"):
        write_bar_cache(bars, "AAPL", FROM, TO, "5", tmp_path)

    write_bar_cache(bars, "AAPL", FROM, TO, "5", tmp_path, overwrite=True)


def test_a_duplicate_minute_is_refused():
    rows = minutes("2025-03-07", "09:30", 3)
    rows.append(dict(rows[1]))

    with pytest.raises(ValueError, match="duplicate"):
        resample_to_5m(frame(rows), FROM, TO)


def test_integer_prices_and_volume_come_out_as_floats():
    rows = [{"time": epoch("2025-03-07", "09:30") + 60 * i, "open": 100 + i,
             "high": 101 + i, "low": 99 + i, "close": 100 + i, "volume": 5}
            for i in range(5)]

    bars = resample_to_5m(frame(rows), FROM, TO).bars

    for column in ("open", "high", "low", "close", "volume", "timestamp"):
        assert str(bars[column].dtype) == "float64", column


def test_bars_per_session_counts_a_normal_day_and_an_early_close():
    result = resample_to_5m(
        frame(minutes("2025-03-07", "09:30", 390),
              minutes("2024-12-24", "09:30", 390),
              minutes("2025-03-10", "09:30", 12)), FROM, TO)

    assert result.bars_per_session == {78: 1, 42: 1, 3: 1}
    assert result.early_close_minutes_dropped == 180


def test_session_close_on_an_early_close_day_ignores_late_prints():
    rows = frame(minutes("2024-12-24", "09:30", 390))

    # minute 209 is the last one before 13:00; its close is base + 209.25
    assert session_close(rows, "2024-12-24") == 100.0 + 209 + 0.25


def test_write_bar_cache_keeps_the_old_file_when_the_rebuild_fails(tmp_path):
    bars = resample_to_5m(frame(minutes("2025-03-07", "09:30", 5)),
                          FROM, TO).bars
    write_bar_cache(bars, "AAPL", FROM, TO, "5", tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    old = (tmp_path / before[0]).read_bytes()

    with pytest.raises(ValueError, match="no bars"):
        write_bar_cache(bars.iloc[0:0], "AAPL", FROM, TO, "5", tmp_path,
                        overwrite=True)

    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert (tmp_path / before[0]).read_bytes() == old


def test_write_bar_cache_overwrite_replaces_the_file(tmp_path):
    first = resample_to_5m(frame(minutes("2025-03-07", "09:30", 5)),
                           FROM, TO).bars
    second = resample_to_5m(frame(minutes("2025-03-07", "09:30", 10)),
                            FROM, TO).bars
    write_bar_cache(first, "AAPL", FROM, TO, "5", tmp_path)

    write_bar_cache(second, "AAPL", FROM, TO, "5", tmp_path, overwrite=True)

    cached = load_bars("AAPL", FROM, TO, "5", cache_dir=tmp_path,
                       fetcher=no_fetch)
    assert len(cached) == 2
    assert [p.name for p in tmp_path.iterdir()] == [
        "AAPL_5_2024-09-02_2026-09-01.parquet"]
