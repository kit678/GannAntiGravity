from typing import Optional

from strategy.entry_detectors.base import EntryDetector, EntrySignal, BarContext
from study_tool.event_pipeline import PriceInteractionEvent, EventType


_PROGRESSION_FRACTIONS = {"0.875", "0.75", "0.5", "horizontal"}


class MomentumImmediateDetector(EntryDetector):
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

        if context.momentum.state != "momentum":
            return None

        current_target = context.progression.get_current_target(event.fan_id)
        if current_target is None:
            return None

        return EntrySignal(
            detector_name="MomentumImmediateDetector",
            fan_id=event.fan_id,
            fan_identity=event.fan_identity,
            priority_label=event.priority_label,
            side=side,
            entry_price=event.close,
            stop_price=event.close,
            target=current_target,
            entry_path="momentum_immediate",
            fraction=event.fraction,
            momentum=context.momentum,
            anchor_type=anchor,
        )
