"""
Pivot Detection Module

Detects pivot highs and lows using left/right bar validation.
Implements successive pivot filtering (keeps highest high / lowest low when
consecutive pivots are of the same type).

Based on reference implementation from PivotHighLowAngles.js
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class Pivot:
    """Represents a detected pivot point"""
    time: int           # Unix timestamp (seconds)
    price: float        # Price at pivot
    bar_index: int      # Index in candle array
    pivot_type: str     # 'high' or 'low'


class PivotDetector:
    """
    Detects pivot highs and lows from OHLC candle data.
    
    A pivot high is confirmed when the high at bar[i] is greater than
    the highs of all bars within [i-left_bars, i+right_bars].
    
    A pivot low is confirmed when the low at bar[i] is less than
    the lows of all bars within [i-left_bars, i+right_bars].
    
    Successive pivot filtering: When two consecutive pivots are of the
    same type, only the most extreme is kept (highest high / lowest low).
    """
    
    def __init__(self, left_bars: int = 5, right_bars: int = 5):
        """
        Initialize the pivot detector.
        
        Args:
            left_bars: Number of bars to the left for pivot confirmation
            right_bars: Number of bars to the right for pivot confirmation
        """
        self.left_bars = left_bars
        self.right_bars = right_bars
        
        # State for successive pivot filtering
        self.last_high_pivot: Optional[Pivot] = None
        self.last_low_pivot: Optional[Pivot] = None
        self.last_pivot_type: Optional[str] = None
    
    def reset(self):
        """Reset detector state (call on new symbol/interval)"""
        self.last_high_pivot = None
        self.last_low_pivot = None
        self.last_pivot_type = None
    
    def detect_pivots(self, candles: List[Dict[str, Any]], current_index: int) -> Dict[str, Any]:
        """
        Detect pivot at the candidate index (current_index - right_bars).
        
        Args:
            candles: List of candle dicts with 'time', 'open', 'high', 'low', 'close'
            current_index: Current bar index (we check right_bars behind)
            
        Returns:
            Dict with:
                - pivot_high: Pivot object if detected, None otherwise
                - pivot_low: Pivot object if detected, None otherwise
                - new_fan: Dict with 'from' and 'to' pivots if a new fan should be drawn
        """
        result = {
            'pivot_high': None,
            'pivot_low': None,
            'new_fan': None
        }
        
        # Need enough bars for confirmation
        min_bars_needed = self.left_bars + self.right_bars + 1
        if current_index < min_bars_needed - 1:
            return result
        
        # Candidate index is right_bars behind current
        candidate_idx = current_index - self.right_bars
        
        if candidate_idx < self.left_bars:
            return result
        
        candidate = candles[candidate_idx]
        candidate_high = float(candidate['high'])
        candidate_low = float(candidate['low'])
        candidate_time = int(candidate['time'])
        
        # Check for pivot high
        is_pivot_high = True
        for i in range(1, self.left_bars + 1):
            if float(candles[candidate_idx - i]['high']) >= candidate_high:
                is_pivot_high = False
                break
        
        if is_pivot_high:
            for i in range(1, self.right_bars + 1):
                if float(candles[candidate_idx + i]['high']) >= candidate_high:
                    is_pivot_high = False
                    break
        
        # Check for pivot low
        is_pivot_low = True
        for i in range(1, self.left_bars + 1):
            if float(candles[candidate_idx - i]['low']) <= candidate_low:
                is_pivot_low = False
                break
        
        if is_pivot_low:
            for i in range(1, self.right_bars + 1):
                if float(candles[candidate_idx + i]['low']) <= candidate_low:
                    is_pivot_low = False
                    break
        
        # Process confirmed pivots with successive filtering
        if is_pivot_high:
            new_pivot = Pivot(
                time=candidate_time,
                price=candidate_high,
                bar_index=candidate_idx,
                pivot_type='high'
            )
            
            # Successive high filter: keep the highest
            if self.last_pivot_type == 'high':
                if new_pivot.price > self.last_high_pivot.price:
                    # Replace with higher high
                    self.last_high_pivot = new_pivot
            else:
                # Alternate type - complete a fan pair
                if self.last_low_pivot is not None:
                    result['new_fan'] = {
                        'from': {
                            'time': self.last_low_pivot.time,
                            'price': self.last_low_pivot.price,
                            'bar_index': self.last_low_pivot.bar_index,
                            'type': 'low'
                        },
                        'to': {
                            'time': new_pivot.time,
                            'price': new_pivot.price,
                            'bar_index': new_pivot.bar_index,
                            'type': 'high'
                        }
                    }
                
                self.last_high_pivot = new_pivot
                self.last_pivot_type = 'high'
            
            result['pivot_high'] = new_pivot
        
        if is_pivot_low:
            new_pivot = Pivot(
                time=candidate_time,
                price=candidate_low,
                bar_index=candidate_idx,
                pivot_type='low'
            )
            
            # Successive low filter: keep the lowest
            if self.last_pivot_type == 'low':
                if new_pivot.price < self.last_low_pivot.price:
                    # Replace with lower low
                    self.last_low_pivot = new_pivot
            else:
                # Alternate type - complete a fan pair
                if self.last_high_pivot is not None:
                    result['new_fan'] = {
                        'from': {
                            'time': self.last_high_pivot.time,
                            'price': self.last_high_pivot.price,
                            'bar_index': self.last_high_pivot.bar_index,
                            'type': 'high'
                        },
                        'to': {
                            'time': new_pivot.time,
                            'price': new_pivot.price,
                            'bar_index': new_pivot.bar_index,
                            'type': 'low'
                        }
                    }
                
                self.last_low_pivot = new_pivot
                self.last_pivot_type = 'low'
            
            result['pivot_low'] = new_pivot
        
        return result
    
    def get_state(self) -> Dict[str, Any]:
        """Get current detector state for serialization"""
        return {
            'last_high_pivot': {
                'time': self.last_high_pivot.time,
                'price': self.last_high_pivot.price,
                'bar_index': self.last_high_pivot.bar_index
            } if self.last_high_pivot else None,
            'last_low_pivot': {
                'time': self.last_low_pivot.time,
                'price': self.last_low_pivot.price,
                'bar_index': self.last_low_pivot.bar_index
            } if self.last_low_pivot else None,
            'last_pivot_type': self.last_pivot_type
        }
    
    def restore_state(self, state: Dict[str, Any]):
        """Restore detector state from serialized form"""
        if state.get('last_high_pivot'):
            hp = state['last_high_pivot']
            self.last_high_pivot = Pivot(
                time=hp['time'],
                price=hp['price'],
                bar_index=hp['bar_index'],
                pivot_type='high'
            )
        else:
            self.last_high_pivot = None
        
        if state.get('last_low_pivot'):
            lp = state['last_low_pivot']
            self.last_low_pivot = Pivot(
                time=lp['time'],
                price=lp['price'],
                bar_index=lp['bar_index'],
                pivot_type='low'
            )
        else:
            self.last_low_pivot = None
        
        self.last_pivot_type = state.get('last_pivot_type')
