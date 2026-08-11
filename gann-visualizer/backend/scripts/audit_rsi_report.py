"""Re-derive every claim in an RSI report from raw candles, independently.

This is the anti-lookahead check. It does not call the strategy; it recomputes
RSI, SMA, stops, entries and exits from `candles.csv` and asserts the report
agrees. A hypothesis that quietly priced an entry off a bar that had not closed,
or anchored a line on a pivot that had not confirmed, fails here.

Usage:
    python gann-visualizer/backend/scripts/audit_rsi_report.py \
        logs/backend/runs/BTCUSDT/240/2026-08-10_rsi4h
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd

from analysis.rsi_pivots import compute_rsi_series

TOLERANCE = 1e-6


class Audit:
    def __init__(self) -> None:
        self.checks = 0
        self.failures: list[str] = []

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        self.checks += 1
        if not condition:
            self.failures.append(f"{name}: {detail}")

    def close(self, name: str, actual: float, expected: float, detail: str = "") -> None:
        self.check(name, abs(actual - expected) <= max(TOLERANCE, abs(expected) * 1e-9),
                   f"{detail} got {actual!r} expected {expected!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--report", default="rsi_trendline_break_strategy.json")
    args = parser.parse_args()

    candles = pd.read_csv(os.path.join(args.run_dir, "candles.csv")).reset_index(drop=True)
    report_path = os.path.join(args.run_dir, "analysis", "hypotheses", args.report)
    with open(report_path, encoding="utf-8") as handle:
        report = json.load(handle)

    log = report["detailed_log"]
    parameters = report.get("parameters", {})
    rsi_period = int(parameters.get("rsi_period", 14))
    sma_period = int(parameters.get("sma_period", 200))
    lookback = int(parameters.get("swing_lookback", 20))
    buffer = float(parameters.get("stop_buffer", 0.0005))
    max_hold = int(parameters.get("max_hold_bars", 40))

    rsi = compute_rsi_series(candles["close"], period=rsi_period)
    sma = candles["close"].rolling(sma_period, min_periods=sma_period).mean()
    high = candles["high"].to_numpy(float)
    low = candles["low"].to_numpy(float)
    close = candles["close"].to_numpy(float)
    open_ = candles["open"].to_numpy(float)

    audit = Audit()

    for entry in log:
        bar = int(entry["bar_index"])
        side = entry["direction"]
        tag = f"bar {bar} {side}"

        # --- indicators the report claims ---------------------------- #
        audit.close("rsi_value", entry["rsi_value"], float(rsi.iloc[bar]), tag)
        audit.close("sma_value", entry["sma_value"], float(sma.iloc[bar]), tag)
        audit.close("signal_close", entry["signal_close"], float(close[bar]), tag)

        # --- the trend filter actually held -------------------------- #
        if side == "LONG":
            audit.check("trend filter", close[bar] > sma.iloc[bar], tag)
        else:
            audit.check("trend filter", close[bar] < sma.iloc[bar], tag)

        # --- entry is the NEXT bar's open, never the signal close ----- #
        entry_bar = int(entry["entry_bar_index"])
        audit.check("entry bar is after the signal", entry_bar == bar + 1,
                    f"{tag} entry_bar={entry_bar}")
        audit.close("entry price is that bar's open",
                    entry["entry_price"], float(open_[entry_bar]), tag)

        # --- stop comes from bars the trader had already seen --------- #
        window_start = max(0, bar - lookback)
        if side == "LONG":
            expected_stop = float(low[window_start:bar + 1].min()) * (1 - buffer)
        else:
            expected_stop = float(high[window_start:bar + 1].max()) * (1 + buffer)
        audit.close("stop from signal-bar lookback", entry["stop_price"], expected_stop, tag)

        # --- geometry: anchors confirmed before the break ------------- #
        anchor_a, anchor_b = entry["pivot_a_bar_index"], entry["pivot_b_bar_index"]
        audit.check("anchor A precedes anchor B", anchor_a < anchor_b, tag)
        audit.check("newest anchor precedes the break", anchor_b < bar, tag)
        audit.close("anchor A rsi", entry["pivot_a_rsi"], float(rsi.iloc[anchor_a]), tag)
        audit.close("anchor B rsi", entry["pivot_b_rsi"], float(rsi.iloc[anchor_b]), tag)

        # --- slope sense matches the trade direction ------------------ #
        if side == "LONG":
            audit.check("LONG breaks a FALLING line drawn on highs",
                        entry["line_direction"] == "down"
                        and entry["pivot_a_rsi"] > entry["pivot_b_rsi"], tag)
        else:
            audit.check("SHORT breaks a RISING line drawn on lows",
                        entry["line_direction"] == "up"
                        and entry["pivot_a_rsi"] < entry["pivot_b_rsi"], tag)

        # --- the break is a genuine two-bar cross --------------------- #
        slope = entry["line_slope"]
        start_bar, start_rsi = entry["line_start_bar_index"], entry["line_start_rsi"]
        line_at = lambda b: start_rsi + slope * (b - start_bar)  # noqa: E731
        audit.close("line value at break", entry["line_value_at_break"], line_at(bar), tag)
        if side == "LONG":
            audit.check("rsi was at or below the line the bar before",
                        float(rsi.iloc[bar - 1]) <= line_at(bar - 1) + TOLERANCE, tag)
            audit.check("rsi is above the line at the break",
                        float(rsi.iloc[bar]) > line_at(bar), tag)
        else:
            audit.check("rsi was at or above the line the bar before",
                        float(rsi.iloc[bar - 1]) >= line_at(bar - 1) - TOLERANCE, tag)
            audit.check("rsi is below the line at the break",
                        float(rsi.iloc[bar]) < line_at(bar), tag)

        # --- replay the exit from raw price --------------------------- #
        stop = entry["stop_price"]
        target = entry["target_price"]
        expected_exit_bar, expected_exit_price, expected_reason = None, None, "max_hold"
        for position in range(entry_bar, min(entry_bar + max_hold, len(candles))):
            if side == "LONG":
                stop_hit, target_hit = low[position] <= stop, high[position] >= target
            else:
                stop_hit, target_hit = high[position] >= stop, low[position] <= target
            expected_exit_bar = position
            expected_exit_price = float(close[position])
            if stop_hit:
                expected_exit_price, expected_reason = stop, "stop_loss"
                break
            if target_hit:
                expected_exit_price, expected_reason = target, "target"
                break

        audit.check("exit bar", entry["exit_bar_index"] == expected_exit_bar,
                    f"{tag} got {entry['exit_bar_index']} expected {expected_exit_bar}")
        audit.check("exit reason",
                    entry["exit_reason"] in (expected_reason, "end_of_data"),
                    f"{tag} got {entry['exit_reason']} expected {expected_reason}")
        audit.check("exit is not before entry",
                    entry["exit_bar_index"] >= entry_bar, tag)
        if entry["exit_reason"] == expected_reason:
            audit.close("exit price", entry["exit_price"], expected_exit_price, tag)

        # --- fees are actually charged -------------------------------- #
        audit.check("fees charged", entry["fees"] > 0, tag)
        audit.close("net = gross - fees",
                    entry["net_pnl"], entry["gross_pnl"] - entry["fees"], tag)
        risk = abs(entry["entry_price"] - entry["stop_price"])
        audit.close("net_r = net / risk", entry["net_r"], entry["net_pnl"] / risk, tag)

    print(f"{len(log)} trades, {audit.checks} assertions")
    if audit.failures:
        print(f"\n{len(audit.failures)} FAILURES:")
        for failure in audit.failures[:40]:
            print("  " + failure)
        return 1
    print("\nPASS - every entry, stop, break and exit re-derives from raw candles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
