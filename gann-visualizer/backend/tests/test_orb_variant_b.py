import sys
from datetime import date, time
from pathlib import Path

import pandas as pd
import pytest
import pytz

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.orb.session import add_bar_index, split_sessions
from strategy.orb.variant_b_noise_band import daily_atr, generate_signal

IST = pytz.timezone("Asia/Kolkata")
DAY = "2026-08-04"


def _session(closes, opens=None):
    n = len(closes)
    opens = opens or list(closes)
    rows = []
    for i in range(n):
        naive = pd.Timestamp(f"{DAY} 09:15:00") + pd.Timedelta(minutes=5 * i)
        rows.append(
            {
                "timestamp": int(IST.localize(naive.to_pydatetime()).timestamp()),
                "open": opens[i],
                "high": max(opens[i], closes[i]) + 0.5,
                "low": min(opens[i], closes[i]) - 0.5,
                "close": closes[i],
                "volume": 1000,
            }
        )
    bars = add_bar_index(pd.DataFrame(rows))
    return split_sessions(bars)[date(2026, 8, 4)]


# anchor 100.0, atr 40.0, k 0.25 -> band is 100 +/- 10 -> [90, 110]
PARAMS = {"warmup_minutes": 15, "bar_minutes": 5, "k": 0.25, "flat_by": time(10, 5)}


def test_daily_atr_averages_true_range():
    daily = pd.DataFrame(
        {
            "high": [110.0, 112.0, 111.0],
            "low": [100.0, 102.0, 101.0],
            "close": [105.0, 108.0, 106.0],
        }
    )
    atr = daily_atr(daily, length=2)

    # TR: bar0 = 10 (no prev close), bar1 = max(10, 7, 3) = 10, bar2 = max(10, 3, 7) = 10
    assert pd.isna(atr.iloc[0])  # NaN during warmup
    assert atr.iloc[1] == pytest.approx(10.0)
    assert atr.iloc[2] == pytest.approx(10.0)


def test_upward_band_break_produces_a_long():
    session = _session([100.0, 100.0, 100.0, 115.0, 115.0, 115.0, 115.0, 115.0])
    result = generate_signal(session, PARAMS, atr=40.0)

    assert result.triggered
    assert result.signal.side == "LONG"
    assert result.signal.bar_index == 3
    assert result.signal.entry_price == 115.0
    assert result.signal.stop_price == pytest.approx(90.0)


def test_downward_band_break_produces_a_short():
    session = _session([100.0, 100.0, 100.0, 85.0, 85.0, 85.0, 85.0, 85.0])
    result = generate_signal(session, PARAMS, atr=40.0)

    assert result.signal.side == "SHORT"
    assert result.signal.stop_price == pytest.approx(110.0)


def test_no_breach_produces_no_signal():
    session = _session([100.0, 100.0, 100.0, 105.0, 95.0, 104.0, 96.0, 100.0])
    result = generate_signal(session, PARAMS, atr=40.0)

    assert not result.triggered
    assert result.reason == "no_breakout"


def test_band_anchors_to_todays_open_not_yesterdays_close():
    # Session gaps up: opens at 200, so the band is 200 +/- 10, not 100 +/- 10.
    session = _session(
        [200.0, 200.0, 200.0, 205.0, 205.0, 205.0, 205.0, 205.0],
        opens=[200.0] * 8,
    )
    result = generate_signal(session, PARAMS, atr=40.0)

    assert not result.triggered  # 205 is inside 200 +/- 10
    assert result.diagnostics["anchor"] == 200.0
    assert result.diagnostics["upper"] == pytest.approx(210.0)


def test_missing_atr_is_skipped():
    session = _session([100.0] * 8)
    result = generate_signal(session, PARAMS, atr=None)

    assert not result.triggered
    assert result.reason == "no_atr"


def test_non_positive_atr_is_skipped():
    session = _session([100.0] * 8)
    result = generate_signal(session, PARAMS, atr=0.0)

    assert not result.triggered
    assert result.reason == "no_atr"


def test_trigger_with_no_bars_left_before_flat_is_skipped():
    # Breaks out on bar 7 (09:50), which is the flat-by bar - nothing left to hold.
    session = _session([100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 115.0])
    result = generate_signal(session, {**PARAMS, "flat_by": time(9, 50)}, atr=40.0)

    assert not result.triggered
    assert result.reason == "no_bars_before_flat"
    assert result.diagnostics["trigger_bar"] == 7


def test_missing_anchor_bar_is_skipped():
    session = _session([100.0] * 8).iloc[1:].reset_index(drop=True)
    result = generate_signal(session, PARAMS, atr=40.0)

    assert not result.triggered
    assert result.reason == "no_anchor_bar"
