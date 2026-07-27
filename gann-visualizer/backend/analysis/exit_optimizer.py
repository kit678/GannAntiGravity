"""
Exit Optimizer — finds optimal R-multiple TP for bounce follow-through events
using structural stop loss (test candle low, close-based trigger).

Grid searches R values [1.0, 1.5, 2.0, 2.5, 3.0] with:
  - SL: test candle low × 0.9985 (0.15% buffer below), close-based trigger
  - TP: entry + (risk × R), risk = entry − sl_price
  - Max hold: 10 bars (exit at close if neither triggers)

Walk-forward validated (70/30 chronological split).
Integrated into HypothesisRunner.run_all() for automatic per-hypothesis optimization.
"""

import math
import re
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

TAKER_FEE = 0.0004           # 0.04% per side
SL_BUFFER = 0.0              # No buffer, exact test candle extreme
R_VALUES = [1.0, 1.5, 2.0, 2.5, 3.0]   # R-multiples to test
MAX_HOLD_BARS = 10           # exit at close if neither SL nor TP hit

# Event type → trade direction mapping
_BEARISH_TYPES = {'RESISTANCE_REJECTION', 'RESISTANCE_TEST', 'CROSS_DOWN', 'GAP_CROSS_DOWN'}
_BULLISH_TYPES = {'SUPPORT_BOUNCE', 'SUPPORT_TEST', 'CROSS_UP', 'GAP_CROSS_UP', 'target_hit', 'target_failed', 'breach_confirmed', 'BREACH_CONFIRMED_NO_ALPHA'}


def _detect_side(event_type: str) -> Optional[str]:
    """Return 'LONG', 'SHORT', or None (skip) for a given event type."""
    if event_type in _BEARISH_TYPES:
        return "SHORT"
    if event_type in _BULLISH_TYPES:
        return "LONG"
    return None


@dataclass
class TradeSimResult:
    """Result of simulating one trade with a specific R value."""
    entry_bar: int
    entry_price: float
    side: str          # LONG or SHORT
    exit_bar: int
    exit_price: float
    exit_reason: str   # stop_loss, target_hit, time_exit
    raw_pnl: float
    net_pnl: float
    pnl_pct: float
    bars_held: int


@dataclass
class ComboResult:
    """Aggregated results for one R value."""
    r_value: float
    sl_pct_below_entry: float = 0.0  # avg SL distance as % of entry
    tp_pct_above_entry: float = 0.0  # avg TP distance as % of entry
    n: int = 0
    wins: int = 0
    total_pnl: float = 0.0
    avg_bars_held: float = 0.0
    avg_profit: float = 0.0
    avg_loss: float = 0.0
    max_drawdown_run: float = 0.0
    trades: List[TradeSimResult] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return self.wins / self.n if self.n > 0 else 0.0

    @property
    def avg_pnl(self) -> float:
        return self.total_pnl / self.n if self.n > 0 else 0.0

    @property
    def profit_factor(self) -> float:
        win_pnl = sum(t.net_pnl for t in self.trades if t.net_pnl > 0)
        loss_pnl = abs(sum(t.net_pnl for t in self.trades if t.net_pnl < 0))
        return win_pnl / loss_pnl if loss_pnl > 0 else float('inf')

    @property
    def expectancy(self) -> float:
        if self.n == 0:
            return 0.0
        avg_w = sum(t.net_pnl for t in self.trades if t.net_pnl > 0) / max(self.wins, 1)
        avg_l = abs(sum(t.net_pnl for t in self.trades if t.net_pnl < 0)) / max(self.n - self.wins, 1)
        if avg_l == 0:
            return float('inf')
        return (self.win_rate * avg_w - (1 - self.win_rate) * avg_l) / avg_l

    @property
    def composite_score(self) -> float:
        """Composite: expectancy × profit_factor × sqrt(n)."""
        if self.n < 5:
            return 0.0
        return self.expectancy * self.profit_factor * math.sqrt(self.n)

    def summary_dict(self) -> Dict[str, Any]:
        return {
            "r_value": self.r_value,
            "sl_pct_below_entry": round(self.sl_pct_below_entry, 4),
            "tp_pct_above_entry": round(self.tp_pct_above_entry, 4),
            "n": self.n,
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 2),
            "expectancy": round(self.expectancy, 4),
            "total_pnl": round(self.total_pnl, 2),
            "avg_pnl": round(self.avg_pnl, 2),
            "avg_bars_held": round(self.avg_bars_held, 1),
            "composite_score": round(self.composite_score, 2),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Exit Optimizer
# ═══════════════════════════════════════════════════════════════════════════════

class ExitOptimizer:
    """
    Optimizes R-multiple TP for bounce follow-through events.

    SL: test candle low × (1 − SL_BUFFER), close-based trigger.
    TP: entry + (risk × R), where risk = entry − sl_price.
    Max hold: 10 bars.

    Walk-forward validated (70/30 chronological split).
    """

    def __init__(
        self,
        events_df: pd.DataFrame,
        candles_df: pd.DataFrame,
        train_pct: float = 0.7,
        commission: float = TAKER_FEE,
    ):
        self.events_df = events_df.reset_index(drop=True)
        self.candles_df = candles_df
        self.train_pct = train_pct
        self.commission = commission

        # Normalize candle index — candles.csv uses 'timestamp' not 'bar_index'
        if 'bar_index' not in self.candles_df.columns and 'Bar_Index' not in self.candles_df.columns:
            self.candles_df['bar_index'] = range(len(self.candles_df))
        self.candle_bar_col = 'bar_index' if 'bar_index' in self.candles_df.columns else 'Bar_Index'

        # Build candle lookup by bar_index (sequential)
        self.candle_lookup: Dict[int, Dict] = {}
        for idx, c in self.candles_df.iterrows():
            bidx = int(c[self.candle_bar_col])
            self.candle_lookup[bidx] = {
                'open': float(c.get('open', c.get('Open', 0))),
                'high': float(c.get('high', c.get('High', 0))),
                'low': float(c.get('low', c.get('Low', 0))),
                'close': float(c.get('close', c.get('Close', 0))),
                'timestamp': float(c.get('timestamp', c.get('time', 0))),
            }

        self.max_candle_idx = max(self.candle_lookup.keys()) if self.candle_lookup else 0

        # Build timestamp-based lookup for events that reference Raw_Timestamp
        self.ts_to_bar: Dict[int, int] = {}
        for bidx, c in self.candle_lookup.items():
            ts = int(c.get('timestamp', 0))
            if ts > 0:
                self.ts_to_bar[ts] = bidx

        # Split events chronologically for walk-forward
        self._split_events()

    def _split_events(self):
        """Split events chronologically into in-sample and walk-forward test sets."""
        if 'bar_index' not in self.events_df.columns:
            if 'Bar_Index' in self.events_df.columns:
                self.events_df['bar_index'] = self.events_df['Bar_Index']
            else:
                self.events_df['bar_index'] = range(len(self.events_df))

        self.events_df = self.events_df.sort_values('bar_index').reset_index(drop=True)
        split_idx = int(len(self.events_df) * self.train_pct)

        self.train_events = self.events_df.iloc[:split_idx].copy() if split_idx >= 10 else self.events_df.copy()
        self.test_events = self.events_df.iloc[split_idx:].copy() if split_idx >= 10 else pd.DataFrame()

    def optimize(self) -> Dict[str, Any]:
        """
        Run optimization: grid search R values with fixed structural SL.
        Returns best R and walk-forward validation.
        """
        print(f"  [ExitOptimizer] Events: {len(self.events_df)} total "
              f"({len(self.train_events)} train, {len(self.test_events)} test)")

        # Grid search all R values
        print(f"  [ExitOptimizer] Grid searching R values {R_VALUES}...")
        results: List[ComboResult] = []

        for r in R_VALUES:
            result = self._simulate_r(self.train_events, r)
            if result.n >= 5:
                results.append(result)
                print(f"    R={r:.1f}: n={result.n}, WR={result.win_rate:.1%}, "
                      f"PF={result.profit_factor:.2f}, Expect={result.expectancy:.4f}, "
                      f"Composite={result.composite_score:.2f}")

        if not results:
            return {"error": "No valid R values (all had < 5 qualifying trades)"}

        # Rank by composite_score
        results.sort(key=lambda r: r.composite_score, reverse=True)
        best = results[0]

        print(f"  [ExitOptimizer] Best: R={best.r_value:.1f}, WR={best.win_rate:.1%}, "
              f"PF={best.profit_factor:.2f}")

        # Walk-forward validation on best R
        wf = self._validate_wf(best.r_value)

        return {
            "config": {
                "sl_type": "structural_test_low",
                "sl_buffer": SL_BUFFER,
                "sl_trigger": "close_based",
                "tp_type": "fixed_rr",
                "best_r": best.r_value,
                "max_hold_bars": MAX_HOLD_BARS,
            },
            "best": best.summary_dict(),
            "all_r_results": [r.summary_dict() for r in results],
            "walk_forward_validation": wf,
        }

    def get_per_event_trades(self, r_value: float) -> Dict[int, Dict[str, Any]]:
        """
        Simulate all events with a given R value and return per-event trade
        results keyed by Raw_Timestamp (int).
        Used to attach entry/exit data to detailed_log for the navigator.
        """
        from datetime import datetime, timezone

        REASON_LABELS = {
            "stop_loss": "Stop loss",
            "target_hit": "TP hit",
            "time_exit": "Max hold",
            "end_of_data": "End of data",
        }

        def _fmt_time(ts_val) -> str:
            """Format epoch ms or s timestamp to readable UTC string."""
            try:
                v = float(ts_val)
                secs = v / 1000.0 if v > 1e10 else v
                return datetime.fromtimestamp(secs, tz=timezone.utc).strftime("%m/%d %H:%M UTC")
            except (ValueError, TypeError, OSError):
                return ""

        out: Dict[int, Dict[str, Any]] = {}
        for _, event in self.events_df.iterrows():
            sim = self._simulate_one(event, r_value)
            raw_ts = int(float(event.get('Raw_Timestamp', event.get('Timestamp', 0))))
            if sim is None:
                continue

            # Get entry and exit timestamps
            entry_ts = self.candle_lookup.get(sim.entry_bar, {}).get('timestamp')
            exit_ts = self.candle_lookup.get(sim.exit_bar, {}).get('timestamp')

            exit_label = REASON_LABELS.get(sim.exit_reason, sim.exit_reason)
            if sim.exit_reason == 'time_exit':
                exit_label = f"Max hold ({sim.bars_held}b)"
            elif sim.exit_reason == 'stop_loss':
                exit_label = f"SL @ {sim.exit_price:.1f}"
            elif sim.exit_reason == 'target_hit':
                exit_label = f"TP @ {sim.exit_price:.1f}"

            out[raw_ts] = {
                "entry_price": sim.entry_price,
                "entry_time": _fmt_time(entry_ts) if entry_ts else "",
                "exit_price": sim.exit_price,
                "exit_time": _fmt_time(exit_ts) if exit_ts else "",
                "exit_reason": sim.exit_reason,
                "exit_label": exit_label,
                "net_pnl": sim.net_pnl,
                "pnl_pct": sim.pnl_pct,
                "bars_held": sim.bars_held,
                "r_value": r_value,
            }
        return out

    # ── Core simulation methods ───────────────────────────────────────────────

    def _simulate_r(self, events: pd.DataFrame, r_value: float) -> ComboResult:
        """Simulate all events with a single R value."""
        result = ComboResult(r_value=r_value)

        total_sl_pct = 0.0
        total_tp_pct = 0.0
        pnl_series = []

        for _, event in events.iterrows():
            sim = self._simulate_one(event, r_value)
            if sim is None:
                continue

            result.trades.append(sim)
            result.n += 1
            result.total_pnl += sim.net_pnl
            result.avg_bars_held += sim.bars_held

            if sim.net_pnl > 0:
                result.wins += 1
                result.avg_profit += sim.net_pnl
            else:
                result.avg_loss += abs(sim.net_pnl)

            pnl_series.append(sim.net_pnl)

        if result.n > 0:
            result.avg_bars_held /= result.n
        if result.wins > 0:
            result.avg_profit /= result.wins
        if result.n - result.wins > 0:
            result.avg_loss /= (result.n - result.wins)

        return result

    def _simulate_one(self, event, r_value: float) -> Optional[TradeSimResult]:
        """Simulate one trade with structural SL and R-based TP.
        Handles both BFT events (test-candle SL) and generic events (%-based SL).
        """
        etype = str(event.get('Type', ''))
        side = _detect_side(etype)
        if side is None:
            return None

        # ── Find confirmation candle ───────────────────────────────────────────
        raw_ts = int(float(event.get('Raw_Timestamp', 0)))
        conf_bar_idx = self.ts_to_bar.get(raw_ts)
        if conf_bar_idx is None:
            conf_bar_idx = int(event.get('bar_index', event.get('Bar_Index', -1)))
            if conf_bar_idx not in self.candle_lookup:
                return None

        conf_candle = self.candle_lookup.get(conf_bar_idx)
        if conf_candle is None:
            return None

        entry_price = conf_candle['close']

        # ── Try to find test candle (only for BFT events with T+N details) ─────
        test_candle = None
        t_delay = 1
        details = str(event.get("Details", ""))
        m = re.search(r'T\+(\d+)', details)
        if m:
            t_delay = int(m.group(1))
            test_bar_idx = conf_bar_idx - t_delay
            test_candle = self.candle_lookup.get(test_bar_idx)

        # ── Compute SL: test-candle-based for BFT, %-based for generic ────────
        GENERIC_RISK_PCT = 0.005  # 0.5% risk for non-BFT events

        if test_candle is not None:
            # BFT: structural SL below/above test candle extreme
            if side == "LONG":
                sl_price = test_candle['low'] * (1.0 - SL_BUFFER)
                risk = entry_price - sl_price
            else:
                sl_price = test_candle['high'] * (1.0 + SL_BUFFER)
                risk = sl_price - entry_price
        else:
            # Generic: %-based SL
            if side == "LONG":
                sl_price = entry_price * (1.0 - GENERIC_RISK_PCT)
                risk = entry_price - sl_price
            else:
                sl_price = entry_price * (1.0 + GENERIC_RISK_PCT)
                risk = sl_price - entry_price

        if risk <= 0:
            return None

        tp_price = entry_price + risk * r_value if side == "LONG" else entry_price - risk * r_value

        # ── Per-bar forward replay ────────────────────────────────────────────
        for offset in range(1, MAX_HOLD_BARS + 1):
            bidx = conf_bar_idx + offset
            candle = self.candle_lookup.get(bidx)
            if candle is None:
                # End of data — count as time exit at entry
                return self._make_result(
                    conf_bar_idx, entry_price, side,
                    bidx - 1, entry_price, "end_of_data", 0.0, offset - 1,
                )

            # 1. Check stop loss — close-based trigger (wicks don't count)
            if side == "LONG" and candle['close'] <= sl_price:
                raw_pnl = sl_price - entry_price
                return self._make_result(
                    conf_bar_idx, entry_price, side,
                    bidx, sl_price, "stop_loss", raw_pnl, offset,
                )
            elif side == "SHORT" and candle['close'] >= sl_price:
                raw_pnl = entry_price - sl_price
                return self._make_result(
                    conf_bar_idx, entry_price, side,
                    bidx, sl_price, "stop_loss", raw_pnl, offset,
                )

            # 2. Check take profit — immediate exit on wick reaching TP
            if side == "LONG" and candle['high'] >= tp_price:
                raw_pnl = tp_price - entry_price
                return self._make_result(
                    conf_bar_idx, entry_price, side,
                    bidx, tp_price, "target_hit", raw_pnl, offset,
                )
            elif side == "SHORT" and candle['low'] <= tp_price:
                raw_pnl = entry_price - tp_price
                return self._make_result(
                    conf_bar_idx, entry_price, side,
                    bidx, tp_price, "target_hit", raw_pnl, offset,
                )

        # ── Time exit at max_hold ─────────────────────────────────────────────
        final_bar_idx = conf_bar_idx + MAX_HOLD_BARS
        final_candle = self.candle_lookup.get(final_bar_idx, conf_candle)
        exit_price = final_candle['close']
        raw_pnl = exit_price - entry_price if side == "LONG" else entry_price - exit_price

        return self._make_result(
            conf_bar_idx, entry_price, side,
            final_bar_idx, exit_price, "time_exit", raw_pnl, MAX_HOLD_BARS,
        )

    def _make_result(self, entry_bar, entry_price, side, exit_bar, exit_price,
                     exit_reason, raw_pnl, bars_held) -> TradeSimResult:
        """Create TradeSimResult with commission applied."""
        commission = entry_price * TAKER_FEE + exit_price * TAKER_FEE
        net_pnl = raw_pnl - commission
        pnl_pct = (net_pnl / entry_price) * 100 if entry_price > 0 else 0.0
        return TradeSimResult(
            entry_bar=entry_bar, entry_price=entry_price, side=side,
            exit_bar=exit_bar, exit_price=exit_price, exit_reason=exit_reason,
            raw_pnl=raw_pnl, net_pnl=net_pnl, pnl_pct=pnl_pct,
            bars_held=bars_held,
        )

    # ── Walk-forward validation ───────────────────────────────────────────────

    def _validate_wf(self, r_value: float) -> Dict[str, Any]:
        """Apply best R to walk-forward test set."""
        if len(self.test_events) < 5:
            return {
                "test_n": len(self.test_events),
                "applied": False,
                "reason": "Insufficient test events (< 5)",
            }

        # Re-run train for comparison
        train_result = self._simulate_r(self.train_events, r_value)
        test_result = self._simulate_r(self.test_events, r_value)

        return {
            "r_value": r_value,
            "train_n": train_result.n,
            "train_wr": round(train_result.win_rate, 4),
            "train_profit_factor": round(train_result.profit_factor, 2),
            "train_expectancy": round(train_result.expectancy, 4),
            "train_total_pnl": round(train_result.total_pnl, 2),
            "test_n": test_result.n,
            "test_wr": round(test_result.win_rate, 4),
            "test_profit_factor": round(test_result.profit_factor, 2),
            "test_expectancy": round(test_result.expectancy, 4),
            "test_total_pnl": round(test_result.total_pnl, 2),
            "persistent": (
                test_result.n >= 5
                and test_result.win_rate >= train_result.win_rate * 0.7
                and test_result.profit_factor >= train_result.profit_factor * 0.7
                and test_result.expectancy > 0
            ),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Integration helper — filter events for bounce follow-through hypotheses
# ═══════════════════════════════════════════════════════════════════════════════

def filter_bounce_events(df: pd.DataFrame, min_confirm_bars: int = 1,
                         max_lookback_bars: int = 3,
                         candles_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Filter events to those that pass bounce follow-through pre-checks.
    Replicates the filtering logic from _BounceFollowThroughParam.evaluate().
    Returns DataFrame with only qualifying events.

    Uses timestamp-based candle lookup to handle mismatch between
    events.bar_index (global) and candles.csv row index.
    """
    bounces = df[df['Type'].isin(['SUPPORT_BOUNCE', 'RESISTANCE_REJECTION'])].copy()
    if bounces.empty:
        return bounces

    # Build candle lookup by sequential index (row number)
    candle_lookup = {}
    ts_to_candle_idx = {}  # timestamp -> sequential candle index
    if candles_df is not None and len(candles_df) > 0:
        for idx, c in candles_df.iterrows():
            candle_data = {
                'open': float(c.get('open', c.get('Open', 0))),
                'close': float(c.get('close', c.get('Close', 0))),
                'high': float(c.get('high', c.get('High', 0))),
                'low': float(c.get('low', c.get('Low', 0))),
            }
            candle_lookup[idx] = candle_data
            ts = c.get('timestamp', c.get('time', None))
            if ts is not None:
                ts_to_candle_idx[int(float(ts))] = idx

    keep = []
    for _, row in bounces.iterrows():
        details = str(row.get("Details", ""))
        m = re.search(r'T\+(\d+)', details)
        t_delay = int(m.group(1)) if m else 0

        if t_delay < min_confirm_bars:
            continue
        if t_delay > max_lookback_bars:
            continue

        if candle_lookup and ts_to_candle_idx:
            # Use timestamp-based lookup to find confirmation candle
            raw_ts = int(float(row.get('Raw_Timestamp', row.get('Timestamp', 0))))
            conf_idx = ts_to_candle_idx.get(raw_ts)
            if conf_idx is None:
                continue

            # Test candle is t_delay bars before confirmation
            test_idx = conf_idx - t_delay
            conf = candle_lookup.get(conf_idx)
            test = candle_lookup.get(test_idx)
            if conf is None or test is None:
                continue

            etype = str(row.get("Type", ""))
            if etype == 'SUPPORT_BOUNCE':
                if conf['close'] <= conf['open']:
                    continue
                if conf['close'] <= test['close']:
                    continue
            elif etype == 'RESISTANCE_REJECTION':
                if conf['close'] >= conf['open']:
                    continue
                if conf['close'] >= test['close']:
                    continue

        keep.append(row.name)

    return bounces.loc[keep]
