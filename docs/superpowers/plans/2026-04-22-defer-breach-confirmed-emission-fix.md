# Defer BREACH_CONFIRMED Emission — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix retro sweep Path B by deferring BREACH_CONFIRMED emission in section 2 so `_confirm_pending_breach_if_valid` runs first in `angular_coverage_study.py`.

**Architecture:** Instead of emitting `BREACH_CONFIRMED` immediately in section 2's pending breach loop, collect ready breaches in a `deferred_breaches` list. After section 3, expose a `flush_deferred_breaches()` method that `angular_coverage_study.py` calls after `_confirm_pending_breach_if_valid` has run, so `skip_section2` flag is set before emission.

**Tech Stack:** Python, `unified_state_machine.py`, `angular_coverage_study.py`

---

## Files

- **Modify:** `gann-visualizer/backend/study_tool/unified_state_machine.py:23-35` (`__init__`), `296-346` (section 2), `450` (return from process_bar), `480` (new `flush_deferred_breaches` method)
- **Modify:** `gann-visualizer/backend/study_tool/angular_coverage_study.py:699-707` (call flush after _confirm_pending_breach_if_valid), `1130` (also clear deferred breaches when setting skip_section2)

---

## Task 1: Add `deferred_breaches` field to UnifiedStateMachine.__init__

**Files:**
- Modify: `gann-visualizer/backend/study_tool/unified_state_machine.py:23-35`

- [ ] **Step 1: Add `deferred_breaches: List[Tuple]` to `__init__`**

Find the `__init__` method of `UnifiedStateMachine` (around line 23). Add `self.deferred_breaches: List[Tuple] = []` as an instance attribute alongside `self.pending_breaches` and `self.pending_tests`.

```python
def __init__(self, ...):
    ...
    self.pending_breaches: Dict[str, Dict] = {}
    self.pending_tests: Dict[str, Dict] = {}
    self.deferred_breaches: List[Tuple] = []  # NEW: deferred breach emissions
```

- [ ] **Step 2: Commit**

```bash
git add gann-visualizer/backend/study_tool/unified_state_machine.py
git commit -m "feat: add deferred_breaches list to UnifiedStateMachine"
```

---

## Task 2: Modify section 2 to collect instead of emit

**Files:**
- Modify: `gann-visualizer/backend/study_tool/unified_state_machine.py:296-346` (section 2 pending breach update loop)

- [ ] **Step 1: Replace immediate emission with deferred collection for UP direction**

In the section 2 loop, change the UP direction block (lines 321-331) from:
```python
if c_close > max(bec_close, zec_high):
    results.append(EventOutput(
        fan_id=fan_id, fan_identity=fan_identity, priority_label=fan_obj.priority_label,
        fraction=frac_name, price=c_close, event_type='BREACH_CONFIRMED',
        details=f"UP (T+{bars_elapsed} bars)", direction='up'
    ))
    keys_to_remove.append(state_key)
    evaluations.append(f"[{fan_identity} {frac_name}] Pending Breach UP: C ({c_close:.2f}) > max(BEC={bec_close:.2f}, ZEC={zec_high:.2f}) -> BREACH_CONFIRMED")
```

To:
```python
if c_close > max(bec_close, zec_high):
    # Collect for deferred emission - will emit after TARGET_HIT processing
    self.deferred_breaches.append(('up', state_key, fan_id, fan_identity, fan_obj.priority_label, frac_name, c_close, bars_elapsed))
    keys_to_remove.append(state_key)
    evaluations.append(f"[{fan_identity} {frac_name}] Pending Breach UP: C ({c_close:.2f}) > max(BEC={bec_close:.2f}, ZEC={zec_high:.2f}) -> DEFERRED")
```

- [ ] **Step 2: Replace immediate emission with deferred collection for DOWN direction**

In the DOWN direction block (lines 337-346), change similarly:
```python
if c_close < min(bec_close, zec_low):
    results.append(EventOutput(
        fan_id=fan_id, fan_identity=fan_identity, priority_label=fan_obj.priority_label,
        fraction=frac_name, price=c_close, event_type='BREACH_CONFIRMED',
        details=f"DOWN (T+{bars_elapsed} bars)", direction='down'
    ))
    keys_to_remove.append(state_key)
    evaluations.append(f"[{fan_identity} {frac_name}] Pending Breach DOWN: C ({c_close:.2f}) < min(BEC={bec_close:.2f}, ZEC={zec_low:.2f}) -> BREACH_CONFIRMED")
```

To:
```python
if c_close < min(bec_close, zec_low):
    # Collect for deferred emission - will emit after TARGET_HIT processing
    self.deferred_breaches.append(('down', state_key, fan_id, fan_identity, fan_obj.priority_label, frac_name, c_close, bars_elapsed))
    keys_to_remove.append(state_key)
    evaluations.append(f"[{fan_identity} {frac_name}] Pending Breach DOWN: C ({c_close:.2f}) < min(BEC={bec_close:.2f}, ZEC={zec_low:.2f}) -> DEFERRED")
```

- [ ] **Step 3: Commit**

```bash
git add gann-visualizer/backend/study_tool/unified_state_machine.py
git commit -m "feat: defer BREACH_CONFIRMED emission in section 2 pending breach loop"
```

---

## Task 3: Add `flush_deferred_breaches()` method

**Files:**
- Modify: `gann-visualizer/backend/study_tool/unified_state_machine.py` (new method near `_start_pending_breach`)

- [ ] **Step 1: Add `flush_deferred_breaches()` method after the section 3 loop**

After the section 3 loop (after line 349: `del self.pending_breaches[key]`), add a new method:

```python
def flush_deferred_breaches(self) -> List[EventOutput]:
    """
    Emit deferred BREACH_CONFIRMED events, checking skip_section2 flag first.
    Called by angular_coverage_study.py after TARGET_HIT processing has had
    a chance to set skip_section2=True on pending breaches.
    """
    results = []
    for entry in self.deferred_breaches:
        direction, state_key, fan_id, fan_identity, priority_label, frac_name, price, bars_elapsed = entry

        # Check skip_section2 flag - if set, breach was already confirmed as NO_ALPHA
        state = self.pending_breaches.get(state_key)
        if state and state.get('skip_section2'):
            self._log_evaluation(f"[{fan_identity} {frac_name}] Deferred Breach {direction.upper()}: skip_section2=True -> SKIPPED (already NO_ALPHA)")
            # Remove from pending_breaches since already handled
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
            direction=direction
        ))
        self._log_evaluation(f"[{fan_identity} {frac_name}] Deferred Breach {direction.upper()}: -> BREACH_CONFIRMED")
        if state_key in self.pending_breaches:
            del self.pending_breaches[state_key]

    self.deferred_breaches.clear()
    return results
```

Add this method around line 480 (after the section 3 code), right before the `_log_trace` call at the end of `process_bar`.

- [ ] **Step 2: Commit**

```bash
git add gann-visualizer/backend/study_tool/unified_state_machine.py
git commit -m "feat: add flush_deferred_breaches() method for deferred emission"
```

---

## Task 4: Call `flush_deferred_breaches()` in angular_coverage_study.py

**Files:**
- Modify: `gann-visualizer/backend/study_tool/angular_coverage_study.py:699-707` (after _confirm_pending_breach_if_valid)

- [ ] **Step 1: Call `flush_deferred_breaches()` after _confirm_pending_breach_if_valid block**

In the `if target_hit:` block in `angular_coverage_study.py`, after the `_confirm_pending_breach_if_valid` call (line 707), add a call to flush the deferred breaches:

```python
                # Flush deferred BREACH_CONFIRMED events now that TARGET_HIT has had a chance
                # to set skip_section2=True on prior line's pending breach
                deferred_results = self.state_machine.flush_deferred_breaches()
                for evt in deferred_results:
                    ui_events.append({
                        'time': timestamp,
                        'fan': evt.priority_label,
                        'fanIdentity': evt.fan_identity,
                        'fraction': evt.fraction,
                        'price': evt.price,
                        'type': evt.event_type,
                        'details': evt.details,
                        'open': c_open,
                        'high': c_high,
                        'low': c_low,
                        'close': close_price,
                        'activeAngles': active_angle_prices,
                        'cluster': is_cluster,
                        'zone': current_zone_str or "",
                        'zoneExtremes': z_extremes or "",
                        'nextAngleLine': ''
                    })
```

- [ ] **Step 2: Commit**

```bash
git add gann-visualizer/backend/study_tool/angular_coverage_study.py
git commit -m "feat: call flush_deferred_breaches() after TARGET_HIT processing"
```

---

## Task 5: Also flush deferred breaches when setting skip_section2

**Files:**
- Modify: `gann-visualizer/backend/study_tool/angular_coverage_study.py:1130` (when setting skip_section2=True)

- [ ] **Step 1: Clear any deferred breach for this state key when setting skip_section2**

In `_confirm_pending_breach_if_valid()`, after setting `state['skip_section2'] = True` (line 1130), add a line to also remove any deferred breach for this state key so it doesn't get emitted as BREACH_CONFIRMED:

```python
state = state_machine_state[prev_state_key]

# Mark it so section 2 skips its BREACH_CONFIRMED emission
state['skip_section2'] = True

# Also clear from deferred_breaches if present (will be emitted as BREACH_CONFIRMED_NO_ALPHA instead)
self.state_machine.deferred_breaches = [
    d for d in self.state_machine.deferred_breaches
    if d[1] != prev_state_key  # d[1] is state_key in deferred tuple
]

# Confirm the pending breach
self.event_logger.log_event(...)
```

- [ ] **Step 2: Commit**

```bash
git add gann-visualizer/backend/study_tool/angular_coverage_study.py
git commit -m "feat: clear deferred breach when confirming as BREACH_CONFIRMED_NO_ALPHA"
```

---

## Task 6: Verify the fix with simulation

- [ ] **Step 1: Re-run the backend simulation**

Run:
```bash
cd c:/Dev/GannTesting/gann-visualizer/backend && python run_simulation.py --symbol "^NSEI" --resolution "4" --source "yfinance"
```

- [ ] **Step 2: Check simulation_trace.log for 10:55 AM Bar 25 L2-H1**

Expected: Line 63 should now show `DEFERRED` instead of `BREACH_CONFIRMED`:
```
[RETRO] [Bar 25] [2026-04-09 10:55] ... -> [L2-H1 0.875] Pending Breach UP: C (23828.85) > max(BEC=23825.40, ZEC=23825.40) -> DEFERRED
```

Also look for the flushed emission after TARGET_HIT:
```
[Tracking] BREACH_CONFIRMED_NO_ALPHA: found pending on Fan_L2_H1_Fan_L2_H1_f0 fraction=0.875 bar=25 (cross-bar)
```

And the deferred BREACH_CONFIRMED that should be SKIPPED:
```
Deferred Breach UP: skip_section2=True -> SKIPPED (already NO_ALPHA)
```

- [ ] **Step 3: Check simulation_events.csv for 10:55 AM L2-H1 0.875 row**

Expected: Row with fraction=0.875 and fan=P1 (L2-H1) at 10:55 AM should show `BREACH_CONFIRMED_NO_ALPHA` (not `BREACH_CONFIRMED`).

- [ ] **Step 4: Commit the verified fix**

```bash
git add -A
git commit -m "fix: defer BREACH_CONFIRMED emission so TARGET_HIT can confirm prior breach as NO_ALPHA"
```