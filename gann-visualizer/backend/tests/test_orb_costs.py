import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.orb.costs import SLIPPAGE_SWEEP, breakeven_slippage


def test_sweep_is_ascending_and_starts_at_zero():
    assert SLIPPAGE_SWEEP[0] == 0.0
    assert SLIPPAGE_SWEEP == sorted(SLIPPAGE_SWEEP)


def test_interpolates_the_zero_crossing():
    # +2.0 at 0.5 slippage, -2.0 at 1.0 -> crosses exactly halfway, at 0.75
    pnl = {0.0: 4.0, 0.5: 2.0, 1.0: -2.0}
    assert breakeven_slippage(pnl) == pytest.approx(0.75)


def test_already_negative_at_zero_slippage_reports_zero():
    pnl = {0.0: -1.0, 0.5: -2.0, 1.0: -3.0}
    assert breakeven_slippage(pnl) == 0.0


def test_still_positive_at_the_top_reports_the_top_as_a_floor():
    pnl = {0.0: 5.0, 1.0: 4.0, 3.0: 3.0}
    assert breakeven_slippage(pnl) == 3.0


def test_exact_zero_at_a_tested_level_reports_that_level():
    pnl = {0.0: 2.0, 0.5: 0.0, 1.0: -2.0}
    assert breakeven_slippage(pnl) == pytest.approx(0.5)


def test_empty_input_is_rejected():
    with pytest.raises(ValueError, match="at least one"):
        breakeven_slippage({})


def test_result_does_not_depend_on_dict_insertion_order():
    # Same data as test_interpolates_the_zero_crossing, but keys inserted out of order.
    pnl = {1.0: -2.0, 0.0: 4.0, 0.5: 2.0}
    assert breakeven_slippage(pnl) == pytest.approx(0.75)
