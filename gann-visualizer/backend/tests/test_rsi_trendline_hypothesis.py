import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd

from analysis.rsi_trendline_hypothesis import RSITrendlineBreakHypothesis, swing_stop_price


def test_swing_stop_uses_the_lowest_low_in_the_lookback_for_a_long():
    candles = pd.DataFrame({
        "bar_index": list(range(6)),
        "high": [105.0, 106.0, 107.0, 108.0, 109.0, 110.0],
        "low": [100.0, 96.0, 99.0, 101.0, 103.0, 104.0],
    })

    stop = swing_stop_price(candles, bar_index=5, side="LONG", lookback=5, buffer=0.0)

    assert stop == 96.0


def test_swing_stop_uses_the_highest_high_in_the_lookback_for_a_short():
    candles = pd.DataFrame({
        "bar_index": list(range(6)),
        "high": [105.0, 112.0, 107.0, 108.0, 109.0, 110.0],
        "low": [100.0, 96.0, 99.0, 101.0, 103.0, 104.0],
    })

    stop = swing_stop_price(candles, bar_index=5, side="SHORT", lookback=5, buffer=0.0)

    assert stop == 112.0


def test_swing_stop_applies_the_buffer_outward():
    candles = pd.DataFrame({
        "bar_index": [0, 1],
        "high": [110.0, 110.0],
        "low": [100.0, 100.0],
    })

    long_stop = swing_stop_price(candles, bar_index=1, side="LONG", lookback=2, buffer=0.01)
    short_stop = swing_stop_price(candles, bar_index=1, side="SHORT", lookback=2, buffer=0.01)

    assert long_stop == 99.0
    assert short_stop == 111.1


def build_trending_candles(bars=420):
    """Rising price with regular pullbacks -- produces RSI peaks and breaks."""
    rows = []
    price = 100.0
    for i in range(bars):
        price += 0.9 if (i % 11) < 8 else -1.6
        rows.append({
            "bar_index": i,
            "time": pd.Timestamp("2026-01-01") + pd.Timedelta(minutes=15 * i),
            "open": price,
            "high": price + 0.8,
            "low": price - 0.8,
            "close": price,
            "volume": 1.0,
        })
    return pd.DataFrame(rows)


def test_hypothesis_returns_a_trade_scored_result_with_a_line_timeline():
    result = RSITrendlineBreakHypothesis().evaluate(pd.DataFrame(), candles_df=build_trending_candles())

    assert result["trade_scored"] is True
    assert "exit_optimization" in result
    assert isinstance(result["detailed_log"], list)
    assert isinstance(result["line_timeline"], list)
    assert isinstance(result["rsi_series"], list)
    assert isinstance(result["skipped"], dict)


def test_every_signal_links_to_a_segment_in_the_timeline():
    result = RSITrendlineBreakHypothesis().evaluate(pd.DataFrame(), candles_df=build_trending_candles())

    timeline_ids = {segment["segment_id"] for segment in result["line_timeline"]}
    assert result["detailed_log"], "expected at least one trade-scored signal"

    for entry in result["detailed_log"]:
        assert entry["segment_id"] in timeline_ids
        assert entry["stop_rule"] == "swing_extreme"
        assert entry["swing_lookback"] == 20
        for field in ("rsi_value", "stop_price", "best_r", "entry_price", "outcome", "net_pnl"):
            assert field in entry


def test_timeline_segments_carry_a_validity_window_and_anchors():
    result = RSITrendlineBreakHypothesis().evaluate(pd.DataFrame(), candles_df=build_trending_candles())

    assert result["line_timeline"]
    for segment in result["line_timeline"]:
        assert segment["valid_from_bar"] <= segment["valid_to_bar"]
        assert segment["direction"] in ("up", "down")
        assert segment["end_reason"] in ("broken", "re_anchored", "end_of_data")
        assert segment["anchor_a"]["bar_index"] < segment["anchor_b"]["bar_index"]


def test_empty_candles_return_an_empty_result_without_raising():
    result = RSITrendlineBreakHypothesis().evaluate(pd.DataFrame(), candles_df=pd.DataFrame())

    assert result["sample_size"] == 0
    assert result["detailed_log"] == []
    assert result["line_timeline"] == []
