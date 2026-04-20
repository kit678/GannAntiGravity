# BREACH_CONFIRMED Event Type Redesign

**Date:** 2026-04-20
**Status:** Approved

---

## Overview

Redesign the `BREACH_CONFIRMED` event type to use a two-part confirmation rule involving the Breach Extreme Close (BEC) and Zone Extreme Close (ZEC) of the prior zone. Introduces `BREACH_CONFIRMED_NO_ALPHA` for intra-bar multi-cross scenarios and next-target-hit-before-confirmation scenarios.

---

## Definitions

### BEC — Breach Extreme Close
- The `close` price of the candle that creates the pending breach (the breaching candle)
- Captured at the moment `CROSS_UP` or `CROSS_DOWN` fires
- Stored as `bec_close` on the pending breach dict

### ZEC — Zone Extreme Close
- The most extreme close of the **prior zone** (the zone immediately preceding the BEC's zone)
- Retrieved from `_historical_zones[fan_id]` at the last bar where the zone was Z_PRIOR
- For **UP direction**: `zec_high = zone_highest_close` of Z_PRIOR
- For **DOWN direction**: `zec_low = zone_lowest_close` of Z_PRIOR

---

## Confirmation Rule

### Pending Breach Creation (on CROSS_UP / CROSS_DOWN)
1. Record `bec_close = c_close` of the breaching candle
2. Identify the prior zone Z_PRIOR (the zone immediately before the BEC's zone)
3. Retrieve from historical zones: `zec_high` and `zec_low` of Z_PRIOR
4. Store `bec_close`, `zec_high`, `zec_low`, `prior_zone_fraction` on the pending breach dict

### Breach Confirmation (subsequent bars)
**UP direction:**
- Fire `BREACH_CONFIRMED` when: `c_close > max(bec_close, zec_high)`

**DOWN direction:**
- Fire `BREACH_CONFIRMED` when: `c_close < min(bec_close, zec_low)`

---

## Pending Breach Lifecycle

| Condition | Outcome |
|-----------|---------|
| Price closes beyond max(bec_close, zec_high) — UP | `BREACH_CONFIRMED` fires |
| Price closes below min(bec_close, zec_low) — DOWN | `BREACH_CONFIRMED` fires |
| Fan becomes invalid | Pending breach **silently cancelled** (no event) |
| Next target hit before confirmation | `BREACH_CONFIRMED_NO_ALPHA` fires |
| Price pulls back across line but not beyond bec_close | Pending breach **stays alive** |

The reversal check against `line_price_at_breach` is **removed**. Price pulling back across the line does not cancel the pending breach.

---

## BREACH_CONFIRMED_NO_ALPHA

Two scenarios produce `BREACH_CONFIRMED_NO_ALPHA` instead of regular `BREACH_CONFIRMED`:

### 1. Intra-bar Multi-cross
When multiple intersection events fire on the same bar across different lines:
- All **intermediate lines** (lines crossed before the furthest line) that had `CROSS_UP` or `CROSS_DOWN` fire `BREACH_CONFIRMED_NO_ALPHA`
- The **furthest line** fires its normal event type (whatever it is — CROSS_UP, SUPPORT_TEST, etc.)
- These confirmations happen within the same bar — no alpha to trade

**Example:** In one bar, price crosses 0.75 (CROSS_UP) and 0.5 (CROSS_UP):
- 0.75 → `BREACH_CONFIRMED_NO_ALPHA` (intermediate)
- 0.5 → normal pending breach created

### 2. Next Target Hit Before Breach Confirmation
When `TARGET_HIT` fires on a line before the pending breach on the prior line has confirmed:
- Fire `BREACH_CONFIRMED_NO_ALPHA` for the pending breach immediately
- Remove the pending breach from tracking
- `TARGET_HIT` still fires normally

---

## Zone Tracker Changes

The `AngleZoneTracker` already tracks `zone_highest_close` and `zone_lowest_close` per zone in `_zone_extremes[fan_id]`, updated continuously as candles progress.

No new tracking fields are needed. ZEC retrieval:
1. Identify Z_PRIOR (the zone immediately before the BEC's zone)
2. Look up the last `ZoneSnapshot` for Z_PRIOR from `_historical_zones[fan_id]`
3. Read its `zone_highest_close` / `zone_lowest_close`

---

## Code Changes

### UnifiedStateMachine
- `_start_pending_breach()`: Add `zec_high`, `zec_low`, `bec_close`, `prior_zone_fraction` to pending breach dict
- `process_bar()` pending breach update loop: Replace `extreme_price` check with `max(bec_close, zec_high)` / `min(bec_close, zec_low)` rule
- Remove reversal check against `line_price_at_breach`
- Add `BREACH_CONFIRMED_NO_ALPHA` handling for next-target-hit path
- Intra-bar multi-cross: emit `BREACH_CONFIRMED_NO_ALPHA` for intermediate lines

### AngleZoneTracker
- No structural changes needed
- Ensure `get_zone_at_bar()` returns ZoneSnapshot with `zone_highest_close` / `zone_lowest_close` correctly populated

### AngularCoverageStudy
- Update `_handle_target_hit_intra_bar_breach()` to emit `BREACH_CONFIRMED_NO_ALPHA` instead of `BREACH_CONFIRMED`

### EventLogger
- Ensure `BREACH_CONFIRMED_NO_ALPHA` string value is handled in CSV export

---

## EventType Enum

No changes to `EventType` enum structure. `BREACH_CONFIRMED_NO_ALPHA` is a string value emitted via the existing enum member, with the details field distinguishing the subtype.

---

## CSV Export

`BREACH_CONFIRMED_NO_ALPHA` is included in CSV export (unlike `ZONE_CHANGE` which is filtered). Event type string values must remain stable for frontend compatibility.
