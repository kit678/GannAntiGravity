import os
import re

def fix_state_machine():
    file_path = 'c:/Dev/GannTesting/gann-visualizer/backend/study_tool/unified_state_machine.py'
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Remove deferred_breaches list from initialization
    content = content.replace(
        "        self.deferred_breaches: List[Tuple] = []  # deferred breach emissions\n",
        ""
    )

    # 2. Remove appending to deferred_breaches for UP
    content = content.replace(
        "                    self.deferred_breaches.append(('up', state_key, fan_id, fan_identity, fan_obj.priority_label, frac_name, c_close, bars_elapsed, bar_index))\n",
        ""
    )

    # 3. Remove appending to deferred_breaches for DOWN
    content = content.replace(
        "                    self.deferred_breaches.append(('down', state_key, fan_id, fan_identity, fan_obj.priority_label, frac_name, c_close, bars_elapsed, bar_index))\n",
        ""
    )

    # 4. Replace flush_deferred_breaches with flush_confirmed_breaches
    old_flush = re.search(r"    def flush_deferred_breaches\(self\) -> List\[EventOutput\]:.*?        self\.confirmed_this_bar\.clear\(\)\n        return results", content, re.DOTALL).group(0)

    new_flush = '''    def flush_confirmed_breaches(self) -> List[EventOutput]:
        """
        Emit mathematically confirmed BREACH_CONFIRMED events, checking skip_section2 flag first.
        Called by angular_coverage_study.py after TARGET_HIT processing has had 
        a chance to set skip_section2=True on pending breaches.
        """
        results = []

        # Process confirmed_this_bar — these were already mathematically confirmed in Section 2.
        # _on_target_hit() has had a chance to set skip_section2=True on the
        # pending_breaches entry. Check the flag and emit the correct event type.
        for entry in self.confirmed_this_bar:
            direction, state_key, fan_id, fan_identity, priority_label, frac_name, price, bars_elapsed, bar_index = entry

            # Retrieve state for event emission fields
            state = self.pending_breaches.get(state_key)

            # If state is None, it means _confirm_pending_breach_if_valid() already emitted
            # the NO_ALPHA event and deleted it from pending_breaches! So we just skip it.
            if not state:
                continue

            # Check skip_section2 — if True, emit BREACH_CONFIRMED_NO_ALPHA instead
            if state.get('skip_section2'):
                results.append(EventOutput(
                    fan_id=fan_id,
                    fan_identity=fan_identity,
                    priority_label=priority_label,
                    fraction=frac_name,
                    price=price,
                    event_type='BREACH_CONFIRMED_NO_ALPHA',
                    details=f"{'UP' if direction == 'up' else 'DOWN'} (T+{bars_elapsed} bars, path=B cross-bar)",
                    direction=direction,
                    bar_index=bar_index
                ))
                # Write corrected state_block to trace (Section 2 traced it as BREACH_CONFIRMED — fix it)
                import datetime
                dt_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')    
                dir_str = direction.upper()
                pending_bar = state.get('first_breach_bar', bar_index)
                bec = float(state.get('bec_close', price))
                zec_h = float(state.get('zec_high', price))
                zec_l = float(state.get('zec_low', price))
                state_str = (
                    f"[STATE] pending_breach: fan={fan_id} line={frac_name} direction={dir_str} "
                    f"bec_close={bec:.2f} zec_high={zec_h:.2f} zec_low={zec_l:.2f} "
                    f"pending_bar={pending_bar} outcome=BREACH_CONFIRMED_NO_ALPHA"
                )
                with open(self.trace_log_path, 'a', encoding='utf-8') as f:    
                    f.write(f"[Bar {bar_index}] [{dt_str}]  -> {state_str}\\n") 
                del self.pending_breaches[state_key]
                continue

            # No skip — emit BREACH_CONFIRMED normally
            results.append(EventOutput(
                fan_id=fan_id,
                fan_identity=fan_identity,
                priority_label=priority_label,
                fraction=frac_name,
                price=price,
                event_type='BREACH_CONFIRMED',
                details=f"{'UP' if direction == 'up' else 'DOWN'} (T+{bars_elapsed} bars)",
                direction=direction,
                bar_index=bar_index
            ))
            del self.pending_breaches[state_key]

        self.confirmed_this_bar.clear()
        return results'''

    content = content.replace(old_flush, new_flush)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

fix_state_machine()
