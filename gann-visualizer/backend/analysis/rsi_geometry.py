"""Compatibility shim.

The geometry engine now lives in three focused modules:

    analysis.rsi_pivots       RSI series, fractal candidates, dominance
    analysis.rsi_line_policy  anchor policies and the line primitive
    analysis.rsi_sweep        the causal state machine

Prefer importing from those directly.  This module exists so existing imports
keep resolving.

Deleted here, deliberately:
    DeterministicPivotLineBuilder.build_lines        -> NearestPairAnchorPolicy
    DeterministicPivotLineBuilder.build_best_fit_lines (RANSAC)
    DeterministicPivotLineBuilder.cluster_best_fit_lines   (0 callers)
    DeterministicPivotLineBuilder._ols_best_fit            (0 callers)
    DeterministicPivotLineBuilder._total_least_squares     (0 callers)
    detect_rsi_pivots / detect_rsi_line_breaks       -> run_causal_sweep

RANSAC and the other best-fit builders are gone on purpose: a regression line
has RSI on both sides of it by construction, so "the break" is not a distinct
event.  This strategy needs a line that is touched, then broken.
"""

from __future__ import annotations

from analysis.rsi_line_policy import (
    AnchorPolicy,
    NearestPairAnchorPolicy,
    RSILine,
    WalkBackAnchorPolicy,
    count_touches,
    line_between,
)
from analysis.rsi_pivots import (
    GeometryParams,
    RSIPivot,
    apply_dominance,
    compute_rsi_series,
    detect_fractal_candidates,
)
from analysis.rsi_sweep import (
    BreakSignal,
    LineSegment,
    SweepResult,
    run_causal_sweep,
)

__all__ = [
    "AnchorPolicy",
    "BreakSignal",
    "GeometryParams",
    "LineSegment",
    "NearestPairAnchorPolicy",
    "RSILine",
    "RSIPivot",
    "SweepResult",
    "WalkBackAnchorPolicy",
    "apply_dominance",
    "compute_rsi_series",
    "count_touches",
    "detect_fractal_candidates",
    "line_between",
    "run_causal_sweep",
]
