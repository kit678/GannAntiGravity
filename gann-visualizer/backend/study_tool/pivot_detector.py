from dataclasses import dataclass
from typing import List, Dict, Any, Optional

# Global registry to persist pivot counts and labels across instances/rebuilds
# Key: f"{symbol}_{left}_{right}_{resolution}"
# Value: {'high_count': 0, 'low_count': 0, 'pivots': {time: label}}
_PIVOT_REGISTRY = {}

def clear_pivot_registry(key: str = None):
    """Clear the global pivot registry for a specific key or all keys"""
    global _PIVOT_REGISTRY
    if key:
        if key in _PIVOT_REGISTRY:
            del _PIVOT_REGISTRY[key]
    else:
        _PIVOT_REGISTRY = {}

@dataclass
class Pivot:
    """Represents a detected pivot point"""
    time: int           # Unix timestamp (seconds)
    price: float        # Price at pivot (high for pivot high, low for pivot low)
    bar_index: int      # Index in candle array
    pivot_type: str     # 'high' or 'low'
    label: str = ""    # Permanent identity (e.g., 'H1', 'L1')
    close_price: float = None  # Closing price at pivot bar (used for fan origin price)


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
    
    def __init__(self, left_bars: int = 5, right_bars: int = 5, symbol: str = None, resolution: str = None):
        """
        Initialize the pivot detector.
        
        Args:
            left_bars: Number of bars to the left for pivot confirmation
            right_bars: Number of bars to the right for pivot confirmation
            symbol: Ticker symbol (for registry key)
            resolution: Timeframe resolution (for registry key)
        """
        self.left_bars = left_bars
        self.right_bars = right_bars
        
        # Registry key for persistence
        self.registry_key = None
        if symbol:
            res = resolution if resolution else "default"
            self.registry_key = f"{symbol}_{left_bars}_{right_bars}_{res}"
        
        # State for successive pivot filtering
        self.last_high_pivot: Optional[Pivot] = None
        self.last_low_pivot: Optional[Pivot] = None
        self.last_pivot_type: Optional[str] = None
        self.confirmed_pivots: List[Pivot] = []
        
        # Absolute counters for permanent identity mapping
        # Initialize from registry if available
        self.high_count: int = 0
        self.low_count: int = 0
        
        if self.registry_key:
             self._sync_from_registry()
    
    def _sync_from_registry(self):
        """Load counts from global registry, but preserve local counts if they're higher.
        
        This ensures we never regress to lower counts, even if the registry
        was partially cleared or corrupted.
        """
        if not self.registry_key:
            return
            
        if self.registry_key not in _PIVOT_REGISTRY:
            _PIVOT_REGISTRY[self.registry_key] = {
                'high_count': 0, 
                'low_count': 0, 
                'pivots': {} # time -> label
            }
            
        reg = _PIVOT_REGISTRY[self.registry_key]
        reg_high = reg['high_count']
        reg_low = reg['low_count']
        
        # CRITICAL: Only update from registry if counts are higher
        # This prevents accidental count regression
        if reg_high > self.high_count:
            self.high_count = reg_high
        if reg_low > self.low_count:
            self.low_count = reg_low
        
    def _update_registry_counts(self):
        """Update global registry with current counts"""
        if not self.registry_key:
            return
        if self.registry_key not in _PIVOT_REGISTRY:
            _PIVOT_REGISTRY[self.registry_key] = {'high_count': 0, 'low_count': 0, 'pivots': {}}
        _PIVOT_REGISTRY[self.registry_key]['high_count'] = self.high_count
        _PIVOT_REGISTRY[self.registry_key]['low_count'] = self.low_count

    def _get_registry_label(self, time: int, pivot_type: str) -> Optional[str]:
        """Get existing label for a timestamp and type if it exists"""
        if not self.registry_key or self.registry_key not in _PIVOT_REGISTRY:
            return None
        key = f"{time}_{pivot_type}"
        return _PIVOT_REGISTRY[self.registry_key]['pivots'].get(key)

    def _set_registry_label(self, time: int, pivot_type: str, label: str):
        """Save label for a timestamp and type"""
        if not self.registry_key:
            return
        if self.registry_key not in _PIVOT_REGISTRY:
            _PIVOT_REGISTRY[self.registry_key] = {'high_count': 0, 'low_count': 0, 'pivots': {}}
        key = f"{time}_{pivot_type}"
        _PIVOT_REGISTRY[self.registry_key]['pivots'][key] = label

    def _remove_registry_label(self, time: int, pivot_type: str):
        """Remove label for a timestamp (used during replacement)"""
        if not self.registry_key or not time or self.registry_key not in _PIVOT_REGISTRY:
            return
        key = f"{time}_{pivot_type}"
        if key in _PIVOT_REGISTRY[self.registry_key]['pivots']:
            del _PIVOT_REGISTRY[self.registry_key]['pivots'][key]
    
    def release_pivot(self, pivot_time: int, pivot_type: str):
        """
        Release a pivot so it can be reused in a new fan.
        
        When a fan is invalidated, call this to clear the pivot's state.
        The pivot will still retain its label (H1, L1, etc.) for tracking purposes,
        but it will be treated as available for new fan formations.
        
        Args:
            pivot_time: The timestamp of the pivot to release
            pivot_type: 'high' or 'low'
        """
        if pivot_type == 'high' and self.last_high_pivot and self.last_high_pivot.time == pivot_time:
            self.last_high_pivot = None
        elif pivot_type == 'low' and self.last_low_pivot and self.last_low_pivot.time == pivot_time:
            self.last_low_pivot = None
    
    def reset(self, clear_registry: bool = False):
        """
        Reset detector state (call on new symbol/interval).
        Args:
            clear_registry: If True, wipes the global registry for this key (hard reset).
                          If False, attempts to sync from registry (soft reset/rebuild).
        
        NOTE: high_count and low_count are NEVER reset. They persist across the entire
        simulation to ensure unique pivot labels (H1, H2, H3... L1, L2, L3...).
        This prevents the same pivot labels from being reused after fan invalidation.
        """
        self.last_high_pivot = None
        self.last_low_pivot = None
        self.last_pivot_type = None
        self.confirmed_pivots = []
        
        if clear_registry and self.registry_key:
            if self.registry_key in _PIVOT_REGISTRY:
                del _PIVOT_REGISTRY[self.registry_key]
        
        # CRITICAL FIX: Never reset high_count and low_count.
        # They must persist across the entire simulation to ensure:
        # 1. Each pivot has a unique label (H1, H2, H3...)
        # 2. Pivot labels are not reused after fan invalidation
        # 3. H1-L1, H2-L1, H2-L2, H3-L2... are all different fans
        
        # Only sync from registry if it exists (to restore counts after crash recovery)
        if self.registry_key and not clear_registry:
            self._sync_from_registry()
        # If clear_registry=True, we keep our current counts (they're preserved)
    
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
        candidate_close = float(candidate.get('close', candidate['high']))
        candidate_time = int(candidate['time'])
        
        # Check for pivot high
        is_pivot_high = True
        high_fail_reason = ""
        for i in range(1, self.left_bars + 1):
            if float(candles[candidate_idx - i]['high']) >= candidate_high:
                is_pivot_high = False
                high_fail_reason = f"Left neighbor -{i} >= candidate"
                break
        
        if is_pivot_high:
            for i in range(1, self.right_bars + 1):
                if float(candles[candidate_idx + i]['high']) >= candidate_high:
                    is_pivot_high = False
                    high_fail_reason = f"Right neighbor +{i} >= candidate"
                    break
        
        # Check for pivot low
        is_pivot_low = True
        low_fail_reason = ""
        for i in range(1, self.left_bars + 1):
            if float(candles[candidate_idx - i]['low']) <= candidate_low:
                is_pivot_low = False
                low_fail_reason = f"Left neighbor -{i} <= candidate"
                break
        
        if is_pivot_low:
            for i in range(1, self.right_bars + 1):
                if float(candles[candidate_idx + i]['low']) <= candidate_low:
                    is_pivot_low = False
                    low_fail_reason = f"Right neighbor +{i} <= candidate"
                    break
        
        if is_pivot_high:
             # print(f"[PivotDetector] FOUND RAW HIGH at {candidate_time} Price: {candidate_high}")
             pass
        if is_pivot_low:
             # print(f"[PivotDetector] FOUND RAW LOW at {candidate_time} Price: {candidate_low}")
             pass
        
        # Process detected pivots - add to confirmed_pivots IMMEDIATELY
        # Successive filtering: if same type as last, replace if better (higher high / lower low)
        
        if is_pivot_high:
            new_pivot = Pivot(
                time=candidate_time,
                price=candidate_high,
                bar_index=candidate_idx,
                pivot_type='high',
                close_price=candidate_close
            )
            
            # DEBUG LOG
            # print(f"DEBUG: Found High Pivot at {candidate_idx} price {candidate_high}")
            
            if self.last_pivot_type == 'high' and self.last_high_pivot is not None:
                # Same type as last - successive filtering
                if new_pivot.price > self.last_high_pivot.price:
                    # New high is higher - REPLACE the last one in confirmed_pivots. Inherit previous label.
                    new_pivot.label = self.last_high_pivot.label
                    
                    # Update Registry: Move label to new timestamp
                    self._remove_registry_label(self.last_high_pivot.time, 'high')
                    self._set_registry_label(new_pivot.time, 'high', new_pivot.label)
                    
                    if self.confirmed_pivots and self.confirmed_pivots[-1].pivot_type == 'high':
                        self.confirmed_pivots[-1] = new_pivot
                    self.last_high_pivot = new_pivot
                # else: ignore this lower high
            else:
                # Different type or first pivot - add immediately
                
                # Check global registry for existing label (Rebuild Persistence)
                existing_label = self._get_registry_label(new_pivot.time, 'high')
                
                if existing_label:
                    new_pivot.label = existing_label
                    # Do not increment high_count, as we are reusing an existing ID
                else:
                    self.high_count += 1
                    new_pivot.label = f"H{self.high_count}"
                    self._set_registry_label(new_pivot.time, 'high', new_pivot.label)
                    self._update_registry_counts()
                
                self.confirmed_pivots.append(new_pivot)
                self.last_high_pivot = new_pivot
                self.last_pivot_type = 'high'
                
                # Generate fan signal if we have a preceding low
                if self.last_low_pivot is not None:
                    result['new_fan'] = {
                        'from': {
                            'time': self.last_low_pivot.time,
                            'price': self.last_low_pivot.price,
                            'bar_index': self.last_low_pivot.bar_index,
                            'type': 'low',
                            'label': self.last_low_pivot.label
                        },
                        'to': {
                            'time': new_pivot.time,
                            'price': new_pivot.price,
                            'bar_index': new_pivot.bar_index,
                            'type': 'high',
                            'label': new_pivot.label
                        }
                    }
            
            result['pivot_high'] = new_pivot
        
        if is_pivot_low:
            new_pivot = Pivot(
                time=candidate_time,
                price=candidate_low,
                bar_index=candidate_idx,
                pivot_type='low',
                close_price=candidate_close
            )

            # DEBUG LOG
            # print(f"DEBUG: Found Low Pivot at {candidate_idx} price {candidate_low}")
            
            if self.last_pivot_type == 'low' and self.last_low_pivot is not None:
                # Same type as last - successive filtering
                if new_pivot.price < self.last_low_pivot.price:
                    # New low is lower - REPLACE the last one in confirmed_pivots. Inherit previous label.
                    new_pivot.label = self.last_low_pivot.label
                    
                    # Update Registry: Move label to new timestamp
                    self._remove_registry_label(self.last_low_pivot.time, 'low')
                    self._set_registry_label(new_pivot.time, 'low', new_pivot.label)
                    
                    if self.confirmed_pivots and self.confirmed_pivots[-1].pivot_type == 'low':
                        self.confirmed_pivots[-1] = new_pivot
                    self.last_low_pivot = new_pivot
                # else: ignore this higher low
            else:
                # Different type or first pivot - add immediately
                
                # Check global registry for existing label (Rebuild Persistence)
                existing_label = self._get_registry_label(new_pivot.time, 'low')
                
                if existing_label:
                    new_pivot.label = existing_label
                    # Do not increment low_count
                else:
                    self.low_count += 1
                    new_pivot.label = f"L{self.low_count}"
                    self._set_registry_label(new_pivot.time, 'low', new_pivot.label)
                    self._update_registry_counts()
                
                self.confirmed_pivots.append(new_pivot)
                self.last_low_pivot = new_pivot
                self.last_pivot_type = 'low'
                
                # Generate fan signal if we have a preceding high
                if self.last_high_pivot is not None:
                    result['new_fan'] = {
                        'from': {
                            'time': self.last_high_pivot.time,
                            'price': self.last_high_pivot.price,
                            'bar_index': self.last_high_pivot.bar_index,
                            'type': 'high',
                            'label': self.last_high_pivot.label
                        },
                        'to': {
                            'time': new_pivot.time,
                            'price': new_pivot.price,
                            'bar_index': new_pivot.bar_index,
                            'type': 'low',
                            'label': new_pivot.label
                        }
                    }
            
            result['pivot_low'] = new_pivot
        
        return result
    
    def get_state(self) -> Dict[str, Any]:
        """Get current detector state for serialization"""
        return {
            'last_high_pivot': {
                'time': self.last_high_pivot.time,
                'price': self.last_high_pivot.price,
                'bar_index': self.last_high_pivot.bar_index,
                'pivot_type': 'high',
                'label': self.last_high_pivot.label
            } if self.last_high_pivot else None,
            'last_low_pivot': {
                'time': self.last_low_pivot.time,
                'price': self.last_low_pivot.price,
                'bar_index': self.last_low_pivot.bar_index,
                'pivot_type': 'low',
                'label': self.last_low_pivot.label
            } if self.last_low_pivot else None,
            'last_pivot_type': self.last_pivot_type,
            'high_count': self.high_count,
            'low_count': self.low_count,
            'confirmed_pivots': [
                {
                    'time': p.time,
                    'price': p.price,
                    'bar_index': p.bar_index,
                    'pivot_type': p.pivot_type,
                    'label': p.label
                } for p in self.confirmed_pivots
            ]
        }
    
    def restore_state(self, state: Dict[str, Any]):
        """Restore detector state from serialized form"""
        # print(f"[PivotDetector] Restoring state. Counts in state: H={state.get('high_count')} L={state.get('low_count')}")
        
        if state.get('last_high_pivot'):
            hp = state['last_high_pivot']
            self.last_high_pivot = Pivot(
                time=hp['time'],
                price=hp['price'],
                bar_index=hp['bar_index'],
                pivot_type='high',
                label=hp.get('label', "")
            )
        else:
            self.last_high_pivot = None
        
        if state.get('last_low_pivot'):
            lp = state['last_low_pivot']
            self.last_low_pivot = Pivot(
                time=lp['time'],
                price=lp['price'],
                bar_index=lp['bar_index'],
                pivot_type='low',
                label=lp.get('label', "")
            )
        else:
            self.last_low_pivot = None
        
        self.last_pivot_type = state.get('last_pivot_type')
        
        # Restore counters - CRITICAL for maintaining label continuity
        self.high_count = state.get('high_count', 0)
        self.low_count = state.get('low_count', 0)
        
        # print(f"[PivotDetector] Restored counters: H={self.high_count} L={self.low_count}")
        
        self.confirmed_pivots = []
        if state.get('confirmed_pivots'):
            for p in state['confirmed_pivots']:
                self.confirmed_pivots.append(Pivot(
                    time=p['time'],
                    price=p['price'],
                    bar_index=p['bar_index'],
                    pivot_type=p['pivot_type'],
                    label=p.get('label', "")
                ))
