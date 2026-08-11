"""Paper-trade the RSI trendline break on Binance, 4h and slower.

Only 4h/6h/12h are worth running. On 15m and 1h the strategy is net-negative
once fees are charged -- see docs/superpowers/specs/2026-08-10-rsi-trendline-results.md.

Signals and entries come from `RSITrendlineBreakHypothesis.entry_for_break`,
the same function the backtest uses. A live loop with its own copy of the entry
rule is a loop that tests something other than what was measured.

Modes:
    --replay N   feed N historical bars in one at a time and reconcile the
                 result against the backtest. Run this first; it is the proof
                 that the live path and the tested path agree.
    (default)    poll live public klines, simulate fills locally. Places NO
                 orders and needs no API key.

No order placement exists here yet, on testnet or anywhere else. Fills are
simulated from public klines. Wiring `binance_client.place_market_order` in is
deliberately left until the simulated log has run long enough to be worth
believing.

Usage:
    python run_rsi_paper.py BTCUSDT 4h --replay 2000
    python run_rsi_paper.py BTCUSDT 4h --once
    python run_rsi_paper.py BTCUSDT 4h
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

import pandas as pd

from analysis.rsi_trendline_hypothesis import RSITrendlineBreakHypothesis

KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
STATE_ROOT = os.path.join(backend_dir, "..", "..", "logs", "backend", "paper")

INTERVAL_SECONDS = {
    "15m": 900, "1h": 3600, "2h": 7200, "4h": 14400,
    "6h": 21600, "12h": 43200, "1d": 86400,
}

# SMA(200) warmup plus room for the geometry to find anchors up to
# max_span_bars back. Below this the strategy silently produces nothing.
MIN_HISTORY_BARS = 400


# --------------------------------------------------------------------- #
# market data
# --------------------------------------------------------------------- #

def fetch_klines(symbol: str, interval: str, limit: int = 600) -> pd.DataFrame:
    """Recent klines. The LAST row is the still-forming bar, deliberately kept.

    Its `open` is final the moment it exists, and that open is the entry price
    the strategy specifies -- fill on the bar after the break.
    """
    url = f"{KLINES_URL}?symbol={symbol}&interval={interval}&limit={limit}"
    with urllib.request.urlopen(url, timeout=30) as response:
        raw = json.load(response)
    frame = pd.DataFrame([
        {
            "timestamp": int(row[0]) // 1000,
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
            "close_ms": int(row[6]),
        }
        for row in raw
    ])
    frame["time"] = pd.to_datetime(frame["timestamp"], unit="s")
    frame["bar_index"] = frame.index
    return frame


# --------------------------------------------------------------------- #
# the trader
# --------------------------------------------------------------------- #

class RSIPaperTrader:
    def __init__(self, symbol: str, interval: str, risk_fraction: float = 0.01,
                 equity: float = 10000.0, state_path: Optional[str] = None):
        self.symbol = symbol
        self.interval = interval
        self.risk_fraction = risk_fraction
        self.starting_equity = equity
        self.hypothesis = RSITrendlineBreakHypothesis()
        self.max_hold = int(self.hypothesis.parameters["max_hold_bars"])
        self.selected_r = float(self.hypothesis.parameters["selected_r"])
        self.taker = float(self.hypothesis.parameters["fee_rate"])
        self.maker = float(self.hypothesis.parameters["maker_fee_rate"])

        self.open_positions: List[Dict[str, Any]] = []
        self.closed_trades: List[Dict[str, Any]] = []
        self.seen_signal_bars: set = set()
        # Polling is deliberately more frequent than the bar period, so the
        # same closed bar is seen repeatedly. Marking it twice would double
        # every holding period and fire max_hold exits at half the true age.
        self.last_marked_bar: Optional[str] = None
        self.state_path = state_path or os.path.join(
            STATE_ROOT, f"{symbol}_{interval}.json")

    # ----------------------------------------------------------------- #

    def signals_on_bar(self, candles: pd.DataFrame, signal_bar: int):
        """Breaks that fired on `signal_bar`, as tradeable entries.

        `last_bar` is passed as one past the frame end on purpose. The
        hypothesis normally refuses a signal whose entry bar is the final bar,
        because a backtest cannot simulate a trade with no bars after it. Live,
        that bar is precisely the one we fill on -- it has just opened.
        """
        prepared = self.hypothesis.prepare(candles)
        entries = []
        for signal in prepared["sweep"].signals:
            if int(signal.bar_index) != signal_bar:
                continue
            entry, reason = self.hypothesis.entry_for_break(
                candles=prepared["candles"],
                row_by_bar=prepared["row_by_bar"],
                bar_index=int(signal.bar_index),
                side=signal.side,
                last_bar=len(candles),
            )
            entries.append((entry, reason, signal))
        return entries

    def open_position(self, entry, signal, bar_time) -> Dict[str, Any]:
        risk = abs(entry.entry_price - entry.stop_price)
        target = (entry.entry_price + risk * self.selected_r
                  if entry.side == "LONG"
                  else entry.entry_price - risk * self.selected_r)
        position = {
            "symbol": self.symbol,
            "side": entry.side,
            "signal_bar_time": str(bar_time),
            "entry_bar_index": entry.entry_bar_index,
            "entry_price": entry.entry_price,
            "stop_price": entry.stop_price,
            "target_price": target,
            "risk_per_unit": risk,
            "risk_pct": risk / entry.entry_price,
            "quantity": self._size(entry.entry_price, risk),
            "bars_held": 0,
            "rsi_at_break": float(signal.rsi_value),
            "line_value_at_break": float(signal.line_value_at_break),
            "opened_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.open_positions.append(position)
        return position

    def _size(self, entry_price: float, risk: float) -> float:
        """Fixed-fractional on the stop distance, not on notional.

        The 20-bar swing stop can sit 10% from entry on 4h, so a fixed notional
        size would make risk-per-trade swing by an order of magnitude.
        """
        if risk <= 0:
            return 0.0
        return round((self.starting_equity * self.risk_fraction) / risk, 6)

    def update_positions(self, bar: pd.Series) -> List[Dict[str, Any]]:
        """Mark every open position against one newly closed bar."""
        closed = []
        still_open = []
        for position in self.open_positions:
            position["bars_held"] += 1
            high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])

            if position["side"] == "LONG":
                stop_hit, target_hit = low <= position["stop_price"], high >= position["target_price"]
            else:
                stop_hit, target_hit = high >= position["stop_price"], low <= position["target_price"]

            # Stop before target: on a bar that spans both, assume the worse
            # fill. Anything else quietly inflates the result.
            if stop_hit:
                closed.append(self._close(position, position["stop_price"], "stop_loss", bar))
            elif target_hit:
                closed.append(self._close(position, position["target_price"], "target", bar))
            elif position["bars_held"] >= self.max_hold:
                closed.append(self._close(position, close, "max_hold", bar))
            else:
                still_open.append(position)

        self.open_positions = still_open
        self.closed_trades.extend(closed)
        return closed

    def _close(self, position, exit_price, reason, bar) -> Dict[str, Any]:
        # Mirrors signal_trade_simulator._simulate_single_trade exactly,
        # rounding included: cost summed before subtracting, net rounded to 6dp,
        # net_r derived from the ROUNDED net. Without that, a paper log and a
        # backtest log of the same trade differ in the last decimal -- invisible
        # on a 2,000-dollar BTC stop, but 2e-4 R on a 0.0024-dollar ADA stop,
        # which is enough to make reconciliation look like a real disagreement.
        is_maker = reason == "target"
        cost = (position["entry_price"] * self.taker
                + exit_price * (self.maker if is_maker else self.taker))
        gross = ((exit_price - position["entry_price"]) if position["side"] == "LONG"
                 else (position["entry_price"] - exit_price))
        net = round(gross - cost, 6)
        return {
            **position,
            "exit_price": round(exit_price, 6),
            "exit_reason": reason,
            "exit_time": str(bar["time"]),
            "exit_is_maker": is_maker,
            "gross_pnl": round(gross, 6),
            "fees": round(cost, 6),
            "net_pnl": net,
            "net_r": round(net / position["risk_per_unit"], 6),
            "cash_pnl": net * position["quantity"],
            "outcome": "WIN" if net > 0 else ("LOSS" if net < 0 else "BREAKEVEN"),
        }

    # ----------------------------------------------------------------- #

    def stats(self) -> Dict[str, Any]:
        trades = self.closed_trades
        if not trades:
            return {"n": 0}
        r_values = [t["net_r"] for t in trades]
        wins = [r for r in r_values if r > 0]
        losses = [-r for r in r_values if r < 0]
        gross_loss = sum(losses)
        return {
            "n": len(trades),
            "win_rate": len(wins) / len(trades),
            "expectancy_r": sum(r_values) / len(trades),
            "total_r": sum(r_values),
            "profit_factor": (sum(wins) / gross_loss) if gross_loss else float("inf"),
            "cash_pnl": sum(t["cash_pnl"] for t in trades),
        }

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as handle:
            json.dump({
                "symbol": self.symbol,
                "interval": self.interval,
                "parameters": self.hypothesis.parameters,
                "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "last_marked_bar": self.last_marked_bar,
                "open_positions": self.open_positions,
                "closed_trades": self.closed_trades,
                "stats": self.stats(),
            }, handle, indent=1, default=str)

    def load(self) -> bool:
        if not os.path.exists(self.state_path):
            return False
        with open(self.state_path, encoding="utf-8") as handle:
            state = json.load(handle)
        self.open_positions = state.get("open_positions", [])
        self.closed_trades = state.get("closed_trades", [])
        self.last_marked_bar = state.get("last_marked_bar")
        self.seen_signal_bars = {
            t["signal_bar_time"] for t in self.closed_trades + self.open_positions
        }
        return True


# --------------------------------------------------------------------- #
# replay reconciliation
# --------------------------------------------------------------------- #

def command_replay(symbol: str, interval: str, bars: int) -> int:
    """Drive the live loop bar by bar over history, then check it agrees.

    The live loop only ever sees bars up to `cursor`, so if its results match
    the backtest's, the backtest is not using anything the live loop lacks.
    """
    history_path = os.path.join(
        backend_dir, "..", "..", "logs", "backend", "history",
        symbol, interval, "candles.csv")
    if not os.path.exists(history_path):
        raise SystemExit(f"no history at {history_path} -- run fetch_binance_history.py")

    full = pd.read_csv(history_path).tail(bars).reset_index(drop=True)
    full["bar_index"] = full.index
    full["time"] = pd.to_datetime(full["timestamp"], unit="s")

    trader = RSIPaperTrader(symbol, interval,
                            state_path=os.path.join(STATE_ROOT, f"replay_{symbol}_{interval}.json"))

    print(f"replaying {len(full)} bars of {symbol} {interval}, one at a time")
    started = time.time()
    for cursor in range(MIN_HISTORY_BARS, len(full) - 1):
        # `cursor` is the bar that has just closed; `cursor + 1` has just
        # opened and is the bar an entry fills on. Positions are marked
        # against the bar that closed, BEFORE this bar's signal is acted on --
        # a position opened now is exposed to its own entry bar, and gets
        # marked on the next pass when that bar closes. Marking after opening
        # would skip the entry bar entirely, which is how a gap straight
        # through the stop goes unrecorded.
        visible = full.iloc[: cursor + 2].reset_index(drop=True)
        visible["bar_index"] = visible.index
        signal_bar = cursor

        trader.update_positions(full.iloc[cursor])

        for entry, reason, signal in trader.signals_on_bar(visible, signal_bar):
            if entry is None:
                continue
            key = str(full["time"].iloc[signal_bar])
            if key in trader.seen_signal_bars:
                continue
            trader.seen_signal_bars.add(key)
            trader.open_position(entry, signal, full["time"].iloc[signal_bar])

    # Mark against the final bar so trades opened on the second-to-last bar
    # are not left dangling.
    trader.update_positions(full.iloc[len(full) - 1])

    trader.save()
    elapsed = time.time() - started

    backtest = RSITrendlineBreakHypothesis().evaluate(pd.DataFrame(), full.copy())

    # Compare like with like. The backtest sees the whole file, so it also
    # scores signals from before the live loop's warmup finished, and signals
    # near the end whose trades the live loop has not closed yet. Neither is a
    # disagreement. The comparable set is: signal bar at or after the live
    # loop's first eligible bar, and closed by both.
    first_eligible = MIN_HISTORY_BARS - 1
    # A signal in the final max_hold bars cannot have been closed by the live
    # loop, because the bars that would close it do not exist yet.
    last_closeable = len(full) - trader.max_hold - 2

    live_by_bar = {int(t["entry_bar_index"]) - 1: t for t in trader.closed_trades}
    backtest_by_bar = {
        int(e["bar_index"]): e for e in backtest["detailed_log"]
        if first_eligible <= int(e["bar_index"]) <= last_closeable
    }

    # Both sides now round identically, so this is a strict equality check with
    # only float-noise slack.
    r_tolerance = 1e-9

    only_backtest = sorted(set(backtest_by_bar) - set(live_by_bar))
    only_live = sorted(
        bar for bar in set(live_by_bar) - set(backtest_by_bar)
        if bar <= last_closeable
    )
    mismatched = [
        bar for bar in sorted(set(live_by_bar) & set(backtest_by_bar))
        if abs(live_by_bar[bar]["net_r"] - backtest_by_bar[bar]["net_r"]) > r_tolerance
        or live_by_bar[bar]["exit_reason"] != backtest_by_bar[bar]["exit_reason"]
    ]

    live = trader.stats()
    comparable = [backtest_by_bar[b] for b in backtest_by_bar]
    print(f"\n{'':<30} {'n':>6} {'win':>8} {'exp(R)':>9} {'totR':>9}")
    print("-" * 66)
    print(f"{'live loop (bar by bar)':<30} {live['n']:>6} {live['win_rate']:>8.3f} "
          f"{live['expectancy_r']:>9.3f} {live['total_r']:>9.2f}")
    if comparable:
        r_values = [e["net_r"] for e in comparable]
        wins = sum(1 for r in r_values if r > 0)
        print(f"{'backtest (same bars)':<30} {len(comparable):>6} "
              f"{wins / len(comparable):>8.3f} "
              f"{sum(r_values) / len(comparable):>9.3f} {sum(r_values):>9.2f}")
    print(f"{'backtest (whole file)':<30} {backtest['sample_size']:>6} "
          f"{backtest['win_rate']:>8.3f} {backtest['expectancy_r']:>9.3f} "
          f"{backtest['total_r']:>9.2f}")

    print(f"\nreplayed {len(full) - MIN_HISTORY_BARS} bars in {elapsed:.0f}s; "
          f"{len(trader.open_positions)} still open at the end")
    print(f"signals only the backtest found: {only_backtest or 'none'}")
    print(f"signals only the live loop found: {only_live or 'none'}")
    print(f"trades scored differently: {mismatched or 'none'}")

    if only_backtest or only_live or mismatched:
        print("\nFAIL - the live loop and the backtest disagree. The live path "
              "is seeing something different; do not trade this.")
        return 1
    print(f"\nPASS - all {len(live_by_bar)} trades identical to the backtest, "
          "from bar-by-bar data only")
    return 0


# --------------------------------------------------------------------- #
# live polling
# --------------------------------------------------------------------- #

def poll_once(trader: RSIPaperTrader, verbose: bool = True) -> Dict[str, Any]:
    candles = fetch_klines(trader.symbol, trader.interval)
    forming = candles.iloc[-1]
    signal_bar = len(candles) - 2
    last_closed = candles.iloc[signal_bar]

    key = str(last_closed["time"])
    closed = []
    if trader.last_marked_bar != key:
        closed = trader.update_positions(last_closed)
        trader.last_marked_bar = key

    opened = []
    if key not in trader.seen_signal_bars:
        for entry, reason, signal in trader.signals_on_bar(candles, signal_bar):
            if entry is None:
                if verbose:
                    print(f"  break on {key} skipped: {reason}")
                continue
            trader.seen_signal_bars.add(key)
            opened.append(trader.open_position(entry, signal, last_closed["time"]))

    if verbose:
        print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%SZ}] "
              f"{trader.symbol} {trader.interval}  last closed {key}  "
              f"close {float(last_closed['close']):,.2f}  "
              f"forming open {float(forming['open']):,.2f}")
        for position in closed:
            print(f"  CLOSED {position['side']} {position['exit_reason']} "
                  f"{position['net_r']:+.2f}R")
        for position in opened:
            print(f"  OPENED {position['side']} @ {position['entry_price']:,.2f} "
                  f"stop {position['stop_price']:,.2f} "
                  f"target {position['target_price']:,.2f} "
                  f"risk {position['risk_pct'] * 100:.2f}%")
        print(f"  open {len(trader.open_positions)}  closed {len(trader.closed_trades)}  "
              f"{_stats_line(trader.stats())}")

    trader.save()
    return {"opened": opened, "closed": closed}


def _stats_line(stats: Dict[str, Any]) -> str:
    if not stats.get("n"):
        return "no closed trades yet"
    return (f"win {stats['win_rate']:.3f}  exp {stats['expectancy_r']:+.3f}R  "
            f"PF {stats['profit_factor']:.2f}  cash {stats['cash_pnl']:+,.2f}")


def command_live(symbol: str, interval: str, once: bool, risk: float,
                 equity: float) -> int:
    trader = RSIPaperTrader(symbol, interval, risk_fraction=risk, equity=equity)
    if trader.load():
        print(f"resumed: {len(trader.open_positions)} open, "
              f"{len(trader.closed_trades)} closed")

    period = INTERVAL_SECONDS[interval]
    print(f"paper trading {symbol} {interval}  R={trader.selected_r} "
          f"hold={trader.max_hold}  risk={risk:.1%} of {equity:,.0f}")
    print(f"state: {os.path.abspath(trader.state_path)}")
    print("no orders are placed; fills are simulated from public klines\n")

    while True:
        try:
            poll_once(trader)
        except Exception as exc:  # noqa: BLE001 - a poll failure must not end the run
            print(f"  poll failed: {type(exc).__name__}: {exc}")
        if once:
            return 0
        # Wake shortly after each bar closes rather than polling constantly.
        now = time.time()
        time.sleep(max(30.0, period - (now % period) + 15.0))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", nargs="?", default="BTCUSDT")
    parser.add_argument("interval", nargs="?", default="4h",
                        choices=sorted(INTERVAL_SECONDS))
    parser.add_argument("--replay", type=int, metavar="BARS",
                        help="reconcile the live loop against the backtest")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--risk", type=float, default=0.01)
    parser.add_argument("--equity", type=float, default=10000.0)
    args = parser.parse_args()

    if args.interval in ("15m", "1h"):
        print(f"WARNING: {args.interval} is net-negative after fees. "
              "Only 4h and slower showed an edge.\n")

    if args.replay:
        return command_replay(args.symbol, args.interval, args.replay)
    return command_live(args.symbol, args.interval, args.once,
                        args.risk, args.equity)


if __name__ == "__main__":
    sys.exit(main())
