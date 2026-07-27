from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd

from analysis.rsi_line_policy import (
    AdjacentAnchorPolicy,
    CollinearExtendAnchorPolicy,
    NearestPairAnchorPolicy,
    WalkBackAnchorPolicy,
)
from analysis.rsi_pivots import compute_rsi_series
from analysis.rsi_pivots import GeometryParams
from analysis.rsi_sweep import run_causal_sweep
from analysis.signal_trade_simulator import CandleSignal, simulate_trade_grid
from analysis.strategy_analyzer import Hypothesis

POLICIES = {
    "collinear_extend": CollinearExtendAnchorPolicy,
    "adjacent": AdjacentAnchorPolicy,
    "walk_back": WalkBackAnchorPolicy,
    "nearest_pair": NearestPairAnchorPolicy,
}


def swing_stop_price(
    candles: pd.DataFrame, bar_index: int, side: str, lookback: int, buffer: float
) -> float:
    """Stop at the nearest price swing extreme, per the strategy guide.

    Deliberately NOT the breakout candle's own low/high: entering at a candle's
    close with a stop at that same candle's extreme gives a stop ~0.2% of price
    away, which noise removes before the thesis resolves.
    """
    start = max(0, bar_index - lookback)
    window = candles.iloc[start : bar_index + 1]
    if side == "LONG":
        return float(window["low"].min()) * (1.0 - buffer)
    return float(window["high"].max()) * (1.0 + buffer)


class RSITrendlineBreakHypothesis(Hypothesis):
    def __init__(self):
        super().__init__(
            name="RSI Trendline Break Strategy",
            description="Causal RSI trendline breaks filtered by price vs SMA(200).",
        )
        self.set_parameters(
            rsi_period=14,
            sma_period=200,
            anchor_policy="collinear_extend",
            pivot_left_bars=2,
            pivot_right_bars=2,
            min_swing=2.0,
            tolerance=5.0,
            min_line_length=5,
            max_span_bars=150,
            swing_lookback=20,
            stop_buffer=0.0005,
            r_values=[1.0, 1.5, 2.0, 2.5, 3.0],
            max_hold_bars=40,
        )

    # ------------------------------------------------------------------ #

    def evaluate(self, df: pd.DataFrame, candles_df: pd.DataFrame = None) -> Dict[str, Any]:
        if candles_df is None or candles_df.empty:
            return self._empty_result()

        candles = candles_df.copy().reset_index(drop=True)
        if "bar_index" not in candles.columns:
            candles["bar_index"] = candles.index

        period = int(self.parameters["rsi_period"])
        sma_period = int(self.parameters["sma_period"])
        candles["rsi"] = compute_rsi_series(candles["close"], period=period)
        candles["sma"] = candles["close"].rolling(sma_period, min_periods=sma_period).mean()

        params = GeometryParams(
            left_bars=int(self.parameters["pivot_left_bars"]),
            right_bars=int(self.parameters["pivot_right_bars"]),
            min_swing=float(self.parameters["min_swing"]),
            tolerance=float(self.parameters["tolerance"]),
            min_length=int(self.parameters["min_line_length"]),
            max_span_bars=int(self.parameters["max_span_bars"]),
        )
        policy = POLICIES[str(self.parameters["anchor_policy"])]()
        sweep = run_causal_sweep(candles["rsi"], policy, params)

        segments_by_id = {segment.segment_id: segment for segment in sweep.segments}
        last_bar = int(candles["bar_index"].max())

        skipped = {
            "trend_filter": 0,
            "warmup": 0,
            "invalid_risk": 0,
            "last_bar": 0,
            "missing_candle": 0,
        }
        candidates: List[Dict[str, Any]] = []

        for signal in sweep.signals:
            match = candles.loc[candles["bar_index"] == signal.bar_index]
            if match.empty:
                skipped["missing_candle"] += 1
                continue

            row = match.iloc[0]
            if signal.bar_index >= last_bar:
                skipped["last_bar"] += 1
                continue

            sma_value = row["sma"]
            if pd.isna(sma_value):
                skipped["warmup"] += 1
                continue

            close_price = float(row["close"])
            if signal.side == "LONG" and not close_price > float(sma_value):
                skipped["trend_filter"] += 1
                continue
            if signal.side == "SHORT" and not close_price < float(sma_value):
                skipped["trend_filter"] += 1
                continue

            stop_price = swing_stop_price(
                candles,
                bar_index=int(signal.bar_index),
                side=signal.side,
                lookback=int(self.parameters["swing_lookback"]),
                buffer=float(self.parameters["stop_buffer"]),
            )
            if signal.side == "LONG" and stop_price >= close_price:
                skipped["invalid_risk"] += 1
                continue
            if signal.side == "SHORT" and stop_price <= close_price:
                skipped["invalid_risk"] += 1
                continue

            candidates.append(
                {
                    "signal": CandleSignal(
                        bar_index=int(signal.bar_index),
                        side=signal.side,
                        entry_price=close_price,
                        stop_price=stop_price,
                        signal_time=self._time_string(row.get("time")),
                    ),
                    "detail": self._detail_record(
                        row=row,
                        signal=signal,
                        segment=segments_by_id[signal.segment_id],
                        stop_price=stop_price,
                        candles=candles,
                    ),
                }
            )

        rsi_series = self._rsi_series_payload(candles)
        line_timeline = self._timeline_payload(sweep.segments, candles)

        if not candidates:
            return self._empty_result(
                rsi_series=rsi_series, line_timeline=line_timeline, skipped=skipped
            )

        exit_optimization = simulate_trade_grid(
            candles=candles,
            signals=[c["signal"] for c in candidates],
            r_values=self.parameters["r_values"],
            max_hold_bars=int(self.parameters["max_hold_bars"]),
        )
        best = exit_optimization.get("best") or {}
        best_r = best.get("r_value")
        per_signal = exit_optimization.get("per_signal", {})

        detailed_log: List[Dict[str, Any]] = []
        for index, candidate in enumerate(candidates):
            trade = per_signal.get(f"{candidate['signal'].bar_index}:{index}")
            if trade is None:
                continue
            entry = dict(candidate["detail"])
            entry.update(
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
            detailed_log.append(entry)

        return self._summarize(
            detailed_log=detailed_log,
            exit_optimization=exit_optimization,
            rsi_series=rsi_series,
            line_timeline=line_timeline,
            skipped=skipped,
        )

    # ------------------------------------------------------------------ #

    @staticmethod
    def _time_string(value: Any) -> str | None:
        if value is None or (not isinstance(value, pd.Timestamp) and pd.isna(value)):
            return None
        if isinstance(value, pd.Timestamp):
            return value.strftime("%Y-%m-%dT%H:%M:%S")
        return str(value)

    def _bar_time(self, candles: pd.DataFrame, bar_index: int) -> str | None:
        if "time" not in candles.columns:
            return None
        match = candles.loc[candles["bar_index"] == bar_index, "time"]
        if match.empty:
            return None
        return self._time_string(match.iloc[0])

    @staticmethod
    def _event_time_fields(time_value: Any, fallback_bar_index: int) -> Dict[str, Any]:
        timestamp = fallback_bar_index
        if time_value is not None and not (
            not isinstance(time_value, pd.Timestamp) and pd.isna(time_value)
        ):
            if isinstance(time_value, pd.Timestamp):
                timestamp = int(time_value.timestamp())
            elif isinstance(time_value, str):
                timestamp = int(pd.Timestamp(time_value).timestamp())
            else:
                timestamp = int(time_value)
        return {
            "time": datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
            "timestamp": timestamp,
        }

    def _anchor_payload(self, pivot, candles: pd.DataFrame) -> Dict[str, Any]:
        return {
            "bar_index": int(pivot.bar_index),
            "rsi": float(pivot.rsi_value),
            "kind": pivot.kind,
            "time": self._bar_time(candles, int(pivot.bar_index)),
        }

    def _detail_record(self, row, signal, segment, stop_price, candles) -> Dict[str, Any]:
        event_time = self._event_time_fields(
            row["time"] if "time" in row.index else None, int(signal.bar_index)
        )
        return {
            "time": event_time["time"],
            "timestamp": event_time["timestamp"],
            "type": f"RSI_TRENDLINE_BREAK_{signal.side}",
            "bar_index": int(signal.bar_index),
            "direction": signal.side,
            "entry_side": signal.side,
            "entry_price": float(row["close"]),
            "price": float(row["close"]),
            "stop_price": float(stop_price),
            "stop_rule": "swing_extreme",
            "swing_lookback": int(self.parameters["swing_lookback"]),
            "is_retro": False,
            "trend_filter_passed": True,
            "sma_period": int(self.parameters["sma_period"]),
            "sma_value": float(row["sma"]),
            "rsi_period": int(self.parameters["rsi_period"]),
            "rsi_value": float(signal.rsi_value),
            "segment_id": int(segment.segment_id),
            "line_direction": segment.line.direction,
            "line_start_bar_index": int(segment.line.start_bar_index),
            "line_end_bar_index": int(segment.line.end_bar_index),
            "line_start_rsi": float(segment.line.start_rsi),
            "line_end_rsi": float(segment.line.end_rsi),
            "line_slope": float(segment.line.slope),
            "line_value_at_break": float(signal.line_value_at_break),
            "touch_count": int(segment.touch_count),
            "pivot_a_bar_index": int(segment.anchor_a.bar_index),
            "pivot_a_rsi": float(segment.anchor_a.rsi_value),
            "pivot_a_kind": segment.anchor_a.kind,
            "pivot_a_time": self._bar_time(candles, int(segment.anchor_a.bar_index)),
            "pivot_b_bar_index": int(segment.anchor_b.bar_index),
            "pivot_b_rsi": float(segment.anchor_b.rsi_value),
            "pivot_b_kind": segment.anchor_b.kind,
            "pivot_b_time": self._bar_time(candles, int(segment.anchor_b.bar_index)),
        }

    def _rsi_series_payload(self, candles: pd.DataFrame) -> List[Dict[str, Any]]:
        if "time" not in candles.columns:
            return []
        payload = []
        for _, row in candles.iterrows():
            value = row.get("rsi")
            if pd.isna(value):
                continue
            payload.append(
                {
                    "bar_index": int(row["bar_index"]),
                    "time": self._time_string(row["time"]),
                    "rsi": float(value),
                }
            )
        return payload

    def _timeline_payload(self, segments, candles: pd.DataFrame) -> List[Dict[str, Any]]:
        payload = []
        for segment in segments:
            payload.append(
                {
                    "segment_id": int(segment.segment_id),
                    "direction": segment.line.direction,
                    "valid_from_bar": int(segment.valid_from_bar),
                    "valid_to_bar": int(segment.valid_to_bar),
                    "valid_from_time": self._bar_time(candles, int(segment.valid_from_bar)),
                    "valid_to_time": self._bar_time(candles, int(segment.valid_to_bar)),
                    "end_reason": segment.end_reason,
                    "slope": float(segment.line.slope),
                    "touch_count": int(segment.touch_count),
                    "anchor_a": self._anchor_payload(segment.anchor_a, candles),
                    "anchor_b": self._anchor_payload(segment.anchor_b, candles),
                }
            )
        return payload

    @staticmethod
    def _summarize(
        detailed_log, exit_optimization, rsi_series, line_timeline, skipped
    ) -> Dict[str, Any]:
        n = len(detailed_log)
        wins = sum(1 for entry in detailed_log if entry.get("outcome") == "WIN")
        total = round(sum(float(e.get("net_pnl", 0.0)) for e in detailed_log), 6)
        average = round(total / n, 6) if n else 0.0

        return {
            "sample_size": n,
            "win_rate": round(wins / n, 4) if n else 0.0,
            "live_sample_size": n,
            "live_win_rate": round(wins / n, 4) if n else 0.0,
            "retro_sample_size": 0,
            "retro_win_rate": 0.0,
            "avg_mfe_10": 0.0,
            "avg_mae_10": 0.0,
            "avg_net_pnl": average,
            "net_pnl_total": total,
            "composite": average * (n ** 0.5) if n else 0.0,
            "groups": {},
            "detailed_log": detailed_log,
            "exit_optimization": exit_optimization,
            "trade_scored": True,
            "rsi_series": rsi_series,
            "line_timeline": line_timeline,
            "skipped": skipped,
        }

    def _empty_result(self, rsi_series=None, line_timeline=None, skipped=None) -> Dict[str, Any]:
        return self._summarize(
            detailed_log=[],
            exit_optimization={"best": None, "all_r_results": [], "per_signal": {}},
            rsi_series=rsi_series or [],
            line_timeline=line_timeline or [],
            skipped=skipped
            or {
                "trend_filter": 0, "warmup": 0, "invalid_risk": 0,
                "last_bar": 0, "missing_candle": 0,
            },
        )
