import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd

from analysis.rsi_pivots import (
    GeometryParams,
    RSIPivot,
    apply_dominance,
    compute_rsi_series,
    detect_fractal_candidates,
)


def test_geometry_params_expose_defaults_for_every_knob():
    params = GeometryParams()

    assert params.left_bars == 3
    assert params.right_bars == 3
    assert params.min_swing == 8.0
    assert params.tolerance == 1.5
    assert params.min_length == 8
    assert params.max_span_bars == 150


def test_rsi_series_stays_in_range_and_rises_on_uptrend():
    close = pd.Series([float(100 + i) for i in range(40)])
    rsi = compute_rsi_series(close, period=14)

    assert len(rsi) == 40
    assert rsi.iloc[-1] > 90.0
    assert ((rsi >= 0.0) & (rsi <= 100.0)).all()


def test_fractal_candidate_confirms_right_bars_after_its_own_bar():
    rsi = pd.Series([40.0, 42.0, 55.0, 43.0, 41.0, 39.0, 38.0])

    candidates = detect_fractal_candidates(rsi, left_bars=2, right_bars=2)
    highs = [c for c in candidates if c.kind == "high"]

    assert highs[0].bar_index == 2
    assert highs[0].rsi_value == 55.0
    assert highs[0].confirmation_bar_index == 4


def test_dominance_replaces_a_weaker_same_kind_pivot():
    weak = RSIPivot(bar_index=10, rsi_value=60.0, kind="high", confirmation_bar_index=12)
    strong = RSIPivot(bar_index=14, rsi_value=68.0, kind="high", confirmation_bar_index=16)

    pivots, changed = apply_dominance([weak], strong, min_swing=8.0)

    assert pivots == [strong]
    assert changed == "high"


def test_dominance_keeps_the_stronger_incumbent_and_reports_no_change():
    strong = RSIPivot(bar_index=10, rsi_value=68.0, kind="high", confirmation_bar_index=12)
    weak = RSIPivot(bar_index=14, rsi_value=61.0, kind="high", confirmation_bar_index=16)

    pivots, changed = apply_dominance([strong], weak, min_swing=8.0)

    assert pivots == [strong]
    assert changed is None


def test_dominance_rejects_an_opposite_pivot_below_min_swing():
    high = RSIPivot(bar_index=10, rsi_value=68.0, kind="high", confirmation_bar_index=12)
    shallow_low = RSIPivot(bar_index=14, rsi_value=63.0, kind="low", confirmation_bar_index=16)

    pivots, changed = apply_dominance([high], shallow_low, min_swing=8.0)

    assert pivots == [high]
    assert changed is None


def test_dominance_appends_an_opposite_pivot_meeting_min_swing():
    high = RSIPivot(bar_index=10, rsi_value=68.0, kind="high", confirmation_bar_index=12)
    deep_low = RSIPivot(bar_index=14, rsi_value=52.0, kind="low", confirmation_bar_index=16)

    pivots, changed = apply_dominance([high], deep_low, min_swing=8.0)

    assert pivots == [high, deep_low]
    assert changed == "low"


def test_dominance_produces_strict_alternation_over_a_stream():
    stream = [
        RSIPivot(bar_index=2, rsi_value=70.0, kind="high", confirmation_bar_index=4),
        RSIPivot(bar_index=6, rsi_value=72.0, kind="high", confirmation_bar_index=8),
        RSIPivot(bar_index=10, rsi_value=50.0, kind="low", confirmation_bar_index=12),
        RSIPivot(bar_index=14, rsi_value=48.0, kind="low", confirmation_bar_index=16),
        RSIPivot(bar_index=18, rsi_value=66.0, kind="high", confirmation_bar_index=20),
    ]

    pivots = []
    for candidate in stream:
        pivots, _ = apply_dominance(pivots, candidate, min_swing=8.0)

    kinds = [p.kind for p in pivots]
    assert kinds == ["high", "low", "high"]
    assert [p.bar_index for p in pivots] == [6, 14, 18]
