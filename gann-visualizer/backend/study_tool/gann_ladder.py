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
        target_found, body_found, too_large, dimension
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
