"""
Sub-level gap must be measured in price, not in grid squares.

`segment_start` and `segment_end` are squares. A level's `price` is
`square / price_scale`. So a gap derived from the segment bounds has to be
divided by the scale before it is compared against bar highs and lows.

At scale 1 the two units are numerically identical, which is why every other
test in this suite passes either way. These tests run at scale 10, where they
differ by exactly that factor, and check against a real ladder rather than a
synthetic one so the expected value comes from the geometry itself.
"""
import math
import sys
import os

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.gann_ladder_analyzer import GannLadderAnalyzer
from study_tool.run_ladder_study import build_all_ladders, degree_to_square

PRICE = 1307.35          # RELIANCE, roughly spot
SUN = degree_to_square(155.0)
MOON = degree_to_square(331.0)


def real_ladder(scale):
    return build_all_ladders(PRICE, scale, SUN, MOON)


def adjacent_subs(levels):
    """Two neighbouring sub-levels from one segment, and their true price gap."""
    for lv in levels:
        if lv["kind"] != "sub" or lv.get("sub_index") is None:
            continue
        for other in levels:
            if (other.get("source") == lv["source"]
                    and other.get("segment_start") == lv["segment_start"]
                    and other.get("sub_index") == lv["sub_index"] + 1):
                return lv, other, abs(other["price"] - lv["price"])
    raise AssertionError("no adjacent sub-level pair found in the ladder")


def test_sub_gap_is_a_price_distance_at_scale_10():
    levels = real_ladder(10)
    lower, _upper, true_gap = adjacent_subs(levels)

    analyzer = GannLadderAnalyzer({"price_scale": 10})

    assert math.isclose(analyzer._sub_gap(lower), true_gap, rel_tol=1e-9), (
        "sub gap must equal the real price distance between adjacent "
        "sub-levels, not the distance in grid squares"
    )


def test_sub_gap_unchanged_at_scale_1():
    """Regression guard: scale 1 behaviour must not move."""
    levels = real_ladder(1)
    lower, _upper, true_gap = adjacent_subs(levels)

    analyzer = GannLadderAnalyzer({"price_scale": 1})

    assert math.isclose(analyzer._sub_gap(lower), true_gap, rel_tol=1e-9)


def test_touch_tolerance_stays_inside_one_level_at_scale_10():
    """
    The consequence that matters.

    Tolerance is a fraction of the gap. If the gap is inflated by the scale,
    tolerance grows to a whole level wide and every bar 'touches' something,
    which would quietly destroy the x10 corpus rather than fail loudly.
    """
    levels = real_ladder(10)
    lower, _upper, true_gap = adjacent_subs(levels)

    analyzer = GannLadderAnalyzer({
        "price_scale": 10,
        "touch_tolerance_sublevels": 0.1,
    })
    tolerance = analyzer._sub_gap(lower) * analyzer.touch_tolerance

    assert tolerance < true_gap / 2, (
        f"tolerance {tolerance} reaches beyond half a level ({true_gap / 2}); "
        "levels would overlap and every bar would register a touch"
    )


def test_sub_gap_falls_back_to_one_when_segment_is_missing():
    """A level with no segment bounds still returns the documented default."""
    analyzer = GannLadderAnalyzer({"price_scale": 10})
    assert analyzer._sub_gap({"price": 100.0}) == 1.0
