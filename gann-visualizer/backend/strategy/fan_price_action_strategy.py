from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from study_tool.event_pipeline import PriceInteractionEvent, EventType, PipelineOutput
from analysis.target_progression import TargetProgression
from strategy.entry_detectors.base import BarContext, EntrySignal, MomentumContext
from strategy.entry_detectors.breach_retest import BreachRetestDetector
from strategy.entry_detectors.momentum_immediate import MomentumImmediateDetector
from strategy.entry_detectors.counter_directional import CounterDirectionalDetector
from strategy.entry_detectors.rejection_entry import RejectionEntryDetector


@dataclass
class ActiveTrade:
    detector_name: str
    fan_id: str
    fan_identity: str
    priority_label: str
    side: str
    entry_price: float
    entry_bar: int
    entry_time: int
    stop_price: float
    target: str
    entry_path: str = ""
    fraction: str = ""
    momentum: Optional[MomentumContext] = None
    anchor_type: str = ""
    fan_geometry: Optional[dict] = None
    progression_step: str = ""


class FanPriceActionStrategy:
    def __init__(self, progression: TargetProgression):
        self.progression = progression
        self.detectors = [
            BreachRetestDetector(),
            MomentumImmediateDetector(),
            CounterDirectionalDetector(),
            RejectionEntryDetector(),
        ]
        self.trades: Dict[str, List[Dict[str, Any]]] = {
            "BreachRetestDetector": [],
            "MomentumImmediateDetector": [],
            "CounterDirectionalDetector": [],
            "RejectionEntryDetector": [],
        }
        self.active_trades: Dict[str, Dict[str, ActiveTrade]] = {
            "BreachRetestDetector": {},
            "MomentumImmediateDetector": {},
            "CounterDirectionalDetector": {},
            "RejectionEntryDetector": {},
        }
        self.breached_setups: Dict[str, Dict[str, Any]] = {}

    def process_bar(
        self,
        pipeline_output: PipelineOutput,
        candles: List[Dict[str, Any]],
        bar_index: int,
        atr: float,
        momentum: MomentumContext,
        active_fans: Dict[str, Any] = None,
    ):
        self._active_fans = active_fans or {}
        self._candles = candles
        current_candle = candles[bar_index]
        bar_time = current_candle.get("time", 0)

        bar_ctx = BarContext(
            candles=candles,
            bar_index=bar_index,
            atr=atr,
            momentum=momentum,
            progression=self.progression,
            breached_setups=self.breached_setups,
        )

        for event in pipeline_output.events:
            self._handle_fan_lifecycle(event, bar_time)

            for detector in self.detectors:
                signal = detector.detect(event, bar_ctx)
                if signal:
                    self._open_trade(signal, bar_index, bar_time)

                if hasattr(detector, 'on_retest_event'):
                    retest_signal = detector.on_retest_event(event, bar_ctx)
                    if retest_signal:
                        self._open_trade(retest_signal, bar_index, bar_time)

            self._handle_exit_events(event, bar_index, bar_time, current_candle)

    def _handle_fan_lifecycle(self, event: PriceInteractionEvent, bar_time: int):
        if event.event_type == EventType.FAN_VALIDATED:
            fs = self.progression.get_fan_state(event.fan_id)
            if not fs:
                self.progression.register_fan(event.fan_id)
                self.progression.activate_fan(event.fan_id)

        if event.event_type == EventType.FAN_DEACTIVATED:
            self.progression.on_fan_deactivated(event.fan_id)
            self.progression.remove_fan(event.fan_id)
            for det_name in self.active_trades:
                self.active_trades[det_name].pop(event.fan_id, None)
            keys_to_remove = [
                k for k, v in self.breached_setups.items()
                if v.get("fan_id") == event.fan_id
            ]
            for k in keys_to_remove:
                del self.breached_setups[k]

    def _build_fan_geometry(self, fan_obj) -> Optional[dict]:
        """Extract fan geometry (origin, anchor, rays) from an AngleFan object.
        AngleFan uses from_pivot/to_pivot dicts with 'time' (Unix timestamp) and 'price'."""
        if not fan_obj:
            return None
        try:
            fp = getattr(fan_obj, 'from_pivot', {}) or {}
            tp = getattr(fan_obj, 'to_pivot', {}) or {}
            at = str(getattr(fan_obj, 'anchor_type', '')).upper()

            # Determine which pivot is origin (anchor) and which is the other
            if at == 'HIGH':
                # from_pivot is the HIGH anchor, to_pivot is the opposite
                origin = {"time": int(fp.get('time', 0)), "price": float(fp.get('price', 0)), "label": "high"}
                anchor = {"time": int(tp.get('time', 0)), "price": float(tp.get('price', 0)), "label": "low"}
            else:
                # from_pivot is the LOW anchor, to_pivot is the opposite
                origin = {"time": int(fp.get('time', 0)), "price": float(fp.get('price', 0)), "label": "low"}
                anchor = {"time": int(tp.get('time', 0)), "price": float(tp.get('price', 0)), "label": "high"}

            # Color/style scheme matching angle_engine.py create_fan():
            # Main angle: #808080 gray, width 2, dotted
            # 7/8 (0.875): #2196F3 blue, width 2, dotted
            # 3/4 (0.75):  #4CAF50 green, width 2, dotted
            # 1/2 (0.5):   #FF9800 orange, width 4, dotted
            # 1/4 (0.25):  #F44336 red, width 2, dotted
            # Horizontal:  #FFFFFF white, width 1, dotted
            FRACTION_COLORS = {
                None: ("#808080", 2),       # Main angle line (gray)
                0.875: ("#2196F3", 2),      # 7/8 (blue)
                0.75: ("#4CAF50", 2),       # 3/4 (green)
                0.5: ("#FF9800", 4),        # 1/2 (orange, thicker)
                0.25: ("#F44336", 2),       # 1/4 (red)
            }
            HORIZONTAL_COLOR = ("#FFFFFF", 1)  # White, thin

            main_line_count = 0
            rays = []
            for idx, line in enumerate(getattr(fan_obj, 'lines', [])):
                frac = getattr(line, 'fraction', None)
                base_id = f"{getattr(fan_obj, 'id', '?')}"

                # Distinguish multiple main/horizontal lines by index
                if frac is None:
                    ray_id = f"{base_id}_main_{main_line_count}"
                    main_line_count += 1
                else:
                    ray_id = f"{base_id}_{frac}"

                # Check if this is a horizontal line (start_price == end_price)
                start_p = float(getattr(line, 'start_price', 0))
                end_p = float(getattr(line, 'end_price', 0))
                is_horizontal = abs(start_p - end_p) < 0.0001

                if is_horizontal:
                    color, width = HORIZONTAL_COLOR
                elif frac is not None:
                    # Round frac to known fractions for lookup
                    frac_rounded = round(frac, 4)
                    color, width = FRACTION_COLORS.get(frac_rounded, ("#2196F3", 2))
                else:
                    color, width = FRACTION_COLORS.get(None, ("#808080", 2))

                rays.append({
                    "id": ray_id,
                    "points": [
                        {"time": int(getattr(line, 'start_time', 0)), "price": start_p},
                        {"time": int(getattr(line, 'end_time', 0)), "price": end_p},
                    ],
                    "color": color,
                    "width": width,
                    "linestyle": 1,          # Dotted (matching angle_engine)
                    "extendRight": True,
                })

            return {"origin": origin, "anchor": anchor, "rays": rays}
        except Exception:
            return None

    def _open_trade(self, signal: EntrySignal, bar_index: int, bar_time: int):
        det_trades = self.active_trades.get(signal.detector_name, {})
        if signal.fan_id in det_trades:
            return

        fan_obj = self._active_fans.get(signal.fan_id) if hasattr(self, '_active_fans') else None
        fan_geometry = self._build_fan_geometry(fan_obj)

        trade = ActiveTrade(
            detector_name=signal.detector_name,
            fan_id=signal.fan_id,
            fan_identity=signal.fan_identity,
            priority_label=signal.priority_label,
            side=signal.side,
            entry_price=signal.entry_price,
            entry_bar=bar_index,
            entry_time=bar_time,
            stop_price=signal.stop_price,
            target=signal.target,
            entry_path=signal.entry_path,
            fraction=signal.fraction,
            momentum=signal.momentum,
            anchor_type=signal.anchor_type,
            fan_geometry=fan_geometry,
        )
        det_trades[signal.fan_id] = trade

    def _handle_exit_events(
        self,
        event,
        bar_index: int,
        bar_time: int,
        current_candle: Dict[str, Any],
    ):
        close_price = current_candle.get("close", 0.0)
        high_price = current_candle.get("high", close_price)
        low_price = current_candle.get("low", close_price)

        # Handle both typed PriceInteractionEvent (pipeline) and dict events (study intersection_events)
        evt_type = (
            getattr(event, 'event_type', None)
            or getattr(event, 'type', None)
            or (event.get('type', '') if isinstance(event, dict) else '')
        )
        evt_type_str = str(evt_type).replace('EventType.', '')
        # Dict events use 'fanIdentity' (e.g. "H5-L2") or 'fan' keys
        # Typed pipeline events use 'fan_id' (e.g. "Fan_H5_L2")
        # Normalize dict event fanIdentity format to match pipeline fan_id format
        fan_id = (
            getattr(event, 'fan_id', None)
            or (event.get('fan_id', '') if isinstance(event, dict) else '')
        )
        if not fan_id and isinstance(event, dict):
            raw = event.get('fanIdentity', '') or event.get('fan', '')
            if raw and not raw.startswith('Fan_'):
                fan_id = f"Fan_{raw.replace('-', '_')}"

        # Actively evaluate stops before checking target events
        for det_name, det_trades in list(self.active_trades.items()):
            trade = det_trades.get(fan_id)
            if trade:
                stop_hit = False
                if trade.side == "LONG" and low_price <= trade.stop_price:
                    stop_hit = True
                elif trade.side == "SHORT" and high_price >= trade.stop_price:
                    stop_hit = True
                    
                if stop_hit:
                    self._close_trade(
                        det_name, trade, bar_index, bar_time,
                        trade.stop_price, "LOSS", "stop_loss"
                    )

        if evt_type_str == 'TARGET_HIT':
            for det_name, det_trades in self.active_trades.items():
                trade = det_trades.get(fan_id)
                if trade:
                    self._close_trade(
                        det_name, trade, bar_index, bar_time,
                        close_price, "WIN", "target_hit"
                    )

        if evt_type_str == 'TARGET_FAILED':
            for det_name, det_trades in self.active_trades.items():
                trade = det_trades.get(fan_id)
                if trade:
                    self._close_trade(
                        det_name, trade, bar_index, bar_time,
                        close_price, "LOSS", "target_failed"
                    )

    def _build_explanation(
        self,
        detector_name: str,
        trade: ActiveTrade,
        entry_bar: int,
        exit_bar: int,
        entry_time: int,
        exit_time: int,
        entry_price: float,
        exit_price: float,
        outcome: str,
        reason: str,
    ) -> str:
        from datetime import datetime, timezone
        fmt = lambda ts: datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC') if ts and ts > 0 else '?'
        lines = [
            f"Sub-Strategy: {detector_name}",
            f"Trade: {trade.side} on fan {trade.fan_identity} ({trade.anchor_type} anchor)",
            f"Entry Path: {trade.entry_path}",
            f"Fraction: {trade.fraction} | Target: {trade.target}",
            f"Entry: bar {entry_bar} ({fmt(entry_time)}) @ {entry_price:.2f}",
            f"Exit:  bar {exit_bar} ({fmt(exit_time)}) @ {exit_price:.2f}",
            f"Outcome: {outcome} | Reason: {reason}",
        ]
        return "\n".join(lines)

    def _close_trade(
        self,
        detector_name: str,
        trade: ActiveTrade,
        bar_index: int,
        bar_time: int,
        exit_price: float,
        outcome: str,
        reason: str,
    ):
        if trade.side == "LONG":
            pnl = exit_price - trade.entry_price
        else:
            pnl = trade.entry_price - exit_price

        explanation = self._build_explanation(
            detector_name, trade, trade.entry_bar, bar_index,
            trade.entry_time, bar_time, trade.entry_price, exit_price, outcome, reason,
        )

        record = {
            "detector": detector_name,
            "fan_id": trade.fan_id,
            "fan_identity": trade.fan_identity,
            "anchor_type": trade.anchor_type,
            "side": trade.side,
            "entry_price": trade.entry_price,
            "exit_price": exit_price,
            "pnl": pnl,
            "outcome": outcome,
            "entry_bar": trade.entry_bar,
            "entry_time": trade.entry_time,
            "exit_bar": bar_index,
            "exit_time": bar_time,
            "entry_path": trade.entry_path,
            "progression_step": trade.progression_step,
            "fraction": trade.fraction,
            "target_fraction": trade.target,
            "stop_price": trade.stop_price,
            "stop_triggered": reason == "stop_loss",
            "exit_reason": reason,
            "explanation": explanation,
        }
        if trade.fan_geometry is not None:
            record["fan_geometry"] = trade.fan_geometry
        self.trades[detector_name].append(record)
        self.active_trades[detector_name].pop(trade.fan_id, None)

    def get_summary(self) -> Dict[str, Any]:
        result = {}
        for det_name, trades in self.trades.items():
            wins = [t for t in trades if t.get("outcome") == "WIN"]
            losses = [t for t in trades if t.get("outcome") == "LOSS"]
            total_pnl = sum(t.get("pnl", 0) for t in trades)
            wr = (len(wins) / len(trades) * 100) if trades else 0
            gross_profit = sum(t["pnl"] for t in wins) if wins else 0
            gross_loss = abs(sum(t["pnl"] for t in losses)) if losses else 0
            pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
            result[det_name] = {
                "trades": len(trades), "wr": wr, "pf": pf, "total_pnl": total_pnl,
                "trades_list": trades,
            }
        return result

    def close_all_trades(self, close_price: float, bar_index: int, bar_time: int):
        for det_name, det_trades in list(self.active_trades.items()):
            for trade in list(det_trades.values()):
                if trade.side == "LONG":
                    pnl = close_price - trade.entry_price
                else:
                    pnl = trade.entry_price - close_price
                outcome = "WIN" if pnl > 0 else "LOSS"
                explanation = self._build_explanation(
                    det_name, trade, trade.entry_bar, bar_index,
                    trade.entry_time, bar_time, trade.entry_price, close_price, outcome, "end_of_replay",
                )

                record = {
                    "detector": det_name,
                    "fan_id": trade.fan_id,
                    "fan_identity": trade.fan_identity,
                    "anchor_type": trade.anchor_type,
                    "side": trade.side,
                    "entry_price": trade.entry_price,
                    "exit_price": close_price,
                    "pnl": pnl,
                    "outcome": outcome,
                    "entry_bar": trade.entry_bar,
                    "entry_time": trade.entry_time,
                    "exit_bar": bar_index,
                    "exit_time": bar_time,
                    "entry_path": trade.entry_path,
                    "progression_step": trade.progression_step,
                    "fraction": trade.fraction,
                    "target_fraction": trade.target,
                    "stop_price": trade.stop_price,
                    "stop_triggered": False,
                    "exit_reason": "end_of_replay",
                    "explanation": explanation,
                }
                if trade.fan_geometry is not None:
                    record["fan_geometry"] = trade.fan_geometry
                self.trades[det_name].append(record)
                self.active_trades[det_name].pop(trade.fan_id, None)
