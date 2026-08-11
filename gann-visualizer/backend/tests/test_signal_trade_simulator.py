import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from analysis.signal_trade_simulator import CandleSignal, simulate_trade_grid


def _signal_keys(result):
    return list(result["per_signal"].keys())


def _valid_candles(start_bar_index=10):
    return pd.DataFrame(
        {
            "bar_index": [start_bar_index, start_bar_index + 1, start_bar_index + 2],
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
        }
    )


def _valid_signal(bar_index=10):
    return CandleSignal(
        bar_index=bar_index,
        side="LONG",
        entry_price=100.0,
        stop_price=99.0,
        signal_time="2026-07-10T10:15:00",
    )


def test_trade_grid_marks_target_hit_as_win_when_net_pnl_positive():
    candles = pd.DataFrame(
        {
            "bar_index": [10, 11, 12, 13],
            "open": [100, 101, 102, 103],
            "high": [101, 104, 108, 109],
            "low": [99, 100, 101, 102],
            "close": [100, 103, 107, 108],
        }
    )
    signal = CandleSignal(
        bar_index=10,
        side="LONG",
        entry_price=100.0,
        stop_price=99.0,
        signal_time="2026-07-10T10:15:00",
    )

    result = simulate_trade_grid(candles, [signal], r_values=[1.0, 2.0], max_hold_bars=3)
    signal_key = "10:0"

    assert result["best"]["r_value"] == 2.0
    assert result["best"]["wins"] == 1
    assert result["best"]["net_pnl_total"] > 0
    assert result["all_r_results"][0]["n"] == 1
    assert _signal_keys(result) == [signal_key]
    assert result["per_signal"][signal_key]["outcome"] == "WIN"
    assert result["per_signal"][signal_key]["exit_reason"] == "target"
    assert result["per_signal"][signal_key]["net_pnl"] > 0


def test_trade_grid_marks_stop_loss_as_loss():
    candles = pd.DataFrame(
        {
            "bar_index": [20, 21, 22],
            "open": [200, 199, 198],
            "high": [201, 200, 199],
            "low": [199, 196, 195],
            "close": [200, 196, 195],
        }
    )
    signal = CandleSignal(
        bar_index=20,
        side="LONG",
        entry_price=200.0,
        stop_price=198.0,
        signal_time="2026-07-10T11:00:00",
    )

    result = simulate_trade_grid(candles, [signal], r_values=[1.0], max_hold_bars=2)
    signal_key = "20:0"

    assert _signal_keys(result) == [signal_key]
    assert result["per_signal"][signal_key]["outcome"] == "LOSS"
    assert result["per_signal"][signal_key]["exit_reason"] == "stop_loss"
    assert result["per_signal"][signal_key]["net_pnl"] < 0
    assert result["best"]["losses"] == 1
    assert result["best"]["gross_loss"] == 2.0


def test_trade_grid_returns_r_grid_summary_and_best_per_signal_choice():
    candles = pd.DataFrame(
        {
            "bar_index": [30, 31, 32, 33],
            "open": [100, 100.5, 200, 199.5],
            "high": [100.5, 101.5, 200.5, 201.0],
            "low": [99.5, 100.2, 199.5, 198.0],
            "close": [100, 101.2, 200, 198.5],
        }
    )
    signals = [
        CandleSignal(
            bar_index=30,
            side="LONG",
            entry_price=100.0,
            stop_price=99.0,
            signal_time="2026-07-10T12:00:00",
        ),
        CandleSignal(
            bar_index=32,
            side="SHORT",
            entry_price=200.0,
            stop_price=202.0,
            signal_time="2026-07-10T12:30:00",
        ),
    ]

    result = simulate_trade_grid(candles, signals, r_values=[1.0, 2.0], max_hold_bars=1)

    assert set(result.keys()) == {
        "best", "hindsight_best", "selected_r", "all_r_results", "per_signal",
    }
    assert len(result["all_r_results"]) == 2
    assert [row["r_value"] for row in result["all_r_results"]] == [1.0, 2.0]
    assert result["best"]["r_value"] == 1.0
    assert result["best"]["n"] == 2
    assert result["best"]["wins"] == 2
    assert _signal_keys(result) == ["30:0", "32:1"]
    assert result["per_signal"]["30:0"]["r_value"] == 1.0
    assert result["per_signal"]["32:1"]["side"] == "SHORT"


def test_trade_grid_keeps_distinct_signals_from_same_bar_in_per_signal_results():
    candles = pd.DataFrame(
        {
            "bar_index": [40, 41],
            "open": [100, 100],
            "high": [100.5, 102.5],
            "low": [99.5, 99.2],
            "close": [100, 101.5],
        }
    )
    signals = [
        CandleSignal(
            bar_index=40,
            side="LONG",
            entry_price=100.0,
            stop_price=99.0,
            signal_time="2026-07-10T13:00:00",
        ),
        CandleSignal(
            bar_index=40,
            side="LONG",
            entry_price=100.0,
            stop_price=98.0,
            signal_time="2026-07-10T13:00:30",
        ),
    ]

    result = simulate_trade_grid(candles, signals, r_values=[1.0], max_hold_bars=1)

    assert _signal_keys(result) == ["40:0", "40:1"]
    assert result["best"]["n"] == 2
    assert result["per_signal"]["40:0"]["target_price"] == 101.0
    assert result["per_signal"]["40:0"]["exit_reason"] == "target"
    assert result["per_signal"]["40:1"]["target_price"] == 102.0
    assert result["per_signal"]["40:1"]["exit_reason"] == "target"


def test_trade_grid_exits_at_last_close_when_data_ends_before_max_hold():
    candles = pd.DataFrame(
        {
            "bar_index": [50, 51, 52],
            "open": [100, 100.5, 101.0],
            "high": [100.5, 101.5, 102.0],
            "low": [99.5, 100.0, 100.5],
            "close": [100.0, 101.0, 101.5],
        }
    )
    signal = CandleSignal(
        bar_index=50,
        side="LONG",
        entry_price=100.0,
        stop_price=99.0,
        signal_time="2026-07-10T14:00:00",
    )

    result = simulate_trade_grid(candles, [signal], r_values=[5.0], max_hold_bars=5)
    trade = result["per_signal"]["50:0"]

    assert trade["exit_bar_index"] == 52
    assert trade["exit_price"] == 101.5
    assert trade["exit_reason"] == "end_of_data"
    assert trade["outcome"] == "WIN"


@pytest.mark.parametrize(
    ("signal", "message"),
    [
        (
            CandleSignal(
                bar_index=60,
                side="LONG",
                entry_price=100.0,
                stop_price=101.0,
                signal_time="2026-07-10T15:00:00",
            ),
            "invalid stop orientation",
        ),
        (
            CandleSignal(
                bar_index=60,
                side="SHORT",
                entry_price=100.0,
                stop_price=99.0,
                signal_time="2026-07-10T15:05:00",
            ),
            "invalid stop orientation",
        ),
    ],
)
def test_trade_grid_rejects_invalid_stop_orientation(signal, message):
    candles = pd.DataFrame(
        {
            "bar_index": [60, 61],
            "open": [100.0, 100.5],
            "high": [101.0, 101.5],
            "low": [99.5, 100.0],
            "close": [100.5, 101.0],
        }
    )

    with pytest.raises(ValueError, match=message):
        simulate_trade_grid(candles, [signal], r_values=[1.0], max_hold_bars=1)


def _flat_candles(n=8, start_bar_index=0):
    """Candles that drift nowhere, so neither stop nor target is ever hit."""
    return pd.DataFrame(
        {
            "bar_index": list(range(start_bar_index, start_bar_index + n)),
            "open": [100.0] * n,
            "high": [100.5] * n,
            "low": [99.5] * n,
            "close": [100.0] * n,
        }
    )


def test_per_signal_max_hold_bars_truncates_the_window():
    candles = _flat_candles(n=8)
    signal = CandleSignal(
        bar_index=0,
        side="LONG",
        entry_price=100.0,
        stop_price=90.0,
        signal_time="2026-08-07T09:35:00",
        max_hold_bars=2,
    )

    result = simulate_trade_grid(
        candles=candles,
        signals=[signal],
        r_values=[2.0],
        max_hold_bars=7,
    )

    trade = result["best"]["per_signal"]["0:0"]
    assert trade["exit_bar_index"] == 2
    assert trade["exit_reason"] == "max_hold"


def test_omitting_max_hold_bars_uses_the_global_limit():
    candles = _flat_candles(n=8)
    signal = CandleSignal(
        bar_index=0,
        side="LONG",
        entry_price=100.0,
        stop_price=90.0,
        signal_time="2026-08-07T09:35:00",
    )

    result = simulate_trade_grid(
        candles=candles,
        signals=[signal],
        r_values=[2.0],
        max_hold_bars=4,
    )

    trade = result["best"]["per_signal"]["0:0"]
    assert trade["exit_bar_index"] == 4
    assert trade["exit_reason"] == "max_hold"


def test_non_positive_per_signal_max_hold_bars_is_rejected():
    candles = _flat_candles(n=8)
    signal = CandleSignal(
        bar_index=0,
        side="LONG",
        entry_price=100.0,
        stop_price=90.0,
        signal_time="2026-08-07T09:35:00",
        max_hold_bars=0,
    )

    with pytest.raises(ValueError, match="max_hold_bars"):
        simulate_trade_grid(
            candles=candles,
            signals=[signal],
            r_values=[2.0],
            max_hold_bars=7,
        )
