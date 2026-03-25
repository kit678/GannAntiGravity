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
        for event in intersection_events:
            if event.fan_id not in active_fans:
                continue
                
            fan_obj = active_fans[event.fan_id]
            line_id = event.line_id
            state_key = f"{event.fan_id}_{line_id}"
            
            line_price = event.price
            prev_line_price = getattr(event, 'prev_price', line_price)
            
            fan_identity = event.priority_label.split('(')[-1].rstrip(')').strip() if '(' in event.priority_label else event.priority_label
            frac_name = f"{event.fraction}" if event.fraction is not None else "main"

            # Determine hit type based on wicks and closes relative to PREVIOUS line price and CURRENT line price
            # CROSS_UP: prev_close <= prev_line_price and close > current_line_price
            # CROSS_DOWN: prev_close >= prev_line_price and close < current_line_price
            # SUPPORT_TEST: prev_close > prev_line_price, low <= current_line_price, close >= current_line_price
            # RESISTANCE_TEST: prev_close < prev_line_price, high >= current_line_price, close <= current_line_price

            hit_type = 'TOUCH'
            details = 'Angle Test'
            direction = None

            is_cross_up = prev_close <= prev_line_price and c_close > line_price
            is_cross_down = prev_close >= prev_line_price and c_close < line_price
            is_support_test = prev_close > prev_line_price and c_low <= line_price and c_close >= line_price
            is_resistance_test = prev_close < prev_line_price and c_high >= line_price and c_close <= line_price

            if is_cross_up:
                hit_type = 'CROSS_UP'
                details = 'Breakout Attempt'
                direction = 'up'
                self._start_pending_breach(state_key, event.fan_id, line_id, 'up', c_high, bar_index, line_price, event.fraction, fan_obj)
            elif is_cross_down:
                hit_type = 'CROSS_DOWN'
                details = 'Breakdown Attempt'
                direction = 'down'
                self._start_pending_breach(state_key, event.fan_id, line_id, 'down', c_low, bar_index, line_price, event.fraction, fan_obj)
            elif is_support_test:
                hit_type = 'SUPPORT_TEST'
                details = 'Testing Support'
                self._start_pending_test(state_key, event.fan_id, line_id, 'SUPPORT_TEST', bar_index, line_price, event.fraction)
            elif is_resistance_test:
                hit_type = 'RESISTANCE_TEST'
                details = 'Testing Resistance'
                self._start_pending_test(state_key, event.fan_id, line_id, 'RESISTANCE_TEST', bar_index, line_price, event.fraction)
            else:
                # E.g. gap over line without touching? Or pure touch
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

            # Calculate current line price
            current_line_price = state['line_price_at_breach']
            if (state['line_end_time'] - state['line_start_time']) > 0:
                time_ratio = (c_time - state['line_start_time']) / (state['line_end_time'] - state['line_start_time'])
                time_ratio = max(0, min(1, time_ratio))
                current_line_price = state['line_start_price'] + time_ratio * (state['line_end_price'] - state['line_start_price'])

            if state['direction'] == 'up':
                if c_close > state['extreme_price']:
                    results.append(EventOutput(
                        fan_id=fan_id, fan_identity=fan_identity, priority_label=fan_obj.priority_label,
                        fraction=frac_name, price=c_close, event_type='BREACH_CONFIRMED',
                        details=f"UP (T+{bars_elapsed} bars)", direction='up'
                    ))
                    keys_to_remove.append(state_key)
                elif c_close < current_line_price:
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
                elif c_close > current_line_price:
                    results.append(EventOutput(
                        fan_id=fan_id, fan_identity=fan_identity, priority_label=fan_obj.priority_label,
                        fraction=frac_name, pri
