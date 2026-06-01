from typing import Optional

from strategy.entry_detectors.base import EntryDetector, EntrySignal, BarContext
from study_tool.event_pipeline import PriceInteractionEvent, EventType


_SEQUENCE_UP = ["0.875", "0.75", "0.5", "0.25"]
_SEQUENCE_DOWN = ["0.25", "0.5", "0.75", "0.875"]


def _adjacent_line(fraction: str, direction_up: bool) -> Optional[str]:
    seq = _SEQUENCE_UP if direction_up else _SEQUENCE_DOWN
    try:
        idx = seq.index(fraction)
        if idx + 1 < len(seq):
            return seq[idx + 1]
    except ValueError:
        pass
    return None


class RejectionEntryDetector(EntryDetector):
    def detect(
        self,
        event: PriceInteractionEvent,
        context: BarContext,
    ) -> Optional[EntrySignal]:
        if event.event_type == EventType.RESISTANCE_REJECTION:
            target = _adjacent_line(event.fraction, direction_up=False)
            return EntrySignal(
                detector_name="RejectionEntryDetector",
                fan_id=event.fan_id,
                fan_identity=event.fan_identity,
                priority_label=event.priority_label,
                side="SHORT",
                entry_price=event.close,
                stop_price=event.price,
                target=target or event.fraction,
                entry_path="rejection_bounce",
                fraction=event.fraction,
                momentum=context.momentum,
                anchor_type=event.anchor_type,
            )

        if event.event_type == EventType.SUPPORT_BOUNCE:
            target = _adjacent_line(event.fraction, direction_up=True)
            return EntrySignal(
                detector_name="RejectionEntryDetector",
                fan_id=event.fan_id,
                fan_identity=event.fan_identity,
                priority_label=event.priority_label,
                side="LONG",
                entry_price=event.close,
                stop_price=event.price,
                target=target or event.fraction,
                entry_path="rejection_bounce",
                fraction=event.fraction,
                momentum=context.momentum,
                anchor_type=event.anchor_type,
            )

        return None
