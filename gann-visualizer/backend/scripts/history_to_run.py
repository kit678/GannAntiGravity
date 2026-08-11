"""Turn a history-corpus file into a run directory the Navigator can open.

The Hypothesis Navigator reads `logs/backend/runs/<SYMBOL>/<RESOLUTION>/<run_id>/`
and expects `candles.csv` plus `analysis/hypotheses/*.json`. The history corpus
has price only, so this writes the directory and generates the RSI report into it.

An empty `events.csv` is written because `HypothesisRunner.run_all` returns
early without one. The Gann hypotheses simply score nothing, which is correct --
this run has no Gann event stream.

Usage:
    python gann-visualizer/backend/scripts/history_to_run.py BTCUSDT 4h
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd

from analysis.rsi_trendline_hypothesis import RSITrendlineBreakHypothesis

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
HISTORY_ROOT = os.path.join(REPO_ROOT, "logs", "backend", "history")
RUNS_ROOT = os.path.join(REPO_ROOT, "logs", "backend", "runs")

# The Navigator's run paths are keyed by resolution in minutes.
RESOLUTION_MINUTES = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "4h": "240", "6h": "360", "12h": "720", "1d": "1440",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol")
    parser.add_argument("interval")
    parser.add_argument("--run-id")
    parser.add_argument("--bars", type=int, default=0,
                        help="use only the last N bars (0 = all)")
    args = parser.parse_args()

    source = os.path.join(HISTORY_ROOT, args.symbol, args.interval, "candles.csv")
    if not os.path.exists(source):
        raise SystemExit(f"no history at {source}")

    candles = pd.read_csv(source)
    if args.bars:
        candles = candles.tail(args.bars).reset_index(drop=True)
        candles["bar_index"] = candles.index

    # The hypothesis wants pd.Timestamp in `time` so its own _time_string()
    # can format pivot/entry times for the report. Every OTHER consumer of
    # candles.csv -- notably GET /api/hypothesis-runs/.../candles, which the
    # Navigator's chart calls to load a run's price data -- expects `time` to
    # be the same raw epoch seconds as `timestamp`, matching every other run
    # in the repo. Writing a formatted string there 500s that endpoint
    # (`int("2026-01-23 04:00:00")`) and the failure surfaces in the browser
    # as an opaque CORS error, not the ValueError it actually is.
    candles_for_report = candles.copy()
    candles_for_report["time"] = pd.to_datetime(candles["timestamp"], unit="s")

    resolution = RESOLUTION_MINUTES.get(args.interval, args.interval)
    run_id = args.run_id or f"hist_{args.interval}"
    run_dir = os.path.join(RUNS_ROOT, args.symbol, resolution, run_id)
    output_dir = os.path.join(run_dir, "analysis", "hypotheses")
    os.makedirs(output_dir, exist_ok=True)

    candles_for_disk = candles.copy()
    candles_for_disk["time"] = candles_for_disk["timestamp"]
    candles_for_disk.to_csv(os.path.join(run_dir, "candles.csv"), index=False)
    with open(os.path.join(run_dir, "events.csv"), "w", encoding="utf-8") as handle:
        handle.write("Type,Time,Price,Bar_Index,Raw_Timestamp\n")

    hypothesis = RSITrendlineBreakHypothesis()
    result = hypothesis.evaluate(pd.DataFrame(), candles_df=candles_for_report)

    report = {
        "hypothesis_name": hypothesis.name,
        "description": hypothesis.description,
        "parameters": hypothesis.parameters,
        "trade_scored": True,
        "in_sample": {
            key: result.get(key)
            for key in (
                "sample_size", "win_rate", "live_sample_size", "live_win_rate",
                "retro_sample_size", "retro_win_rate", "avg_mfe_10", "avg_mae_10",
                "composite", "net_pnl_total", "avg_net_pnl", "expectancy_r",
                "total_r", "profit_factor", "avg_win_r", "avg_loss_r",
            )
        },
        "walk_forward": {},
        "groups": {},
        "detailed_log": result["detailed_log"],
        "rsi_series": result["rsi_series"],
        "line_timeline": result["line_timeline"],
        "skipped": result["skipped"],
        "exit_optimization": {
            key: value for key, value in result["exit_optimization"].items()
            if key != "per_signal"
        },
    }

    path = os.path.join(output_dir, "rsi_trendline_break_strategy.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, default=str)

    print(f"{len(candles)} bars -> {run_dir}")
    print(f"  trades   {result['sample_size']}")
    print(f"  win rate {result['win_rate']:.3f}")
    print(f"  exp      {result['expectancy_r']:+.3f} R")
    print(f"  PF       {result['profit_factor']:.2f}")
    print(f"  segments {len(result['line_timeline'])}")
    print(f"  report   {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
