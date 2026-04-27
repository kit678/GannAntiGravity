import os

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

    # 4. Rewrite flush_deferred_breaches -> flush_confirmed_breaches
    old_flush = '''    def flush_deferred_breaches(self) -> List[EventOutput]:
        """
        Emit deferred and confirmed BREACH_CONFIRMED events, checking skip_section2 flag first.
        Called by angular_coverage_study.py after TARGET_HIT processing has had 
        a chance to set skip_section2=True on pending breaches.

        Processing order:
        1. deferred_breaches — breaches that weren't yet confirmed (still within zone)
        2. confirmed_this_bar — breaches that WERE confirmed in Section 2 this bar
           and must NOT be deleted until after skip_section2 is checked.        
        """
        results = []

        # 1. Process deferred (not-yet-confirmed) breaches
        for entry in self.deferred_breaches:
            direction, state_key, fan_id, fan_identity, priority_label, frac_name, price, bars_elapsed, deferred_bar_index = entry

            # Check skip_section2 flag - if set, breach was confirmed as NO_ALPHA by TARGET_HIT
            state = self.pending_breaches.get(state_key)
            if state and state.get('skip_section2'):
                # TARGET_HIT confirmed this as BREACH_CONFIRMED_NO_ALPHA — skip BREACH_CONFIRMED
                if state_key in self.pending_breaches:
                    del self.pending_breaches[state_key]
                continue

            # Emit BREACH_CONFIRMED
            results.append(EventOutput(
                fan_id=fan_id,
                fan_identity=fan_identity,
                priority_label=priority_label,
                fraction=frac_name,
                price=price,
                event_type='BREACH_CONFIRMED',
                details=f"{'UP' if direction == 'up' else 'DOWN'} (T+{bars_elapsed} bars)",
                direction=direction,
                bar_index=deferred_bar_index
            ))
            state = self.pending_breaches.get(state_key)
            if state:
                self.emit_pending_breach_state(
                    bar_index=deferred_bar_index,
                    fan_id=state['fan_id'],
                    fraction=state['fraction'],
                    direction=direction.upper(),
                    bec_close=state['bec_close'],
                    zec_high=state['zec_high'],
                    zec_low=state['zec_low'],
                    pending_bar=state['first_breach_bar'],
                    outcome='BREACH_CONFIRMED'
                )
            if state_key in self.pending_breaches:
                del self.pending_breaches[state_key]

        # 2. Process confirmed_this_bar — these were already confirmed in Section 2.
        #    _on_target_hit() has had a chance to set skip_section2=True on the
        #    pending_breaches entry. Check the flag and emit the correct event type.
        for entry in self.confirmed_this_bar:
            direction, state_key, fan_id, fan_identity, priority_label, frac_name, price, bars_elapsed, bar_index = entry

            # Retrieve state for event emission fields
            state = self.pending_breaches.get(state_key)

            # Check skip_section2 — if True, emit BREACH_CONFIRMED_NO_ALPHA instead
            if state and state.get('skip_section2'):
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
                if state_key in self.pending_breaches:
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
            if state_key in self.pending_breaches:
                del self.pending_breaches[state_key]

        self.deferred_breaches.clear()
        self.confirmed_this_bar.clear()
        return results'''

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
