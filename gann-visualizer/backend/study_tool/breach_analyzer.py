"""
Breach Analyzer Module (v4.0)

Implements Extreme-Close Confirmation state machine and advanced ML metrics:
- Touch (Test/Rejection)
- Unconfirmed Breach (Breakout)
- Confirmed Breach (Close beyond breaching candle's extreme)
- Reversal (Failed Breakout / Fake-out)
- Rest (Consolidation)
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass

@dataclass
class BreachConfirmation:
    fan_id: str
    angle_name: str
    breach_direction: str
    confirmation_price: float
    bars_elapsed: int
    first_breach_bar: int
    confirmation_bar: int
    distance_from_origin: int
    angle_slope: float

    def to_dict(self):
        return self.__dict__

@dataclass
class AngleReversal:
    fan_id: str
    angle_name: str
    attempted_direction: str
    reversal_bar: int
    bars_elapsed: int

    def to_dict(self):
        return self.__dict__

@dataclass
class RestEvent:
    fan_id: str
    angle_name: str
    rest_price: float
    rest_bar: int
    bars_elapsed: int

    def to_dict(self):
        return self.__dict__

class BreachAnalyzer:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.rest_tolerance = config.get('rest_tolerance_percent', 0.15) / 100.0
        self.rest_required_bars = config.get('rest_required_bars', 3)
        
        # State tracking
        self.active_breaches: Dict[str, Dict[str, Any]] = {}  # fan_id_line_id -> state dict
        self.rest_counters: Dict[str, int] = {}               # fan_id_line_id -> consecutive rest bars

    def process_bar(
        self, 
        current_candle: Dict[str, Any], 
        bar_index: int, 
        intersection_events: list, 
        active_fans: dict
    ) -> Dict[str, List[Any]]:
        
        results = {
            'confirmations': [], 
            'reversals': [], 
            'rest_events': []
        }
        
        close_price = float(current_candle.get('close', 0))
        open_price = float(current_candle.get('open', 0))
        high_price = float(current_candle.get('high', 0))
        low_price = float(current_candle.get('low', 0))

        # 1. Process Intersections for new Unconfirmed Breaches or Rest events
        for event in intersection_events:
            if event.fan_id not in active_fans:
                continue
                
            fan_obj = active_fans[event.fan_id]
            line_id = event.line_id
            state_key = f"{event.fan_id}_{line_id}"
            
            # Calculate line price at current bar
            line_price = event.price
            
            # Check for Rest (Consolidation)
            price_range_mid = (open_price + close_price) / 2
            if abs(price_range_mid - line_price) / line_price <= self.rest_tolerance:
                self.rest_counters[state_key] = self.rest_counters.get(state_key, 0) + 1
                if self.rest_counters[state_key] == self.rest_required_bars:
                    results['rest_events'].append(RestEvent(
                        fan_id=event.fan_id,
                        angle_name=str(event.fraction) if event.fraction else "Horizontal",
                        rest_price=close_price,
                        rest_bar=bar_index,
                        bars_elapsed=self.rest_required_bars
                    ))
            else:
                self.rest_counters[state_key] = 0

            # Check for Unconfirmed Breach
            if state_key not in self.active_breaches:
                # Determine direction of intersection
                is_up_breach = close_price > line_price and open_price <= line_price
                is_down_breach = close_price < line_price and open_price >= line_price
                
                if is_up_breach or is_down_breach:
                    direction = 'up' if is_up_breach else 'down'
                    extreme_price = high_price if is_up_breach else low_price
                    
                    # Calculate ML metrics
                    distance_from_origin = bar_index - fan_obj.anchor.bar_index
                    angle_slope = 0.0 # Placeholder: Calculate actual slope from fan_obj.lines if needed
                    
                    self.active_breaches[state_key] = {
                        'direction': direction,
                        'extreme_price': extreme_price,
                        'first_breach_bar': bar_index,
                        'line_price_at_breach': line_price,
                        'distance_from_origin': distance_from_origin,
                        'angle_slope': angle_slope,
                        'fraction': event.fraction
                    }

        # 2. Update existing Unconfirmed Breaches (Check for Confirmation or Reversal)
        keys_to_remove = []
        for state_key, state in self.active_breaches.items():
            fan_id, line_id = state_key.split('_', 1)
            if fan_id not in active_fans:
                keys_to_remove.append(state_key)
                continue
                
            # Skip if this is the bar the breach just happened
            if state['first_breach_bar'] == bar_index:
                continue
                
            bars_elapsed = bar_index - state['first_breach_bar']
            
            # We need the current line price to check for reversals
            # Approximation: use the line_price_at_breach or calculate exact if available
            current_line_price = state['line_price_at_breach'] 
            
            if state['direction'] == 'up':
                if close_price > state['extreme_price']:
                    # Confirmed Breach
                    results['confirmations'].append(BreachConfirmation(
                        fan_id=fan_id,
                        angle_name=str(state['fraction']) if state['fraction'] else "Horizontal",
                        breach_direction='up',
                        confirmation_price=close_price,
                        bars_elapsed=bars_elapsed,
                        first_breach_bar=state['first_breach_bar'],
                        confirmation_bar=bar_index,
                        distance_from_origin=state['distance_from_origin'],
                        angle_slope=state['angle_slope']
                    ))
                    keys_to_remove.append(state_key)
                elif close_price < current_line_price:
                    # Reversal (Fake-out)
                    results['reversals'].append(AngleReversal(
                        fan_id=fan_id,
                        angle_name=str(state['fraction']) if state['fraction'] else "Horizontal",
                        attempted_direction='up',
                        reversal_bar=bar_index,
                        bars_elapsed=bars_elapsed
                    ))
                    keys_to_remove.append(state_key)
                    
            elif state['direction'] == 'down':
                if close_price < state['extreme_price']:
                    # Confirmed Breach
                    results['confirmations'].append(BreachConfirmation(
                        fan_id=fan_id,
                        angle_name=str(state['fraction']) if state['fraction'] else "Horizontal",
                        breach_direction='down',
                        confirmation_price=close_price,
                        bars_elapsed=bars_elapsed,
                        first_breach_bar=state['first_breach_bar'],
                        confirmation_bar=bar_index,
                        distance_from_origin=state['distance_from_origin'],
                        angle_slope=state['angle_slope']
                    ))
                    keys_to_remove.append(state_key)
                elif close_price > current_line_price:
                    # Reversal (Fake-out)
                    results['reversals'].append(AngleReversal(
                        fan_id=fan_id,
                        angle_name=str(state['fraction']) if state['fraction'] else "Horizontal",
                        attempted_direction='down',
                        reversal_bar=bar_index,
                        bars_elapsed=bars_elapsed
                    ))
                    keys_to_remove.append(state_key)

        # Cleanup resolved states
        for key in keys_to_remove:
            del self.active_breaches[key]

        return results

    def remove_fan(self, fan_id: str):
        """Clean up state when a fan is invalidated."""
        keys_to_remove = [k for k in self.active_breaches.keys() if k.startswith(f"{fan_id}_")]
        for k in keys_to_remove:
            del self.active_breaches[k]
            
        rest_keys_to_remove = [k for k in self.rest_counters.keys() if k.startswith(f"{fan_id}_")]
        for k in rest_keys_to_remove:
            del self.rest_counters[k]

    def get_state(self) -> Dict[str, Any]:
        return {
            'active_breaches': self.active_breaches,
            'rest_counters': self.rest_counters
        }

    def restore_state(self, state: Dict[str, Any]):
        self.active_breaches = state.get('active_breaches', {})
        self.rest_counters = state.get('rest_counters', {})
