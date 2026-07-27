"""Prefix-stability: what the sweep emitted for bars <= k must never change
as more bars arrive.  This is the regression test for the repaint defect where
a pivot superseded at bar 150 rewrites what was anchored at bar 100.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import pytest

from analysis.rsi_line_policy import NearestPairAnchorPolicy, WalkBackAnchorPolicy
from analysis.rsi_pivots import compute_rsi_series
from analysis.rsi_pivots import GeometryParams
from analysis.rsi_sweep import run_causal_sweep

CANDLES = 'C:/Dev/GannTesting/logs/backend/runs/BTCUSDT/15/2026-07-10_barctx_v2/candles.csv'

PARAMS = GeometryParams(
    left_bars=3, right_bars=3, min_swing=8.0,
    tolerance=1.5, min_length=8, max_span_bars=150,
)


def synthetic_rsi():
    """Adversarial by construction: deep legs establish lows, then a shallow dip
    that FAILS min_swing is discarded, leaving two same-kind highs adjacent in the
    accumulated list and forcing a dominance REPLACEMENT.

    A plain alternating saw-tooth is useless here: it yields a perfect HLHLHL...
    candidate stream, apply_dominance never takes its replace branch, and batch
    and incremental dominance produce identical output -- so the test would pass
    against repainting code. This fixture produces 6 replacements.
    """
    values = []
    for cycle in range(7):
        base_peak = 76.0 - cycle * 2.5
        deep_low = 38.0 + cycle * 0.8
        values += [deep_low + 6, deep_low + 2, deep_low, deep_low + 3, deep_low + 7]
        values += [base_peak - 6, base_peak - 2, base_peak, base_peak - 3]
        values += [base_peak - 5, base_peak - 4]
        values += [base_peak - 1, base_peak + 1.5, base_peak - 2, base_peak - 6]
    return pd.Series(values)


def test_synthetic_fixture_actually_forces_dominance_replacements():
    """Guards the guard: if this fixture stops producing replacements, the
    prefix-stability tests below become vacuous."""
    from analysis.rsi_pivots import apply_dominance, detect_fractal_candidates

    pivots, replacements = [], 0
    for candidate in detect_fractal_candidates(synthetic_rsi(), PARAMS.left_bars, PARAMS.right_bars):
        before = len(pivots)
        had_previous = bool(pivots)
        pivots, changed = apply_dominance(pivots, candidate, PARAMS.min_swing)
        if changed and had_previous and len(pivots) == before:
            replacements += 1

    assert replacements >= 3, f"fixture only forced {replacements} replacements"


def signal_fingerprint(result, upto_bar):
    return [
        (s.bar_index, s.side, round(s.line_value_at_break, 6))
        for s in result.signals
        if s.bar_index <= upto_bar
    ]


def segment_fingerprint(result, upto_bar):
    return [
        (
            s.line.start_bar_index, s.line.end_bar_index,
            round(s.line.start_rsi, 6), round(s.line.end_rsi, 6),
            s.valid_from_bar,
        )
        for s in result.segments
        if s.valid_from_bar <= upto_bar
    ]


@pytest.mark.parametrize("policy", [WalkBackAnchorPolicy(), NearestPairAnchorPolicy()])
def test_synthetic_prefix_is_stable_as_more_bars_arrive(policy):
    rsi = synthetic_rsi()
    full = run_causal_sweep(rsi, policy, PARAMS)

    for cut in range(30, len(rsi), 7):
        prefix = run_causal_sweep(rsi.iloc[:cut].reset_index(drop=True), policy, PARAMS)
        horizon = cut - PARAMS.right_bars - 1

        assert signal_fingerprint(prefix, horizon) == signal_fingerprint(full, horizon), (
            f"signals for bars <= {horizon} changed when data grew to {cut} bars"
        )
        assert segment_fingerprint(prefix, horizon) == segment_fingerprint(full, horizon), (
            f"segments valid by bar {horizon} changed when data grew to {cut} bars"
        )


@pytest.mark.skipif(not os.path.exists(CANDLES), reason="run fixture not present")
def test_real_candles_prefix_is_stable():
    candles = pd.read_csv(CANDLES).reset_index(drop=True)
    rsi = compute_rsi_series(candles['close'], period=14)
    policy = WalkBackAnchorPolicy()
    full = run_causal_sweep(rsi, policy, PARAMS)

    for cut in (400, 600, 800):
        prefix = run_causal_sweep(rsi.iloc[:cut].reset_index(drop=True), policy, PARAMS)
        horizon = cut - PARAMS.right_bars - 1

        assert signal_fingerprint(prefix, horizon) == signal_fingerprint(full, horizon)
        assert segment_fingerprint(prefix, horizon) == segment_fingerprint(full, horizon)
