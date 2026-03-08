# Dynamic Auto-Scaling (TODO)

## Context
When an asset operates at vastly different scale limits (such as Nifty50 at ₹24000+, versus AAPL at $250, versus penny stocks < $10), relying on a static geometric calculation for trend angles results in severe "clipping". 
The default `setPriceToBarRatio()` dictates how much price change constitutes "one geometry unit" on the grid. 

## The Core Interaction
Our Angle Engine algorithm physically plots circles behind the scenes (spanning Price × Time), assigning arcs across that defined radius limits to map Gan fan fractional lines.

- A ratio of `5.5` means 5.5 decimal points fits into 1 horizontal bar unit.
- If $AAPL moves 5 points over an entire month, the Angle Engine physically equates that to "less than shifting 1 grid block", causing absolute flatness to line paths. 
- Meanwhile, an equivalent NIFTY swing moving 900+ points translates accurately and extends the angles aggressively spanning visually beautifully. 

## The Fix: Dynamic Scaling Engine
To support auto-mapping geometry reliably, without user input:

We need to implement logic running upon a TradingView chart rehydrating and locking into a new ticker symbol or a dramatically new timeframe window.

1. **Trigger Phase:** Catch `widget.activeChart().onSymbolChanged().subscribe()`.
2. **Detection Phase:** Identify the new active asset's most recent "close price", or rely on `symbolInfo.pricescale`.
3. **Multiplier Lookup:** 
    * Provide `5.5` scaler for values inside bounds e.g `> $5,000`
    * Provide `0.55` scaler for values e.g `$500 -> $5,000`
    * Provide `0.055` scaler for equity ` < $500 ` etc.
4. **Implementation Phase:** Inject value into visual engine by forcing  `widget.activeChart().setPriceToBarRatio(newScaler)`.
