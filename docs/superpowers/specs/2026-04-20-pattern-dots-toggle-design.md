# Pattern Dots Toggle - Design Spec

## Overview

Add a toggle switch to show/hide candle pattern circles (triangle-down icons above candle highs). The toggle appears in the toolbar within the pivot settings area.

## Feature Details

### Placement
- Located in the pivot settings area, alongside `showIntersectionLabels` checkbox
- Only visible when `strategy === 'angular_coverage'` or `strategy === 'pivot_points_only'`

### Behavior
- **Default state:** OFF (hidden)
- **Toggle ON:** Pattern circles become visible
- **Toggle OFF:** Pattern circles become invisible immediately

### Technical Implementation

#### UI (App.jsx)
1. Add state: `const [showPatternDots, setShowPatternDots] = useState(false)`
2. Add checkbox in pivot settings area:
```jsx
<label title="Show candle pattern circles above/below candles" style={{ display: 'flex', alignItems: 'center' }}>
    <input type="checkbox"
        checked={showPatternDots}
        onChange={(e) => setShowPatternDots(e.target.checked)}
    /> Show Patterns
</label>
```
3. Pass prop to TVChartContainer: `showPatternDots={showPatternDots}`

#### Logic (TVChartContainer.jsx)
1. Add prop: `showPatternDots = false`
2. Store pattern marker IDs in `patternMarkersRef` when created
3. When `showPatternDots` changes:
   - If OFF: iterate all stored markers and call `shape.setProperties({ visible: false })`
   - If ON: call `shape.setProperties({ visible: true })`

#### Pattern Marker Tracking
- Pattern markers are stored in `patternMarkersRef` with structure: `{ price, time, pattern, shapeId }`
- When `plotPatternLabel` creates a shape, it pushes the marker with shapeId
- Use `chart.getShapeById(id)` to get the shape, then `setProperties({ visible: false/true })`

## Files to Modify

1. **gann-visualizer/frontend/src/App.jsx**
   - Add `showPatternDots` state (default: false)
   - Add checkbox toggle UI in pivot settings section
   - Pass `showPatternDots` prop to TVChartContainer

2. **gann-visualizer/frontend/src/TVChartContainer.jsx**
   - Accept `showPatternDots` prop
   - Add `useEffect` to handle show/hide when prop changes
   - Use `chart.getShapeById(id).setProperties({ visible: false/true })`

## Design Notes

- Uses same pattern as TradingView drawings panel visibility toggle
- Shapes are not deleted, just hidden/shown — toggling back on immediately reveals them
- No need to track new state for visibility; can infer from `showPatternDots` prop value
