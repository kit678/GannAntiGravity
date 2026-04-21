# Post-0.5 Target Progression Redesign

## Status

Approved: 2026-04-21

## Overview

Correct the target progression behavior after the 0.5 (1/2) angle division line is hit. The previous implementation treated `horizontal` and `0.25` as a mutually exclusive race — whichever was hit first would cancel the other and potentially complete the fan. The corrected behavior treats both as independent, concurrent targets.

## Problem

After 0.5 is hit, the fan's remaining target sequence was modeled as:
```
[horizontal | 0.25]   # one or the other, not both
→ full_coverage
```

This caused incorrect behavior:
- If 0.25 was hit first, `horizontal` was cancelled and the fan was marked COMPLETE immediately
- Full coverage was not pursued when 0.25 was hit before horizontal
- Price reaction at 0.25 (reversal, bounce) was conflated with fan completion

Observed trading behavior contradicts the old model:
- 0.25 often acts as a reaction/reversal level
- Full coverage is still achievable even if 0.25 is hit first
- Horizontal remains a valid target regardless of 0.25 hit ordering

## Design

### Concurrent Target Model

After 0.5 is hit, both `horizontal` and `0.25` are **active concurrently** — independent targets, hit in any order, both valid:

```
0.875 → 0.75 → 0.5 → [horizontal, 0.25] → full_coverage
```

- `targets_remaining` holds both: `['horizontal', '0.25']`
- `current_target` is set to `None` (list-based tracking is the source of truth)
- Fan stays open (not COMPLETE) until all targets are resolved
- Only proceeds to `full_coverage` when both are hit

### Hit Processing

When either `horizontal` or `0.25` is hit:

1. Emit `TargetHit` event with `details` noting hit ordering:
   - `TargetHit(target_name='0.25', details="hit_before_horizontal")` when 0.25 hit first
   - `TargetHit(target_name='horizontal', details="hit_before_quarter")` when horizontal hit first
2. Remove the hit target from `targets_remaining`
3. If the other target is still pending: set `current_target = remaining_target`
4. If both are hit: advance to `full_coverage`

### Horizontal-First Path

When horizontal is hit first:
- `targets_remaining` becomes `['0.25']`
- `current_target` becomes `'0.25'`
- Fan continues toward 0.25, then full_coverage

### Quarter-First Path

When 0.25 is hit first:
- `targets_remaining` becomes `['horizontal']`
- `current_target` becomes `'horizontal'`
- Fan continues toward horizontal (full coverage still possible)
- The `TargetHit` for 0.25 includes `details="hit_before_horizontal"` for replay filtering

### Unknown Behavior Flag

The `TargetHit.details` field is used to tag cases where 0.25 was hit before horizontal. This allows replay/simulation analysis to mine the unknown price behavior in these scenarios without changing the event schema.

## Files to Modify

### `gann-visualizer/backend/study_tool/target_progression.py`

1. **Module docstring** (lines 1-16): Remove "horizontal target is cancelled" special rule
2. **`_advance_target()`** for `just_hit == '0.5'`: Set `current_target = None`, `targets_remaining = ['horizontal', '0.25']`
3. **`on_angle_contact()`** (lines 166-170): Remove `_handle_quarter_before_horizontal()` special case routing; use normal `targets_remaining` check
4. **`_advance_target()`** for `just_hit in ('horizontal', '0.25')`: If one is hit and the other is still pending, keep fan open with remaining target. Only advance to `full_coverage` when both are hit.
5. **`_handle_quarter_before_horizontal()`**: Delete — no longer needed as a separate path
6. **`FanTargetState`**: Add `quarter_before_horizontal: bool = False` field for ordering metadata

### `gann-visualizer/backend/docs/EVENT_TYPES.md`

1. **Target Progression Sequence** section (lines 141-151): Update to reflect concurrent model
2. **TARGET_HIT semantic** (line 92): Clarify that post-half targets are concurrent

## Acceptance Criteria

1. When 0.5 is hit → `targets_remaining` contains both `horizontal` and `0.25`
2. Fan does NOT complete when 0.25 is hit first — `completed = False`, `horizontal` remains in `targets_remaining`
3. If horizontal is subsequently hit → fan advances to `full_coverage`
4. `TargetHit` for 0.25 hit before horizontal includes `details="hit_before_horizontal"`
5. `FanTargetState.current_target` is `None` after 0.5 until only one target remains
6. All existing tests pass after changes