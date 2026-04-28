import sys
import os
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

import pandas as pd
from analysis.strategy_analyzer import PostBreachPullbackHypothesis


def _row(bar, ts, fan, frac, etype, mfe10=0.0, mae10=0.0, direction=""):
    return {
        "bar_index": bar,
        "Raw_Timestamp": ts,
        "Fan": fan,
        "Fraction": frac,
        "Type": etype,
        "Direction": direction,
        "MFE_5": mfe10 * 0.5,
        "MAE_5": mae10 * 0.5,
        "MFE_10": mfe10,
        "MAE_10": mae10,
        "MFE_20": mfe10 * 1.5,
        "MAE_20": mae10 * 1.5,
        "MFE_50": mfe10 * 2,
        "MAE_50": mae10 * 2,
        "Open": 100.0,
        "High": 101.0,
        "Low": 99.0,
        "Close": 100.5,
    }


def test_pullback_pair_within_window_is_identified():
    rows = [
        _row(5, 1700000000, "P1 (H1-L1)", "0.5", "BREACH_CONFIRMED", direction="up"),
        _row(8, 1700001500, "P1 (H1-L1)", "0.5", "SUPPORT_TEST", mfe10=5.0, mae10=1.0),
    ]
    df = pd.DataFrame(rows)
    h = PostBreachPullbackHypothesis()
    h.set_parameters(pullback_window_bars=10)

    result = h.evaluate(df)
    assert result["sample_size"] == 1


def test_pullback_pair_outside_window_ignored():
    rows = [
        _row(5, 1700000000, "P1 (H1-L1)", "0.5", "BREACH_CONFIRMED", direction="up"),
        _row(17, 1700004500, "P1 (H1-L1)", "0.5", "SUPPORT_TEST", mfe10=5.0, mae10=1.0),
    ]
    df = pd.DataFrame(rows)
    h = PostBreachPullbackHypothesis()
    h.set_parameters(pullback_window_bars=10)

    result = h.evaluate(df)
    assert result["sample_size"] == 0


def test_pullback_pair_wrong_direction_ignored():
    """UP-breach + RESISTANCE_TEST is not a continuation entry."""
    rows = [
        _row(5, 1700000000, "P1 (H1-L1)", "0.5", "BREACH_CONFIRMED", direction="up"),
        _row(8, 1700001500, "P1 (H1-L1)", "0.5", "RESISTANCE_TEST", mfe10=5.0, mae10=1.0),
    ]
    df = pd.DataFrame(rows)
    h = PostBreachPullbackHypothesis()
    h.set_parameters(pullback_window_bars=10)

    result = h.evaluate(df)
    assert result["sample_size"] == 0


def test_pullback_pair_different_line_ignored():
    """Pullback must be on the same (fan, fraction) as the breach."""
    rows = [
        _row(5, 1700000000, "P1 (H1-L1)", "0.5", "BREACH_CONFIRMED", direction="up"),
        _row(8, 1700001500, "P1 (H1-L1)", "0.75", "SUPPORT_TEST", mfe10=5.0, mae10=1.0),
    ]
    df = pd.DataFrame(rows)
    h = PostBreachPullbackHypothesis()
    h.set_parameters(pullback_window_bars=10)

    result = h.evaluate(df)
    assert result["sample_size"] == 0


def test_returns_required_keys():
    rows = [
        _row(5, 1700000000, "P1 (H1-L1)", "0.5", "BREACH_CONFIRMED", direction="up"),
        _row(8, 1700001500, "P1 (H1-L1)", "0.5", "SUPPORT_TEST", mfe10=5.0, mae10=1.0),
    ]
    df = pd.DataFrame(rows)
    result = PostBreachPullbackHypothesis().evaluate(df)
    for key in ("sample_size", "win_rate", "avg_mfe_10", "avg_mae_10"):
        assert key in result


def test_empty_dataframe_returns_zero_sample_size():
    result = PostBreachPullbackHypothesis().evaluate(pd.DataFrame())
    assert result["sample_size"] == 0
