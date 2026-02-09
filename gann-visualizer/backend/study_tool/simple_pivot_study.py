"""
Simple Pivot Detection Study

Detects pivot highs and pivot lows using left/right bar validation.
Uses the exact same mechanism as the Angular Price Coverage Strategy.

A pivot high is confirmed when the high at bar[i] is strictly greater than
the highs of all bars within [i - leftBars, i + rightBars].

A pivot low is confirmed when the low at bar[i] is strictly less than
the lows of all bars within [i - leftBars, i + rightBars].
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class PivotPoint:
    """Represents a detected pivot point"""
    time: int           # Unix timestamp (seconds)
    price: float        # Price at pivot
    pivot_type: str     # 'high' or 'low'
    bar_index: int      # Index in candle array


class SimplePivotStudy:
    """
    Simple Pivot Detection Study
    
    Detects and marks pivot highs and lows on the chart using
    the same left/right bar validation as the Angular Price Coverage Strategy.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        config = config or {}
        self.left_bars = config.get('left_bars', 5)
        self.right_bars = config.get('right_bars', 5)
        
        # State tracking
        self.confirmed_pivots: List[PivotPoint] = []
        self.last_processed_index = -1
        self._state_cache = None
        
    def process_bar(self, candles: List[Dict], bar_index: int, state: Optional[Dict] = None) -> Dict:
        """
        Process a single bar and detect newly confirmed pivots.
        
        Pivots are confirmed with a delay of `right_bars` since we need
        future bars to confirm a pivot.
        
        Returns:
            Dict with pivot_markers and state
        """
        # Restore state if provided
        if state:
            self.restore_state(state)
            
        output_markers = []
        
        # The candidate bar index for pivot confirmation
        # A pivot at bar[candidate_idx] is confirmed when we have seen bar[candidate_idx + right_bars]
        candidate_idx = bar_index - self.right_bars
        
        # Check if we have enough bars and haven't already processed this candidate
        if candidate_idx >= self.left_bars and candidate_idx > self.last_processed_index:
            # Check for pivot high
            is_pivot_high = self._check_pivot_high(candles, candidate_idx)
            
            # Check for pivot low
            is_pivot_low = self._check_pivot_low(candles, candidate_idx)
            
            candidate_candle = candles[candidate_idx]
            
            if is_pivot_high:
                pivot = PivotPoint(
                    time=candidate_candle['time'],
                    price=candidate_candle['high'],
                    pivot_type='high',
                    bar_index=candidate_idx
                )
                self.confirmed_pivots.append(pivot)
                
                # Create marker for frontend
                marker_id = f"pivot_high_{pivot.time}"
                output_markers.append({
                    'id': marker_id,
                    'type': 'pivot_high',
                    'time': pivot.time,
                    'price': pivot.price,
                    'bar_index': pivot.bar_index
                })
                
            if is_pivot_low:
                pivot = PivotPoint(
                    time=candidate_candle['time'],
                    price=candidate_candle['low'],
                    pivot_type='low',
                    bar_index=candidate_idx
                )
                self.confirmed_pivots.append(pivot)
                
                # Create marker for frontend
                marker_id = f"pivot_low_{pivot.time}"
                output_markers.append({
                    'id': marker_id,
                    'type': 'pivot_low',
                    'time': pivot.time,
                    'price': pivot.price,
                    'bar_index': pivot.bar_index
                })
            
            self.last_processed_index = candidate_idx
        
        # Return results in study format
        return {
            'drawings': [],  # No line drawings for simple pivot study
            'pivot_markers': output_markers,
            'remove_drawings': [],
            'state': self._get_state()
        }
    
    def _check_pivot_high(self, candles: List[Dict], idx: int) -> bool:
        """Check if bar at idx is a pivot high"""
        candidate_high = candles[idx]['high']
        
        # Check left bars
        for i in range(1, self.left_bars + 1):
            if idx - i < 0:
                return False
            if candles[idx - i]['high'] >= candidate_high:
                return False
        
        # Check right bars
        for i in range(1, self.right_bars + 1):
            if idx + i >= len(candles):
                return False
            if candles[idx + i]['high'] >= candidate_high:
                return False
        
        return True
    
    def _check_pivot_low(self, candles: List[Dict], idx: int) -> bool:
        """Check if bar at idx is a pivot low"""
        candidate_low = candles[idx]['low']
        
        # Check left bars
        for i in range(1, self.left_bars + 1):
            if idx - i < 0:
                return False
            if candles[idx - i]['low'] <= candidate_low:
                return False
        
        # Check right bars
        for i in range(1, self.right_bars + 1):
            if idx + i >= len(candles):
                return False
            if candles[idx + i]['low'] <= candidate_low:
                return False
        
        return True
    
    def _get_state(self) -> Dict:
        """Get current state for caching"""
        return {
            'left_bars': self.left_bars,
            'right_bars': self.right_bars,
            'last_processed_index': self.last_processed_index,
            'confirmed_pivots_count': len(self.confirmed_pivots)
        }
    
    def restore_state(self, state: Dict):
        """Restore state from cache"""
        if not state:
            return
        # Note: We don't restore confirmed_pivots as they're regenerated on reset
        self.last_processed_index = state.get('last_processed_index', -1)
