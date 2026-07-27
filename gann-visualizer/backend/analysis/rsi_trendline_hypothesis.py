from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd

from analysis.rsi_geometry import (
    DeterministicPivotLineBuilder,
    RSIBreakSignal,
    compute_rsi_series,
    detect_rsi_line_breaks,
    detect_rsi_pivots,
)
from analysis.signal_trade_simulator import CandleSignal, simulate_trade_grid
from analysis.strategy_analyzer import Hypothesis


class RSITrendlineBreakHypothesis(Hypothesis):
    def __init__(self):
        super().__init__(
            name="RSI Trendline Break Strategy",
            description="Trade-scored RSI trendline breaks filtered by price vs SMA(200).",
        )
        self.set_parameters(
            rsi_period=14,
            sma_period=200,
            pivot_left_bars=2,
            pivot_right_bars=2,
            min_swing=3.0,
            structural_tolerance=3.0,
            min_line_length=8,
            max_slope=1.0,
            rsi_window_bars=40,
            r_values=[1.0, 1.5, 2.0, 2.5, 3.0],
            max_hold_bars=10,
        )

    def evaluate(self, df: pd.DataFrame, candles_df: pd.DataFrame = None) -> Dict[str, Any]:
        if candles_df is None or candles_df.empty:
            return self._empty_result()

        candles = self._prepare_candles(candles_df)
        candles["rsi"] = compute_rsi_series(candles["close"], period=int(self.parameters["rsi_period"]))
        candles["sma"] = candles["close"].rolling(
            window=int(self.parameters["sma_period"]),
            min_periods=int(self.parameters["sma_period"]),
        ).mean()

        pivots = detect_rsi_pivots(
            candles["rsi"],
            left_bars=int(self.parameters["pivot_left_bars"]),
            right_bars=int(self.parameters["pivot_right_bars"]),
            min_swing=float(self.parameters["min_swing"]),
        )
        builder = DeterministicPivotLineBuilder()
        # Build pivot-to-pivot lines (used for break detection of event
        # lines) — these define the *event* line geometry: any pivot
        # pair that passes the structural checks is a candidate line
        # that the RSI curve could break through.
        lines = builder.build_lines(
            pivots,
            rsi=candles["rsi"],
            structural_tolerance=float(self.parameters["structural_tolerance"]),
            min_length=int(self.parameters["min_line_length"]),
            max_slope=float(self.parameters["max_slope"]),
        )
        # OLS best-fit lines via RANSAC — these are the *display* lines
        # (3 per direction max) that the user sees on the chart.  Break
        # detection now runs against these so the trade signal fires
        # when RSI crosses the same line the user sees.
        display_max_slope = min(0.5, float(self.parameters["max_slope"]))
        best_fit_lines = builder.build_best_fit_lines(
            pivots,
            rsi=candles["rsi"],
            structural_tolerance=float(self.parameters["structural_tolerance"]),
            min_length=int(self.parameters["min_line_length"]),
            max_slope=display_max_slope,
        )
        # Use the best-fit lines for break detection — combine with
        # original pivot-to-pivot lines so we don't miss any.
        combined_lines = list(best_fit_lines) + list(lines)
        breaks = detect_rsi_line_breaks(
            candles=candles,
            rsi=candles["rsi"],
            lines=combined_lines,
            window_bars=int(self.parameters["rsi_window_bars"]),
        )

        line_lookup = {
            (line.start_bar_index, line.end_bar_index, line.direction): line for line in lines
        }
        pivot_lookup = {pivot.bar_index: pivot for pivot in pivots}

        candidate_payloads: List[Dict[str, Any]] = []
        last_bar_index = int(candles["bar_index"].max())

        for signal in breaks:
            candle = candles.loc[candles["bar_index"] == signal.bar_index]
            if candle.empty:
                continue

            row = candle.iloc[0]
            close_price = float(row["close"])
            sma_value = row["sma"]
            trend_filter_passed = self._passes_trend_filter(
                direction=signal.direction,
                close_price=close_price,
                sma_value=sma_value,
            )

            if not trend_filter_passed:
                continue
            if int(signal.bar_index) >= last_bar_index:
                continue

            stop_price = float(row["low"]) if signal.direction == "LONG" else float(row["high"])
            if stop_price == close_price:
                continue

            line = line_lookup.get(
                (signal.line.start_bar_index, signal.line.end_bar_index, signal.line.direction),
                signal.line,
            )
            pivot_a = pivot_lookup.get(line.start_bar_index)
            pivot_b = pivot_lookup.get(line.end_bar_index)

            candidate_payloads.append(
                {
                    "signal": CandleSignal(
                        bar_index=int(signal.bar_index),
                        side=signal.direction,
                        entry_price=close_price,
                        stop_price=stop_price,
                        signal_time=row["time"] if "time" in row.index else int(signal.bar_index),
                    ),
                    "detail": self._build_detail_record(
                        row=row,
                        signal=signal,
                        line=line,
                        pivot_a=pivot_a,
                        pivot_b=pivot_b,
                        trend_filter_passed=trend_filter_passed,
                        stop_price=stop_price,
                        candles=candles,
                    ),
                }
            )

        if not candidate_payloads:
            return self._empty_result()

        exit_optimization = simulate_trade_grid(
            candles=candles,
            signals=[payload["signal"] for payload in candidate_payloads],
            r_values=self.parameters["r_values"],
            max_hold_bars=int(self.parameters["max_hold_bars"]),
        )

        best = exit_optimization.get("best")
        best_r = best.get("r_value") if best else None
        per_signal = exit_optimization.get("per_signal", {})

        detailed_log: List[Dict[str, Any]] = []
        for signal_index, payload in enumerate(candidate_payloads):
            signal = payload["signal"]
            detail = dict(payload["detail"])
            signal_key = f"{signal.bar_index}:{signal_index}"
            trade = per_signal.get(signal_key)
            if trade is None:
                continue

            detail.update(
                {
                    "best_r": best_r,
                    "target_price": float(trade["target_price"]),
                    "risk_per_unit": float(trade["risk_per_unit"]),
                    "exit_bar_index": int(trade["exit_bar_index"]),
                    "exit_time": trade.get("exit_time"),
                    "exit_price": float(trade["exit_price"]),
                    "exit_reason": trade["exit_reason"],
                    "gross_pnl": float(trade["gross_pnl"]),
                    "net_pnl": float(trade["net_pnl"]),
                    "fees": float(trade["fees"]),
                    "bars_held": int(trade["exit_bar_index"] - trade["bar_index"]),
                    "outcome": trade["outcome"],
                }
            )
            detailed_log.append(detail)

        # Build full RSI series for all candles (for price-pane overlay)
        def _bar_time(bar_index: int) -> str:
            if "time" not in candles.columns:
                return None
            match = candles.loc[candles["bar_index"] == bar_index, "time"]
            if match.empty:
                return None
            tv = match.iloc[0]
            if tv is None or pd.isna(tv):
                return None
            if isinstance(tv, pd.Timestamp):
                return tv.strftime("%Y-%m-%dT%H:%M:%S")
            return str(tv)

        rsi_series_raw = []
        if "time" in candles.columns:
            for _, crow in candles.iterrows():
                rsi_val = crow.get("rsi")
                if pd.isna(rsi_val):
                    continue
                bar_idx = int(crow["bar_index"])
                tv = crow["time"]
                if isinstance(tv, pd.Timestamp):
                    time_str = tv.strftime("%Y-%m-%dT%H:%M:%S")
                else:
                    time_str = str(tv)
                rsi_series_raw.append({
                    "bar_index": bar_idx,
                    "time": time_str,
                    "rsi": float(rsi_val),
                })

        # Build all active RSI lines with pivot data and timestamps
        # Combine event lines + best-fit cluster lines (the latter use a
        # marker so the frontend can distinguish them, but they share the
        # same display format)
        all_rsi_lines = []
        seen_keys: set = set()

        # Best-fit lines first so they win display priority by score
        for l in best_fit_lines:
            key = ("bestfit", int(l.start_bar_index), int(l.end_bar_index), l.direction)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            a_bar = int(l.start_bar_index)
            b_bar = int(l.end_bar_index)
            all_rsi_lines.append({
                "start_bar_index": a_bar,
                "end_bar_index": b_bar,
                "start_rsi": float(l.start_rsi),
                "end_rsi": float(l.end_rsi),
                "direction": l.direction,
                "score": float(l.score),
                "kind": "best_fit",
                "pivot_a": {
                    "bar_index": a_bar,
                    "rsi": float(l.start_rsi),
                    "kind": "high" if l.direction == "down" else "low",
                    "time": _bar_time(a_bar),
                },
                "pivot_b": {
                    "bar_index": b_bar,
                    "rsi": float(l.end_rsi),
                    "kind": "high" if l.direction == "down" else "low",
                    "time": _bar_time(b_bar),
                },
            })

        for l in lines:
            p_a = pivot_lookup.get(l.start_bar_index)
            p_b = pivot_lookup.get(l.end_bar_index)
            a_bar = int(p_a.bar_index) if p_a else int(l.start_bar_index)
            b_bar = int(p_b.bar_index) if p_b else int(l.end_bar_index)
            key = ("event", a_bar, b_bar, l.direction)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            all_rsi_lines.append({
                "start_bar_index": int(l.start_bar_index),
                "end_bar_index": int(l.end_bar_index),
                "start_rsi": float(l.start_rsi),
                "end_rsi": float(l.end_rsi),
                "direction": l.direction,
                "score": float(l.score),
                "pivot_a": {
                    "bar_index": a_bar,
                    "rsi": float(p_a.rsi_value) if p_a else float(l.start_rsi),
                    "kind": p_a.kind if p_a else ("high" if l.direction == "down" else "low"),
                    "time": _bar_time(a_bar),
                },
                "pivot_b": {
                    "bar_index": b_bar,
                    "rsi": float(p_b.rsi_value) if p_b else float(l.end_rsi),
                    "kind": p_b.kind if p_b else ("high" if l.direction == "down" else "low"),
                    "time": _bar_time(b_bar),
                },
            })

        return self._summarize_result(detailed_log, exit_optimization, rsi_series_raw, all_rsi_lines)

    @staticmethod
    def _prepare_candles(candles_df: pd.DataFrame) -> pd.DataFrame:
        candles = candles_df.copy().reset_index(drop=True)
        if "bar_index" not in candles.columns:
            candles["bar_index"] = candles.index
        return candles

    @staticmethod
    def _passes_trend_filter(direction: str, close_price: float, sma_value: Any) -> bool:
        if pd.isna(sma_value):
            return False
        if direction == "LONG":
            return close_price > float(sma_value)
        return close_price < float(sma_value)

    @staticmethod
    def _event_time_fields(time_value: Any, fallback_bar_index: int) -> Dict[str, Any]:
        timestamp = fallback_bar_index

        if time_value is not None and not pd.isna(time_value):
            if isinstance(time_value, pd.Timestamp):
                timestamp = int(time_value.timestamp())
            elif hasattr(time_value, "timestamp") and not isinstance(time_value, (int, float, str)):
                timestamp = int(time_value.timestamp())
            elif isinstance(time_value, str):
                timestamp = int(pd.Timestamp(time_value).timestamp())
            else:
                timestamp = int(time_value)

        return {
            "time": datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "timestamp": timestamp,
        }

    def _build_detail_record(
        self,
        row: pd.Series,
        signal: RSIBreakSignal,
        line,
        pivot_a,
        pivot_b,
        trend_filter_passed: bool,
        stop_price: float,
        candles: pd.DataFrame = None,
    ) -> Dict[str, Any]:
        direction = str(signal.direction).upper()
        event_time = self._event_time_fields(
            time_value=row["time"] if "time" in row.index else None,
            fallback_bar_index=int(signal.bar_index),
        )

        def _pivot_time(bar_index: int) -> str:
            if candles is None or "time" not in candles.columns:
                return None
            match = candles.loc[candles["bar_index"] == bar_index, "time"]
            if match.empty:
                return None
            tv = match.iloc[0]
            if tv is None or pd.isna(tv):
                return None
            if isinstance(tv, pd.Timestamp):
                return tv.strftime("%Y-%m-%dT%H:%M:%S")
            return str(tv)

        return {
            "time": event_time["time"],
            "timestamp": event_time["timestamp"],
            "type": f"RSI_TRENDLINE_BREAK_{direction}",
            "bar_index": int(signal.bar_index),
            "direction": direction,
            "entry_price": float(row["close"]),
            "price": float(row["close"]),
            "stop_price": float(stop_price),
            "is_retro": False,
            "trend_filter_passed": trend_filter_passed,
            "sma_period": int(self.parameters["sma_period"]),
            "sma_value": float(row["sma"]),
            "rsi_period": int(self.parameters["rsi_period"]),
            "rsi_value": float(signal.rsi_value),
            "rsi_window": signal.rsi_window,
            "line_direction": line.direction,
            "line_start_bar_index": int(line.start_bar_index),
            "line_end_bar_index": int(line.end_bar_index),
            "line_start_rsi": float(line.start_rsi),
            "line_end_rsi": float(line.end_rsi),
            "line_value_at_break": float(signal.line_value_at_break),
            "pivot_a_bar_index": int(pivot_a.bar_index) if pivot_a is not None else int(line.start_bar_index),
            "pivot_a_rsi": float(pivot_a.rsi_value) if pivot_a is not None else float(line.start_rsi),
            "pivot_a_kind": pivot_a.kind if pivot_a is not None else ("high" if line.direction == "down" else "low"),
            "pivot_a_time": _pivot_time(int(pivot_a.bar_index)) if pivot_a is not None else _pivot_time(int(line.start_bar_index)),
            "pivot_b_bar_index": int(pivot_b.bar_index) if pivot_b is not None else int(line.end_bar_index),
            "pivot_b_rsi": float(pivot_b.rsi_value) if pivot_b is not None else float(line.end_rsi),
            "pivot_b_kind": pivot_b.kind if pivot_b is not None else ("high" if line.direction == "down" else "low"),
            "pivot_b_time": _pivot_time(int(pivot_b.bar_index)) if pivot_b is not None else _pivot_time(int(line.end_bar_index)),
        }

    @staticmethod
    def _summarize_result(
        detailed_log: List[Dict[str, Any]],
        exit_optimization: Dict[str, Any],
        rsi_series: list = None,
        all_rsi_lines: list = None,
    ) -> Dict[str, Any]:
        n = len(detailed_log)
        wins = sum(1 for entry in detailed_log if entry.get("outcome") == "WIN")
        total_net_pnl = round(sum(float(entry.get("net_pnl", 0.0)) for entry in detailed_log), 6)
        avg_net_pnl = round(total_net_pnl / n, 6) if n else 0.0

        result = {
            "sample_size": n,
            "win_rate": round(wins / n, 4) if n else 0.0,
            "live_sample_size": n,
            "live_win_rate": round(wins / n, 4) if n else 0.0,
            "retro_sample_size": 0,
            "retro_win_rate": 0.0,
            "avg_mfe_10": 0.0,
            "avg_mae_10": 0.0,
            "avg_net_pnl": avg_net_pnl,
            "net_pnl_total": total_net_pnl,
            "composite": avg_net_pnl * (n ** 0.5) if n else 0.0,
            "groups": {},
            "detailed_log": detailed_log,
            "exit_optimization": exit_optimization,
            "trade_scored": True,
        }
        if rsi_series:
            result["rsi_series"] = rsi_series
        if all_rsi_lines:
            result["all_rsi_lines"] = all_rsi_lines
        return result

    def _empty_result(self) -> Dict[str, Any]:
        return self._summarize_result(
            detailed_log=[],
            exit_optimization={"best": None, "all_r_results": [], "per_signal": {}},
        )
