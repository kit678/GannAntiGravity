import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from analysis.rsi_line_policy import (
    line_between,
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


# --- AdjacentAnchorPolicy -------------------------------------------------
#
# Walk-back's poke-through rule is one-sided: it rejects anchors that something
# rises ABOVE, but never rejects a line that floats far above the structure.
# Measured on BTCUSDT 15m, walk-back lines sit a mean 10.87 RSI points above the
# highs they pass over (max 37.7) and 73.6% touch nothing but their two anchors.
# Adjacency makes skipping structurally impossible instead of merely discouraged.

def test_adjacent_policy_takes_the_immediately_preceding_pivot():
    from analysis.rsi_line_policy import AdjacentAnchorPolicy

    pivots = [high(10, 70.0), high(20, 64.0), high(30, 62.0), high(40, 58.0)]

    anchor = AdjacentAnchorPolicy().anchor(pivots, pivots[-1], PARAMS)

    assert anchor is not None
    assert anchor.bar_index == 30, "must use the adjacent high, not reach back to 10"


def test_adjacent_policy_refuses_to_skip_when_the_adjacent_pivot_fails():
    """The defining property: it declines rather than reaching further back.

    Walk-back would skip bar 30 here and anchor at bar 20, producing a line that
    passes over bar 30. Adjacency emits no line at all.
    """
    from analysis.rsi_line_policy import AdjacentAnchorPolicy

    # bar 30 is HIGHER than the newest, so it fails the lower-high test
    pivots = [high(10, 70.0), high(20, 64.0), high(30, 45.0), high(40, 58.0)]

    assert AdjacentAnchorPolicy().anchor(pivots, pivots[-1], PARAMS) is None


def test_adjacent_policy_declines_when_the_adjacent_pivot_is_too_close():
    from analysis.rsi_line_policy import AdjacentAnchorPolicy

    pivots = [high(10, 70.0), high(37, 58.0), high(40, 55.0)]  # span 3 < min_length

    assert AdjacentAnchorPolicy().anchor(pivots, pivots[-1], PARAMS) is None


def test_adjacent_policy_never_leaves_an_intermediate_same_kind_pivot():
    """Zero-skip, stated as the property rather than as an example."""
    from analysis.rsi_line_policy import AdjacentAnchorPolicy

    pivots = [high(0, 90.0), high(12, 80.0), high(24, 74.0), high(36, 70.0), high(48, 61.0)]
    policy = AdjacentAnchorPolicy()

    for idx in range(1, len(pivots)):
        newest = pivots[idx]
        anchor = policy.anchor(pivots[: idx + 1], newest, PARAMS)
        if anchor is None:
            continue
        between = [
            p for p in pivots
            if anchor.bar_index < p.bar_index < newest.bar_index and p.kind == newest.kind
        ]
        assert between == [], f"skipped {[p.bar_index for p in between]}"


# --- CollinearExtendAnchorPolicy ------------------------------------------

def test_collinear_extend_reaches_back_through_pivots_that_sit_on_the_line():
    from analysis.rsi_line_policy import CollinearExtendAnchorPolicy

    # 70 / 64 / 62 / 58: bar 20 is 2.0 off the 70->58 line, bar 30 is exact
    pivots = [high(10, 70.0), high(20, 64.0), high(30, 62.0), high(40, 58.0)]
    loose = GeometryParams(min_length=8, max_span_bars=150, tolerance=5.0)

    anchor = CollinearExtendAnchorPolicy().anchor(pivots, pivots[-1], loose)

    assert anchor is not None
    assert anchor.bar_index == 10, "should extend all the way back while collinear"


def test_collinear_extend_stops_where_the_structure_leaves_the_line():
    from analysis.rsi_line_policy import CollinearExtendAnchorPolicy

    # bar 20 sits far BELOW the 70->58 line, so the line must not reach past bar 30
    pivots = [high(10, 70.0), high(20, 40.0), high(30, 62.0), high(40, 58.0)]
    loose = GeometryParams(min_length=8, max_span_bars=150, tolerance=5.0)

    anchor = CollinearExtendAnchorPolicy().anchor(pivots, pivots[-1], loose)

    assert anchor is not None
    assert anchor.bar_index == 30, "must stop at the last collinear pivot"


def test_collinear_extend_never_leaves_a_pivot_off_the_line():
    """The property that makes it safe: same zero-skip guarantee as adjacency."""
    from analysis.rsi_line_policy import CollinearExtendAnchorPolicy

    pivots = [high(0, 90.0), high(12, 84.0), high(24, 61.0), high(36, 70.0), high(48, 61.0)]
    loose = GeometryParams(min_length=8, max_span_bars=150, tolerance=5.0)
    policy = CollinearExtendAnchorPolicy()

    for idx in range(1, len(pivots)):
        newest = pivots[idx]
        anchor = policy.anchor(pivots[: idx + 1], newest, loose)
        if anchor is None:
            continue
        line = line_between(anchor, newest)
        for m in pivots[: idx + 1]:
            if anchor.bar_index < m.bar_index < newest.bar_index:
                assert abs(m.rsi_value - line.value_at(m.bar_index)) <= loose.tolerance, (
                    f"pivot at bar {m.bar_index} was skipped"
                )


def test_collinear_extend_degenerates_to_adjacency_at_tight_tolerance():
    """Explains why tolerance 1.5 hid the multi-touch structure entirely."""
    from analysis.rsi_line_policy import AdjacentAnchorPolicy, CollinearExtendAnchorPolicy

    pivots = [high(10, 70.0), high(20, 64.0), high(30, 62.0), high(40, 58.0)]
    tight = GeometryParams(min_length=8, max_span_bars=150, tolerance=0.5)

    assert (CollinearExtendAnchorPolicy().anchor(pivots, pivots[-1], tight).bar_index
            == AdjacentAnchorPolicy().anchor(pivots, pivots[-1], tight).bar_index)
