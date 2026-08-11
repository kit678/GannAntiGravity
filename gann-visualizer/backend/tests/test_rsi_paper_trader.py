"""Position bookkeeping in the paper trader.

Both cases here were live bugs caught by reconciling the replay against the
backtest, and both are silent -- they change PnL without erroring.
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from run_rsi_paper import RSIPaperTrader


def _bar(high, low, close, time="t"):
    return pd.Series({"high": high, "low": low, "close": close, "time": time})


def _trader(tmpdir="."):
    return RSIPaperTrader("BTCUSDT", "4h",
                          state_path=os.path.join(tmpdir, "_unused_state.json"))


def _position(trader, side="LONG", entry=100.0, stop=99.0, target=103.0):
    position = {
        "symbol": "BTCUSDT", "side": side, "signal_bar_time": "t0",
        "entry_bar_index": 1, "entry_price": entry, "stop_price": stop,
        "target_price": target, "risk_per_unit": abs(entry - stop),
        "risk_pct": abs(entry - stop) / entry, "quantity": 1.0,
        "bars_held": 0, "rsi_at_break": 55.0, "line_value_at_break": 54.0,
        "opened_at": "t0",
    }
    trader.open_positions.append(position)
    return position


# --------------------------------------------------------------------- #
# exposure
# --------------------------------------------------------------------- #

def test_stop_is_taken_before_target_on_a_bar_that_spans_both():
    """Assume the worse fill. Anything else quietly inflates the result."""
    trader = _trader()
    _position(trader)
    closed = trader.update_positions(_bar(high=105.0, low=98.0, close=104.0))
    assert len(closed) == 1
    assert closed[0]["exit_reason"] == "stop_loss"
    assert closed[0]["net_r"] < 0


def test_max_hold_exits_after_exactly_max_hold_bars():
    trader = _trader()
    _position(trader)
    flat = _bar(high=100.2, low=99.8, close=100.0)
    for _ in range(trader.max_hold - 1):
        assert trader.update_positions(flat) == []
    closed = trader.update_positions(flat)
    assert len(closed) == 1
    assert closed[0]["exit_reason"] == "max_hold"
    assert closed[0]["bars_held"] == trader.max_hold


def test_a_gap_straight_through_the_stop_exits_at_the_stop():
    trader = _trader()
    _position(trader)
    closed = trader.update_positions(_bar(high=100.1, low=90.0, close=95.0))
    assert len(closed) == 1
    assert closed[0]["exit_reason"] == "stop_loss"
    # Filled at the stop, not at the gap low -- this model does not simulate
    # slippage through a gap, and must not pretend it fills better either.
    assert closed[0]["exit_price"] == 99.0


def test_short_stops_out_on_a_move_up():
    trader = _trader()
    _position(trader, side="SHORT", entry=100.0, stop=101.0, target=97.0)
    closed = trader.update_positions(_bar(high=102.0, low=99.5, close=101.5))
    assert closed[0]["exit_reason"] == "stop_loss"


def test_short_reaches_its_target_on_a_move_down():
    trader = _trader()
    _position(trader, side="SHORT", entry=100.0, stop=101.0, target=97.0)
    closed = trader.update_positions(_bar(high=100.2, low=96.5, close=96.8))
    assert closed[0]["exit_reason"] == "target"
    assert closed[0]["net_r"] > 0


# --------------------------------------------------------------------- #
# fees, matching the backtest exactly
# --------------------------------------------------------------------- #

def test_target_exit_pays_maker_and_stop_exit_pays_taker():
    trader = _trader()
    _position(trader)
    target_exit = trader.update_positions(_bar(high=103.5, low=99.5, close=103.2))[0]
    assert target_exit["exit_is_maker"] is True
    assert target_exit["fees"] == round(100.0 * trader.taker + 103.0 * trader.maker, 6)

    trader.open_positions.clear()
    _position(trader)
    stop_exit = trader.update_positions(_bar(high=100.2, low=98.0, close=98.5))[0]
    assert stop_exit["exit_is_maker"] is False
    assert stop_exit["fees"] == round(100.0 * trader.taker + 99.0 * trader.taker, 6)


def test_net_r_uses_the_same_rounding_as_the_backtest():
    """A tiny per-unit risk amplifies 6dp rounding; both sides must round alike."""
    trader = _trader()
    _position(trader, entry=0.167, stop=0.16461765, target=0.17414705)
    closed = trader.update_positions(_bar(high=0.18, low=0.166, close=0.175))[0]
    cost = 0.167 * trader.taker + closed["exit_price"] * trader.maker
    expected_net = round((closed["exit_price"] - 0.167) - cost, 6)
    assert closed["net_pnl"] == expected_net
    assert closed["net_r"] == round(expected_net / closed["risk_per_unit"], 6)


# --------------------------------------------------------------------- #
# polling the same bar twice
# --------------------------------------------------------------------- #

def test_polling_twice_within_one_bar_does_not_age_positions_twice():
    """The loop polls more often than the bar period, so it re-sees bars.

    Marking the same closed bar twice doubles every holding period and fires
    max_hold exits at half the true age. Silent, and it shortens every trade.
    """
    import run_rsi_paper

    frame = pd.DataFrame({
        "timestamp": [0, 1], "open": [100.0, 100.0], "high": [100.2, 100.2],
        "low": [99.8, 99.8], "close": [100.0, 100.0], "volume": [1.0, 1.0],
        "close_ms": [0, 1], "time": ["t0", "t1"], "bar_index": [0, 1],
    })

    trader = _trader()
    position = _position(trader)
    original_fetch = run_rsi_paper.fetch_klines
    run_rsi_paper.fetch_klines = lambda *a, **k: frame.copy()
    trader.save = lambda: None
    trader.signals_on_bar = lambda *a, **k: []
    try:
        run_rsi_paper.poll_once(trader, verbose=False)
        run_rsi_paper.poll_once(trader, verbose=False)
        run_rsi_paper.poll_once(trader, verbose=False)
    finally:
        run_rsi_paper.fetch_klines = original_fetch

    assert position["bars_held"] == 1


# --------------------------------------------------------------------- #
# sizing
# --------------------------------------------------------------------- #

def test_size_scales_inversely_with_stop_distance():
    """Risk per trade is fixed; a wider stop must buy less, not risk more."""
    trader = RSIPaperTrader("BTCUSDT", "4h", risk_fraction=0.01, equity=10000.0)
    tight = trader._size(entry_price=100.0, risk=1.0)
    wide = trader._size(entry_price=100.0, risk=10.0)
    assert tight == 100.0
    assert wide == 10.0
    assert tight * 1.0 == wide * 10.0  # same 100 dollars at risk


def test_zero_risk_sizes_to_nothing_rather_than_dividing_by_zero():
    assert RSIPaperTrader("BTCUSDT", "4h")._size(entry_price=100.0, risk=0.0) == 0.0
