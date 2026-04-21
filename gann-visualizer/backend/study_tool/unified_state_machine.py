"""
Unified State Machine for Event Classification
"""
import os
import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from .event_logger import EventType
from .candlestick_detector import CandlestickPatternDetector

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
    def __init__(self, config: Dict[str, Any], event_logger=None):
        self.config = config
        self.rest_tolerance = config.get('rest_tolerance_percent', 0.15) / 100.0
        self.rest_required_bars = config.get('rest_required_bars', 3)
        self.bounce_threshold_percent = config.get('bounce_threshold_percent', 0.3)
        self.rejection_lookback_bars = config.get('rejection_lookback_bars', 5)
        self.run_mode = config.get('run_mode', 'simulation')
        
        # Setup trace logger
        log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
            "logs", "backend"
        )
        os.makedirs(log_dir, exist_ok=True)
        self.trace_log_path = os.path.join(log_dir, f"{self.run_mode}_trace.log")
        
        # Initialize log file
        # For simulation: always truncate on init (since it's instantiated once per run)
        # For replay: truncate ONLY ONCE per server lifecycle
        should_truncate = False
        if self.run_mode == 'simulation':
            should_truncate = True
        elif self.run_mode == 'replay':
            if not hasattr(UnifiedStateMachine, '_replay_log_truncated'):
                should_truncate = True
                UnifiedStateMachine._replay_log_truncated = True
        
        if should_truncate:
            with open(self.trace_log_path, 'w', encoding='utf-8') as f:
                f.write(f"=== {self.run_mode.upper()} DECISION TRACE LOG ===\n")
                f.write("Event Type Definitions:\n")
                f.write("- CROSS_UP: Price opens below/on and closes above the line\n")
                f.write("- CROSS_DOWN: Price opens above/on and closes below the line\n")
                f.write("- SUPPORT_TEST: Candle opens and closes above line, but low wick touches/pierces line\n")
                f.write("- RESISTANCE_TEST: Candle opens and closes below line, but high wick touches/pierces line\n")
                f.write("- BREACH_CONFIRMED: Price closes beyond max(BEC_close, ZEC_high) for UP, ")
                f.write("or below min(BEC_close, ZEC_low) for DOWN.\n")
                f.write("- BREACH_CONFIRMED_NO_ALPHA: Intra-bar multi-cross or next-target-hit. ")
                f.write("No tradeable alpha.\n")
                f.write("- SUPPORT_BOUNCE: Price bounces up by threshold % after a SUPPORT_TEST\n")
                f.write("- RESISTANCE_REJECTION: Price rejects down by threshold % after a RESISTANCE_TEST\n")
                f.write("- TARGET_HIT: First contact with an angle line in the target progression sequence. ")
                f.write("Only fires once per line; subsequent contacts are ignored.\n")
                f.write("=================================================\n\n")

        # State tracking per line: fan_id_line_id
        self.pending_breaches: Dict[str, Dict[str, Any]] = {}
        self.pending_tests: Dict[str, Dict[str, Any]] = {}
        self.rest_counters: Dict[str, Dict[str, Any]] = {}

        # Candlestick pattern detector
        pattern_log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
            "logs", "backend"
        )
        pattern_log_path = os.path.join(pattern_log_dir, "candle_patterns.log")
        self.pattern_detector = CandlestickPatternDetector(pattern_log_path)

        # Event logger for candle pattern events
        self.event_logger = event_logger

    def _log_trace(self, bar_index: int, c_time: int, c_open: float, c_high: float, c_low: float, c_close: float, evaluations: List[str], is_retro: bool = False):
        """Write a structured one-liner trace for the current bar."""
        dt_str = datetime.datetime.fromtimestamp(c_time).strftime('%Y-%m-%d %H:%M')
        retro_str = "[RETRO] " if is_retro else ""

        # Detect candlestick pattern
        ohlc = {'open': c_open, 'high': c_high, 'low': c_low, 'close': c_close}
        pattern = self.pattern_detector.detect(ohlc)
        pattern_str = f"[Pattern: {pattern.name}]" if pattern.name != "NO_PATTERN" else ""

        header = f"{retro_str}[Bar {bar_index}] [{dt_str}] [O:{c_open:.2f}, H:{c_high:.2f}, L:{c_low:.2f}, C:{c_close:.2f}]"

        with open(self.trace_log_path, 'a', encoding='utf-8') as f:
            if not evaluations:
                f.write(f"{header} {pattern_str} -> [No Intersection Detected] -> No Event\n")
            else:
                for eval_str in evaluations:
                    f.write(f"{header} {pattern_str} -> {eval_str}\n")

        # Log candle pattern event if event_logger is provided
        if self.event_logger is not None:
            self.event_logger.log_candle_pattern(
                timestamp=c_time,
                price=c_close,
                pattern_name=pattern.name,
                pattern_details={
                    'open': c_open,
                    'high': c_high,
                    'low': c_low,
                    'close': c_close,
                    'bar_index': bar_index
                }
            )

    def process_bar(
        self,
        current_candle: Dict[str, Any],
        prev_candle: Dict[str, Any],
        bar_index: int,
        intersection_events: list,
        active_fans: dict,
        candles: list = None,
        is_retro: bool = False,
        retro_fan_ids: list = None,
        zec_info: Dict[str, Dict[str, Any]] = None
    ) -> List[EventOutput]:

        results: List[EventOutput] = []
        evaluations: List[str] = []
        zec_info = zec_info or {}

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

        for fan_id in sorted(events_by_fan.keys()):
            fan_events = events_by_fan[fan_id]
            if fan_id not in active_fans:
                continue

            fan_obj = active_fans[fan_id]

            # Sort events by price distance from open to find the "first" line encountered
            fan_events.sort(key=lambda e: abs(c_open - e.price))

            crosses_up_this_bar = []
            crosses_down_this_bar = []

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

                # Crosses (Physical or Gap)
                is_cross_up = (c_open <= line_price and c_close > line_price) or (event.prev_price is not None and prev_close < event.prev_price and c_close > line_price)
                is_cross_down = (c_open >= line_price and c_close < line_price) or (event.prev_price is not None and prev_close > event.prev_price and c_close < line_price)

                if is_cross_up:
                    hit_type = 'CROSS_UP'
                    details = 'Breakout Attempt'
                    direction = 'up'
                    fan_zec = zec_info.get(event.fan_id, {})
                    self._start_pending_breach(
                        state_key=state_key,
                        fan_id=event.fan_id,
                        line_id=line_id,
                        direction='up',
                        extreme_price=c_close,
                        bar_index=bar_index,
                        line_price=line_price,
                        fraction=event.fraction,
                        fan_obj=fan_obj,
                        bec_close=c_close,
                        zec_high=fan_zec.get('zec_high', c_close),
                        zec_low=fan_zec.get('zec_low', c_close),
                        prior_zone_fraction=fan_zec.get('prior_zone_fraction', ''))
                    crosses_up_this_bar.append((state_key, event, fan_identity, frac_name, fan_obj))
                    if c_open <= line_price:
                        evaluations.append(f"[{fan_identity} {frac_name} @ {line_price:.2f}] O <= Line & C > Line -> CROSS_UP (Pending Breach UP)")
                    else:
                        evaluations.append(f"[{fan_identity} {frac_name} @ {line_price:.2f}] PrevC < PrevLine & C > Line -> GAP CROSS_UP (Pending Breach UP)")
                elif is_cross_down:
                    hit_type = 'CROSS_DOWN'
                    details = 'Breakdown Attempt'
                    direction = 'down'
                    fan_zec = zec_info.get(event.fan_id, {})
                    self._start_pending_breach(
                        state_key=state_key,
                        fan_id=event.fan_id,
                        line_id=line_id,
                        direction='down',
                        extreme_price=c_close,
                        bar_index=bar_index,
                        line_price=line_price,
                        fraction=event.fraction,
                        fan_obj=fan_obj,
                        bec_close=c_close,
                        zec_high=fan_zec.get('zec_high', c_close),
                        zec_low=fan_zec.get('zec_low', c_close),
                        prior_zone_fraction=fan_zec.get('prior_zone_fraction', ''))
                    crosses_down_this_bar.append((state_key, event, fan_identity, frac_name, fan_obj))
                    if c_open >= line_price:
                        evaluations.append(f"[{fan_identity} {frac_name} @ {line_price:.2f}] O >= Line & C < Line -> CROSS_DOWN (Pending Breach DOWN)")
                    else:
                        evaluations.append(f"[{fan_identity} {frac_name} @ {line_price:.2f}] PrevC > PrevLine & C < Line -> GAP CROSS_DOWN (Pending Breach DOWN)")
                elif is_support_test:
                    hit_type = 'SUPPORT_TEST'
                    details = 'Testing Support'
                    self._start_pending_test(state_key, event.fan_id, line_id, 'SUPPORT_TEST', bar_index, line_price, event.fraction, c_close)
                    evaluations.append(f"[{fan_identity} {frac_name} @ {line_price:.2f}] O >= Line & C >= Line & L <= Line -> SUPPORT_TEST (Pending Bounce)")
                elif is_resistance_test:
                    hit_type = 'RESISTANCE_TEST'
                    details = 'Testing Resistance'
                    self._start_pending_test(state_key, event.fan_id, line_id, 'RESISTANCE_TEST', bar_index, line_price, event.fraction, c_close)
                    evaluations.append(f"[{fan_identity} {frac_name} @ {line_price:.2f}] O <= Line & C <= Line & H >= Line -> RESISTANCE_TEST (Pending Rejection)")
                else:
                    # Pure touch
                    evaluations.append(f"[{fan_identity} {frac_name} @ {line_price:.2f}] Intersection detected but did not meet strict wick/body criteria -> TOUCH")

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
                self._process_rest_event(state_key, event.fan_id, frac_name, line_price, c_close, c_open, c_high, c_low, bar_index, fan_obj, event.priority_label, fan_identity, results, evaluations)

            # Intra-bar immediate breach confirmation
            if len(crosses_up_this_bar) > 1:
                # Sort by line price ascending
                crosses_up_this_bar.sort(key=lambda x: x[1].price)
                # All except the last one (highest price) are confirmed
                for state_key, event, fan_identity, frac_name, fan_obj in crosses_up_this_bar[:-1]:
                    results.append(EventOutput(
                        fan_id=event.fan_id, fan_identity=fan_identity, priority_label=fan_obj.priority_label,
                        fraction=frac_name, price=c_close, event_type='BREACH_CONFIRMED_NO_ALPHA',
                        details="UP (Intra-bar multi-cross, no alpha)", direction='up'
                    ))
                    if state_key in self.pending_breaches:
                        del self.pending_breaches[state_key]
                    evaluations.append(f"[{fan_identity} {frac_name}] Intra-bar multi-cross -> BREACH_CONFIRMED_NO_ALPHA")

            if len(crosses_down_this_bar) > 1:
                # Sort by line price descending
                crosses_down_this_bar.sort(key=lambda x: x[1].price, reverse=True)
                # All except the last one (lowest price) are confirmed
                for state_key, event, fan_identity, frac_name, fan_obj in crosses_down_this_bar[:-1]:
                    results.append(EventOutput(
                        fan_id=event.fan_id, fan_identity=fan_identity, priority_label=fan_obj.priority_label,
                        fraction=frac_name, price=c_close, event_type='BREACH_CONFIRMED_NO_ALPHA',
                        details="DOWN (Intra-bar multi-cross, no alpha)", direction='down'
                    ))
                    if state_key in self.pending_breaches:
                        del self.pending_breaches[state_key]
                    evaluations.append(f"[{fan_identity} {frac_name}] Intra-bar multi-cross -> BREACH_CONFIRMED_NO_ALPHA")

        # 2. Update existing pending breaches
        keys_to_remove = []
        for state_key in sorted(self.pending_breaches.keys()):
            state = self.pending_breaches[state_key]
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

            # Skip if this pending breach will be confirmed via TARGET_HIT (cross-bar Path B)
            if state.get('skip_section2'):
                evaluations.append(f"[{fan_identity} {frac_name}] Pending Breach UP: skip_section2=True -> SKIPPED (awaiting TARGET_HIT)")
                continue

            # Active momentum fake out check: Did price close back across the ORIGINAL breach price?
            # This prevents steep lines from causing passive fake outs just by sloping past a stationary price
            if state['direction'] == 'up':
                bec_close = state.get('bec_close', state['extreme_price'])
                zec_high = state.get('zec_high', state['extreme_price'])
                if c_close > max(bec_close, zec_high):
                    results.append(EventOutput(
                        fan_id=fan_id, fan_identity=fan_identity, priority_label=fan_obj.priority_label,
                        fraction=frac_name, price=c_close, event_type='BREACH_CONFIRMED',
                        details=f"UP (T+{bars_elapsed} bars)", direction='up'
                    ))
                    keys_to_remove.append(state_key)
                    evaluations.append(f"[{fan_identity} {frac_name}] Pending Breach UP: C ({c_close:.2f}) > max(BEC={bec_close:.2f}, ZEC={zec_high:.2f}) -> BREACH_CONFIRMED")
            elif state['direction'] == 'down':
                # Skip if this pending breach will be confirmed via TARGET_HIT (cross-bar Path B)
                if state.get('skip_section2'):
                    evaluations.append(f"[{fan_identity} {frac_name}] Pending Breach DOWN: skip_section2=True -> SKIPPED (awaiting TARGET_HIT)")
                    continue
                bec_close = state.get('bec_close', state['extreme_price'])
                zec_low = state.get('zec_low', state['extreme_price'])
                if c_close < min(bec_close, zec_low):
                    results.append(EventOutput(
                        fan_id=fan_id, fan_identity=fan_identity, priority_label=fan_obj.priority_label,
                        fraction=frac_name, price=c_close, event_type='BREACH_CONFIRMED',
                        details=f"DOWN (T+{bars_elapsed} bars)", direction='down'
                    ))
                    keys_to_remove.append(state_key)
                    evaluations.append(f"[{fan_identity} {frac_name}] Pending Breach DOWN: C ({c_close:.2f}) < min(BEC={bec_close:.2f}, ZEC={zec_low:.2f}) -> BREACH_CONFIRMED")

        for key in keys_to_remove:
            del self.pending_breaches[key]

        # 3. Update existing pending tests (Bounce / Rejection)
        keys_to_remove = []
        for state_key in sorted(self.pending_tests.keys()):
            state = self.pending_tests[state_key]
            fan_id = state['fan_id']
            if fan_id not in active_fans:
                keys_to_remove.append(state_key)
                continue

            bars_elapsed = bar_index - state['test_bar']
            if bars_elapsed > self.rejection_lookback_bars:
                keys_to_remove.append(state_key)
                evaluations.append(f"[{fan_id} {state['fraction']}] Pending Test expired after {bars_elapsed} bars -> Removed")
                continue

            fan_obj = active_fans[fan_id]
            fan_identity = fan_obj.priority_label.split('(')[-1].rstrip(')').strip() if '(' in fan_obj.priority_label else fan_obj.priority_label
            frac_name = f"{state['fraction']}" if state['fraction'] is not None else "main"

            line_price = state['line_price']
            threshold = line_price * (self.bounce_threshold_percent / 100.0)

            if state['test_type'] == 'SUPPORT_TEST':
                # Cancel if price closes decisively below the candle that triggered the test
                if c_close < state['candle_close']:
                    keys_to_remove.append(state_key)
                    evaluations.append(f"[{fan_identity} {frac_name}] Pending SUPPORT_TEST: C ({c_close:.2f}) < Test Candle Close ({state['candle_close']:.2f}) -> Cancelled")
                    continue
                if c_close >= line_price + threshold:
                    results.append(EventOutput(
                        fan_id=fan_id, fan_identity=fan_identity, priority_label=fan_obj.priority_label,
                        fraction=frac_name, price=c_close, event_type='SUPPORT_BOUNCE',
                        details=f"Bounced (T+{bars_elapsed} bars)", direction='up'
                    ))
                    keys_to_remove.append(state_key)
                    evaluations.append(f"[{fan_identity} {frac_name}] Pending SUPPORT_TEST: C ({c_close:.2f}) >= Line + Threshold ({line_price + threshold:.2f}) -> SUPPORT_BOUNCE")
            elif state['test_type'] == 'RESISTANCE_TEST':
                # Cancel if price closes decisively above the candle that triggered the test
                if c_close > state['candle_close']:
                    keys_to_remove.append(state_key)
                    evaluations.append(f"[{fan_identity} {frac_name}] Pending RESISTANCE_TEST: C ({c_close:.2f}) > Test Candle Close ({state['candle_close']:.2f}) -> Cancelled")
                    continue
                if c_close <= line_price - threshold:
                    results.append(EventOutput(
                        fan_id=fan_id, fan_identity=fan_identity, priority_label=fan_obj.priority_label,
                        fraction=frac_name, price=c_close, event_type='RESISTANCE_REJECTION',
                        details=f"Rejected (T+{bars_elapsed} bars)", direction='down'
                    ))
                    keys_to_remove.append(state_key)
                    evaluations.append(f"[{fan_identity} {frac_name}] Pending RESISTANCE_TEST: C ({c_close:.2f}) <= Line - Threshold ({line_price - threshold:.2f}) -> RESISTANCE_REJECTION")

        for key in keys_to_remove:
            del self.pending_tests[key]

        # If there are active fans but no evaluations were generated, log the distances to explain why
        if active_fans and not evaluations:
            # If this is a retro sweep, only log distances for the new fans being retroactively evaluated
            fans_to_log = active_fans
            if is_retro and retro_fan_ids:
                fans_to_log = {fid: fan for fid, fan in active_fans.items() if fid in retro_fan_ids}
                
            for fan_id in sorted(fans_to_log.keys()):
                fan_obj = fans_to_log[fan_id]
                fan_identity = fan_obj.priority_label.split('(')[-1].rstrip(')').strip() if '(' in fan_obj.priority_label else fan_obj.priority_label
                
                # Find the nearest line for this fan
                nearest_line = None
                min_dist = float('inf')
                
                # Calculate current prices for all lines in this fan
                for line in fan_obj.lines:
                    bar_span = line.end_bar_index - line.start_bar_index
                    if bar_span > 0:
                        bars_from_origin = bar_index - line.start_bar_index
                        slope = (line.end_price - line.start_price) / bar_span
                        price_at_t = line.start_price + bars_from_origin * slope
                        
                        dist = abs(c_close - price_at_t)
                        if dist < min_dist:
                            min_dist = dist
                            frac_str = str(line.fraction) if line.fraction is not None else "horizontal"
                            nearest_line = f"{frac_str} @ {price_at_t:.2f}"
                
                if nearest_line:
                    evaluations.append(f"[{fan_identity}] Nearest line is {nearest_line} (Distance: {min_dist:.2f}) -> No Intersection")

        self._log_trace(bar_index, c_time, c_open, c_high, c_low, c_close, evaluations, is_retro)

        return results

    def _start_pending_breach(self, state_key, fan_id, line_id, direction, extreme_price, bar_index, line_price, fraction, fan_obj, bec_close: float, zec_high: float, zec_low: float, prior_zone_fraction: str):
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
            'line_end_price': line_end_price,
            'bec_close': bec_close,
            'zec_high': zec_high,
            'zec_low': zec_low,
            'prior_zone_fraction': prior_zone_fraction,
            'skip_section2': False,
        }

    def _start_pending_test(self, state_key, fan_id, line_id, test_type, bar_index, line_price, fraction, candle_close):
        self.pending_tests[state_key] = {
            'fan_id': fan_id,
            'fraction': fraction,
            'line_price': line_price,
            'test_type': test_type,
            'test_bar': bar_index,
            'candle_close': candle_close
        }

    def _process_rest_event(self, state_key, fan_id, frac_name, line_price, c_close, c_open, c_high, c_low, bar_index, fan_obj, priority_label, fan_identity, results, evaluations):
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
                    evaluations.append(f"[{fan_identity} {frac_name}] Rest count reached {self.rest_required_bars} -> REST_ON_ANGLE")
                else:
                    evaluations.append(f"[{fan_identity} {frac_name}] Near line, rest count incremented to {self.rest_counters[state_key]['count']}")
            else:
                # Broken continuity, reset
                self.rest_counters[state_key] = {'count': 1, 'polarity': line_polarity, 'last_bar': bar_index}
                evaluations.append(f"[{fan_identity} {frac_name}] Near line but continuity broken, rest count reset to 1")
        else:
            # Not resting, reset
            if state_key in self.rest_counters:
                del self.rest_counters[state_key]
                evaluations.append(f"[{fan_identity} {frac_name}] Moved away from line, rest count cleared")

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
