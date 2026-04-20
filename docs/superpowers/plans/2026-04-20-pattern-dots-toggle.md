# Pattern Dots Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a toggle switch to show/hide candle pattern circles (triangle-down icons above candle highs) in the toolbar pivot settings area.

**Architecture:** Add state in App.jsx for `showPatternDots` (default false). Pass as prop to TVChartContainer. In TVChartContainer, store shape IDs in patternMarkersRef and toggle visibility via `setProperties({ visible: true/false })` when prop changes.

**Tech Stack:** React state, TradingView Charting Library shapes API

---

## Task 1: Add showPatternDots state to App.jsx

**Files:**
- Modify: `gann-visualizer/frontend/src/App.jsx:51`

- [ ] **Step 1: Add state declaration after showIntersectionLabels**

Find line 51 which has:
```jsx
const [showIntersectionLabels, setShowIntersectionLabels] = useState(false)
```

Add after it:
```jsx
const [showPatternDots, setShowPatternDots] = useState(false)
```

- [ ] **Step 2: Commit**

```bash
git add gann-visualizer/frontend/src/App.jsx
git commit -m "feat: add showPatternDots state (default false)"
```

---

## Task 2: Add checkbox toggle UI in App.jsx pivot settings area

**Files:**
- Modify: `gann-visualizer/frontend/src/App.jsx:451-456`

- [ ] **Step 1: Add checkbox after Show Intersections label**

Find lines 450-456:
```jsx
                            {strategy === 'angular_coverage' && (
                                <label title="Draw text labels showing hit prices on intersections" style={{ display: 'flex', alignItems: 'center' }}>
                                    <input type="checkbox"
                                        checked={showIntersectionLabels}
                                        onChange={(e) => setShowIntersectionLabels(e.target.checked)}
                                    /> Show Intersections
                                </label>
                            )}
```

Add after the closing of this block (after line 456):
```jsx
                                <label title="Show candle pattern circles above/below candles" style={{ display: 'flex', alignItems: 'center' }}>
                                    <input type="checkbox"
                                        checked={showPatternDots}
                                        onChange={(e) => setShowPatternDots(e.target.checked)}
                                    /> Show Patterns
                                </label>
```

- [ ] **Step 2: Commit**

```bash
git add gann-visualizer/frontend/src/App.jsx
git commit -m "feat: add Show Patterns checkbox toggle in toolbar"
```

---

## Task 3: Pass showPatternDots prop to TVChartContainer

**Files:**
- Modify: `gann-visualizer/frontend/src/App.jsx:515`

- [ ] **Step 1: Add showPatternDots prop to TVChartContainer**

Find line 515:
```jsx
                        showPatternLegend={strategy === 'angular_coverage'}
```

Add after it:
```jsx
                        showPatternDots={showPatternDots}
```

- [ ] **Step 2: Commit**

```bash
git add gann-visualizer/frontend/src/App.jsx
git commit -m "feat: pass showPatternDots prop to TVChartContainer"
```

---

## Task 4: Accept showPatternDots prop in TVChartContainer

**Files:**
- Modify: `gann-visualizer/frontend/src/TVChartContainer.jsx:5`

- [ ] **Step 1: Add showPatternDots to destructured props**

Find line 5:
```jsx
export const TVChartContainer = forwardRef(({ symbol = 'NIFTY 50', datafeedUrl, interval = '60', onTradeLogged, dataSource = 'dhan', cycleType = '24_hour', sessionDuration = 'standard', onSymbolChange, onPlayingStateChange, selectedInteraction, showPatternLegend = false, ...props }, ref) => {
```

Add `showPatternDots = false` to the destructured props:
```jsx
export const TVChartContainer = forwardRef(({ symbol = 'NIFTY 50', datafeedUrl, interval = '60', onTradeLogged, dataSource = 'dhan', cycleType = '24_hour', sessionDuration = 'standard', onSymbolChange, onPlayingStateChange, selectedInteraction, showPatternLegend = false, showPatternDots = false, ...props }, ref) => {
```

- [ ] **Step 2: Commit**

```bash
git add gann-visualizer/frontend/src/TVChartContainer.jsx
git commit -m "feat: accept showPatternDots prop in TVChartContainer"
```

---

## Task 5: Add useEffect to toggle pattern dot visibility

**Files:**
- Modify: `gann-visualizer/frontend/src/TVChartContainer.jsx` (after line 666 where patternMarkersRef is defined)

- [ ] **Step 1: Add useEffect to handle show/hide**

Find line 666:
```jsx
    const patternMarkersRef = useRef({});
```

Add after the closing of the block that contains it (look for the next function or comment), or right after the `patternMarkersRef` declaration line. Add this useEffect:

```jsx
    // Handle pattern dots visibility toggle
    useEffect(() => {
        if (!widgetRef.current) return;

        const chart = widgetRef.current.activeChart();
        if (!chart) return;

        // Iterate all pattern markers and toggle visibility
        const buckets = patternMarkersRef.current;
        Object.keys(buckets).forEach(bucketKey => {
            const markers = buckets[bucketKey];
            markers.forEach(marker => {
                if (marker.shapeId) {
                    try {
                        const shape = chart.getShapeById(marker.shapeId);
                        if (shape) {
                            shape.setProperties({ visible: showPatternDots });
                        }
                    } catch (e) {
                        // Shape may have been removed, ignore
                    }
                }
            });
        });
    }, [showPatternDots]);
```

- [ ] **Step 2: Commit**

```bash
git add gann-visualizer/frontend/src/TVChartContainer.jsx
git commit -m "feat: add useEffect to toggle pattern dots visibility"
```

---

## Self-Review Checklist

1. **Spec coverage:**
   - [x] State added in App.jsx (Task 1)
   - [x] Checkbox toggle UI added (Task 2)
   - [x] Prop passed to TVChartContainer (Task 3)
   - [x] Prop accepted in TVChartContainer (Task 4)
   - [x] Visibility toggle logic implemented (Task 5)

2. **Placeholder scan:** No TODOs, no TBDs, all code is complete

3. **Type consistency:** `showPatternDots` used consistently throughout, `patternMarkersRef` structure matches existing code (`{ price, time, pattern, shapeId }`)

---

**Plan complete.** Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
