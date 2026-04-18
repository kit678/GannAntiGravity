# Angular Price Coverage Strategy - Event Classification Implementation

## Overview

This document details the implementation of event classification and detection for the Angular Price Coverage Strategy, including what has been implemented, how it works, and what remains pending.

---

## Part 1: Implemented Features

### 1. Retroactive Sweep (Core Architectural Fix)

**Problem Identified:**
When a new fan is confirmed (e.g., at bar T), the system previously only evaluated the current candle and future candles against the fan's angle lines. All price action that occurred between the fan's anchor bar and the confirmation bar was ignored.

**Example:**
- Price rises from L3, crosses through the 3/4 angle line
- Price pulls back but doesn't break through
- The 5th bar after L3 confirms the L3 pivot
- A new fan (L3-H2 or L3-H3) is created
- The system sees the current bar as a standalone event, missing the context that price already touched the line previously

**Solution Implemented:**
Added a `retroactive_sweep()` method to `IntersectionDetector` that:
1. Triggered when a new fan is confirmed
2. Looks back from the anchor bar to the current bar
3. Evaluates all historical candles against the new angle lines
4. Logs all historical intersections with proper event types

**Implementation Location:**
- `backend/study_tool/intersection_detector.py` - `retroactive_sweep()` method
- `backend/study_tool/angular_coverage_study.py` - Call to retroactive sweep in fan creation flow

**Expected Behavior:**
When a fan is created, historical price interactions with the fan's lines are retroactively detected and logged, providing complete context.

---

### 2. Preceding Context for Cross Events

**Problem Identified:**
The system used a rigid binary logic for classifying events:
- `CROSS_DOWN`: `open > line AND close < line`
- `CROSS_UP`: `open < line AND close > line`

This ignored market mechanics. A candle opening barely above a line and closing way below is a rejection, not a structural breakdown.

**Solution Implemented:**
Updated the logic to correctly classify cross events based on open and close prices relative to the line:

**For CROSS_UP:**
- Price opens below/on and closes above the line
- `open <= line AND close > line`

**For CROSS_DOWN:**
- Price opens above/on and closes below the line
- `open >= line AND close < line`

**For SUPPORT_TEST:**
- Price was above, dips below/touches, but closes above
- `prev_close > line AND low <= line AND close > line`

**For RESISTANCE_TEST:**
- Price was below, spikes above/touches, but closes below
- `prev_close < line AND high >= line AND close < line`

**Implementation Location:**
- `backend/study_tool/angular_coverage_study.py` - `_process_intersection_event()` method

**Implementation Details:**
```python
# CROSS_UP: Price opens below/on and closes above the line
if c_open <= event.price and c_close > event.price:
    hit_type = 'CROSS_UP'
    details = 'Breakout Attempt'
# CROSS_DOWN: Price opens above/on and closes below the line
elif c_open >= event.price and c_close < event.price:
    hit_type = 'CROSS_DOWN'
    details = 'Breakdown Attempt'
# SUPPORT_TEST: Price was above, dips below/touches, but closes above
elif prev_close > event.price and c_low <= event.price and c_close > event.price:
    hit_type = 'SUPPORT_TEST'
    details = 'Testing Support'
# RESISTANCE_TEST: Price was below, spikes above/touches, but closes below
elif prev_close < event.price and c_high >= event.price and c_close < event.price:
    hit_type = 'RESISTANCE_TEST'
    details = 'Testing Resistance'
```

**Expected Results:**
- CROSS_UP count dropped significantly (only genuine breakouts)
- CROSS_DOWN count dropped significantly (only genuine breakdowns)
- More accurate classification of rejection vs cross events

---

### 3. Terminology Cleanup

**Changes Made:**

| Old Term | New Term | Reason |
|----------|----------|--------|
| `FAN_INVALIDATED` | `FAN_DEACTIVATED` | "Invalidated" implies rule violation; fans deactivate per lifecycle rules |
| "Resting / Throwback" | "Testing Support" | Initial test should not prematurely claim a throwback |
| "Rejection / Pullback" | "Testing Resistance" | Initial test should not prematurely claim a rejection |

**New Event Types Added to EventType Enum:**
```python
SUPPORT_BOUNCE = "SUPPORT_BOUNCE"       # Price successfully bounced from support
RESISTANCE_REJECTION = "RESISTANCE_REJECTION"  # Price successfully rejected from resistance
FAN_DEACTIVATED = "FAN_DEACTIVATED"     # Fan completed/deactivated (not invalidated)
```

**Implementation Location:**
- `backend/study_tool/event_logger.py` - EventType enum
- `backend/study_tool/angular_coverage_study.py` - UI event labels

---

### 4. Unique Fan Labels (H/L Increment)

**Problem Identified:**
When a fan was invalidated and a new fan was created, the system reused the same labels (e.g., H1-L1 became H1-L1 again), making it impossible to distinguish between different physical fans.

**Solution Implemented:**
- H and L counters never reset
- When a fan is invalidated, the pivot is "released" for reuse but retains its unique label
- New fans get incremented labels (H1→H2, L1→L2)

**Implementation Location:**
- `backend/study_tool/pivot_detector.py`:
  - `reset()` method - counters preserved, never reset to 0
  - `release_pivot()` method - releases pivot for new fan formation
  - `_sync_from_registry()` - preserves higher counts from registry
- `backend/study_tool/angular_coverage_study.py` - Calls `release_pivot()` when fan is removed

**Expected Behavior:**
- Fan labels increment throughout the entire simulation
- Example: H1-L1, H2-L1, H2-L2, H3-L2, H3-L3
- Each physical fan has a unique identifier for accurate analysis

---

## Part 2: Event Classification Logic

### Current Event Types

| Type | Definition | Details |
|------|------------|---------|
| `TOUCH` | Price touches the angle line | Default when no other conditions match |
| `CROSS_UP` | Price opens below/on and closes above the line | Breakout Attempt |
| `CROSS_DOWN` | Price opens above/on and closes below the line | Breakdown Attempt |
| `SUPPORT_TEST` | Price tests support from above | Prev close > line, low touches, close > line |
| `RESISTANCE_TEST` | Price tests resistance from below | Prev close < line, high touches, close < line |
| `FAKE_OUT` | Cross followed by immediate reversal | Tracked by breach_analyzer |
| `BREACH_CONFIRMED` | N successive closes past the line | Tracked by breach_analyzer |
| `REST_ON_ANGLE` | Price rests on line for multiple bars | Enhanced detection with wick probes and polarity |
| `SUPPORT_BOUNCE` | Price successfully bounced from support | Tracked by bounce_rejection_tracker |
| `RESISTANCE_REJECTION` | Price successfully rejected from resistance | Tracked by bounce_rejection_tracker |
| `FAN_DEACTIVATED` | Fan completes or is removed | Fan lifecycle event |

### Event Classification Flow

```
For each candle at bar T:
    1. Detect intersections with all active fan angle lines
    
    2. For each intersection:
       a. Get previous candle data
       b. Apply classification logic:
          - If open <= line AND close > line:
            - CROSS_UP
          - If open >= line AND close < line:
            - CROSS_DOWN
          - If prev_close > line AND low <= line AND close > line:
            - SUPPORT_TEST
          - If prev_close < line AND high >= line AND close < line:
            - RESISTANCE_TEST
          - Else: TOUCH
    
    3. Send events through tracking modules (breach_analyzer, fan_validator)
    
    4. For new fans:
       a. Trigger retroactive sweep
       b. Process historical intersections with proper context
```

---

## Part 3: Fan Geometry and Line Polarity

### Fan Types

| Fan Type | Anchor | Line Direction | Initial Function |
|----------|--------|----------------|------------------|
| **Low-Anchored** | Low pivot (L) | Lines angled DOWN | Resistance lines |
| **High-Anchored** | High pivot (H) | Lines angled UP | Support lines |

### Angle Role Reversal

Once an angle line is breached and confirmed:
- **Resistance becomes Support** (Low-anchored lines)
- **Support becomes Resistance** (High-anchored lines)

Price often returns to test the breached angle before continuing in the direction of the breach.

---

## Part 4: Expected Simulation Results

### Event Type Distribution (Sample Run)

| Event Type | Count | Notes |
|------------|-------|-------|
| `SUPPORT_TEST` | ~2500 | Tests of support lines |
| `RESISTANCE_TEST` | ~2500 | Tests of resistance lines |
| `CROSS_DOWN` | ~650 | Only genuine breakdowns |
| `CROSS_UP` | ~600 | Only genuine breakouts |
| `TOUCH` | ~100 | Minor touches |
| `zone_change` | ~400 | Zone transitions |

### CSV Output Format

```
#,Time,Fan,Fraction,Price,Type,Details,MFE_10,MAE_10,bars_elapsed
1,"3/11/2026, 10:47:00 AM",P1 (L1-H1),main,24049.40,SUPPORT_TEST,Testing Support,64.70,39.25,0
```

---

## Part 5: Pending Implementations

### 1. Enhanced REST_ON_ANGLE Logic ✅ IMPLEMENTED

**Definition:**
Resting = Price hovering near/at the angle line for multiple bars without decisively breaking through it.

**Includes:**
- Small-bodied candles consolidating near the line
- Repeated wick probes toward the line with closes staying on one side
- Price "grinding" toward the line but not breaking it

**Key Distinction:**
| Scenario | Classification |
|----------|----------------|
| Resting | Neutral, watching |
| Resting ends with bounce | `SUPPORT_BOUNCE` / `RESISTANCE_REJECTION` |
| Resting ends with breach | `BREACH_CONFIRMED` |

**Implementation Details:**
1. Broadened definition to include wick probes (not just small bodies)
2. Tracks line polarity (angled_up, angled_down, neutral)
3. Emits ONE `REST_ON_ANGLE` event when resting period begins (not spam per bar)
4. Categorizes resting behavior by line polarity and rest type (body_consolidation, wick_consolidation)

**Implementation Location:**
- `backend/study_tool/bounce_rejection_tracker.py` - `BounceRejectionTracker` class

### 2. Support/Resistance Confirmation Events ✅ IMPLEMENTED

**Implemented Events:**
- `SUPPORT_BOUNCE` - Price successfully bounces from support after test
- `RESISTANCE_REJECTION` - Price successfully rejects from resistance after test

**Implementation Approach:**
- Tracks candles AFTER a test
- If price moves favorably away from line by threshold (0.3% default): emit confirmation event
- Looks back up to 5 bars for confirmation

**Implementation Location:**
- `backend/study_tool/bounce_rejection_tracker.py` - `BounceRejectionTracker` class

### 3. Fan Health Tracking

**Status:** Not implemented (considered but deferred)

**Purpose:** Track per-angle-line health metrics:
- Total tests count
- Bounce rate (successful reversals / total tests)
- Average bounce distance
- Confluence score (multiple lines at same price)

**Current Assessment:** May be unnecessary complexity. The Confluence detection in the existing analyzer may be sufficient for hypothesis testing.

---

## Part 6: File Modifications Summary

### Files Modified

| File | Changes |
|------|---------|
| `backend/study_tool/intersection_detector.py` | Added `retroactive_sweep()` method |
| `backend/study_tool/angular_coverage_study.py` | Retroactive sweep call, context checking, terminology updates, unique fan labels, bounce/rejection tracking |
| `backend/study_tool/event_logger.py` | New event types in enum |
| `backend/study_tool/pivot_detector.py` | Counter preservation, `release_pivot()` method |
| `backend/study_tool/bounce_rejection_tracker.py` | **NEW** - SUPPORT_BOUNCE, RESISTANCE_REJECTION, enhanced REST_ON_ANGLE |
| `backend/run_simulation.py` | Minor fixes for CSV export |

### Key Methods Added/Modified

| Method | File | Purpose |
|--------|------|---------|
| `retroactive_sweep()` | intersection_detector.py | Look back and detect historical intersections |
| `_process_intersection_event()` | angular_coverage_study.py | Classify events with directional context |
| `release_pivot()` | pivot_detector.py | Release pivot for new fan formation |
| `reset()` | pivot_detector.py | Preserve H/L counters, never reset to 0 |
| `BounceRejectionTracker.process_bar()` | bounce_rejection_tracker.py | Track bounces, rejections, and rest events |
| `_process_rest_event()` | bounce_rejection_tracker.py | Enhanced REST_ON_ANGLE with wick probes and polarity |
| `_track_pending_test()` | bounce_rejection_tracker.py | Track tests for bounce/rejection confirmation |

---

## Part 7: Testing and Verification

### How to Verify Implementation

1. **Run Simulation:**
   ```bash
   python backend/run_simulation.py --symbol "^NSEI" --resolution 4 --source yfinance
   ```

2. **Check CSV Output:**
   - Verify "Testing Support" not "Resting / Throwback"
   - Verify "Testing Resistance" not "Rejection / Pullback"
   - Verify fan labels increment (H1, H2, H3... L1, L2, L3...)
   - Verify CROSS_UP/DOWN counts are significantly lower than before

3. **Check Logs:**
   - Look for `[RetroSweep]` log entries when new fans are created
   - Verify "Testing Resistance" appears for rejection events without falling context

### Expected Log Output for Retroactive Sweep

```
[RetroSweep] New fan Fan_L3_H2 created. Anchor at bar 45, current bar 52
  [RetroSweep] HIT: P2 frac=0.75 @ 23972.00 | Bar 48 (2026-03-11 13:31)
  [RetroSweep] HIT: P2 frac=0.75 @ 23976.90 | Bar 52 (2026-03-11 13:43)
  [RetroSweep] Total historical hits for Fan_L3_H2: 2
```

---

*Document Version: 1.1*
*Last Updated: March 22, 2026*

## Changelog

### v1.1 (March 22, 2026)
- **FIXED:** Bug in `angular_coverage_study.py` line 880 - undefined variable `current_idx` changed to `current_bar_index`
- **FIXED:** Bug in `angular_coverage_study.py` line 794 - wrong method call `self.event_logger.log()` changed to `self.event_logger.log_event()`
- **IMPLEMENTED:** Enhanced REST_ON_ANGLE logic with wick probes and line polarity tracking
- **IMPLEMENTED:** SUPPORT_BOUNCE and RESISTANCE_REJECTION confirmation events
- **NEW MODULE:** `bounce_rejection_tracker.py` for bounce/rejection detection

### v1.0 (March 2026)
- Initial implementation of retroactive sweep, preceding context, terminology cleanup, and unique fan labels
