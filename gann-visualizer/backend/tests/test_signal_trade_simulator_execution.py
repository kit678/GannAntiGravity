"""Execution realism in the shared trade model.

Three things the simulator could not previously express, each of which made
every hypothesis using it look better than it was:

* entering at the signal bar's close, which is a fill you cannot get -- the
  signal is only knowable once that bar has closed
* charging one fee rate for every exit, when a resting target is a maker fill
  and a stop is not
* reporting whichever R value won in hindsight as the headline
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from analysis.signal_trade_simulator import CandleSignal, simulate_trade_grid


def _candles(rows):
    frame = pd.DataFrame(rows, columns=["bar_index", "open", "high", "low", "close"])
    frame["time"] = ["t%d" % b for b in frame["bar_index"]]
    return frame


# --------------------------------------------------------------------- #
# entry timing
# --------------------------------------------------------------------- #

def test_next_bar_entry_is_exposed_on_its_own_bar():
    """Entering at bar 2's open means bar 2's low can stop you out."""
    candles = _candles([
        [0, 100.0, 100.0, 100.0, 100.0],
        [1, 100.0, 100.0, 100.0, 100.0],
        [2, 100.0, 100.0, 90.0, 95.0],   # gaps down through the stop on the entry bar
        [3, 95.0, 96.0, 95.0, 95.0],
    ])
    signal = CandleSignal(
        bar_index=1, side="LONG", entry_price=100.0, stop_price=99.0,
        signal_time="t1", entry_bar_index=2,
    )
    result = simulate_trade_grid(candles, [signal], [1.0], max_hold_bars=5)
    trade = result["per_signal"]["1:0"]
    assert trade["exit_reason"] == "stop_loss"
    assert trade["exit_bar_index"] == 2


def test_close_entry_is_not_exposed_on_the_signal_bar():
    """Default behaviour is unchanged: exposure starts the bar after the signal."""
    candles = _candles([
        [0, 100.0, 100.0, 100.0, 100.0],
        [1, 100.0, 100.0, 90.0, 100.0],  # signal bar dips below the stop
        [2, 100.0, 101.0, 100.0, 101.0],
        [3, 101.0, 102.0, 101.0, 102.0],
    ])
    signal = CandleSignal(
        bar_index=1, side="LONG", entry_price=100.0, stop_price=99.0, signal_time="t1",
    )
    result = simulate_trade_grid(candles, [signal], [1.0], max_hold_bars=5)
    trade = result["per_signal"]["1:0"]
    assert trade["exit_reason"] != "stop_loss"
    assert trade["exit_bar_index"] > 1


def test_entry_bar_index_is_reported_on_the_trade():
    candles = _candles([[b, 100.0, 101.0, 99.5, 100.0] for b in range(6)])
    signal = CandleSignal(
        bar_index=1, side="LONG", entry_price=100.0, stop_price=99.0,
        signal_time="t1", entry_bar_index=2,
    )
    trade = simulate_trade_grid(candles, [signal], [1.0], max_hold_bars=3)["per_signal"]["1:0"]
    assert trade["entry_bar_index"] == 2


def test_max_hold_counts_bars_from_the_entry_bar():
    """Two entry modes, same holding period -- 3 bars of exposure each."""
    flat = _candles([[b, 100.0, 100.5, 99.5, 100.0] for b in range(10)])

    close_entry = CandleSignal(1, "LONG", 100.0, 99.0, "t1")
    open_entry = CandleSignal(1, "LONG", 100.0, 99.0, "t1", entry_bar_index=2)

    a = simulate_trade_grid(flat, [close_entry], [5.0], max_hold_bars=3)["per_signal"]["1:0"]
    b = simulate_trade_grid(flat, [open_entry], [5.0], max_hold_bars=3)["per_signal"]["1:0"]

    assert a["exit_bar_index"] == 4   # bars 2,3,4
    assert b["exit_bar_index"] == 4   # bars 2,3,4
    assert a["exit_reason"] == "max_hold"
    assert b["exit_reason"] == "max_hold"


# --------------------------------------------------------------------- #
# maker / taker fees
# --------------------------------------------------------------------- #

def test_target_exit_pays_the_maker_fee():
    candles = _candles([
        [0, 100.0, 100.0, 100.0, 100.0],
        [1, 100.0, 100.0, 100.0, 100.0],
        [2, 100.0, 102.0, 100.0, 101.5],  # target 101 filled as a resting limit
    ])
    signal = CandleSignal(1, "LONG", 100.0, 99.0, "t1")
    trade = simulate_trade_grid(
        candles, [signal], [1.0], max_hold_bars=3,
        fee_rate=0.0004, maker_fee_rate=0.0002,
    )["per_signal"]["1:0"]

    assert trade["exit_reason"] == "target"
    assert trade["exit_is_maker"] is True
    assert trade["fees"] == round(100.0 * 0.0004 + 101.0 * 0.0002, 6)


def test_stop_exit_pays_the_taker_fee_on_both_sides():
    candles = _candles([
        [0, 100.0, 100.0, 100.0, 100.0],
        [1, 100.0, 100.0, 100.0, 100.0],
        [2, 100.0, 100.0, 98.0, 98.5],
    ])
    signal = CandleSignal(1, "LONG", 100.0, 99.0, "t1")
    trade = simulate_trade_grid(
        candles, [signal], [1.0], max_hold_bars=3,
        fee_rate=0.0004, maker_fee_rate=0.0002,
    )["per_signal"]["1:0"]

    assert trade["exit_reason"] == "stop_loss"
    assert trade["exit_is_maker"] is False
    assert trade["fees"] == round((100.0 + 99.0) * 0.0004, 6)


def test_maker_rate_defaults_to_the_taker_rate():
    candles = _candles([
        [0, 100.0, 100.0, 100.0, 100.0],
        [1, 100.0, 100.0, 100.0, 100.0],
        [2, 100.0, 102.0, 100.0, 101.5],
    ])
    signal = CandleSignal(1, "LONG", 100.0, 99.0, "t1")
    trade = simulate_trade_grid(
        candles, [signal], [1.0], max_hold_bars=3, fee_rate=0.0004,
    )["per_signal"]["1:0"]
    assert trade["fees"] == round((100.0 + 101.0) * 0.0004, 6)


# --------------------------------------------------------------------- #
# R selection
# --------------------------------------------------------------------- #

def _two_outcome_candles():
    # rises to +2R (102) then falls back; R=1 and R=2 both win, R=3 does not.
    return _candles([
        [0, 100.0, 100.0, 100.0, 100.0],
        [1, 100.0, 100.0, 100.0, 100.0],
        [2, 100.0, 102.0, 100.0, 100.2],
        [3, 100.2, 100.5, 100.0, 100.1],
    ])


def test_select_r_pins_the_headline_to_a_declared_r():
    signal = CandleSignal(1, "LONG", 100.0, 99.0, "t1")
    result = simulate_trade_grid(
        _two_outcome_candles(), [signal], [1.0, 2.0, 3.0],
        max_hold_bars=5, select_r=1.0,
    )
    assert result["best"]["r_value"] == 1.0
    assert result["selected_r"] == 1.0


def test_hindsight_best_is_reported_separately_from_the_selection():
    signal = CandleSignal(1, "LONG", 100.0, 99.0, "t1")
    result = simulate_trade_grid(
        _two_outcome_candles(), [signal], [1.0, 2.0, 3.0],
        max_hold_bars=5, select_r=1.0,
    )
    assert result["hindsight_best"]["r_value"] == 2.0
    assert result["hindsight_best"]["net_pnl_total"] > result["best"]["net_pnl_total"]


def test_without_select_r_the_headline_is_still_the_hindsight_best():
    """Unchanged default -- callers that have not opted in keep their behaviour."""
    signal = CandleSignal(1, "LONG", 100.0, 99.0, "t1")
    result = simulate_trade_grid(
        _two_outcome_candles(), [signal], [1.0, 2.0, 3.0], max_hold_bars=5,
    )
    assert result["best"]["r_value"] == 2.0
    assert result["selected_r"] is None


# --------------------------------------------------------------------- #
# R-multiple reporting
# --------------------------------------------------------------------- #

def test_trade_reports_its_realized_r_multiple():
    """Summing price deltas across a 60k BTC and a 24k index is meaningless."""
    candles = _candles([
        [0, 100.0, 100.0, 100.0, 100.0],
        [1, 100.0, 100.0, 100.0, 100.0],
        [2, 100.0, 102.0, 100.0, 101.5],
    ])
    signal = CandleSignal(1, "LONG", 100.0, 98.0, "t1")  # risk 2.0
    trade = simulate_trade_grid(candles, [signal], [1.0], max_hold_bars=3)["per_signal"]["1:0"]
    assert trade["net_r"] == 1.0


def test_r_summary_reports_expectancy_and_profit_factor():
    """One +1R winner and one -1R loser: expectancy 0, profit factor 1."""
    candles = _candles([
        [0, 100.0, 100.0, 100.0, 100.0],
        [1, 100.0, 100.0, 100.0, 100.0],
        [2, 100.0, 101.5, 100.0, 101.0],   # signal 1 hits +1R
        [3, 101.0, 101.0, 101.0, 101.0],
        [4, 101.0, 101.0, 101.0, 101.0],
        [5, 101.0, 101.0, 99.0, 99.5],     # signal 4 stopped at -1R
    ])
    signals = [
        CandleSignal(1, "LONG", 100.0, 99.0, "t1"),
        CandleSignal(3, "LONG", 101.0, 100.0, "t3"),
    ]
    result = simulate_trade_grid(candles, signals, [1.0], max_hold_bars=4)
    best = result["best"]
    assert best["n"] == 2
    assert best["expectancy_r"] == 0.0
    assert best["profit_factor"] == 1.0
    assert best["avg_win_r"] == 1.0
    assert best["avg_loss_r"] == 1.0
