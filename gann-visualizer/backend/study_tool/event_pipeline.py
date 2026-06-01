from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any


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
