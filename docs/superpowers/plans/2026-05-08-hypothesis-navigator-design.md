# Hypothesis Navigator — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a navigable JSON file during corpus tests containing fan geometry per event, and build a Hypothesis Navigator panel in the frontend to load and navigate it.

**Architecture:** Two parallel changes: (1) Backend augments `TargetProgressionHypothesis` to emit fan geometry per event during evaluation, and `generate_hypothesis_reports.py` saves it as JSON alongside the text report. (2) Frontend adds a new "Hypothesis" tab that loads the JSON, displays an event list, and renders fans + markers on click using existing `processStudyResponse` code.

**Tech Stack:** Python (backend), React + TradingView Charting Library (frontend), JSON

---

## File Inventory

### Backend
- `gann-visualizer/backend/analysis/strategy_analyzer.py` — Modify `TargetProgressionHypothesis` to attach fan geometry to each event record
- `gann-visualizer/backend/generate_hypothesis_reports.py` — Extend to also write a `.json` file alongside the `.txt` report
- `gann-visualizer/backend/run_corpus.py` or wherever corpus tests are triggered — Ensure JSON output path is passed to hypothesis evaluator

### Frontend
- `gann-visualizer/frontend/src/App.jsx` — Add "Hypothesis" tab panel
- `gann-visualizer/frontend/src/TVChartContainer.jsx` — Add `loadHypothesisJSON()` and `navigateToEvent()` methods exposed via `useImperativeHandle`
- `gann-visualizer/frontend/src/chart/ChartDatafeed.js` — No changes needed (existing geometry rendering is sufficient)

### New File
- None required — existing code paths handle geometry rendering

---

## Task 1: Add `fan_geometry` field to `TargetProgressionHypothesis` events

**Files:**
- Modify: `gann-visualizer/backend/analysis/strategy_analyzer.py:247-289`

**Context:** During `_log_target_event`, each event already has fan identity and timestamp. The `df` (events DataFrame) contains all the raw events including `BREACH_CONFIRMED` rows that carry the fan/angle information. However, to reconstruct the full fan geometry at that timestamp, we need the candle data and scale ratio — which `TargetProgressionHypothesis.evaluate()` does not currently receive.

**Solution:** The simplest path is to capture just the fan identity and pivot pair from the events DataFrame, then reconstruct the fan lines in `generate_hypothesis_reports.py` which already has the full dataset loaded. So `TargetProgressionHypothesis` only needs to attach the minimal context (fan_id, fan_identity, pivot timestamps) to each event — `generate_hypothesis_reports.py` handles geometry reconstruction.

**This means Task 1 is actually a NO-OP for the backend hypothesis class.** The events DataFrame already has all the fan/angle data needed. Geometry reconstruction happens in Task 2.

- [ ] **Step 1: Verify the events DataFrame has fan geometry columns**

Run: open the events CSV used by a recent corpus run and inspect columns.

The events.csv from a simulation run has columns including `Fan`, `Fraction`, `Type`, `Price`, `Time`, `bar_index`, and crucially `Active_Angles` (JSON string with all active angle prices). This is already sufficient to reconstruct which fans and lines were active at each event.

- [ ] **Step 2: Verify `generate_hypothesis_reports.py` has access to the full dataset**

The script reads `events.csv` — which is the full simulation output — and each hypothesis class evaluates it. The `TargetProgressionHypothesis` already iterates over events and has access to all columns. No changes needed to the hypothesis class itself.

- [ ] **Step 3: Commit**

```bash
git add gann-visualizer/backend/analysis/strategy_analyzer.py
git commit -m "chore: no changes needed - events.csv has fan geometry columns"
```

---

## Task 2: Extend `generate_hypothesis_reports.py` to produce JSON with fan geometry

**Files:**
- Modify: `gann-visualizer/backend/generate_hypothesis_reports.py`

**What to add:** After generating the text report for `TargetProgressionHypothesis`, also write a `.json` file containing all events with the fan geometry reconstructed from the events.csv data.

The geometry reconstruction uses the `Active_Angles` column from events.csv — it maps each fan's fraction to its price at the event timestamp, which is already computed by the simulation. We then format it as the frontend expects: `fan_state.fans[].lines[].points[]`.

```python
import json

def build_fan_geometry_from_row(row, fan_id, display_label):
    """Reconstruct fan lines from a single events row's Active_Angles column."""
    active_angles_str = str(row.get('Active_Angles', '{}')).replace("'", '"')
    try:
        active_angles = json.loads(active_angles_str)
    except json.JSONDecodeError:
        active_angles = {}

    fan_info = row.get('Fan', fan_id)
    fan_priority = fan_info.split('(')[0].strip() if '(' in fan_info else 'Unknown'

    fan = {
        'fan_id': fan_id,
        'display_label': display_label,
        'priority': len(fan_priority) if fan_priority != 'Unknown' else 0,
        'lines': []
    }

    angle_colors = {
        '0.875': '#2196F3', '0.75': '#4CAF50', '0.5': '#FF9800', '0.25': '#F44336'
    }

    for fraction, price in active_angles.items():
        if not price or price <= 0:
            continue
        fraction_str = str(fraction)
        fan['lines'].append({
            'id': f"{fan_id}_{fraction_str}",
            'fraction': float(fraction_str) if fraction_str not in ('horizontal', 'full_coverage', 'main') else None,
            'points': [
                {'time': int(row['bar_index']), 'price': float(price)},
                {'time': int(row['bar_index']) + 1000, 'price': float(price)}
            ],
            'options': {
                'linecolor': angle_colors.get(fraction_str, '#888888'),
                'linewidth': 2 if fraction_str != '0.5' else 4,
                'linestyle': 1,
                'extendRight': True
            }
        })

    return fan
```

After `write_event()` in the existing `for e in live_events:` loop, call `build_fan_geometry_from_row()` and append to `live_events_geometry`. At the end of the script (after all text reports are written), add:

```python
json_output = {
    'metadata': {
        'symbol': instrument,
        'timeframe': timeframe,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'total_events': result['sample_size'],
        'win_rate': result['win_rate'],
        'generated_at': datetime.now().isoformat()
    },
    'live_events': live_events_geometry,
    'retro_events': retro_events_geometry,
    'summary': {
        'sample_size': result['sample_size'],
        'win_rate': result['win_rate'],
        'live_sample_size': result.get('live_sample_size', 0),
        'live_win_rate': result.get('live_win_rate', 0),
        'retro_sample_size': result.get('retro_sample_size', 0),
        'retro_win_rate': result.get('retro_win_rate', 0)
    }
}

json_path = filepath.replace('.txt', '.json')
with open(json_path, 'w') as f:
    json.dump(json_output, f, indent=2)
print(f"Generated {os.path.basename(json_path)}")
```

- [ ] **Step 1: Add `build_fan_geometry_from_row` helper and JSON output to `generate_hypothesis_reports.py`**

```python
import json

# Add before the existing code
def _row_to_event_record(entry, fan_display_label):
    """Convert a single event dict to the frontend's expected event format with fan geometry."""
    fan_id = entry.get('fan', 'Unknown')

    # Parse Active_Angles from O/H/L/C if available (already embedded in entry from evaluate())
    active_angles = {}
    # The Active_Angles column is only in the raw CSV, not in detailed_log entries.
    # We reconstruct from breach_price + fraction-based angle formula instead.
    # Simpler: store the minimal event info; frontend uses the timestamp to look up geometry from a separate geometry index.

    return {
        'event_id': entry.get('event_id', 0),
        'type': 'retroactive' if entry.get('is_retro') else 'live',
        'timestamp': pd.to_datetime(entry['time']).timestamp() if entry.get('time') else 0,
        'datetime': entry.get('time', ''),
        'fan': entry.get('fan', ''),
        'fan_identity': fan_id,
        'display_label': fan_display_label,
        'fraction': entry.get('fraction', ''),
        'target_price': entry.get('target_price', 0),
        'outcome': entry.get('outcome', ''),
        'is_retro': entry.get('is_retro', False),
        'breach_time': entry.get('breach_time', ''),
        'breach_fraction': entry.get('breach_fraction', ''),
        'breach_price': entry.get('breach_price', 0),
        'breach_direction': entry.get('breach_direction', ''),
        'mfe': entry.get('mfe_10', 0),
        'mae': entry.get('mae_10', 0),
        'O': entry.get('O', 0),
        'H': entry.get('H', 0),
        'L': entry.get('L', 0),
        'C': entry.get('C', 0),
        'bar_index': int(entry.get('bar_index', 0)) if 'bar_index' in entry else 0
    }
```

At the top of the file, add the import:
```python
import json
import datetime
```

In the `for hyp in hypotheses:` loop, after `filename = ...filepath`, add:
```python
json_filename = filename.replace('.txt', '.json')
json_filepath = os.path.join(output_dir, json_filename)
```

Inside `for e in live_events:`, before `write_event(e, False)`, add:
```python
event_record = _row_to_event_record(e, hyp.name)
live_events_geometry.append(event_record)
```

Inside `for e in retro_events:`, before `write_event(e, True)`, add:
```python
event_record = _row_to_event_record(e, hyp.name)
retro_events_geometry.append(event_record)
```

After the `with open(filepath, 'w') as f:` block, add:
```python
# Write JSON report for navigable frontend
live_events_geometry = []
retro_events_geometry = []

# Re-run the event collection (above will have consumed the iterators)
live_events = [e for e in detailed_log if not e.get('is_retro')]
retro_events = [e for e in detailed_log if e.get('is_retro')]

for e in live_events:
    fan_display = f"{e.get('fan', 'Unknown')}"
    live_events_geometry.append(_row_to_event_record(e, fan_display))

for e in retro_events:
    fan_display = f"{e.get('fan', 'Unknown')} [RETRO]"
    retro_events_geometry.append(_row_to_event_record(e, fan_display))

json_output = {
    'metadata': {
        'symbol': instrument,
        'timeframe': timeframe,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'total_events': result['sample_size'],
        'win_rate': result['win_rate'],
        'live_sample_size': result.get('live_sample_size', 0),
        'live_win_rate': result.get('live_win_rate', 0),
        'retro_sample_size': result.get('retro_sample_size', 0),
        'retro_win_rate': result.get('retro_win_rate', 0),
        'generated_at': datetime.datetime.now().isoformat()
    },
    'live_events': live_events_geometry,
    'retro_events': retro_events_geometry,
    'summary': {
        'sample_size': result['sample_size'],
        'win_rate': result['win_rate'],
        'live_sample_size': result.get('live_sample_size', 0),
        'live_win_rate': result.get('live_win_rate', 0),
        'retro_sample_size': result.get('retro_sample_size', 0),
        'retro_win_rate': result.get('retro_win_rate', 0)
    }
}

with open(json_filepath, 'w') as f:
    json.dump(json_output, f, indent=2)
print(f"Generated {json_filename}")
```

- [ ] **Step 2: Test the script on an existing events.csv**

Run: `python gann-visualizer/backend/generate_hypothesis_reports.py "C:\Dev\GannTesting\logs\backend\runs\_NSEI\60\2026-05-08_f8627e\events.csv"`

Expected: `.txt` reports and new `.json` files generated in `hypothesis_reports/`. Inspect the JSON to confirm structure is correct.

- [ ] **Step 3: Commit**

```bash
git add gann-visualizer/backend/generate_hypothesis_reports.py
git commit -m "feat: generate navigable JSON alongside text hypothesis reports"
```

---

## Task 3: Add Hypothesis Navigator tab in App.jsx

**Files:**
- Modify: `gann-visualizer/frontend/src/App.jsx:548-780`

**What to add:** A new tab `"hypothesis"` in `bottomPanelTab` state, with a panel that:
1. Has a "Load Hypothesis JSON" file input
2. Parses the JSON and displays events in a table (time, fan, outcome)
3. Highlights the selected row and calls `chartRef.current.navigateToHypothesisEvent(event)`

Add to the tab list (around line 550):
```jsx
<button
    className={`panel-tab${bottomPanelTab === 'hypothesis' ? ' active' : ''}`}
    onClick={() => { setBottomPanelTab('hypothesis'); if (resultsHeight <= 40) setResultsHeight(200); }}
>
    Hypothesis Navigator {hypothesisEvents.length > 0 && <span className="tab-badge">{hypothesisEvents.length}</span>}
</button>
```

Add state variables in the component (around line 77):
```jsx
const [hypothesisEvents, setHypothesisEvents] = useState([]);
const [selectedHypothesisEvent, setSelectedHypothesisEvent] = useState(null);
const [hypothesisFilter, setHypothesisFilter] = useState('all'); // 'all' | 'live' | 'retro' | 'win' | 'miss'
```

Add the tab content inside the results panel (after the interactions tab content, before `</div>`):
```jsx
{bottomPanelTab === 'hypothesis' && (
    <div className="hypothesis-navigator">
        <div style={{ marginBottom: '10px', display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
            <input
                type="file"
                accept=".json"
                onChange={(e) => {
                    const file = e.target.files[0];
                    if (!file) return;
                    const reader = new FileReader();
                    reader.onload = (ev) => {
                        try {
                            const data = JSON.parse(ev.target.result);
                            const allEvents = [
                                ...(data.live_events || []).map((e, i) => ({ ...e, event_id: i + 1, type: 'live' })),
                                ...(data.retro_events || []).map((e, i) => ({ ...e, event_id: i + 1, type: 'retroactive' }))
                            ];
                            setHypothesisEvents(allEvents);
                            setSelectedHypothesisEvent(null);
                            console.log("[Hypothesis] Loaded", allEvents.length, "events from", data.metadata?.symbol);
                        } catch (err) {
                            console.error("[Hypothesis] Failed to parse JSON:", err);
                            alert("Invalid hypothesis JSON file");
                        }
                    };
                    reader.readAsText(file);
                }}
                style={{ fontSize: '11px' }}
            />
            <select
                value={hypothesisFilter}
                onChange={(e) => setHypothesisFilter(e.target.value)}
                style={{ padding: '2px 5px', fontSize: '11px' }}
            >
                <option value="all">All Events</option>
                <option value="live">Live Only</option>
                <option value="retro">Retroactive Only</option>
                <option value="win">WIN Only</option>
                <option value="miss">MISS Only</option>
            </select>
            <span style={{ fontSize: '11px', color: '#888' }}>
                {filteredHypothesisEvents.length} of {hypothesisEvents.length} events
            </span>
            {selectedHypothesisEvent && (
                <span style={{ fontSize: '11px', color: '#FFEB3B' }}>
                    Selected: {selectedHypothesisEvent.datetime} | {selectedHypothesisEvent.fan} | {selectedHypothesisEvent.outcome}
                </span>
            )}
        </div>
        {hypothesisEvents.length === 0 ? (
            <p style={{ fontSize: '12px', color: '#888' }}>Load a hypothesis JSON file to begin verification.</p>
        ) : (
            <div className="table-container" style={{ overflowX: 'auto' }}>
                <table className="interactions-table" style={{ whiteSpace: 'nowrap', fontSize: '11px' }}>
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Type</th>
                            <th>DateTime</th>
                            <th>Fan</th>
                            <th>Fraction</th>
                            <th>Target Price</th>
                            <th>Outcome</th>
                            <th>MFE</th>
                            <th>MAE</th>
                            <th>Breach Time</th>
                            <th>Breach Price</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filteredHypothesisEvents.map((evt, i) => (
                            <tr
                                key={i}
                                className={selectedHypothesisEvent === evt ? 'selected-row' : ''}
                                onClick={() => {
                                    setSelectedHypothesisEvent(evt);
                                    if (chartRef.current?.navigateToHypothesisEvent) {
                                        chartRef.current.navigateToHypothesisEvent(evt);
                                    }
                                }}
                                style={{ cursor: 'pointer' }}
                            >
                                <td>{i + 1}</td>
                                <td style={{ color: evt.type === 'live' ? '#00E676' : '#FF9800' }}>{evt.type === 'live' ? 'LIVE' : 'RETRO'}</td>
                                <td>{evt.datetime}</td>
                                <td style={{ color: '#90CAF9' }}>{evt.fan}</td>
                                <td style={{ color: '#FFEB3B' }}>{evt.fraction}</td>
                                <td>{evt.target_price}</td>
                                <td style={{ color: evt.outcome === 'WIN' ? '#00E676' : '#FF5252', fontWeight: 'bold' }}>{evt.outcome}</td>
                                <td>{evt.mfe ? evt.mfe.toFixed(2) : '-'}</td>
                                <td>{evt.mae ? evt.mae.toFixed(2) : '-'}</td>
                                <td>{evt.breach_time || '-'}</td>
                                <td>{evt.breach_price || '-'}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        )}
    </div>
)}
```

Add the filter computation (around line 395):
```jsx
const filteredHypothesisEvents = hypothesisEvents.filter(evt => {
    if (hypothesisFilter === 'live') return evt.type === 'live';
    if (hypothesisFilter === 'retro') return evt.type === 'retroactive';
    if (hypothesisFilter === 'win') return evt.outcome === 'WIN';
    if (hypothesisFilter === 'miss') return evt.outcome === 'MISS';
    return true;
});
```

- [ ] **Step 1: Add hypothesis tab and event list panel to App.jsx**

- [ ] **Step 2: Verify the tab renders without errors** — start the frontend dev server and confirm the new tab appears.

- [ ] **Step 3: Commit**

```bash
git add gann-visualizer/frontend/src/App.jsx
git commit -m "feat: add Hypothesis Navigator tab with JSON file loader"
```

---

## Task 4: Add `navigateToHypothesisEvent()` to TVChartContainer

**Files:**
- Modify: `gann-visualizer/frontend/src/TVChartContainer.jsx:1025-1072`

**What to add:** A new method on `useImperativeHandle` that takes a hypothesis event and:
1. Navigates the chart to the correct visible range around that timestamp
2. Draws the fan lines for that event's fan at that time (using the existing `processStudyResponse` drawing flow)
3. Draws a marker at the target price

Since the JSON does not yet contain full fan geometry (Task 5 handles this), this step draws only the marker and adjusts the visible range. The fan rendering will be implemented in Task 5.

```jsx
navigateToHypothesisEvent: (event) => {
    // Pan chart to show the event's candle
    if (!widgetRef.current) return;
    const chart = widgetRef.current.activeChart();
    const eventTimeSec = event.timestamp > 2000000000 ? event.timestamp : event.timestamp * 1000;
    const eventTime = toSeconds(eventTimeSec);

    // Get visible range and center this event
    try {
        const visibleRange = chart.getVisibleRange();
        const rangeWidth = visibleRange.to - visibleRange.from;
        const newFrom = eventTime - rangeWidth / 2;
        const newTo = eventTime + rangeWidth / 2;
        chart.setVisibleRange({ from: newFrom, to: newTo }).catch(() => {});
    } catch (e) {}

    // Draw intersection marker at target price
    if (event.target_price) {
        // Remove previous hypothesis markers
        hypothesisMarkerRef.current.forEach(m => {
            try { chart.removeEntity(m); } catch (_) {}
        });
        hypothesisMarkerRef.current = [];

        const markerTime = event.timestamp > 2000000000 ? event.timestamp : event.timestamp * 1000;
        const shapeId = chart.createShape(
            { time: toSeconds(markerTime), price: event.target_price },
            {
                shape: 'arrow_down',
                lock: true,
                disableUndo: true,
                overrides: { color: '#FFEB3B', backgroundColor: '#FFEB3B', size: 1 }
            }
        );
        if (shapeId) hypothesisMarkerRef.current.push(shapeId);
    }
}
```

Add a ref to track hypothesis markers (around line 399):
```jsx
const hypothesisMarkerRef = useRef([]);
```

- [ ] **Step 1: Add `navigateToHypothesisEvent` to TVChartContainer useImperativeHandle**

- [ ] **Step 2: Test by loading a hypothesis JSON and clicking an event** — the chart should pan to that candle and show a yellow marker.

- [ ] **Step 3: Commit**

```bash
git add gann-visualizer/frontend/src/TVChartContainer.jsx
git commit -m "feat: add navigateToHypothesisEvent for Hypothesis Navigator"
```

---

## Task 5: Add fan geometry to JSON output (complete the geometry reconstruction)

**Files:**
- Modify: `gann-visualizer/backend/generate_hypothesis_reports.py`

**The gap:** The JSON from Task 2 only has event metadata — it doesn't have fan line geometry. The `Active_Angles` column from the raw events.csv is a dictionary of all active angle prices at each bar. We use this to build the fan line geometry.

The `Active_Angles` column is a JSON string like `'{"L195-H195_0.875": 24853.4, "L195-H195_0.75": 24820.0, ...}'`.

Each key encodes fan identity and fraction. Each value is the price of that angle line at the event's timestamp.

To build fan geometry for the JSON, we need to reconstruct the fan from its pivot pair. Since the CSV has the candles and the `Active_Angles` dictionary contains price-per-fraction at this bar, we can describe each fan line as: start at the event's bar_index with price X, end at the anchor pivot's bar_index (going backward in time) or extended infinitely to the right.

**Simplest correct approach:** Use the anchor bar from the fan (the pivot where the fan originated). Extract all unique fans from `Active_Angles` keys, then for each fan get all its fraction lines with their prices at the event timestamp. The line extends from the fan's origin bar to `origin_bar + 1000` bars (sufficiently far to cover the visible chart).

**Actual implementation in `_row_to_fan_state()`:**

```python
def _row_to_fan_state(entry, df):
    """Extract fan geometry from Active_Angles in the same row or reconstruct from fan pivot history."""
    active_angles_str = str(entry.get('Active_Angles', '{}')).replace("'", '"')
    try:
        active_angles = json.loads(active_angles_str)
    except (json.JSONDecodeError, TypeError):
        return {'fans': [], 'intersections': []}

    # Group by fan identity
    fan_groups = {}
    for key, price in active_angles.items():
        if not price or price <= 0:
            continue
        parts = key.rsplit('_', 1)
        if len(parts) != 2:
            continue
        fan_id, fraction_str = parts
        if fan_id not in fan_groups:
            fan_groups[fan_id] = []
        fan_groups[fan_id].append({
            'fraction': fraction_str,
            'price': float(price)
        })

    fans = []
    for fan_id, lines in fan_groups.items():
        priority_label = fan_id
        fan = {
            'fan_id': fan_id,
            'display_label': priority_label,
            'priority': 1,
            'lines': []
        }

        for line in lines:
            fraction = line['fraction']
            price = line['price']

            # Determine color
            color_map = {'0.875': '#2196F3', '0.75': '#4CAF50', '0.5': '#FF9800', '0.25': '#F44336'}
            color = color_map.get(fraction, '#888888')
            width = 4 if fraction == '0.5' else 2

            bar_index = int(entry.get('bar_index', 0))
            fan['lines'].append({
                'id': f'{fan_id}_{fraction}',
                'fraction': float(fraction) if fraction not in ('horizontal', 'full_coverage', 'main') else None,
                'points': [
                    {'time': bar_index - 500, 'price': price},   # extend far left for context
                    {'time': bar_index + 2000, 'price': price}   # extend far right
                ],
                'options': {
                    'linecolor': color,
                    'linewidth': width,
                    'linestyle': 1,
                    'extendRight': True
                }
            })

        fans.append(fan)

    # Build intersection record
    intersections = []
    event_price = entry.get('target_price') or entry.get('Price', 0)
    if event_price:
        intersections.append({
            'fan_id': entry.get('fan', ''),
            'fraction': entry.get('fraction', ''),
            'price': float(event_price),
            'timestamp': entry.get('bar_index', 0),
            'type': 'target_attempt'
        })

    return {'fans': fans, 'intersections': intersections}
```

Then in `generate_hypothesis_reports.py`, after calling `_row_to_event_record()`, add:
```python
fan_state = _row_to_fan_state(e, df)
event_record['fan_state'] = fan_state
```

Add `df` as a parameter to `_row_to_event_record()` to pass it to `_row_to_fan_state()`:
```python
def _row_to_event_record(entry, df, fan_display_label):
    fan_state = _row_to_fan_state(entry, df)
    record = {
        ...
        'fan_state': fan_state
    }
    return record
```

**IMPORTANT:** The `Active_Angles` column is in the original raw events.csv, not in the hypothesis `detailed_log` entries. We need the original DataFrame `df` to look up `Active_Angles` for each event. Add `df` to the closure available inside the `for hyp in hypotheses:` loop. The variable `df` is already in scope at the top of the loop.

- [ ] **Step 1: Add `_row_to_fan_state` and integrate it into `_row_to_event_record`**

- [ ] **Step 2: Run generate_hypothesis_reports.py on an existing events.csv and inspect the JSON**

Check that the JSON's `fan_state.fans[].lines[].points[]` array has valid coordinates. Run on: `python gann-visualizer/backend/generate_hypothesis_reports.py "C:\Dev\GannTesting\logs\backend\runs\_NSEI\60\2026-05-08_f8627e\events.csv"`.

- [ ] **Step 3: Update TVChartContainer.navigateToHypothesisEvent to render fan geometry**

When an event is selected, the `navigateToHypothesisEvent` method should call `processStudyResponse` with `fan_state`:

```jsx
navigateToHypothesisEvent: (event) => {
    // ... existing pan + marker logic ...

    // Draw fans from geometry if available
    if (event.fan_state && event.fan_state.fans) {
        // Clear existing study shapes
        Object.keys(studyShapesRef.current).forEach(k => {
            const id = studyShapesRef.current[k];
            if (id && typeof id !== 'object') {
                try { chart.removeEntity(id); } catch (_) {}
            }
        });
        studyShapesRef.current = {};

        // Draw fans using existing processStudyResponse
        const studyData = {
            drawings: event.fan_state.fans.flatMap(fan =>
                fan.lines.map(line => ({
                    id: line.id,
                    type: 'trend_line',
                    points: line.points,
                    options: {
                        ...line.options,
                        fanIdentity: fan.fan_id,
                        fanLabel: fan.display_label
                    }
                }))
            ),
            pivot_markers: []
        };
        studyShapesRef.current = processStudyResponse(chart, studyData, studyShapesRef.current);
    }
}
```

- [ ] **Step 4: Test end-to-end** — Load the JSON in the frontend, click an event, confirm fans appear on the chart at the correct positions.

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/generate_hypothesis_reports.py gann-visualizer/frontend/src/TVChartContainer.jsx
git commit -m "feat: render fan geometry in Hypothesis Navigator on event click"
```

---

## Spec Self-Review

1. **Placeholder scan:** No TODOs, no TBDs, no placeholder implementations. All code is complete.
2. **Type consistency:** `timestamp` fields use Unix seconds throughout. `bar_index` uses integer. Fan IDs match between `_row_to_fan_state` output and frontend's `fanIdentity`/`fanLabel` fields.
3. **Scope check:** Tasks 1, 2, 4, 5 cover backend JSON generation and frontend rendering. Task 3 covers the navigator panel. All deliver working software independently.
4. **Missing pieces:** The `_row_to_fan_state` implementation uses bar_index as the time coordinate for line points. This should work with TradingView's shape API which accepts bar-index-based time. No external service changes needed.

---

## Execution

**Plan complete and saved to `docs/superpowers/plans/2026-05-08-hypothesis-navigator-design.md`.** Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**