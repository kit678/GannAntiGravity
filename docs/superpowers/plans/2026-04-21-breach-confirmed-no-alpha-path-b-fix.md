# BREACH_CONFIRMED_NO_ALPHA Path B Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix order-of-operations bug where `BREACH_CONFIRMED` fires before `TARGET_HIT` can confirm the prior line's pending breach as `BREACH_CONFIRMED_NO_ALPHA`.

**Architecture:** Add a `skip_section2: bool` flag to pending breach state. When `_confirm_pending_breach_if_valid()` finds a pending breach on line N (the prior line to the TARGET_HIT line), it sets `skip_section2 = True`. Section 2 of `process_bar()` skips emitting `BREACH_CONFIRMED` for flagged pending breaches, allowing `_confirm_pending_breach_if_valid()` to emit `BREACH_CONFIRMED_NO_ALPHA` instead.

**Tech Stack:** Python, `unified_state_machine.py`, `angular_coverage_study.py`

---

## Files

- **Modify:** `gann-visualizer/backend/study_tool/unified_state_machine.py:432-481` (`_start_pending_breach` signature and body), `gann-visualizer/backend/study_tool/unified_state_machine.py:316-326` (section 2 skip logic)
- **Modify:** `gann-visualizer/backend/study_tool/angular_coverage_study.py:1118-1125` (set skip flag before confirming)

---

## Task 1: Add `skip_section2` field to pending breach state

**Files:**
- Modify: `gann-visualizer/backend/study_tool/unified_state_machine.py:432-481`

- [ ] **Step 1: Add `skip_section2=False` to pending breach dict in `_start_pending_breach`**

Locate the `_start_pending_breach` method. In the dict that represents the pending breach state (around line 447-460), add `skip_section2: bool = False` as a field.

The method signature already accepts all needed fields. Find the `self.pending_breaches[state_key] = {...}` dict and add the new field:

```python
self.pending_breaches[state_key] = {
    'fan_id': fan_id,
    'line_id': line_id,
    'direction': direction,
    'extreme_price': extreme_price,
    'first_breach_bar': bar_index,
    'line_price': line_price,
    'fraction': fraction,
    'fan_obj': fan_obj,
    'bec_close': bec_close,
    'zec_high': zec_high,
    'zec_low': zec_low,
    'prior_zone_fraction': prior_zone_fraction,
    'skip_section2': False,  # NEW
}
```

- [ ] **Step 2: Commit**

```bash
git add gann-visualizer/backend/study_tool/unified_state_machine.py
git commit -m "feat: add skip_section2 flag to pending breach state"
```

---

## Task 2: Add section 2 skip logic for flagged pending breaches

**Files:**
- Modify: `gann-visualizer/backend/study_tool/unified_state_machine.py:305-326` (section 2 pending breach update loop)

- [ ] **Step 1: Add skip check at the start of section 2 pending breach processing**

In the section 2 loop at lines 305-326, add a check at the top of the body — right after `bars_elapsed = bar_index - state['first_breach_bar']` — to skip if `state.get('skip_section2')` is True.

The code currently:
```python
bars_elapsed = bar_index - state['first_breach_bar']

fan_obj = active_fans[fan_id]
fan_identity = fan_obj.priority_label.split('(')[-1].rstrip(')').strip() if '(' in fan_obj.priority_label else fan_obj.priority_label
frac_name = f"{state['fraction']}" if state['fraction'] is not None else "main"

# Active momentum fake out check...
```

Change to:
```python
bars_elapsed = bar_index - state['first_breach_bar']

# Skip if this pending breach will be confirmed via TARGET_HIT (cross-bar Path B)
if state.get('skip_section2'):
    evaluations.append(f"[{fan_identity} {frac_name}] Pending Breach UP: skip_section2=True -> SKIPPED (awaiting TARGET_HIT)")
    continue

fan_obj = active_fans[fan_id]
fan_identity = fan_obj.priority_label.split('(')[-1].rstrip(')').strip() if '(' in fan_obj.priority_label else fan_obj.priority_label
frac_name = f"{state['fraction']}" if state['fraction'] is not None else "main"

# Active momentum fake out check...
```

Add the same skip check for the 'down' direction branch (around line 327-337).

- [ ] **Step 2: Commit**

```bash
git add gann-visualizer/backend/study_tool/unified_state_machine.py
git commit -m "feat: skip BREACH_CONFIRMED emission when skip_section2=True"
```

---

## Task 3: Set `skip_section2=True` in `_confirm_pending_breach_if_valid`

**Files:**
- Modify: `gann-visualizer/backend/study_tool/angular_coverage_study.py:1127-1128` (before log_event call)

- [ ] **Step 1: Set skip_section2 flag before logging BREACH_CONFIRMED_NO_ALPHA**

In `_confirm_pending_breach_if_valid()`, right before calling `self.event_logger.log_event()` to emit `BREACH_CONFIRMED_NO_ALPHA`, set `skip_section2 = True` on the pending breach state dict:

```python
state = state_machine_state[prev_state_key]

# Mark it so section 2 skips its BREACH_CONFIRMED emission
state['skip_section2'] = True

# Confirm the pending breach
self.event_logger.log_event(
    timestamp=timestamp,
    event_type=EventType.BREACH_CONFIRMED_NO_ALPHA,
    ...
```

This ensures that even if section 2 hasn't run yet (or runs again on a subsequent bar), it won't emit a duplicate `BREACH_CONFIRMED`.

- [ ] **Step 2: Commit**

```bash
git add gann-visualizer/backend/study_tool/angular_coverage_study.py
git commit -m "feat: mark pending breach skip_section2=True before emitting BREACH_CONFIRMED_NO_ALPHA"
```

---

## Task 4: Verify the fix with the replay trace

- [ ] **Step 1: Re-run the backend replay**

Run the study tool on the same dataset that produced the 10:55 AM breach event.

Expected in `replay_trace.log`:
- Bar 25 (10:55 AM) should show the 0.875 pending breach SKIPPED (awaiting TARGET_HIT)
- `BREACH_CONFIRMED_NO_ALPHA` should appear instead of `BREACH_CONFIRMED` for the 0.875 line

Expected in the price interaction table:
- Row 8 @ 10:55 AM should show `BREACH_CONFIRMED_NO_ALPHA` for the 0.875 line (not `BREACH_CONFIRMED`)

- [ ] **Step 2: Commit the verified fix**

```bash
git add -A
git commit -m "fix: BREACH_CONFIRMED_NO_ALPHA Path B now fires correctly when TARGET_HIT precedes breach confirmation"
```