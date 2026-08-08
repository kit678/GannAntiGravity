import sys
from datetime import date, time
from pathlib import Path

import pandas as pd
import pytz

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.crt.swept_level import generate_signal
from strategy.orb.session import add_bar_index, split_sessions

IST = pytz.timezone("Asia/Kolkata")
DAY = "2026-08-04"


def _session(bars):
    """bars: list of (open, high, low, close) tuples, 5-minute from 09:15."""
    rows = []
    for i, (o, h, l, c) in enumerate(bars):
        naive = pd.Timestamp(f"{DAY} 09:15:00") + pd.Timedelta(minutes=5 * i)
        rows.append(
            {
                "timestamp": int(IST.localize(naive.to_pydatetime()).timestamp()),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 1000,
            }
        )
    frame = add_bar_index(pd.DataFrame(rows))
    return split_sessions(frame)[date(2026, 8, 4)]


def _flat(n, price=100.0):
    """n quiet bars forming a tight range."""
    return [(price, price + 0.5, price - 0.5, price)] * n


PARAMS = {"lookback_bars": 4, "bar_minutes": 5, "flat_by": time(11, 0)}


def test_swept_high_produces_a_short():
    # 4 quiet bars set the level (high 100.5). Bar 4 wicks to 103 but closes back at 100.
    bars = _flat(4) + [(100.0, 103.0, 99.8, 100.0)] + _flat(4)
    result = generate_signal(_session(bars), PARAMS)

    assert result.triggered
    assert result.signal.side == "SHORT"
    assert result.signal.bar_index == 4
    assert result.signal.entry_price == 100.0
    assert result.signal.stop_price == 103.0  # beyond the wick extreme


def test_swept_low_produces_a_long():
    bars = _flat(4) + [(100.0, 100.2, 97.0, 100.0)] + _flat(4)
    result = generate_signal(_session(bars), PARAMS)

    assert result.triggered
    assert result.signal.side == "LONG"
    assert result.signal.bar_index == 4
    assert result.signal.entry_price == 100.0
    assert result.signal.stop_price == 97.0


def test_close_beyond_the_level_is_a_real_breakout_not_a_sweep():
    # Wick AND close both clear the level -> genuine breakout, not a failed one.
    bars = _flat(4) + [(100.0, 103.0, 99.8, 102.5)] + _flat(4)
    result = generate_signal(_session(bars), PARAMS)

    assert not result.triggered
    assert result.reason == "no_sweep"


def test_no_wick_beyond_the_level_produces_no_signal():
    bars = _flat(9)
    result = generate_signal(_session(bars), PARAMS)

    assert not result.triggered
    assert result.reason == "no_sweep"


def test_only_the_first_sweep_is_taken():
    # Sweeps the high at bar 4, then sweeps the low at bar 6.
    bars = _flat(4) + [(100.0, 103.0, 99.8, 100.0)] + _flat(1) + [(100.0, 100.2, 96.0, 100.0)] + _flat(3)
    result = generate_signal(_session(bars), PARAMS)

    assert result.signal.side == "SHORT"
    assert result.signal.bar_index == 4


def test_session_shorter_than_the_lookback_is_skipped():
    bars = _flat(3)  # need 4 prior bars before any signal is possible
    result = generate_signal(_session(bars), PARAMS)

    assert not result.triggered
    assert result.reason == "insufficient_lookback"


def test_sweep_on_the_last_holdable_bar_is_skipped():
    # 09:15 + 5*8 = 09:55 is the last bar; flat_by lands on it, so nothing remains to hold.
    bars = _flat(8) + [(100.0, 103.0, 99.8, 100.0)]
    result = generate_signal(_session(bars), {**PARAMS, "flat_by": time(9, 55)})

    assert not result.triggered
    assert result.reason == "no_bars_before_flat"


def test_level_uses_only_bars_before_the_trigger():
    # The level must come from the 4 bars BEFORE the sweep bar, never including it.
    bars = _flat(4) + [(100.0, 103.0, 99.8, 100.0)] + _flat(4)
    result = generate_signal(_session(bars), PARAMS)

    # Level high is the quiet-bar high (100.5), not the sweep bar's own 103.
    assert result.diagnostics["level_high"] == 100.5
    assert result.diagnostics["level_low"] == 99.5


def test_lookback_window_is_bounded_not_cumulative():
    # An old spike outside the lookback window must not define the level.
    bars = [(100.0, 120.0, 99.5, 100.0)] + _flat(4) + [(100.0, 103.0, 99.8, 100.0)] + _flat(3)
    result = generate_signal(_session(bars), PARAMS)

    # With lookback=4, the bar-5 sweep sees bars 1-4 only, so the 120 spike is out of range.
    assert result.triggered
    assert result.diagnostics["level_high"] == 100.5
