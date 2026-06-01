from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any

from study_tool.unified_state_machine import UnifiedStateMachine
from study_tool.angle_zone_tracker import AngleZoneTracker
from study_tool.cluster_detector import ClusterDetector
from study_tool.bounce_rejection_tracker import BounceRejectionTracker
from study_tool.fan_validator import FanValidator
from study_tool.intersection_detector import IntersectionDetector


class EventType(Enum):
    CROSS_UP = "CROSS_UP"
    CROSS_DOWN = "CROSS_DOWN"
    GAP_CROSS_UP = "GAP_CROSS_UP"
    GAP_CROSS_DOWN = "GAP_CROSS_DOWN"
    SUPPORT_TEST = "SUPPORT_TEST"
    RESISTANCE_TEST = "RESISTANCE_TEST"
    SUPPORT_BOUNCE = "SUPPORT_BOUNCE"
    RESISTANCE_REJECTION = "RESISTANCE_REJECTION"
    BREACH_CONFIRMED = "BREACH_CONFIRMED"
    BREACH_CONFIRMED_NO_ALPHA = "BREACH_CONFIRMED_NO_ALPHA"
    REST_ON_ANGLE = "REST_ON_ANGLE"
    TARGET_HIT = "TARGET_HIT"
    TARGET_FAILED = "TARGET_FAILED"
    FAN_VALIDATED = "FAN_VALIDATED"
    ZONE_CHANGE = "ZONE_CHANGE"
    FAN_DEACTIVATED = "FAN_DEACTIVATED"


@dataclass
class BounceRejectionContext:
    direction: str
    strength: float
    bars_to_confirm: int
    line_price: float


@dataclass
class RestContext:
    rest_type: str
    bars_resting: int


@dataclass
class PriceInteractionEvent:
    event_type: EventType
    fan_id: str
    fan_identity: str
    priority_label: str
    fraction: str
    price: float
    direction: Optional[str]
    bar_index: int
    timestamp: int

    open: float
    high: float
    low: float
    close: float

    current_zone: Optional[str] = None
    zone_highest_close: Optional[float] = None
    zone_lowest_close: Optional[float] = None
    bars_in_zone: Optional[int] = None

    cluster_state: bool = False

    active_angle_prices: Dict[str, float] = field(default_factory=dict)
    next_angle_line: Optional[str] = None

    is_gap_cross: bool = False

    bounce_rejection: Optional[BounceRejectionContext] = None
    rest_context: Optional[RestContext] = None

    anchor_bar_index: int = 0
    scale_ratio: float = 0.0
    anchor_price: float = 0.0
    origin_bar_index: int = 0
    origin_price: float = 0.0
    fan_geometry: Optional[dict] = None

    anchor_type: str = ""


@dataclass
class PipelineState:
    state_machine_state: Dict[str, Any] = field(default_factory=dict)
    zone_tracker_state: Dict[str, Any] = field(default_factory=dict)
    cluster_state: Dict[str, Any] = field(default_factory=dict)
    bounce_rejection_state: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineOutput:
    events: List[PriceInteractionEvent] = field(default_factory=list)
    state: PipelineState = field(default_factory=PipelineState)
    fan_validations: List[Dict[str, Any]] = field(default_factory=list)


class EventPipeline:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.state_machine = UnifiedStateMachine(config)
        self.zone_tracker = AngleZoneTracker()
        iou_threshold = config.get('iou_threshold', 0.70)
        self.cluster_detector = ClusterDetector(iou_threshold=iou_threshold)
        self.bounce_rejection_tracker = BounceRejectionTracker(config)
        self.intersection_detector = IntersectionDetector()
        self._prior_pipeline_state: Optional[PipelineState] = None

    def process_bar(
        self,
        candles: List[Dict[str, Any]],
        bar_index: int,
        active_fans: Dict[str, Any],
        fan_validator: FanValidator,
        prior_state: Optional[PipelineState] = None,
    ) -> PipelineOutput:
        if bar_index < 1:
            return PipelineOutput()

        current_candle = candles[bar_index]
        prev_candle = candles[bar_index - 1]

        intersections = self.intersection_detector.detect(
            current_candle, prev_candle, active_fans, bar_index
        )

        state_machine_outputs = self.state_machine.process_bar(
            current_candle, prev_candle, bar_index, intersections, active_fans, candles=candles
        )

        zone_contexts: Dict[str, Dict[str, Any]] = {}
        for fan_id, fan_obj in active_fans.items():
            snapshot = self.zone_tracker.compute_snapshot(fan_obj, current_candle, bar_index)
            zone_contexts[fan_id] = {
                "current_zone": snapshot.zone,
                "zone_highest_close": snapshot.zone_highest_close,
                "zone_lowest_close": snapshot.zone_lowest_close,
                "bars_in_zone": snapshot.bars_in_zone,
            }

        cluster_result = self.cluster_detector.process_candle(current_candle, bar_index)
        cluster_state = cluster_result.get('in_cluster', False)

        bar_events_for_tracker = [
            {
                "type": out.event_type,
                "fan_id": out.fan_id,
                "fanIdentity": out.fan_identity,
                "fraction": str(out.fraction),
                "price": out.price,
                "direction": out.direction,
                "time": current_candle.get("time", 0),
            }
            for out in state_machine_outputs
        ]
        tracker_results = self.bounce_rejection_tracker.process_bar(
            current_candle, bar_index, bar_events_for_tracker, active_fans
        )

        fan_validations = fan_validator.process_intersections(
            intersections, current_candle, bar_index
        )

        events = self._build_events(
            state_machine_outputs=state_machine_outputs,
            current_candle=current_candle,
            bar_index=bar_index,
            active_fans=active_fans,
            zone_contexts=zone_contexts,
            cluster_state=cluster_state,
            tracker_results=tracker_results,
        )

        pipeline_state = PipelineState(
            state_machine_state=self.state_machine.get_state(),
            zone_tracker_state=self.zone_tracker.get_state(),
            cluster_state={"cluster": cluster_state},
            bounce_rejection_state=self.bounce_rejection_tracker.get_state()
            if hasattr(self.bounce_rejection_tracker, 'get_state')
            else {},
        )

        self._prior_pipeline_state = pipeline_state

        fan_validation_dicts = []
        for fv in fan_validations:
            if hasattr(fv, 'to_dict'):
                fan_validation_dicts.append(fv.to_dict())
            elif isinstance(fv, dict):
                fan_validation_dicts.append(fv)

        return PipelineOutput(
            events=events,
            state=pipeline_state,
            fan_validations=fan_validation_dicts,
        )

    def _build_events(
        self,
        state_machine_outputs: List[Any],
        current_candle: Dict[str, Any],
        bar_index: int,
        active_fans: Dict[str, Any],
        zone_contexts: Dict[str, Dict[str, Any]],
        cluster_state: bool,
        tracker_results: Dict[str, List[Any]],
    ) -> List[PriceInteractionEvent]:
        events: List[PriceInteractionEvent] = []

        open_p = current_candle.get("open", 0.0)
        high_p = current_candle.get("high", 0.0)
        low_p = current_candle.get("low", 0.0)
        close_p = current_candle.get("close", 0.0)
        timestamp = current_candle.get("time", 0)

        bounce_map = {}
        rejection_map = {}
        for b in tracker_results.get("bounces", []):
            bid = getattr(b, 'fan_id', '')
            aname = getattr(b, 'angle_name', '')
            key = f"{bid}:{aname}"
            bounce_map[key] = b
        for r in tracker_results.get("rejections", []):
            rid = getattr(r, 'fan_id', '')
            rname = getattr(r, 'angle_name', '')
            key = f"{rid}:{rname}"
            rejection_map[key] = r

        rest_lookup: Dict[str, Any] = {}
        for rest in tracker_results.get("rest_events", []):
            rid = getattr(rest, 'fan_id', '')
            rname = getattr(rest, 'angle_name', '')
            rest_lookup[f"{rid}:{rname}"] = rest

        for output in state_machine_outputs:
            event_type_str = output.event_type
            try:
                event_type = EventType(event_type_str)
            except ValueError:
                event_type = EventType.CROSS_UP

            fan_id = output.fan_id or ""
            fan_identity = output.fan_identity or ""
            priority_label = output.priority_label or ""
            fraction = str(output.fraction) if output.fraction is not None else ""
            price = output.price or 0.0
            direction = output.direction

            zone_context = zone_contexts.get(fan_id) if zone_contexts else None
            current_zone = zone_context.get("current_zone") if zone_context else None
            zone_high = zone_context.get("zone_highest_close") if zone_context else None
            zone_low = zone_context.get("zone_lowest_close") if zone_context else None
            bars_in_zone = zone_context.get("bars_in_zone") if zone_context else None

            anchor_type = ""
            if fan_identity and "-" in fan_identity:
                parts = fan_identity.split("-")
                if parts and parts[0].startswith("H"):
                    anchor_type = "HIGH"
                elif parts and parts[0].startswith("L"):
                    anchor_type = "LOW"

            is_gap = event_type_str in ("GAP_CROSS_UP", "GAP_CROSS_DOWN")

            active_angle_prices: Dict[str, float] = {}
            fan_obj = active_fans.get(fan_id) if fan_id else None
            if fan_obj and hasattr(fan_obj, 'angle_lines'):
                for line_name, line_data in fan_obj.angle_lines.items():
                    if hasattr(line_data, 'current_price'):
                        active_angle_prices[str(line_name)] = line_data.current_price

            br_ctx = None
            key = f"{fan_id}:{fraction}"
            if key in bounce_map:
                b = bounce_map[key]
                br_ctx = BounceRejectionContext(
                    direction="up",
                    strength=getattr(b, 'bounce_distance', 0.0),
                    bars_to_confirm=getattr(b, 'bars_elapsed', 0),
                    line_price=getattr(b, 'bounce_price', price),
                )
            elif key in rejection_map:
                r = rejection_map[key]
                br_ctx = BounceRejectionContext(
                    direction="down",
                    strength=getattr(r, 'rejection_distance', 0.0),
                    bars_to_confirm=getattr(r, 'bars_elapsed', 0),
                    line_price=getattr(r, 'rejection_price', price),
                )

            rest_ctx = None
            if key in rest_lookup:
                rest = rest_lookup[key]
                rest_ctx = RestContext(
                    rest_type=getattr(rest, 'rest_type', ''),
                    bars_resting=getattr(rest, 'bars_elapsed', 0),
                )

            event = PriceInteractionEvent(
                event_type=event_type,
                fan_id=fan_id,
                fan_identity=fan_identity,
                priority_label=priority_label,
                fraction=fraction,
                price=price,
                direction=direction,
                bar_index=bar_index,
                timestamp=timestamp,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                current_zone=current_zone,
                zone_highest_close=zone_high,
                zone_lowest_close=zone_low,
                bars_in_zone=bars_in_zone,
                cluster_state=cluster_state,
                active_angle_prices=active_angle_prices,
                is_gap_cross=is_gap,
                bounce_rejection=br_ctx,
                rest_context=rest_ctx,
                anchor_type=anchor_type,
            )
            events.append(event)

        return events
