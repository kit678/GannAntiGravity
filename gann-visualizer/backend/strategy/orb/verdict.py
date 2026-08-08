"""
The pre-registered verdict rule, as a pure function.

Frozen before the first run. Changing any threshold here after seeing results
invalidates the test.
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

MIN_TRADES = 30
MIN_PLACEBO_PERCENTILE = 95.0

PASS = "PASS"
FRAGILE = "FRAGILE"
FAIL = "FAIL"
INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class CellResult:
    """One point in the robustness grid, already simulated."""

    label: str
    is_headline: bool
    n_trades_test: int
    avg_net_pnl_test_base: float
    avg_net_pnl_test_stressed: float
    avg_net_pnl_train_base: float


def decide_verdict(
    cells: Sequence[CellResult],
    placebo_percentile: Optional[float],
    data_source: str,
    min_trades: int = MIN_TRADES,
) -> Tuple[str, List[str]]:
    """Return (verdict, reasons). Reasons are empty only on a clean PASS."""
    reasons: List[str] = []

    if data_source.lower() == "yfinance":
        return INCONCLUSIVE, [
            "data source is yfinance, which caps intraday history at ~60 days "
            "(~40 sessions) — far too few sessions to conclude anything"
        ]

    headline = next((cell for cell in cells if cell.is_headline), None)
    if headline is None:
        return INCONCLUSIVE, ["no headline cell in the robustness grid"]

    if placebo_percentile is None:
        return INCONCLUSIVE, ["placebo test did not run"]

    if headline.n_trades_test < min_trades:
        return INCONCLUSIVE, [
            f"only {headline.n_trades_test} second-half trades, need {min_trades}"
        ]

    non_finite = [
        name
        for name, value in (
            ("avg_net_pnl_test_base", headline.avg_net_pnl_test_base),
            ("avg_net_pnl_test_stressed", headline.avg_net_pnl_test_stressed),
            ("avg_net_pnl_train_base", headline.avg_net_pnl_train_base),
        )
        if not math.isfinite(value)
    ]
    if not math.isfinite(placebo_percentile):
        non_finite.append("placebo_percentile")
    if non_finite:
        return FAIL, [
            f"non-finite value(s) in headline result: {', '.join(non_finite)} — "
            "treating corrupt/undefined performance data as a failure, not a pass"
        ]

    if headline.avg_net_pnl_test_base <= 0:
        reasons.append(
            f"headline avg net P&L at base costs is {headline.avg_net_pnl_test_base:.4f}"
        )
    if headline.avg_net_pnl_test_stressed <= 0:
        reasons.append(
            f"headline avg net P&L at 2x costs is {headline.avg_net_pnl_test_stressed:.4f}"
        )
    if headline.avg_net_pnl_train_base <= 0:
        reasons.append(
            f"first-half avg net P&L is {headline.avg_net_pnl_train_base:.4f}, "
            "so the halves disagree"
        )
    if placebo_percentile < MIN_PLACEBO_PERCENTILE:
        reasons.append(
            f"placebo percentile {placebo_percentile:.1f} is below "
            f"{MIN_PLACEBO_PERCENTILE:.0f} — random entries do about as well"
        )

    if reasons:
        return FAIL, reasons

    fragile = [
        cell.label
        for cell in cells
        if not cell.is_headline
        and (not math.isfinite(cell.avg_net_pnl_test_base) or cell.avg_net_pnl_test_base <= 0)
    ]
    if fragile:
        return FRAGILE, [
            f"headline passed but neighbour cell {label} is not positive at base costs"
            for label in fragile
        ]

    return PASS, []
