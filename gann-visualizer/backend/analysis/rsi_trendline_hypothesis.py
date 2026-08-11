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
            r_values=[1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0],
            max_hold_bars=40,
            # --- execution model -------------------------------------- #
            # The break is only knowable once its bar has closed, so the
            # earliest honest fill is the NEXT bar's open. Entering at the
            # signal bar's close is a ~1-bar advantage on every trade.
            entry_offset=1,
            # Binance USD-M futures. Fees are not a rounding error here: the
            # stop sits ~0.7% away and a taker round trip costs 0.08%, so
            # ~11% of the risk on every trade is fees.
            fee_rate=0.0004,
            maker_fee_rate=0.0002,
            slippage_per_side=0.0,
            # R must be declared in advance. Left None, the headline becomes
            # whichever R won in hindsight -- a choice unavailable live.
            selected_r=3.0,
        )

    # ------------------------------------------------------------------ #

    def prepare(self, candles_df: pd.DataFrame) -> Dict[str, Any]:
        """Indicators, geometry sweep, and the bar lookups, with no trade logic.

        Split out of ``evaluate`` so a research harness can take the same
        prepared state and feed the entry rule a *different* list of breaks --
        which is what the placebo gate needs -- without reimplementing any of
        it.
        """
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

        # One pass to build the lookups every payload helper needs, instead of
        # a full-frame boolean scan per signal and per segment anchor.
        self._time_by_bar = (
            {int(b): self._time_string(t)
             for b, t in zip(candles["bar_index"], candles["time"])}
            if "time" in candles.columns else {}
        )

        return {
            "candles": candles,
            "sweep": sweep,
            "row_by_bar": {int(b): i for i, b in enumerate(candles["bar_index"])},
            "last_bar": int(candles["bar_index"].max()),
        }

    def evaluate(self, df: pd.DataFrame, candles_df: pd.DataFrame = None) -> Dict[str, Any]:
        if candles_df is None or candles_df.empty:
            return self._empty_result()

        prepared = self.prepare(candles_df)
        candles = prepared["candles"]
        sweep = prepared["sweep"]
        row_by_bar = prepared["row_by_bar"]
        last_bar = prepared["last_bar"]
        segments_by_id = {segment.segment_id: segment for segment in sweep.segments}

        skipped = {
            "trend_filter": 0,
            "warmup": 0,
            "invalid_risk": 0,
            "last_bar": 0,
            "missing_candle": 0,
        }
        candidates: List[Dict[str, Any]] = []

        for signal in sweep.signals:
            entry, reason = self.entry_for_break(
                candles=candles,
                row_by_bar=row_by_bar,
                bar_index=int(signal.bar_index),
                side=signal.side,
                last_bar=last_bar,
            )
            if entry is None:
                skipped[reason] += 1
                continue

            candidates.append(
                {
                    "signal": entry,
                    "detail": self._detail_record(
                        row=candles.iloc[row_by_bar[int(signal.bar_index)]],
                        signal=signal,
                        segment=segments_by_id[signal.segment_id],
                        stop_price=entry.stop_price,
                        entry_price=entry.entry_price,
                        entry_bar_index=entry.entry_bar_index,
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

        selected_r = self.parameters.get("selected_r")
        exit_optimization = simulate_trade_grid(
            candles=candles,
            signals=[c["signal"] for c in candidates],
            r_values=self.parameters["r_values"],
            max_hold_bars=int(self.parameters["max_hold_bars"]),
            fee_rate=float(self.parameters["fee_rate"]),
            maker_fee_rate=float(self.parameters["maker_fee_rate"]),
            slippage_per_side=float(self.parameters["slippage_per_side"]),
            select_r=None if selected_r is None else float(selected_r),
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
                    "net_r": float(trade["net_r"]),
                    "fees": float(trade["fees"]),
                    "exit_is_maker": bool(trade["exit_is_maker"]),
                    "bars_held": int(trade["exit_bar_index"] - trade["entry_bar_index"]),
                    "outcome": trade["outcome"],
                    "trade_matched": True,
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

    def entry_for_break(
        self,
        candles: pd.DataFrame,
        row_by_bar: Dict[int, int],
        bar_index: int,
        side: str,
        last_bar: int,
    ):
        """Turn one RSI break into a tradeable signal, or say why not.

        Public so the placebo harness can feed it *shifted* break bars and
        still exercise exactly the entry rule that ships. Duplicating this
        logic in a research script is how the 2026-07-27 placebo ended up
        testing a configuration the strategy never used.

        Returns ``(CandleSignal, None)`` or ``(None, skip_reason)``.
        """
        row_position = row_by_bar.get(int(bar_index))
        if row_position is None:
            return None, "missing_candle"

        row = candles.iloc[row_position]
        entry_offset = int(self.parameters["entry_offset"])
        entry_bar_index = int(bar_index) + entry_offset
        if entry_bar_index >= last_bar:
            return None, "last_bar"

        sma_value = row["sma"]
        if pd.isna(sma_value):
            return None, "warmup"

        close_price = float(row["close"])
        if side == "LONG" and not close_price > float(sma_value):
            return None, "trend_filter"
        if side == "SHORT" and not close_price < float(sma_value):
            return None, "trend_filter"

        entry_price = self._entry_price(candles, int(bar_index), entry_offset)
        if entry_price is None:
            return None, "missing_candle"

        # The stop is derived from the signal bar's own lookback window --
        # what the trader could see when the break printed -- not from the
        # entry bar, which has not opened yet at decision time.
        stop_price = swing_stop_price(
            candles,
            bar_index=int(bar_index),
            side=side,
            lookback=int(self.parameters["swing_lookback"]),
            buffer=float(self.parameters["stop_buffer"]),
        )
        if side == "LONG" and stop_price >= entry_price:
            return None, "invalid_risk"
        if side == "SHORT" and stop_price <= entry_price:
            return None, "invalid_risk"

        return CandleSignal(
            bar_index=int(bar_index),
            side=side,
            entry_price=entry_price,
            stop_price=stop_price,
            signal_time=self._time_string(row.get("time")),
            entry_bar_index=entry_bar_index,
        ), None

    @staticmethod
    def _time_string(value: Any) -> str | None:
        if value is None or (not isinstance(value, pd.Timestamp) and pd.isna(value)):
            return None
        if isinstance(value, pd.Timestamp):
            return value.strftime("%Y-%m-%dT%H:%M:%S")
        return str(value)

    def _bar_time(self, candles: pd.DataFrame, bar_index: int) -> str | None:
        """Time for a bar, via the index built in ``evaluate``.

        The obvious ``candles.loc[candles["bar_index"] == bar]`` is a full
        boolean scan of the frame. It is called once per segment anchor, so on
        a multi-year series it was the single most expensive thing the
        hypothesis did -- half its total runtime.
        """
        cached = getattr(self, "_time_by_bar", None)
        if cached is not None:
            return cached.get(int(bar_index))
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

    @staticmethod
    def _entry_price(candles: pd.DataFrame, bar_index: int, entry_offset: int):
        """Signal-bar close at offset 0, otherwise the offset bar's OPEN."""
        if entry_offset == 0:
            match = candles.loc[candles["bar_index"] == bar_index, "close"]
            return float(match.iloc[0]) if not match.empty else None
        column = "open" if "open" in candles.columns else "close"
        match = candles.loc[candles["bar_index"] == bar_index + entry_offset, column]
        return float(match.iloc[0]) if not match.empty else None

    def _detail_record(
        self, row, signal, segment, stop_price, entry_price, entry_bar_index, candles
    ) -> Dict[str, Any]:
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
            "entry_price": float(entry_price),
            "entry_bar_index": int(entry_bar_index),
            "entry_time": self._bar_time(candles, int(entry_bar_index)),
            "entry_offset": int(self.parameters["entry_offset"]),
            "signal_close": float(row["close"]),
            "price": float(entry_price),
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
        """One dict per bar. Zipped columns, not ``iterrows`` -- the latter
        rebuilds a Series per row and cost a second on its own."""
        if "time" not in candles.columns:
            return []
        bars = candles["bar_index"].to_numpy()
        values = candles["rsi"].to_numpy(dtype=float)
        times = candles["time"].tolist()
        return [
            {
                "bar_index": int(bars[i]),
                "time": self._time_string(times[i]),
                "rsi": float(values[i]),
            }
            for i in range(len(bars))
            if not pd.isna(values[i])
        ]

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

        # R-multiples, because price-unit totals cannot be pooled across a
        # 60,000-dollar BTC and a 24,000-point index.
        r_values = [float(e.get("net_r", 0.0)) for e in detailed_log]
        won = [r for r in r_values if r > 0]
        lost = [-r for r in r_values if r < 0]
        gross_win, gross_loss = sum(won), sum(lost)

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
            "expectancy_r": round(sum(r_values) / n, 6) if n else 0.0,
            "total_r": round(sum(r_values), 6),
            "profit_factor": (
                round(gross_win / gross_loss, 6) if gross_loss else 0.0
            ),
            "avg_win_r": round(gross_win / len(won), 6) if won else 0.0,
            "avg_loss_r": round(gross_loss / len(lost), 6) if lost else 0.0,
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
