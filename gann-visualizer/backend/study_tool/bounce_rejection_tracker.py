"""
Bounce Rejection Tracker Module

Tracks price behavior after SUPPORT_TEST and RESISTANCE_TEST events to detect:
- SUPPORT_BOUNCE: Price successfully bounced from support after test
- RESISTANCE_REJECTION: Price successfully rejected from resistance after test

Also tracks REST_ON_ANGLE periods with enhanced detection:
- Small-bodied candles consolidating near the line
- Repeated wick probes toward the line with closes staying on one side
- Price "grinding" toward the line but not breaking it
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class BounceConfirmation:
    fan_id: str
    angle_name: str
    bounce_direction: str
    bounce_price: float
    test_bar: int
    bounce_bar: int
    bars_elapsed: int
    bounce_distance: float

    def to_dict(self):
        return self.__dict__


@dataclass
class RejectionConfirmation:
    fan_id: str
    angle_name: str
    rejection_direction: str
    rejection_price: float
    test_bar: int
    rejection_bar: int
    bars_elapsed: int
    rejection_distance: float

    def to_dict(self):
        return self.__dict__


@dataclass
class EnhancedRestEvent:
    fan_id: str
    angle_name: str
    rest_price: float
    rest_bar: int
    bars_elapsed: int
    line_polarity: str
    rest_type: str

    def to_dict(self):
        return self.__dict__


class BounceRejectionTracker:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.bounce_threshold_percent = config.get('bounce_threshold_percent', 0.3)
        self.rejection_lookback_bars = config.get('rejection_lookback_bars', 5)
        self.rest_tolerance_percent = config.get('rest_tolerance_percent', 0.15)
        self.rest_required_bars = config.get('rest_required_bars', 3)
        
        self.pending_tests: Dict[str, Dict[str, Any]] = {}
        self.rest_counters: Dict[str, Dict[str, Any]] = {}
        self.emitted_rest_events: set = set()

    def process_bar(
        self,
        current_candle: Dict[str, Any],
        bar_index: int,
        intersection_events: List[Dict],
        active_fans: Dict[str, Any]
    ) -> Dict[str, List[Any]]:
        results = {
            'bounces': [],
            'rejections': [],
            'rest_events': []
        }

        close_price = float(current_candle.get('close', 0))
        open_price = float(current_candle.get('open', 0))
        high_price = float(current_candle.get('high', 0))
        low_price = float(current_candle.get('low', 0))

        for event in intersection_events:
            fan_id = event.get('fan_id', '')
            fraction = event.get('fraction', 'main')
            line_id = f"{fan_id}_{fraction}"
            
            if fan_id not in active_fans:
                continue
            
            fan_obj = active_fans[fan_id]
            line_price = event.get('price', 0)
            event_type = event.get('type', '')
            
            self._process_rest_event(
                line_id, fan_id, fraction, line_price,
                close_price, open_price, high_price, low_price,
                bar_index, event_type, fan_obj, results
            )
            
            self._track_pending_test(
                line_id, fan_id, fraction, line_price,
                event_type, bar_index, fan_obj
            )

        keys_to_remove = []
        for state_key, state in self.pending_tests.items():
            test_bar = state['test_bar']
            bars_elapsed = bar_index - test_bar
            
            if bars_elapsed > self.rejection_lookback_bars:
                keys_to_remove.append(state_key)
                continue
            
            line_price = state['line_price']
            close_price = float(current_candle.get('close', 0))
            high_price = float(current_candle.get('high', 0))
            low_price = float(current_candle.get('low', 0))
            
            threshold = line_price * (self.bounce_threshold_percent / 100.0)
            
            if state['test_type'] == 'SUPPORT_TEST':
                if close_price >= line_price + threshold:
                    results['bounces'].append(BounceConfirmation(
                        fan_id=state['fan_id'],
                        angle_name=state['angle_name'],
                        bounce_direction='up',
                        bounce_price=close_price,
                        test_bar=test_bar,
                        bounce_bar=bar_index,
                        bars_elapsed=bars_elapsed,
                        bounce_distance=close_price - line_price
                    ))
                    keys_to_remove.append(state_key)
                    
            elif state['test_type'] == 'RESISTANCE_TEST':
                if close_price <= line_price - threshold:
                    results['rejections'].append(RejectionConfirmation(
                        fan_id=state['fan_id'],
                        angle_name=state['angle_name'],
                        rejection_direction='down',
                        rejection_price=close_price,
                        test_bar=test_bar,
                        rejection_bar=bar_index,
                        bars_elapsed=bars_elapsed,
                        rejection_distance=line_price - close_price
                    ))
                    keys_to_remove.append(state_key)

        for key in keys_to_remove:
            del self.pending_tests[key]

        return results

    def _process_rest_event(
        self,
        line_id: str,
        fan_id: str,
        fraction: str,
        line_price: float,
        close_price: float,
        open_price: float,
        high_price: float,
        low_price: float,
        bar_index: int,
        event_type: str,
        fan_obj: Any,
        results: Dict
    ):
        if line_id in self.emitted_rest_events:
            self.rest_counters[line_id] = {'count': 0, 'bars': []}
            return
        
        body_size = abs(open_price - close_price)
        candle_range = high_price - low_price
        is_small_body = body_size <= (candle_range * 0.4) if candle_range > 0 else True
        is_near_line = abs(close_price - line_price) / line_price <= (self.rest_tolerance_percent / 100.0)
        
        has_upper_wick = (high_price - max(open_price, close_price)) > body_size
        has_lower_wick = (min(open_price, close_price) - low_price) > body_size
        is_wick_probe = (has_upper_wick or has_lower_wick) and is_near_line
        
        line_polarity = 'neutral'
        if hasattr(fan_obj, 'anchor_type') and fan_obj.anchor_type:
            if fan_obj.anchor_type == 'low':
                line_polarity = 'angled_down'
            elif fan_obj.anchor_type == 'high':
                line_polarity = 'angled_up'
        
        if (is_small_body or is_wick_probe) and is_near_line:
            if line_id not in self.rest_counters:
                self.rest_counters[line_id] = {'count': 0, 'bars': [], 'polarity': line_polarity}
            
            self.rest_counters[line_id]['count'] += 1
            self.rest_counters[line_id]['bars'].append(bar_index)
            self.rest_counters[line_id]['polarity'] = line_polarity
            
            if self.rest_counters[line_id]['count'] >= self.rest_required_bars:
                rest_type = 'wick_consolidation' if is_wick_probe else 'body_consolidation'
                
                results['rest_events'].append(EnhancedRestEvent(
                    fan_id=fan_id,
                    angle_name=str(fraction) if fraction else "main",
                    rest_price=close_price,
                    rest_bar=bar_index,
                    bars_elapsed=self.rest_counters[line_id]['count'],
                    line_polarity=line_polarity,
                    rest_type=rest_type
                ))
                self.emitted_rest_events.add(line_id)
                self.rest_counters[line_id] = {'count': 0, 'bars': [], 'polarity': line_polarity}
        else:
            self.rest_counters[line_id] = {'count': 0, 'bars': [], 'polarity': line_polarity}

    def _track_pending_test(
        self,
        line_id: str,
        fan_id: str,
        fraction: str,
        line_price: float,
        event_type: str,
        bar_index: int,
        fan_obj: Any
    ):
        if event_type in ('SUPPORT_TEST', 'RESISTANCE_TEST'):
            self.pending_tests[line_id] = {
                'fan_id': fan_id,
                'angle_name': str(fraction) if fraction else "main",
                'line_price': line_price,
                'test_type': event_type,
                'test_bar': bar_index
            }

    def remove_fan(self, fan_id: str):
        keys_to_remove = [k for k in self.pending_tests.keys() if k.startswith(f"{fan_id}_")]
        for k in keys_to_remove:
            del self.pending_tests[k]
        
        rest_keys = [k for k in self.rest_counters.keys() if k.startswith(f"{fan_id}_")]
        for k in rest_keys:
            del self.rest_counters[k]
        
        emit_keys = [k for k in self.emitted_rest_events if k.startswith(f"{fan_id}_")]
        for k in emit_keys:
            self.emitted_rest_events.discard(k)

    def get_state(self) -> Dict[str, Any]:
        return {
            'pending_tests': self.pending_tests,
            'rest_counters': self.rest_counters,
            'emitted_rest_events': list(self.emitted_rest_events)
        }

    def restore_state(self, state: Dict[str, Any]):
        self.pending_tests = state.get('pending_tests', {})
        self.rest_counters = state.get('rest_counters', {})
        self.emitted_rest_events = set(state.get('emitted_rest_events', []))
