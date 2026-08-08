import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from scripts.run_orb_test import build_parser, render_report


def _report(verdict="PASS", preliminary=False):
    return {
        "symbol": "^NSEI",
        "variant": "A",
        "data_source": "dhan",
        "preliminary": preliminary,
        "sessions": {
            "available": 500,
            "traded": 380,
            "skipped": 120,
            "skip_reasons": {"no_breakout": 118, "degenerate_range": 2},
        },
        "split": {
            "train_dates": ["2024-01-01", "2024-06-01"],
            "test_dates": ["2024-06-02", "2025-01-01"],
        },
        "cells": [
            {
                "label": "or=15,r=2.0",
                "is_headline": True,
                "n_trades_test": 190,
                "avg_net_pnl_test_base": 3.5,
                "avg_net_pnl_test_stressed": 1.5,
                "avg_net_pnl_train_base": 4.0,
            },
            {
                "label": "or=30,r=2.0",
                "is_headline": False,
                "n_trades_test": 180,
                "avg_net_pnl_test_base": 2.0,
                "avg_net_pnl_test_stressed": 0.5,
                "avg_net_pnl_train_base": 2.5,
            },
        ],
        "headline_cell": {
            "label": "or=15,r=2.0",
            "is_headline": True,
            "n_trades_test": 190,
            "avg_net_pnl_test_base": 3.5,
            "avg_net_pnl_test_stressed": 1.5,
            "avg_net_pnl_train_base": 4.0,
        },
        "info_only_r1_avg_net_pnl_test": 1.2,
        "slippage_sweep": {0.0: 5.5, 1.0: 3.5, 2.0: 1.5, 3.0: -0.5},
        "breakeven_slippage": 2.75,
        "placebo_percentile": 98.5,
        "placebo_seeds": 200,
        "fee_rate_base": 0.0003,
        "fee_rate_stressed": 0.0006,
        "verdict": verdict,
        "verdict_reasons": [],
    }


def test_report_leads_with_the_verdict_and_breakeven_slippage():
    text = render_report(_report())

    assert "VERDICT: PASS" in text
    assert "Breakeven slippage" in text
    assert "2.75" in text


def test_report_flags_preliminary_runs_loudly():
    text = render_report(_report(verdict="INCONCLUSIVE", preliminary=True))

    assert "PRELIMINARY — INSUFFICIENT DATA" in text


def test_report_labels_the_fee_rate_as_an_estimate():
    text = render_report(_report())

    assert "estimate" in text.lower()


def test_report_shows_session_accounting_with_reasons():
    text = render_report(_report())

    assert "no_breakout" in text
    assert "380" in text


def test_report_marks_the_info_only_row_as_not_the_verdict():
    text = render_report(_report())

    assert "not the verdict" in text.lower()


def test_parser_requires_symbol_and_variant():
    parser = build_parser()
    args = parser.parse_args(["--symbol", "^NSEI", "--variant", "A"])

    assert args.symbol == "^NSEI"
    assert args.variant == "A"
    assert args.source == "yfinance"


def test_parser_rejects_an_unknown_variant():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--symbol", "^NSEI", "--variant", "Z"])
