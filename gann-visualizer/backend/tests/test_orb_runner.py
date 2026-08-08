import sys
from datetime import time
from pathlib import Path

import pandas as pd
import pytest
import pytz

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.orb.runner import ROBUSTNESS_GRID, run_orb

IST = pytz.timezone("Asia/Kolkata")


def _day(day, closes):
    rows = []
    for i, close in enumerate(closes):
        naive = pd.Timestamp(f"{day} 09:15:00") + pd.Timedelta(minutes=5 * i)
        rows.append(
            {
                "timestamp": int(IST.localize(naive.to_pydatetime()).timestamp()),
                "open": close,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": 1000,
            }
        )
    return pd.DataFrame(rows)


def _winning_day(day):
    """Breaks up at bar 3, then keeps running — target is reached."""
    return _day(day, [100.0, 100.0, 100.0, 102.0, 104.0, 108.0, 112.0, 116.0])


def _losing_day(day):
    """Breaks up at bar 3, then collapses through the stop."""
    return _day(day, [100.0, 100.0, 100.0, 102.0, 100.0, 97.0, 95.0, 93.0])


def _quiet_day(day):
    return _day(day, [100.0] * 8)


RUN_KWARGS = dict(
    symbol="TEST",
    variant="A",
    bar_minutes=5,
    flat_by=time(10, 5),
    placebo_seeds=5,
)


def test_grid_has_exactly_one_headline_cell_per_variant():
    for variant in ("A", "B"):
        headlines = [cell for cell in ROBUSTNESS_GRID[variant] if cell["is_headline"]]
        assert len(headlines) == 1, variant


def test_session_accounting_covers_every_session():
    bars = pd.concat([_winning_day("2026-08-03"), _quiet_day("2026-08-04")])
    report = run_orb(bars=bars, daily_bars=None, data_source="synthetic", **RUN_KWARGS)

    accounting = report["sessions"]
    assert accounting["available"] == 2
    assert accounting["traded"] + accounting["skipped"] == accounting["available"]
    assert accounting["skip_reasons"]["no_breakout"] == 1


def test_train_test_split_lands_on_the_expected_boundary():
    days = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"]
    bars = pd.concat([_winning_day(d) for d in days])
    report = run_orb(bars=bars, daily_bars=None, data_source="synthetic", **RUN_KWARGS)

    assert report["split"]["train_dates"] == days[:2]
    assert report["split"]["test_dates"] == days[2:]


def test_a_losing_synthetic_set_is_reported_as_losing():
    """Sign regression. Guards against an inverted P&L making everything look good."""
    days = [f"2026-08-{d:02d}" for d in (3, 4, 5, 6, 7, 10)]
    bars = pd.concat([_losing_day(d) for d in days])
    report = run_orb(bars=bars, daily_bars=None, data_source="synthetic", **RUN_KWARGS)

    headline = report["headline_cell"]
    assert headline["avg_net_pnl_test_base"] < 0
    assert report["verdict"] in {"FAIL", "INCONCLUSIVE"}


def test_yfinance_source_forces_inconclusive_even_when_profitable():
    days = [f"2026-08-{d:02d}" for d in (3, 4, 5, 6, 7, 10)]
    bars = pd.concat([_winning_day(d) for d in days])
    report = run_orb(bars=bars, daily_bars=None, data_source="yfinance", **RUN_KWARGS)

    assert report["verdict"] == "INCONCLUSIVE"
    assert report["preliminary"] is True


def test_report_contains_the_slippage_sweep_and_breakeven():
    days = [f"2026-08-{d:02d}" for d in (3, 4, 5, 6)]
    bars = pd.concat([_winning_day(d) for d in days])
    report = run_orb(bars=bars, daily_bars=None, data_source="synthetic", **RUN_KWARGS)

    assert set(report["slippage_sweep"]) == {0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0}
    assert isinstance(report["breakeven_slippage"], float)


def test_variant_b_requires_daily_bars():
    bars = _winning_day("2026-08-03")
    with pytest.raises(ValueError, match="daily_bars"):
        run_orb(
            bars=bars,
            daily_bars=None,
            data_source="synthetic",
            symbol="TEST",
            variant="B",
            bar_minutes=5,
            flat_by=time(10, 5),
            placebo_seeds=5,
        )


def test_empty_bars_raise_rather_than_reporting_no_trades():
    with pytest.raises(ValueError, match="empty"):
        run_orb(
            bars=pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"]),
            daily_bars=None,
            data_source="synthetic",
            **RUN_KWARGS,
        )


def test_report_includes_placebo_percentile_and_attrition_stats():
    days = [f"2026-08-{d:02d}" for d in (3, 4, 5, 6, 7, 10)]
    bars = pd.concat([_winning_day(d) for d in days])
    report = run_orb(bars=bars, daily_bars=None, data_source="synthetic", **RUN_KWARGS)

    assert report["placebo_percentile"] is None or isinstance(report["placebo_percentile"], float)
    if report["placebo_percentile"] is not None:
        assert 0.0 <= report["placebo_percentile"] <= 100.0
    stats = report["placebo_stats"]
    assert stats["seeds_requested"] == RUN_KWARGS["placebo_seeds"]
    assert stats["real_signal_count"] == len(days)
    assert stats["seeds_used"] <= stats["seeds_requested"]


def test_variant_b_runs_end_to_end_with_daily_bars():
    days = [f"2026-08-{d:02d}" for d in range(3, 3 + 20)]
    bars = pd.concat([_winning_day(d) for d in days])

    daily_rows = []
    for i, day in enumerate(days):
        naive = pd.Timestamp(f"{day} 00:00:00")
        daily_rows.append(
            {
                "timestamp": int(IST.localize(naive.to_pydatetime()).timestamp()),
                "open": 100.0,
                "high": 116.5,
                "low": 99.5,
                "close": 116.0,
                "volume": 100000,
            }
        )
    daily_bars = pd.DataFrame(daily_rows)

    report = run_orb(
        symbol="TEST",
        variant="B",
        bars=bars,
        daily_bars=daily_bars,
        data_source="synthetic",
        bar_minutes=5,
        flat_by=time(10, 5),
        placebo_seeds=5,
    )

    assert report["variant"] == "B"
    assert report["verdict"] in {"PASS", "FRAGILE", "FAIL", "INCONCLUSIVE"}
    assert report["sessions"]["available"] == len(days)
