# Trade Marker Alignment Design Spec

## 1. Overview
Currently, entry and exit trades are marked on the TradingView chart using `text` shapes containing "E" and "X". Due to TradingView's anchor behaviors, text labels align their left edge to the target time coordinate, causing the markers to render to the right of the intended candle. This makes them visually misleading.

This design replaces the floating text labels with short, precisely aligned vertical lines drawn directly above or below the entry/exit candles.

## 2. Implementation Approach
We will modify the `plotTradeShape` and `plotSingleTradeMarker` functions in `TVChartContainer.jsx`.

### 2.1 Shape Replacement
Instead of `shape: 'text'`, we will use `shape: 'trend_line'` via `createMultipointShape`. 
By passing an array of two points with the exact same `time` but slightly different `price` values, we create a perfectly vertical line segment that is immune to horizontal alignment drift.

### 2.2 Coordinate Calculation
To ensure the markers scale naturally with chart zoom and volatility, we will calculate the line length and gap based on the specific candle's price range.

**For a Long Entry or Short Exit (Marker Below Candle):**
- Point 1 (Top of line): `candle_low - (candle_range * 0.2)`
- Point 2 (Bottom of line): `candle_low - (candle_range * 0.6)`

**For a Short Entry or Long Exit (Marker Above Candle):**
- Point 1 (Bottom of line): `candle_high + (candle_range * 0.2)`
- Point 2 (Top of line): `candle_high + (candle_range * 0.6)`

*Fallback Logic:* If the specific candle isn't loaded in the chart data at the time of drawing, we will fall back to using a fixed percentage of the trade price (e.g., gap = `price * 0.002`, length = `price * 0.004`).

### 2.3 Styling
- **Entry Markers:** Green color (`#00C853`), Line Width 3, `disableUndo: true`, `lock: true`.
- **Exit Markers:** Gray color (`#9E9E9E`), Line Width 3, `disableUndo: true`, `lock: true`.

## 3. Data Structure Updates
The internal data passed to `plotTradeShape` will be updated to support multipoint coordinates.
Currently, the trade object looks like:
```javascript
const entryMarker = {
    time: entryTime,
    type: 'entry',
    price: entryPrice,
    label: 'E',
};
```
We will modify this to supply `price1` and `price2`:
```javascript
const entryMarker = {
    time: entryTime,
    type: 'entry',
    price1: startPrice,
    price2: endPrice,
};
```
And `plotTradeShape` will map these to `[{ time, price: price1 }, { time, price: price2 }]`.

## 4. Considerations
- The line length (0.4x candle range) and gap (0.2x candle range) are starting defaults. They may be slightly tweaked during implementation if they appear too long or too short against the live chart.
- By using `trend_line`, we inherently avoid the TradingView `arrow_up`/`arrow_down` shapes that are currently reserved for pivot (pattern) dots, preserving clear visual distinction between pivots and trades.