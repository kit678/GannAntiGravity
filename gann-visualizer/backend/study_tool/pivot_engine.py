"""
Pivot Engine - Detects swing highs and lows, creates pivot pairs

This module handles:
- Swing pivot detection using configurable lookback
- Creating inner/outer pivot pairs
- Categorizing pairs as Scenario 1 or 2
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class PivotType(Enum):
    """Type of pivot point"""
    HIGH = "high"
    LOW = "low"


class Scenario(Enum):
    """
    Scenario based on temporal order of pivots:
    - SCENARIO_1: HIGH formed first, LOW formed after (price rising from low)
    - SCENARIO_2: LOW formed first, HIGH formed after (price falling from high)
    """
    SCENARIO_1 = 1  # High first, Low second -> Rising from low
    SCENARIO_2 = 2  # Low first, High second -> Falling from high


@dataclass
class Pivot:
    """Represents a single pivot point"""
    index: int          # Bar index in DataFrame
    timestamp: int      # Unix timestamp
    price: float        # Price level
    pivot_type: PivotType
    
    def to_dict(self) -> Dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "price": self.price,
            "type": self.pivot_type.value
        }


@dataclass
class PivotPair:
    """
    Represents a pair of pivots for angle calculation.
    first_pivot: The pivot that formed earlier in time
    second_pivot: The pivot that formed later in time
    """
    first_pivot: Pivot
    second_pivot: Pivot
    scenario: Scenario
    pair_type: str = "inner"  # "inner" or "outer"
    
    def to_dict(self) -> Dict:
        return {
            "first_pivot": self.first_pivot.to_dict(),
            "second_pivot": self.second_pivot.to_dict(),
            "scenario": self.scenario.value,
            "pair_type": self.pair_type
        }


class PivotEngine:
    """
    Engine for detecting swing pivots and creating pivot pairs.
    
    Usage:
        engine = PivotEngine(df, lookback=10)
        pivots = engine.detect_pivots()
        pairs = engine.create_pivot_pairs(current_price=100.0)
    """
    
    def __init__(self, df: pd.DataFrame, lookback: int = 10):
        """
        Initialize pivot engine.
        
        Args:
            df: DataFrame with OHLCV data (columns: timestamp, open, high, low, close)
            lookback: Number of bars to look back for pivot confirmation
        """
        self.df = df.copy()
        self.lookback = lookback
        self.pivots: List[Pivot] = []
        
        # Ensure required columns exist
        required_cols = ['timestamp', 'high', 'low']
        for col in required_cols:
            if col not in self.df.columns:
                raise ValueError(f"Missing required column: {col}")
        
        # Ensure numeric types
        self.df['high'] = pd.to_numeric(self.df['high'], errors='coerce')
        self.df['low'] = pd.to_numeric(self.df['low'], errors='coerce')
    
    def detect_pivots(self) -> List[Pivot]:
        """
        Detect swing high and low pivots.
        
        A swing high is a high that is higher than the highs of `lookback` bars 
        on both sides.
        A swing low is a low that is lower than the lows of `lookback` bars 
        on both sides.
        
        Returns:
            List of Pivot objects sorted by timestamp
        """
        self.pivots = []
        n = len(self.df)
        lb = self.lookback
        
        for i in range(lb, n - lb):
            # Check for swing high
            is_swing_high = True
            current_high = self.df.iloc[i]['high']
            
            for j in range(1, lb + 1):
                if (self.df.iloc[i - j]['high'] >= current_high or 
                    self.df.iloc[i + j]['high'] >= current_high):
                    is_swing_high = False
                    break
            
            if is_swing_high:
                self.pivots.append(Pivot(
                    index=i,
                    timestamp=int(self.df.iloc[i]['timestamp']),
                    price=current_high,
                    pivot_type=PivotType.HIGH
                ))
            
            # Check for swing low
            is_swing_low = True
            current_low = self.df.iloc[i]['low']
            
            for j in range(1, lb + 1):
                if (self.df.iloc[i - j]['low'] <= current_low or 
                    self.df.iloc[i + j]['low'] <= current_low):
                    is_swing_low = False
                    break
            
            if is_swing_low:
                self.pivots.append(Pivot(
                    index=i,
                    timestamp=int(self.df.iloc[i]['timestamp']),
                    price=current_low,
                    pivot_type=PivotType.LOW
                ))
        
        # Sort by timestamp
        self.pivots.sort(key=lambda p: p.timestamp)
        return self.pivots
    
    def get_recent_pivots(self, current_index: int, count: int = 4) -> List[Pivot]:
        """
        Get the most recent pivots before the current index.
        
        Args:
            current_index: Current bar index
            count: Number of recent pivots to return
            
        Returns:
            List of recent Pivot objects
        """
        recent = [p for p in self.pivots if p.index < current_index]
        return recent[-count:] if len(recent) >= count else recent
    
    def create_pivot_pairs(
        self, 
        current_price: Optional[float] = None,
        current_index: Optional[int] = None
    ) -> List[PivotPair]:
        """
        Create pivot pairs for angle calculation.
        
        Identifies:
        - INNER pair: Most recent high-low pair closest to current price
        - OUTER pair(s): Larger structural pivots
        
        Args:
            current_price: Current market price (optional, for context)
            current_index: Current bar index (optional)
            
        Returns:
            List of PivotPair objects (inner first, then outer)
        """
        if len(self.pivots) < 2:
            return []
        
        pairs = []
        
        # Get all highs and lows
        highs = [p for p in self.pivots if p.pivot_type == PivotType.HIGH]
        lows = [p for p in self.pivots if p.pivot_type == PivotType.LOW]
        
        if not highs or not lows:
            return []
        
        # Find the most recent high and low
        recent_high = highs[-1]
        recent_low = lows[-1]
        
        # Determine which formed first (this determines the scenario)
        if recent_low.timestamp < recent_high.timestamp:
            # Low formed first, High formed after -> Scenario 2 (Falling from high)
            inner_pair = PivotPair(
                first_pivot=recent_low,
                second_pivot=recent_high,
                scenario=Scenario.SCENARIO_2,
                pair_type="inner"
            )
        else:
            # High formed first, Low formed after -> Scenario 1 (Rising from low)
            inner_pair = PivotPair(
                first_pivot=recent_high,
                second_pivot=recent_low,
                scenario=Scenario.SCENARIO_1,
                pair_type="inner"
            )
        
        pairs.append(inner_pair)
        
        # Look for outer pairs (larger structure)
        # Find the overall highest high and lowest low
        if len(highs) >= 2 and len(lows) >= 2:
            # Get second-to-last pivots for outer pair
            outer_highs = [h for h in highs if h != recent_high]
            outer_lows = [l for l in lows if l != recent_low]
            
            if outer_highs and outer_lows:
                # Find the highest high and lowest low among outer pivots
                highest_outer = max(outer_highs, key=lambda p: p.price)
                lowest_outer = min(outer_lows, key=lambda p: p.price)
                
                # Or use the most significant outer pair
                if lowest_outer.timestamp < highest_outer.timestamp:
                    outer_pair = PivotPair(
                        first_pivot=lowest_outer,
                        second_pivot=highest_outer,
                        scenario=Scenario.SCENARIO_2,
                        pair_type="outer"
                    )
                else:
                    outer_pair = PivotPair(
                        first_pivot=highest_outer,
                        second_pivot=lowest_outer,
                        scenario=Scenario.SCENARIO_1,
                        pair_type="outer"
                    )
                
                # Only add if different from inner
                if (outer_pair.first_pivot != inner_pair.first_pivot or 
                    outer_pair.second_pivot != inner_pair.second_pivot):
                    pairs.append(outer_pair)
        
        return pairs
    
    def get_pivots_in_range(
        self, 
        start_timestamp: int, 
        end_timestamp: int
    ) -> List[Pivot]:
        """
        Get all pivots within a time range.
        
        Args:
            start_timestamp: Start of range (Unix timestamp)
            end_timestamp: End of range (Unix timestamp)
            
        Returns:
            List of Pivot objects in the range
        """
        return [
            p for p in self.pivots 
            if start_timestamp <= p.timestamp <= end_timestamp
        ]
    
    def to_dict(self) -> Dict:
        """Export all pivots as dictionary"""
        return {
            "lookback": self.lookback,
            "pivots": [p.to_dict() for p in self.pivots]
        }
