"""Evaluate the RSI trendline break strategy over the multi-year history corpus.

Everything here reports **expectancy in R**, never price-unit PnL: the corpus
pools a 60,000-dollar BTC with a 150-dollar SOL, and summing their price deltas
is meaningless.

Three commands, meant to be run in this order:

    baseline   what the shipped configuration actually does, train and test
    sweep      parameter ranges, scored on TRAIN ONLY
    placebo    does the break moment carry an edge over a time-shifted control
    confirm    evaluate ONE named configuration on TEST -- run this last, once

The train/test cut is a fixed date, not a percentage, so re-running with more
symbols cannot quietly move the boundary. Nothing in `sweep` is allowed to see
test data; that is the whole point of the split.

Usage:
    python gann-visualizer/backend/scripts/fetch_binance_history.py
    python gann-visualizer/backend/scripts/rsi_research.py baseline
    python gann-visualizer/backend/scripts/rsi_research.py sweep --grid trade
    python gann-visualizer/backend/scripts/rsi_research.py placebo
"""

from __future__ import annotations

import argparse
import glob
import itertools
import json
import os
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd

from analysis.rsi_trendline_hypothesis import RSITrendlineBreakHypothesis
from analysis.signal_trade_simulator import simulate_trade_grid

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
HISTORY_ROOT = os.path.join(REPO_ROOT, "logs", "backend", "history")

# Out-of-sample begins here and is not looked at until `confirm`.
TEST_START = pd.Timestamp("2025-01-01")


# --------------------------------------------------------------------- #
# corpus
# --------------------------------------------------------------------- #

def load_corpus(symbols: Optional[List[str]], intervals: Optional[List[str]]):
    loaded = []
    for path in sorted(glob.glob(os.path.join(HISTORY_ROOT, "*", "*", "candles.csv"))):
        parts = path.replace("\\", "/").split("/")
        symbol, interval = parts[-3], parts[-2]
        if symbols and symbol not in symbols:
            continue
        if intervals and interval not in intervals:
            continue
        frame = pd.read_csv(path)
        frame["time"] = pd.to_datetime(frame["timestamp"], unit="s")
        frame = frame.reset_index(drop=True)
        frame["bar_index"] = frame.index
        loaded.append((f"{symbol} {interval}", frame))
    if not loaded:
        raise SystemExit(
            f"no candles under {HISTORY_ROOT} -- run fetch_binance_history.py first"
        )
    return loaded


# --------------------------------------------------------------------- #
# scoring
# --------------------------------------------------------------------- #

def summarise(trades: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """n / win rate / expectancy / profit factor over a list of trades in R."""
    n = len(trades)
    if not n:
        return None
    r_values = [t["net_r"] for t in trades]
    wins = [r for r in r_values if r > 0]
    losses = [-r for r in r_values if r < 0]
    gross_win, gross_loss = sum(wins), sum(losses)
    return {
        "n": n,
        "win_rate": len(wins) / n,
        "expectancy_r": sum(r_values) / n,
        "total_r": sum(r_values),
        "profit_factor": (gross_win / gross_loss) if gross_loss else float("inf"),
        "avg_win_r": (gross_win / len(wins)) if wins else 0.0,
        "avg_loss_r": (gross_loss / len(losses)) if losses else 0.0,
    }


def sequential_only(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop trades that would have opened while another was still running.

    With a 40-bar hold and a signal every few bars, the raw list double-counts
    the same market move many times over. One position at a time is both what
    you would actually trade and what makes the sample closer to independent.
    """
    kept: List[Dict[str, Any]] = []
    free_from = -1
    for trade in sorted(trades, key=lambda t: t["entry_bar"]):
        if trade["entry_bar"] < free_from:
            continue
        kept.append(trade)
        free_from = trade["exit_bar"]
    return kept


def split_by_date(trades: List[Dict[str, Any]]):
    train = [t for t in trades if t["time"] < TEST_START]
    test = [t for t in trades if t["time"] >= TEST_START]
    return train, test


def print_row(label: str, stats: Optional[Dict[str, Any]]) -> None:
    if stats is None:
        print(f"{label:<34} {'-':>6}")
        return
    print(
        "%-34s %6d %8.3f %9.3f %9.2f %8.2f %8.2f"
        % (label, stats["n"], stats["win_rate"], stats["expectancy_r"],
           stats["total_r"], stats["profit_factor"], stats["avg_win_r"])
    )


HEADER = "%-34s %6s %8s %9s %9s %8s %8s" % (
    "", "n", "win", "exp(R)", "totR", "PF", "avgW")


# --------------------------------------------------------------------- #
# running one configuration
# --------------------------------------------------------------------- #

def make_hypothesis(overrides: Dict[str, Any]) -> RSITrendlineBreakHypothesis:
    hypothesis = RSITrendlineBreakHypothesis()
    hypothesis.set_parameters(**{**hypothesis.parameters, **overrides})
    return hypothesis


def trades_for_config(
    corpus, overrides: Dict[str, Any], per_r: bool = False
) -> Dict[float, List[Dict[str, Any]]]:
    """Trades keyed by R value.

    One `evaluate` call yields every R in the grid, so sweeping R is free once
    the geometry has been swept -- which is the expensive part.
    """
    by_r: Dict[float, List[Dict[str, Any]]] = {}
    for label, candles in corpus:
        hypothesis = make_hypothesis(overrides)
        result = hypothesis.evaluate(pd.DataFrame(), candles.copy())
        optimization = result.get("exit_optimization") or {}
        results = optimization.get("all_r_results") or []
        if not per_r:
            selected = optimization.get("best")
            results = [selected] if selected else []
        for r_result in results:
            bucket = by_r.setdefault(r_result["r_value"], [])
            for trade in r_result["per_signal"].values():
                bucket.append({
                    "net_r": trade["net_r"],
                    "entry_bar": trade["entry_bar_index"],
                    "exit_bar": trade["exit_bar_index"],
                    "time": pd.Timestamp(trade["signal_time"]),
                    "market": label,
                })
    return by_r


# --------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------- #

def command_baseline(corpus, args) -> None:
    overrides = parse_overrides(args.set)
    by_r = trades_for_config(corpus, overrides, per_r=False)
    trades = next(iter(by_r.values()), [])

    train, test = split_by_date(trades)
    print(f"shipped configuration{format_overrides(overrides)}")
    print(f"train < {TEST_START.date()} <= test\n")
    print(HEADER)
    print("-" * 88)
    print_row("ALL   every signal", summarise(trades))
    print_row("ALL   one position at a time", summarise(sequential_only(trades)))
    print_row("TRAIN every signal", summarise(train))
    print_row("TEST  every signal", summarise(test))
    print_row("TEST  one position at a time", summarise(sequential_only(test)))
    print()
    print(HEADER)
    print("-" * 88)
    for market in sorted({t["market"] for t in trades}):
        print_row(market, summarise([t for t in trades if t["market"] == market]))


GRIDS: Dict[str, Dict[str, List[Any]]] = {
    # Trade rules. Geometry held at the shipped values, so one sweep of the
    # expensive part covers the whole grid.
    "trade": {
        "swing_lookback": [10, 20, 40],
        "max_hold_bars": [20, 40, 80],
        "entry_offset": [1],
    },
    # Geometry. Ranges rather than one guessed value per knob.
    "geometry": {
        "rsi_period": [8, 14, 21],
        "min_swing": [2.0, 5.0, 8.0],
        "pivot_left_bars": [2, 3],
        "pivot_right_bars": [2, 3],
    },
    "policy": {
        "anchor_policy": ["collinear_extend", "adjacent", "walk_back", "nearest_pair"],
    },
    "cost": {
        # Costs are a stress axis, not something to optimise. Best case is a
        # VIP maker-both-sides fill; worst is taker plus a tick of slippage.
        "fee_rate": [0.0002, 0.0004, 0.0005],
        "slippage_per_side": [0.0, 0.0002],
    },
}


def command_sweep(corpus, args) -> None:
    grid = GRIDS[args.grid]
    base = parse_overrides(args.set)
    keys = sorted(grid)
    combinations = list(itertools.product(*(grid[k] for k in keys)))

    print(f"grid '{args.grid}': {len(combinations)} configurations x "
          f"{len(corpus)} markets, scored on TRAIN ONLY (< {TEST_START.date()})")
    print()
    print("%-66s %6s %8s %9s %8s" % ("config", "n", "win", "exp(R)", "PF"))
    print("-" * 100)

    rows = []
    started = time.time()
    for combination in combinations:
        overrides = {**base, **dict(zip(keys, combination))}
        by_r = trades_for_config(corpus, overrides, per_r=True)
        for r_value, trades in sorted(by_r.items()):
            train, _ = split_by_date(trades)
            train = sequential_only(train) if args.sequential else train
            stats = summarise(train)
            if not stats or stats["n"] < args.min_trades:
                continue
            label = format_overrides({**dict(zip(keys, combination)), "R": r_value})
            rows.append((stats["expectancy_r"], label, stats))

    rows.sort(reverse=True, key=lambda row: row[0])
    for _, label, stats in rows[: args.top]:
        print("%-66s %6d %8.3f %9.3f %8.2f"
              % (label[:66], stats["n"], stats["win_rate"],
                 stats["expectancy_r"], stats["profit_factor"]))
    print()
    print(f"{len(rows)} configurations cleared min-trades={args.min_trades} "
          f"in {time.time() - started:.0f}s")
    if rows:
        print()
        print("best on TRAIN:", rows[0][1])
        print("Run `confirm` with those values to score it on TEST. Once.")


PLACEBO_SHIFTS = (-11, 7, 13, 23, 37)


def command_placebo(corpus, args) -> None:
    """Hold every rule constant and move only the bar the break is read on.

    A strategy whose entries score no better than the same entries taken 13
    bars later has no entry edge, whatever its win rate says.
    """
    overrides = parse_overrides(args.set)
    buckets: Dict[str, List[Dict[str, Any]]] = {}

    for label, candles in corpus:
        hypothesis = make_hypothesis(overrides)
        prepared = hypothesis.prepare(candles.copy())
        breaks = [(int(s.bar_index), s.side) for s in prepared["sweep"].signals]
        if not breaks:
            continue

        variants = {"REAL rsi-break": breaks}
        for shift in PLACEBO_SHIFTS:
            variants["placebo %+d bars" % shift] = [
                (bar + shift, side) for bar, side in breaks
            ]
        variants["placebo flipped side"] = [
            (bar, "SHORT" if side == "LONG" else "LONG") for bar, side in breaks
        ]

        for name, bars_sides in variants.items():
            trades = run_break_list(hypothesis, prepared, bars_sides)
            buckets.setdefault(name, []).extend(trades)

    print(f"placebo gate{format_overrides(overrides)}   "
          f"R={overrides.get('selected_r', 3.0)}")
    print()
    print(HEADER)
    print("-" * 88)
    for name in ["REAL rsi-break"] + [
        "placebo %+d bars" % s for s in PLACEBO_SHIFTS
    ] + ["placebo flipped side"]:
        if name in buckets:
            print_row(name, summarise(buckets[name]))

    real = summarise(buckets.get("REAL rsi-break", []))
    others = [summarise(v) for k, v in buckets.items() if k != "REAL rsi-break"]
    others = [o for o in others if o]
    if real and others:
        best_placebo = max(o["expectancy_r"] for o in others)
        print()
        if real["expectancy_r"] > best_placebo:
            print("PASS - the real break beats every time-shifted control "
                  f"({real['expectancy_r']:+.3f}R vs {best_placebo:+.3f}R)")
        else:
            print("FAIL - a shifted control matches or beats the real break "
                  f"({real['expectancy_r']:+.3f}R vs {best_placebo:+.3f}R). "
                  "The entry moment is not doing work.")


def run_break_list(hypothesis, prepared, bars_sides) -> List[Dict[str, Any]]:
    """Score an arbitrary list of (bar, side) through the shipped entry rule."""
    candles = prepared["candles"]
    signals = []
    for bar_index, side in bars_sides:
        entry, _ = hypothesis.entry_for_break(
            candles=candles,
            row_by_bar=prepared["row_by_bar"],
            bar_index=bar_index,
            side=side,
            last_bar=prepared["last_bar"],
        )
        if entry is not None:
            signals.append(entry)
    if not signals:
        return []

    parameters = hypothesis.parameters
    optimization = simulate_trade_grid(
        candles=candles,
        signals=signals,
        r_values=parameters["r_values"],
        max_hold_bars=int(parameters["max_hold_bars"]),
        fee_rate=float(parameters["fee_rate"]),
        maker_fee_rate=float(parameters["maker_fee_rate"]),
        slippage_per_side=float(parameters["slippage_per_side"]),
        select_r=None if parameters.get("selected_r") is None
        else float(parameters["selected_r"]),
    )
    return [
        {
            "net_r": trade["net_r"],
            "entry_bar": trade["entry_bar_index"],
            "exit_bar": trade["exit_bar_index"],
            "time": pd.Timestamp(trade["signal_time"]),
            "market": "",
        }
        for trade in (optimization["best"] or {"per_signal": {}})["per_signal"].values()
    ]


def command_confirm(corpus, args) -> None:
    overrides = parse_overrides(args.set)
    by_r = trades_for_config(corpus, overrides, per_r=False)
    trades = next(iter(by_r.values()), [])
    train, test = split_by_date(trades)

    print("OUT-OF-SAMPLE CONFIRMATION" + format_overrides(overrides))
    print()
    print(HEADER)
    print("-" * 88)
    print_row("TRAIN (fitted here)", summarise(train))
    print_row("TEST  (never fitted)", summarise(test))
    print_row("TEST  one position at a time", summarise(sequential_only(test)))

    test_stats = summarise(test)
    print()
    if test_stats and test_stats["expectancy_r"] > 0:
        print(f"TEST expectancy {test_stats['expectancy_r']:+.3f}R over "
              f"{test_stats['n']} trades.")
    else:
        print("TEST expectancy is not positive. The configuration failed "
              "out of sample regardless of its train figure.")


# --------------------------------------------------------------------- #

def parse_overrides(pairs: Iterable[str]) -> Dict[str, Any]:
    overrides: Dict[str, Any] = {}
    for pair in pairs or []:
        key, _, raw = pair.partition("=")
        try:
            value: Any = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        overrides[key.strip()] = value
    return overrides


def format_overrides(overrides: Dict[str, Any]) -> str:
    if not overrides:
        return ""
    return "  " + " ".join(f"{k}={v}" for k, v in sorted(overrides.items()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command",
                        choices=["baseline", "sweep", "placebo", "confirm"])
    parser.add_argument("--symbols", nargs="+")
    parser.add_argument("--intervals", nargs="+")
    parser.add_argument("--grid", default="trade", choices=sorted(GRIDS))
    parser.add_argument("--set", nargs="+", default=[],
                        help="parameter overrides, e.g. --set max_hold_bars=80")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--min-trades", type=int, default=200)
    parser.add_argument("--sequential", action="store_true",
                        help="score only non-overlapping trades")
    args = parser.parse_args()

    corpus = load_corpus(args.symbols, args.intervals)
    print(f"corpus: {len(corpus)} markets, "
          f"{sum(len(c) for _, c in corpus):,} bars")
    print()

    {
        "baseline": command_baseline,
        "sweep": command_sweep,
        "placebo": command_placebo,
        "confirm": command_confirm,
    }[args.command](corpus, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
