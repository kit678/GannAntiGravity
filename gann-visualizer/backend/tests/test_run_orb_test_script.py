import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from scripts.run_orb_test import build_parser, fetch_bars, render_report


def _report(verdict="PASS", preliminary=False, placebo_percentile=98.5, placebo_stats=None):
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
        "placebo_percentile": placebo_percentile,
        "placebo_seeds": 200,
        "placebo_stats": placebo_stats,
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


def test_report_renders_placebo_attrition_stats():
    stats = {
        "seeds_requested": 200,
        "seeds_used": 180,
        "real_signal_count": 10,
        "min_placebo_signals_in_a_seed": 3,
        "full_strength_seeds": 40,
    }
    text = render_report(_report(placebo_stats=stats))

    assert "180/200" in text
    assert "40 full strength" in text
    assert "Caution" in text  # 40/180 < 0.5, should trigger the warning


def test_report_omits_caution_when_most_seeds_are_full_strength():
    stats = {
        "seeds_requested": 200,
        "seeds_used": 200,
        "real_signal_count": 10,
        "min_placebo_signals_in_a_seed": 10,
        "full_strength_seeds": 190,
    }
    text = render_report(_report(placebo_stats=stats))

    assert "Caution" not in text


def test_report_handles_missing_placebo_percentile_without_crashing():
    text = render_report(_report(placebo_percentile=None))

    assert "None%" not in text
    assert "did not run" in text.lower()


def test_report_handles_missing_placebo_stats():
    text = render_report(_report(placebo_stats=None))

    assert "None" not in text.split("## Placebo")[1].split("## Assumptions")[0]


def test_fetch_bars_raises_on_empty_intraday_data():
    from unittest.mock import MagicMock, patch

    with patch("yfinance_client.YFinanceClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.fetch_data.return_value = pd.DataFrame()
        mock_client_cls.return_value = mock_client

        with pytest.raises(ValueError, match="no intraday bars"):
            fetch_bars("^NSEI", "yfinance", "5", "2024-01-01", "2024-02-01")


def test_fetch_bars_returns_none_for_empty_daily_data():
    from unittest.mock import MagicMock, patch

    with patch("yfinance_client.YFinanceClient") as mock_client_cls:
        mock_client = MagicMock()
        intraday_df = pd.DataFrame({"timestamp": [1, 2], "close": [100.0, 101.0]})
        mock_client.fetch_data.side_effect = [intraday_df, pd.DataFrame()]
        mock_client_cls.return_value = mock_client

        intraday, daily = fetch_bars("^NSEI", "yfinance", "5", "2024-01-01", "2024-02-01")

        assert not intraday.empty
        assert daily is None
