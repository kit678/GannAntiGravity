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


from study_tool.gann_ladder import build_gann_square


def test_spiral_places_the_first_ring_correctly():
    grid = build_gann_square(27, 1)
    centre = grid["centre"]
    by_value = {c["value"]: (c["row"], c["col"]) for c in grid["position_sequence"]}
    # 2 is left of centre, 3 above that, and 9 closes ring 1 down-left.
    assert by_value[1] == centre
    assert by_value[2] == (centre[0], centre[1] - 1)
    assert by_value[9] == (centre[0] + 1, centre[1] - 1)


def test_odd_squares_lie_on_one_diagonal():
    grid = build_gann_square(400, 1)
    centre = grid["centre"]
    by_value = {c["value"]: (c["row"], c["col"]) for c in grid["position_sequence"]}
    # (2m+1)^2 sits at offset (m, -m).
    for m, square in enumerate([1, 9, 25, 49, 81, 121, 169, 225, 289, 361]):
        row, col = by_value[square]
        assert (row - centre[0], col - centre[1]) == (m, -m)


def test_body_one_resolves_to_the_grid_centre():
    grid = build_gann_square(27, 1)
    assert grid["body_position"] == grid["centre"]
    assert grid["body_found"] is True


def test_target_and_body_positions_are_found():
    grid = build_gann_square(27, 155)
    assert grid["target_found"] is True
    assert grid["body_found"] is True
    by_value = {c["value"]: (c["row"], c["col"]) for c in grid["position_sequence"]}
    assert grid["target_position"] == by_value[27]
    assert grid["body_position"] == by_value[155]


def test_grid_expands_to_contain_both_target_and_body():
    # A small target with a large body still needs a grid holding the body.
    grid = build_gann_square(27, 360)
    assert grid["target_found"] is True
    assert grid["body_found"] is True


def test_too_large_a_grid_is_refused_rather_than_built():
    grid = build_gann_square(50_000_000, 1)
    assert grid["too_large"] is True
    assert grid["position_sequence"] == []


from study_tool.gann_ladder import cross_marks, subdivide


def test_cross_marks_reproduces_the_worked_example():
    grid = build_gann_square(27, 1)
    marks = cross_marks(grid, grid["body_position"], grid["target_position"], 8)
    assert [c["value"] for c in marks["up"]] == [28, 31, 34, 37, 40, 43, 46, 49]
    assert [c["value"] for c in marks["down"]] == [25, 23, 21, 19, 17, 15, 13, 11]


def test_cross_marks_inward_walk_steps_by_the_inner_ring_width():
    # Ring 2 spans 9..24 with a 45 degree step of 2.
    grid = build_gann_square(27, 1)
    marks = cross_marks(grid, grid["body_position"], grid["target_position"], 8)
    values = [c["value"] for c in marks["down"]]
    gaps = [values[i] - values[i + 1] for i in range(len(values) - 1)]
    assert gaps == [2, 2, 2, 2, 2, 2, 2]


def test_cross_marks_honours_the_requested_count():
    grid = build_gann_square(27, 1)
    marks = cross_marks(grid, grid["body_position"], grid["target_position"], 3)
    assert len(marks["up"]) == 3
    assert len(marks["down"]) == 3


def test_cross_marks_returns_fewer_near_the_edge_rather_than_raising():
    grid = build_gann_square(27, 1)
    marks = cross_marks(grid, grid["body_position"], grid["target_position"], 500)
    assert 0 < len(marks["up"]) < 500


def test_cross_marks_empty_when_the_target_is_missing():
    grid = build_gann_square(27, 1)
    marks = cross_marks(grid, grid["body_position"], (-1, -1), 8)
    assert marks["up"] == []
    assert marks["down"] == []


def test_cross_marks_arm_angles_advance_in_order_and_wrap_after_eight():
    grid = build_gann_square(3197, 155)
    marks = cross_marks(grid, grid["body_position"], grid["target_position"], 9)
    degrees = [
        arm_degree((c["row"], c["col"]), grid["body_position"])
        for c in marks["up"]
    ]
    assert len(set(degrees[:8])) == 8
    assert degrees[8] == degrees[0]


def test_cross_marks_off_centre_spacing_is_uneven():
    grid = build_gann_square(3197, 155)
    marks = cross_marks(grid, grid["body_position"], grid["target_position"], 8)
    values = [c["value"] for c in marks["up"]]
    gaps = {values[i + 1] - values[i] for i in range(len(values) - 1)}
    assert len(gaps) > 1


def test_subdivide_reproduces_the_worked_example():
    assert subdivide(25, 28) == [
        25.375, 25.75, 26.125, 26.5, 26.875, 27.25, 27.625, 28,
    ]


def test_subdivide_returns_eight_points_ending_at_the_upper_bound():
    points = subdivide(49, 81)
    assert len(points) == 8
    assert points[-1] == 81


def test_subdivide_honours_a_custom_part_count():
    assert subdivide(0, 4, 4) == [1, 2, 3, 4]


from study_tool.gann_ladder import build_ladder


def centre_ladder(target=27, scale=1, count=8):
    grid = build_gann_square(target, 1)
    return build_ladder(
        grid=grid,
        cross_centre=grid["body_position"],
        source="center",
        scale=scale,
        count=count,
    )


def test_ladder_includes_the_worked_example_majors():
    majors = [lv["square"] for lv in centre_ladder() if lv["kind"] == "major"]
    for square in (11, 13, 25, 28, 31, 49):
        assert square in majors


def test_ladder_subdivides_the_straddling_segment():
    # 27 sits between 25 and 28. Sorted descending, so highest first.
    subs = [
        lv["square"]
        for lv in centre_ladder()
        if lv["kind"] == "sub" and lv["segment_start"] == 25 and lv["segment_end"] == 28
    ]
    assert subs == [27.625, 27.25, 26.875, 26.5, 26.125, 25.75, 25.375]


def test_straddling_segment_has_levels_both_sides_of_the_price():
    subs = [lv for lv in centre_ladder() if lv["segment_start"] == 25]
    assert any(lv["direction"] == "up" for lv in subs)
    assert any(lv["direction"] == "down" for lv in subs)


def test_ladder_emits_sub_indices_one_to_seven_only():
    ladder = centre_ladder()
    indices = {lv["sub_index"] for lv in ladder if lv["kind"] == "sub"}
    assert sorted(indices) == [1, 2, 3, 4, 5, 6, 7]


def test_ladder_has_no_duplicate_squares():
    squares = [lv["square"] for lv in centre_ladder()]
    assert len(set(squares)) == len(squares)


def test_ladder_flags_the_halfway_sub_level():
    halfway = [lv for lv in centre_ladder() if lv["is_halfway"]]
    assert all(lv["sub_index"] == 4 for lv in halfway)
    straddling = next(lv for lv in halfway if lv["segment_start"] == 25)
    assert straddling["square"] == 26.5


def test_ladder_labels_majors_with_their_own_arm_angle():
    by_square = {
        lv["square"]: lv["degree"] for lv in centre_ladder() if lv["kind"] == "major"
    }
    assert by_square[25] == 0
    assert by_square[28] == 45
    assert by_square[49] == 0


def test_sub_levels_inherit_the_angle_of_their_segment():
    subs = [lv for lv in centre_ladder() if lv["segment_start"] == 25]
    assert all(lv["degree"] == 0 for lv in subs)


def test_sub_levels_take_the_ring_of_their_segment_start():
    # 49 opens ring 4. A sub-level just below it belongs to a segment starting
    # in ring 3, so it must be tagged ring 3.
    ladder = centre_ladder(target=48)
    just_below = next(
        lv for lv in ladder
        if lv["kind"] == "sub" and lv["segment_end"] == 49 and lv["sub_index"] == 7
    )
    assert just_below["square"] > 48
    assert just_below["ring"] == 3


def test_a_price_exactly_on_a_major_is_listed_as_a_major():
    # 28 sits on the centre cross's 45 degree arm.
    ladder = centre_ladder(target=28)
    major = next(lv for lv in ladder if lv["square"] == 28)
    assert major["kind"] == "major"
    assert major["degree"] == 45
    starts = {lv["segment_start"] for lv in ladder if lv["kind"] == "sub"}
    assert 25 in starts
    assert 28 in starts


def test_scale_changes_price_but_not_square():
    plain = centre_ladder(scale=1)
    scaled = centre_ladder(scale=10)
    assert scaled[0]["square"] == plain[0]["square"]
    assert abs(scaled[0]["price"] - plain[0]["square"] / 10) < 1e-9


def test_fractional_sub_levels_survive_scaling():
    level = next(
        lv for lv in centre_ladder(scale=10)
        if lv["kind"] == "sub" and lv["square"] == 26.5
    )
    assert abs(level["price"] - 2.65) < 1e-9


def test_ladder_is_sorted_by_square_descending():
    squares = [lv["square"] for lv in centre_ladder()]
    assert squares == sorted(squares, reverse=True)


def test_ladder_tags_every_level_with_its_source():
    grid = build_gann_square(27, 1)
    ladder = build_ladder(
        grid=grid, cross_centre=grid["body_position"], source="moon", scale=1, count=8
    )
    assert all(lv["source"] == "moon" for lv in ladder)


def test_empty_ladder_when_the_target_is_missing():
    grid = build_gann_square(27, 1)
    ladder = build_ladder(
        grid=grid,
        cross_centre=grid["body_position"],
        source="center",
        scale=1,
        count=8,
        target_position=(-1, -1),
    )
    assert ladder == []
