# Post-0.5 Target Progression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct target progression after 0.5 so horizontal and 0.25 are concurrent independent targets — neither cancels the other, full coverage still achievable after 0.25 is hit first.

**Architecture:** `FanTargetState.targets_remaining` becomes the sole source of truth for post-0.5 tracking. `current_target` is `None` after 0.5 until only one target remains. `_handle_quarter_before_horizontal()` is deleted.

**Tech Stack:** Python, pytest, `target_progression.py`

---

## File Map

| File | Responsibility |
|------|----------------|
| `gann-visualizer/backend/study_tool/target_progression.py` | Core state machine — all logic changes here |
| `gann-visualizer/backend/tests/test_target_progression.py` | Tests — update method names + add new concurrent-behavior tests |
| `gann-visualizer/backend/docs/EVENT_TYPES.md` | Already updated in brainstorming phase |

---

## Task 1: Add `quarter_before_horizontal` field to `FanTargetState`

**Files:**
- Modify: `gann-visualizer/backend/study_tool/target_progression.py:37-56`

- [ ] **Step 1: Add the field to `FanTargetState` dataclass**

In the dataclass definition, add `quarter_before_horizontal: bool = False` after `horizontal_target_active`.

---

## Task 2: Update `_advance_target()` — post-0.5 concurrent model

**Files:**
- Modify: `gann-visualizer/backend/study_tool/target_progression.py:252-298`

- [ ] **Step 1: Update `just_hit == '0.5'` branch**

Replace lines 256-265:

```python
if just_hit == '0.5':
    if state.horizontal_target_active and state.horizontal_target_price is not None:
        state.current_target = 'horizontal'
        state.targets_remaining = ['horizontal']
    else:
        state.current_target = '0.25'
        state.targets_remaining = ['0.25']
    return
```

With:

```python
if just_hit == '0.5':
    # Both targets active concurrently; list-based tracking is source of truth
    state.current_target = None
    if state.horizontal_target_active and state.horizontal_target_price is not None:
        state.targets_remaining = ['horizontal', '0.25']
    else:
        state.targets_remaining = ['0.25']
    return
```

- [ ] **Step 2: Update `just_hit == 'horizontal'` branch (lines 271-276)**

After `state.current_target = FINAL_TARGET` block, update to check if 0.25 is still pending:

```python
if just_hit == 'horizontal':
    state.current_target = FINAL_TARGET
    state.targets_remaining = [FINAL_TARGET]
    return
```

This is unchanged — horizontal-first path already proceeds to full_coverage. But the next step handles the case where 0.25 hasn't been hit yet — actually, `horizontal` is in `targets_remaining` but we just hit it, so we need to also check the remaining list.

Replace the entire block after `if just_hit == 'horizontal':` with:

```python
if just_hit == 'horizontal':
    # Horizontal hit — if 0.25 already hit too, go to full_coverage
    # Otherwise 0.25 remains pending
    if '0.25' in state.targets_hit:
        state.current_target = FINAL_TARGET
        state.targets_remaining = [FINAL_TARGET]
    else:
        state.current_target = '0.25'
        state.targets_remaining = ['0.25']
    return
```

- [ ] **Step 3: Update `just_hit == '0.25'` branch (lines 278-288)**

Replace:

```python
if just_hit == '0.25':
    # 1/4 was the last target if horizontal was cancelled
    if 'horizontal' not in state.targets_hit:
        # 1/4 reached but horizontal wasn't — no more targets
        state.current_target = None
        state.completed = True
    else:
        # Both horizontal and 1/4 were hit — proceed to full coverage
        state.current_target = FINAL_TARGET
        state.targets_remaining = [FINAL_TARGET]
    return
```

With:

```python
if just_hit == '0.25':
    # Record ordering metadata for replay analysis
    if 'horizontal' not in state.targets_hit:
        state.quarter_before_horizontal = True
    # 0.25 hit — if horizontal already hit too, go to full_coverage
    # Otherwise horizontal remains pending
    if 'horizontal' in state.targets_hit:
        state.current_target = FINAL_TARGET
        state.targets_remaining = [FINAL_TARGET]
    else:
        state.current_target = 'horizontal'
        state.targets_remaining = ['horizontal']
    return
```

---

## Task 3: Update `on_angle_contact()` — remove old special case routing

**Files:**
- Modify: `gann-visualizer/backend/study_tool/target_progression.py:126-190`

- [ ] **Step 1: Remove `_handle_quarter_before_horizontal()` special case at lines 166-170**

Replace:

```python
if state.current_target != angle_name:
    # Special case: 1/4 reached before horizontal
    if angle_name == '0.25' and state.current_target == 'horizontal':
        return self._handle_quarter_before_horizontal(state, bar_index, price)
    return None
```

With:

```python
if state.current_target is not None and state.current_target != angle_name:
    # current_target is set — only process if this is the active target
    return None
```

Then handle the case where `current_target is None` (post-0.5 concurrent state) — we still want to process hits for targets in `targets_remaining`. Add after the dedup check (after `state.angles_contacted.append(angle_name)`):

```python
# When current_target is None (post-0.5), process if angle is in targets_remaining
if state.current_target is None:
    if angle_name not in state.targets_remaining:
        return None
    # Valid concurrent hit — fall through to record and advance
```

---

## Task 4: Delete `_handle_quarter_before_horizontal()`

**Files:**
- Modify: `gann-visualizer/backend/study_tool/target_progression.py:299-326`

- [ ] **Step 1: Delete the entire method**

Remove the entire `_handle_quarter_before_horizontal` method (lines 299-326).

---

## Task 5: Update `FanTargetState.to_dict()` and `from_dict()` if needed

**Files:**
- Modify: `gann-visualizer/backend/study_tool/target_progression.py:57-63`

- [ ] **Step 1: Verify dataclass serialization handles new field**

`to_dict()` uses `asdict(self)` and `from_dict()` uses `cls(**data)` — both are auto-generated and handle new fields automatically. No changes needed.

---

## Task 6: Update tests to use `on_angle_contact()` + new behavior

**Files:**
- Modify: `gann-visualizer/backend/tests/test_target_progression.py`

- [ ] **Step 1: Replace all `on_breach_confirmed` calls with `on_angle_contact`**

In every test method, replace:
```python
tp.on_breach_confirmed('fan1', '7/8', 10, 100.0)
```
With:
```python
tp.on_angle_contact('fan1', '0.875', 10, 100.0)
```

Note: angle names in tests are `'7/8'`, `'3/4'`, `'1/2'`, `'1/4'` but the code uses `'0.875'`, `'0.75'`, `'0.5'`, `'0.25'`. Update the angle names in test calls to match the code's string representation.

- [ ] **Step 2: Update `test_target_sequence_basic`**

Replace the `on_breach_confirmed` calls and assertions to use `on_angle_contact` with correct angle names:

```python
def test_target_sequence_basic(self):
    """Standard progression: 7/8 → 3/4 → 1/2 → [horizontal, 0.25]."""
    tp = TargetProgression()
    tp.register_fan('fan1', horizontal_target_price=105.0, full_coverage_target_price=110.0)
    tp.activate_fan('fan1')

    # Hit 0.875
    hit = tp.on_angle_contact('fan1', '0.875', bar_index=10, price=100.0)
    assert hit is not None
    assert hit.target_name == '0.875'
    assert tp.get_current_target('fan1') == '0.75'

    # Hit 0.75
    hit = tp.on_angle_contact('fan1', '0.75', bar_index=20, price=102.0)
    assert hit is not None
    assert tp.get_current_target('fan1') == '0.5'

    # Hit 0.5
    hit = tp.on_angle_contact('fan1', '0.5', bar_index=30, price=105.0)
    assert hit is not None
    # After 0.5, current_target is None (concurrent state)
    assert tp.get_current_target('fan1') is None
    state = tp.get_fan_state('fan1')
    assert 'horizontal' in state.targets_remaining
    assert '0.25' in state.targets_remaining
```

- [ ] **Step 3: Update `test_horizontal_then_full_coverage`**

```python
def test_horizontal_then_full_coverage(self):
    """After horizontal breach (with 0.25 already hit), go to full_coverage."""
    tp = TargetProgression()
    tp.register_fan('fan1', horizontal_target_price=105.0, full_coverage_target_price=110.0)
    tp.activate_fan('fan1')

    tp.on_angle_contact('fan1', '0.875', 10, 100.0)
    tp.on_angle_contact('fan1', '0.75', 20, 102.0)
    tp.on_angle_contact('fan1', '0.5', 30, 105.0)

    # Both targets now pending — hit 0.25 first
    hit = tp.on_angle_contact('fan1', '0.25', bar_index=35, price=103.0)
    assert hit is not None
    assert hit.target_name == '0.25'
    assert tp.get_current_target('fan1') == 'horizontal'

    # Now hit horizontal
    hit = tp.on_angle_contact('fan1', 'horizontal', bar_index=40, price=106.0)
    assert hit is not None
    assert tp.get_current_target('fan1') == 'full_coverage'

    # Hit full coverage
    tp.on_angle_contact('fan1', 'full_coverage', bar_index=50, price=110.0)
    assert tp.is_fan_completed('fan1')
```

- [ ] **Step 4: Replace `test_quarter_before_horizontal_cancels_target`**

Replace the entire test with:

```python
def test_quarter_before_horizontal_keeps_fan_open(self):
    """If 1/4 is reached before horizontal, fan stays open — horizontal remains pending."""
    tp = TargetProgression()
    tp.register_fan('fan1', horizontal_target_price=105.0, full_coverage_target_price=110.0)
    tp.activate_fan('fan1')

    tp.on_angle_contact('fan1', '0.875', 10, 100.0)
    tp.on_angle_contact('fan1', '0.75', 20, 102.0)
    tp.on_angle_contact('fan1', '0.5', 30, 105.0)

    # 0.25 arrives first — fan stays open
    hit = tp.on_angle_contact('fan1', '0.25', bar_index=35, price=98.0)
    assert hit is not None
    assert hit.target_name == '0.25'
    assert tp.is_fan_completed('fan1') is False
    assert tp.get_current_target('fan1') == 'horizontal'

    # Verify ordering metadata
    state = tp.get_fan_state('fan1')
    assert state.quarter_before_horizontal is True
    assert state.horizontal_target_active is True  # NOT cancelled

    # Now hit horizontal — should proceed to full_coverage
    tp.on_angle_contact('fan1', 'horizontal', bar_index=40, price=106.0)
    assert tp.get_current_target('fan1') == 'full_coverage'
```

- [ ] **Step 5: Update remaining tests (`test_wrong_target_ignored`, `test_no_horizontal_target`, `test_target_hits_history`, `test_serialization_roundtrip`)**

Replace all `on_breach_confirmed` calls with `on_angle_contact` and update angle name strings.

For `test_no_horizontal_target`, after 0.5, with no horizontal:
- `current_target` should be `None`
- `targets_remaining` should be `['0.25']`

```python
def test_no_horizontal_target(self):
    """If no horizontal target price is provided, 0.25 is still a concurrent target after 1/2."""
    tp = TargetProgression()
    tp.register_fan('fan1', horizontal_target_price=None, full_coverage_target_price=110.0)
    tp.activate_fan('fan1')

    tp.on_angle_contact('fan1', '0.875', 10, 100.0)
    tp.on_angle_contact('fan1', '0.75', 20, 102.0)
    tp.on_angle_contact('fan1', '0.5', 30, 105.0)

    # No horizontal → current_target is None, 0.25 is the only pending target
    state = tp.get_fan_state('fan1')
    assert state.targets_remaining == ['0.25']
    assert tp.get_current_target('fan1') is None
```

- [ ] **Step 6: Run all tests**

Run: `cd c:\Dev\GannTesting\gann-visualizer\backend && python -m pytest tests/test_target_progression.py -v`

Expected: All 8 tests pass.

---

## Task 7: Verify the module docstring is updated

**Files:**
- Modify: `gann-visualizer/backend/study_tool/target_progression.py:1-16`

- [ ] **Step 1: Verify docstring reflects concurrent model**

The docstring was already updated during brainstorming. Verify it now reads:

```
Target sequence per fan:
    7/8 → 3/4 → 1/2 → [horizontal_target, 1/4] (concurrent) → full_coverage

Special rules:
- Fan is only active for progression after FanValidator marks it validated
- After 1/2 breach, both horizontal_target and 1/4 are active concurrently,
  hit in any order — neither cancels the other
- After both horizontal and 1/4 are hit, final target is full_coverage
  (Michael Jenkins secret angle method — other pivot's price)
```

---

## Task 8: Commit

- [ ] **Step 1: Commit**

```bash
git add gann-visualizer/backend/study_tool/target_progression.py gann-visualizer/backend/tests/test_target_progression.py gann-visualizer/backend/docs/EVENT_TYPES.md docs/superpowers/specs/2026-04-21-post-half-target-progression-design.md
git commit -m "$(cat <<'EOF'
feat: correct post-0.5 target progression — horizontal and 0.25 are concurrent

Both horizontal and 0.25 are now independent targets after 0.5 is hit.
Neither cancels the other. Fan stays open after 0.25 hit first; full
coverage still pursued. Hit ordering metadata recorded for replay analysis.

Breaks: test_quarter_before_horizontal_cancels_target (old behavior removed)
Fixes: target_progression.py concurrent-target design per 2026-04-21 spec

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|------------------|------|
| Concurrent model post-0.5 | Task 2, 3 |
| current_target = None after 0.5 | Task 2 |
| Fan stays open after 0.25 hit first | Task 2, 4 |
| quarter_before_horizontal metadata | Task 1, 2 |
| Delete _handle_quarter_before_horizontal | Task 4 |
| Update EVENT_TYPES.md | Already done |
| Update module docstring | Task 7 |
| All tests pass | Task 6 |