"""rsi_geometry is now a compatibility shim over the three focused modules.

The previous contents tested DeterministicPivotLineBuilder, which this change
deletes.  Two of those four tests were already failing on main because their
fixtures used pivot spans below the min_length=8 default.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import pytest

import analysis.rsi_geometry as rsi_geometry


def test_shim_reexports_the_public_surface():
    for name in (
        "RSIPivot", "RSILine", "GeometryParams", "LineSegment", "BreakSignal",
        "SweepResult", "compute_rsi_series", "detect_fractal_candidates",
        "apply_dominance", "run_causal_sweep",
        "WalkBackAnchorPolicy", "NearestPairAnchorPolicy",
    ):
        assert hasattr(rsi_geometry, name), f"shim is missing {name}"


def test_shim_rsi_matches_the_pivot_module():
    from analysis.rsi_pivots import compute_rsi_series as canonical

    close = pd.Series([float(100 + (i % 7)) for i in range(60)])
    pd.testing.assert_series_equal(rsi_geometry.compute_rsi_series(close), canonical(close))


@pytest.mark.parametrize(
    "removed",
    [
        "DeterministicPivotLineBuilder",
        "detect_rsi_pivots",
        "detect_rsi_line_breaks",
        "RSIBreakSignal",
    ],
)
def test_superseded_symbols_are_gone(removed):
    assert not hasattr(rsi_geometry, removed), (
        f"{removed} was superseded by the causal sweep and must not be re-exported"
    )
