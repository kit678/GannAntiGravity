"""A/B the walk-back anchor policy against the nearest-pair rival.

Identical candles, identical trade rules -- only the anchor policy differs.
Reports geometry quality alongside trade outcome, because a policy that trades
better while drawing nonsense is not the goal.

Usage:
    python gann-visualizer/backend/scripts/compare_rsi_policies.py <candles.csv>
"""

from __future__ import annotations

import os
import statistics
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd

from analysis.rsi_line_policy import NearestPairAnchorPolicy, WalkBackAnchorPolicy
from analysis.rsi_pivots import compute_rsi_series
from analysis.rsi_pivots import GeometryParams
from analysis.rsi_sweep import run_causal_sweep
from analysis.rsi_trendline_hypothesis import RSITrendlineBreakHypothesis

PARAMS = GeometryParams(
    left_bars=3, right_bars=3, min_swing=8.0,
    tolerance=1.5, min_length=8, max_span_bars=150,
)


def geometry_report(rsi: pd.Series, policy) -> dict:
    result = run_causal_sweep(rsi, policy, PARAMS)
    poked = 0
    for segment in result.segments:
        same_kind = [p for p in result.pivots if p.kind == segment.anchor_b.kind]
        for pivot in same_kind:
            if not (segment.line.start_bar_index < pivot.bar_index < segment.line.end_bar_index):
                continue
            value = segment.line.value_at(pivot.bar_index)
            if segment.line.direction == "down" and pivot.rsi_value > value + PARAMS.tolerance:
                poked += 1
                break
            if segment.line.direction == "up" and pivot.rsi_value < value - PARAMS.tolerance:
                poked += 1
                break
    spans = [s.line.end_bar_index - s.line.start_bar_index for s in result.segments] or [0]
    return {
        "pivots": len(result.pivots),
        "segments": len(result.segments),
        "poked": poked,
        "poked_pct": round(100.0 * poked / len(result.segments), 1) if result.segments else 0.0,
        "median_span": statistics.median(spans),
        "max_span": max(spans),
        "raw_breaks": len(result.signals),
    }


def trade_report(candles: pd.DataFrame, policy_name: str) -> dict:
    hypothesis = RSITrendlineBreakHypothesis()
    hypothesis.set_parameters(**{**hypothesis.parameters, "anchor_policy": policy_name})
    result = hypothesis.evaluate(pd.DataFrame(), candles_df=candles)
    best = (result.get("exit_optimization") or {}).get("best") or {}
    return {
        "n": result["sample_size"],
        "win_rate": result["win_rate"],
        "best_r": best.get("r_value"),
        "net_pnl": result["net_pnl_total"],
        "skipped": result["skipped"],
    }


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)

    path = sys.argv[1]
    candles = pd.read_csv(path).reset_index(drop=True)
    candles["bar_index"] = candles.index
    rsi = compute_rsi_series(candles["close"], period=14)

    print(f"candles: {path}  ({len(candles)} bars)\n")
    header = f"{'policy':<14}{'pivots':>7}{'segs':>6}{'poked':>7}{'poked%':>8}{'medSpan':>9}{'maxSpan':>9}"
    print("GEOMETRY"); print(header)
    for name, policy in (("walk_back", WalkBackAnchorPolicy()), ("nearest_pair", NearestPairAnchorPolicy())):
        g = geometry_report(rsi, policy)
        print(f"{name:<14}{g['pivots']:>7}{g['segments']:>6}{g['poked']:>7}"
              f"{g['poked_pct']:>8}{g['median_span']:>9}{g['max_span']:>9}")

    print("\nTRADES")
    print(f"{'policy':<14}{'n':>5}{'win':>8}{'bestR':>7}{'netPnL':>12}")
    for name in ("walk_back", "nearest_pair"):
        t = trade_report(candles, name)
        print(f"{name:<14}{t['n']:>5}{t['win_rate']:>8.3f}"
              f"{str(t['best_r']):>7}{t['net_pnl']:>12.1f}")
        print(f"{'':<14}skipped: {t['skipped']}")


if __name__ == "__main__":
    main()
