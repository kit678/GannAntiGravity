import sys
from datetime import date, time
from pathlib import Path

import pandas as pd
import pytest
import pytz

sys.path.append(str(Path(__file__).resolve().parents[1]))

from analysis.signal_trade_simulator import CandleSignal
from strategy.orb.placebo import build_placebo_signals, placebo_percentile
from strategy.orb.session import add_bar_index, split_sessions
from strategy.orb.types import OrbSignal

IST = pytz.timezone("Asia/Kolkata")


def _sessions(day="2026-08-04", n=8):
    rows = []
    for i in range(n):
        naive = pd.Timestamp(f"{day} 09:15:00") + pd.Timedelta(minutes=5 * i)
        rows.append(
            {
                "timestamp": int(IST.localize(naive.to_pydatetime()).timestamp()),
                "open": 100.0,
                "high": 100.5,
                "low": 99.5,
                "close": 100.0,
                "volume": 1000,
            }
        )
    return split_sessions(add_bar_index(pd.DataFrame(rows)))


def _real_signal():
    return OrbSignal.fired(
        date(2026, 8, 4),
        CandleSignal(
            bar_index=3,
            side="LONG",
            entry_price=102.0,
            stop_price=99.0,
            signal_time="2026-08-04T09:30:00+05:30",
            max_hold_bars=4,
        ),
    )


PARAMS = {"or_minutes": 15, "flat_by": time(10, 5)}


def test_placebo_preserves_the_stop_distance():
    placebos = build_placebo_signals([_real_signal()], _sessions(), PARAMS, seed=1)

    assert len(placebos) == 1
    placebo = placebos[0]
    assert abs(placebo.entry_price - placebo.stop_price) == pytest.approx(3.0)


def test_placebo_entry_comes_from_a_tradable_bar_in_the_same_session():
    placebos = build_placebo_signals([_real_signal()], _sessions(), PARAMS, seed=1)

    assert placebos[0].bar_index in {3, 4, 5, 6, 7}


def test_placebo_stop_orientation_matches_its_side():
    for seed in range(20):
        for placebo in build_placebo_signals([_real_signal()], _sessions(), PARAMS, seed=seed):
            if placebo.side == "LONG":
                assert placebo.stop_price < placebo.entry_price
            else:
                assert placebo.stop_price > placebo.entry_price


def test_placebo_is_deterministic_for_a_given_seed():
    first = build_placebo_signals([_real_signal()], _sessions(), PARAMS, seed=7)
    second = build_placebo_signals([_real_signal()], _sessions(), PARAMS, seed=7)

    assert first == second


def test_different_seeds_eventually_differ():
    runs = {
        tuple((s.bar_index, s.side) for s in build_placebo_signals(
            [_real_signal()], _sessions(), PARAMS, seed=seed
        ))
        for seed in range(30)
    }
    assert len(runs) > 1


def test_skipped_sessions_produce_no_placebo():
    skipped = OrbSignal.skipped(date(2026, 8, 4), "no_breakout")
    assert build_placebo_signals([skipped], _sessions(), PARAMS, seed=1) == []


def test_percentile_ranks_the_real_result_against_the_distribution():
    assert placebo_percentile(10.0, [1.0, 2.0, 3.0, 4.0]) == 100.0
    assert placebo_percentile(0.0, [1.0, 2.0, 3.0, 4.0]) == 0.0
    assert placebo_percentile(2.5, [1.0, 2.0, 3.0, 4.0]) == 50.0


def test_percentile_needs_a_distribution():
    with pytest.raises(ValueError, match="empty"):
        placebo_percentile(1.0, [])
