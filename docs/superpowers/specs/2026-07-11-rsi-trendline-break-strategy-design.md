# RSI Trendline Break Strategy Design

**Date:** 2026-07-11
**Status:** Pending Review
**Owner:** kit678

## 1. Goal

Design a new non-angular strategy that reuses the current hypothesis, reporting, trade simulation, and Hypothesis Navigator infrastructure to test RSI trendline breaks.

The strategy baseline is:

- compute `RSI(14)` from `candles.csv`
- detect deterministic RSI pivots
- build pivot-to-pivot RSI trendlines
- trigger on RSI trendline breaks
- filter signals using price relative to `SMA(200)`
- enter on the same bar close as the RSI break
- score results from actual simulated trades, not MFE-only labels
- expose the full RSI geometry and trade payload in the Hypothesis Navigator

This design must also leave room for future line-building variants, especially a best-fit recent RSI structure mode.

## 2. Why This Is Needed

The current system is strong at evaluating Gann and event-driven strategies, but this RSI trendline concept is a different family of idea:

- its signal source is oscillator geometry rather than price-angle geometry
- its main implementation risk is whether the detected RSI lines match what a human would reasonably draw
- its win rate must still be measured in the same practical way as the current actual-trade hypotheses

The project already has useful infrastructure for this:

- candle-driven hypotheses can run from `candles.csv`
- the unified hypothesis runner can evaluate non-Gann strategies
- the exit optimizer already simulates actual futures-style trades with structural stops, fee-adjusted PnL, and TP as `R` multiples
- detailed per-event logs already support downstream visualization and trade-label reuse

The missing piece is a reusable RSI geometry layer plus a trade-scored hypothesis that emits navigator-friendly objects.

## 3. Recommendation

Implement this as a dedicated RSI hypothesis backed by a reusable RSI geometry engine.

Recommended architecture:

1. build RSI geometry from candles in a standalone module
2. plug a deterministic pivot-to-pivot line builder into that engine for v1
3. feed breakout candidates into a new actual-trade-scored hypothesis
4. enrich each signal with full verification data for the Hypothesis Navigator

This is preferred over an all-in-one hypothesis because the line-building logic will likely change as the strategy is refined. Separating geometry generation from trade evaluation makes it easier to verify whether the problem is:

- bad RSI structure detection
- bad breakout timing
- bad trade management

## 4. Non-Goals

The first implementation will not:

- replace or refactor the existing Gann event stream
- add live-trading hooks
- make RSI geometry a first-class event family throughout the entire backend
- implement the best-fit RSI structure builder in the same pass
- optimize every stop-loss and trend-filter variation up front

V1 is a backtestable, trade-scored, navigator-visible hypothesis with a clean extension point for later variants.

## 5. Architecture Overview

The strategy should be split into four pieces.

### 5.1 RSI Geometry Engine

Input:

- `candles_df`

Output:

- RSI series
- pivot list
- line candidates
- breakout candidates

Responsibility:

- compute oscillator geometry only
- no trade scoring
- no exit optimization

### 5.2 RSI Line Builder Interface

This should define the contract for turning RSI pivots into line objects.

V1 implementation:

- `DeterministicPivotLineBuilder`

Deferred future implementation:

- `BestFitRecentStructureLineBuilder`

This interface is required so the framework can compare multiple line-construction styles later without rewriting the rest of the hypothesis pipeline.

### 5.3 RSI Trendline Break Trade Hypothesis

This hypothesis should:

- consume breakout candidates from the geometry engine
- apply the `price vs SMA(200)` filter
- create entries on the same breakout bar close
- simulate actual trades using a fixed stop and `R`-multiple targets
- emit trade-enriched detailed logs for reporting and visualization

### 5.4 Hypothesis Navigator Payload Adapter

The strategy must expose enough signal context for manual validation in the existing frontend.

Each detailed-log entry should carry:

- RSI value at signal
- pivot anchor bars and RSI values
- trendline endpoints and slope
- breakout bar index and breakout direction
- `SMA(200)` filter state
- entry, stop, TP, exit, bars held, outcome, PnL

The key design principle is that the user should be able to answer both:

- "Did we draw the RSI structure correctly?"
- "Did the resulting trade behave correctly?"

without reading backend internals.

### 5.5 Navigator Verification Scope

V1 should treat the Hypothesis Navigator as the primary verification surface, but it should not require a full custom RSI pane inside the TradingView chart widget.

Recommended v1 scope:

- keep chart navigation focused on the existing candle chart and trade timing
- add RSI-specific verification data to the selected-event experience inside the Hypothesis Navigator itself
- provide a compact RSI verification panel or equivalent selected-event view that shows the local RSI shape, pivot anchors, active line, break point, and trade summary

This keeps frontend scope realistic while still making the RSI geometry visually inspectable where the user already reviews hypotheses.

## 6. Strategy Rules

### 6.1 Indicators

V1 defaults:

- `RSI period = 14`
- `SMA period = 200`

Both should be implemented as parameters so they can be varied later, but the baseline report should treat these defaults as the primary configuration.

### 6.2 Pivot Detection

RSI pivots should be deterministic and derived from fixed left/right bar rules.

Requirements:

- no hand-drawn ambiguity
- no regression fitting in v1
- pivot detection must produce reproducible anchor bars
- pivots should be stable enough to inspect in the Hypothesis Navigator

The exact left/right settings belong in implementation parameters, but the design contract is that pivot selection must be fixed and repeatable.

### 6.3 Trendline Construction

V1 should use pivot-to-pivot deterministic lines only.

Design constraints:

- line endpoints come from actual detected RSI pivots
- lines are extended forward until invalidated or broken
- line-building must be deterministic given the same pivot sequence
- the builder must prefer a single newest valid line for each active direction rather than emitting a noisy cloud of equivalent lines

This keeps the visual output understandable and reduces ambiguity in breakout timing.

### 6.4 Breakout Trigger

Entry trigger:

- signal occurs when RSI breaks the active trendline
- entry happens on the same price-bar close as the RSI break

This is the recommended baseline because it is easy to verify and consistent with the need for deterministic first-pass testing.

### 6.5 Trend Filter

Default filter:

- longs allowed only when price close is above `SMA(200)`
- shorts allowed only when price close is below `SMA(200)`

No slope filter is required in v1. Slope-based filtering remains a later variation.

## 7. Trade Scoring

### 7.1 Win Definition

Win rate must be based on actual simulated trades, not MFE/MAE classification.

The implementation should reuse the existing actual-trade pattern already present in [exit_optimizer.py](file:///c:/Dev/GannTesting/gann-visualizer/backend/analysis/exit_optimizer.py):

- entry price from the signal bar close
- stop loss from a deterministic structural rule
- TP derived as an `R` multiple of risk
- fee-adjusted `net_pnl`
- trade outcome defined from realized PnL

This aligns the strategy with the project rule that ranking and evaluation should follow actual trade outcomes.

### 7.2 Stop Loss

Default stop rule:

- long: low of the breakout candle
- short: high of the breakout candle

This is the v1 baseline because it is deterministic, local to the signal, and easy to visually audit.

### 7.3 Take Profit Grid

V1 should test this default `R` grid:

- `1.0R`
- `1.5R`
- `2.0R`
- `2.5R`
- `3.0R`

This mirrors the current exit-optimization style and is broad enough for initial exploration.

### 7.4 Trade Simulation Rules

The trade simulator should follow the same style as the existing actual-trade infrastructure:

- risk is defined by the stop-loss distance
- TP is `entry +/- risk * R`
- commission/fees must be included
- stop-loss and TP checks must be deterministic and documented
- a max-hold fallback should exist so trades always terminate

The detailed log must store the chosen trade result per signal and the optimizer summary must preserve the full tested `R` grid.

## 8. Data Flow

The end-to-end flow should be:

1. load `candles.csv`
2. compute `RSI(14)` and `SMA(200)`
3. detect deterministic RSI pivots
4. build pivot-to-pivot RSI trendlines
5. detect line breaks
6. apply the `price vs SMA(200)` filter
7. create a trade entry on breakout bar close
8. set stop from breakout candle extreme
9. simulate trades across the configured `R` grid
10. select and report results using realized trade outcomes
11. attach geometry and trade payloads to `detailed_log`
12. surface those fields in the Hypothesis Navigator

## 9. Components and Responsibilities

### 9.1 `rsi_geometry.py` or equivalent module

Should contain:

- RSI calculation helpers
- pivot detection helpers
- line-building interface
- deterministic line-builder implementation
- breakout detection helpers

This module should be pure data transformation from candles to geometry objects.

### 9.2 New hypothesis class

Should contain:

- strategy metadata
- orchestration between geometry engine and trade simulation
- trend filter application
- result assembly in the repo's standard hypothesis format

This class should not bury low-level geometry calculations inside a large monolith.

### 9.3 Existing trade simulation reuse

The implementation should reuse current exit-optimization patterns rather than inventing a new parallel trade model.

Expected reuse areas:

- `R`-multiple testing
- fee-adjusted PnL
- per-event entry/exit fields
- walk-forward-compatible result packaging

### 9.4 Navigator integration

The existing reporting layer should remain the primary output path.

The strategy must produce detailed-log payloads that are rich enough for frontend rendering without requiring an entirely separate export format.

## 10. Detailed Log Contract

Each signal entry should include, at minimum:

- `time`
- `bar_index`
- `signal_direction`
- `rsi_value`
- `sma_200`
- `trend_filter_passed`
- `pivot_a_bar_index`
- `pivot_a_rsi`
- `pivot_b_bar_index`
- `pivot_b_rsi`
- `line_start_bar`
- `line_end_bar`
- `line_slope`
- `line_value_at_break`
- `break_bar_index`
- `breakout_type`
- `rsi_window` or equivalent compact local RSI series around the signal
- `entry_price`
- `entry_side`
- `stop_price`
- tested `R` values or selected `best_r`
- `exit_price`
- `exit_reason`
- `net_pnl`
- `pnl_pct`
- `bars_held`
- `outcome`

If convenient for the frontend, the line may also be emitted as a compact object with endpoint coordinates rather than only flattened columns.

The contract must be rich enough for the frontend to render a selected-event RSI verification panel without needing to re-run indicator calculations in the browser.

## 11. Error Handling

The design must handle the following cases explicitly:

### 11.1 Indicator warmup

- skip bars before both RSI and `SMA(200)` are available
- do not fabricate partial signals during warmup

### 11.2 Missing geometry

- if there are not enough pivots to form a valid line, emit no signal
- if a line cannot be extended to the current bar, discard it cleanly

### 11.3 Ambiguous candidate lines

- deterministic selection must prefer the newest valid qualifying line
- the engine must not emit multiple equivalent active lines for the same direction unless explicitly configured later

### 11.4 Invalid risk

- if stop calculation yields zero or negative risk, skip the trade
- this should not fail the whole hypothesis run

### 11.5 Missing candle lookup

- if a signal cannot be mapped back to the needed candle row for simulation or visualization, skip that signal and record the issue

### 11.6 Partial navigator payload

- missing optional visual fields should not crash the hypothesis
- core trade fields are required, but non-essential display fields may degrade gracefully

## 12. Testing Strategy

The implementation should be tested at three levels.

### 12.1 Geometry unit tests

Cover:

- RSI calculation sanity
- pivot detection on controlled synthetic series
- deterministic line construction from known pivots
- breakout timing against known examples

### 12.2 Trade simulation integration tests

Cover:

- same-bar close entry
- breakout-candle stop-loss logic
- TP hit behavior
- SL hit behavior
- time-exit behavior
- fee-adjusted `net_pnl`
- win classification from realized PnL

### 12.3 Reporting and navigator contract tests

Cover:

- detailed-log payload contains the minimum visual verification fields
- hypothesis output remains compatible with the unified runner/report path
- the navigator can consume entries without missing required signal metadata

## 13. Walk-Forward and Ranking

The hypothesis should participate in the same broader evaluation discipline as the rest of the framework:

- report in-sample trade results
- preserve per-`R` optimization output
- remain compatible with walk-forward validation

The primary score for judging whether the strategy is promising should be actual trade performance:

- win rate
- expectancy
- profit factor
- sample size
- walk-forward persistence

MFE/MAE may still be stored as diagnostics if useful, but not as the main success definition.

## 14. Reuse of Existing Infrastructure

The implementation should reuse as much of the already implemented infrastructure as possible.

Specifically:

- use `candles.csv` as the main input source
- fit into the unified hypothesis/report pipeline
- reuse existing actual-trade simulation ideas from the exit optimizer
- preserve the standard result shape with `in_sample`, `walk_forward`, `groups`, and `detailed_log`
- keep the Hypothesis Navigator as the main manual verification surface

One explicit compatibility requirement is that the per-hypothesis backend enrichment path must preserve custom `detailed_log` fields for non-fan strategies. The current fan-oriented enrichment path cannot be allowed to discard RSI-specific verification fields such as local RSI series, pivot anchors, and line metadata.

The design should avoid introducing a parallel custom report format unless the frontend truly cannot consume the existing detailed-log pattern.

## 15. Variations To Test After Implementation

The first implementation should keep a dedicated follow-up list so experiments remain structured.

### 15.1 Indicator variations

- `RSI(8)`
- `RSI(14)`
- `RSI(21)`
- alternate `SMA` filter lengths

### 15.2 Geometry variations

- best-fit recent RSI structure builder
- different pivot left/right sensitivity
- stricter or looser line-validity rules
- alternate breakout tolerance around the RSI line
- one-signal-per-line vs multiple signals from the same line

### 15.3 Entry and filter variations

- same-bar close vs next-bar open
- price vs `SMA(200)` only
- price vs `SMA(200)` plus slope
- no trend filter
- long-only or short-only tests

### 15.4 Risk and exit variations

- breakout candle extreme stop
- nearest recent price swing stop
- stop linked to the price structure associated with the RSI anchors
- TP grid extension with `0.75R`, `1.25R`, `4.0R`
- different max-hold bar settings

### 15.5 Validation variations

- compare deterministic pivot-to-pivot builder vs future best-fit builder on the same runs
- test whether the visually most believable line logic also produces better actual trade persistence

## 16. Implementation Notes

The core engineering risk is not indicator math. It is geometry trustworthiness.

Therefore the implementation should prioritize:

1. deterministic, inspectable RSI objects
2. compatibility with actual-trade scoring
3. rich Hypothesis Navigator visibility
4. easy substitution of future line-building variants

If a trade-off appears between adding more strategy variants now versus making the RSI geometry inspectable and reliable, the design prefers inspectability first.

## 17. Spec Self-Review

- Placeholder scan: no unresolved `TODO`, `TBD`, or deferred decisions remain inside the v1 baseline
- Internal consistency: the architecture, scoring model, and navigator contract all assume actual-trade evaluation and deterministic pivot-based geometry
- Scope check: this is one implementation plan, not a multi-project decomposition
- Ambiguity check: v1 defaults are explicit for indicator settings, trend filter, entry timing, stop rule, and TP grid; future variations are isolated in Section 15
