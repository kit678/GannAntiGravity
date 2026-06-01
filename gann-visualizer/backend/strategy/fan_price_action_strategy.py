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
    entry_path: str
    fraction: str
    momentum: Optional[MomentumContext] = None
    anchor_type: str = ""
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
    ):
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

    def _open_trade(self, signal: EntrySignal, bar_index: int, bar_time: int):
        det_trades = self.active_trades.get(signal.detector_name, {})
        if signal.fan_id in det_trades:
            return

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
        )
        det_trades[signal.fan_id] = trade

    def _handle_exit_events(
        self,
        event: PriceInteractionEvent,
        bar_index: int,
        bar_time: int,
        current_candle: Dict[str, Any],
    ):
        close_price = current_candle.get("close", 0.0)

        if event.event_type == EventType.TARGET_HIT:
            for det_name, det_trades in self.active_trades.items():
                trade = det_trades.get(event.fan_id)
                if trade:
                    self._close_trade(
                        det_name, trade, bar_index, bar_time,
                        close_price, "WIN", "target_hit"
                    )

        if event.event_type == EventType.TARGET_FAILED:
            for det_name, det_trades in self.active_trades.items():
                trade = det_trades.get(event.fan_id)
                if trade:
                    self._close_trade(
                        det_name, trade, bar_index, bar_time,
                        close_price, "LOSS", "target_failed"
                    )

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
            "exit_bar": bar_index,
            "entry_path": trade.entry_path,
            "progression_step": trade.progression_step,
            "fraction": trade.fraction,
            "target_fraction": trade.target,
            "stop_price": trade.stop_price,
            "stop_triggered": reason == "stop_loss",
            "exit_reason": reason,
        }
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
