# TradingView Advanced Charting Library - Coding Standards

**Version**: 1.0  
**Date**: 2026-01-09  
**Reference**: TradingView Charting Library Documentation v28+

---

## Table of Contents

1. [Overview](#overview)
2. [Datafeed Implementation](#datafeed-implementation)
3. [Time and Timestamps](#time-and-timestamps)
4. [Shape and Drawing API](#shape-and-drawing-api)
5. [Chart Methods Best Practices](#chart-methods-best-practices)
6. [Custom Replay Implementation](#custom-replay-implementation)
7. [Error Handling](#error-handling)
8. [Performance Guidelines](#performance-guidelines)

---

## Overview

This document establishes coding standards for working with TradingView's Advanced Charting Library in our Gann Visual Backtester project.

### Key Principles

1. **Data Accuracy First** - Most issues with the library appear because data is provided incorrectly
2. **Respect Unsupported Features** - Bar Replay Tool is officially unsupported; our workaround has limitations
3. **Use Documented APIs** - Undocumented features may change without notice
4. **Enable Debug Mode During Development** - Set `debug: true` in Widget Constructor

### Unsupported Features (Do NOT Rely On)

Per TradingView documentation, these are **not supported**:
- Pine Script®
- Alerts
- **Bar Replay Tool** (our custom implementation is a workaround)
- Range Bars
- Strategy Tester
- Patterns

---

## Datafeed Implementation

### 1. UDF Endpoints

Our backend provides these UDF-compliant endpoints:

| Endpoint | Purpose | Returns |
|----------|---------|---------|
| `/config` | Library configuration | Supported resolutions, features |
| `/search` | Symbol search | Array of symbol objects |
| `/symbols` | Symbol info | Symbol metadata (pricescale, session, etc.) |
| `/history` | Historical bars | OHLCV data in UDF format |
| `/time` | Server time | Unix timestamp |

### 2. getBars Response Format

```javascript
// CORRECT: UDF history response format
return {
    "s": "ok",          // Status: "ok", "no_data", "error"
    "t": [timestamps],  // Array of Unix timestamps (SECONDS)
    "o": [opens],       // Array of open prices
    "h": [highs],       // Array of high prices
    "l": [lows],        // Array of low prices
    "c": [closes],      // Array of close prices
    "v": [volumes],     // Array of volumes (optional)
}
```

### 3. noData Flag Usage

```javascript
// When there's no more historical data available
onHistoryCallback([], { noData: true });

// When returning data but more may exist
onHistoryCallback(bars, { noData: false });

// CRITICAL: Don't return noData:true for gaps in data
// This stops TradingView from requesting more history
```

### 4. Custom Datafeed Wrapper Pattern

```javascript
class ChartDatafeed {
    constructor(originalDatafeed) {
        this.originalDatafeed = originalDatafeed;
        this.isCustomMode = false;
        this.customData = [];
    }

    getBars(symbolInfo, resolution, periodParams, onHistoryCallback, onErrorCallback) {
        if (this.isCustomMode) {
            // Serve custom data
            const bars = this.customData.slice(0, this.currentStep + 1);
            onHistoryCallback(bars, { noData: false });
            return;
        }
        
        // Delegate to original datafeed
        return this.originalDatafeed.getBars(/* ... */);
    }
}
```

---

## Time and Timestamps

### 1. Timestamp Format

**TradingView uses Unix timestamps in SECONDS**, not milliseconds.

```javascript
// CORRECT: Convert milliseconds to seconds
const shapeTime = Math.floor(tradeTimeMs / 1000);

// Helper functions
const toSeconds = (t) => String(t).length > 10 ? Math.floor(t / 1000) : t;
const toMilliseconds = (t) => String(t).length <= 10 ? t * 1000 : t;
```

### 2. Timezone Handling

```javascript
// Set timezone in Widget Constructor
const widget = new TradingView.widget({
    timezone: 'Asia/Kolkata',  // Explicit timezone for Dhan data
    // ...
});
```

### 3. Date Filtering in Backend

```python
# Use IST timezone for Dhan data filtering
import pytz
ist = pytz.timezone('Asia/Kolkata')

from_dt = ist.localize(datetime.strptime(req.from_date, "%Y-%m-%d"))
from_ts = int(from_dt.timestamp())
```

---

## Shape and Drawing API

### 1. createShape Method

```javascript
// Creating a single-point shape (arrow, icon, etc.)
chart.createShape(
    { time: 1514764800, price: 24000 },  // Point (time in SECONDS)
    {
        shape: 'arrow_up',  // Shape type
        overrides: {
            color: '#00E676',
            size: 1  // Numeric: 1 (smallest) to 4 (largest)
        }
    }
);
```

**Important**: `createShape` returns a **Promise** (since v29). Handle accordingly:

```javascript
const shapeId = await chart.createShape(point, options);
// Or with .then()
chart.createShape(point, options).then(id => console.log('Created:', id));
```

### 2. Available Single-Point Shapes

- `arrow_up`, `arrow_down` - Trade markers
- `vertical_line`, `horizontal_line` - Reference lines
- `icon` - Custom FontAwesome icons
- `flag`, `label` - Annotations

### 3. createMultipointShape Method

```javascript
// Creating a trend line (2 points)
chart.createMultipointShape(
    [
        { time: 1514764800, price: 24000 },
        { time: 1514851200, price: 24500 }
    ],
    {
        shape: 'trend_line',
        overrides: {
            linecolor: '#FF5252',
            linewidth: 2
        }
    }
);
```

### 4. Execution Shapes for Trading

```javascript
// Use createExecutionShape for buy/sell markers
const execution = chart.createExecutionShape()
    .setTime(timestamp)        // Unix timestamp in seconds
    .setPrice(price)
    .setDirection('buy')       // 'buy' or 'sell'
    .setArrowColor('#00E676')
    .setText('Buy Signal');
```

### 5. Removing Shapes

```javascript
// Remove all shapes
chart.removeAllShapes();

// Remove specific shape by ID
chart.removeEntity(shapeId);
```

---

## Chart Methods Best Practices

### 1. Chart Ready Pattern

Always wait for chart to be ready before making API calls:

```javascript
widget.onChartReady(() => {
    const chart = widget.activeChart();
    // Now safe to call chart methods
});
```

### 2. Data Ready Pattern

Wait for data to load before plotting markers:

```javascript
chart.dataReady(() => {
    console.log('Data is loaded, safe to plot markers');
    plotTradeMarkers(trades);
});
```

### 3. setVisibleRange

```javascript
// Set visible time range
chart.setVisibleRange({
    from: startTimeSeconds,
    to: endTimeSeconds + (30 * 60)  // Add buffer
}).then(() => {
    console.log('Range set successfully');
}).catch(err => {
    console.error('setVisibleRange failed:', err);
});
```

### 4. resetData and resetCache

```javascript
// When historical data changes, reset cache first
widget.resetCache();  // Clear datafeed cache globally
chart.resetData();    // Trigger re-fetch of data

// IMPORTANT: resetData only requests visible range by default (v27+)
// Use featureset 'request_only_visible_range_on_reset' to change this
```

### 5. Resolution Changes

```javascript
// Subscribe to resolution changes
chart.onIntervalChanged().subscribe(null, () => {
    widget.resetCache();
    chart.resetData();
});

// Set resolution programmatically
chart.setResolution('1', () => {
    console.log('Resolution changed to 1-minute');
});
```

---

## Custom Replay Implementation

Since Bar Replay is **not supported** in Advanced Charts, we use a custom workaround.

### 1. Architecture

```
┌─────────────────────────────────────────┐
│  ChartDatafeed (wrapper)                │
│  - Stores all candles in buffer         │
│  - Controls currentStep index           │
│  - Manages subscriber notifications     │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  playback_step()                        │
│  1. Increment currentStep               │
│  2. Call resetCache() + resetData()     │
│  3. Notify subscribers                  │
│  4. Evaluate strategy at step           │
└─────────────────────────────────────────┘
```

### 2. Key Patterns

```javascript
// Step 1: Load all candles
setProgressiveReplayData(candles, strategy, ...) {
    this.customData = candles;
    this.currentStep = replayStartIndex;
    this.isCustomMode = true;
    
    chart.resetData();  // Trigger initial render
}

// Step 2: Advance playback
playback_step() {
    if (this.currentStep >= this.customData.length - 1) {
        this.playback_stop();
        return;
    }
    
    this.currentStep++;
    
    // Force chart update
    window.tvWidget.resetCache();
    chart.resetData();
    
    // Notify subscribers
    Object.values(this.subscribers).forEach(sub => {
        sub.callback(this.customData[this.currentStep]);
    });
}
```

### 3. Limitations

- Full chart re-render on each step (performance cost)
- Not suitable for very large datasets (10k+ bars)
- Custom implementation may break with library updates
- Shapes must be re-plotted after resetData

---

## Error Handling

### 1. createShape Error Handling

```javascript
try {
    const shapeId = await chart.createShape(point, options);
    console.log('Shape created:', shapeId);
} catch (err) {
    console.error('createShape failed:', err.message);
    // Common causes:
    // - Invalid time (no bar at that timestamp)
    // - Invalid price (outside visible range)
    // - Chart not ready
}
```

### 2. Time Violation Errors

```
Error: putToCacheNewBar: time violation
```

This occurs when you try to update historical data via subscribeBars callback.

**Solution**: Use `resetCache()` + `resetData()` instead.

### 3. Debug Mode

```javascript
const widget = new TradingView.widget({
    debug: true,  // Enable detailed console logging
    // ...
});
```

---

## Performance Guidelines

### 1. Limit Data Per Request

```python
# Backend: Limit bars per request to prevent timeouts
MAX_BARS_PER_REQUEST = 2000

# Different limits per resolution
LIMITS = {
    '1': 7,      # 1-min: ~5-7 trading days
    '5': 30,     # 5-min: ~25 trading days
    '15': 80,    # 15-min: ~60 trading days
    '60': 300,   # 60-min: ~250 trading days
    'D': 3000    # Daily: ~7 years
}
```

### 2. Marker Plotting Optimization

```javascript
// Batch marker plotting
const trades = [...];
const batchSize = 50;

for (let i = 0; i < trades.length; i += batchSize) {
    const batch = trades.slice(i, i + batchSize);
    batch.forEach(t => plotTradeShape(chart, t));
    
    // Small delay between batches for UI responsiveness
    await new Promise(r => setTimeout(r, 10));
}
```

### 3. Deduplication

```javascript
// Prevent duplicate markers
const plottedTrades = new Set();

function plotTradeShape(chart, trade) {
    const key = `${trade.time}_${trade.type}_${trade.price}`;
    if (plottedTrades.has(key)) return false;
    
    plottedTrades.add(key);
    // ... plot logic
}
```

### 4. Clean Up on Mode Exit

```javascript
function exitCustomMode() {
    this.playback_stop();
    this.isCustomMode = false;
    this.customData = [];
    this.subscribers = {};
    
    // Reset to normal data flow
    chart.setSymbol(currentSymbol, currentResolution);
}
```

---

## Quick Reference

### Widget Constructor Essential Options

```javascript
const widget = new TradingView.widget({
    symbol: 'NIFTY 50',
    interval: '1',
    timezone: 'Asia/Kolkata',
    container: containerRef,
    datafeed: customDatafeed,
    library_path: '/charting_library/',
    locale: 'en',
    theme: 'Dark',
    autosize: true,
    debug: process.env.NODE_ENV !== 'production',
    
    // Performance options
    time_scale: {
        right_offset: 5  // Limit future whitespace
    },
    
    // Feature toggles
    disabled_features: [
        'use_localstorage_for_settings',
        'header_compare'
    ],
    enabled_features: [
        'study_templates',
        'header_symbol_search'
    ]
});
```

### Common Method Signatures

| Method | Returns | Notes |
|--------|---------|-------|
| `createShape(point, options)` | `Promise<EntityId>` | Single-point drawings |
| `createMultipointShape(points, options)` | `Promise<EntityId>` | Multi-point drawings |
| `setVisibleRange({from, to})` | `Promise<void>` | Set time range |
| `removeAllShapes()` | `void` | Clear all drawings |
| `resetData()` | `void` | Re-fetch chart data |
| `dataReady(callback)` | `void` | Wait for data load |

---

## References

- TradingView Charting Library Documentation: `/docs/tradingvew_advanced_charting_library/TradingView_Charting_Library_Docs.md`
- Datafeed API: Lines 4800-5000
- Drawings API: Lines 15050-15200
- Chart Methods: Lines 13500-13550
- Unsupported Features: Lines 596-607
