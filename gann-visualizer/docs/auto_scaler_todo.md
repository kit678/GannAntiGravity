# Auto-Scaler Todo
The visualization engine uses a `PriceToBarRatio` variable within TradingView logic (`TVChartContainer`) to dictate visual arc geometry (radius matching and line slopes). Currently, it sits at a hard constraint base of `5.5`.

A fixed proportion will cause geometric clipping on low-priced assets (or dynamically compressed asset ranges over tight timelines) since angle limits flatten out. 

## Requirements
To prevent manually needing to guess whether the scale ratio must be lowered to `.55` or raised to `55` based on what ticket is loaded, we need an auto-scaler in `TVChartContainer.jsx * onSymbolChanged()`.

1. **Price Detection**: Grab the initial starting price for the loaded ticker once the resolution has rendered.
2. **Order of Magnitude Matcher**: Align the `5.5` scaler base to the target asset.
   - Example scaling (Need to fine-tune based on mathematical range bounds):
      - Indices like NIFTY (`~24000`) -> use `5.5` 
      - Heavy equites (`$200` AAPL) -> use `.55` 
      - Tight equities (`$15` ABC) -> use `.055`
3. Automatically execute and store the result via `chartWidget.activeChart().setPriceToBarRatio()`.

Doing so dynamically calculates how much price width spans a single bar, keeping 1/8th Gann fraction lines mathematically robust to span the physical view correctly.
