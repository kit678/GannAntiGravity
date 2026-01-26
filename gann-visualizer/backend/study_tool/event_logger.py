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


@dataclass
class Event:
    """Represents a logged event"""
    timestamp: int          # Bar timestamp
    event_type: EventType
    angle_name: Optional[str] = None
    price: Optional[float] = None
    direction: Optional[str] = None  # "up", "down"
    details: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "datetime": datetime.fromtimestamp(self.timestamp).isoformat() if self.timestamp else None,
            "event_type": self.event_type.value,
            "angle_name": self.angle_name,
            "price": self.price,
            "direction": self.direction,
            "details": self.details or {}
        }


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
        details: Optional[Dict] = None
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
            
        Returns:
            The logged Event object
        """
        event = Event(
            timestamp=timestamp,
            event_type=event_type,
            angle_name=angle_name,
            price=price,
            direction=direction,
            details=details
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
            "breach_directions": {"up": 0, "down": 0}
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
        
        return stats
    
    def export_csv(self, filepath: str):
        """
        Export events to CSV file.
        
        Args:
            filepath: Path to output CSV file
        """
        if not self.events:
            return
        
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Flatten events for CSV
        rows = []
        for event in self.events:
            row = event.to_dict()
            # Flatten details into separate columns
            if row.get("details"):
                for key, value in row["details"].items():
                    row[f"detail_{key}"] = value
                del row["details"]
            rows.append(row)
        
        # Write CSV
        if rows:
            fieldnames = list(rows[0].keys())
            # Add all detail fields
            for row in rows:
                for key in row.keys():
                    if key not in fieldnames:
                        fieldnames.append(key)
            
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
