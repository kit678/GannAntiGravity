"""
Tests for the Gann ladder maths, ported from utils/gannLevels.js in the
GannSq9 repo. Expected values are taken from that module's passing JS suite -
a disagreement means this port is wrong, not the expectations.
"""
import sys
import os

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.gann_ladder import arm_degree, ring_of


CENTRE = (0, 0)


def test_arm_degree_labels_the_eight_arms():
    # Offsets are (row - centre_row, col - centre_col). 0 degrees is the
    # down-left diagonal, where the odd squares lie.
    cases = {
        (1, -1): 0,
        (0, -1): 45,
        (-1, -1): 90,
        (-1, 0): 135,
        (-1, 1): 180,
        (0, 1): 225,
        (1, 1): 270,
        (1, 0): 315,
    }
    for (d_row, d_col), degree in cases.items():
        assert arm_degree((d_row, d_col), CENTRE) == degree


def test_arm_degree_is_distance_independent():
    # Three cells out along an arm is the same arm as one cell out.
    assert arm_degree((3, -3), CENTRE) == 0
    assert arm_degree((5, 0), CENTRE) == 315


def test_arm_degree_returns_none_for_the_centre_itself():
    assert arm_degree((0, 0), CENTRE) is None


def test_arm_degree_returns_none_off_the_cross():
    # Neither same row, same column, nor an exact diagonal.
    assert arm_degree((1, -3), CENTRE) is None
    assert arm_degree((2, 5), CENTRE) is None


def test_arm_degree_never_returns_360():
    # A full lap beyond a 0 mark is itself 0 - the angle names the arm,
    # not the lap.
    assert arm_degree((9, -9), CENTRE) == 0


def test_arm_degree_works_off_centre():
    centre = (7, 5)
    assert arm_degree((7, 4), centre) == 45      # directly left
    assert arm_degree((7, 5), centre) is None    # the centre itself


def test_ring_of_documented_boundaries():
    cases = [
        (1, 1), (8, 1),
        (9, 2), (24, 2),
        (25, 3), (48, 3),
        (49, 4), (80, 4),
        (360, 9),
        (361, 10), (440, 10),
    ]
    for square, ring in cases:
        assert ring_of(square) == ring


def test_ring_of_odd_square_opens_a_ring():
    assert ring_of(24) == 2
    assert ring_of(25) == 3


def test_ring_of_never_below_one():
    assert ring_of(1) == 1
    assert ring_of(0) == 1
