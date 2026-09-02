"""
Event Logger - Logs all price-angle interactions for analysis

This module handles:
- Logging angle touches, breaches, and reactions
- Logging indicator states
- Exporting data for analysis
"""

import json
import csv
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path


class EventType(Enum):
    """Types of events to log.

    Single source of truth: see docs/EVENT_TYPES.md for full documentation.
    """
    # Core Event Types
    BREACH_CONFIRMED = "breach_confirmed"    # N successive closes achieved
    BREACH_CONFIRMED_NO_ALPHA = "BREACH_CONFIRMED_NO_ALPHA"  # Intra-bar or next-target-hit, no alpha
    TARGET_HIT = "target_hit"               # Target in progression sequence reached
    TARGET_FAILED = "target_failed"         # Failed to reach target, crossed back
    FAN_VALIDATED = "fan_validated"           # Fan validated via 7/8 interaction
    ZONE_CHANGE = "zone_change"              # Price moved to a new angle zone

    # Frontend Alignment Types (for direct CSV compatibility)
    CROSS_UP = "CROSS_UP"
    CROSS_DOWN = "CROSS_DOWN"
    SUPPORT_TEST = "SUPPORT_TEST"
    RESISTANCE_TEST = "RESISTANCE_TEST"
    SUPPORT_BOUNCE = "SUPPORT_BOUNCE"  # Price successfully bounced from support
    RESISTANCE_REJECTION = "RESISTANCE_REJECTION"  # Price successfully rejected from resistance
    FAN_DEACTIVATED = "FAN_DEACTIVATED"  # Fan deactivated/completed (not invalidated)

    # Pipeline Event Types
    GAP_CROSS_UP = "GAP_CROSS_UP"
    GAP_CROSS_DOWN = "GAP_CROSS_DOWN"
    REST_ON_ANGLE = "REST_ON_ANGLE"

    # Gann Ladder Event Types (Phase 2)
    LADDER_TOUCH = "LADDER_TOUCH"                          # bar's range reached a level
    LADDER_CROSS = "LADDER_CROSS"                          # moved through, unconfirmed
    LADDER_BREACH_CONFIRMED = "LADDER_BREACH_CONFIRMED"    # N successive closes beyond
    LADDER_BREACH_REJECTED = "LADDER_BREACH_REJECTED"      # crossed, failed to confirm
    LADDER_RETEST = "LADDER_RETEST"                        # returned to a breached level
    LADDER_BREACH_RESOLVED = "LADDER_BREACH_RESOLVED"      # terminal outcome assigned


# Human-readable display names for each event type
EVENT_TYPE_DISPLAY_NAMES: dict = {
    "CROSS_UP": "Cross Up (Bullish)",
    "CROSS_DOWN": "Cross Down (Bearish)",
    "GAP_CROSS_UP": "Gap Cross Up (Bullish)",
    "GAP_CROSS_DOWN": "Gap Cross Down (Bearish)",
    "SUPPORT_TEST": "Support Test",
    "RESISTANCE_TEST": "Resistance Test",
    "SUPPORT_BOUNCE": "Support Bounce",
    "RESISTANCE_REJECTION": "Resistance Rejection",
    "BREACH_CONFIRMED": "Breach Confirmed",
    "BREACH_CONFIRMED_NO_ALPHA": "Breach Confirmed (No Alpha)",
    "REST_ON_ANGLE": "Rest on Angle",
    "TARGET_HIT": "Target Hit",
    "TARGET_FAILED": "Target Failed",
    "FAN_VALIDATED": "Fan Validated (7/8)",
    "ZONE_CHANGE": "Zone Change",
    "FAN_DEACTIVATED": "Fan Deactivated",
    "breach_confirmed": "Breach Confirmed",
    "target_hit": "Target Hit",
    "target_failed": "Target Failed",
    "fan_validated": "Fan Validated (7/8)",
    "zone_change": "Zone Change",
    "LADDER_TOUCH": "Ladder Touch",
    "LADDER_CROSS": "Ladder Cross",
    "LADDER_BREACH_CONFIRMED": "Ladder Breach Confirmed",
    "LADDER_BREACH_REJECTED": "Ladder Breach Rejected",
    "LADDER_RETEST": "Ladder Retest",
    "LADDER_BREACH_RESOLVED": "Ladder Breach Resolved",
}
"""Human-readable display names for each event type value string."""


@dataclass
class Event:
    """Represents a logged event"""
    timestamp: int          # Bar timestamp
    event_type: EventType
    angle_name: Optional[str] = None
    price: Optional[float] = None
    direction: Optional[str] = None  # "up", "down"
    details: Optional[Dict] = None

    # Bar identity
    bar_index: Optional[int] = None

    # Fan identity (H1-L1 style label, e.g. from state_event.fan_identity)
    fan_identity: Optional[str] = None
    priority_label: Optional[str] = None

    # OHLC data for the bar where the event occurred
    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    close_price: Optional[float] = None

    # Angle prices snapshot (all active lines for the fan at this bar)
    active_angle_prices: Optional[Dict[str, float]] = None

    # Contextual Structural Data
    cluster_state: Optional[bool] = False
    current_zone: Optional[str] = None
    zone_highest_close: Optional[float] = None
    zone_lowest_close: Optional[float] = None
    bars_in_zone: Optional[int] = None

    # Target Progression Info
    next_angle_line: Optional[str] = None

    # Event classification flags
    is_gap_cross: bool = False
    is_retro: bool = False
    anchor_type: Optional[str] = None  # "HIGH" or "LOW"

    # Bounce / Rejection context (from BounceRejectionTracker)
    bounce_rejection: Optional[Dict] = None  # {direction, strength, bars_to_confirm, line_price}
    rest_context: Optional[Dict] = None      # {rest_type, bars_resting}

    # State machine snapshot at time of event
    state_snapshot: Optional[Dict] = None    # {pending_breaches, pending_tests, active_targets, ...}

    # Human-readable display name for event type
    event_type_display_name: Optional[str] = None

    # Identity (for multi-instrument / multi-timeframe corpora)
    instrument: Optional[str] = None
    timeframe: Optional[str] = None

    # Forward-looking outcomes (populated post-simulation)
    mfe_5: Optional[float] = None
    mae_5: Optional[float] = None
    mfe_10: Optional[float] = None
    mae_10: Optional[float] = None
    mfe_20: Optional[float] = None
    mae_20: Optional[float] = None
    mfe_50: Optional[float] = None
    mae_50: Optional[float] = None
    # Raw forward excursions, not sorted into favourable/adverse.
    #
    # For an event with no direction - every LADDER_TOUCH - mfe/mae fall back
    # to labelling whichever move was larger as favourable. That is decided
    # after the fact and cannot be predicted, so it leaks as a training label.
    # These keep the two directions separate.
    exc_up_5: Optional[float] = None
    exc_down_5: Optional[float] = None
    exc_up_10: Optional[float] = None
    exc_down_10: Optional[float] = None
    exc_up_20: Optional[float] = None
    exc_down_20: Optional[float] = None
    exc_up_50: Optional[float] = None
    exc_down_50: Optional[float] = None
    reversal_outcome: Optional[str] = None  # "WIN", "LOSS", or None for first-break detection
    body_break: Optional[bool] = None  # Next bar close broke test candle's body

    # Fan geometry context (for true angular fan ray reconstruction)
    anchor_bar_index: Optional[int] = None
    scale_ratio: Optional[float] = None
    anchor_price: Optional[float] = None
    origin_bar_index: Optional[int] = None   # Bar index of the fan's temporal origin (where lines radiate from)
    origin_price: Optional[float] = None     # Price at the fan's temporal origin
    fan_geometry: Optional[Dict] = None      # Captured fan ray geometry for hypothesis navigator

    # Gann ladder level identity (Phase 2)
    level_source: Optional[str] = None        # 'center' | 'sun' | 'moon'
    level_price: Optional[float] = None
    level_square: Optional[float] = None      # fractional for sub-levels
    level_kind: Optional[str] = None          # 'major' | 'sub'
    level_degree: Optional[int] = None        # 0/45/.../315 - the arm
    level_ring: Optional[int] = None          # band between odd squares
    level_sub_index: Optional[int] = None     # 1..7, None for majors
    level_is_halfway: Optional[bool] = None
    level_segment_start: Optional[float] = None
    level_segment_end: Optional[float] = None

    # Instrument scaling in use for this walk
    price_scale: Optional[int] = None         # 1 or 10

    # Celestial body position at the time of the event
    body_degree: Optional[float] = None       # raw ecliptic longitude
    body_square: Optional[int] = None         # the square it mapped to

    # Breach linkage. Without this, "of the breaches that confirmed, how many
    # were retested and held?" cannot be answered from the corpus.
    breach_id: Optional[str] = None           # set on a confirmed breach
    parent_breach_id: Optional[str] = None    # set on its retests and resolution

    def to_dict(self) -> Dict:
        # Resolve human-readable display name
        evt_type_val = self.event_type.value
        display_name = self.event_type_display_name or EVENT_TYPE_DISPLAY_NAMES.get(evt_type_val, evt_type_val)

        return {
            "timestamp": self.timestamp,
            "datetime": datetime.fromtimestamp(self.timestamp).isoformat() if self.timestamp else None,
            "event_type": self.event_type.value,
            "event_type_display_name": display_name,
            "angle_name": self.angle_name,
            "price": self.price,
            "direction": self.direction,
            "bar_index": self.bar_index,
            "fan_identity": self.fan_identity,
            "priority_label": self.priority_label,
            "open": self.open_price,
            "high": self.high_price,
            "low": self.low_price,
            "close": self.close_price,
            "active_angle_prices": self.active_angle_prices or {},
            "cluster_state": self.cluster_state,
            "current_zone": self.current_zone,
            "zone_highest_close": self.zone_highest_close,
            "zone_lowest_close": self.zone_lowest_close,
            "bars_in_zone": self.bars_in_zone,
            "next_angle_line": self.next_angle_line,
            "is_gap_cross": self.is_gap_cross,
            "is_retro": self.is_retro,
            "anchor_type": self.anchor_type,
            "bounce_rejection": self.bounce_rejection,
            "rest_context": self.rest_context,
            "state_snapshot": self.state_snapshot,
            "instrument": self.instrument,
            "timeframe": self.timeframe,
            "mfe_5": self.mfe_5,
            "mae_5": self.mae_5,
            "mfe_10": self.mfe_10,
            "mae_10": self.mae_10,
            "mfe_20": self.mfe_20,
            "mae_20": self.mae_20,
            "mfe_50": self.mfe_50,
            "mae_50": self.mae_50,
            "exc_up_5": self.exc_up_5,
            "exc_down_5": self.exc_down_5,
            "exc_up_10": self.exc_up_10,
            "exc_down_10": self.exc_down_10,
            "exc_up_20": self.exc_up_20,
            "exc_down_20": self.exc_down_20,
            "exc_up_50": self.exc_up_50,
            "exc_down_50": self.exc_down_50,
            "reversal_outcome": self.reversal_outcome,
            "body_break": self.body_break,
            "details": self.details or {},
            # Fan geometry context
            "anchor_bar_index": self.anchor_bar_index,
            "scale_ratio": self.scale_ratio,
            "anchor_price": self.anchor_price,
            "origin_bar_index": self.origin_bar_index,
            "origin_price": self.origin_price,
            "fan_geometry": self.fan_geometry,
            # Gann ladder level identity (Phase 2)
            "level_source": self.level_source,
            "level_price": self.level_price,
            "level_square": self.level_square,
            "level_kind": self.level_kind,
            "level_degree": self.level_degree,
            "level_ring": self.level_ring,
            "level_sub_index": self.level_sub_index,
            "level_is_halfway": self.level_is_halfway,
            "level_segment_start": self.level_segment_start,
            "level_segment_end": self.level_segment_end,
            "price_scale": self.price_scale,
            "body_degree": self.body_degree,
            "body_square": self.body_square,
            "breach_id": self.breach_id,
            "parent_breach_id": self.parent_breach_id,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Event':
        # Resolve event_type before constructing so we can pass required args
        evt_type_val = data.get("event_type")
        try:
            resolved_event_type = EventType(evt_type_val)
        except (ValueError, KeyError):
            resolved_event_type = EventType.CROSS_UP

        event = cls(
            timestamp=data.get("timestamp", 0),
            event_type=resolved_event_type,
        )
        event.angle_name = data.get("angle_name")
        event.price = data.get("price")
        event.direction = data.get("direction")
        event.bar_index = data.get("bar_index")
        event.fan_identity = data.get("fan_identity")
        event.priority_label = data.get("priority_label")
        event.open_price = data.get("open")
        event.high_price = data.get("high")
        event.low_price = data.get("low")
        event.close_price = data.get("close")
        event.active_angle_prices = data.get("active_angle_prices", {})
        event.cluster_state = data.get("cluster_state", False)
        event.current_zone = data.get("current_zone")
        event.zone_highest_close = data.get("zone_highest_close")
        event.zone_lowest_close = data.get("zone_lowest_close")
        event.bars_in_zone = data.get("bars_in_zone")
        event.next_angle_line = data.get("next_angle_line")
        event.is_gap_cross = data.get("is_gap_cross", False)
        event.is_retro = data.get("is_retro", False)
        event.anchor_type = data.get("anchor_type")
        event.bounce_rejection = data.get("bounce_rejection")
        event.rest_context = data.get("rest_context")
        event.state_snapshot = data.get("state_snapshot")
        event.event_type_display_name = data.get("event_type_display_name")
        event.instrument = data.get("instrument")
        event.timeframe = data.get("timeframe")
        event.mfe_5 = data.get("mfe_5")
        event.mae_5 = data.get("mae_5")
        event.mfe_10 = data.get("mfe_10")
        event.mae_10 = data.get("mae_10")
        event.mfe_20 = data.get("mfe_20")
        event.mae_20 = data.get("mae_20")
        event.mfe_50 = data.get("mfe_50")
        event.mae_50 = data.get("mae_50")
        event.exc_up_5 = data.get("exc_up_5")
        event.exc_down_5 = data.get("exc_down_5")
        event.exc_up_10 = data.get("exc_up_10")
        event.exc_down_10 = data.get("exc_down_10")
        event.exc_up_20 = data.get("exc_up_20")
        event.exc_down_20 = data.get("exc_down_20")
        event.exc_up_50 = data.get("exc_up_50")
        event.exc_down_50 = data.get("exc_down_50")
        event.reversal_outcome = data.get("reversal_outcome")
        event.body_break = data.get("body_break")
        event.details = data.get("details", {})
        # Fan geometry context
        event.anchor_bar_index = data.get("anchor_bar_index")
        event.scale_ratio = data.get("scale_ratio")
        event.anchor_price = data.get("anchor_price")
        event.origin_bar_index = data.get("origin_bar_index")
        event.origin_price = data.get("origin_price")
        event.fan_geometry = data.get("fan_geometry")
        # Gann ladder level identity (Phase 2)
        event.level_source = data.get("level_source")
        event.level_price = data.get("level_price")
        event.level_square = data.get("level_square")
        event.level_kind = data.get("level_kind")
        event.level_degree = data.get("level_degree")
        event.level_ring = data.get("level_ring")
        event.level_sub_index = data.get("level_sub_index")
        event.level_is_halfway = data.get("level_is_halfway")
        event.level_segment_start = data.get("level_segment_start")
        event.level_segment_end = data.get("level_segment_end")
        event.price_scale = data.get("price_scale")
        event.body_degree = data.get("body_degree")
        event.body_square = data.get("body_square")
        event.breach_id = data.get("breach_id")
        event.parent_breach_id = data.get("parent_breach_id")
        return event


class EventLogger:
    """
    Logger for tracking price-angle interactions.
    
    Usage:
        logger = EventLogger()
        logger.log_angle_touch(timestamp, price, "7/8θ", candle_analysis)
        logger.export_csv("events.csv")
    """
    
    def __init__(self, session_name: Optional[str] = None):
        """
        Initialize event logger.
        
        Args:
            session_name: Optional name for this logging session
        """
        self.session_name = session_name or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.events: List[Event] = []
        self.indicator_snapshots: List[Dict] = []
    
    def log_event(
        self,
        timestamp: int,
        event_type: EventType,
        angle_name: Optional[str] = None,
        price: Optional[float] = None,
        direction: Optional[str] = None,
        details: Optional[Dict] = None,
        bar_index: Optional[int] = None,
        fan_identity: Optional[str] = None,
        priority_label: Optional[str] = None,
        open_price: Optional[float] = None,
        high_price: Optional[float] = None,
        low_price: Optional[float] = None,
        close_price: Optional[float] = None,
        active_angle_prices: Optional[Dict[str, float]] = None,
        cluster_state: Optional[bool] = False,
        current_zone: Optional[str] = None,
        zone_highest_close: Optional[float] = None,
        zone_lowest_close: Optional[float] = None,
        bars_in_zone: Optional[int] = None,
        next_angle_line: Optional[str] = None,
        is_gap_cross: bool = False,
        is_retro: bool = False,
        anchor_type: Optional[str] = None,
        bounce_rejection: Optional[Dict] = None,
        rest_context: Optional[Dict] = None,
        state_snapshot: Optional[Dict] = None,
        anchor_bar_index: Optional[int] = None,
        scale_ratio: Optional[float] = None,
        anchor_price: Optional[float] = None,
        origin_bar_index: Optional[int] = None,
        origin_price: Optional[float] = None,
        fan_geometry: Optional[Dict] = None
    ) -> Event:
        """
        Log a generic event.

        Args:
            timestamp: Bar timestamp
            event_type: Type of event
            angle_name: Name of angle involved (if applicable)
            price: Price at event
            direction: Direction of movement
            details: Additional details
            bar_index: Bar index in the simulation
            fan_identity: Fan identity label (e.g. H1-L1)
            priority_label: Fan priority label
            open_price: Candle Open
            high_price: Candle High
            low_price: Candle Low
            close_price: Candle Close
            active_angle_prices: Dictionary of all current angle prices for the fan
            cluster_state: Whether price is in a cluster/consolidation
            current_zone: The zone the price is in
            zone_highest_close: Highest close price within the zone
            zone_lowest_close: Lowest close price within the zone
            bars_in_zone: Number of bars price has been in this zone
            next_angle_line: Last angle line touched/crossed
            is_gap_cross: Whether this is a gap cross event
            is_retro: Whether this event was retroactively generated
            anchor_type: Type of anchor pivot ("HIGH" or "LOW")
            bounce_rejection: Bounce/rejection context {direction, strength, bars_to_confirm, line_price}
            rest_context: Rest context {rest_type, bars_resting}
            state_snapshot: State machine snapshot at time of event
            anchor_bar_index: Bar index of the fan's anchor pivot
            scale_ratio: Scale ratio for the fan
            anchor_price: Price at the fan's anchor pivot
            origin_bar_index: Bar index of the fan's origin pivot
            origin_price: Price at the fan's origin pivot
            fan_geometry: Full fan ray geometry dict

        Returns:
            The logged Event object
        """
        event = Event(
            timestamp=timestamp,
            event_type=event_type,
            angle_name=angle_name,
            price=price,
            direction=direction,
            details=details,
            bar_index=bar_index,
            fan_identity=fan_identity,
            priority_label=priority_label,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
            active_angle_prices=active_angle_prices,
            cluster_state=cluster_state,
            current_zone=current_zone,
            zone_highest_close=zone_highest_close,
            zone_lowest_close=zone_lowest_close,
            bars_in_zone=bars_in_zone,
            next_angle_line=next_angle_line,
            is_gap_cross=is_gap_cross,
            is_retro=is_retro,
            anchor_type=anchor_type,
            bounce_rejection=bounce_rejection,
            rest_context=rest_context,
            state_snapshot=state_snapshot,
            anchor_bar_index=anchor_bar_index,
            scale_ratio=scale_ratio,
            anchor_price=anchor_price,
            origin_bar_index=origin_bar_index,
            origin_price=origin_price,
            fan_geometry=fan_geometry
        )
        self.events.append(event)
        return event
    
    def log_angle_touch(
        self,
        timestamp: int,
        price: float,
        angle_name: str,
        candle_analysis: Optional[Dict] = None,
        tolerance_percent: float = 0.1
    ) -> Event:
        """
        Log when price touches an angle level.
        
        Args:
            timestamp: Bar timestamp
            price: Price at touch
            angle_name: Name of angle touched
            candle_analysis: Candle pattern analysis at this bar
            tolerance_percent: How close is considered a "touch"
        """
        return self.log_event(
            timestamp=timestamp,
            event_type=EventType.ANGLE_TOUCH,
            angle_name=angle_name,
            price=price,
            details={
                "candle_analysis": candle_analysis,
                "tolerance_percent": tolerance_percent
            }
        )
    
    def log_angle_breach(
        self,
        timestamp: int,
        price: float,
        angle_name: str,
        direction: str,
        close_count: int = 1
    ) -> Event:
        """
        Log when price breaches an angle level.
        
        Args:
            timestamp: Bar timestamp
            price: Price at breach
            angle_name: Name of angle breached
            direction: Direction of breach ("up" or "down")
            close_count: Number of successive closes in breach direction
        """
        return self.log_event(
            timestamp=timestamp,
            event_type=EventType.ANGLE_BREACH,
            angle_name=angle_name,
            price=price,
            direction=direction,
            details={"close_count": close_count}
        )
    
    def log_angle_reaction(
        self,
        timestamp: int,
        price: float,
        angle_name: str,
        reaction_type: str,
        strength: float = 1.0
    ) -> Event:
        """
        Log when price reacts at an angle level.
        
        Args:
            timestamp: Bar timestamp
            price: Price at reaction
            angle_name: Name of angle
            reaction_type: Type of reaction (e.g., "bounce", "rejection", "consolidation")
            strength: Reaction strength (0.0 to 1.0)
        """
        return self.log_event(
            timestamp=timestamp,
            event_type=EventType.ANGLE_REACTION,
            angle_name=angle_name,
            price=price,
            details={
                "reaction_type": reaction_type,
                "strength": strength
            }
        )
    
    def log_candle_pattern(
        self,
        timestamp: int,
        price: float,
        pattern_name: str,
        pattern_details: Dict
    ) -> Event:
        """
        Log a detected candle pattern.
        
        Args:
            timestamp: Bar timestamp
            price: Close price
            pattern_name: Name of pattern
            pattern_details: Pattern specifics
        """
        return self.log_event(
            timestamp=timestamp,
            event_type=EventType.CANDLE_PATTERN,
            price=price,
            details={
                "pattern_name": pattern_name,
                **pattern_details
            }
        )
    
    def log_indicator_snapshot(
        self,
        timestamp: int,
        indicators: Dict[str, Any]
    ):
        """
        Log a snapshot of indicator values.
        
        Args:
            timestamp: Bar timestamp
            indicators: Dictionary of indicator names to values
        """
        snapshot = {
            "timestamp": timestamp,
            "datetime": datetime.fromtimestamp(timestamp).isoformat() if timestamp else None,
            **indicators
        }
        self.indicator_snapshots.append(snapshot)
    
    def get_events_by_type(self, event_type: EventType) -> List[Event]:
        """Get all events of a specific type"""
        return [e for e in self.events if e.event_type == event_type]
    
    def get_events_for_angle(self, angle_name: str) -> List[Event]:
        """Get all events for a specific angle"""
        return [e for e in self.events if e.angle_name == angle_name]
    
    def get_events_in_range(
        self, 
        start_timestamp: int, 
        end_timestamp: int
    ) -> List[Event]:
        """Get events within a time range"""
        return [
            e for e in self.events 
            if start_timestamp <= e.timestamp <= end_timestamp
        ]
    
    def get_statistics(self) -> Dict:
        """
        Calculate statistics from logged events.
        
        Returns:
            Dictionary of statistics
        """
        stats = {
            "total_events": len(self.events),
            "events_by_type": {},
            "events_by_angle": {},
            "breach_directions": {"up": 0, "down": 0},
            "cluster_stats": {"in_cluster": 0, "out_cluster": 0},
            "vacuum_zones": {} # Tracking velocity between zones
        }
        
        for event in self.events:
            # Count by type
            type_name = event.event_type.value
            stats["events_by_type"][type_name] = stats["events_by_type"].get(type_name, 0) + 1
            
            # Count by angle
            if event.angle_name:
                stats["events_by_angle"][event.angle_name] = \
                    stats["events_by_angle"].get(event.angle_name, 0) + 1
            
            # Count breach directions
            if event.event_type == EventType.BREACH_CONFIRMED and event.direction:
                stats["breach_directions"][event.direction] += 1
                
            # Count cluster state
            if event.cluster_state:
                stats["cluster_stats"]["in_cluster"] += 1
            else:
                stats["cluster_stats"]["out_cluster"] += 1
                
            # Time-Decay and Vacuum tracking can be extrapolated from ZONE_CHANGE events
            if event.event_type == EventType.ZONE_CHANGE and event.current_zone:
                zone_name = event.current_zone
                if zone_name not in stats["vacuum_zones"]:
                    stats["vacuum_zones"][zone_name] = 0
                stats["vacuum_zones"][zone_name] += 1
        
        return stats
    
    def enrich_with_forward_outcomes(self, candles: List[Dict]):
        'Post-process events to calculate forward-looking outcomes (MFE/MAE). Args: candles - The full list of candles used in the simulation.'
        if not self.events or not candles:
            return
            
        # Create a fast lookup for candle index by timestamp
        timestamp_to_idx = {int(c['time']): i for i, c in enumerate(candles)}
        
        for event in self.events:
            if event.event_type.value == "zone_change":
                continue  # ZONE_CHANGE events are excluded from CSV, skip enrichment
            if event.timestamp not in timestamp_to_idx or event.price is None:
                continue
                
            idx = timestamp_to_idx[event.timestamp]
            
            # We need a direction to calculate MFE/MAE. 
            # If the event has a direction (e.g., BREACH_CONFIRMED), use it.
            # Otherwise, we might just log absolute max/min, but MFE/MAE is better.
            # For now, let's calculate absolute max high and min low over next N bars.
            
            def calc_excursions(n_bars: int):
                fix_applied = 0
                end_idx = min(idx + n_bars + 1, len(candles))
                if end_idx <= idx + 1:
                    return None, None, None, None

                future_candles = candles[idx+1:end_idx]
                max_high = max(c['high'] for c in future_candles)
                min_low = min(c['low'] for c in future_candles)

                exc_up = max_high - event.price
                exc_down = event.price - min_low

                # If we have a direction, we can define Favorable vs Adverse
                if event.direction == 'up':
                    mfe = exc_up
                    mae = exc_down
                elif event.direction == 'down':
                    mfe = exc_down
                    mae = exc_up
                else:
                    # Infer direction from event type when possible
                    if event.event_type == EventType.SUPPORT_TEST:
                        # Support bounce goes UP
                        mfe = exc_up
                        mae = exc_down
                        fix_applied += 1
                    elif event.event_type == EventType.RESISTANCE_TEST:
                        # Resistance rejection goes DOWN
                        mfe = exc_down
                        mae = exc_up
                        fix_applied += 1
                    else:
                        # If no direction, we calculate the maximum excursion in both directions
                        # and assign the larger one to MFE and the smaller to MAE.
                        mfe = max(exc_up, exc_down)
                        mae = min(exc_up, exc_down)

                # Ensure MFE and MAE are positive values representing the excursion distance
                mfe = max(0, mfe)
                mae = max(0, mae)
                exc_up = max(0, exc_up)
                exc_down = max(0, exc_down)

                return mfe, mae, exc_up, exc_down

            event.mfe_5, event.mae_5, event.exc_up_5, event.exc_down_5 = calc_excursions(5)
            event.mfe_10, event.mae_10, event.exc_up_10, event.exc_down_10 = calc_excursions(10)
            event.mfe_20, event.mae_20, event.exc_up_20, event.exc_down_20 = calc_excursions(20)
            event.mfe_50, event.mae_50, event.exc_up_50, event.exc_down_50 = calc_excursions(50)

            # First-break reversal detection: did price reverse at the line?
            # Applies to ALL angle division lines (not just 0.25)
            # Only SUPPORT_TEST and RESISTANCE_TEST — NOT TARGET_HIT
            if (event.event_type in (EventType.SUPPORT_TEST, EventType.RESISTANCE_TEST)
                    and event.high_price is not None
                    and event.low_price is not None
                    and event.timestamp in timestamp_to_idx):
                # Determine expected reversal direction
                if event.event_type == EventType.SUPPORT_TEST:
                    expected_dir = 'up'
                elif event.event_type == EventType.RESISTANCE_TEST:
                    expected_dir = 'down'
                else:
                    expected_dir = None

                if expected_dir:
                    event_high = event.high_price
                    event_low = event.low_price
                    bar_idx = timestamp_to_idx[event.timestamp]
                    end_i = min(bar_idx + 10 + 1, len(candles))

                    for i in range(bar_idx + 1, end_i):
                        bar_close = candles[i].get('close', 0)
                        if expected_dir == 'up':
                            if bar_close > event_high:
                                event.reversal_outcome = "WIN"
                                break
                            if bar_close < event_low:
                                event.reversal_outcome = "LOSS"
                                break
                        else:
                            if bar_close < event_low:
                                event.reversal_outcome = "WIN"
                                break
                            if bar_close > event_high:
                                event.reversal_outcome = "LOSS"
                                break

                # Body break: did next bar's close break the test candle's body?
                if (event.event_type in (EventType.SUPPORT_TEST, EventType.RESISTANCE_TEST)
                        and event.close_price is not None
                        and event.timestamp in timestamp_to_idx):
                    bar_idx = timestamp_to_idx[event.timestamp]
                    if bar_idx + 1 < len(candles):
                        next_close = candles[bar_idx + 1].get('close', 0)
                        if event.event_type == EventType.SUPPORT_TEST:
                            event.body_break = next_close > event.close_price
                        else:
                            event.body_break = next_close < event.close_price
                    # else: last bar, body_break stays None

    def export_csv(self, filepath: str):
        'Export events to CSV file, aligned with frontend UI columns and enriched data.'
        if not self.events:
            return
            
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        rows = []
        for i, event in enumerate(self.events):
            # Skip ZONE_CHANGE events to match frontend price interactions table
            if event.event_type.value == "zone_change":
                continue
                
            # Extract fan identity and priority from details if available
            fan_id = event.details.get('fan_id', '') if event.details else ''
            
            # Format datetime like frontend: 3/10/2026, 10:35:00 AM
            dt_str = ""
            if event.timestamp:
                dt = datetime.fromtimestamp(event.timestamp)
                dt_str = dt.strftime("%m/%d/%Y, %I:%M:%S %p")
                
            # Use UI-specific type if available, otherwise fallback to event_type name
            display_type = event.details.get('ui_type', event.event_type.name) if event.details else event.event_type.name
            
            # Format details exactly like frontend
            details_str = ""
            if event.details and 'ui_details' in event.details:
                details_str = str(event.details['ui_details']).replace(',', ';')
            elif event.details and 'details' in event.details:
                details_str = str(event.details['details']).replace(',', ';')

            row = {
                "#": len(rows) + 1,
                "Time": dt_str,
                "Fan": event.fan_identity or fan_id,
                "Fraction": event.angle_name or "",
                "Price": round(event.price, 2) if event.price else "",
                "Type": display_type,
                "Details": details_str,
                "Open": round(event.open_price, 2) if event.open_price is not None else "",
                "High": round(event.high_price, 2) if event.high_price is not None else "",
                "Low": round(event.low_price, 2) if event.low_price is not None else "",
                "Close": round(event.close_price, 2) if event.close_price is not None else "",
                "Active_Angles": json.dumps({k: round(v, 2) for k, v in event.active_angle_prices.items()}) if event.active_angle_prices else "",
                "Cluster": event.cluster_state,
                "Zone": event.current_zone or "",
                "Zone_Highest_Close": round(event.zone_highest_close, 2) if event.zone_highest_close is not None else "",
                "Zone_Lowest_Close": round(event.zone_lowest_close, 2) if event.zone_lowest_close is not None else "",
                "Bars_In_Zone": event.bars_in_zone if event.bars_in_zone is not None else "",
                "Next_Angle_Line": event.next_angle_line or "",
                "Bar_Index": event.bar_index if event.bar_index is not None else "",
                "Priority_Label": event.priority_label or "",
                "Is_Gap_Cross": event.is_gap_cross,
                "Is_Retro": event.is_retro,
                "Anchor_Type": event.anchor_type or "",
                "Instrument": event.instrument or "",
                "Timeframe": event.timeframe or "",
                # Keep these for analysis but place them after main columns
                "MFE_5":  round(event.mfe_5,  4) if event.mfe_5  is not None else "",
                "MAE_5":  round(event.mae_5,  4) if event.mae_5  is not None else "",
                "MFE_10": round(event.mfe_10, 4) if event.mfe_10 is not None else "",
                "MAE_10": round(event.mae_10, 4) if event.mae_10 is not None else "",
                "MFE_20": round(event.mfe_20, 4) if event.mfe_20 is not None else "",
                "MAE_20": round(event.mae_20, 4) if event.mae_20 is not None else "",
                "MFE_50": round(event.mfe_50, 4) if event.mfe_50 is not None else "",
                "MAE_50": round(event.mae_50, 4) if event.mae_50 is not None else "",
                "Raw_Timestamp": event.timestamp,
                "Direction": event.direction or "",
                "Exc_Up_10": round(event.exc_up_10, 4) if event.exc_up_10 is not None else "",
                "Exc_Down_10": round(event.exc_down_10, 4) if event.exc_down_10 is not None else "",
                "Reversal_Outcome": event.reversal_outcome or "",
                "Body_Break": event.body_break if event.body_break is not None else "",
                # Fan geometry context
                "anchor_bar_index": event.anchor_bar_index if event.anchor_bar_index is not None else "",
                "scale_ratio": round(event.scale_ratio, 4) if event.scale_ratio is not None else "",
                "anchor_price": round(event.anchor_price, 2) if event.anchor_price is not None else "",
                "origin_bar_index": event.origin_bar_index if event.origin_bar_index is not None else "",
                "origin_price": round(event.origin_price, 2) if event.origin_price is not None else "",
                # Gann ladder level identity
                "Level_Source": event.level_source or "",
                "Level_Price": round(event.level_price, 4) if event.level_price is not None else "",
                "Level_Square": round(event.level_square, 4) if event.level_square is not None else "",
                "Level_Kind": event.level_kind or "",
                "Level_Degree": event.level_degree if event.level_degree is not None else "",
                "Level_Ring": event.level_ring if event.level_ring is not None else "",
                "Level_Sub_Index": event.level_sub_index if event.level_sub_index is not None else "",
                "Level_Is_Halfway": event.level_is_halfway if event.level_is_halfway is not None else "",
                "Level_Segment_Start": round(event.level_segment_start, 4) if event.level_segment_start is not None else "",
                "Level_Segment_End": round(event.level_segment_end, 4) if event.level_segment_end is not None else "",
                "Price_Scale": event.price_scale if event.price_scale is not None else "",
                "Body_Degree": round(event.body_degree, 4) if event.body_degree is not None else "",
                "Body_Square": event.body_square if event.body_square is not None else "",
                "Breach_Id": event.breach_id or "",
                "Parent_Breach_Id": event.parent_breach_id or "",
            }

            rows.append(row)
        
        if rows:
            # strictly ordered headers to match frontend first
            fieldnames = ["#", "Time", "Fan", "Fraction", "Price", "Type", "Details",
                          "Open", "High", "Low", "Close", "Active_Angles",
                          "Cluster", "Zone", "Zone_Highest_Close", "Zone_Lowest_Close",
                          "Bars_In_Zone", "Next_Angle_Line",
                          "Bar_Index", "Priority_Label", "Is_Gap_Cross", "Is_Retro", "Anchor_Type",
                          "Instrument", "Timeframe",
                          "MFE_5", "MAE_5", "MFE_10", "MAE_10",
                          "MFE_20", "MAE_20", "MFE_50", "MAE_50",
                          "Raw_Timestamp", "Direction",
                          "Exc_Up_10", "Exc_Down_10",
                          "Reversal_Outcome",
                          "Body_Break",
                          "anchor_bar_index", "scale_ratio", "anchor_price", "origin_bar_index", "origin_price",
                          "Level_Source", "Level_Price", "Level_Square", "Level_Kind", "Level_Degree",
                          "Level_Ring", "Level_Sub_Index", "Level_Is_Halfway", "Level_Segment_Start",
                          "Level_Segment_End", "Price_Scale", "Body_Degree", "Body_Square",
                          "Breach_Id", "Parent_Breach_Id"]
            
            with open(path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
    
    def export_json(self, filepath: str):
        'Export events to JSON file.'
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "session_name": self.session_name,
            "event_count": len(self.events),
            "events": [e.to_dict() for e in self.events],
            "indicator_snapshots": self.indicator_snapshots,
            "statistics": self.get_statistics()
        }
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def export_hypothesis_json(self, filepath: str, symbol: str = "", resolution: str = ""):
        'Export events with ALL available descriptive fields for robust Hypothesis Navigator testing.'
        from datetime import datetime, timezone as dt_timezone

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        events_out = []
        for i, event in enumerate(self.events):
            evt = event.to_dict()
            details = evt.get("details") or {}
            fan_id = details.get("fan_id") if details else None

            # Fan identity: prefer explicit fan_identity, then from state_event (details['fan_id'])
            resolved_fan_identity = evt.get("fan_identity") or fan_id
            if not resolved_fan_identity:
                # Try to derive from fan_geometry ray IDs
                fan_geom = evt.get("fan_geometry")
                if fan_geom and fan_geom.get("rays"):
                    for ray in fan_geom["rays"]:
                        rid = ray.get("id", "")
                        if rid.startswith("Fan_"):
                            resolved_fan_identity = rid[4:].replace("_", "-").rsplit("-", 1)[0] if ray.get("fraction") else rid[4:].replace("_", "-")
                            break

            # Event type display name: prefer the new event_type_display_name, then map from enum value
            display_type = evt.get("event_type_display_name") or EVENT_TYPE_DISPLAY_NAMES.get(
                evt.get("event_type", ""), evt.get("event_type", "-")
            )

            # Descriptive details string from CSV export logic
            description = ""
            if details:
                if "ui_details" in details:
                    description = str(details["ui_details"]).replace(",", ";")
                elif "details" in details:
                    description = str(details["details"]).replace(",", ";")

            entry = {
                # Identity
                "event_id": i + 1,
                "event_type": evt.get("event_type"),
                "event_type_display": display_type,

                # Fan identification
                "fan_display": resolved_fan_identity or evt.get("angle_name"),
                "fan_identity": resolved_fan_identity,
                "priority_label": evt.get("priority_label"),
                "fraction": evt.get("angle_name") or (details.get("fraction") if details else None),

                # Timing
                "timestamp": evt.get("timestamp"),
                "datetime": evt.get("datetime"),
                "bar_index": evt.get("bar_index"),
                "resolution": resolution,

                # Price context
                "price": evt.get("price"),
                "direction": evt.get("direction"),
                "open": evt.get("open"),
                "high": evt.get("high"),
                "low": evt.get("low"),
                "close": evt.get("close"),

                # Angle context at this bar
                "active_angle_prices": evt.get("active_angle_prices", {}),
                "next_angle_line": evt.get("next_angle_line"),

                # Structural context
                "cluster_state": evt.get("cluster_state"),
                "current_zone": evt.get("current_zone"),
                "zone_highest_close": evt.get("zone_highest_close"),
                "zone_lowest_close": evt.get("zone_lowest_close"),
                "bars_in_zone": evt.get("bars_in_zone"),

                # Event classification
                "is_gap_cross": evt.get("is_gap_cross"),
                "is_retro": evt.get("is_retro"),
                "anchor_type": evt.get("anchor_type"),

                # Bounce / Rejection / Rest context
                "bounce_rejection": evt.get("bounce_rejection"),
                "rest_context": evt.get("rest_context"),

                # State machine snapshot at time of event
                "state_snapshot": evt.get("state_snapshot"),

                # Descriptive
                "description": description,

                # Forward-looking outcomes (all horizons)
                "mfe_5": evt.get("mfe_5"),
                "mae_5": evt.get("mae_5"),
                "mfe_10": evt.get("mfe_10"),
                "mae_10": evt.get("mae_10"),
                "mfe_20": evt.get("mfe_20"),
                "mae_20": evt.get("mae_20"),
                "mfe_50": evt.get("mfe_50"),
                "mae_50": evt.get("mae_50"),
                "exc_up_10": evt.get("exc_up_10"),
                "exc_down_10": evt.get("exc_down_10"),
                "reversal_outcome": evt.get("reversal_outcome"),
                "body_break": evt.get("body_break"),

                # Instrument identity
                "instrument": evt.get("instrument"),
                "timeframe": evt.get("timeframe"),

                # Raw details (for debugging)
                "details": details,

                # Fan geometry context (for chart rendering)
                "fan_geometry": evt.get("fan_geometry"),
                "anchor_bar_index": evt.get("anchor_bar_index"),
                "scale_ratio": evt.get("scale_ratio"),
                "anchor_price": evt.get("anchor_price"),
                "origin_bar_index": evt.get("origin_bar_index"),
                "origin_price": evt.get("origin_price"),

                # Gann ladder level identity (Phase 2)
                "level_source": evt.get("level_source"),
                "level_price": evt.get("level_price"),
                "level_square": evt.get("level_square"),
                "level_kind": evt.get("level_kind"),
                "level_degree": evt.get("level_degree"),
                "level_ring": evt.get("level_ring"),
                "level_sub_index": evt.get("level_sub_index"),
                "level_is_halfway": evt.get("level_is_halfway"),
                "level_segment_start": evt.get("level_segment_start"),
                "level_segment_end": evt.get("level_segment_end"),
                "price_scale": evt.get("price_scale"),
                "body_degree": evt.get("body_degree"),
                "body_square": evt.get("body_square"),
                "breach_id": evt.get("breach_id"),
                "parent_breach_id": evt.get("parent_breach_id"),
            }
            events_out.append(entry)

        data = {
            "symbol": symbol,
            "resolution": resolution,
            "generated_at": datetime.now(dt_timezone.utc).isoformat(),
            "event_count": len(events_out),
            "events": events_out
        }

        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    def clear(self):
        'Clear all logged events'
        self.events = []
        self.indicator_snapshots = []
