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
    """Types of events to log"""
    ANGLE_TOUCH = "angle_touch"
    ANGLE_BREACH = "angle_breach"
    ANGLE_REACTION = "angle_reaction"
    HORIZONTAL_TOUCH = "horizontal_touch"
    HORIZONTAL_BREACH = "horizontal_breach"
    PIVOT_FORMED = "pivot_formed"
    MOMENTUM_CHANGE = "momentum_change"
    REVERSAL_SIGNAL = "reversal_signal"
    CANDLE_PATTERN = "candle_pattern"
    # New event types for price movement tracking
    BREACH_CONFIRMED = "breach_confirmed"    # N successive closes achieved
    ANGLE_REVERSAL = "angle_reversal"        # Successive close streak broken — price reversed
    FAKE_OUT = "fake_out"                    # Price crossed the line but immediately failed
    REST_ON_ANGLE = "rest_on_angle"          # Price rests on angle after breach
    TARGET_HIT = "target_hit"               # Target in progression sequence reached
    TARGET_FAILED = "target_failed"         # Failed to reach target, crossed back
    FAN_VALIDATED = "fan_validated"           # Fan validated via 7/8 interaction
    ZONE_CHANGE = "zone_change"              # Price moved to a new angle zone
    
    # Frontend Alignment Types (for direct CSV compatibility)
    TOUCH = "TOUCH"
    CROSS_UP = "CROSS_UP"
    CROSS_DOWN = "CROSS_DOWN"
    SUPPORT_TEST = "SUPPORT_TEST"
    RESISTANCE_TEST = "RESISTANCE_TEST"
    SUPPORT_BOUNCE = "SUPPORT_BOUNCE"  # Price successfully bounced from support
    RESISTANCE_REJECTION = "RESISTANCE_REJECTION"  # Price successfully rejected from resistance
    FAN_DEACTIVATED = "FAN_DEACTIVATED"  # Fan deactivated/completed (not invalidated)


@dataclass
class Event:
    """Represents a logged event"""
    timestamp: int          # Bar timestamp
    event_type: EventType
    angle_name: Optional[str] = None
    price: Optional[float] = None
    direction: Optional[str] = None  # "up", "down"
    details: Optional[Dict] = None

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

    # Target Progression Info
    next_angle_line: Optional[str] = None

    # Forward-looking outcomes (populated post-simulation)
    mfe_10: Optional[float] = None  # Max Favorable Excursion (next 10 bars)
    mae_10: Optional[float] = None  # Max Adverse Excursion (next 10 bars)
    mfe_20: Optional[float] = None  # Max Favorable Excursion (next 20 bars)
    mae_20: Optional[float] = None  # Max Adverse Excursion (next 20 bars)

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "datetime": datetime.fromtimestamp(self.timestamp).isoformat() if self.timestamp else None,
            "event_type": self.event_type.value,
            "angle_name": self.angle_name,
            "price": self.price,
            "direction": self.direction,
            "open": self.open_price,
            "high": self.high_price,
            "low": self.low_price,
            "close": self.close_price,
            "active_angle_prices": self.active_angle_prices or {},
            "cluster_state": self.cluster_state,
            "current_zone": self.current_zone,
            "zone_highest_close": self.zone_highest_close,
            "zone_lowest_close": self.zone_lowest_close,
            "next_angle_line": self.next_angle_line,
            "mfe_10": self.mfe_10,
            "mae_10": self.mae_10,
            "mfe_20": self.mfe_20,
            "mae_20": self.mae_20,
            "details": self.details or {}
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Event':
        event = cls()
        event.timestamp = data.get("timestamp")
        
        # Handle event_type conversion
        evt_type_val = data.get("event_type")
        try:
            event.event_type = EventType(evt_type_val)
        except ValueError:
            # Fallback if somehow invalid
            event.event_type = EventType.TOUCH
            
        event.angle_name = data.get("angle_name")
        event.price = data.get("price")
        event.direction = data.get("direction")
        event.open_price = data.get("open")
        event.high_price = data.get("high")
        event.low_price = data.get("low")
        event.close_price = data.get("close")
        event.active_angle_prices = data.get("active_angle_prices", {})
        event.cluster_state = data.get("cluster_state", False)
        event.current_zone = data.get("current_zone")
        event.zone_highest_close = data.get("zone_highest_close")
        event.zone_lowest_close = data.get("zone_lowest_close")
        event.next_angle_line = data.get("next_angle_line")
        event.mfe_10 = data.get("mfe_10")
        event.mae_10 = data.get("mae_10")
        event.mfe_20 = data.get("mfe_20")
        event.mae_20 = data.get("mae_20")
        event.details = data.get("details", {})
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
        open_price: Optional[float] = None,
        high_price: Optional[float] = None,
        low_price: Optional[float] = None,
        close_price: Optional[float] = None,
        active_angle_prices: Optional[Dict[str, float]] = None,
        cluster_state: Optional[bool] = False,
        current_zone: Optional[str] = None,
        zone_highest_close: Optional[float] = None,
        zone_lowest_close: Optional[float] = None,
        next_angle_line: Optional[str] = None
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
            open_price: Candle Open
            high_price: Candle High
            low_price: Candle Low
            close_price: Candle Close
            active_angle_prices: Dictionary of all current angle prices for the fan
            cluster_state: Whether price is in a cluster/consolidation
            current_zone: The zone the price is in
            zone_highest_close: Highest close price within the zone
            zone_lowest_close: Lowest close price within the zone
            next_angle_line: Last angle line touched/crossed

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
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
            active_angle_prices=active_angle_prices,
            cluster_state=cluster_state,
            current_zone=current_zone,
            zone_highest_close=zone_highest_close,
            zone_lowest_close=zone_lowest_close,
            next_angle_line=next_angle_line
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
            if event.event_type == EventType.ANGLE_BREACH and event.direction:
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
        """
        Post-process events to calculate forward-looking outcomes (MFE/MAE).
        This is crucial for strategy formulation and ML data collection.
        
        Args:
            candles: The full list of candles used in the simulation.
        """
        if not self.events or not candles:
            return
            
        # Create a fast lookup for candle index by timestamp
        timestamp_to_idx = {int(c['time']): i for i, c in enumerate(candles)}
        
        for event in self.events:
            if event.timestamp not in timestamp_to_idx or event.price is None:
                continue
                
            idx = timestamp_to_idx[event.timestamp]
            
            # We need a direction to calculate MFE/MAE. 
            # If the event has a direction (e.g., BREACH_CONFIRMED), use it.
            # Otherwise, we might just log absolute max/min, but MFE/MAE is better.
            # For now, let's calculate absolute max high and min low over next N bars.
            
            def calc_excursions(n_bars: int):
                end_idx = min(idx + n_bars + 1, len(candles))
                if end_idx <= idx + 1:
                    return None, None
                    
                future_candles = candles[idx+1:end_idx]
                max_high = max(c['high'] for c in future_candles)
                min_low = min(c['low'] for c in future_candles)
                
                # If we have a direction, we can define Favorable vs Adverse
                if event.direction == 'up':
                    mfe = max_high - event.price
                    mae = event.price - min_low
                elif event.direction == 'down':
                    mfe = event.price - min_low
                    mae = max_high - event.price
                else:
                    # If no direction, we calculate the maximum excursion in both directions
                    # and assign the larger one to MFE and the smaller to MAE.
                    # This represents the "potential" of the move regardless of direction.
                    exc_up = max_high - event.price
                    exc_down = event.price - min_low
                    mfe = max(exc_up, exc_down)
                    mae = min(exc_up, exc_down)
                    
                # Ensure MFE and MAE are positive values representing the excursion distance
                mfe = max(0, mfe)
                mae = max(0, mae)
                    
                return mfe, mae

            event.mfe_10, event.mae_10 = calc_excursions(10)
            event.mfe_20, event.mae_20 = calc_excursions(20)

    def export_csv(self, filepath: str):
        """
        Export events to CSV file, aligned with frontend UI columns and enriched data.
        
        Args:
            filepath: Path to output CSV file
        """
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
                "Fan": fan_id,
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
                "Next_Angle_Line": event.next_angle_line or "",
                # Keep these for analysis but place them after main columns
                "MFE_10": round(event.mfe_10, 2) if event.mfe_10 is not None else "",
                "MAE_10": round(event.mae_10, 2) if event.mae_10 is not None else "",
                "MFE_20": round(event.mfe_20, 2) if event.mfe_20 is not None else "",
                "MAE_20": round(event.mae_20, 2) if event.mae_20 is not None else "",
                "Raw_Timestamp": event.timestamp,
                "Direction": event.direction or ""
            }

            rows.append(row)
        
        if rows:
            # strictly ordered headers to match frontend first
            fieldnames = ["#", "Time", "Fan", "Fraction", "Price", "Type", "Details",
                          "Open", "High", "Low", "Close", "Active_Angles",
                          "Cluster", "Zone", "Zone_Highest_Close", "Zone_Lowest_Close",
                          "Next_Angle_Line",
                          "MFE_10", "MAE_10", "MFE_20", "MAE_20", "Raw_Timestamp", "Direction"]
            
            with open(path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
    
    def export_json(self, filepath: str):
        """
        Export events to JSON file.
        
        Args:
            filepath: Path to output JSON file
        """
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
    
    def clear(self):
        """Clear all logged events"""
        self.events = []
        self.indicator_snapshots = []
