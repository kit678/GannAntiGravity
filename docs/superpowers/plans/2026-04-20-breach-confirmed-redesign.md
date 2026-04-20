# BREACH_CONFIRMED Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the redesigned BREACH_CONFIRMED event type using BEC + ZEC (prior zone extremes) confirmation rule, add BREACH_CONFIRMED_NO_ALPHA for intra-bar multi-cross and next-target-hit scenarios, and remove the reversal cancellation of pending breaches.

**Architecture:** The state machine (`UnifiedStateMachine`) stores BEC and ZEC on the pending breach dict at creation time. AngularCoverageStudy passes the prior zone's extremes to `process_bar`. Confirmation checks `c_close > max(bec_close, zec_high)` for UP and `c_close < min(bec_close, zec_low)` for DOWN.

**Tech Stack:** Python, existing `unified_state_machine.py`, `angular_coverage_study.py`, `event_logger.py`

---

## File Structure

- `gann-visualizer/backend/study_tool/event_logger.py` — Add `BREACH_CONFIRMED_NO_ALPHA` to `EventType` enum
- `gann-visualizer/backend/study_tool/unified_state_machine.py` — Core changes: update `_start_pending_breach`, pending breach lifecycle, confirmation logic, intra-bar multi-cross suffix
- `gann-visualizer/backend/study_tool/angular_coverage_study.py` — Pass ZEC info to state machine; update `_handle_target_hit_intra_bar_breach` to emit `BREACH_CONFIRMED_NO_ALPHA`
- `gann-visualizer/backend/docs/EVENT_TYPES.md` — Already updated from brainstorming phase
- `gann-visualizer/backend/study_tool/breach_analyzer.py` — Standalone module; no changes needed (separate from state machine path)

---

## Task 1: Add BREACH_CONFIRMED_NO_ALPHA to EventType Enum

**Files:**
- Modify: `gann-visualizer/backend/study_tool/event_logger.py:25-28`

- [ ] **Step 1: Read current EventType enum**

Run: `Read event_logger.py lines 19-38`

- [ ] **Step 2: Add BREACH_CONFIRMED_NO_ALPHA enum member**

```python
BREACH_CONFIRMED = "breach_confirmed"    # N successive closes achieved
BREACH_CONFIRMED_NO_ALPHA = "BREACH_CONFIRMED_NO_ALPHA"  # Intra-bar or next-target-hit, no alpha
```

Run: `Edit old_string with the new member added after BREACH_CONFIRMED line`

- [ ] **Step 3: Commit**

```bash
git add gann-visualizer/backend/study_tool/event_logger.py
git commit -m "feat: add BREACH_CONFIRMED_NO_ALPHA to EventType enum"
```

---

## Task 2: Update _start_pending_breach to Store BEC and ZEC

**Files:**
- Modify: `gann-visualizer/backend/study_tool/unified_state_machine.py:405-429`

- [ ] **Step 1: Read current _start_pending_breach implementation**

Run: `Read unified_state_machine.py lines 405-429`

- [ ] **Step 2: Update _start_pending_breach signature and body**

Change the function signature to add `bec_close: float`, `zec_high: float`, `zec_low: float`, `prior_zone_fraction: str` parameters.

Update the pending breach dict (lines 418-429) to store:
```python
'bec_close': bec_close,
'zec_high': zec_high,
'zec_low': zec_low,
'prior_zone_fraction': prior_zone_fraction,
```

The existing fields (`extreme_price`, `line_price_at_breach`, etc.) are still needed for other purposes — do NOT remove them.

- [ ] **Step 3: Commit**

```bash
git add gann-visualizer/backend/study_tool/unified_state_machine.py
git commit -m "feat: add BEC/ZEC fields to _start_pending_breach"
```

---

## Task 3: Update process_bar Signature to Accept ZEC Info

**Files:**
- Modify: `gann-visualizer/backend/study_tool/unified_state_machine.py:117-127`

- [ ] **Step 1: Add zec_info parameter to process_bar**

Add `zec_info: Dict[str, Dict[str, Any]] = None` to the `process_bar` signature. Default to `None` for backward compatibility.

Initialize `zec_info = zec_info or {}` at the start of the method body.

- [ ] **Step 2: Commit**

```bash
git add gann-visualizer/backend/study_tool/unified_state_machine.py
git commit -m "feat: add zec_info parameter to process_bar"
```

---

## Task 4: Update _start_pending_breach Call Sites in process_bar

**Files:**
- Modify: `gann-visualizer/backend/study_tool/unified_state_machine.py:192, 202`

- [ ] **Step 1: Update CROSS_UP call to _start_pending_breach (line 192)**

Change from:
```python
self._start_pending_breach(state_key, event.fan_id, line_id, 'up', c_close, bar_index, line_price, event.fraction, fan_obj)
```

To:
```python
fan_zec = zec_info.get(event.fan_id, {})
self._start_pending_breach(
    state_key=state_key,
    fan_id=event.fan_id,
    line_id=line_id,
    direction='up',
    extreme_price=c_close,      # kept for existing logic
    bar_index=bar_index,
    line_price=line_price,
    fraction=event.fraction,
    fan_obj=fan_obj,
    bec_close=c_close,
    zec_high=fan_zec.get('zec_high', c_close),
    zec_low=fan_zec.get('zec_low', c_close),
    prior_zone_fraction=fan_zec.get('prior_zone_fraction', '')
)
```

- [ ] **Step 2: Update CROSS_DOWN call to _start_pending_breach (line 202)**

Same pattern as Step 1, using `direction='down'` and passing the same `bec_close`, `zec_high`, `zec_low`.

- [ ] **Step 3: Commit**

```bash
git add gann-visualizer/backend/study_tool/unified_state_machine.py
git commit -m "feat: pass BEC/ZEC to _start_pending_breach on CROSS events"
```

---

## Task 5: Update Pending Breach Confirmation Logic

**Files:**
- Modify: `gann-visualizer/backend/study_tool/unified_state_machine.py:265-313` (pending breach update loop)

- [ ] **Step 1: Replace extreme_price checks with BEC+ZEC rule**

In the pending breach update loop (lines 285-310), replace the current `extreme_price` checks with the BEC+ZEC confirmation rule:

**For UP direction (replace lines 285-297):**
```python
if state['direction'] == 'up':
    bec_close = state.get('bec_close', state['extreme_price'])
    zec_high = state.get('zec_high', bec_close)
    confirmation_threshold = max(bec_close, zec_high)
    if c_close > confirmation_threshold:
        results.append(EventOutput(
            fan_id=fan_id, fan_identity=fan_identity, priority_label=fan_obj.priority_label,
            fraction=frac_name, price=c_close, event_type='BREACH_CONFIRMED',
            details=f"UP (T+{bars_elapsed} bars)", direction='up'
        ))
        keys_to_remove.append(state_key)
        evaluations.append(f"[{fan_identity} {frac_name}] Pending Breach UP: C ({c_close:.2f}) > max(BEC={bec_close:.2f}, ZEC={zec_high:.2f}) -> BREACH_CONFIRMED")
    # REMOVED: reversal check against line_price_at_breach — pending breach stays alive
```

**For DOWN direction (replace lines 298-310):**
```python
elif state['direction'] == 'down':
    bec_close = state.get('bec_close', state['extreme_price'])
    zec_low = state.get('zec_low', bec_close)
    confirmation_threshold = min(bec_close, zec_low)
    if c_close < confirmation_threshold:
        results.append(EventOutput(
            fan_id=fan_id, fan_identity=fan_identity, priority_label=fan_obj.priority_label,
            fraction=frac_name, price=c_close, event_type='BREACH_CONFIRMED',
            details=f"DOWN (T+{bars_elapsed} bars)", direction='down'
        ))
        keys_to_remove.append(state_key)
        evaluations.append(f"[{fan_identity} {frac_name}] Pending Breach DOWN: C ({c_close:.2f}) < min(BEC={bec_close:.2f}, ZEC={zec_low:.2f}) -> BREACH_CONFIRMED")
    # REMOVED: reversal check against line_price_at_breach — pending breach stays alive
```

- [ ] **Step 2: Commit**

```bash
git add gann-visualizer/backend/study_tool/unified_state_machine.py
git commit -m "feat: use BEC+ZEC confirmation rule, remove reversal cancellation"
```

---

## Task 6: Update Intra-bar Multi-cross to Emit BREACH_CONFIRMED_NO_ALPHA

**Files:**
- Modify: `gann-visualizer/backend/study_tool/unified_state_machine.py:237-263`

- [ ] **Step 1: Update intra-bar CROSS_UP handling (lines 237-249)**

Change `event_type='BREACH_CONFIRMED'` to `event_type='BREACH_CONFIRMED_NO_ALPHA'` and details to reflect no alpha:

```python
if len(crosses_up_this_bar) > 1:
    crosses_up_this_bar.sort(key=lambda x: x[1].price)
    for state_key, event, fan_identity, frac_name, fan_obj in crosses_up_this_bar[:-1]:
        results.append(EventOutput(
            fan_id=event.fan_id, fan_identity=fan_identity, priority_label=fan_obj.priority_label,
            fraction=frac_name, price=c_close, event_type='BREACH_CONFIRMED_NO_ALPHA',
            details="UP (Intra-bar multi-cross, no alpha)", direction='up'
        ))
        if state_key in self.pending_breaches:
            del self.pending_breaches[state_key]
        evaluations.append(f"[{fan_identity} {frac_name}] Intra-bar multi-cross -> BREACH_CONFIRMED_NO_ALPHA")
```

- [ ] **Step 2: Update intra-bar CROSS_DOWN handling (lines 251-263)**

Same change: `event_type='BREACH_CONFIRMED_NO_ALPHA'` and updated details string.

- [ ] **Step 3: Commit**

```bash
git add gann-visualizer/backend/study_tool/unified_state_machine.py
git commit -m "feat: emit BREACH_CONFIRMED_NO_ALPHA for intra-bar multi-cross"
```

---

## Task 7: Update AngularCoverageStudy to Compute and Pass ZEC Info

**Files:**
- Modify: `gann-visualizer/backend/study_tool/angular_coverage_study.py:288-315` (zone tracking loop) and line 409 (`_process_tracking_modules` call)

**Critical note on ordering:** In `process_bar`, `compute_snapshot` (line 291) is called **before** `_process_tracking_modules` (line 409). Since `compute_snapshot` resets `_zone_extremes[fan_id]` to the **new** zone's extremes, we must capture ZEC **before** `compute_snapshot` overwrites it.

- [ ] **Step 1: Capture ZEC before compute_snapshot in the zone tracking loop**

In the zone tracking loop (lines 288-315), add ZEC capture **before** `compute_snapshot` is called for each fan. The ZEC for a fan is the current `_zone_extremes[fan_id]` (the zone BEFORE `compute_snapshot` updates it to the new zone):

```python
# 2.5 Process Zone Tracking for ALL active fans for the LIVE bar
for fan_id, fan_obj in self.angle_engine.active_fans.items():
    if getattr(fan_obj, '_zone_caught_up_to', -1) < bar_index:
        # CAPTURE ZEC BEFORE compute_snapshot overwrites _zone_extremes
        # At this point, _zone_extremes[fan_id] still holds the PRIOR zone's extremes
        if fan_id in self.zone_tracker._zone_extremes:
            extremes = self.zone_tracker._zone_extremes[fan_id]
            last_zone_snap = self.zone_tracker._last_zones.get(fan_id)
            self._pending_zec_info = getattr(self, '_pending_zec_info', {})
            self._pending_zec_info[fan_id] = {
                'zec_high': extremes.get('highest_close'),
                'zec_low': extremes.get('lowest_close'),
                'prior_zone_fraction': last_zone_snap.zone if last_zone_snap else None
            }

        snapshot = self.zone_tracker.compute_snapshot(fan_obj, current_candle, bar_index)
        fan_obj._zone_caught_up_to = bar_index
        # ... rest of existing zone change handling ...
```

Note: `_pending_zec_info` is stored on `self` so it persists until `_process_tracking_modules` consumes it.

- [ ] **Step 2: Pass zec_info to _process_tracking_modules and forward to process_bar**

Modify the `_process_tracking_modules` call (line ~409) to pass `zec_info`:
```python
self._process_tracking_modules(
    current_candle, prev_candle, bar_index, events or [], ui_events, candles,
    zec_info=getattr(self, '_pending_zec_info', {})
)
```

Then update `_process_tracking_modules` signature (line 423) to accept `zec_info`:
```python
def _process_tracking_modules(
    self,
    current_candle: Dict[str, Any],
    prev_candle: Dict[str, Any],
    bar_index: int,
    intersection_events: list,
    ui_events: list,
    candles: list,
    is_retro: bool = False,
    retro_fan_ids: list = None,
    zec_info: Dict[str, Dict[str, Any]] = None
):
```

And pass it to `state_machine.process_bar`:
```python
state_events = self.state_machine.process_bar(
    current_candle, prev_candle, bar_index,
    intersection_events, self.angle_engine.active_fans, candles, is_retro, retro_fan_ids,
    zec_info=zec_info or {}
)
```

- [ ] **Step 3: Clear _pending_zec_info after use**

After the `state_machine.process_bar` call in `_process_tracking_modules`, clear the pending ZEC info:
```python
self._pending_zec_info = {}
```

- [ ] **Step 4: Commit**

```bash
git add gann-visualizer/backend/study_tool/angular_coverage_study.py
git commit -m "feat: capture ZEC before compute_snapshot, pass to state machine"
```

---

## Task 8: Update _handle_target_hit_intra_bar_breach to Emit BREACH_CONFIRMED_NO_ALPHA

**Files:**
- Modify: `gann-visualizer/backend/study_tool/angular_coverage_study.py:1109-1143`

- [ ] **Step 1: Update event_logger.log_event call to use BREACH_CONFIRMED_NO_ALPHA**

Change `event_type=EventType.BREACH_CONFIRMED` to `event_type=EventType.BREACH_CONFIRMED_NO_ALPHA`.

- [ ] **Step 2: Update ui_events dict type field**

Change `'type': 'BREACH_CONFIRMED'` to `'type': 'BREACH_CONFIRMED_NO_ALPHA'` in the ui_events dict (line ~1142).

- [ ] **Step 3: Update log message**

Change the log message at line ~1133 from `'BREACH_CONFIRMED (intra-bar)'` to `'BREACH_CONFIRMED_NO_ALPHA (intra-bar via target progression)'`.

- [ ] **Step 4: Commit**

```bash
git add gann-visualizer/backend/study_tool/angular_coverage_study.py
git commit -m "feat: emit BREACH_CONFIRMED_NO_ALPHA for next-target-hit intra-bar breach"
```

---

## Task 9: Update Debug Log String in unified_state_machine.py

**Files:**
- Modify: `gann-visualizer/backend/study_tool/unified_state_machine.py:58-60`

- [ ] **Step 1: Update the debug log string**

Replace lines 58-60 with the updated description:
```python
f.write("- BREACH_CONFIRMED: Price closes beyond max(BEC_close, ZEC_high) for UP, ")
f.write("or below min(BEC_close, ZEC_low) for DOWN.\n")
f.write("- BREACH_CONFIRMED_NO_ALPHA: Intra-bar multi-cross or next-target-hit. ")
f.write("No tradeable alpha.\n")
```

- [ ] **Step 2: Commit**

```bash
git add gann-visualizer/backend/study_tool/unified_state_machine.py
git commit -m "chore: update debug log to reflect BEC+ZEC rule and NO_ALPHA variant"
```

---

## Task 10: Verify All Changes Against Spec

**Files to review:**
- `gann-visualizer/backend/study_tool/event_logger.py` — EventType enum
- `gann-visualizer/backend/study_tool/unified_state_machine.py` — BEC+ZEC fields, confirmation rule, NO_ALPHA handling
- `gann-visualizer/backend/study_tool/angular_coverage_study.py` — ZEC passing, target-hit handler

- [ ] **Step 1: Cross-check each spec item**

Read through the spec at `docs/superpowers/specs/2026-04-20-breach-confirmed-redesign.md` and verify:
1. BEC = `bec_close` stored at pending breach creation ✓?
2. ZEC = `zec_high`/`zec_low` from prior zone stored at pending breach creation ✓?
3. UP confirmation: `c_close > max(bec_close, zec_high)` ✓?
4. DOWN confirmation: `c_close < min(bec_close, zec_low)` ✓?
5. Pending breach stays alive on reversal (no cancellation against `line_price_at_breach`) ✓?
6. Fan invalidation silently cancels pending breach ✓?
7. Next target hit fires `BREACH_CONFIRMED_NO_ALPHA` ✓?
8. Intra-bar multi-cross intermediate lines fire `BREACH_CONFIRMED_NO_ALPHA` ✓?
9. `BREACH_CONFIRMED_NO_ALPHA` added to EventType enum ✓?

- [ ] **Step 2: Run existing tests**

```bash
cd gann-visualizer/backend
python -m pytest tests/ -v --tb=short 2>&1 | head -100
```

Fix any test failures before proceeding.

- [ ] **Step 3: Commit verification**

```bash
git add -A
git commit -m "chore: verify BREACH_CONFIRMED redesign against spec"
```

---

## Spec Coverage Checklist

| Spec Item | Tasks |
|-----------|-------|
| BEC / ZEC definitions | Task 2, 4 |
| Confirmation rule (max BEC, ZEC) | Task 5 |
| Pending breach stays alive on reversal | Task 5 |
| Fan invalidation silently cancels | Task 5 (existing behavior at line 270) |
| Next target hit → BREACH_CONFIRMED_NO_ALPHA | Task 8 |
| Intra-bar multi-cross → BREACH_CONFIRMED_NO_ALPHA | Task 6 |
| BREACH_CONFIRMED_NO_ALPHA added to enum | Task 1 |
| ZEC passed from AngularCoverageStudy | Task 7 |
| Documentation updated | Already done in brainstorming phase |
