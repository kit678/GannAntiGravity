# Event Type Reference

**Single source of truth for all event types in the Gann trading visualization system.**

---

## Overview

Event types are emitted by two main sources:
1. **AngularPriceCoverageStudy** (`angular_coverage_study.py`) - Direct event emission
2. **UnifiedStateMachine** (`unified_state_machine.py`) - Returns EventOutput objects with string event types

---

## Frontend Alignment Types

*These map directly to frontend UI columns and MUST maintain exact string values.*

### CROSS_UP
- **Value**: `"CROSS_UP"`
- **Semantic**: Price opens at or below the line and closes above it (or gap cross above)
- **Emission Mechanism**: `UnifiedStateMachine.process_bar()` — `c_open <= line_price AND c_close > line_price`
- **Fires When**: Strict candle close crosses above the line (or prev_close < prev_line AND c_close > line for gap cross)

### CROSS_DOWN
- **Value**: `"CROSS_DOWN"`
- **Semantic**: Price opens at or above the line and closes below it (or gap cross below)
- **Emission Mechanism**: `UnifiedStateMachine.process_bar()` — `c_open >= line_price AND c_close < line_price`
- **Fires When**: Strict candle close crosses below the line (or prev_close > prev_line AND c_close < line for gap cross)

### SUPPORT_TEST
- **Value**: `"SUPPORT_TEST"`
- **Semantic**: Candle opens and closes above line, but low wick touches/pierces line
- **Emission Mechanism**: `UnifiedStateMachine.process_bar()` — `c_open >= line_price AND c_close >= line_price AND c_low <= line_price`
- **Fires When**: Body holds above line but wick touches the line from above

### RESISTANCE_TEST
- **Value**: `"RESISTANCE_TEST"`
- **Semantic**: Candle opens and closes below line, but high wick touches/pierces line
- **Emission Mechanism**: `UnifiedStateMachine.process_bar()` — `c_open <= line_price AND c_close <= line_price AND c_high >= line_price`
- **Fires When**: Body holds below line but wick touches the line from below

### SUPPORT_BOUNCE
- **Value**: `"SUPPORT_BOUNCE"`
- **Semantic**: Price bounces up by threshold % after a SUPPORT_TEST
- **Emission Mechanism**: `UnifiedStateMachine.process_bar()` — after SUPPORT_TEST, if `c_close >= line_price + threshold` within lookback bars
- **Cancellation**: If before a bounce confirms, price closes below the `candle_close` of the triggering test candle, the pending test is cancelled without event
- **Fires When**: Confirmation that price rejected down from support and bounced

### RESISTANCE_REJECTION
- **Value**: `"RESISTANCE_REJECTION"`
- **Semantic**: Price rejects down by threshold % after a RESISTANCE_TEST
- **Emission Mechanism**: `UnifiedStateMachine.process_bar()` — after RESISTANCE_TEST, if `c_close <= line_price - threshold` within lookback bars
- **Cancellation**: If before a rejection confirms, price closes above the `candle_close` of the triggering test candle, the pending test is cancelled without event
- **Fires When**: Confirmation that price rejected up from resistance and fell

### FAN_DEACTIVATED
- **Value**: `"FAN_DEACTIVATED"`
- **Semantic**: Fan deactivated/completed (not invalidated)
- **Emission Mechanism**: `angular_coverage_study.py` — when fan anchor time is reached and fan completes its run
- **Fires When**: Fan anchor bar time is reached

---

## Core Event Types

### BREACH_CONFIRMED
- **Value**: `"breach_confirmed"`
- **Semantic**: Price closes beyond the extreme of (BEC close OR ZEC extreme). For multi-line crosses, all except furthest line get immediate intrabar confirmation.
- **Emission Mechanism**: `UnifiedStateMachine.process_bar()` — pending breach confirmation using BEC and ZEC of the prior zone
- **Supporting Definitions**:
  - **BEC (Breach Extreme Close)**: The `close` price of the candle that creates the pending breach (i.e., the candle that crosses the line).
  - **ZEC (Zone Extreme Close)**: The highest close (for UP) or lowest close (for DOWN) of all candles whose closes fall within the prior zone (the zone immediately preceding the BEC's zone). Retrieved from `AngleZoneTracker._historical_zones` at the last bar where the zone was Z_PRIOR.
- **Fires When**:
  - UP: `c_close > max(BEC_close, ZEC_highest_close)`
  - DOWN: `c_close < min(BEC_close, ZEC_lowest_close)`
- **Note**: Core state machine event; frontend receives via ui_events with type='BREACH_CONFIRMED'

### BREACH_CONFIRMED_NO_ALPHA
- **Value**: `"BREACH_CONFIRMED_NO_ALPHA"`
- **Semantic**: Breach confirmed but no tradeable alpha — either intra-bar stacked confirmation or next target hit before breach confirmation.
- **Emission Mechanism**: `UnifiedStateMachine.process_bar()` — intra-bar multi-cross logic, and when next target is hit before pending breach confirms
- **Fires When**:
  - **Intra-bar multi-cross**: When multiple CROSS_UP/CROSS_DOWN events fire on the same bar across different lines, intermediate lines fire `BREACH_CONFIRMED_NO_ALPHA`. The furthest line fires its normal event.
  - **Next target hit before confirmation**: When `TARGET_HIT` fires on a line before the pending breach on the prior line has confirmed, the pending breach fires `BREACH_CONFIRMED_NO_ALPHA`.
- **Note**: Distinguishable from `BREACH_CONFIRMED` so trading algorithms can exclude these from alpha calculations.

### TARGET_HIT
- **Value**: `"target_hit"`
- **Semantic**: First contact with an angle line in the target progression sequence. Only fires once per line; subsequent contacts are ignored.
- **Emission Mechanism**: `angular_coverage_study.py` via `target_progression.on_angle_contact()`
- **Fires When**: Price first touches any angle line in the target progression sequence (0.875 → 0.75 → 0.5 → [horizontal and 0.25 concurrently] → full_coverage). Post-0.5 targets (horizontal, 0.25) are independent and concurrent — both must be hit before full_coverage. Hit ordering is recorded in `TargetHit.details` (e.g., `"hit_before_horizontal"` on the 0.25 hit).
- **Intra-bar side effect**: When `TARGET_HIT` fires on line N+1 and the same bar created a pending breach on line N (via `CROSS_UP`/`CROSS_DOWN`), the pending breach on line N is immediately confirmed as `BREACH_CONFIRMED_NO_ALPHA`. This ensures `BREACH_CONFIRMED_NO_ALPHA` and `TARGET_HIT` appear in the same bar when price crosses one line and touches the next in sequence.

### TARGET_FAILED
- **Value**: `"target_failed"`
- **Semantic**: Fan was invalidated while a target progression was in-flight (breach confirmed on origin angle but next target was not reached before fan became invalid)
- **Emission Mechanism**: `angular_coverage_study.py` in `_sync_fans()` — when fan is deactivated and `has_pending_progression()` returns True
- **Fires When**: Fan gets invalidated (either price crosses anchor point, or an opposite-direction fan takes over) AND there was a breach confirmed on the origin angle but the progression was not completed
- **Note**: Previously fired when price crossed back over the origin angle. Now fires only on fan invalidation, which is a more definitive failure signal

### FAN_VALIDATED
- **Value**: `"fan_validated"`
- **Semantic**: Fan validated via 7/8 interaction
- **Emission Mechanism**: `angular_coverage_study.py` — via validation_detect module when fan validation occurs
- **Fires When**: Fan validation occurs via 7/8 interaction

### ZONE_CHANGE
- **Value**: `"zone_change"`
- **Semantic**: Price moved to a new angle zone
- **Emission Mechanism**: `angular_coverage_study.py` — via `zone_tracker.has_zone_changed()`
- **Fires When**: Zone tracker detects zone change for a fan
- **Note**: Explicitly filtered out in CSV export to match frontend price interactions table

---

## Event Type Resolution

State machine events (from `UnifiedStateMachine.EventOutput`) are resolved to `EventType` enum in `angular_coverage_study.py`:

```python
try:
    evt_enum = EventType[state_event.event_type]  # By name
except KeyError:
    try:
        evt_enum = EventType(state_event.event_type)  # By value
    except ValueError:
        evt_enum = EventType.TOUCH  # Fallback
```

---

## CSV Export Compatibility

The CSV export (`event_logger.py`) uses `event.event_type.value` for the "Type" column. String values of event types must remain stable for frontend compatibility.

**ZONE_CHANGE is explicitly filtered out** from CSV export to match frontend price interactions table.

---

## Target Progression Sequence

Events fire in sequence as price advances through fan angle lines:
1. `TARGET_HIT` on 0.875 (7/8)
2. `TARGET_HIT` on 0.75 (3/4)
3. `TARGET_HIT` on 0.5 (1/2)
4. `TARGET_HIT` on horizontal target AND/OR 0.25 (1/4) — both are active concurrently, hit in any order. Hit ordering is recorded in `TargetHit.details`.
5. After both horizontal and 0.25 are hit → `TARGET_HIT` on full_coverage

If price reverses before reaching next target: `TARGET_FAILED`
