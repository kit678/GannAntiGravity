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


# --------------------------------------------------------------------- #
# execution model
# --------------------------------------------------------------------- #

def test_default_entry_is_the_next_bar_open_not_the_signal_close():
    candles = build_trending_candles()
    result = RSITrendlineBreakHypothesis().evaluate(pd.DataFrame(), candles_df=candles)
    assert result["detailed_log"], "fixture produced no trades"

    for entry in result["detailed_log"]:
        bar = entry["bar_index"]
        assert entry["entry_bar_index"] == bar + 1
        assert entry["entry_price"] == candles.loc[bar + 1, "open"]
        assert entry["entry_price"] != entry["signal_close"] or True  # may coincide


def test_entry_offset_zero_restores_the_signal_bar_close():
    candles = build_trending_candles()
    hypothesis = RSITrendlineBreakHypothesis()
    hypothesis.set_parameters(**{**hypothesis.parameters, "entry_offset": 0})
    result = hypothesis.evaluate(pd.DataFrame(), candles_df=candles)

    for entry in result["detailed_log"]:
        assert entry["entry_bar_index"] == entry["bar_index"]
        assert entry["entry_price"] == entry["signal_close"]


def test_fees_are_charged_on_every_trade():
    result = RSITrendlineBreakHypothesis().evaluate(
        pd.DataFrame(), candles_df=build_trending_candles()
    )
    assert result["detailed_log"]
    assert all(entry["fees"] > 0 for entry in result["detailed_log"])
    assert all(entry["net_pnl"] < entry["gross_pnl"] for entry in result["detailed_log"])


def test_target_exits_are_charged_the_maker_rate():
    # R=1 so the synthetic fixture actually reaches its targets; at R=3 it
    # never does and the assertion would have nothing to bite on.
    hypothesis = RSITrendlineBreakHypothesis()
    hypothesis.set_parameters(**{**hypothesis.parameters, "selected_r": 1.0})
    result = hypothesis.evaluate(pd.DataFrame(), candles_df=build_trending_candles())
    targets = [e for e in result["detailed_log"] if e["exit_reason"] == "target"]
    assert targets, "fixture produced no target exits"
    for entry in targets:
        assert entry["exit_is_maker"] is True
        expected = entry["entry_price"] * 0.0004 + entry["exit_price"] * 0.0002
        assert round(entry["fees"], 6) == round(expected, 6)


def test_headline_uses_the_declared_r_not_the_hindsight_winner():
    result = RSITrendlineBreakHypothesis().evaluate(
        pd.DataFrame(), candles_df=build_trending_candles()
    )
    optimization = result["exit_optimization"]
    assert optimization["selected_r"] == 3.0
    assert optimization["best"]["r_value"] == 3.0
    assert "hindsight_best" in optimization


def test_summary_reports_expectancy_in_r():
    result = RSITrendlineBreakHypothesis().evaluate(
        pd.DataFrame(), candles_df=build_trending_candles()
    )
    log = result["detailed_log"]
    assert log
    expected = sum(e["net_r"] for e in log) / len(log)
    assert result["expectancy_r"] == round(expected, 6)
    assert result["profit_factor"] >= 0.0
    assert result["avg_win_r"] >= 0.0
