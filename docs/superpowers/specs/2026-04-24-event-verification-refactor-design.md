# Event Verification Refactor Design

**Date:** 2026-04-24
**Status:** Draft

---

## Problem

The current event verification script (`verify_trace_events.py`) produces confusing output with terminology (SOFT_CHECK, UNHANDLED, etc.) that was never formally defined. It cannot comprehensively verify event accuracy or detect missed events because the trace log lacks structured state context for state-dependent event types.

**Goal:** Two questions, answered clearly:
1. **Accuracy** — Of the events that fired, were they correct?
2. **Completeness** — Did any bars where the state machine evaluated a line miss an event they should have caught?

---

## Scope

The refactor has two parts:
1. **Enhance the trace log** to emit structured state context alongside human-readable output (preserving replay compatibility)
2. **Refactor the verification script** to produce a clean, simple report answering accuracy and completeness

---

## Part 1: Trace Log Enhancement

### Principle
The replay trace log must remain identical to the simulation trace log. The state machine writes to a shared `_log_trace()` method used by both simulation and replay. Changes must not alter existing human-readable event strings.

### Change: Add `[STATE]` Blocks

After each bar's evaluation lines (the `-> event_type` lines), append structured `[STATE]` blocks for state-dependent events. These are **additional lines** — they do not modify existing output.

#### Placement
For each bar, the `[STATE]` block appears after all evaluation lines for that bar, before the next bar's header.

#### Format

**Pending Breach (BREACH_CONFIRMED / BREACH_CONFIRMED_NO_ALPHA / DEFERRED):**
```
[STATE] pending_breach: fan={fan_id} line={fraction} direction={UP|DOWN} bec_close={float} zec_high={float} zec_low={float} pending_bar={bar_index} outcome={BREACH_CONFIRMED|BREACH_CONFIRMED_NO_ALPHA|DEFERRED}
```

**Pending Test (SUPPORT_BOUNCE / RESISTANCE_REJECTION):**
```
[STATE] pending_test: fan={fan_id} line={fraction} direction={UP|DOWN} trigger_close={float} trigger_bar={bar_index}
```

**Fan Validated:**
```
[STATE] fan_validated: fan={fan_id} origin_bar={bar_index} breach_close={float}
```

**Fan Deactivated:**
```
[STATE] fan_deactivated: fan={fan_id} reason={COMPLETED|INVALIDATED}
```

**Target Hit:**
```
[STATE] target_hit: fan={fan_id} line={fraction} target={fraction_value} hit_bar={bar_index}
```

#### Implementation Location
`UnifiedStateMachine._log_trace()` — append `[STATE]` lines to the `all_evals` list before writing. The caller (`angular_coverage_study.py`) passes the state context via `process_bar()` return values or existing state dictionaries.

#### Code Changes

**unified_state_machine.py:**
- Add `pending_breach_state`, `pending_test_state` fields to store context as events are created
- Modify `_log_trace()` to serialize these into `[STATE]` blocks alongside evaluation lines

**angular_coverage_study.py:**
- At the point where `BREACH_CONFIRMED`, `BREACH_CONFIRMED_NO_ALPHA`, `DEFERRED`, `SUPPORT_BOUNCE`, `RESISTANCE_REJECTION`, `FAN_VALIDATED`, `FAN_DEACTIVATED`, `TARGET_HIT` events are created, store the relevant context (BEC close, ZEC values, trigger candle, fan_id, line fraction) into the state machine's state fields so `_log_trace()` can emit them

**Key constraint:** No existing event string format changes. `[STATE]` blocks are strictly additive lines after the `-> outcome` lines.

---

## Part 2: Verification Script Refactor

### Output Format

The script produces **one CSV** and **one text report**.

#### Report (`TRACE_AUDIT_REPORT.txt`)

```
=== EVENT VERIFICATION REPORT ===
Generated: {timestamp}
Source: {events_csv}, {trace_log}

ACCURACY (events that fired — were they correct per EVENT_TYPES.md definitions?)
  Events checked: {N}
  Accurate: {N} ({pct}%)
  Inaccurate: {N} ({pct}%)
    — list of (bar, timestamp, fan, line, event_type, expected_condition, actual)

  NOTE: Accuracy must be 100%. Any inaccuracy is a bug in event detection logic.

STATE-DEPENDENT EVENTS (verified via [STATE] blocks — not re-evaluated)
  {N} events (BREACH_CONFIRMED_NO_ALPHA, TARGET_HIT, FAN_VALIDATED, etc.)
    — list of (bar, event_type, [STATE] context present: YES/NO)

COMPLETENESS (bars where state machine evaluated a line — were all events caught?)
  Bars evaluated: {N}
  Events correctly identified: {N}
  Missed events: {N}  ← bars where OHLC meets event definition but no event in CSV
    — list of (bar, timestamp, fan, line, expected_event, reason_missed)

SUMMARY
  Accuracy: {pct}%  (100% required)
  Completeness: {pct}%
  Status: PASS / FAIL
```

#### Verification CSV (`EVENT_VERIFICATION.csv`)

Columns:
- `bar_index`, `timestamp`, `fan`, `fraction`, `event_type`, `line_price`, `ohlc`
- `accuracy_result`: `ACCURATE` / `INACCURATE` / `PARTIAL` / `N/A`
- `accuracy_detail`: for inaccurate events, what was wrong
- `missed_event`: `YES` / `NO` / `N/A`
- `missed_detail`: for missed events, what was missed

### Verification Logic

**ACCURATE / INACCURATE** — applied per event:

| Event Type | Verification Method |
|---|---|
| CROSS_UP | O ≤ line AND C ≥ line → ACCURATE else INACCURATE |
| CROSS_DOWN | O ≥ line AND C ≤ line → ACCURATE else INACCURATE |
| SUPPORT_TEST | O ≥ line AND C ≥ line AND L ≤ line AND C > line → ACCURATE |
| RESISTANCE_TEST | O ≤ line AND C ≤ line AND H ≥ line AND C > line → ACCURATE |
| SUPPORT_TOUCH | O ≥ line AND C ≥ line AND L ≤ line AND C == line → ACCURATE |
| RESISTANCE_TOUCH | O ≤ line AND C ≤ line AND H ≥ line AND C == line → ACCURATE |
| BREACH_CONFIRMED | verify against [STATE] block: C > max(BEC, ZEC) or C < min(BEC, ZEC) |
| BREACH_CONFIRMED_NO_ALPHA | [STATE] block available — Path A (intra-bar) or Path B (target hit before breach) |
| DEFERRED | [STATE] block available — C did not breach BEC/ZEC boundary |
| FAN_VALIDATED | [STATE] block available |
| TARGET_HIT | [STATE] block available |
| FAN_DEACTIVATED | [STATE] block available |
| SUPPORT_BOUNCE | [STATE] block: pending_test context + subsequent bar C ≥ trigger + threshold |
| RESISTANCE_REJECTION | [STATE] block: pending_test context + subsequent bar C ≤ trigger - threshold |

**MISSED EVENT detection:**

For each bar where the state machine evaluated at least one line:
1. Parse all line prices evaluated on that bar from the trace
2. For each (fan, line_fraction, line_price), check if the bar's OHLC meets any event definition
3. If an event definition is met but no matching event appears in the CSV → MISSED

The check covers only: CROSS_UP, CROSS_DOWN, SUPPORT_TEST, RESISTANCE_TEST, SUPPORT_TOUCH, RESISTANCE_TOUCH.

**What does NOT count as a missed event:**
- "No Intersection Detected" bars — the state machine correctly determined no line was near enough to evaluate
- State-dependent events (BREACH_CONFIRMED, TARGET_HIT, etc.) — these require cross-bar state only available via [STATE] blocks

---

## Files Changed

1. `gann-visualizer/backend/study_tool/unified_state_machine.py` — add state serialization to `_log_trace()`
2. `gann-visualizer/backend/study_tool/angular_coverage_study.py` — populate state context before emitting events
3. `gann-visualizer/backend/analysis/verify_trace_events.py` — complete rewrite with clean report output

---

## Backward Compatibility

- Existing trace log format is unchanged — `[STATE]` blocks are additive
- Replay output is unchanged — replay's `_log_trace()` also emits `[STATE]` blocks (same code path)
- Old verification reports are not generated; new script replaces old one

---

## Decisions

1. **Accuracy threshold: 100%** — Algorithmic trading has deterministic rules; any inaccuracy is a bug
2. **TOUCH events: classify as SUPPORT_TOUCH or RESISTANCE_TOUCH** — Every intersection that doesn't meet CROSS criteria still has directional context based on where the close is relative to the line. If `C > line_price` → SUPPORT_TOUCH, if `C < line_price` → RESISTANCE_TOUCH. Generic "TOUCH" is not a valid terminal event type.
3. **Trace log format: additive [STATE] blocks only** — Do not modify existing human-readable event strings. The [STATE] block is an additional line after all evaluations for a bar. This preserves replay trace log compatibility.

## ML Training Data Structure

The trace log is human-readable debugging output. For ML training, a separate structured dataset is needed.

### ML Event Table (`events_ml.csv`)

Produced by the verification script alongside the accuracy report. A fully-labeled, machine-readable event dataset.

Columns:
- `bar_index`, `timestamp`, `fan_id`, `fraction`, `line_price`
- `open`, `high`, `low`, `close`
- `event_type` — one of: `CROSS_UP`, `CROSS_DOWN`, `SUPPORT_TEST`, `RESISTANCE_TEST`, `SUPPORT_TOUCH`, `RESISTANCE_TOUCH`, `BREACH_CONFIRMED`, `BREACH_CONFIRMED_NO_ALPHA`, `TARGET_HIT`, `FAN_VALIDATED`, `FAN_DEACTIVATED`, `TARGET_FAILED`, `SUPPORT_BOUNCE`, `RESISTANCE_REJECTION`
- `direction` — UP / DOWN / N/A
- `zone`, `zone_high`, `zone_low`, `bec_close`, `zec_high`, `zec_low`
- `target_hit_sequence` — for TARGET_HIT, which target in sequence (0.875 / 0.75 / 0.5 / horizontal / 0.25 / full_coverage)
- `bars_elapsed` — bars since last event on this fan/line
- `is_missed_event` — TRUE if this was a missed detection (completeness gap found)
- `accuracy_verified` — TRUE / FALSE / N/A

This dataset is self-contained: every row has all context needed for ML training without referencing external state.

### ML Bar Features Table (`bars_ml.csv`)

For bars where no event fired but a line was evaluated (the "near miss" bars), produce a features-only table for ML training on negative cases.

Columns:
- `bar_index`, `timestamp`, `fan_id`, `fraction`, `line_price`
- `open`, `high`, `low`, `close`, `range`, `body_size`
- `distance_to_line` — how far nearest line was from price
- `nearest_line_direction` — line above/below price
- `event_type` — always `NONE` for these rows
- `zone`, `zone_high`, `zone_low`
- `reason_no_event` — why no event fired (e.g., "close did not cross line", "wick did not pierce line")

Combined with `events_ml.csv`, this gives ML training a complete picture: labeled positive cases + labeled negative cases from the same distribution of evaluated bars.

## Open Questions

- ~~should the ML CSVs be produced only for bars that pass accuracy check, or for all bars including inaccurate ones (with an `is_accurate` flag)?~~ → **All events included in events_ml.csv, with `is_accurate=FALSE` for inaccurate ones**
- ~~The [STATE] block format needs review once implemented — it must not interfere with replay trace log parsing~~ → **Confirmed: [STATE] blocks on separate lines do not break existing replay trace log parsing**
