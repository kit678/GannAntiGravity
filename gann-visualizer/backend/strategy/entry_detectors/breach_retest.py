from typing import Optional

from strategy.entry_detectors.base import EntryDetector, EntrySignal, BarContext
from study_tool.event_pipeline import PriceInteractionEvent, EventType


_PROGRESSION_FRACTIONS = {"0.875", "0.75", "0.5", "horizontal"}
_RETEST_TYPES = {EventType.SUPPORT_TEST, EventType.RESISTANCE_TEST, EventType.REST_ON_ANGLE}


class BreachRetestDetector(EntryDetector):
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
        if anchor == "LOW":
            side = "LONG"
        elif anchor == "HIGH":
            side = "SHORT"
        else:
            return None

        setup_key = f"{event.fan_id}:{event.fraction}"
        context.breached_setups[setup_key] = {
            "fan_id": event.fan_id,
            "fan_identity": event.fan_identity,
            "priority_label": event.priority_label,
            "fraction": event.fraction,
            "line_price": event.close,
            "side": side,
            "anchor_type": anchor,
            "breach_bar": event.bar_index,
            "breach_momentum": context.momentum,
            "breached": True,
            "retest_pending": False,
        }
        return None

    def on_retest_event(
        self,
        event: PriceInteractionEvent,
        context: BarContext,
    ) -> Optional[EntrySignal]:
        if event.event_type not in _RETEST_TYPES:
            return None

        setup_key = f"{event.fan_id}:{event.fraction}"
        setup = context.breached_setups.get(setup_key)
        if not setup or not setup.get("breached"):
            return None

        current_target = context.progression.get_current_target(event.fan_id)
        if current_target is None:
            return None

        return EntrySignal(
            detector_name="BreachRetestDetector",
            fan_id=event.fan_id,
            fan_identity=event.fan_identity,
            priority_label=event.priority_label,
            side=setup["side"],
            entry_price=event.close,
            stop_price=setup["line_price"],
            target=current_target,
            entry_path="breach_retest",
            fraction=event.fraction,
            momentum=context.momentum,
            anchor_type=setup["anchor_type"],
        )
