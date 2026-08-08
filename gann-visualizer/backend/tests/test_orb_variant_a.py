import sys
from datetime import date, time
from pathlib import Path

import pandas as pd
import pytz

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.orb.session import add_bar_index, split_sessions
from strategy.orb.variant_a_range import generate_signal

IST = pytz.timezone("Asia/Kolkata")
DAY = "2026-08-04"


def _session(closes, highs=None, lows=None, opens=None):
    """Build one 5-minute session from 09:15 with the given closes."""
    n = len(closes)
    highs = highs or [c + 0.5 for c in closes]
    lows = lows or [c - 0.5 for c in closes]
    opens = opens or list(closes)
    rows = []
    for i in range(n):
        naive = pd.Timestamp(f"{DAY} 09:15:00") + pd.Timedelta(minutes=5 * i)
        rows.append(
            {
                "timestamp": int(IST.localize(naive.to_pydatetime()).timestamp()),
                "open": opens[i],
                "high": highs[i],
                "low": lows[i],
                "close": closes[i],
                "volume": 1000,
            }
        )
    bars = add_bar_index(pd.DataFrame(rows))
    return split_sessions(bars)[date(2026, 8, 4)]


PARAMS = {"or_minutes": 15, "bar_minutes": 5, "flat_by": time(10, 5)}


def test_upward_break_produces_a_long_at_the_trigger_close():
    # OR bars (09:15-09:25) high tops out at 100.5. Bar 3 closes at 102.
    session = _session([100.0, 100.0, 100.0, 102.0, 102.0, 102.0, 102.0, 102.0])
    result = generate_signal(session, PARAMS)

    assert result.triggered
    assert result.signal.side == "LONG"
    assert result.signal.bar_index == 3
    assert result.signal.entry_price == 102.0
    assert result.signal.stop_price == 99.5      # lowest low of the OR window
    assert result.signal.max_hold_bars == 4      # bars 4..7 remain before 10:05


def test_downward_break_produces_a_short():
    session = _session([100.0, 100.0, 100.0, 98.0, 98.0, 98.0, 98.0, 98.0])
    result = generate_signal(session, PARAMS)

    assert result.triggered
    assert result.signal.side == "SHORT"
    assert result.signal.bar_index == 3
    assert result.signal.entry_price == 98.0
    assert result.signal.stop_price == 100.5     # highest high of the OR window


def test_inside_day_produces_no_signal():
    session = _session([100.0] * 8)
    result = generate_signal(session, PARAMS)

    assert not result.triggered
    assert result.reason == "no_breakout"


def test_only_the_first_trigger_is_taken():
    # Breaks down at bar 3, then back up above the range at bar 5.
    session = _session([100.0, 100.0, 100.0, 98.0, 99.0, 102.0, 102.0, 102.0])
    result = generate_signal(session, PARAMS)

    assert result.signal.side == "SHORT"
    assert result.signal.bar_index == 3


def test_degenerate_range_is_skipped():
    session = _session(
        [100.0] * 8,
        highs=[100.0] * 8,
        lows=[100.0] * 8,
    )
    result = generate_signal(session, PARAMS)

    assert not result.triggered
    assert result.reason == "degenerate_range"


def test_short_opening_range_is_skipped():
    session = _session([100.0, 100.0])  # only two bars, need three
    result = generate_signal(session, PARAMS)

    assert not result.triggered
    assert result.reason == "short_opening_range"


def test_trigger_with_no_bars_left_before_flat_is_skipped():
    # Breaks out on bar 7 (09:50), which is the flat-by bar — nothing left to hold.
    session = _session([100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 102.0])
    result = generate_signal(session, {**PARAMS, "flat_by": time(9, 50)})

    assert not result.triggered
    assert result.reason == "no_bars_before_flat"
    assert result.diagnostics["trigger_bar"] == 7


def test_diagnostics_record_the_range():
    session = _session([100.0, 100.0, 100.0, 102.0, 102.0, 102.0, 102.0, 102.0])
    result = generate_signal(session, PARAMS)

    assert result.diagnostics["orh"] == 100.5
    assert result.diagnostics["orl"] == 99.5
