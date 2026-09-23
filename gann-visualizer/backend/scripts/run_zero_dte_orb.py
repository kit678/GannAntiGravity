"""
CLI for the US 0DTE opening-range-breakout test (bought premium, never sold).

The opening-range lengths are declared here, before any run, and the result has
to hold across all of them. Reporting whichever one won afterwards is curve
fitting. Spread is a stress axis, not a parameter: the report leads with the
level at which the edge dies.

The headline metric is the mean per-trade return with a confidence interval,
plus the minimum effect this sample size could actually detect. Win rate and
profit factor are reported but not judged on: both are dollar-weighted and
neither can separate "is zero" from "cannot tell".

Example:
    python scripts/run_zero_dte_orb.py --underlyings SPY QQQ IWM \\
        --start 2025-03-01 --end 2026-09-19 --out reports/zero_dte_orb_pooled.md
"""

import argparse
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List

sys.path.append(str(Path(__file__).resolve().parents[1]))

from alpaca_client import AlpacaClient
from strategy.orb.costs import breakeven_slippage
from strategy.zero_dte.core import (
    SPREAD_SWEEP,
    OptionTrade,
    minimum_detectable_effect,
    summarise,
)
from strategy.zero_dte.runner import BarSource, load_sessions, run_cell

# Pre-registered before running. The result must hold across all three.
OR_MINUTES_VARIANTS: List[int] = [5, 10, 15]
BREAKOUT_RULES: List[str] = ["close", "touch"]

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="0DTE opening range breakout, long premium only")
    p.add_argument("--underlyings", nargs="+", default=["SPY", "QQQ", "IWM"])
    p.add_argument("--start", default="2025-03-01")
    p.add_argument("--end", default="2026-09-19")
    p.add_argument("--take-profit", type=float, default=1.0, help="fraction, 1.0 = +100%%")
    p.add_argument("--stop-loss", type=float, default=0.5, help="fraction, 0.5 = -50%%")
    p.add_argument("--notional", type=float, default=500.0)
    p.add_argument("--fee-per-contract", type=float, default=0.05)
    p.add_argument("--out", default=None, help="write the markdown report here")
    return p.parse_args()


def table(rows: List[List[str]], header: List[str]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def stats_row(label: List[str], trades: List[OptionTrade]) -> List[str]:
    s = summarise(trades)
    if not s.get("trades"):
        return label + ["0"] + ["-"] * 6
    mde = minimum_detectable_effect(s["return_sd"], int(s["trades"]))
    return label + [
        str(s["trades"]),
        f"{s['mean_return']:+.2f}%",
        f"[{s['ci_low']:+.1f}%, {s['ci_high']:+.1f}%]",
        f"{s['t_stat']:.2f}",
        f"{mde:.2f}%",
        f"{s['win_rate']:.1f}%",
        f"{s['profit_factor']:.2f}",
    ]


STATS_HEADER = ["N", "Mean ret", "95% CI", "t", "MDE(80%)", "Win%", "PF"]


def weekday_breakdown(trades: List[OptionTrade]) -> str:
    rows = []
    for i, name in enumerate(WEEKDAYS):
        day_trades = [t for t in trades if t.session_date.weekday() == i]
        if day_trades:
            rows.append(stats_row([name], day_trades))
    return table(rows, ["Day"] + STATS_HEADER)


def half_split(trades: List[OptionTrade]) -> str:
    if len(trades) < 4:
        return "_not enough trades to split_"
    ordered = sorted(trades, key=lambda t: t.session_date)
    cut = (len(ordered) + 1) // 2
    rows = []
    for name, chunk in [("First half", ordered[:cut]), ("Second half", ordered[cut:])]:
        rows.append(stats_row([f"{name} ({chunk[0].session_date}..{chunk[-1].session_date})"], chunk))
    return table(rows, ["Period"] + STATS_HEADER)


def main() -> None:
    args = parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()

    source = BarSource(AlpacaClient())
    sessions_by_symbol = {}
    for symbol in args.underlyings:
        sessions_by_symbol[symbol] = load_sessions(source, symbol, start, end)
        print(f"Loaded {len(sessions_by_symbol[symbol])} {symbol} sessions", flush=True)

    out: List[str] = [
        f"# 0DTE Opening Range Breakout — {', '.join(args.underlyings)}",
        "",
        f"- Window: {start} to {end}",
        "- Direction: **bought premium only** (ATM 0DTE call on an upside break, put on a downside break)",
        f"- Exits: +{args.take_profit:.0%} / -{args.stop_loss:.0%} / flat by 15:30 ET",
        f"- Sizing: ${args.notional:,.0f} notional, sized off the observed premium so contract",
        "  count does not move with the spread; minimum 1 contract so expensive days stay in",
        f"- Fee ${args.fee_per_contract}/contract/side",
        "- Entry is the bar AFTER the breakout bar closes, never the breakout close itself",
        "- A bar spanning both target and stop is scored as a **loss**",
        "",
        "**Judge on `Mean ret` and its CI.** `MDE(80%)` is the smallest true edge this",
        "sample could reliably detect — if |Mean ret| < MDE, the run cannot answer the",
        "question either way, whatever the profit factor says.",
        "",
        "## Pooled across underlyings, zero spread",
        "",
    ]

    pooled: Dict[tuple, List[OptionTrade]] = {}
    all_skips: Dict[tuple, Counter] = {}
    rows = []

    for rule in BREAKOUT_RULES:
        for or_minutes in OR_MINUTES_VARIANTS:
            trades: List[OptionTrade] = []
            skips: Counter = Counter()
            for symbol, sessions in sessions_by_symbol.items():
                cell_trades, cell_skips = run_cell(
                    sessions, source, symbol,
                    or_minutes=or_minutes, spread_pct=0.0,
                    take_profit_pct=args.take_profit, stop_loss_pct=args.stop_loss,
                    fee_per_contract=args.fee_per_contract, notional=args.notional,
                    breakout_rule=rule,
                )
                trades += cell_trades
                skips.update(cell_skips)
            pooled[(rule, or_minutes)] = trades
            all_skips[(rule, or_minutes)] = skips
            rows.append(stats_row([rule, f"{or_minutes}m"], trades))
            s = summarise(trades)
            print(f"{rule:>6} OR={or_minutes:>2}m n={s.get('trades',0)} "
                  f"mean={s.get('mean_return',0):+.2f}% t={s.get('t_stat',0):.2f} "
                  f"skips={dict(skips)}", flush=True)

    out.append(table(rows, ["Rule", "OR"] + STATS_HEADER))

    out += ["", "## Per-underlying (close rule, zero spread)", ""]
    per_symbol_rows = []
    for or_minutes in OR_MINUTES_VARIANTS:
        for symbol, sessions in sessions_by_symbol.items():
            cell_trades, _ = run_cell(
                sessions, source, symbol, or_minutes=or_minutes, spread_pct=0.0,
                take_profit_pct=args.take_profit, stop_loss_pct=args.stop_loss,
                fee_per_contract=args.fee_per_contract, notional=args.notional,
            )
            per_symbol_rows.append(stats_row([symbol, f"{or_minutes}m"], cell_trades))
    out.append(table(per_symbol_rows, ["Symbol", "OR"] + STATS_HEADER))

    out += ["", "## Spread stress (close rule, pooled)", ""]
    spread_rows = []
    per_variant_pnl: Dict[int, Dict[float, float]] = {}
    for or_minutes in OR_MINUTES_VARIANTS:
        per_variant_pnl[or_minutes] = {}
        for spread in SPREAD_SWEEP:
            trades = []
            for symbol, sessions in sessions_by_symbol.items():
                cell_trades, _ = run_cell(
                    sessions, source, symbol, or_minutes=or_minutes, spread_pct=spread,
                    take_profit_pct=args.take_profit, stop_loss_pct=args.stop_loss,
                    fee_per_contract=args.fee_per_contract, notional=args.notional,
                )
                trades += cell_trades
            s = summarise(trades)
            per_variant_pnl[or_minutes][spread] = s.get("mean_return", 0.0)
            spread_rows.append(stats_row([f"{or_minutes}m", f"{spread:.0%}"], trades))
    out.append(table(spread_rows, ["OR", "Spread"] + STATS_HEADER))

    out += ["", "### Breakeven spread (mean return crosses zero)", ""]
    for or_minutes, by_spread in per_variant_pnl.items():
        out.append(f"- **OR {or_minutes}m** — crosses zero at a round-trip spread of "
                   f"**{breakeven_slippage(by_spread):.2%}**")

    out += ["", "## Sessions dropped, and why", "",
            "_A run that cannot account for every session is not auditable._", ""]
    skip_rows = []
    for (rule, or_minutes), skips in all_skips.items():
        if skips:
            skip_rows.append([rule, f"{or_minutes}m",
                              ", ".join(f"{k}={v}" for k, v in sorted(skips.items()))])
        else:
            skip_rows.append([rule, f"{or_minutes}m", "none"])
    out.append(table(skip_rows, ["Rule", "OR", "Skipped"]))

    for or_minutes in OR_MINUTES_VARIANTS:
        trades = pooled[("close", or_minutes)]
        out += ["", f"## OR {or_minutes}m (close rule), zero spread", "",
                "### By weekday", "",
                "_Reported, not used as a filter. Selecting the good days after the fact "
                "is how a backtest fools you._", "",
                weekday_breakdown(trades),
                "", "### Chronological halves", "", half_split(trades)]

    report = "\n".join(out)
    print("\n" + report)

    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")
        print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
