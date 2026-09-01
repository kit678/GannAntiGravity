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
