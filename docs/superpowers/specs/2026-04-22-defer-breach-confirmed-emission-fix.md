# Defer BREACH_CONFIRMED Emission — Fix Retro Sweep Path B

## Problem

During retro sweep, `BREACH_CONFIRMED` fires for the 0.875 line at 10:55 AM because `on_angle_contact('0.75')` returns `None` during retro processing (line already in `angles_contacted`), so `_confirm_pending_breach_if_valid` never runs and `skip_section2` is never set.

## Root Cause

When `target_progression.on_angle_contact()` is called for an angle that's already in `angles_contacted`, it returns `None`. This means `_confirm_pending_breach_if_valid` is never called, `skip_section2` is never set, and section 2 of `process_bar()` emits `BREACH_CONFIRMED` instead of skipping.

## Solution: Defer Section 2 BREACH_CONFIRMED Emission

Instead of emitting `BREACH_CONFIRMED` immediately during section 2's pending breach loop, collect the pending breaches that are ready to confirm, then emit after all bar processing is complete.

This gives `target_progression.on_angle_contact()` and `_confirm_pending_breach_if_valid()` a chance to run first (via state machine events processed in section 1) and set `skip_section2=True` on the pending breach.

### Changes

**`unified_state_machine.py`:**
1. Instead of emitting `BREACH_CONFIRMED` immediately in section 2, collect ready breaches in a `deferred_breaches` list
2. After section 3 (pending tests), emit deferred breaches
3. Section 2 still checks `skip_section2` flag — if set, skip the breach (but still add to deferred list for potential `BREACH_CONFIRMED_NO_ALPHA` later)
4. Add a new method `_flush_deferred_breaches()` to emit at the right time

**`angular_coverage_study.py`:**
- `_confirm_pending_breach_if_valid` already sets `skip_section2=True` before emitting `BREACH_CONFIRMED_NO_ALPHA`. This is unchanged.
- The key improvement: section 2 defers emission so `_confirm_pending_breach_if_valid` runs first.

### Flow After Fix

**During bar processing:**
1. Section 1: Processes intersection events, calls `_start_pending_breach()` for crosses
2. Section 2: Iterates pending breaches. If `skip_section2=True`, logs "SKIPPED" and skips. Otherwise, checks threshold — if ready, adds to `deferred_breaches` (doesn't emit yet)
3. State machine returns events to `angular_coverage_study.py`
4. `angular_coverage_study.py` processes TARGET_HIT, calls `_confirm_pending_breach_if_valid`, which sets `skip_section2=True` on the prior line's pending breach
5. Return to state machine, which then calls `_flush_deferred_breaches()`
6. `_flush_deferred_breaches()` checks `skip_section2`: if True, skip (breach was already confirmed as NO_ALPHA); if False, emit BREACH_CONFIRMED

### Alternative Considered

Option A (fix `on_angle_contact`) was rejected because it would change core target progression logic that's working correctly for live processing. Option B is surgical — only changes when section 2 emits, no changes to target logic.