with open('c:/Dev/GannTesting/gann-visualizer/backend/study_tool/unified_state_machine.py', 'r') as f:
    content = f.read()

content = content.replace('''
                if is_support_test and not is_cross_down:
                    hit_type = 'SUPPORT_TEST'
                    details = 'Testing Support'
                    self._start_pending_test(state_key, event.fan_id, line_id, 'SUPPORT_TEST', bar_index, line_price, event.fraction)
                elif is_resistance_test and not is_cross_up:
                    hit_type = 'RESISTANCE_TEST'
                    details = 'Testing Resistance'
                    self._start_pending_test(state_key, event.fan_id, line_id, 'RESISTANCE_TEST', bar_index, line_price, event.fraction)
                elif is_support_test and is_cross_up:
                    # We crossed UP over the line, but our low wick tested it as support on the way up
                    # We log it as a CROSS_UP in the primary event, but we ALSO need to register the support test
                    self._start_pending_test(state_key, event.fan_id, line_id, 'SUPPORT_TEST', bar_index, line_price, event.fraction)
                elif is_resistance_test and is_cross_down:
                    # We crossed DOWN under the line, but our high wick tested it as resistance on the way down
                    self._start_pending_test(state_key, event.fan_id, line_id, 'RESISTANCE_TEST', bar_index, line_price, event.fraction)
''', '''
                # A single candle can pierce support (cross down) AND bounce off it (support test)
                if is_support_test:
                    if not is_cross_down and not is_cross_up:
                        hit_type = 'SUPPORT_TEST'
                        details = 'Testing Support'
                    self._start_pending_test(state_key, event.fan_id, line_id, 'SUPPORT_TEST', bar_index, line_price, event.fraction)
                    
                    # If it's ALSO a cross, emit the test as a SEPARATE event
                    if is_cross_up or is_cross_down:
                        results.append(EventOutput(
                            fan_id=event.fan_id,
                            fan_identity=fan_identity,
                            priority_label=event.priority_label,
                            fraction=frac_name,
                            price=line_price,
                            event_type='SUPPORT_TEST',
                            details='Testing Support (Wick)',
                            direction='up'
                        ))
                elif is_resistance_test:
                    if not is_cross_up and not is_cross_down:
                        hit_type = 'RESISTANCE_TEST'
                        details = 'Testing Resistance'
                    self._start_pending_test(state_key, event.fan_id, line_id, 'RESISTANCE_TEST', bar_index, line_price, event.fraction)
                    
                    # If it's ALSO a cross, emit the test as a SEPARATE event
                    if is_cross_up or is_cross_down:
                        results.append(EventOutput(
                            fan_id=event.fan_id,
                            fan_identity=fan_identity,
                            priority_label=event.priority_label,
                            fraction=frac_name,
                            price=line_price,
                            event_type='RESISTANCE_TEST',
                            details='Testing Resistance (Wick)',
                            direction='down'
                        ))
''')
with open('c:/Dev/GannTesting/gann-visualizer/backend/study_tool/unified_state_machine.py', 'w') as f:
    f.write(content)
