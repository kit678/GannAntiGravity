# Fix BREACH_CONFIRMED_NO_ALPHA Path B — Order-of-Operations Bug

## Problem

At 10:55 AM (Bar 25), the 0.875 line's pending breach confirmed as `BREACH_CONFIRMED` instead of `BREACH_CONFIRMED_NO_ALPHA`.

The price interaction table shows:
- Row 3 @ 10:51 AM: 0.875 line had `CROSS_UP` (pending breach created)
- Row 7 @ 10:55 AM: 0.75 line had `TARGET_HIT`
- Row 8 @ 10:55 AM: 0.875 line had `BREACH_CONFIRMED` ← should be `BREACH_CONFIRMED_NO_ALPHA`

Per `EVENT_TYPES.md` Path B: *"When `TARGET_HIT` fires on line N+1 and the prior line N had a pending breach created in an earlier bar (not the same bar), the pending breach on N is immediately confirmed as `BREACH_CONFIRMED_NO_ALPHA`."*

## Root Cause

The execution order causes `_confirm_pending_breach_if_valid()` to run too late:

1. `state_machine.process_bar()` runs section 2 (lines 296-340) — emits `BREACH_CONFIRMED` for cross-bar pending breaches
2. `process_bar()` returns to `angular_coverage_study.py`
3. TARGET_HIT is processed, `_confirm_pending_breach_if_valid()` is called → but `BREACH_CONFIRMED` already fired

Section 2 has no knowledge of TARGET_HIT events that will fire later in the same bar.

## Solution: Mark pending breaches for TARGET_HIT confirmation

When `_confirm_pending_breach_if_valid()` finds a pending breach on the previous line (N), it marks that pending breach with a flag `skip_section2 = True`. Section 2 skips emitting for flagged pending breaches.

### Changes

**`unified_state_machine.py`:**
- Add `skip_section2: bool = False` field to pending breach state in `_start_pending_breach()`
- In section 2, skip `BREACH_CONFIRMED` emission when `skip_section2 == True`
- Clear the flag after processing so it doesn't persist

**`angular_coverage_study.py`:**
- In `_confirm_pending_breach_if_valid()`, before logging `BREACH_CONFIRMED_NO_ALPHA`, set `skip_section2 = True` on the found pending breach state

### Flow After Fix

1. `process_bar()` runs section 1 (crosses), section 2 (pending breaches) — but section 2 skips the 0.875 pending breach because `skip_section2 == True`
2. `process_bar()` returns — no `BREACH_CONFIRMED` emitted for 0.875
3. TARGET_HIT on 0.75 is processed, `_confirm_pending_breach_if_valid()` runs and emits `BREACH_CONFIRMED_NO_ALPHA` for 0.875