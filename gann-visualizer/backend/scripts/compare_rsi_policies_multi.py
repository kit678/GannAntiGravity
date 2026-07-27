"""Compare RSI anchor policies across every available run.

A single 961-bar window with n~30 cannot separate these policies -- that is the
whole reason this script exists. It pools results across every symbol,
timeframe and run that has candles, so the adjacency-vs-walk-back question is
answered on more than one sample.

Usage:
    python gann-visualizer/backend/scripts/compare_rsi_policies_multi.py
"""

from __future__ import annotations

import glob
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd

from analysis.rsi_trendline_hypothesis import RSITrendlineBreakHypothesis

POLICIES = ("collinear_extend", "walk_back")
MIN_BARS = 300
REQUIRED = {"open", "high", "low", "close"}


def evaluate(candles: pd.DataFrame, policy: str) -> dict | None:
    hypothesis = RSITrendlineBreakHypothesis()
    hypothesis.set_parameters(**{**hypothesis.parameters, "anchor_policy": policy})
    try:
        return hypothesis.evaluate(pd.DataFrame(), candles_df=candles)
    except Exception:
        return None


def main() -> None:
    pattern = os.path.join("logs", "backend", "runs", "*", "*", "*", "candles.csv")
    files = sorted(glob.glob(pattern))

    header = f"{'run':<34}{'tf':>4}"
    for policy in POLICIES:
        header += f"{policy + ' n':>12}{'win':>8}{'net':>11}"
    print(header)
    print("-" * len(header))

    totals = {policy: {"n": 0, "wins": 0, "net": 0.0, "runs": 0} for policy in POLICIES}

    for path in files:
        parts = path.replace(os.sep, "/").split("/")
        symbol, timeframe, run_id = parts[3], parts[4], parts[5]

        try:
            candles = pd.read_csv(path).reset_index(drop=True)
        except Exception:
            continue
        if len(candles) < MIN_BARS or not REQUIRED <= set(candles.columns):
            continue
        candles["bar_index"] = candles.index

        row = f"{(symbol + '/' + run_id)[:34]:<34}{timeframe:>4}"
        for policy in POLICIES:
            result = evaluate(candles, policy)
            if result is None:
                row += f"{'err':>12}{'':>8}{'':>11}"
                continue
            n = result["sample_size"]
            win = result["win_rate"]
            net = result["net_pnl_total"]
            row += f"{n:>12}{win:>8.3f}{net:>11.1f}"
            totals[policy]["n"] += n
            totals[policy]["wins"] += round(win * n)
            totals[policy]["net"] += net
            totals[policy]["runs"] += 1
        print(row)

    print("-" * len(header))
    for policy in POLICIES:
        t = totals[policy]
        rate = t["wins"] / t["n"] if t["n"] else 0.0
        print(
            f"{policy:<14} POOLED over {t['runs']:>2} runs   "
            f"n={t['n']:>4}  wins={t['wins']:>4}  win_rate={rate:.4f}  net={t['net']:.1f}"
        )

    print()
    print("Pooling is not walk-forward: these are in-sample results per run, using")
    print("one fixed parameter set. It answers 'is one policy consistently better',")
    print("not 'does this strategy work out of sample'.")


if __name__ == "__main__":
    main()
