# Universal Strategy Interactions & Hypothesis Navigator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Price Interactions tab and Hypothesis Navigator work for every strategy via unified response schema, polymorphic column schemas, and BaseStrategy-level event extraction.

**Architecture:** Add `extract_events()` and `get_interaction_column_schema()` to `BaseStrategy` with default no-ops. Unify `_process_strategy_bar` to emit `intersection_events` and `strategy_meta`. Unify frontend `ChartDatafeed.js` into single `step_update` handler. Render Price Interactions table dynamically from column schema.

**Tech Stack:** Python/FastAPI backend (main.py, base_strategy.py, ema_crossover_strategy.py), React frontend (App.jsx, TVChartContainer.jsx, ChartDatafeed.js)

---

## Task 1: Add default methods to BaseStrategy

**Files:**
- Modify: `gann-visualizer/backend/base_strategy.py` (end of file)

- [ ] **Step 1: Add `get_indicator_series`, `extract_events`, `get_strategy_meta`, `get_interaction_column_schema` to BaseStrategy**

Make `get_indicator_series` no longer abstract — give it a default returning `{}`. Add three new methods with default no-op implementations.

Replace the end of `base_strategy.py` (from line 61 onwards, keeping `__init__` and `generate_signals` signature but making `get_indicator_series` non-abstract):

```
    @abstractmethod
    def generate_signals(self) -> pd.DataFrame:
        """
        Generate buy/sell signals based on strategy logic.
        
        Returns:
            DataFrame with added columns:
                - signal: 1 (buy), -1 (sell), 0 (hold)
                - signal_price: price at which signal was generated
                - signal_label: human-readable description of the signal
        """
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """Return the name of this strategy"""
        pass
    
    def get_strategy_description(self) -> str:
        """Return a description of the strategy (optional override)"""
        return f"{self.get_strategy_name()} - No description provided"
    
    def get_indicator_series(self) -> Dict[str, list]:
        """
        Return indicator time-value pairs for chart rendering.
        Override in strategies that have indicators (EMA lines, etc.).
        
        Returns:
            Dict mapping indicator name to list of {"time": int, "value": float} dicts
        """
        return {}
    
    def extract_events(self, df: pd.DataFrame, bar_index: int) -> list:
        """
        Extract strategy-specific interaction events at the given bar index.
        
        Called during step-by-step replay for the Price Interactions tab.
        Default returns empty list. Override per strategy.

        Args:
            df: DataFrame with signal columns (after generate_signals)
            bar_index: Index of the current bar being evaluated

        Returns:
            List of event dicts with keys: time, price, type, details,
            open, high, low, close, strategy_data
        """
        return []

    def get_strategy_meta(self) -> dict:
        """
        Return strategy metadata used by frontend for column rendering.

        Returns:
            dict with: name, display_name, is_study, column_schema, filter_field, filter_options
        """
        return {
            "name": self.__class__.__name__,
            "display_name": self.get_strategy_name(),
            "is_study": False,
            "column_schema": self.get_interaction_column_schema(),
            "filter_field": None,
            "filter_options": [],
        }

    def get_interaction_column_schema(self) -> list:
        """
        Return column definitions for Price Interactions table.
        Override per strategy. Default returns universal columns only.

        Each column dict: {"key": str, "label": str, "width": str, "format": str}
        Dot-notation keys (e.g. "strategy_data.fan") traverse nested dicts.
        """
        return [
            {"key": "time",    "label": "Time",    "width": "140px", "format": "datetime"},
            {"key": "type",    "label": "Event",   "width": "110px", "format": "text"},
            {"key": "price",   "label": "Price",   "width": "80px",  "format": "price"},
            {"key": "details", "label": "Details", "width": "200px", "format": "text"},
            {"key": "open",    "label": "Open",    "width": "70px",  "format": "price"},
            {"key": "high",    "label": "High",    "width": "70px",  "format": "price"},
            {"key": "low",     "label": "Low",     "width": "70px",  "format": "price"},
            {"key": "close",   "label": "Close",   "width": "70px",  "format": "price"},
        ]
    
    def validate_data(self) -> bool:
```

Note: This means `generate_signals()` and `get_strategy_name()` remain abstract. `get_indicator_series()` is now a concrete method (was previously not abstract but also not defined — existing strategy classes like `EMACrossoverStrategy` already override it). The five strategy classes that currently exist all already override `get_strategy_name()` and `generate_signals()` — no changes needed there.

- [ ] **Step 2: Verify no existing strategy breaks**

```bash
cd gann-visualizer/backend && python -c "from strategies import STRATEGY_REGISTRY; import pandas as pd; df = pd.DataFrame({'timestamp':[1,2,3], 'open':[100,101,102], 'high':[103,104,105], 'low':[99,98,97], 'close':[102,103,104]}); [print(f'{k}: {v(df).get_strategy_meta()[\"display_name\"]}') for k,v in STRATEGY_REGISTRY.items()]"
```

Expected: All strategies print their display names with no errors.

- [ ] **Step 3: Commit**

```bash
cd gann-visualizer/backend && git add base_strategy.py && git commit -m "feat: add extract_events, get_strategy_meta, get_interaction_column_schema to BaseStrategy"
```

---

## Task 2: Implement EMACrossoverStrategy interactions

**Files:**
- Modify: `gann-visualizer/backend/ema_crossover_strategy.py`

- [ ] **Step 1: Add `extract_events` method to EMACrossoverStrategy**

Add after `get_strategy_description()` (before `get_indicator_series`). The method checks if a crossover occurred at the given bar_index and returns the appropriate event dict.

```python
    def get_strategy_description(self) -> str:
        return "Two-line EMA crossover on 9 and 21 periods"

    def extract_events(self, df: pd.DataFrame, bar_index: int) -> list:
        events = []
        if bar_index < self.slow_period + 1 or bar_index >= len(df):
            return events
        
        required = ['open', 'high', 'low', 'close', 'timestamp', 'ema_9', 'ema_21']
        if not all(c in df.columns for c in required):
            return events
        
        prev_9 = df['ema_9'].iloc[bar_index - 1]
        prev_21 = df['ema_21'].iloc[bar_index - 1]
        curr_9 = df['ema_9'].iloc[bar_index]
        curr_21 = df['ema_21'].iloc[bar_index]
        
        if pd.isna(prev_9) or pd.isna(prev_21) or pd.isna(curr_9) or pd.isna(curr_21):
            return events
        
        prev_9_above = prev_9 > prev_21
        curr_9_above = curr_9 > curr_21
        
        import math
        
        if not prev_9_above and curr_9_above:
            events.append({
                "time": int(df['timestamp'].iloc[bar_index]),
                "price": float(df['close'].iloc[bar_index]),
                "type": "EMA_CROSSOVER_UP",
                "details": f"9 EMA ({curr_9:.2f}) crossed above 21 EMA ({curr_21:.2f})",
                "open": safe_float(df['open'].iloc[bar_index]),
                "high": safe_float(df['high'].iloc[bar_index]),
                "low": safe_float(df['low'].iloc[bar_index]),
                "close": safe_float(df['close'].iloc[bar_index]),
                "strategy_data": {
                    "crossover_direction": "BUY",
                    "fast_ema_value": round(float(curr_9), 2),
                    "slow_ema_value": round(float(curr_21), 2),
                }
            })
        elif prev_9_above and not curr_9_above:
            events.append({
                "time": int(df['timestamp'].iloc[bar_index]),
                "price": float(df['close'].iloc[bar_index]),
                "type": "EMA_CROSSOVER_DOWN",
                "details": f"9 EMA ({curr_9:.2f}) crossed below 21 EMA ({curr_21:.2f})",
                "open": safe_float(df['open'].iloc[bar_index]),
                "high": safe_float(df['high'].iloc[bar_index]),
                "low": safe_float(df['low'].iloc[bar_index]),
                "close": safe_float(df['close'].iloc[bar_index]),
                "strategy_data": {
                    "crossover_direction": "SELL",
                    "fast_ema_value": round(float(curr_9), 2),
                    "slow_ema_value": round(float(curr_21), 2),
                }
            })
        
        return events
```

Add a module-level helper at the top (after imports):

```python
import math

def safe_float(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return 0.0
    return float(val)
```

- [ ] **Step 2: Add `get_interaction_column_schema` override**

```python
    def get_interaction_column_schema(self) -> list:
        return [
            {"key": "time",                              "label": "Time",         "width": "140px", "format": "datetime"},
            {"key": "strategy_data.crossover_direction", "label": "Direction",    "width": "80px",  "format": "text"},
            {"key": "strategy_data.fast_ema_value",      "label": "Fast EMA",     "width": "80px",  "format": "price"},
            {"key": "strategy_data.slow_ema_value",      "label": "Slow EMA",     "width": "80px",  "format": "price"},
            {"key": "type",                              "label": "Event",        "width": "110px", "format": "text"},
            {"key": "price",                             "label": "Price",        "width": "80px",  "format": "price"},
            {"key": "details",                           "label": "Details",      "width": "200px", "format": "text"},
            {"key": "open",                              "label": "Open",         "width": "70px",  "format": "price"},
            {"key": "high",                              "label": "High",         "width": "70px",  "format": "price"},
            {"key": "low",                               "label": "Low",          "width": "70px",  "format": "price"},
            {"key": "close",                             "label": "Close",        "width": "70px",  "format": "price"},
        ]
```

- [ ] **Step 3: Override `get_strategy_meta` to include filter options**

```python
    def get_strategy_meta(self) -> dict:
        meta = super().get_strategy_meta()
        meta["filter_field"] = "strategy_data.crossover_direction"
        meta["filter_options"] = ["BUY", "SELL"]
        return meta
```

- [ ] **Step 4: Verify import and quick smoke test**

```bash
cd gann-visualizer/backend && python -c "
import pandas as pd, numpy as np
from ema_crossover_strategy import EMACrossoverStrategy
import time
n = 100
df = pd.DataFrame({
    'timestamp': [int(time.time())+i*60 for i in range(n)],
    'open': np.random.uniform(100, 110, n),
    'high': np.random.uniform(100, 110, n),
    'low': np.random.uniform(100, 110, n),
    'close': np.random.uniform(100, 110, n),
})
s = EMACrossoverStrategy(df)
sig = s.generate_signals()
print('Signal columns:', list(sig.columns))
print('Column schema:', s.get_interaction_column_schema())
crosses = [i for i in range(len(sig)) if sig['signal'].iloc[i] != 0]
print(f'Crossover bars: {len(crosses)}')
for ci in crosses[:3]:
    print(f'  Bar {ci}: events={s.extract_events(sig, ci)}')
print('Strategy meta:', s.get_strategy_meta())
"
```

Expected: Prints column schema, crossover bars found, events extracted with strategy_data at each crossover bar.

- [ ] **Step 5: Commit**

```bash
cd gann-visualizer/backend && git add ema_crossover_strategy.py && git commit -m "feat: add extract_events and column schema to EMACrossoverStrategy"
```

---

## Task 3: Unify backend response in main.py

**Files:**
- Modify: `gann-visualizer/backend/main.py` (lines ~1283-1498, ~1260-1269, ~1070-1075)

- [ ] **Step 1: Update `_process_strategy_bar` to emit `intersection_events` and `strategy_meta`**

Change the return statement at the end of `_process_strategy_bar` (around line 1488) from:

```python
        return {
            "type": "signal", 
            "signal": current_trade,
            "indicator_drawings": indicator_drawings,
            "indicator_series": indicator_series
        }
```

to:

```python
        # Extract interaction events from strategy
        interaction_events = []
        try:
            if hasattr(strategy, 'extract_events'):
                interaction_events = strategy.extract_events(signals_df, req.current_index)
        except Exception as evt_err:
            print(f"[Strategy] Error extracting events: {evt_err}")

        # Build strategy_meta (always included — overhead is negligible ~few hundred bytes)
        strategy_meta = None
        try:
            if hasattr(strategy, 'get_strategy_meta'):
                strategy_meta = strategy.get_strategy_meta()
        except Exception as meta_err:
            print(f"[Strategy] Error getting meta: {meta_err}")

        return {
            "type": "step_update",
            "signal": current_trade,
            "drawings": indicator_drawings,
            "remove_drawings": [],
            "pivot_markers": [],
            "intersection_events": interaction_events,
            "indicator_series": indicator_series,
            "candle_pattern": None,
            "debug_info": None,
            "hypothesis_updates": [],
            "strategy_meta": strategy_meta
        }
```

- [ ] **Step 2: Update `_process_study_bar` return to unified schema**

Change the return at the end of `_process_study_bar` (around line 1260) from:

```python
        return {
            "type": "drawing_update",
            "drawings": output_drawings,
            "pivot_markers": output_pivots,
            "remove_drawings": output_remove,
            "intersection_events": output_intersection_events,
            "candle_pattern": output_candle_pattern,
            "debug_info": debug_info,
            "state": {}
        }
```

to:

```python
        # Wrap intersection_events: move angle-specific fields into strategy_data
        wrapped_events = []
        for evt in output_intersection_events:
            wrapped_events.append({
                "time": evt.get("time", 0),
                "price": evt.get("price", 0),
                "type": evt.get("type", ""),
                "details": evt.get("details", ""),
                "open": evt.get("open", 0),
                "high": evt.get("high", 0),
                "low": evt.get("low", 0),
                "close": evt.get("close", 0),
                "strategy_data": {
                    "fan": evt.get("fan", ""),
                    "fanIdentity": evt.get("fanIdentity", evt.get("fan", "")),
                    "fraction": evt.get("fraction", ""),
                    "activeAngles": evt.get("activeAngles", {}),
                    "zone": evt.get("zone", ""),
                    "zoneExtremes": evt.get("zoneExtremes", {}),
                    "nextAngleLine": evt.get("nextAngleLine", ""),
                    "cluster": evt.get("cluster", False),
                    "bar_index": evt.get("bar_index", 0),
                }
            })

        study_meta = {
            "name": "angular_coverage",
            "display_name": "Angular Price Coverage",
            "is_study": True,
            "column_schema": [
                {"key": "time",                          "label": "Time",            "width": "140px", "format": "datetime"},
                {"key": "strategy_data.fan",             "label": "Fan",             "width": "120px", "format": "text"},
                {"key": "strategy_data.fraction",        "label": "Fraction",        "width": "70px",  "format": "text"},
                {"key": "type",                          "label": "Type",            "width": "110px", "format": "text"},
                {"key": "price",                         "label": "Price",           "width": "80px",  "format": "price"},
                {"key": "details",                       "label": "Details",         "width": "200px", "format": "text"},
                {"key": "open",                          "label": "O",               "width": "60px",  "format": "price"},
                {"key": "high",                          "label": "H",               "width": "60px",  "format": "price"},
                {"key": "low",                           "label": "L",               "width": "60px",  "format": "price"},
                {"key": "close",                         "label": "C",               "width": "60px",  "format": "price"},
                {"key": "strategy_data.cluster",         "label": "Cluster",         "width": "70px",  "format": "text"},
                {"key": "strategy_data.zone",            "label": "Zone",            "width": "80px",  "format": "text"},
                {"key": "strategy_data.zoneExtremes",    "label": "Zone Extremes",   "width": "140px", "format": "text"},
                {"key": "strategy_data.nextAngleLine",   "label": "Next Angle Line", "width": "110px", "format": "text"},
            ],
            "filter_field": "strategy_data.fanIdentity",
            "filter_options": [],
        }

        return {
            "type": "step_update",
            "signal": None,
            "drawings": output_drawings,
            "pivot_markers": output_pivots,
            "remove_drawings": output_remove,
            "intersection_events": wrapped_events,
            "indicator_series": None,
            "candle_pattern": output_candle_pattern,
            "debug_info": debug_info,
            "hypothesis_updates": [],
            "strategy_meta": study_meta,
        }
```

- [ ] **Step 3: Remove `evaluate_strategy_step` dispatch — keep but unify the type check**

The `evaluate_strategy_step` function at line 1058 is fine — it already routes to `_process_study_bar` vs `_process_strategy_bar`. No changes needed there. Both now return `"type": "step_update"`.

- [ ] **Step 4: Handle initial `strategy_meta` in `fetch_candles` for studies**

In `fetch_candles` (around line 1042), add `strategy_meta` to the response for studies:

```python
        strategy_meta = None
        if is_study(req.strategy):
            strategy_meta = {
                "name": req.strategy,
                "display_name": "Angular Price Coverage" if req.strategy == "angular_coverage" else "Pivot Points Only",
                "is_study": True,
                "column_schema": [...same as above...],
                "filter_field": "strategy_data.fanIdentity",
                "filter_options": [],
            }

        return {
            "candles": candles_list, 
            "option_cache_ready": option_cache_ready, 
            "markers": initial_markers,
            "drawings": initial_drawings,
            "strategy_meta": strategy_meta,
            "actual_start_date": actual_start_date,
            "actual_start_timestamp": actual_start_timestamp
        }
```

- [ ] **Step 5: Verify backend returns unified schema**

```bash
cd gann-visualizer/backend && python -c "
import json
from main import _process_strategy_bar, _process_study_bar
# Quick syntax check - import succeeds
from base_strategy import BaseStrategy
print('Imports OK')
"
```

Expected: No errors.

- [ ] **Step 6: Commit**

```bash
cd gann-visualizer/backend && git add main.py && git commit -m "feat: unify backend response to step_update schema with intersection_events and strategy_meta"
```

---

## Task 4: Unify frontend ChartDatafeed.js

**Files:**
- Modify: `gann-visualizer/frontend/src/chart/ChartDatafeed.js` (lines ~663-715)

- [ ] **Step 1: Replace the response type branching with unified handler**

Replace lines ~663-715 (from `.then(data => {` through the end of `.then()`) with:

```javascript
                .then(data => {
                    const responseType = data.type || 'legacy';

                    // UNIFIED HANDLER: Both "step_update" and legacy types go through studyCallback
                    // Legacy "signal" type is handled transparently via studyCallback wrapper
                    if (this.studyCallback) {
                        if (responseType === 'step_update') {
                            // New unified response - pass through directly
                            this.studyCallback(data);
                        } else if (responseType === 'signal' || responseType === 'legacy') {
                            // Legacy strategy response - wrap into step_update shape
                            this.studyCallback({
                                type: 'step_update',
                                signal: data.signal || null,
                                drawings: data.indicator_drawings || [],
                                remove_drawings: [],
                                pivot_markers: [],
                                intersection_events: [],
                                indicator_series: data.indicator_series || null,
                                candle_pattern: null,
                                debug_info: null,
                                hypothesis_updates: [],
                                strategy_meta: null
                            });
                            
                            // Also forward trade signal to tradeCallback (existing behavior)
                            if (data.signal && this.tradeCallback) {
                                console.log("[Progressive] Signal found at step", this.currentStep, ":", data.signal.type, "@", data.signal.price);
                                this.lastSignalType = data.signal.type;
                                this.tradeCallback(data.signal);
                            }
                        } else if (responseType === 'drawing_update') {
                            // Legacy study response - wrap into step_update shape
                            this.studyCallback({
                                type: 'step_update',
                                signal: null,
                                drawings: data.drawings || [],
                                remove_drawings: data.remove_drawings || [],
                                pivot_markers: data.pivot_markers || [],
                                intersection_events: data.intersection_events || [],
                                indicator_series: null,
                                candle_pattern: data.candle_pattern || null,
                                debug_info: data.debug_info || null,
                                hypothesis_updates: [],
                                strategy_meta: null
                            });
                        }
                    }

                    // Trade signals always forwarded (for legacy path, new path handled inside studyCallback)
                    if (responseType === 'signal' || responseType === 'legacy') {
                        if (data.signal && this.tradeCallback) {
                            console.log("[Progressive] Signal found at step", this.currentStep, ":", data.signal.type, "@", data.signal.price);
                            this.lastSignalType = data.signal.type;
                            this.tradeCallback(data.signal);
                        }
                    }
                })
```

Wait — that duplicates the trade signal handling. Let me redo this cleanly:

```javascript
                .then(data => {
                    const responseType = data.type || 'legacy';

                    // Trade signals: always forward to tradeCallback
                    if (data.signal && this.tradeCallback &&
                        (responseType === 'signal' || responseType === 'legacy' || responseType === 'step_update')) {
                        console.log("[Progressive] Signal found at step", this.currentStep, ":", data.signal.type, "@", data.signal.price);
                        this.lastSignalType = data.signal.type;
                        this.tradeCallback(data.signal);
                    }

                    // Study/drawing callback: wrap legacy types into unified step_update
                    if (this.studyCallback) {
                        if (responseType === 'step_update') {
                            this.studyCallback(data);
                        } else if (responseType === 'signal' || responseType === 'legacy') {
                            this.studyCallback({
                                type: 'step_update',
                                signal: data.signal || null,
                                drawings: data.indicator_drawings || [],
                                remove_drawings: [],
                                pivot_markers: [],
                                intersection_events: [],
                                indicator_series: data.indicator_series || null,
                                candle_pattern: null,
                                debug_info: null,
                                hypothesis_updates: [],
                                strategy_meta: null
                            });
                        } else if (responseType === 'drawing_update') {
                            this.studyCallback({
                                type: 'step_update',
                                signal: null,
                                drawings: data.drawings || [],
                                remove_drawings: data.remove_drawings || [],
                                pivot_markers: data.pivot_markers || [],
                                intersection_events: data.intersection_events || [],
                                indicator_series: null,
                                candle_pattern: data.candle_pattern || null,
                                debug_info: data.debug_info || null,
                                hypothesis_updates: [],
                                strategy_meta: null
                            });
                        }
                    }
                })
```

- [ ] **Step 2: Commit**

```bash
cd gann-visualizer/frontend && git add src/chart/ChartDatafeed.js && git commit -m "feat: unify ChartDatafeed to step_update handler with legacy wrappers"
```

---

## Task 5: Update TVChartContainer to handle unified response + intersection_events

**Files:**
- Modify: `gann-visualizer/frontend/src/TVChartContainer.jsx` (around line 1632, 1802)

- [ ] **Step 1: Make intersection_events emission unconditional**

The study callback block in `startProgressiveReplay` currently processes responses. The intersection_events emission at line 1802 is inside the `if (props.onAvailableFansUpdated)` block's fan visibility logic. Move it to run unconditionally for all step_update responses.

Find the block starting around line 1802 and ensure it runs regardless of fan availability:

```javascript
                        // Emit price interaction events from backend intersection_events (always present in step_update)
                        if (props.onPriceInteraction && studyData.intersection_events && studyData.intersection_events.length > 0) {
                            console.log(`[TVChart] Emitting ${studyData.intersection_events.length} price interactions to App.jsx`);
                            studyData.intersection_events.forEach(evt => {
                                props.onPriceInteraction(evt);
                            });
                        }
```

This code is already at line 1802-1825 but is nested inside the `if (props.onAvailableFansUpdated)` block. Move it to be at the top level of the study callback, right after the `processStudyResponse` call. The exact relocation depends on the brace structure. The code block from line 1802 to 1825 should be extracted outside the `if (props.onAvailableFansUpdated)` block.

Specifically: cut the block from `// Emit price interaction events...` through the closing `}` of the forEach loop, and paste it immediately after the `studyShapesRef.current = processStudyResponse(...)` line (around line 1639), before the indicator lines rendering block.

- [ ] **Step 2: Handle strategy_meta caching and forwarding**

Add a ref for cached column schema:
```javascript
    const cachedColumnSchemaRef = useRef(null);
```

After the intersection_events emission, add strategy_meta handling:
```javascript
                        // Cache and forward strategy_meta (column schema, filter options)
                        if (studyData.strategy_meta) {
                            if (studyData.strategy_meta.column_schema) {
                                cachedColumnSchemaRef.current = studyData.strategy_meta.column_schema;
                            }
                            // Forward to App.jsx via onStrategyMeta callback
                            if (props.onStrategyMeta) {
                                props.onStrategyMeta(studyData.strategy_meta);
                            }
                        }
```

Add `onStrategyMeta` to the props destructuring at the top of the component.

- [ ] **Step 3: Commit**

```bash
cd gann-visualizer/frontend && git add src/TVChartContainer.jsx && git commit -m "feat: unconditional intersection_events emission + strategy_meta forwarding in TVChartContainer"
```

---

## Task 6: Dynamic column rendering in App.jsx Price Interactions tab

**Files:**
- Modify: `gann-visualizer/frontend/src/App.jsx`

- [ ] **Step 1: Add state for column schema and utility to resolve dot-notation keys**

Add new state variables alongside existing state:

```javascript
    const [interactionColumnSchema, setInteractionColumnSchema] = useState(null)
    const [interactionFilterField, setInteractionFilterField] = useState(null)
    const [interactionFilterOptions, setInteractionFilterOptions] = useState([])
```

Add a helper function (outside the component, near `calculateSummary`):

```javascript
const resolveNestedKey = (obj, key) => {
    if (!obj || !key) return null;
    const parts = key.split('.');
    let current = obj;
    for (const part of parts) {
        if (current == null) return null;
        current = current[part];
    }
    return current;
};
```

- [ ] **Step 2: Add `onStrategyMeta` handler to TVChartContainer props**

Find the `<TVChartContainer` JSX element and add:
```jsx
                        onStrategyMeta={(meta) => {
                            if (meta.column_schema) {
                                setInteractionColumnSchema(meta.column_schema);
                            }
                            if (meta.filter_field) {
                                setInteractionFilterField(meta.filter_field);
                            }
                            if (meta.filter_options) {
                                setInteractionFilterOptions(meta.filter_options);
                            }
                        }}
```

- [ ] **Step 3: Build column schema from strategy_meta in fetch_candles response for studies**

In `handleStartReplay`, after `const data = await response.json();`, add:

```javascript
            if (data.strategy_meta && data.strategy_meta.column_schema) {
                setInteractionColumnSchema(data.strategy_meta.column_schema);
                setInteractionFilterField(data.strategy_meta.filter_field || null);
                setInteractionFilterOptions(data.strategy_meta.filter_options || []);
            } else {
                setInteractionColumnSchema(null);
                setInteractionFilterField(null);
                setInteractionFilterOptions([]);
            }
```

- [ ] **Step 4: Replace hardcoded Price Interactions table with dynamic rendering**

The full replacement spans lines ~686-855. Replace the entire `{bottomPanelTab === 'interactions' && (` block. The new code uses `interactionColumnSchema` (with fallback to hardcoded angular_coverage schema for backward compat) and renders all columns dynamically.

Key parts of the new implementation:

```jsx
                        {bottomPanelTab === 'interactions' && (
                            <div className="interactions-list">
                                {priceInteractions.length === 0 ? (
                                    <p>No price interactions recorded yet. Start a step-by-step simulation.</p>
                                ) : (
                                    (() => {
                                        const schema = interactionColumnSchema || [
                                            // Default angular_coverage fallback schema
                                            {"key": "time",                          "label": "Time",            "width": "140px", "format": "datetime"},
                                            {"key": "strategy_data.fan",             "label": "Fan",             "width": "120px", "format": "text"},
                                            {"key": "strategy_data.fraction",        "label": "Fraction",        "width": "70px",  "format": "text"},
                                            {"key": "type",                          "label": "Type",            "width": "110px", "format": "text"},
                                            {"key": "price",                         "label": "Price",           "width": "80px",  "format": "price"},
                                            {"key": "details",                       "label": "Details",         "width": "200px", "format": "text"},
                                            {"key": "open",                          "label": "O",               "width": "60px",  "format": "price"},
                                            {"key": "high",                          "label": "H",               "width": "60px",  "format": "price"},
                                            {"key": "low",                           "label": "L",               "width": "60px",  "format": "price"},
                                            {"key": "close",                         "label": "C",               "width": "60px",  "format": "price"},
                                            {"key": "strategy_data.cluster",         "label": "Cluster",         "width": "70px",  "format": "text"},
                                            {"key": "strategy_data.zone",            "label": "Zone",            "width": "80px",  "format": "text"},
                                            {"key": "strategy_data.zoneExtremes",    "label": "Zone Extremes",   "width": "140px", "format": "text"},
                                            {"key": "strategy_data.nextAngleLine",   "label": "Next Angle Line", "width": "110px", "format": "text"},
                                        ];
                                        
                                        const filterField = interactionFilterField || 'strategy_data.fanIdentity';
                                        const filterOpts = interactionFilterOptions;
                                        
                                        // Build filter options from data if strategy didn't provide them
                                        const dynamicFilterOptions = filterOpts.length > 0 
                                            ? filterOpts 
                                            : [...new Set(priceInteractions.map(h => resolveNestedKey(h, filterField)))]
                                                .filter(Boolean).sort();
                                        
                                        // Filter interactions by current filter
                                        const filteredData = priceInteractions.filter(hit => {
                                            if (filterFan === 'all') return true;
                                            const val = resolveNestedKey(hit, filterField);
                                            return val === filterFan || (hit.fanIdentity || hit.fan) === filterFan;
                                        });

                                        // Helper to format cell value
                                        const formatCell = (hit, col) => {
                                            const val = resolveNestedKey(hit, col.key);
                                            if (val == null || val === '') return '-';
                                            if (col.format === 'datetime') return new Date(val * 1000).toLocaleString().replace(/,/g, '');
                                            if (col.format === 'price' && typeof val === 'number') return val.toFixed(2);
                                            if (typeof val === 'object') {
                                                // Handle zoneExtremes: {lowest_close, highest_close}
                                                if (val.highest_close != null) return `${val.lowest_close?.toFixed(2) || '-'} - ${val.highest_close?.toFixed(2)}`;
                                                return JSON.stringify(val).replace(/,/g, ';');
                                            }
                                            if (typeof val === 'boolean') return val ? 'Yes' : 'No';
                                            return String(val);
                                        };

                                        // Build CSV/TSV helper
                                        const buildCsvRows = (data, includeHeader) => {
                                            const rows = [];
                                            if (includeHeader) rows.push(schema.map(c => c.label));
                                            data.forEach((hit, i) => {
                                                rows.push(schema.map(c => formatCell(hit, c)));
                                            });
                                            return rows;
                                        };

                                        return (
                                            <>
                                                <div style={{ marginBottom: '10px', display: 'flex', gap: '10px', alignItems: 'center', justifyContent: 'space-between', position: 'sticky', top: 0, zIndex: 10, backgroundColor: '#1e1e1e', paddingTop: '4px' }}>
                                                    <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                                                        <label style={{ fontSize: '12px' }}>
                                                            Filter:
                                                            <select
                                                                value={filterFan}
                                                                onChange={(e) => setFilterFan(e.target.value)}
                                                                style={{ marginLeft: '5px', padding: '2px 5px', fontSize: '11px' }}
                                                            >
                                                                <option value="all">All</option>
                                                                {dynamicFilterOptions.map(opt => (
                                                                    <option key={String(opt)} value={String(opt)}>{String(opt)}</option>
                                                                ))}
                                                            </select>
                                                        </label>
                                                        <span style={{ fontSize: '11px', color: '#888' }}>
                                                            Showing {filteredData.length} of {priceInteractions.length} events
                                                        </span>
                                                    </div>
                                                    <div style={{ display: 'flex', gap: '8px' }}>
                                                        <button 
                                                            onClick={() => {
                                                                const rows = buildCsvRows(filteredData, true);
                                                                const tsvContent = rows.map(e => e.join("\t")).join("\n");
                                                                navigator.clipboard.writeText(tsvContent).then(() => {
                                                                    alert("Table copied to clipboard!");
                                                                }).catch(err => console.error(err));
                                                            }}
                                                            style={{ padding: '4px 8px', fontSize: '11px', cursor: 'pointer', backgroundColor: '#4CAF50', color: 'white', border: 'none', borderRadius: '3px' }}
                                                        >Copy Table</button>
                                                        <button 
                                                            onClick={() => {
                                                                const rows = buildCsvRows(priceInteractions, true);
                                                                const csvContent = rows.map(e => e.join(",")).join("\n");
                                                                const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
                                                                const url = URL.createObjectURL(blob);
                                                                const link = document.createElement("a");
                                                                link.setAttribute("href", url);
                                                                link.setAttribute("download", "frontend_price_interactions.csv");
                                                                document.body.appendChild(link);
                                                                link.click();
                                                                document.body.removeChild(link);
                                                                URL.revokeObjectURL(url);
                                                            }}
                                                            style={{ padding: '4px 8px', fontSize: '11px', cursor: 'pointer', backgroundColor: '#2196F3', color: 'white', border: 'none', borderRadius: '3px' }}
                                                        >Export CSV</button>
                                                    </div>
                                                </div>
                                                <div className="table-container" style={{ overflowX: 'auto' }}>
                                                    <table className="interactions-table" style={{ whiteSpace: 'nowrap' }}>
                                                        <thead>
                                                            <tr>
                                                                <th>#</th>
                                                                {schema.map(col => (
                                                                    <th key={col.key} style={col.width ? {minWidth: col.width} : {}}>
                                                                        {col.label}
                                                                    </th>
                                                                ))}
                                                            </tr>
                                                        </thead>
                                                        <tbody>
                                                            {filteredData.map((hit, i) => (
                                                                <tr 
                                                                    key={i}
                                                                    className={i === selectedInteractionIndex ? 'selected-row' : ''}
                                                                    onClick={() => setSelectedInteractionIndex(i)}
                                                                    style={{ cursor: 'pointer' }}
                                                                >
                                                                    <td>{i + 1}</td>
                                                                    {schema.map(col => (
                                                                        <td key={col.key} style={{ fontSize: '11px' }}>
                                                                            {formatCell(hit, col)}
                                                                        </td>
                                                                    ))}
                                                                </tr>
                                                            ))}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </>
                                        );
                                    })()
                                )}
                            </div>
                        )}
```

Note: This is a large replacement. The exact old_str to replace is from line 686 (`{bottomPanelTab === 'interactions' && (`) through line 855 (the closing `)}` before `{bottomPanelTab === 'hypothesis' &&`).

- [ ] **Step 5: Commit**

```bash
cd gann-visualizer/frontend && git add src/App.jsx && git commit -m "feat: dynamic column rendering for Price Interactions tab from strategy_meta"
```

---

## Task 7: End-to-end verification

**Files:** None (verification only)

- [ ] **Step 1: Start backend and verify unified response**

```bash
cd gann-visualizer/backend && python main.py
```

Let it start on port 8005. In another terminal:

```bash
cd gann-visualizer/frontend && npm run dev
```

Expected: Frontend starts on port 5173 (or whatever Vite uses).

- [ ] **Step 2: Test Angular Coverage Strategy**

1. Open browser to frontend
2. Select "Angular Price Coverage Study" from dropdown
3. Set date range, click "Run Step-by-Step"
4. Verify: Price Interactions tab populates with events
5. Verify: Columns show Fan, Fraction, Zone, etc. (dynamic schema fallback)
6. Verify: Fan filter dropdown works

- [ ] **Step 3: Test EMA Crossover Strategy**

1. Select "9/21 EMA Crossover Strategy" from dropdown
2. Click "Run Step-by-Step"
3. Verify: Price Interactions tab populates with EMA crossover events
4. Verify: Columns show Direction, Fast EMA, Slow EMA (EMA schema)
5. Verify: Filter dropdown shows BUY / SELL options

- [ ] **Step 4: Verify console logs for both strategies**

Check browser console for:
- `[TVChart] Emitting N price interactions to App.jsx`
- No errors related to missing fields

---

## Task 8: Cleanup — remove legacy type branching (after verification)

**Files:**
- Modify: `gann-visualizer/frontend/src/chart/ChartDatafeed.js`
- Modify: `gann-visualizer/backend/main.py`

- [ ] **Step 1: Simplify ChartDatafeed.js once backend only returns step_update**

Once verified that the backend always returns `step_update`, simplify the handler to only handle that type:

```javascript
                .then(data => {
                    // All responses now use step_update type
                    if (data.signal && this.tradeCallback) {
                        console.log("[Progressive] Signal found at step", this.currentStep, ":", data.signal.type, "@", data.signal.price);
                        this.lastSignalType = data.signal.type;
                        this.tradeCallback(data.signal);
                    }
                    if (this.studyCallback) {
                        this.studyCallback(data);
                    }
                })
```

- [ ] **Step 2: Commit**

```bash
cd gann-visualizer/frontend && git add src/chart/ChartDatafeed.js && git commit -m "chore: simplify ChartDatafeed to step_update-only handler"
```

---

## Scope Note: Deferred to Follow-Up Plan

The following items from the spec are **not covered** in this plan and should be addressed in a subsequent plan:

| Item | Reason |
|---|---|
| **Hypothesis Navigator live mode** (Section 7 of spec) | Requires backend event buffering, incremental hypothesis evaluation, and `hypothesis_updates` field wiring. The `hypothesis_updates: []` placeholder is already in the schema. |
| **run_simulation.py refactoring** (Section 7 batch mode) | Needs `--strategy` flag and strategy dispatch logic. `EMACrossoverHypothesis` already exists in `strategy_analyzer.py` and reads from `candles.csv` — just needs the runner to invoke it. |
| **Event CSV format changes** (Section 8) | Adding `strategy` and `strategy_data` columns to `events.csv`. Backward-compatible via optional columns. |
| **Other strategy implementations** | `FiveEMAStrategy`, `Mechanical3DaySwingStrategy`, etc. — each gets its own `extract_events()` and `get_interaction_column_schema()` overrides later. |

This plan delivers the core architectural unification — once complete, adding any of the above is a matter of implementing a strategy's `extract_events()` method and wiring the pipeline.```
