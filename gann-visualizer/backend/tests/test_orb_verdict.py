import math
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.orb.verdict import CellResult, decide_verdict


def _cell(label="headline", headline=True, n=40, base=5.0, stressed=2.0, train=4.0):
    return CellResult(
        label=label,
        is_headline=headline,
        n_trades_test=n,
        avg_net_pnl_test_base=base,
        avg_net_pnl_test_stressed=stressed,
        avg_net_pnl_train_base=train,
    )


def _neighbour(label, base=3.0):
    return _cell(label=label, headline=False, base=base)


def test_all_criteria_met_is_a_pass():
    verdict, reasons = decide_verdict(
        cells=[_cell(), _neighbour("r=1.5"), _neighbour("r=3.0")],
        placebo_percentile=98.0,
        data_source="dhan",
    )
    assert verdict == "PASS"
    assert reasons == []


def test_yfinance_data_is_always_inconclusive():
    verdict, reasons = decide_verdict(
        cells=[_cell()], placebo_percentile=99.0, data_source="yfinance"
    )
    assert verdict == "INCONCLUSIVE"
    assert any("yfinance" in reason for reason in reasons)


def test_too_few_trades_is_inconclusive_not_a_pass():
    verdict, reasons = decide_verdict(
        cells=[_cell(n=29)], placebo_percentile=99.0, data_source="dhan"
    )
    assert verdict == "INCONCLUSIVE"
    assert any("29" in reason for reason in reasons)


def test_negative_at_base_costs_is_a_fail():
    verdict, _ = decide_verdict(
        cells=[_cell(base=-1.0)], placebo_percentile=99.0, data_source="dhan"
    )
    assert verdict == "FAIL"


def test_negative_at_stressed_costs_is_a_fail():
    verdict, _ = decide_verdict(
        cells=[_cell(stressed=-0.5)], placebo_percentile=99.0, data_source="dhan"
    )
    assert verdict == "FAIL"


def test_negative_train_half_is_a_fail():
    verdict, _ = decide_verdict(
        cells=[_cell(train=-2.0)], placebo_percentile=99.0, data_source="dhan"
    )
    assert verdict == "FAIL"


def test_failing_the_placebo_is_a_fail():
    verdict, reasons = decide_verdict(
        cells=[_cell()], placebo_percentile=80.0, data_source="dhan"
    )
    assert verdict == "FAIL"
    assert any("placebo" in reason for reason in reasons)


def test_headline_passing_with_a_negative_neighbour_is_fragile():
    verdict, reasons = decide_verdict(
        cells=[_cell(), _neighbour("k=0.15", base=-0.5), _neighbour("k=0.40")],
        placebo_percentile=99.0,
        data_source="dhan",
    )
    assert verdict == "FRAGILE"
    assert any("k=0.15" in reason for reason in reasons)


def test_missing_headline_cell_is_inconclusive():
    verdict, reasons = decide_verdict(
        cells=[_neighbour("r=1.5")], placebo_percentile=99.0, data_source="dhan"
    )
    assert verdict == "INCONCLUSIVE"
    assert any("headline" in reason for reason in reasons)


def test_missing_placebo_is_inconclusive():
    verdict, reasons = decide_verdict(
        cells=[_cell()], placebo_percentile=None, data_source="dhan"
    )
    assert verdict == "INCONCLUSIVE"
    assert any("placebo" in reason for reason in reasons)


def test_nan_headline_pnl_is_a_fail_not_a_pass():
    verdict, reasons = decide_verdict(
        cells=[_cell(base=math.nan)], placebo_percentile=99.0, data_source="dhan"
    )
    assert verdict == "FAIL"
    assert any("non-finite" in reason for reason in reasons)


def test_nan_placebo_percentile_is_a_fail_not_a_pass():
    verdict, reasons = decide_verdict(
        cells=[_cell()], placebo_percentile=math.nan, data_source="dhan"
    )
    assert verdict == "FAIL"
    assert any("non-finite" in reason for reason in reasons)


def test_nan_neighbour_pnl_counts_as_fragile_not_robust():
    verdict, reasons = decide_verdict(
        cells=[_cell(), _neighbour("k=0.15", base=math.nan), _neighbour("k=0.40")],
        placebo_percentile=99.0,
        data_source="dhan",
    )
    assert verdict == "FRAGILE"
    assert any("k=0.15" in reason for reason in reasons)


def test_boundary_exactly_min_trades_is_not_inconclusive():
    verdict, _ = decide_verdict(
        cells=[_cell(n=30)], placebo_percentile=99.0, data_source="dhan"
    )
    assert verdict == "PASS"


def test_boundary_exactly_zero_pnl_is_a_fail():
    verdict, _ = decide_verdict(
        cells=[_cell(base=0.0)], placebo_percentile=99.0, data_source="dhan"
    )
    assert verdict == "FAIL"


def test_boundary_exactly_min_placebo_percentile_passes():
    verdict, _ = decide_verdict(
        cells=[_cell()], placebo_percentile=95.0, data_source="dhan"
    )
    assert verdict == "PASS"


def test_multiple_simultaneous_fail_reasons_all_accumulate():
    verdict, reasons = decide_verdict(
        cells=[_cell(base=-1.0, stressed=-2.0)], placebo_percentile=99.0, data_source="dhan"
    )
    assert verdict == "FAIL"
    assert len(reasons) == 2
