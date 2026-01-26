# Replay Functionality Analysis & Improvement Recommendations

**Date**: 2026-01-09  
**Purpose**: Comprehensive analysis of replay functionality and its interaction with strategies

---

## Executive Summary

After a thorough examination of the codebase, I've identified the current architecture, how replay functionality works, and areas for improvement. The replay functionality is **working separately from the backtest functionality** and correctly handles the "Replay From" date picker. However, there are some structural improvements that can make the codebase more maintainable and aligned with TradingView's best practices.

---

## Current Architecture Overview

### 1. Two Distinct Modes of Operation

#### A. **Instant Backtest Mode** (`Run Backtest` button)
- Calls `/run_backtest` endpoint
- Fetches all candles, runs strategy on backend, returns trades
- Frontend displays all candles and trade markers at once
- Uses `startBacktestInstant()` in `TVChartContainer.jsx`
- Controlled by the main `From:` and `To:` date pickers

#### B. **Progressive Replay Mode** (`Start Replay` button)
- Calls `/fetch_candles` endpoint (no strategy evaluation)
- Loads candles into custom datafeed
- Uses `startProgressiveReplay()` which progressively evaluates strategy
- Strategy is evaluated per-bar via `/evaluate_strategy_step` endpoint
- Uses the **"Replay From:"** date picker to determine starting point
- The Study Tool (`angular_coverage`) uses `/study_process_bar` instead

### 2. Replay Date Picker Mechanics

The **"Replay From:"** date picker (`replayStartDateRef`) works as follows:

```javascript
// From App.jsx lines 127-133
const replayStartDate = replayStartDateRef.current?.value;
let replayStartTimestamp = null;

if (replayStartDate) {
    replayStartTimestamp = new Date(replayStartDate + ' 00:00:00').getTime() / 1000;
    console.log('[Replay] Will start from:', replayStartDate, 'timestamp:', replayStartTimestamp);
}
```

This timestamp is passed to `startProgressiveReplay()` which:
1. Finds the candle index matching or just after this timestamp
2. Sets `replayStartIndex` to that position (or 1 before for context)
3. The `ChartDatafeed.js` starts playback from that index

**Current Behavior**: ✅ **Correct** - Replay starts from the specified date

---

## How Strategies Interact with Replay

### 1. Strategy Selection in Dropdown

The dropdown in `App.jsx` offers these strategies:
- `mechanical_3day` - Mechanical 3-Day Swing
- `ichimoku_cloud` - Ichimoku Cloud Breakout (placeholder)
- `gann_square_9` - Gann Square of 9
- `angular_coverage` - Angular Price Coverage Study

### 2. Strategy Evaluation During Replay

During progressive replay, at each step:

```javascript
// From ChartDatafeed.js lines 444-500
if (this.strategyName === 'angular_coverage') {
    // STUDY TOOL SPECIFIC LOGIC
    fetch(`${this.datafeedUrl}/study_process_bar`, {...})
        .then(data => {
            if (data.status === 'success' && data.drawings) {
                this.tradeCallback({
                    type: 'drawing_update',
                    drawings: data.drawings,
                    state: data.state
                });
            }
        });
} else {
    // STANDARD STRATEGY LOGIC
    fetch(`${this.datafeedUrl}/evaluate_strategy_step`, {...})
        .then(data => {
            if (data.signal) {
                this.tradeCallback(data.signal);
            }
        });
}
```

**Finding #1**: The `angular_coverage` strategy has **special handling** in `ChartDatafeed.js` that differs from other strategies. This creates a coupling issue.

---

## Issues Identified

### Issue #1: Strategy-Specific Logic in Datafeed Layer

**Problem**: The `ChartDatafeed.js` contains conditional logic specifically for `angular_coverage`:
- Different endpoint (`/study_process_bar` vs `/evaluate_strategy_step`)
- Different response handling (drawings vs signals)
- This violates separation of concerns

**Impact**: Adding new study tools or strategies requires modifying the datafeed layer.

### Issue #2: Inconsistent Response Structure

**Standard strategies** return:
```json
{"signal": {"time": 123, "type": "buy", "price": 24000}}
```

**Study tool** returns:
```json
{
  "status": "success",
  "drawings": {...},
  "state": {...}
}
```

This inconsistency requires special handling in multiple places.

### Issue #3: Missing Strategy Registry for Study Tools

The `STRATEGY_REGISTRY` in `strategies.py` doesn't include `angular_coverage`:
```python
STRATEGY_REGISTRY = {
    'mechanical_3day': Mechanical3DaySwingStrategy,
    'gann_square_9': SquareOf9ReversionStrategy,
    'time_cycle_breakout': TimeCycleBreakoutStrategy,
    'ichimoku_cloud': TimeCycleBreakoutStrategy,  # Placeholder
}
# Note: 'angular_coverage' is MISSING
```

This means selecting `angular_coverage` in the dropdown for "Run Backtest" would cause an error.

### Issue #4: TradingView Bar Replay Tool is Unsupported

**Critical**: Per TradingView documentation (lines 596-607):
> Neither Advanced Charts nor Trading Platform provides... **Bar Replay Tool**

The current implementation works around this by:
1. Using `resetData()` and `resetCache()` on each step
2. Managing a custom data buffer
3. Manually pushing bars to subscribers

This workaround is functional but:
- Causes full chart re-renders on each step
- May have performance issues on large datasets
- Is not the "intended" use of the library

---

## Recommended Improvements

### Improvement #1: Unified Strategy/Study Response Interface

Create a unified response format for both strategies and study tools:

```typescript
interface StrategyStepResponse {
    type: 'signal' | 'drawing_update' | 'none';
    signal?: TradeSignal;
    drawings?: DrawingData;
    state?: any;
}
```

**Backend Changes**:
- Create a unified `/evaluate_step` endpoint
- Route internally to strategy or study tool based on strategy name
- Return consistent response structure

### Improvement #2: Strategy Registry Unification

Add study tools to the strategy registry or create a parallel registry:

```python
# Option A: Combine registries
STRATEGY_REGISTRY = {
    'mechanical_3day': Mechanical3DaySwingStrategy,
    'gann_square_9': SquareOf9ReversionStrategy,
    # ...
}

STUDY_REGISTRY = {
    'angular_coverage': AngularCoverageStudy,
}

def get_strategy_or_study(name, df, params=None):
    if name in STRATEGY_REGISTRY:
        return ('strategy', STRATEGY_REGISTRY[name](df, params))
    elif name in STUDY_REGISTRY:
        return ('study', STUDY_REGISTRY[name](df, params))
    raise ValueError(f"Unknown: {name}")
```

### Improvement #3: Remove Strategy-Specific Logic from Datafeed

Move strategy/study discrimination to the backend:

```python
@app.post("/evaluate_step")
async def evaluate_step(req: EvaluateStepRequest):
    """Unified evaluation endpoint"""
    if req.strategy in STRATEGY_REGISTRY:
        # Strategy evaluation
        return evaluate_strategy(req)
    elif req.strategy in STUDY_REGISTRY:
        # Study evaluation
        return evaluate_study(req)
```

Then the frontend can have a single code path:
```javascript
fetch(`${this.datafeedUrl}/evaluate_step`, {
    body: JSON.stringify({
        strategy: this.strategyName,
        candles: candlesUpToNow,
        current_index: this.currentStep
    })
})
```

### Improvement #4: Add `angular_coverage` to Dropdown Guard

Currently, clicking "Run Backtest" with `angular_coverage` selected would fail. Add guard:

```jsx
const handleRunBacktest = async () => {
    if (strategy === 'angular_coverage') {
        alert("Please use 'Run Study' button for Angular Price Coverage Study");
        return;
    }
    // ... rest of backtest logic
}
```

Or better: disable the "Run Backtest" button when `angular_coverage` is selected.

### Improvement #5: Document the Replay Workaround

Since Bar Replay is unsupported in TradingView Advanced Charts, document why and how the current workaround works:

```markdown
## Bar Replay Implementation Note

TradingView's Advanced Charts library officially does NOT support Bar Replay
(see Key-Features documentation). Our implementation works around this by:

1. Loading all candles into a custom datafeed buffer
2. Controlling the `currentStep` index to limit visible bars
3. Using `resetData()` and `resetCache()` to force re-renders
4. Notifying subscribers of new bars as they "appear"

This approach has trade-offs:
- ✅ Provides replay functionality on client-side
- ⚠️ Full chart re-render on each step
- ⚠️ Not tested with very large datasets (10k+ bars)
```

---

## Implementation Priority

| Priority | Change | Effort | Impact |
|----------|--------|--------|--------|
| 🔴 High | Add dropdown guard for `angular_coverage` + backtest | Low | User experience |
| 🔴 High | Document Bar Replay workaround | Low | Maintainability |
| 🟡 Medium | Unified `/evaluate_step` endpoint | Medium | Code quality |
| 🟡 Medium | Strategy/Study registry separation | Medium | Extensibility |
| 🟢 Low | Remove strategy-specific logic from datafeed | High | Architecture |

---

## TradingView Best Practices Integration

From the TradingView documentation, these best practices should be followed:

### Data Connection (docs lines 80-87)
> "Pay attention to the differences between implementing a datafeed in JavaScript via the Datafeed API and using the predefined implementation with a server that responds in the UDF format."

**Current Status**: ✅ Using UDF format for normal chart, custom wrapper for replay

### Provide Correct Amount of Data (docs lines 85-87)
> "Most issues with the library appear because data is provided incorrectly."

**Current Status**: ✅ Data is correctly filtered by requested range

### Enable Debug Logs (docs lines 97-99)
> "Set the `debug` property to `true` in Widget Constructor to enable logs."

**Recommendation**: Add debug mode toggle for development

### Avoid Undocumented Features (docs lines 111-113)
> "All features that are not mentioned in the documentation are subject to change."

**Current Status**: ⚠️ The replay workaround uses internal API patterns that could change

---

## Conclusion

The replay functionality is **working correctly** with respect to the "Replay From" date picker. The main improvements needed are:

1. **Structural**: Unify the strategy/study evaluation pattern
2. **UX**: Add guards and clearer separation between backtest and study modes
3. **Documentation**: Document the Bar Replay workaround limitations
4. **Maintainability**: Remove strategy-specific logic from frontend datafeed layer

The code is functional and the architecture is reasonable given TradingView's limitations. The recommended changes are improvements, not fixes for broken functionality.
