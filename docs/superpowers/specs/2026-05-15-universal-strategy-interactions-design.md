# Universal Strategy Interactions & Hypothesis Navigator

**Status:** Draft  
**Date:** 2026-05-15  
**Author:** Agent-assisted design

## Problem

The Price Interactions tab and Hypothesis Navigator tab on the front-end are hardwired to work only with the Angular Price Coverage study. When replaying any other strategy (e.g., EMA Crossover, Mechanical 3-Day Swing, Ichimoku Cloud), neither tab populates — they show zero events.

**Root cause:** The backend has a binary fork between "studies" (`angular_coverage`, `pivot_points_only`) and "strategies" (everything else). Only the study code path emits `intersection_events`. Strategies emit only buy/sell signals and indicator series. The frontend response dispatch (`signal` vs `drawing_update`) further doubles down on this split.

## Design Goals

1. **Every strategy** — existing and future — populates both the Price Interactions tab and the Hypothesis Navigator automatically.
2. **No per-strategy hardcoding** on the frontend. Column schemas, filter options, and event rendering are driven by metadata from the backend.
3. **Unified code path** — eliminate the `is_study()` fork in response handling; one response schema, one frontend handler.
4. **Preserve existing functionality** — Angular Coverage's rich event model (fans, zones, clusters, target progression) must continue working exactly as before.
5. **Living hypothesis evaluation** — the Hypothesis Navigator can evaluate during live replay, not just from pre-generated batch reports.

## Architecture Overview

```
 ┌──────────────────────────────────────────────────────────────┐
 │                     Frontend (React)                          │
 │                                                               │
 │  App.jsx                                                      │
 │  ├─ Price Interactions tab ← intersection_events (always)    │
 │  │   └─ Columns rendered from strategy_meta.column_schema    │
 │  ├─ Hypothesis Navigator tab ← hypothesis_events (live)      │
 │  │   └─ Columns rendered from strategy_meta.hypothesis_cols  │
 │  └─ TVChartContainer → processStepUpdate() (single handler)  │
 │       └─ No more signal vs drawing_update dispatch           │
 └──────────────┬───────────────────────────────────────────────┘
                │  POST /evaluate_strategy_step
                │  Response: { type: "step_update", ... }
                ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                     Backend (FastAPI)                         │
 │                                                               │
 │  _handle_step(req)  ←── single unified handler               │
 │  │                                                            │
 │  ├─ Strategy path:                                            │
 │  │   strategy.generate_signals()                              │
 │  │   strategy.extract_events(df, bar_index)  ← NEW            │
 │  │   strategy.get_indicator_series()                          │
 │  │   strategy.get_strategy_meta()           ← NEW            │
 │  │                                                            │
 │  └─ Study path:                                               │
 │      study.process_bar(...)                                   │
 │      (wrap response into step_update)                         │
 │                                                               │
 │  Returns unified step_update for both paths                   │
 └──────────────┬───────────────────────────────────────────────┘
                │
                ▼
 ┌──────────────────────────────────────────────────────────────┐
 │                  BaseStrategy (ABC)                           │
 │                                                               │
 │  + generate_signals() → df          (existing, abstract)      │
 │  + get_indicator_series() → dict    (existing)                │
 │  + extract_events(df, bar_index) → list[dict]  ← NEW         │
 │  + get_strategy_meta() → dict                 ← NEW          │
 │  + get_interaction_column_schema() → list      ← NEW         │
 └──────────────────────────────────────────────────────────────┘
```

## Section 1 — Unified Response Schema

The `evaluate_strategy_step` response is unified into a single `step_update` type. Every field is always present; absence is represented by `null` or `[]`.

```json
{
    "type": "step_update",
    "signal": null,
    "drawings": [...],
    "remove_drawings": [...],
    "pivot_markers": [...],
    "intersection_events": [...],
    "indicator_series": null,
    "candle_pattern": null,
    "debug_info": null,
    "strategy_meta": {
        "name": "ema_crossover",
        "display_name": "9/21 EMA Crossover Strategy",
        "is_study": false,
        "column_schema": [...],
        "filter_field": "strategy_data.crossover_direction",
        "filter_options": ["BUY", "SELL"]
    }
}
```

**Backward compatibility:** The old `drawing_update` and `signal` response shapes are wrapped into this format inside `evaluate_strategy_step` before returning. No existing consumer breaks during rollout.

**Frontend impact:** `ChartDatafeed.js` replaces the `responseType === 'drawing_update'` / `responseType === 'signal'` branch with a single path that always calls `studyCallback(data)`.

## Section 2 — Polymorphic Column Schema

Each strategy defines its own `column_schema` via `get_interaction_column_schema()`. This is sent once (cached on the frontend) via `strategy_meta` in the response.

```python
# From EMACrossoverStrategy
def get_interaction_column_schema(self):
    return [
        {"key": "time",                              "label": "Time",         "width": "140px", "format": "datetime"},
        {"key": "strategy_data.crossover_direction", "label": "Direction",    "width": "80px",  "format": "text"},
        {"key": "strategy_data.fast_ema_value",      "label": "Fast EMA",     "width": "80px",  "format": "price"},
        {"key": "strategy_data.slow_ema_value",      "label": "Slow EMA",     "width": "80px",  "format": "price"},
        {"key": "type",                              "label": "Event",        "width": "110px", "format": "text"},
        {"key": "price",                             "label": "Price",        "width": "80px",  "format": "price"},
        {"key": "details",                           "label": "Details",      "width": "200px","format": "text"},
        {"key": "open",                              "label": "Open",         "width": "70px",  "format": "price"},
        {"key": "high",                              "label": "High",         "width": "70px",  "format": "price"},
        {"key": "low",                               "label": "Low",          "width": "70px",  "format": "price"},
        {"key": "close",                             "label": "Close",        "width": "70px",  "format": "price"},
    ]
```

**Key design:** Dot-notation keys (`strategy_data.fan`, `strategy_data.fast_ema_value`) tell the rendering logic how to traverse the event object. The `format` hint controls rendering (datetime → locale string, price → fixed decimal, text → as-is).

**Frontend behavior:**
- On the first `step_update` response (or replay init), the frontend stores `strategy_meta.column_schema`.
- The Price Interactions table is rendered entirely from this schema — zero hardcoded column definitions.
- Filter dropdown options are populated from `strategy_meta.filter_options`.

## Section 3 — Universal Event Model

Every strategy emits events via `extract_events(df, bar_index)` into the same generic shape:

```python
# Generic event dict (emitted by any strategy)
{
    "time": 1234567890,
    "price": 22500.50,
    "type": "EMA_CROSSOVER_UP",
    "details": "9 EMA crossed above 21 EMA",
    "open": 22490.0,
    "high": 22520.0,
    "low": 22485.0,
    "close": 22500.0,
    "strategy_data": {
        "crossover_direction": "BUY",
        "fast_ema_value": 22495.30,
        "slow_ema_value": 22480.10,
    }
}
```

The `strategy_data` dict is polymophic per strategy. The frontend does not interpret it — it only traverses it via the column schema dot-notation.

### Angular Coverage strategy_data mapping

Existing fields (`fan`, `fanIdentity`, `fraction`, `activeAngles`, `zone`, `zoneExtremes`, `nextAngleLine`, `cluster`) are moved into `strategy_data` rather than top-level. This keeps the top-level event clean and forces all strategy-specific data through the same polymorphic channel.

### EMA Crossover events

`EMACrossoverStrategy.extract_events()` detects crossovers from the signal DataFrame and emits events at the bar where the crossover occurred:

| Event type | When |
|---|---|
| `EMA_CROSSOVER_UP` | 9 EMA crosses above 21 EMA (BUY signal bar) |
| `EMA_CROSSOVER_DOWN` | 9 EMA crosses below 21 EMA (SELL signal bar) |
| `EMA_TEST` | Price touches fast EMA without crossing slow EMA (future) |

## Section 4 — BaseStrategy Interface Changes

```python
class BaseStrategy(ABC):
    # --- Existing (unchanged) ---
    @abstractmethod
    def generate_signals(self) -> pd.DataFrame: ...

    @abstractmethod
    def get_strategy_name(self) -> str: ...

    def get_indicator_series(self) -> Dict[str, list]:
        """Override to return indicator time-value pairs for chart rendering."""
        return {}

    # --- NEW METHODS ---
    def extract_events(self, df: pd.DataFrame, bar_index: int) -> list[dict]:
        """
        Extract strategy-specific interaction events at the given bar.
        
        Default: returns empty list. Override per strategy.
        Called during step-by-step replay for the Price Interactions tab.
        """
        return []

    def get_strategy_meta(self) -> dict:
        """
        Return strategy metadata including column schema.
        Default derived from get_strategy_name() and get_interaction_column_schema().
        """
        return {
            "name": self.__class__.__name__,
            "display_name": self.get_strategy_name(),
            "is_study": False,
            "column_schema": self.get_interaction_column_schema(),
            "filter_field": None,
            "filter_options": [],
        }

    def get_interaction_column_schema(self) -> list[dict]:
        """
        Return column definitions for Price Interactions table.
        Override per strategy. Default returns universal columns only.
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
```

New methods have default implementations so no existing strategy breaks. Only strategies that want Price Interactions data override `extract_events()` and `get_interaction_column_schema()`.

## Section 5 — Backend Handler Unification

### `_handle_step(req)` (replaces `evaluate_strategy_step` dispatch)

```python
async def _handle_step(req):
    """Unified step handler for studies and strategies."""
    if is_study(req.strategy):
        raw = await _process_study_bar(req)
        return _wrap_study_response(raw, req.strategy)
    else:
        raw = await _process_strategy_bar(req)
        return _wrap_strategy_response(raw, req.strategy)
```

Both wrappers ensure the output conforms to the `step_update` schema with `intersection_events` and `strategy_meta` always present.

### `_process_strategy_bar` additions

After generating signals, it calls:
```python
events = strategy.extract_events(df, req.current_index)
```
And includes `"intersection_events": events` in the response. It also calls `strategy.get_strategy_meta()` and populates `strategy_meta`.

### `_process_study_bar` changes

The study's existing `intersection_events` output is mapped into the unified event schema by nesting angle-specific fields under `strategy_data`. The study defines its own `get_strategy_meta()` equivalent (or the wrapper hardcodes the angular_coverage column schema during migration).

### `/fetch_candles` additions

Include `strategy_meta` in the response so the frontend has the column schema before the first bar is evaluated. This is null for strategies (since no strategy instance exists at fetch time), so strategy_meta is returned on the first `step_update` instead. The frontend handles the deferred arrival.

## Section 6 — Frontend Changes

### ChartDatafeed.js

| Current | Change |
|---|---|
| Two branches: `responseType === 'drawing_update'` and `responseType === 'signal'` | Single branch: `responseType === 'step_update'` |
| Signal path manually wraps indicator data into a partial studyCallback | studyCallback receives full data always |
| No intersection_events for strategies | Always checks and forwards intersection_events |

### TVChartContainer.jsx

| Current | Change |
|---|---|
| `onPriceInteraction` only called from drawing_update handler | Called unconditionally from step_update handler |
| Fan visibility sync only for studies | Runs for all responses; no-ops when no fan drawings present |
| Indicator lines rendered from signal path workaround | Rendered from unified indicator_series field |

### App.jsx — Price Interactions Tab

| Current | Change |
|---|---|
| Hardcoded columns: `#`, `Time`, `Fan`, `Fraction`, `Price`, `Type`, `Details`, `OHLC`, `Cluster`, `Zone`, `Zone Extremes`, `Next Angle Line`, `Active Angles` | Rendered dynamically from `strategy_meta.column_schema` |
| Hardcoded filter by fan identity | Filter by `strategy_meta.filter_field` using `strategy_meta.filter_options` |
| `interactions-table` class hardcoded | Same class, content dynamically generated |

### App.jsx — Hypothesis Navigator Tab

| Current | Change |
|---|---|
| Loads pre-generated JSON from `GET /api/hypothesis-reports` | Also can load live hypothesis events from replay step response |
| Hardcoded columns: `#`, `Type`, `DateTime`, `Fan`, `Frac`, `Target`, `Price`, `Breach`, `Outcome`, `MFE`, `MAE` | Columns driven by strategy's hypothesis column schema |
| Static batch reports only | Hybrid: batch reports + live replay evaluation |

## Section 7 — Hypothesis Navigator Live Mode

During step-by-step replay, the backend evaluates hypotheses incrementally:

1. On each bar, `extract_events()` produces events.
2. These events are buffered in-memory on the backend.
3. Every N bars (configurable, default 20), hypotheses are evaluated on the buffer.
4. Results are emitted as `hypothesis_updates` in the `step_update` response.
5. The frontend Hypothesis Navigator tab updates live.

The live mode uses the same `Hypothesis.evaluate()` interface as batch mode — the only difference is incremental invocation vs. one-shot.

### Batch mode continues

`run_simulation.py` is refactored to accept a `--strategy` parameter. For every strategy type, it:
1. Fetches candles.
2. Runs the strategy/study to produce events (via the same `extract_events()` interface).
3. Writes `events.csv` and `candles.csv` (already done for angular_coverage).
4. `generate_hypothesis_reports.py` consumes these CSVs using the same `Hypothesis` classes.

This means `EMACrossoverHypothesis` (already defined in `strategy_analyzer.py`) becomes automatically runnable via the batch pipeline once `run_simulation.py` supports the `--strategy ema_crossover` flag.

## Section 8 — Event CSV Format Changes

The current `events.csv` format has these columns:
```
#, Time, Fan, Fraction, Price, Type, Details, Open, High, Low, Close,
Active_Angles, Cluster, Zone, Zone_Highest_Close, Zone_Lowest_Close,
Next_Angle_Line, MFE_10, MAE_10, bars_elapsed, bar_index
```

This is Angle-specific. For universalization, the CSV gains:

1. A `strategy` column identifying which strategy produced the event.
2. A `strategy_data` column (JSON string) holding the polymorphic strategy payload.
3. The Angle-specific columns remain for backward compatibility but are populated only for `angular_coverage` events.

## Section 9 — Strategy_meta Caching

The column schema for a given strategy never changes during replay. To avoid bloating every `step_update` response, `strategy_meta` is included:
- In the first `step_update` response (bar_index = 0 or replay_start)
- Never after that (the frontend caches it)

The frontend stores `cachedColumnSchema` in state, initialized from `fetch_candles` or the first `step_update`.

## Section 10 — Migration Path & Rollout Order

Phases ordered to deliver value at each step without breaking existing functionality:

1. **Add `extract_events()` to BaseStrategy** (default no-op) — No visible change.
2. **Implement `EMACrossoverStrategy.extract_events()`** — Events generated but not yet visible.
3. **Add `get_interaction_column_schema()` to BaseStrategy** — Schema available but not yet consumed.
4. **Unify backend response** — `_process_strategy_bar` wraps output with `intersection_events` and `strategy_meta`. Study path unchanged. Old response types still supported via wrapper.
5. **Unify frontend ChartDatafeed.js** — Single handler for `step_update`. Price Interactions tab now renders dynamically from column schema. EMA crossover events become visible.
6. **Add Hypothesis Navigator live mode** — Backend buffers events, evaluates hypotheses incrementally, emits in step_update.
7. **Refactor run_simulation.py** — Accept `--strategy` parameter. Any strategy can be batch-simulated and fed to `generate_hypothesis_reports.py`.
8. **Cleanup** — Remove old `drawing_update` / `signal` response type branching (no longer needed after all consumers are on `step_update`).

## Section 11 — Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Angular Coverage events change shape (fields move to `strategy_data`) | Phase 1 wraps old format into new; both served during migration |
| Frontend column rendering performance with dynamic schema | Schema cached once; table uses React keys on stable columns |
| Hypothesis live evaluation is too slow for 1m bars | Default batch interval of 20 bars; configurable per strategy |
| `strategy_data` as JSON string in CSV breaks analysis scripts | Provide a `_flatten_strategy_data()` utility for pandas consumption |
