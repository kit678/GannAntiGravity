"""
Unified State Machine for Event Classification
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from .event_logger import EventType

@dataclass
class EventOutput:
    fan_id: str
    fan_identity: str
    priority_label: str
    fraction: Any
    price: float
    event_type: str
    details: str
    direction: Optional[str] = None

class UnifiedStateMachine:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.rest_tolerance = config.get('rest_tolerance_percent', 0.15) / 100.0
        self.rest_required_bars = config.get('rest_required_bars', 3)
        self.bounce_threshold_percent = config.get('bounce_threshold_percent', 0.3)
        self.rejection_lookback_bars = config.get('rejection_lookback_bars', 5)
        
        # State tracking per line: fan_id_line_id
        self.pending_breaches: Dict[str, Dict[str, Any]] = {}
        self.pending_tests: Dict[str, Dict[str, Any]] = {}
        self.rest_counters: Dict[str, Dict[str, Any]] = {}

    def process_bar(
        self,
        current_candle: Dict[str, Any],
        prev_candle: Dict[str, Any],
        bar_index: int,
        intersection_events: list,
        active_fans: dict,
        candles: list = None
    ) -> List[EventOutput]:
        
        results: List[EventOutput] = []
        
        c_open = float(current_candle.get('open', 0))
        c_high = float(current_candle.get('high', 0))
        c_low = float(current_candle.get('low', 0))
        c_close = float(current_candle.get('close', 0))
        c_time = int(current_candle.get('time', 0))

        prev_close = float(prev_candle.get('close', c_open)) if prev_candle else c_open

        # 1. Process new intersections
        # Group events by fan to handle multi-angle crosses correctly
        events_by_fan = {}
        for event in intersection_events:
            if event.fan_id not in events_by_fan:
                events_by_fan[event.fan_id] = []
            events_by_fan[event.fan_id].append(event)

        for fan_id, fan_events in events_by_fan.items():
            if fan_id not in active_fans:
                continue
                
            fan_obj = active_fans[fan_id]
            
            # Sort events by price distance from open to find the "first" line encountered
            fan_events.sort(key=lambda e: abs(c_open - e.price))
            
            cross_triggered = False

            for event in fan_events:
                line_id = event.line_id
                state_key = f"{fan_id}_{line_id}"
                
                line_price = event.price
                
                fan_identity = event.priority_label.split('(')[-1].rstrip(')').strip() if '(' in event.priority_label else event.priority_label
                frac_name = f"{event.fraction}" if event.fraction is not None else "main"

                # Determine hit type based on wicks and closes relative to CURRENT line price
                # RESISTANCE_TEST: Candle opens and closes below line, but high wick touches/pierces line
                # SUPPORT_TEST: Candle opens and closes above line, but low wick touches/pierces line
                # CROSS_UP: Price opens below/on and closes above the line
                # CROSS_DOWN: Price opens above/on and closes below the line

                hit_type = 'TOUCH'
                details = 'Angle Test'
                direction = None

                # Support/Resistance Tests
                is_resistance_test = c_open <= line_price and c_close <= line_price and c_high >= line_price
                is_support_test = c_open >= line_price and c_close >= line_price and c_low <= line_price

                # Crosses
                is_cross_up = c_open <= line_price and c_close > line_price
                is_cross_down = c_open >= line_price and c_close < line_price

                # Prevent a massive candle from triggering crosses on multiple lines within a single fan
                if (is_cross_up or is_cross_down) and cross_triggered:
                    continue

                if is_cross_up:
                    hit_type = 'CROSS_UP'
                    details = 'Breakout Attempt'
                    direction = 'up'
                    self._start_pending_breach(state_key, event.fan_id, line_id, 'up', c_high, bar_index, line_price, event.fraction, fan_obj)
                    cross_triggered = True
                elif is_cross_down:
                    hit_type = 'CROSS_DOWN'
                    details = 'Breakdown Attempt'
                    direction = 'down'
                    self._start_pending_breach(state_key, event.fan_id, line_id, 'down', c_low, bar_index, line_price, event.fraction, fan_obj)
                    cross_triggered = True
                elif is_support_test:
                    hit_type = 'SUPPORT_TEST'
                    details = 'Testing Support'
                    self._start_pending_test(state_key, event.fan_id, line_id, 'SUPPORT_TEST', bar_index, line_price, event.fraction)
                elif is_resistance_test:
                    hit_type = 'RESISTANCE_TEST'
                    details = 'Testing Resistance'
                    self._start_pending_test(state_key, event.fan_id, line_id, 'RESISTANCE_TEST', bar_index, line_price, event.fraction)
                else:
                    # Pure touch
                    pass

                results.append(EventOutput(
                    fan_id=event.fan_id,
                    fan_identity=fan_identity,
                    priority_label=event.priority_label,
                    fraction=frac_name,
                    price=line_price,
                    event_type=hit_type,
                    details=details,
                    direction=direction
                ))

                # Rest processing
                self._process_rest_event(state_key, event.fan_id, frac_name, line_price, c_close, c_open, c_high, c_low, bar_index, fan_obj, event.priority_label, fan_identity, results)

        # 2. Update existing pending breaches
        keys_to_remove = []
        for state_key, state in self.pending_breaches.items():
            fan_id = state['fan_id']
            if fan_id not in active_fans:
                keys_to_remove.append(state_key)
                continue
                
            if state['first_breach_bar'] == bar_index:
                continue
                
            bars_elapsed = bar_index - state['first_breach_bar']
            
            fan_obj = active_fans[fan_id]
            fan_identity = fan_obj.priority_label.split('(')[-1].rstrip(')').strip() if '(' in fan_obj.priority_label else fan_obj.priority_label
            frac_name = f"{state['fraction']}" if state['fraction'] is not None else "main"

            # Active momentum fake out check: Did price close back across the ORIGINAL breach price?
            # This prevents steep lines from causing passive fake outs just by sloping past a stationary price
            if state['direction'] == 'up':
                if c_close > state['extreme_price']:
                    results.append(EventOutput(
                        fan_id=fan_id, fan_identity=fan_identity, priority_label=fan_obj.priority_label,
                        fraction=frac_name, price=c_close, event_type='BREACH_CONFIRMED',
                        details=f"UP (T+{bars_elapsed} bars)", direction='up'
                    ))
                    keys_to_remove.append(state_key)
                elif c_close < state['line_price_at_breach']:
                    results.append(EventOutput(
                        fan_id=fan_id, fan_identity=fan_identity, priority_label=fan_obj.priority_label,
                        fraction=frac_name, price=c_close, event_type='FAKE_OUT',
                        details=f"Failed UP (reversed at bar {bar_index})", direction='up'
                    ))
                    keys_to_remove.append(state_key)
            elif state['direction'] == 'down':
                if c_close < state['extreme_price']:
                    results.append(EventOutput(
                        fan_id=fan_id, fan_identity=fan_identity, priority_label=fan_obj.priority_label,
                        fraction=frac_name, price=c_close, event_type='BREACH_CONFIRMED',
                        details=f"DOWN (T+{bars_elapsed} bars)", direction='down'
                    ))
                    keys_to_remove.append(state_key)
                elif c_close > state['line_price_at_breach']:
                    results.append(EventOutput(
                        fan_id=fan_id, fan_identity=fan_identity, priority_label=fan_obj.priority_label,
                        fraction=frac_name, price=c_close, event_type='FAKE_OUT',
                        details=f"Failed DOWN (reversed at bar {bar_index})", direction='down'
                    ))
                    keys_to_remove.append(state_key)

        for key in keys_to_remove:
            del self.pending_breaches[key]

        # 3. Update existing pending tests (Bounce / Rejection)
        keys_to_remove = []
        for state_key, state in self.pending_tests.items():
            fan_id = state['fan_id']
            if fan_id not in active_fans:
                keys_to_remove.append(state_key)
                continue
                
            bars_elapsed = bar_index - state['test_bar']
            if bars_elapsed > self.rejection_lookback_bars:
                keys_to_remove.append(state_key)
                continue
                
            fan_obj = active_fans[fan_id]
            fan_identity = fan_obj.priority_label.split('(')[-1].rstrip(')').strip() if '(' in fan_obj.priority_label else fan_obj.priority_label
            frac_name = f"{state['fraction']}" if state['fraction'] is not None else "main"
            
            line_price = state['line_price']
            threshold = line_price * (self.bounce_threshold_percent / 100.0)
            
            if state['test_type'] == 'SUPPORT_TEST':
                if c_close >= line_price + threshold:
                    results.append(EventOutput(
                        fan_id=fan_id, fan_identity=fan_identity, priority_label=fan_obj.priority_label,
                        fraction=frac_name, price=c_close, event_type='SUPPORT_BOUNCE',
                        details=f"Bounced (T+{bars_elapsed} bars)", direction='up'
                    ))
                    keys_to_remove.append(state_key)
            elif state['test_type'] == 'RESISTANCE_TEST':
                if c_close <= line_price - threshold:
                    results.append(EventOutput(
                        fan_id=fan_id, fan_identity=fan_identity, priority_label=fan_obj.priority_label,
                        fraction=frac_name, price=c_close, event_type='RESISTANCE_REJECTION',
                        details=f"Rejected (T+{bars_elapsed} bars)", direction='down'
                    ))
                    keys_to_remove.append(state_key)
                    
        for key in keys_to_remove:
            del self.pending_tests[key]

        return results

    def _start_pending_breach(self, state_key, fan_id, line_id, direction, extreme_price, bar_index, line_price, fraction, fan_obj):
        line_start_time = 0
        line_end_time = 0
        line_start_price = 0.0
        line_end_price = 0.0
        for line in fan_obj.lines:
            if line.fraction == fraction or (fraction is None and line.fraction is None):
                line_start_time = line.start_time
                line_end_time = line.end_time
                line_start_price = line.start_price
                line_end_price = line.end_price
                break
                
        self.pending_breaches[state_key] = {
            'fan_id': fan_id,
            'direction': direction,
            'extreme_price': extreme_price,
            'first_breach_bar': bar_index,
            'line_price_at_breach': line_price,
            'fraction': fraction,
            'line_start_time': line_start_time,
            'line_end_time': line_end_time,
            'line_start_price': line_start_price,
            'line_end_price': line_end_price
        }

    def _start_pending_test(self, state_key, fan_id, line_id, test_type, bar_index, line_price, fraction):
        self.pending_tests[state_key] = {
            'fan_id': fan_id,
            'fraction': fraction,
            'line_price': line_price,
            'test_type': test_type,
            'test_bar': bar_index
        }

    def _process_rest_event(self, state_key, fan_id, frac_name, line_price, c_close, c_open, c_high, c_low, bar_index, fan_obj, priority_label, fan_identity, results):
        body_size = abs(c_open - c_close)
        candle_range = c_high - c_low
        is_small_body = body_size <= (candle_range * 0.4) if candle_range > 0 else True
        is_near_line = abs(c_close - line_price) / line_price <= self.rest_tolerance
        
        # A candle with a very small body, near the line, indicates resting.
        # Alternatively, a candle whose body is entirely near the line.
        
        line_polarity = 'neutral'
        if hasattr(fan_obj, 'anchor_type') and fan_obj.anchor_type:
            line_polarity = 'angled_down' if fan_obj.anchor_type == 'low' else 'angled_up'
            
        # Rest logic requires the body to be small relative to the candle, OR the entire body to be close to the line.
        if is_near_line:
            if state_key not in self.rest_counters:
                self.rest_counters[state_key] = {'count': 0, 'polarity': line_polarity, 'last_bar': bar_index - 1}
            
            # Ensure continuity
            if self.rest_counters[state_key]['last_bar'] == bar_index - 1:
                self.rest_counters[state_key]['count'] += 1
                self.rest_counters[state_key]['last_bar'] = bar_index
                
                if self.rest_counters[state_key]['count'] == self.rest_required_bars:
                    results.append(EventOutput(
                        fan_id=fan_id, fan_identity=fan_identity, priority_label=priority_label,
                        fraction=frac_name, price=c_close, event_type='REST_ON_ANGLE',
                        details=f"Resting (T+{self.rest_required_bars} bars)"
                    ))
            else:
                # Broken continuity, reset
                self.rest_counters[state_key] = {'count': 1, 'polarity': line_polarity, 'last_bar': bar_index}
        else:
            # Not resting, reset
            if state_key in self.rest_counters:
                del self.rest_counters[state_key]

    def remove_fan(self, fan_id: str):
        keys_to_remove = [k for k in self.pending_breaches.keys() if k.startswith(f"{fan_id}_")]
        for k in keys_to_remove: del self.pending_breaches[k]
        
        keys_to_remove = [k for k in self.pending_tests.keys() if k.startswith(f"{fan_id}_")]
        for k in keys_to_remove: del self.pending_tests[k]
        
        keys_to_remove = [k for k in self.rest_counters.keys() if k.startswith(f"{fan_id}_")]
        for k in keys_to_remove: del self.rest_counters[k]

    def get_state(self) -> Dict[str, Any]:
        return {
            'pending_breaches': self.pending_breaches,
            'pending_tests': self.pending_tests,
            'rest_counters': self.rest_counters
        }

    def restore_state(self, state: Dict[str, Any]):
        self.pending_breaches = state.get('pending_breaches', {})
        self.pending_tests = state.get('pending_tests', {})
        self.rest_counters = state.get('rest_counters', {})
