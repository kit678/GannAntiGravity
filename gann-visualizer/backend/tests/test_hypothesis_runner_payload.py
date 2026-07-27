"""HypothesisRunner assembles its result from a fixed key list.

Any field a trade-scored hypothesis returns that is not named there is dropped
before the report is ever written to disk -- silently, with no error. That is
how line_timeline, skipped, net_pnl_total and exit_optimization went missing
from the persisted report while every unit test still passed: the tests checked
the hypothesis output, not what the runner kept.

These tests pin the runner's contract instead.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import inspect

from analysis.hypothesis_framework import HypothesisRunner


def _run_all_source() -> str:
    return inspect.getsource(HypothesisRunner.run_all)


def test_runner_carries_rsi_geometry_fields_into_the_report():
    source = _run_all_source()

    for field in ("line_timeline", "rsi_series", "skipped"):
        assert f'"{field}": in_sample.get' in source, (
            f"HypothesisRunner.run_all drops {field!r}; the persisted report will "
            f"not contain it and the Hypothesis Navigator will render nothing"
        )


def test_runner_no_longer_emits_the_superseded_all_rsi_lines_field():
    assert "all_rsi_lines" not in _run_all_source(), (
        "all_rsi_lines was replaced by line_timeline; emitting both invites "
        "consumers to read the stale one"
    )


def test_runner_preserves_trade_scored_pnl_and_exit_grid():
    source = _run_all_source()

    assert 'result["in_sample"]["net_pnl_total"]' in source, (
        "net_pnl_total is what a trade-scored hypothesis is judged on and must "
        "survive into the report rather than being recomputed by consumers"
    )
    assert 'result["exit_optimization"] = in_sample["exit_optimization"]' in source, (
        "the runner skips its own ExitOptimizer for trade-scored hypotheses, so "
        "the hypothesis's own per-R grid is the only one that exists"
    )


def test_runner_still_skips_its_own_optimizer_for_trade_scored_hypotheses():
    assert 'not result.get("trade_scored")' in _run_all_source(), (
        "running the generic ExitOptimizer over a trade-scored hypothesis would "
        "overwrite its own per-R results with events it never traded"
    )


def test_rsi_hypothesis_is_registered_under_the_expected_report_name():
    names = [entry[0] for entry in HypothesisRunner.HYPOTHESIS_CONFIG]

    assert "rsi_trendline_break_strategy" in names, (
        "the report filename is derived from this key; changing it orphans "
        "rsi_trendline_break_strategy.json in the Navigator"
    )
