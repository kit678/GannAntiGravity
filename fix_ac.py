import os
import re

def fix_angular_coverage():
    file_path = 'c:/Dev/GannTesting/gann-visualizer/backend/study_tool/angular_coverage_study.py'
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Replace flush_deferred_breaches with flush_confirmed_breaches
    content = content.replace("flush_deferred_breaches", "flush_confirmed_breaches")

    # 2. Rewrite the end of _confirm_pending_breach_if_valid
    # We will search for everything from "state['skip_section2'] = True" to "def _get_horizontal_target_price"
    search_pattern = r"        state\['skip_section2'\] = True.*?def _get_horizontal_target_price"
    
    replacement = '''        # Mark it so section 2 skips its BREACH_CONFIRMED emission
        state['skip_section2'] = True

        # Delete from pending_breaches so flush_confirmed_breaches() ignores it completely.
        # We will handle ALL emissions for this NO_ALPHA event right here.
        del self.state_machine.pending_breaches[prev_state_key]

        # 1. Emit to Event Logger (CSV)
        self.event_logger.log_event(
            timestamp=timestamp,
            event_type=EventType.BREACH_CONFIRMED_NO_ALPHA,
            angle_name=prev_line,
            price=c_close,
            direction='up' if state.get('direction') == 'up' else 'down',
            open_price=c_open,
            high_price=c_high,
            low_price=c_low,
            close_price=c_close,
            active_angle_prices=active_angle_prices,
            cluster_state=is_cluster,
            current_zone=last_zone.zone if last_zone else None,
            zone_highest_close=last_zone.zone_highest_close if last_zone else None,
            zone_lowest_close=last_zone.zone_lowest_close if last_zone else None,
            details={
                'fan_id': fan_id,
                'cross_bar': True
            }
        )

        # 2. Write to Trace Log directly
        dir_str = 'UP' if state.get('direction') == 'up' else 'DOWN'
        pending_bar = state.get('first_breach_bar', bar_index)
        bec = float(state.get('bec_close', c_close))
        zec_h = float(state.get('zec_high', c_close))
        zec_l = float(state.get('zec_low', c_close))
        state_str = (
            f"[STATE] pending_breach: fan={fan_id} line={prev_line} direction={dir_str} "
            f"bec_close={bec:.2f} zec_high={zec_h:.2f} zec_low={zec_l:.2f} "
            f"pending_bar={pending_bar} outcome=BREACH_CONFIRMED_NO_ALPHA"
        )
        import datetime
        dt_str = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')
        with open(self.state_machine.trace_log_path, 'a', encoding='utf-8') as f:
            f.write(f"[Bar {bar_index}] [{dt_str}] [O:{c_open:.2f}, H:{c_high:.2f}, L:{c_low:.2f}, C:{c_close:.2f}]  -> {state_str}\\n")

        # 3. Append to UI Events
        ui_events.append({
            'time': timestamp,
            'fan': state_event.priority_label if hasattr(state_event, 'priority_label') else fan_id,
            'fanIdentity': state_event.fan_identity if hasattr(state_event, 'fan_identity') else fan_id.split('_')[-1],
            'fraction': prev_line,
            'price': c_close,
            'type': 'BREACH_CONFIRMED_NO_ALPHA',
            'details': 'Target hit before breach confirmation (cross-bar)',
            'open': c_open,
            'high': c_high,
            'low': c_low,
            'close': c_close,
            'activeAngles': active_angle_prices,
            'cluster': is_cluster,
            'zone': last_zone.zone if last_zone else None,
            'zoneExtremes': {
                'highest_close': last_zone.zone_highest_close if last_zone else None,
                'lowest_close': last_zone.zone_lowest_close if last_zone else None
            },
            'bar_index': bar_index,
            'nextAngleLine': ''
        })

        self.log(f"[Tracking] BREACH_CONFIRMED_NO_ALPHA (via target progression): {fan_id} {prev_line}")

    def _get_horizontal_target_price'''

    content = re.sub(search_pattern, replacement, content, flags=re.DOTALL)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_angular_coverage()
