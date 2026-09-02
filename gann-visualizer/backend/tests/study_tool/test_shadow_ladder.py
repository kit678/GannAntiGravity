"""
Shadow ladders: the real ladder slid sideways.

A shadow keeps the number of levels, their spacing (including the uneven
spacing of off-centre crosses) and their ordering, and destroys only whether
they sit at Gann prices. It must never trigger a grid rebuild - that is the
difference between a 3-hour corpus build and a 67-hour one.
"""
import sys
import os

import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.run_ladder_study import build_all_ladders, degree_to_square
from study_tool.shadow_ladder import shadow_offsets, shift_ladder

SUN = degree_to_square(155.0)
MOON = degree_to_square(331.0)


def real_ladder(scale=1):
    return build_all_ladders(1307.35, scale, SUN, MOON)


def test_shadow_has_the_same_number_of_levels():
    levels = real_ladder()
    assert len(shift_ladder(levels, 0.4, scale=1)) == len(levels)


def test_spacing_between_levels_is_preserved_exactly():
    """The control tests the prices, not the shape. The shape must survive."""
    levels = sorted(real_ladder(), key=lambda l: l["price"])
    shifted = sorted(shift_ladder(levels, 0.4, scale=1), key=lambda l: l["price"])

    real_gaps = [b["price"] - a["price"] for a, b in zip(levels, levels[1:])]
    shadow_gaps = [b["price"] - a["price"] for a, b in zip(shifted, shifted[1:])]

    for real, shadow in zip(real_gaps, shadow_gaps):
        assert real == pytest.approx(shadow, abs=1e-9)


def test_labels_are_untouched():
    """Arm, ring, source and kind identify the level and must not move."""
    levels = real_ladder()
    shifted = shift_ladder(levels, 0.4, scale=1)
    for before, after in zip(levels, shifted):
        for field in ("source", "kind", "degree", "ring", "sub_index",
                      "is_halfway"):
            assert before[field] == after[field]


def test_square_stays_consistent_with_price():
    """price == square / scale is an invariant the rest of the code relies on."""
    levels = real_ladder(scale=10)
    shifted = shift_ladder(levels, 0.4, scale=10)
    for level in shifted:
        assert level["price"] == pytest.approx(level["square"] / 10, abs=1e-9)


def test_sub_level_gap_is_unchanged_by_a_shift():
    """
    The analyzer derives touch tolerance from segment_start/segment_end. A
    constant shift must not change that width, or the shadow would be measured
    with a different yardstick than the real ladder.
    """
    from study_tool.gann_ladder_analyzer import GannLadderAnalyzer

    levels = [l for l in real_ladder(scale=10) if l["kind"] == "sub"]
    shifted = shift_ladder(levels, 0.4, scale=10)
    analyzer = GannLadderAnalyzer({"price_scale": 10})

    for before, after in zip(levels, shifted):
        assert analyzer._sub_gap(before) == pytest.approx(
            analyzer._sub_gap(after), abs=1e-9)


def test_the_original_ladder_is_not_mutated():
    levels = real_ladder()
    prices_before = [l["price"] for l in levels]
    shift_ladder(levels, 0.4, scale=1)
    assert [l["price"] for l in levels] == prices_before


def test_offsets_avoid_landing_back_on_the_real_levels():
    """
    An offset near zero or near a whole gap puts the shadow on top of the real
    ladder and dilutes the contrast the control exists to create.
    """
    gap = 2.25
    offsets = shadow_offsets(count=50, gap=gap, seed=7)

    assert len(offsets) == 50
    for delta in offsets:
        assert 0.1 * gap <= delta <= 0.9 * gap


def test_offsets_are_reproducible_from_the_seed():
    assert shadow_offsets(50, 2.25, seed=7) == shadow_offsets(50, 2.25, seed=7)
    assert shadow_offsets(50, 2.25, seed=7) != shadow_offsets(50, 2.25, seed=8)
