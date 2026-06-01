from typing import Optional

from strategy.entry_detectors.base import EntryDetector, EntrySignal, BarContext
from study_tool.event_pipeline import PriceInteractionEvent, EventType


_PROGRESSION_FRACTIONS = {"0.875", "0.75", "0.5", "horizontal"}
_SEQUENCE_UP = ["0.25", "0.5", "0.75", "0.875"]
_SEQUENCE_DOWN = ["0.875", "0.75", "0.5", "0.25"]
_RETEST_TYPES = {EventType.SUPPORT_TEST, EventType.RESISTANCE_TEST, EventType.REST_ON_ANGLE}


def _next_line(fraction: str, direction_up: bool) -> Optional[str]:
    seq = _SEQUENCE_UP if direction_up else _SEQUENCE_DOWN
    try:
        idx = seq.index(fraction)
        if idx + 1 < len(seq):
            return seq[idx + 1]
    except ValueError:
        pass
    return None


class CounterDirectionalDetector(EntryDetector):
    def __init__(self):
        super().__init__()
        self._pending_counter_breaches: dict = {}

    def detect(
        self,
        event: PriceInteractionEvent,
        context: BarContext,
    ) -> Optional[EntrySignal]:
        if event.event_type != EventType.BREACH_CONFIRMED:
            return None
        if event.fraction not in _PROGRESSION_FRACTIONS:
            return None

        anchor = event.anchor_type
        breach_dir = event.direction

        if anchor == "HIGH" and breach_dir == "up":
            side = "LONG"
        elif anchor == "LOW" and breach_dir == "down":
            side = "SHORT"
        else:
            return None

        direction_up = side == "LONG"
        target = _next_line(event.fraction, direction_up)
        if target is None:
            return None

        if context.momentum.state == "momentum":
            return EntrySignal(
                detector_name="CounterDirectionalDetector",
                fan_id=event.fan_id,
                fan_identity=event.fan_identity,
                priority_label=event.priority_label,
                side=side,
                entry_price=event.close,
                stop_price=event.close,
                target=target,
                entry_path="counter_directional_immediate",
                fraction=event.fraction,
                momentum=context.momentum,
                anchor_type=anchor,
            )

        key = f"{event.fan_id}:{event.fraction}"
        self._pending_counter_breaches[key] = {
            "fan_id": event.fan_id,
            "fan_identity": event.fan_identity,
            "priority_label": event.priority_label,
            "fraction": event.fraction,
            "line_price": event.close,
            "side": side,
            "anchor_type": anchor,
            "target": target,
            "breach_bar": event.bar_index,
            "breach_momentum": context.momentum,
        }
        return None

    def on_retest_event(
        self,
        event: PriceInteractionEvent,
        context: BarContext,
    ) -> Optional[EntrySignal]:
        if event.event_type not in _RETEST_TYPES:
            return None

        key = f"{event.fan_id}:{event.fraction}"
        pending = self._pending_counter_breaches.pop(key, None)
        if pending is None:
            return None

        return EntrySignal(
            detector_name="CounterDirectionalDetector",
            fan_id=pending["fan_id"],
            fan_identity=pending["fan_identity"],
            priority_label=pending["priority_label"],
            side=pending["side"],
            entry_price=event.close,
            stop_price=pending["line_price"],
            target=pending["target"],
            entry_path="counter_directional_retest",
            fraction=event.fraction,
            momentum=context.momentum,
            anchor_type=pending["anchor_type"],
        )
