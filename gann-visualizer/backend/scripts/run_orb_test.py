"""
CLI for the ORB go/no-go test.

Examples:
    python scripts/run_orb_test.py --symbol ^NSEI --variant A
    python scripts/run_orb_test.py --symbol ^NSEI --variant B --source dhan \\
        --start 2022-01-01 --end 2026-08-01 --out reports/orb_nifty_b.md
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.orb.runner import run_orb


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the pre-registered ORB go/no-go test")
    parser.add_argument("--symbol", required=True, help="e.g. ^NSEI or ^NSEBANK")
    parser.add_argument(
        "--variant",
        required=True,
        choices=["A", "B", "C"],
        help="A/B = ORB breakout variants, C = CRT liquidity sweep (reversal)",
    )
    parser.add_argument("--source", default="yfinance", choices=["yfinance", "dhan"])
    parser.add_argument("--interval", default="5", help="TradingView-style interval")
    parser.add_argument("--start", default=None, help="YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD")
    parser.add_argument("--placebo-seeds", type=int, default=200)
    parser.add_argument("--out", default=None, help="Write the report here as markdown")
    return parser


def fetch_bars(
    symbol: str, source: str, interval: str, start: str, end: str
) -> Tuple[pd.DataFrame, Optional[pd.DataFrame]]:
    """Return (intraday_bars, daily_bars). Daily is needed only by variant B."""
    if source == "yfinance":
        from yfinance_client import YFinanceClient

        client = YFinanceClient()
    else:
        from dhan_client import DhanClient

        client = DhanClient()

    intraday = client.fetch_data(symbol, start, end, interval)
    if intraday is None or intraday.empty:
        raise ValueError(
            f"{source} returned no intraday bars for {symbol} between {start} and {end}"
        )

    daily = client.fetch_data(symbol, start, end, "D")
    if daily is None or daily.empty:
        daily = None

    return intraday, daily


def render_report(report: Dict[str, Any]) -> str:
    lines = []
    lines.append(f"# ORB {report['variant']} — {report['symbol']}")
    lines.append("")

    if report["preliminary"]:
        lines.append("> **PRELIMINARY — INSUFFICIENT DATA.**")
        lines.append(
            "> Sourced from yfinance, which caps intraday history at roughly 60 days. "
            "The verdict is forced to INCONCLUSIVE regardless of the numbers below."
        )
        lines.append("")

    lines.append(f"## VERDICT: {report['verdict']}")
    lines.append("")
    for reason in report["verdict_reasons"]:
        lines.append(f"- {reason}")
    if report["verdict_reasons"]:
        lines.append("")

    lines.append(f"**Breakeven slippage: {report['breakeven_slippage']} index points per side.**")
    lines.append("")
    lines.append(
        "This is the number to judge margin by — the slippage level at which the edge "
        "reaches zero. Compare it against real execution cost for this instrument."
    )
    lines.append("")

    lines.append("## Sessions")
    lines.append("")
    sessions = report["sessions"]
    lines.append(f"- Available: {sessions['available']}")
    lines.append(f"- Traded: {sessions['traded']}")
    lines.append(f"- Skipped: {sessions['skipped']}")
    for reason, count in sorted(sessions["skip_reasons"].items()):
        lines.append(f"    - {reason}: {count}")
    lines.append("")

    lines.append("## Robustness grid (second half)")
    lines.append("")
    lines.append("| Cell | Headline | Trades | Avg net P&L (base) | Avg net P&L (2x costs) | First half |")
    lines.append("|---|---|---|---|---|---|")
    for cell in report["cells"]:
        lines.append(
            f"| {cell['label']} | {'yes' if cell['is_headline'] else ''} "
            f"| {cell['n_trades_test']} | {cell['avg_net_pnl_test_base']} "
            f"| {cell['avg_net_pnl_test_stressed']} | {cell['avg_net_pnl_train_base']} |"
        )
    lines.append("")
    lines.append(
        f"R = 1.0, second half, base costs: {report['info_only_r1_avg_net_pnl_test']} "
        "— reported for information, **not the verdict**."
    )
    lines.append("")

    lines.append("## Slippage sweep (second half, headline cell)")
    lines.append("")
    lines.append("| Slippage per side | Avg net P&L |")
    lines.append("|---|---|")
    for slippage in sorted(report["slippage_sweep"]):
        lines.append(f"| {slippage} | {report['slippage_sweep'][slippage]} |")
    lines.append("")

    lines.append("## Placebo")
    lines.append("")
    if report["placebo_percentile"] is None:
        lines.append(
            "Placebo test did not run — no seed produced a usable comparison run. "
            "See the verdict reasons above; a missing placebo forces INCONCLUSIVE."
        )
    else:
        lines.append(
            f"Real result beat {report['placebo_percentile']}% of {report['placebo_seeds']} "
            "random-entry runs. Entries were randomised in bar and direction while holding "
            "stop distance and holding period fixed. The pass bar is 95."
        )
    lines.append("")

    stats = report.get("placebo_stats")
    if stats and stats.get("seeds_used"):
        lines.append(
            f"Used {stats['seeds_used']}/{stats['seeds_requested']} placebo seeds "
            f"({stats['full_strength_seeds']} full strength, reproducing all "
            f"{stats['real_signal_count']} real signals; the thinnest seed had only "
            f"{stats['min_placebo_signals_in_a_seed']})."
        )
        if stats["full_strength_seeds"] / stats["seeds_used"] < 0.5:
            lines.append(
                "> **Caution:** fewer than half of placebo seeds were full strength — "
                "the comparison distribution is built from a degraded sample."
            )
        lines.append("")
    elif stats:
        lines.append("No placebo seed produced a usable run — the percentile above is undefined.")
        lines.append("")

    lines.append("## Assumptions")
    lines.append("")
    lines.append(
        f"- Fee rate: {report['fee_rate_base']} base / {report['fee_rate_stressed']} stressed. "
        "This is an **estimate** of NSE brokerage plus STT, exchange charges, stamp duty "
        "and GST, not a measured figure. Refine it against a real contract note."
    )
    lines.append(
        "- Gap-through-stop fills use the exact stop price, which is optimistic. "
        "A strategy that fails under this flattering assumption definitely fails."
    )
    lines.append("")

    return "\n".join(lines)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    end = args.end or datetime.now().strftime("%Y-%m-%d")
    start = args.start or "2020-01-01"

    intraday, daily = fetch_bars(args.symbol, args.source, args.interval, start, end)

    report = run_orb(
        symbol=args.symbol,
        variant=args.variant,
        bars=intraday,
        daily_bars=daily,
        data_source=args.source,
        bar_minutes=int(args.interval) if args.interval.isdigit() else 5,
        placebo_seeds=args.placebo_seeds,
    )

    text = render_report(report)
    print(text)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"\nWritten to {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
