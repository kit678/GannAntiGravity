import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from analysis.rsi_line_policy import (
    NearestPairAnchorPolicy,
    RSILine,
    WalkBackAnchorPolicy,
    count_touches,
)
from analysis.rsi_pivots import GeometryParams, RSIPivot


def high(bar, value):
    return RSIPivot(bar_index=bar, rsi_value=value, kind="high", confirmation_bar_index=bar + 3)


def low(bar, value):
    return RSIPivot(bar_index=bar, rsi_value=value, kind="low", confirmation_bar_index=bar + 3)


PARAMS = GeometryParams(min_length=8, max_span_bars=150, tolerance=1.5)


def test_line_value_interpolates_and_extrapolates():
    line = RSILine(start_bar_index=10, end_bar_index=20, start_rsi=70.0, end_rsi=60.0, direction="down")

    assert line.value_at(10) == 70.0
    assert line.value_at(15) == 65.0
    assert line.value_at(20) == 60.0
    assert line.value_at(30) == 50.0  # extends forward past its anchors
    assert line.slope == -1.0


def test_walk_back_picks_the_furthest_valid_anchor():
    # 70 / 64 / 62 / 58 all sit on one descending slope.
    pivots = [high(10, 70.0), high(20, 64.0), high(30, 62.0), high(40, 58.0)]

    anchor = WalkBackAnchorPolicy().anchor(pivots, pivots[-1], PARAMS)

    assert anchor is not None
    assert anchor.bar_index == 10


def test_walk_back_refuses_an_anchor_whose_line_a_middle_pivot_pokes_through():
    # 68 at bar 30 sits far above the 70 -> 58 line, so bar 10 is not usable.
    pivots = [high(10, 70.0), high(20, 64.0), high(30, 68.0), high(40, 58.0)]

    anchor = WalkBackAnchorPolicy().anchor(pivots, pivots[-1], PARAMS)

    assert anchor is not None
    assert anchor.bar_index == 30


def test_walk_back_rejects_an_anchor_beyond_the_span_cap():
    pivots = [high(10, 70.0), high(200, 58.0)]
    capped = GeometryParams(min_length=8, max_span_bars=150, tolerance=1.5)

    assert WalkBackAnchorPolicy().anchor(pivots, pivots[-1], capped) is None


def test_walk_back_rejects_an_anchor_closer_than_min_length():
    pivots = [high(10, 70.0), high(15, 58.0)]

    assert WalkBackAnchorPolicy().anchor(pivots, pivots[-1], PARAMS) is None


def test_walk_back_requires_a_lower_high_for_a_down_line():
    pivots = [high(10, 58.0), high(20, 70.0)]

    assert WalkBackAnchorPolicy().anchor(pivots, pivots[-1], PARAMS) is None


def test_walk_back_requires_a_higher_low_for_an_up_line():
    rising = [low(10, 30.0), low(20, 42.0), low(30, 48.0)]

    anchor = WalkBackAnchorPolicy().anchor(rising, rising[-1], PARAMS)

    assert anchor is not None
    assert anchor.bar_index == 10

    falling = [low(10, 48.0), low(20, 30.0)]
    assert WalkBackAnchorPolicy().anchor(falling, falling[-1], PARAMS) is None


def test_nearest_pair_policy_takes_the_closest_anchor_instead():
    pivots = [high(10, 70.0), high(20, 64.0), high(30, 62.0), high(40, 58.0)]

    anchor = NearestPairAnchorPolicy().anchor(pivots, pivots[-1], PARAMS)

    assert anchor is not None
    assert anchor.bar_index == 30


def test_count_touches_counts_anchors_and_excludes_pivots_outside_tolerance():
    # The 70 -> 58 line over 30 bars has slope -0.4, so it predicts:
    #   bar 10 -> 70.0  (anchor, exact)
    #   bar 20 -> 66.0  vs pivot 64.0 -> 2.0 away, OUTSIDE the 1.5 tolerance
    #   bar 30 -> 62.0  (exact touch)
    #   bar 40 -> 58.0  (anchor, exact)
    pivots = [high(10, 70.0), high(20, 64.0), high(30, 62.0), high(40, 58.0)]
    line = RSILine(start_bar_index=10, end_bar_index=40, start_rsi=70.0, end_rsi=58.0, direction="down")

    assert count_touches(line, pivots, tolerance=1.5) == 3
    assert count_touches(line, pivots, tolerance=2.5) == 4  # widening admits bar 20


def test_count_touches_ignores_pivots_outside_the_line_span():
    pivots = [high(5, 80.0), high(10, 70.0), high(40, 58.0), high(50, 40.0)]
    line = RSILine(start_bar_index=10, end_bar_index=40, start_rsi=70.0, end_rsi=58.0, direction="down")

    assert count_touches(line, pivots, tolerance=1.5) == 2  # only the two anchors
