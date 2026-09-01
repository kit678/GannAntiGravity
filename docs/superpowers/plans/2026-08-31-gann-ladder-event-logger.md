# Gann Ladder Event Logger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Walk historical bars and record every interaction between price and a Gann Square-of-9 level, producing a dataset Phase 3 can mine.

**Architecture:** Port Phase 1's ladder maths from JavaScript to Python (five pure functions, verified against the JS suite's exact expected values). Extend the existing `EventType` and `Event` in `study_tool/event_logger.py` with ladder-specific types and fields rather than forking them. Add one stateful analyzer, `GannLadderAnalyzer`, shaped like the existing `BreachAnalyzer` — constructed with a config dict, fed one bar at a time, holding serialisable state.

**Tech Stack:** Python 3, pytest, dataclasses. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-31-gann-ladder-event-logger-design.md`

---

## Context an implementer needs

**Phase 1 already exists, in a different repo and language.** `C:\Dev\GannSq9\utils\gannLevels.js` holds the ladder maths, with 37 passing tests in `C:\Dev\GannSq9\utils\__tests__\gannLevels.test.js`. Tasks 1–4 port it. Every expected value in those tasks was taken from that passing JS suite — if a port disagrees, the port is wrong.

**A "ladder" is a labeled list of price levels.** Major levels are actual squares lying on a cross through the grid. Each gap between consecutive majors is divided into eighths; seven sub-levels are emitted (the eighth is the next major).

**"Ring" means a band of values between consecutive odd squares** — 25..48 is ring 3. It is *not* a cell's distance from the grid centre. Square 361 sits nine cells out but opens ring 10.

**Run everything from** `C:\Dev\GannTesting\gann-visualizer\backend`.

Tests follow the existing convention in `tests/study_tool/` — a `sys.path.append` to the backend root, then a normal import. Verified working: `python -m pytest tests/study_tool/ -q` currently passes 4 tests.

---

## File Structure

| File | Responsibility |
|---|---|
| `study_tool/gann_ladder.py` (create) | Pure ladder maths, ported from JS. No state, no I/O. |
| `tests/study_tool/test_gann_ladder.py` (create) | Port verification against the JS suite's values. |
| `study_tool/event_logger.py` (modify) | Add ladder event types and ladder fields to `Event`. |
| `study_tool/gann_ladder_analyzer.py` (create) | Stateful bar-by-bar analyzer producing events. |
| `tests/study_tool/test_gann_ladder_analyzer.py` (create) | Analyzer behaviour on synthetic bars. |

---

## Task 1: Arm angle and ring attribution

**Files:**
- Create: `study_tool/gann_ladder.py`
- Create: `tests/study_tool/test_gann_ladder.py`

Two pure functions with no dependencies.

`arm_degree` answers which of a cross's eight arms a cell sits on. It returns `None` both for the cross's own centre (which belongs to every arm at once) and for any cell not on the cross — that second behaviour is what lets it double as the "is this on the cross" test later.

`ring_of` answers which value band a square falls in. Ring `k` spans `(2k-1)**2` to `(2k+1)**2 - 1`, a width of `8k`.

- [ ] **Step 1: Write the failing test**

Create `tests/study_tool/test_gann_ladder.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/study_tool/test_gann_ladder.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'study_tool.gann_ladder'`

- [ ] **Step 3: Write minimal implementation**

Create `study_tool/gann_ladder.py`:

```python
"""
Gann Square-of-9 level ladder maths.

A Python port of utils/gannLevels.js from the GannSq9 repo. Pure functions,
no state, no I/O. See:
  docs/superpowers/specs/2026-08-31-gann-ladder-event-logger-design.md

Terminology note: "ring" here means a band of values between consecutive odd
squares - ring 3 spans 25..48. It is NOT a cell's geometric distance from the
grid centre. Square 361 sits nine cells out but opens ring 10.
"""

import math
from typing import Dict, List, Optional, Sequence, Tuple

# Arm angle by the sign of the offset from the cross centre, keyed
# (sign(d_row), sign(d_col)). 0 degrees is the down-left diagonal, which is
# where the odd squares (1, 9, 25, 49 ...) lie.
_ARM_BY_SIGN = {
    (1, -1): 0,
    (0, -1): 45,
    (-1, -1): 90,
    (-1, 0): 135,
    (-1, 1): 180,
    (0, 1): 225,
    (1, 1): 270,
    (1, 0): 315,
}


def arm_degree(
    cell: Tuple[int, int],
    cross_centre: Tuple[int, int],
) -> Optional[int]:
    """
    Which of a cross's eight arms a cell sits on.

    Returns None for the cross's own centre (it belongs to every arm at once)
    and None for any cell not on the cross at all. That second case makes this
    usable as the on-cross predicate.

    Never returns 360: a mark one full lap beyond a 0 mark is itself 0. The
    angle identifies the arm, not the lap.

    Args:
        cell: (row, col) of the cell
        cross_centre: (row, col) of the cross's centre

    Returns:
        0, 45, 90, 135, 180, 225, 270, 315, or None
    """
    d_row = cell[0] - cross_centre[0]
    d_col = cell[1] - cross_centre[1]

    if d_row == 0 and d_col == 0:
        return None

    on_cross = d_row == 0 or d_col == 0 or abs(d_row) == abs(d_col)
    if not on_cross:
        return None

    def sign(value: int) -> int:
        return (value > 0) - (value < 0)

    return _ARM_BY_SIGN.get((sign(d_row), sign(d_col)))


def ring_of(square: float) -> int:
    """
    Which value ring a square falls in.

    Ring k spans (2k-1)^2 .. (2k+1)^2 - 1, a width of 8k. This is a band of
    values between consecutive odd squares, NOT a cell's distance from the
    grid centre.

    Args:
        square: the grid square number

    Returns:
        ring index, at least 1
    """
    return max(1, math.floor((math.sqrt(max(square, 0)) + 1) / 2))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/study_tool/test_gann_ladder.py -q`
Expected: PASS, 9 tests

- [ ] **Step 5: Commit**

```bash
git add study_tool/gann_ladder.py tests/study_tool/test_gann_ladder.py
git commit -m "feat: port Gann arm-angle and ring attribution to Python"
```

---

## Task 2: Building the spiral grid

**Files:**
- Modify: `study_tool/gann_ladder.py`
- Modify: `tests/study_tool/test_gann_ladder.py`

The spiral itself. Value 1 sits at the centre; the walk goes left, up, right, down, left, expanding by one ring each lap. The traversal order is recorded because that is what the level search walks.

Two positions are recorded during construction: the `target` (the price's square) and the `body` (a celestial degree used as a square number). Passing `body=1` therefore returns the grid centre, which is how the centre cross is obtained without special-casing it.

- [ ] **Step 1: Write the failing test**

Append to `tests/study_tool/test_gann_ladder.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/study_tool/test_gann_ladder.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_gann_square'`

- [ ] **Step 3: Write minimal implementation**

Append to `study_tool/gann_ladder.py`:

```python
# Grids larger than this are refused rather than built. A million cells is
# already far beyond any real price, and building more wastes minutes.
MAX_CELLS = 4_000_000


def _rings_for(value: float) -> int:
    """Rings needed to contain a value, plus headroom."""
    return max(math.ceil(math.sqrt(max(value, 1)) / 2) + 3, 4)


def build_gann_square(target: int, body: int) -> Dict:
    """
    Build the Square-of-9 spiral containing both the target and the body.

    Passing body=1 returns a grid whose body_position is the grid centre,
    which is how the centre cross is obtained without a special case.

    Args:
        target: the price-derived square to centre the analysis on
        body: a celestial degree, used as a square number

    Returns:
        dict with position_sequence, centre, target_position, body_position,
        target_found, body_found, too_large
    """
    rings = max(_rings_for(max(target, body)), 4)
    dimension = 2 * rings + 1

    empty = {
        "position_sequence": [],
        "centre": (0, 0),
        "target_position": None,
        "body_position": None,
        "target_found": False,
        "body_found": False,
        "too_large": True,
        "dimension": 0,
    }
    if dimension * dimension > MAX_CELLS:
        return empty

    centre_index = rings
    row = col = centre_index
    centre = (centre_index, centre_index)

    position_sequence = [{"row": row, "col": col, "value": 1}]
    target_position = centre if target == 1 else None
    body_position = centre if body == 1 else None

    current = 2
    limit = dimension * dimension

    def step(direction: str, count: int) -> None:
        nonlocal row, col, current, target_position, body_position
        for _ in range(count):
            if current > limit:
                return
            if direction == "left":
                col -= 1
            elif direction == "up":
                row -= 1
            elif direction == "right":
                col += 1
            else:
                row += 1
            position_sequence.append({"row": row, "col": col, "value": current})
            if current == target:
                target_position = (row, col)
            if current == body:
                body_position = (row, col)
            current += 1

    ring = 1
    while current <= limit and ring <= rings:
        step("left", 1)
        step("up", 2 * ring - 1)
        step("right", 2 * ring)
        step("down", 2 * ring)
        step("left", 2 * ring)
        ring += 1

    return {
        "position_sequence": position_sequence,
        "centre": centre,
        "target_position": target_position,
        "body_position": body_position,
        "target_found": target_position is not None,
        "body_found": body_position is not None,
        "too_large": False,
        "dimension": dimension,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/study_tool/test_gann_ladder.py -q`
Expected: PASS, 15 tests

- [ ] **Step 5: Commit**

```bash
git add study_tool/gann_ladder.py tests/study_tool/test_gann_ladder.py
git commit -m "feat: port the Gann spiral grid construction to Python"
```

---

## Task 3: Walking the cross and subdividing gaps

**Files:**
- Modify: `study_tool/gann_ladder.py`
- Modify: `tests/study_tool/test_gann_ladder.py`

`cross_marks` walks the spiral outward and inward from the price's square, collecting cells on the cross. It uses `arm_degree(...) is not None` as its test, so there is one definition of "on the cross" rather than two.

A consequence: the cross's own centre cell is excluded, because `arm_degree`
returns `None` for it. That cell has no single arm to be labelled with.

`subdivide` splits a gap into eight, returning all eight points. The eighth
equals the upper bound; `build_ladder` drops it later because it is already
the next major mark.

- [ ] **Step 1: Write the failing test**

Append to `tests/study_tool/test_gann_ladder.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/study_tool/test_gann_ladder.py -q`
Expected: FAIL — `ImportError: cannot import name 'cross_marks'`

- [ ] **Step 3: Write minimal implementation**

Append to `study_tool/gann_ladder.py`:

```python
def cross_marks(
    grid: Dict,
    cross_centre: Tuple[int, int],
    target_position: Tuple[int, int],
    count: int = 8,
) -> Dict[str, List[Dict]]:
    """
    Collect the squares lying on a cross, walking the spiral out from and back
    from the price's square.

    The cross's own centre cell is excluded, since arm_degree returns None for
    it and it therefore has no arm to be labelled with.

    Args:
        grid: from build_gann_square
        cross_centre: (row, col) the cross passes through
        target_position: (row, col) of the price's square
        count: marks to collect in each direction

    Returns:
        {"up": [...], "down": [...]} of cells, in walk order
    """
    sequence = grid["position_sequence"]
    up: List[Dict] = []
    down: List[Dict] = []

    target_index = None
    for index, cell in enumerate(sequence):
        if (cell["row"], cell["col"]) == tuple(target_position):
            target_index = index
            break
    if target_index is None:
        return {"up": up, "down": down}

    def on_cross(cell: Dict) -> bool:
        return arm_degree((cell["row"], cell["col"]), cross_centre) is not None

    for index in range(target_index + 1, len(sequence)):
        if len(up) >= count:
            break
        if on_cross(sequence[index]):
            up.append(sequence[index])

    for index in range(target_index - 1, -1, -1):
        if len(down) >= count:
            break
        if on_cross(sequence[index]):
            down.append(sequence[index])

    return {"up": up, "down": down}


def subdivide(low: float, high: float, parts: int = 8) -> List[float]:
    """
    Split a gap into equal parts, returning the division points.

    The final element equals `high`. build_ladder drops it, because it is the
    next major mark and is already in the ladder under its own entry.
    """
    step = (high - low) / parts
    return [low + step * (i + 1) for i in range(parts)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/study_tool/test_gann_ladder.py -q`
Expected: PASS, 25 tests

- [ ] **Step 5: Commit**

```bash
git add study_tool/gann_ladder.py tests/study_tool/test_gann_ladder.py
git commit -m "feat: port Gann cross-mark collection and gap subdivision"
```

---

## Task 4: Assembling the ladder

**Files:**
- Modify: `study_tool/gann_ladder.py`
- Modify: `tests/study_tool/test_gann_ladder.py`

The entry point. Four details matter, each with a test:

1. **The straddling segment.** The price sits between the nearest mark below and above. That gap is the one price is actually trading inside, so marks are merged into one ascending list and every consecutive pair is subdivided, that pair included.
2. **A price exactly on a major.** `cross_marks` only walks strictly outward, so it never tests the target's own cell. If that cell is itself on the cross it must be spliced in, or the segments either side wrongly merge into one.
3. **No duplicates.** `subdivide` returns eight points and the eighth is the next major, so only sub-indices 1–7 are emitted.
4. **Direction is per level**, comparing the level's own square against the price's square — not inherited from which walk found the bounding mark, since the straddling segment's sub-levels fall on both sides.

Sub-levels take the angle and ring of `segment_start`, not of their own fractional value. A sub-level just under a ring boundary would otherwise land in the wrong ring.

- [ ] **Step 1: Write the failing test**

Append to `tests/study_tool/test_gann_ladder.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/study_tool/test_gann_ladder.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_ladder'`

- [ ] **Step 3: Write minimal implementation**

Append to `study_tool/gann_ladder.py`:

```python
# Sub-levels emitted per segment. The 8th is the next major mark.
SUBS_PER_SEGMENT = 7

# The sub-index that lands on the midpoint of a segment.
HALFWAY_SUB_INDEX = 4


def build_ladder(
    grid: Dict,
    cross_centre: Tuple[int, int],
    source: str,
    scale: float = 1,
    count: int = 8,
    target_position: Optional[Tuple[int, int]] = None,
) -> List[Dict]:
    """
    Build the full labeled level ladder for one cross.

    Marks are merged into a single ascending list before subdividing, so the
    segment straddling the price is treated like any other. That segment is
    the one price is actually trading inside, so it must not be skipped.

    Args:
        grid: from build_gann_square
        cross_centre: (row, col) the cross passes through
        source: 'center', 'sun' or 'moon'
        scale: price multiplier used to reach the grid (1 or 10)
        count: major marks per direction
        target_position: defaults to the grid's own target

    Returns:
        list of level dicts, sorted by square descending
    """
    if target_position is None:
        target_position = grid["target_position"]
    if target_position is None:
        return []

    marks = cross_marks(grid, cross_centre, target_position, count)
    if not marks["up"] and not marks["down"]:
        return []

    target_square = None
    for cell in grid["position_sequence"]:
        if (cell["row"], cell["col"]) == tuple(target_position):
            target_square = cell["value"]
            break
    if target_square is None:
        return []

    def direction_of(square: float) -> str:
        return "up" if square > target_square else "down"

    # If the price's own square sits on the cross, it is itself a major mark.
    # cross_marks only walks strictly outward, so it never tests that cell -
    # splice it in, or the segments either side would wrongly merge.
    target_cell = {
        "row": target_position[0],
        "col": target_position[1],
        "value": target_square,
    }
    target_is_major = arm_degree(tuple(target_position), cross_centre) is not None

    ascending: List[Dict] = list(reversed(marks["down"]))
    if target_is_major:
        ascending.append(target_cell)
    ascending.extend(marks["up"])

    levels: List[Dict] = []

    for cell in ascending:
        levels.append({
            "price": cell["value"] / scale,
            "square": cell["value"],
            "source": source,
            "kind": "major",
            "degree": arm_degree((cell["row"], cell["col"]), cross_centre),
            "segment_start": None,
            "segment_end": None,
            "sub_index": None,
            "is_halfway": False,
            "ring": ring_of(cell["value"]),
            "direction": direction_of(cell["value"]),
        })

    for index in range(len(ascending) - 1):
        low = ascending[index]
        high = ascending[index + 1]
        points = subdivide(low["value"], high["value"])
        # Angle and ring come from the mark that opens the segment, so a
        # sub-level near a ring boundary is not misattributed.
        segment_degree = arm_degree((low["row"], low["col"]), cross_centre)
        segment_ring = ring_of(low["value"])

        for offset in range(SUBS_PER_SEGMENT):
            square = points[offset]
            levels.append({
                "price": square / scale,
                "square": square,
                "source": source,
                "kind": "sub",
                "degree": segment_degree,
                "segment_start": low["value"],
                "segment_end": high["value"],
                "sub_index": offset + 1,
                "is_halfway": offset + 1 == HALFWAY_SUB_INDEX,
                "ring": segment_ring,
                "direction": direction_of(square),
            })

    levels.sort(key=lambda lv: lv["square"], reverse=True)
    return levels
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/study_tool/test_gann_ladder.py -q`
Expected: PASS, 40 tests

- [ ] **Step 5: Confirm the port matches the JavaScript original**

Run: `cd C:/Dev/GannSq9 && npx jest utils/__tests__/gannLevels.test.js`
Expected: PASS, 38 tests

(Note: `-q` is not a valid flag for this project's Jest CLI and will error with
"Unrecognized option \"q\"" — omit it.)

Both suites assert the same worked example — majors `25, 28, 31, 34, 37, 40, 43, 46, 49`, sub-levels `25.375 … 27.625`, ring boundaries, and the price-on-major case. If the Python suite passes and the JS one does not, or the two disagree on any of those values, stop and report it: the port has diverged.

- [ ] **Step 6: Commit**

```bash
git add study_tool/gann_ladder.py tests/study_tool/test_gann_ladder.py
git commit -m "feat: assemble the labeled Gann ladder in Python"
```

---

## Task 5: Ladder event types and fields

**Files:**
- Modify: `study_tool/event_logger.py`

Additive only. `Event` is a dataclass whose every field is optional, so new fields break no existing consumer. Event type names are prefixed `LADDER_` so ladder events stay separable from angular-coverage events in a shared corpus.

No test of its own — these are declarations, exercised by Task 6's tests.

- [ ] **Step 1: Add the event types**

In `study_tool/event_logger.py`, inside `class EventType(Enum)`, immediately after the `REST_ON_ANGLE = "REST_ON_ANGLE"` line, add:

```python

    # Gann Ladder Event Types (Phase 2)
    LADDER_TOUCH = "LADDER_TOUCH"                          # bar's range reached a level
    LADDER_CROSS = "LADDER_CROSS"                          # moved through, unconfirmed
    LADDER_BREACH_CONFIRMED = "LADDER_BREACH_CONFIRMED"    # N successive closes beyond
    LADDER_BREACH_REJECTED = "LADDER_BREACH_REJECTED"      # crossed, failed to confirm
    LADDER_RETEST = "LADDER_RETEST"                        # returned to a breached level
    LADDER_BREACH_RESOLVED = "LADDER_BREACH_RESOLVED"      # terminal outcome assigned
```

- [ ] **Step 2: Add the display names**

In the same file, inside the `EVENT_TYPE_DISPLAY_NAMES` dict, add these entries before the closing brace:

```python
    "LADDER_TOUCH": "Ladder Touch",
    "LADDER_CROSS": "Ladder Cross",
    "LADDER_BREACH_CONFIRMED": "Ladder Breach Confirmed",
    "LADDER_BREACH_REJECTED": "Ladder Breach Rejected",
    "LADDER_RETEST": "Ladder Retest",
    "LADDER_BREACH_RESOLVED": "Ladder Breach Resolved",
```

- [ ] **Step 3: Add the ladder fields to Event**

In `class Event`, immediately after the `fan_geometry` field (the last field in the dataclass), add:

```python

    # Gann ladder level identity (Phase 2)
    level_source: Optional[str] = None        # 'center' | 'sun' | 'moon'
    level_price: Optional[float] = None
    level_square: Optional[float] = None      # fractional for sub-levels
    level_kind: Optional[str] = None          # 'major' | 'sub'
    level_degree: Optional[int] = None        # 0/45/.../315 - the arm
    level_ring: Optional[int] = None          # band between odd squares
    level_sub_index: Optional[int] = None     # 1..7, None for majors
    level_is_halfway: Optional[bool] = None
    level_segment_start: Optional[float] = None
    level_segment_end: Optional[float] = None

    # Instrument scaling in use for this walk
    price_scale: Optional[int] = None         # 1 or 10

    # Celestial body position at the time of the event
    body_degree: Optional[float] = None       # raw ecliptic longitude
    body_square: Optional[int] = None         # the square it mapped to

    # Breach linkage. Without this, "of the breaches that confirmed, how many
    # were retested and held?" cannot be answered from the corpus.
    breach_id: Optional[str] = None           # set on a confirmed breach
    parent_breach_id: Optional[str] = None    # set on its retests and resolution
```

- [ ] **Step 4: Verify the module still imports and existing tests pass**

Run: `python -c "from study_tool.event_logger import EventType, Event; print(EventType.LADDER_RETEST.value); print('breach_id' in Event.__dataclass_fields__)"`
Expected:
```
LADDER_RETEST
True
```

Run: `python -m pytest tests/study_tool/ -q`
Expected: PASS — all existing tests plus Task 1–4's, no failures

- [ ] **Step 5: Commit**

```bash
git add study_tool/event_logger.py
git commit -m "feat: add ladder event types and level identity fields"
```

---

## Task 6: The ladder analyzer

**Files:**
- Create: `study_tool/gann_ladder_analyzer.py`
- Create: `tests/study_tool/test_gann_ladder_analyzer.py`

Shaped like the existing `BreachAnalyzer`: constructed with a config dict, fed one bar at a time, holding explicit serialisable state so a long walk can be checkpointed.

**What it must not do:** decide whether a retest "held" in a way that discards the evidence. It records the raw measurements — bars elapsed, extreme reached, depth in sub-levels, whether price closed back — and applies a *default* classification on top. Phase 3 can recompute the outcome under any other threshold because every input remains in the record.

- [ ] **Step 1: Write the failing test**

Create `tests/study_tool/test_gann_ladder_analyzer.py`:

```python
"""
Tests for GannLadderAnalyzer, on synthetic bars so every case is unambiguous.
"""
import sys
import os

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.gann_ladder_analyzer import GannLadderAnalyzer
from study_tool.event_logger import EventType


def bar(open_, high, low, close, timestamp=0):
    return {
        "open": open_, "high": high, "low": low,
        "close": close, "timestamp": timestamp,
    }


def level(price, source="center", kind="major", degree=0,
          ring=3, sub_index=None, segment_start=100.0, segment_end=110.0):
    """One ladder level. Segment span 10.0 means a sub-level gap of 1.25."""
    return {
        "price": price, "square": price, "source": source, "kind": kind,
        "degree": degree, "ring": ring, "sub_index": sub_index,
        "is_halfway": sub_index == 4,
        "segment_start": segment_start, "segment_end": segment_end,
        "direction": "up",
    }


LEVELS = [level(105.0)]


def analyzer(**overrides):
    config = {
        "breach_mode": "close",
        "confirmation_closes": 2,
        "touch_tolerance_sublevels": 0.1,
        "resolution_window_bars": 50,
        "retest_window_bars": 50,
        "instrument": "RELIANCE",
        "timeframe": "5",
        "price_scale": 1,
    }
    config.update(overrides)
    return GannLadderAnalyzer(config)


def types_of(events):
    return [e.event_type for e in events]


def run(an, bars, levels=None):
    """Feed bars in order, returning every event produced."""
    levels = levels if levels is not None else LEVELS
    out = []
    for index, b in enumerate(bars):
        out.extend(an.process_bar(b, index, levels))
    return out


def test_touch_within_tolerance_emits_only_a_touch():
    an = analyzer()
    events = run(an, [bar(104.0, 105.0, 103.5, 104.2)])
    assert types_of(events) == [EventType.LADDER_TOUCH]


def test_a_bar_nowhere_near_a_level_emits_nothing():
    an = analyzer()
    events = run(an, [bar(90.0, 91.0, 89.0, 90.5)])
    assert events == []


def test_cross_without_enough_closes_is_rejected_and_never_confirmed():
    an = analyzer()
    events = run(an, [
        bar(104.0, 106.0, 103.5, 105.5),   # crosses and closes above
        bar(105.5, 105.8, 103.0, 103.5),   # falls back before a 2nd close
    ])
    kinds = types_of(events)
    assert EventType.LADDER_CROSS in kinds
    assert EventType.LADDER_BREACH_REJECTED in kinds
    resolved = [e for e in events if e.event_type == EventType.LADDER_BREACH_RESOLVED]
    assert resolved and resolved[0].details["outcome"] == "NEVER_CONFIRMED"


def test_two_successive_closes_confirm_the_breach_with_an_id():
    an = analyzer()
    events = run(an, [
        bar(104.0, 106.0, 103.5, 105.5),
        bar(105.5, 107.0, 105.2, 106.5),
    ])
    confirmed = [e for e in events if e.event_type == EventType.LADDER_BREACH_CONFIRMED]
    assert len(confirmed) == 1
    assert confirmed[0].breach_id
    assert confirmed[0].level_price == 105.0
    assert confirmed[0].direction == "up"


def test_breach_id_is_deterministic_across_identical_runs():
    bars = [
        bar(104.0, 106.0, 103.5, 105.5),
        bar(105.5, 107.0, 105.2, 106.5),
    ]
    first = run(analyzer(), bars)
    second = run(analyzer(), bars)
    ids_first = [e.breach_id for e in first if e.breach_id]
    ids_second = [e.breach_id for e in second if e.breach_id]
    assert ids_first == ids_second
    assert ids_first


def test_retest_carries_the_parent_breach_id():
    an = analyzer()
    events = run(an, [
        bar(104.0, 106.0, 103.5, 105.5),
        bar(105.5, 107.0, 105.2, 106.5),   # confirmed here
        bar(106.5, 106.8, 105.0, 105.6),   # comes back to the level
    ])
    confirmed = next(e for e in events if e.event_type == EventType.LADDER_BREACH_CONFIRMED)
    retests = [e for e in events if e.event_type == EventType.LADDER_RETEST]
    assert retests
    assert retests[0].parent_breach_id == confirmed.breach_id


def test_retest_records_raw_measurements_not_a_verdict():
    an = analyzer()
    events = run(an, [
        bar(104.0, 106.0, 103.5, 105.5),
        bar(105.5, 107.0, 105.2, 106.5),
        bar(106.5, 106.8, 105.0, 105.6),
    ])
    retest = next(e for e in events if e.event_type == EventType.LADDER_RETEST)
    for key in ("bars_since_breach", "retest_extreme",
                "depth_in_sublevels", "crossed_back", "closes_beyond"):
        assert key in retest.details


def test_depth_in_sublevels_is_negative_when_price_stops_short():
    an = analyzer()
    events = run(an, [
        bar(104.0, 106.0, 103.5, 105.5),
        bar(105.5, 107.0, 105.2, 106.5),
        bar(106.5, 106.9, 106.0, 106.4),   # low 106.0, a full sub-level short
    ])
    retests = [e for e in events if e.event_type == EventType.LADDER_RETEST]
    if retests:
        assert retests[0].details["depth_in_sublevels"] < 0


def test_price_that_never_returns_resolves_never_retested():
    an = analyzer(resolution_window_bars=3, retest_window_bars=3)
    bars = [
        bar(104.0, 106.0, 103.5, 105.5),
        bar(105.5, 107.0, 105.2, 106.5),   # confirmed
        bar(106.5, 112.0, 106.4, 111.0),
        bar(111.0, 118.0, 110.8, 117.0),
        bar(117.0, 124.0, 116.5, 123.0),
    ]
    events = run(an, bars)
    resolved = [e for e in events if e.event_type == EventType.LADDER_BREACH_RESOLVED]
    assert resolved
    assert resolved[0].details["outcome"] == "NEVER_RETESTED"


def test_a_breach_still_open_at_the_end_resolves_with_none():
    an = analyzer()
    run(an, [
        bar(104.0, 106.0, 103.5, 105.5),
        bar(105.5, 107.0, 105.2, 106.5),
    ])
    events = an.finalize()
    resolved = [e for e in events if e.event_type == EventType.LADDER_BREACH_RESOLVED]
    assert resolved
    assert resolved[0].details["outcome"] is None
    assert resolved[0].details["truncated"] is True


def test_wick_mode_confirms_on_range_rather_than_close():
    an = analyzer(breach_mode="wick", confirmation_closes=1)
    events = run(an, [bar(104.0, 106.0, 103.5, 104.2)])
    assert EventType.LADDER_BREACH_CONFIRMED in types_of(events)


def test_events_carry_level_identity_and_scale():
    an = analyzer()
    events = run(an, [bar(104.0, 105.0, 103.5, 104.2)])
    touch = events[0]
    assert touch.level_source == "center"
    assert touch.level_kind == "major"
    assert touch.level_degree == 0
    assert touch.level_ring == 3
    assert touch.price_scale == 1
    assert touch.instrument == "RELIANCE"
    assert touch.timeframe == "5"


def test_state_round_trips_without_changing_output():
    bars = [
        bar(104.0, 106.0, 103.5, 105.5),
        bar(105.5, 107.0, 105.2, 106.5),
        bar(106.5, 106.8, 105.0, 105.6),
    ]
    straight = run(analyzer(), bars)

    split = analyzer()
    out = list(split.process_bar(bars[0], 0, LEVELS))
    saved = split.get_state()

    resumed = analyzer()
    resumed.restore_state(saved)
    for index in (1, 2):
        out.extend(resumed.process_bar(bars[index], index, LEVELS))

    assert types_of(out) == types_of(straight)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/study_tool/test_gann_ladder_analyzer.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'study_tool.gann_ladder_analyzer'`

- [ ] **Step 3: Write minimal implementation**

Create `study_tool/gann_ladder_analyzer.py`:

```python
"""
Gann Ladder Analyzer - records price/level interactions bar by bar.

Shaped like BreachAnalyzer: built from a config dict, fed one bar at a time,
holding explicit serialisable state so a long walk can be checkpointed.

This module records. It does not predict. The held/failed classification it
applies is a DEFAULT sitting on top of raw measurements that are all retained,
so Phase 3 can recompute the outcome under any other threshold.
"""

from typing import Any, Dict, List, Optional

from study_tool.event_logger import Event, EventType


class GannLadderAnalyzer:
    """Turns bars plus a level ladder into a stream of interaction events."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.breach_mode = config.get("breach_mode", "close")
        self.confirmation_closes = config.get("confirmation_closes", 2)
        self.touch_tolerance = config.get("touch_tolerance_sublevels", 0.1)
        self.resolution_window = config.get("resolution_window_bars", 50)
        self.retest_window = config.get("retest_window_bars", 50)
        self.instrument = config.get("instrument")
        self.timeframe = config.get("timeframe")
        self.price_scale = config.get("price_scale", 1)

        # level_price -> pending cross state
        self.pending: Dict[float, Dict[str, Any]] = {}
        # breach_id -> open breach state
        self.open_breaches: Dict[str, Dict[str, Any]] = {}

    # -- helpers ---------------------------------------------------------

    def _sub_gap(self, level: Dict) -> float:
        """Price distance between adjacent sub-levels of a level's segment."""
        start = level.get("segment_start")
        end = level.get("segment_end")
        if start is None or end is None or end == start:
            return 1.0
        return abs(end - start) / 8.0

    def _make_event(self, event_type, bar, bar_index, level,
                    direction=None, details=None, breach_id=None,
                    parent_breach_id=None) -> Event:
        return Event(
            timestamp=bar.get("timestamp", bar_index),
            event_type=event_type,
            price=bar.get("close"),
            direction=direction,
            details=details or {},
            bar_index=bar_index,
            open_price=bar.get("open"),
            high_price=bar.get("high"),
            low_price=bar.get("low"),
            close_price=bar.get("close"),
            instrument=self.instrument,
            timeframe=self.timeframe,
            level_source=level.get("source"),
            level_price=level.get("price"),
            level_square=level.get("square"),
            level_kind=level.get("kind"),
            level_degree=level.get("degree"),
            level_ring=level.get("ring"),
            level_sub_index=level.get("sub_index"),
            level_is_halfway=level.get("is_halfway"),
            level_segment_start=level.get("segment_start"),
            level_segment_end=level.get("segment_end"),
            price_scale=self.price_scale,
            breach_id=breach_id,
            parent_breach_id=parent_breach_id,
        )

    def _breach_id(self, level: Dict, bar_index: int) -> str:
        return ":".join(str(part) for part in (
            self.instrument, self.timeframe, self.price_scale,
            level.get("source"), level.get("square"), bar_index,
        ))

    # -- main loop -------------------------------------------------------

    def process_bar(self, bar: Dict, bar_index: int,
                    levels: List[Dict]) -> List[Event]:
        """
        Feed one bar. Returns the events it produced.

        Pure with respect to its inputs: the same bar plus the same state in
        gives the same events out.
        """
        events: List[Event] = []
        high, low, close = bar["high"], bar["low"], bar["close"]

        for level in levels:
            price = level["price"]
            gap = self._sub_gap(level)
            tolerance = gap * self.touch_tolerance

            reached = (low - tolerance) <= price <= (high + tolerance)
            beyond_up = close > price
            beyond_down = close < price

            state = self.pending.get(price)

            if state is None:
                if not reached:
                    continue
                # Wick mode confirms as soon as the range clears the level.
                crossed = high > price or low < price
                if self.breach_mode == "wick" and crossed:
                    direction = "up" if high > price else "down"
                    if self.confirmation_closes <= 1:
                        events.append(self._confirm(bar, bar_index, level, direction))
                        continue
                if (self.breach_mode == "close" and (beyond_up or beyond_down)):
                    direction = "up" if beyond_up else "down"
                    self.pending[price] = {
                        "direction": direction,
                        "closes": 1,
                        "first_bar": bar_index,
                    }
                    events.append(self._make_event(
                        EventType.LADDER_CROSS, bar, bar_index, level,
                        direction=direction,
                    ))
                    if self.confirmation_closes <= 1:
                        events.append(self._confirm(bar, bar_index, level, direction))
                        self.pending.pop(price, None)
                else:
                    events.append(self._make_event(
                        EventType.LADDER_TOUCH, bar, bar_index, level,
                    ))
                continue

            # A cross is pending on this level.
            direction = state["direction"]
            still_beyond = beyond_up if direction == "up" else beyond_down
            if still_beyond:
                state["closes"] += 1
                if state["closes"] >= self.confirmation_closes:
                    events.append(self._confirm(bar, bar_index, level, direction))
                    self.pending.pop(price, None)
            else:
                events.append(self._make_event(
                    EventType.LADDER_BREACH_REJECTED, bar, bar_index, level,
                    direction=direction,
                ))
                events.append(self._make_event(
                    EventType.LADDER_BREACH_RESOLVED, bar, bar_index, level,
                    direction=direction,
                    details={"outcome": "NEVER_CONFIRMED", "truncated": False},
                ))
                self.pending.pop(price, None)

        events.extend(self._track_open_breaches(bar, bar_index))
        return events

    def _confirm(self, bar, bar_index, level, direction) -> Event:
        breach_id = self._breach_id(level, bar_index)
        self.open_breaches[breach_id] = {
            "level": level,
            "direction": direction,
            "bar": bar_index,
            "extreme": bar["high"] if direction == "up" else bar["low"],
            "retested": False,
            "closes_back": 0,
        }
        return self._make_event(
            EventType.LADDER_BREACH_CONFIRMED, bar, bar_index, level,
            direction=direction, breach_id=breach_id,
        )

    def _track_open_breaches(self, bar: Dict, bar_index: int) -> List[Event]:
        """Watch for retests and assign terminal outcomes."""
        events: List[Event] = []
        high, low, close = bar["high"], bar["low"], bar["close"]

        for breach_id in list(self.open_breaches):
            state = self.open_breaches[breach_id]
            if bar_index <= state["bar"]:
                continue

            level = state["level"]
            price = level["price"]
            direction = state["direction"]
            gap = self._sub_gap(level)
            elapsed = bar_index - state["bar"]

            if direction == "up":
                state["extreme"] = max(state["extreme"], high)
                came_back = low <= price + gap
                depth = (price - low) / gap
                crossed_back = close < price
            else:
                state["extreme"] = min(state["extreme"], low)
                came_back = high >= price - gap
                depth = (high - price) / gap
                crossed_back = close > price

            if came_back and not state["retested"]:
                state["retested"] = True
                state["retest_bar"] = bar_index
                if crossed_back:
                    state["closes_back"] += 1
                events.append(self._make_event(
                    EventType.LADDER_RETEST, bar, bar_index, level,
                    direction=direction,
                    parent_breach_id=breach_id,
                    details={
                        "bars_since_breach": elapsed,
                        "retest_extreme": low if direction == "up" else high,
                        "depth_in_sublevels": round(depth, 4),
                        "crossed_back": crossed_back,
                        "closes_beyond": state["closes_back"],
                    },
                ))
            elif state["retested"] and crossed_back:
                state["closes_back"] += 1

            if elapsed >= self.resolution_window:
                events.append(self._resolve(bar, bar_index, breach_id))

        return events

    def _resolve(self, bar, bar_index, breach_id) -> Event:
        state = self.open_breaches.pop(breach_id)
        level = state["level"]

        if not state["retested"]:
            outcome = "NEVER_RETESTED"
        elif state["closes_back"] >= 2:
            outcome = "RETEST_FAILED"
        else:
            outcome = "RETEST_HELD"

        return self._make_event(
            EventType.LADDER_BREACH_RESOLVED, bar, bar_index, level,
            direction=state["direction"],
            parent_breach_id=breach_id,
            details={
                "outcome": outcome,
                "truncated": False,
                "retested": state["retested"],
                "closes_back": state["closes_back"],
            },
        )

    def finalize(self) -> List[Event]:
        """
        Close out breaches still open at the end of the data.

        Emitted with outcome None rather than dropped: truncation is a fact
        about the dataset, not a reason to discard a sample.
        """
        events: List[Event] = []
        for breach_id in list(self.open_breaches):
            state = self.open_breaches.pop(breach_id)
            level = state["level"]
            events.append(Event(
                timestamp=0,
                event_type=EventType.LADDER_BREACH_RESOLVED,
                direction=state["direction"],
                bar_index=state["bar"],
                instrument=self.instrument,
                timeframe=self.timeframe,
                level_source=level.get("source"),
                level_price=level.get("price"),
                level_square=level.get("square"),
                level_kind=level.get("kind"),
                level_degree=level.get("degree"),
                level_ring=level.get("ring"),
                price_scale=self.price_scale,
                parent_breach_id=breach_id,
                details={
                    "outcome": None,
                    "truncated": True,
                    "retested": state["retested"],
                },
            ))
        return events

    # -- checkpointing ---------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        return {
            "pending": {str(k): v for k, v in self.pending.items()},
            "open_breaches": self.open_breaches,
        }

    def restore_state(self, state: Dict[str, Any]) -> None:
        self.pending = {float(k): v for k, v in state.get("pending", {}).items()}
        self.open_breaches = state.get("open_breaches", {})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/study_tool/test_gann_ladder_analyzer.py -q`
Expected: PASS, 13 tests

- [ ] **Step 5: Run the whole study_tool suite for regressions**

Run: `python -m pytest tests/study_tool/ -q`
Expected: PASS — the 4 pre-existing tests, Task 1–4's 40, and these 13

- [ ] **Step 6: Commit**

```bash
git add study_tool/gann_ladder_analyzer.py tests/study_tool/test_gann_ladder_analyzer.py
git commit -m "feat: add the Gann ladder analyzer with breach-retest linkage"
```

---

## Task 7: End-to-end walk on real Reliance bars

**Files:**
- Create: `study_tool/run_ladder_study.py`

Wires the pieces together and proves they work on real data rather than synthetic bars. Rebuilds the Sun and Moon ladders when a body's rounded degree changes — the Moon moves about a degree every 1.8 hours, so on 1-minute bars its levels shift several times a session, and computing them once per run would be silently wrong.

Bars are passed in, not fetched. Fetching and caching are deliberately out of scope for this phase.

- [ ] **Step 1: Write the runner**

Create `study_tool/run_ladder_study.py`:

```python
"""
Run a Gann ladder study over a list of bars.

Bars are supplied by the caller - fetching and caching are out of scope for
this phase. Each bar is a dict with open, high, low, close and an epoch
`timestamp` in seconds.

Usage:
    from study_tool.run_ladder_study import run_study
    events = run_study(bars, instrument="RELIANCE", timeframe="5",
                       price_scale=1, sun_degrees=[...], moon_degrees=[...])
"""

import math
from typing import Any, Dict, List, Optional, Sequence

from study_tool.event_logger import Event, EventLogger
from study_tool.gann_ladder import build_gann_square, build_ladder
from study_tool.gann_ladder_analyzer import GannLadderAnalyzer

# Bodies whose ladders move as the walk advances.
MOVING_BODIES = ("sun", "moon")


def degree_to_square(degree: float, zero_offset: int = 1) -> int:
    """
    Map an ecliptic longitude to a grid square.

    zero_offset 1 places 0 degrees on square 361 = 19^2, which lies on the
    odd-square diagonal - the project's default zero-degree line.
    """
    wrapped = int(round(degree)) % 360
    base = 360 if wrapped == 0 else wrapped
    shifted = base + zero_offset
    return shifted + 360 if shifted < 1 else shifted


def build_all_ladders(price: float, price_scale: int,
                      sun_square: Optional[int],
                      moon_square: Optional[int],
                      count: int = 8) -> List[Dict]:
    """Build the centre, Sun and Moon ladders for one price."""
    target = int(round(price * price_scale))
    levels: List[Dict] = []

    centre_grid = build_gann_square(target, 1)
    if centre_grid["too_large"] or not centre_grid["target_found"]:
        return levels

    levels.extend(build_ladder(
        grid=centre_grid,
        cross_centre=centre_grid["body_position"],
        source="center",
        scale=price_scale,
        count=count,
    ))

    for source, square in (("sun", sun_square), ("moon", moon_square)):
        if square is None:
            continue
        grid = build_gann_square(target, square)
        if grid["too_large"] or not grid["target_found"] or not grid["body_found"]:
            continue
        levels.extend(build_ladder(
            grid=grid,
            cross_centre=grid["body_position"],
            source=source,
            scale=price_scale,
            count=count,
        ))

    return levels


def run_study(
    bars: Sequence[Dict],
    instrument: str,
    timeframe: str,
    price_scale: int,
    sun_degrees: Sequence[float],
    moon_degrees: Sequence[float],
    config: Optional[Dict[str, Any]] = None,
) -> List[Event]:
    """
    Walk the bars, producing ladder interaction events.

    sun_degrees and moon_degrees are per-bar ecliptic longitudes, the same
    length as bars. Ladders are rebuilt only when a body's rounded square
    changes or the price moves to a different grid square - rebuilding every
    bar is wasteful, rebuilding once per run is wrong.
    """
    if not (len(bars) == len(sun_degrees) == len(moon_degrees)):
        raise ValueError(
            "bars, sun_degrees and moon_degrees must be the same length; got "
            f"{len(bars)}, {len(sun_degrees)}, {len(moon_degrees)}"
        )

    settings: Dict[str, Any] = {
        "breach_mode": "close",
        "confirmation_closes": 2,
        "touch_tolerance_sublevels": 0.1,
        "resolution_window_bars": 50,
        "retest_window_bars": 50,
        "instrument": instrument,
        "timeframe": timeframe,
        "price_scale": price_scale,
    }
    if config:
        settings.update(config)

    analyzer = GannLadderAnalyzer(settings)
    events: List[Event] = []

    cached_key = None
    levels: List[Dict] = []

    for index, bar in enumerate(bars):
        sun_square = degree_to_square(sun_degrees[index])
        moon_square = degree_to_square(moon_degrees[index])
        target = int(round(bar["close"] * price_scale))
        key = (target, sun_square, moon_square)

        if key != cached_key:
            levels = build_all_ladders(
                bar["close"], price_scale, sun_square, moon_square
            )
            cached_key = key

        events.extend(analyzer.process_bar(bar, index, levels))

    events.extend(analyzer.finalize())
    return events


def summarise(events: Sequence[Event]) -> Dict[str, int]:
    """Count events by type - a quick sanity check on a walk."""
    counts: Dict[str, int] = {}
    for event in events:
        name = event.event_type.value
        counts[name] = counts.get(name, 0) + 1
    return counts
```

- [ ] **Step 2: Verify it imports and the degree mapping is right**

Run:
```bash
python -c "
from study_tool.run_ladder_study import degree_to_square, build_all_ladders
print('0 deg ->', degree_to_square(0))
print('360 deg ->', degree_to_square(360))
print('154.15 deg ->', degree_to_square(154.15))
levels = build_all_ladders(1287.5, 1, degree_to_square(154.15), degree_to_square(200.0))
print('levels built:', len(levels))
print('sources:', sorted({l['source'] for l in levels}))
"
```
Expected:
```
0 deg -> 361
360 deg -> 361
154.15 deg -> 155
levels built: <a number above 0>
sources: ['center', 'moon', 'sun']
```

`361 = 19^2` sits on the odd-square diagonal, which is the project's chosen zero-degree line. `154.15` rounds to 154, plus the offset of 1, gives 155 — matching the Sun square used when these levels were checked against a chart.

- [ ] **Step 3: Run a real walk on Reliance**

This uses the Dhan credentials already in `gann-visualizer/backend/.env`. If the token has expired the request returns HTTP 401 with error code `DH-901` — refresh it and retry, do not work around it.

Run:
```bash
python -c "
import re, json, urllib.request, datetime, sys
sys.path.insert(0, '.')
from zoneinfo import ZoneInfo
from study_tool.run_ladder_study import run_study, summarise

txt = open('.env').read()
tok = re.search(r'DHAN_ACCESS_TOKEN\s*=\s*\"?([^\"\s]+)', txt).group(1)
cid = re.search(r'DHAN_CLIENT_ID\s*=\s*\"?([^\"\s]+)', txt).group(1)
body = json.dumps({'securityId':'2885','exchangeSegment':'NSE_EQ','instrument':'EQUITY','interval':'5','fromDate':'2026-08-27 09:00:00','toDate':'2026-08-27 16:30:00'}).encode()
req = urllib.request.Request('https://api.dhan.co/v2/charts/intraday', data=body,
    headers={'access-token':tok,'client-id':cid,'Content-Type':'application/json','Accept':'application/json'})
d = json.loads(urllib.request.urlopen(req, timeout=30).read())
bars = [{'open':o,'high':h,'low':l,'close':c,'timestamp':t}
        for o,h,l,c,t in zip(d['open'],d['high'],d['low'],d['close'],d['timestamp'])]
print('bars:', len(bars))

sys.path.insert(0, 'C:/Dev/GannSq9/backend')
from app.utils.ephemeris import calculate_sun_position, calculate_moon_position
UTC = ZoneInfo('UTC')
suns, moons = [], []
for b in bars:
    when = datetime.datetime.fromtimestamp(b['timestamp'], UTC)
    suns.append(calculate_sun_position(when)['angle'])
    moons.append(calculate_moon_position(when)['angle'])
print('sun range: %.3f .. %.3f' % (min(suns), max(suns)))
print('moon range: %.3f .. %.3f' % (min(moons), max(moons)))

events = run_study(bars, 'RELIANCE', '5', 1, suns, moons)
print('events:', len(events))
for k, v in sorted(summarise(events).items()):
    print(' ', k, v)
"
```

Expected: a bar count of 72, a Moon range spanning roughly 3 degrees across the session (it moves ~13°/day), a non-zero event count, and a breakdown including `LADDER_TOUCH` and at least one `LADDER_BREACH_CONFIRMED`.

If the event count is zero, something is wrong — Reliance moved about ₹20 that day across levels spaced ₹2.75 apart, so interactions must exist. Report it rather than accepting it.

- [ ] **Step 4: Commit**

```bash
git add study_tool/run_ladder_study.py
git commit -m "feat: wire the ladder study runner over real bars"
```

---

## Self-review notes

Checked against the spec:

- Ladder port with JS-derived expectations — Tasks 1–4, including the explicit cross-check in Task 4 Step 5.
- Event types and level identity fields — Task 5.
- Breach linkage via `breach_id` / `parent_breach_id` — Task 5 fields, Task 6 behaviour and tests.
- Raw retest measurement, classification applied on top — Task 6 `_track_open_breaches` and `_resolve`.
- Four-outcome classification including truncation — Task 6, `finalize`.
- Ladder rebuild when a body's degree changes — Task 7 `run_study` cache key.
- Both resolutions loggable — `price_scale` is a parameter throughout; Task 7 accepts it.
- `get_state` / `restore_state` — Task 6.

Deliberately not covered, per the spec's out-of-scope section: bar fetching and caching, prediction or scoring, Phase 3 feature work, US market data, bodies beyond Sun and Moon.

---

## Out of scope

- Fetching and caching bars. Note for long runs: Dhan tokens expire every 24 hours and the data API is capped at 100,000 requests/day.
- Prediction, scoring, ranking or position sizing.
- Feature engineering and models — Phase 3.
- US market data. Dhan's Global Stocks API exposes orders and a live feed only, no historical bars.
- Bodies beyond Sun and Moon. `level_source` is a free string, so adding one later needs no schema change.
