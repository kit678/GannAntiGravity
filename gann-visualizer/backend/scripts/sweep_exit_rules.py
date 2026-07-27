"""Sweep entry/stop/hold rules across every hypothesis, scored on real trades.

The shipped trade model uses a hardcoded 0.5% stop for all non-BFT hypotheses and
a 10-bar max hold. That is the same combination that kept the RSI strategy
net-negative until it was replaced by a swing-based stop and a 40-bar hold
(-1178 -> +4920). This sweep tests whether the same fix helps the others.

Every configuration is scored on realized futures trades with fees, never on
MFE/MAE labels.

Usage:
    python gann-visualizer/backend/scripts/sweep_exit_rules.py [run_dir]
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd

from analysis.signal_trade_simulator import CandleSignal, simulate_trade_grid

DEFAULT_RUN = r"logs/backend/runs/BTCUSDT/15/2026-07-10_barctx_v2"
R_GRID = [1.0, 1.5, 2.0, 2.5, 3.0]
TAKER_FEE = 0.0004
SL_BUFFER = 0.0005

LONG_TYPES = {"SUPPORT_BOUNCE", "SUPPORT_TEST", "CROSS_UP", "GAP_CROSS_UP",
              "target_hit", "breach_confirmed"}
SHORT_TYPES = {"RESISTANCE_REJECTION", "RESISTANCE_TEST", "CROSS_DOWN",
               "GAP_CROSS_DOWN", "target_failed"}


def side_of(event_type: str) -> str | None:
    t = str(event_type)
    if t in LONG_TYPES:
        return "LONG"
    if t in SHORT_TYPES:
        return "SHORT"
    return None


def price_swing_pivots(candles: pd.DataFrame, lr: int = 3):
    """Confirmed fractal swing lows/highs on price."""
    lows, highs = [], []
    lo, hi = candles["low"].values, candles["high"].values
    for i in range(lr, len(candles) - lr):
        if all(lo[i] < lo[j] for j in range(i - lr, i)) and all(lo[i] < lo[j] for j in range(i + 1, i + 1 + lr)):
            lows.append((i + lr, i))
        if all(hi[i] > hi[j] for j in range(i - lr, i)) and all(hi[i] > hi[j] for j in range(i + 1, i + 1 + lr)):
            highs.append((i + lr, i))
    return lows, highs


def stop_for(candles, plows, phighs, bar, side, mode, entry):
    """Return a stop price, or None if the rule cannot produce a valid one."""
    if mode.startswith("fixed"):
        pct = float(mode.split("_")[1]) / 100.0
        return entry * (1 - pct) if side == "LONG" else entry * (1 + pct)
    if mode.startswith("window"):
        n = int(mode.split("_")[1])
        start = max(0, bar - n)
        w = candles.iloc[start: bar + 1]
        return (float(w["low"].min()) * (1 - SL_BUFFER) if side == "LONG"
                else float(w["high"].max()) * (1 + SL_BUFFER))
    if mode == "swing_pivot":
        pool = plows if side == "LONG" else phighs
        prior = [b for conf, b in pool if conf <= bar]
        if not prior:
            return None
        p = prior[-1]
        return (float(candles["low"].iloc[p]) * (1 - SL_BUFFER) if side == "LONG"
                else float(candles["high"].iloc[p]) * (1 + SL_BUFFER))
    raise ValueError(mode)


def bar_of(entry_time, dt_to_bar):
    """detailed_log stores entry_time as '07/03 00:00 UTC' -- no year. Match on
    month/day/hour/minute against the candle index instead of parsing a year."""
    if not entry_time:
        return None
    try:
        head = str(entry_time).replace(" UTC", "").strip()
        md, hm = head.split(" ")
        mo, dy = md.split("/")
        hh, mi = hm.split(":")
        return dt_to_bar.get((int(mo), int(dy), int(hh), int(mi)))
    except Exception:
        return None


def build_signals(candles, plows, phighs, events, stop_mode, entry_offset):
    sigs = []
    for bar, side in events:
        b = bar + entry_offset
        if b >= len(candles) - 1:
            continue
        entry = float(candles["close"].iloc[b])
        stop = stop_for(candles, plows, phighs, b, side, stop_mode, entry)
        if stop is None:
            continue
        if side == "LONG" and stop >= entry:
            continue
        if side == "SHORT" and stop <= entry:
            continue
        sigs.append(CandleSignal(b, side, entry, stop, str(b)))
    return sigs


def main() -> None:
    run_dir = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RUN
    candles = pd.read_csv(os.path.join(run_dir, "candles.csv")).reset_index(drop=True)
    candles["bar_index"] = candles.index
    dts = pd.to_datetime(candles["timestamp"], unit="s", utc=True)
    dt_to_bar = {(d.month, d.day, d.hour, d.minute): i for i, d in enumerate(dts)}
    plows, phighs = price_swing_pivots(candles)

    hyp_dir = os.path.join(run_dir, "analysis", "hypotheses")
    summary = json.load(open(os.path.join(hyp_dir, "run_summary.json")))

    configs = []
    for stop_mode in ("fixed_0.5", "fixed_1.0", "window_20", "swing_pivot"):
        for hold in (10, 40):
            configs.append((stop_mode, hold, 0))
    configs.append(("swing_pivot", 40, 1))  # next-bar entry

    print(f"run: {run_dir}\n")
    hdr = f"{'hypothesis':<30}{'baseline':>10}" + "".join(
        f"{m.replace('fixed_','f').replace('window_','w').replace('swing_pivot','swing')}/{h}{'+1' if e else '':>0}"[-11:].rjust(11)
        for m, h, e in configs)
    print(hdr)
    print("-" * len(hdr))

    for h in summary["hypotheses"]:
        fn = h["filename"] if h["filename"].endswith(".json") else h["filename"] + ".json"
        path = os.path.join(hyp_dir, fn)
        if not os.path.exists(path):
            continue
        full = json.load(open(path))
        log = [e for e in full.get("detailed_log", []) if e.get("trade_matched")]
        if len(log) < 30:
            continue

        events = []
        for e in log:
            bar = bar_of(e.get("entry_time"), dt_to_bar)
            if bar is None and e.get("bar_index") is not None:
                bar = int(e["bar_index"])
            side = (e.get("entry_side") or "").upper() or side_of(e.get("type") or e.get("event_type") or "")
            if bar is None or side not in ("LONG", "SHORT"):
                continue
            events.append((int(bar), side))
        if len(events) < 30:
            continue

        base_wr = full["in_sample"]["win_rate"]
        row = f"{h['name'][:29]:<30}{base_wr:>10.3f}"
        for stop_mode, hold, off in configs:
            sigs = build_signals(candles, plows, phighs, events, stop_mode, off)
            if not sigs:
                row += f"{'-':>11}"
                continue
            best = simulate_trade_grid(candles=candles, signals=sigs, r_values=R_GRID,
                                       max_hold_bars=hold, fee_rate=TAKER_FEE)["best"]
            row += f"{best['win_rate']:>11.3f}"
        print(row)

    print()
    print("columns: stop_rule/max_hold  (f=fixed %, w=window bars, swing=prior swing pivot)")
    print("baseline = win rate currently shipped (0.5% or test-candle stop, 10-bar hold)")
    print("all figures are realized futures trades including 0.04%/side taker fees")


if __name__ == "__main__":
    main()
