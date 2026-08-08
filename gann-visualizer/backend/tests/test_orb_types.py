import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from analysis.signal_trade_simulator import CandleSignal
from strategy.orb.types import OrbSignal


def test_skipped_records_the_reason_and_has_no_signal():
    result = OrbSignal.skipped(date(2026, 8, 4), "degenerate_range", range_width=0.0)

    assert result.signal is None
    assert result.reason == "degenerate_range"
    assert result.diagnostics["range_width"] == 0.0
    assert result.triggered is False


def test_fired_carries_the_signal_and_no_reason():
    signal = CandleSignal(
        bar_index=3,
        side="LONG",
        entry_price=101.0,
        stop_price=99.0,
        signal_time="2026-08-04T09:35:00+05:30",
        max_hold_bars=60,
    )
    result = OrbSignal.fired(date(2026, 8, 4), signal, orh=100.5, orl=99.0)

    assert result.signal is signal
    assert result.reason is None
    assert result.diagnostics["orh"] == 100.5
    assert result.triggered is True


def test_fired_rejects_a_missing_signal():
    with pytest.raises(ValueError, match="signal"):
        OrbSignal.fired(date(2026, 8, 4), None)


def test_direct_construction_with_neither_signal_nor_reason_is_rejected():
    with pytest.raises(ValueError, match="exactly one"):
        OrbSignal(session_date=date(2026, 8, 4))


def test_direct_construction_with_both_signal_and_reason_is_rejected():
    signal = CandleSignal(
        bar_index=3,
        side="LONG",
        entry_price=101.0,
        stop_price=99.0,
        signal_time="2026-08-04T09:35:00+05:30",
    )
    with pytest.raises(ValueError, match="exactly one"):
        OrbSignal(session_date=date(2026, 8, 4), signal=signal, reason="also_set")
