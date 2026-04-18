# Gann Angular Price Coverage: Implementation Specification

This document serves as the comprehensive blueprint for the upcoming enhancements to the Gann Angular Price Coverage Strategy, focusing on structural price action, consolidation filtering, and advanced zone-based analysis.

## 1. Cluster Detection & Consolidation Logic
**Objective:** Accurately identify when price action enters a sideways consolidation phase to contextualize micro-events (chop) and prevent false trading signals.
* **Intersection over Union (IoU) & Volatility Contraction:** The system will evaluate the overlap between consecutive candle ranges. A cluster initiates when there is heavy overlap (e.g., >70% IoU) or when Inside Bars indicate volatility contraction.
* **Cluster Bounding Box:** Upon cluster initiation, the system establishes a `Cluster High` and `Cluster Low` based on the initiating candles.
* **Dynamic Expansion:** If subsequent candles push slightly past the box boundaries but fail to close decisively outside them (e.g., wick expansions), the Bounding Box expands to encompass the new extremes.
* **Cluster Resolution:** The cluster state is terminated only when a candle definitively closes outside the expanded Bounding Box boundaries.

## 2. Event Logging Enhancements
**Objective:** Preserve all raw interaction data while providing the Strategy Analyzer with rich contextual flags for filtering and hypothesis testing.
* **`cluster_state` (Boolean):** Every price interaction (Cross, Test, Rest) will be logged normally, but appended with a `cluster_state: True/False` flag. This ensures macro-events are not suppressed, but analysts can easily filter out "chop" noise post-hoc.
* **`Current_Zone` (String):** Every logged event will include the specific spatial zone the price is currently occupying (e.g., `"Between 7/8 and 3/4"`).
* **`Zone_Extremes` (JSON/String):** Every logged event will include the structural extremes established while in the current zone (e.g., `"{High: 23250.50, Low: 23110.20}"`).

## 3. Angle Zone Structural Tracking
**Objective:** Transform abstract spatial zones between Gann angles (7/8, 3/4, 1/2, 1/4) into definitive structural support and resistance ranges.
* **Extreme Tracking:** The `AngleZoneTracker` will be upgraded to monitor the `zone_high` (maximum High) and `zone_low` (minimum Low) for the entire duration the price action remains within a specific inter-angle zone.
* **Continuous Updates:** For every bar that closes within the current zone, the tracker evaluates and updates the extremes.
* **State Reset:** The extremes are hard-reset the moment price transitions into and establishes a new zone.

## 4. Structural Breach Confirmation Logic
**Objective:** Eliminate false breakouts/breakdowns (fake-outs) by enforcing a strict structural rule: a true breach must defeat the structure of the previous zone, not just the angle line.
* **State Machine Upgrade:** The `UnifiedStateMachine` will overhaul its `BREACH_CONFIRMED` logic.
* **Downward Breach Confirmation:** When price crosses down through an angle (e.g., from the 7/8-3/4 zone into the 3/4-1/2 zone), the breach is **ONLY confirmed** if the breaching candle closes **below the `zone_low`** established in the previous zone.
* **Upward Breach Confirmation:** When price crosses up through an angle, the breach is **ONLY confirmed** if the breaching candle closes **above the `zone_high`** established in the previous lower zone.
* **Pending States:** If price crosses an angle but fails to break the required zone extreme, the state remains an unconfirmed cross. If it reverses back across the angle, it is classified as a `FAKE_OUT` or `REJECTION`.

## 5. Strategy Analyzer Enhancements
**Objective:** Leverage the new zone and cluster data to validate core Gann trading hypotheses.
* **Vacuum Effect Analysis:** Utilize zone entry/exit timestamps to calculate the velocity (number of bars) it takes price to traverse a "vacuum" zone (e.g., the typically fast movement between the 1/2 angle and the Horizontal line).
* **Time-Decay / Zone Chop:** Analyze how the duration (bar count) of a `cluster_state` or the time spent trapped inside a specific zone impacts the success probability and MFE (Max Favorable Excursion) of the eventual breakout.
* **Filtered Excursion Metrics:** Allow the analyzer to compare the MAE/MFE of signals generated inside a cluster vs. signals generated in clean trend zones.
