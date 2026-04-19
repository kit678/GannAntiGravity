# Candle Pattern Labels on Chart Design

**Date:** 2026-04-19
**Status:** Approved for implementation

## Goal

Display 2-letter abbreviated labels (PB, DOJI, SS, IH, M, ST) on the TradingView chart at every bar where a candle pattern is detected, positioned above/below the candle wick.

## Pattern Abbreviation Map

| Full Name | Abbreviation |
|-----------|-------------|
| PINBAR | PB |
| DOJI | DOJI |
| SHOOTING_STAR | SS |
| INVERTED_HAMMER | IH |
| MARUBOZU | M |
| SPINNING_TOP | ST |

## Backend Changes

### File: `gann-visualizer/backend/study_tool/angular_coverage_study.py`

The `process_bar()` method already calls `self.state_machine.process_bar()`, which calls `self.pattern_detector.detect(ohlc)`. The pattern result is used to write to the trace log but is NOT included in the return value.

**Change:** Include the detected candle pattern in the per-bar result dict so the frontend can access it.

The `process_bar()` method in `angular_coverage_study.py` returns a dict with keys like `ui_events`, `drawings`, `pivot_markers`. Add `candle_pattern` to this dict.

### Trace Log Format (no change)

The trace log format `[Pattern: PINBAR]` stays as-is for human readability. Only chart labels use initials.

## Frontend Changes

### File: `gann-visualizer/frontend/src/TVChartContainer.jsx`

Add a new `plotPatternLabel(chart, pattern, candle)` function (similar to `plotTradeShape`) that:
1. Takes the TradingView chart instance, pattern abbreviation string, and the candle object
2. Creates a `createShape` call with `text: pattern_abbrev`
3. Positions the label above the candle high (for bearish patterns: SHOOTING_STAR, PINBAR) or below the candle low (for bullish: INVERTED_HAMMER) using a small offset
4. Uses the same time-bucket stacking prevention logic as `plotTradeShape` to avoid overlapping labels

The function is called during progressive replay whenever the per-bar response contains a non-NO_PATTERN candle pattern.

### Pattern Direction for Positioning

- **Bearish (label above):** PINBAR, SHOOTING_STAR, MARUBOZU
- **Bullish (label below):** INVERTED_HAMMER
- **Neutral (label above):** DOJI, SPINNING_TOP

## Files to Modify

1. `gann-visualizer/backend/study_tool/angular_coverage_study.py` — add `candle_pattern` to per-bar response
2. `gann-visualizer/frontend/src/TVChartContainer.jsx` — add `plotPatternLabel()` and call it during progressive replay

## Implementation Steps

1. Update `angular_coverage_study.py` `process_bar()` to include `candle_pattern` in returned dict
2. Update `ChartDatafeed.js` `handleStudy()` callback to extract pattern from response and pass to chart
3. Add `plotPatternLabel()` function in `TVChartContainer.jsx`
4. Call `plotPatternLabel()` in `startProgressiveReplay` study callback when pattern is present
