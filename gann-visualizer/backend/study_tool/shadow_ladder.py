"""
Shadow ladders - the control the whole corpus is measured against.

Take the real ladder and add a constant to every price. The number of levels,
the spacing between them (including the uneven spacing of off-centre crosses),
their ordering and the relationship between the three crosses all survive. The
only thing destroyed is whether the levels sit at Gann prices, which is exactly
the question: is it these prices, or would any grid of this shape look the same?

A shadow is arithmetic on an already-built ladder. It must never call
build_all_ladders. Grid construction costs 27 ms at scale 10 and dominates the
corpus build; rebuilding per shadow turns a 3-hour job into a 67-hour one.
"""

import random
from typing import Dict, List

# Squares and segment bounds live in grid units; price is square / scale. A
# shift has to move all of them together or price == square / scale breaks.
_SQUARE_FIELDS = ("square", "segment_start", "segment_end")


def shift_ladder(levels: List[Dict], delta: float, scale: float) -> List[Dict]:
    """
    Return a copy of `levels` with every price moved by `delta`.

    Args:
        levels: output of build_all_ladders
        delta: price offset to add
        scale: the price scale those levels were built at (1 or 10)

    The input list is not mutated - the real ladder is reused for every shadow
    and for the real run itself.
    """
    square_delta = delta * scale
    shifted = []
    for level in levels:
        copy = dict(level)
        copy["price"] = level["price"] + delta
        for field in _SQUARE_FIELDS:
            if copy.get(field) is not None:
                copy[field] = level[field] + square_delta
        shifted.append(copy)
    return shifted


def shadow_offsets(count: int, gap: float, seed: int) -> List[float]:
    """
    `count` offsets, each between 0.1 and 0.9 of one sub-level gap.

    The bounds matter. An offset near 0, or near a whole gap, lands the shadow
    back on top of the real levels and weakens the contrast the control exists
    to provide.

    Seeded so a corpus build is reproducible.
    """
    rng = random.Random(seed)
    return [rng.uniform(0.1 * gap, 0.9 * gap) for _ in range(count)]
