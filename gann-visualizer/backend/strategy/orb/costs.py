"""
Slippage as a stress axis, not an assumption.

Optimising slippage is meaningless — the best value is always zero. Instead the
strategy is run across a range of slippage levels and the report leads with the
level at which the edge dies.
"""

from typing import Dict, List

# Index points per side.
SLIPPAGE_SWEEP: List[float] = [0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0]

BASE_SLIPPAGE = 1.0
STRESSED_SLIPPAGE = 2.0

BASE_FEE_RATE = 0.0003
STRESSED_FEE_RATE = 0.0006


def breakeven_slippage(pnl_by_slippage: Dict[float, float]) -> float:
    """Slippage level, in index points per side, where average net P&L hits zero.

    Args:
        pnl_by_slippage: average net P&L per trade at each tested slippage level.

    Returns:
        The linearly interpolated crossing point. If P&L is already non-positive
        at the lowest tested level, returns that level (not a negative
        extrapolation) — the strategy loses money even at the best fills tested.
        If P&L is still
        positive at the highest tested level, returns that level, which should be
        read as a floor ("survives at least this much"), not a measurement.
    """
    if not pnl_by_slippage:
        raise ValueError("need at least one slippage level")

    levels = sorted(pnl_by_slippage)

    if pnl_by_slippage[levels[0]] <= 0:
        return float(levels[0])

    for lower, upper in zip(levels, levels[1:]):
        pnl_lower = pnl_by_slippage[lower]
        pnl_upper = pnl_by_slippage[upper]
        if pnl_upper > 0:
            continue
        if pnl_lower == pnl_upper:
            return float(upper)
        fraction = pnl_lower / (pnl_lower - pnl_upper)
        return float(lower + fraction * (upper - lower))

    return float(levels[-1])
