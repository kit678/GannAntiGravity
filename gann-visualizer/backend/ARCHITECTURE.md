# Backtesting Architecture - Separation of Concerns

This document explains the refactored backtesting architecture that properly separates strategy logic from execution logic.

## Overview

The codebase now follows a clean separation between:
1. **Strategy Layer** - Generates buy/sell signals
2. **Execution Layer** - Handles position management, P&L calculation, and trade execution
3. **API Layer** - Routes requests and coordinates components

## Architecture Diagram

```
┌─────────────────────────────────────────────┐
│  STRATEGY LAYER (strategies.py)            │
│  - Pure signal generation                   │
│  - Analyzes market data                     │
│  - Returns buy/sell signals                 │
│  - NO position tracking                     │
│  - NO P&L calculation                       │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  BACKTESTING ENGINE (backtest_engine.py)   │
│  - Consumes strategy signals                │
│  - Manages positions (open/close)           │
│  - Calculates P&L                           │
│  - Tracks metrics                           │
│  - Strategy-agnostic execution              │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  API LAYER (main.py)                       │
│  - FastAPI endpoints                        │
│  - Coordinates strategy + engine            │
│  - Returns results to frontend              │
└─────────────────────────────────────────────┘
```

## Key Components

### 1. Base Strategy Interface (`base_strategy.py`)

All strategies inherit from `BaseStrategy` which defines:
- `generate_signals()` - Returns DataFrame with buy/sell signals
- `get_strategy_name()` - Returns strategy name
- Input validation and data preprocessing

**Key Principle**: Strategies only analyze data and generate signals. They don't track positions or calculate P&L.

### 2. Strategy Implementations (`strategies.py`)

Current strategies:
- `Mechanical3DaySwingStrategy` - Donchian breakout
- `SquareOf9ReversionStrategy` - Gann levels support/resistance
- `TimeCycleBreakoutStrategy` - Placeholder for time cycle analysis

**Adding a new strategy**:
```python
from base_strategy import BaseStrategy, SignalType

class MyCustomStrategy(BaseStrategy):
    def get_strategy_name(self) -> str:
        return "My Custom Strategy"
    
    def generate_signals(self) -> pd.DataFrame:
        df = self.df.copy()
        
        # Your analysis logic here
        for i in range(len(df)):
            if your_buy_condition:
                df.loc[df.index[i], 'signal'] = SignalType.BUY
                df.loc[df.index[i], 'signal_label'] = 'Buy reason'
            elif your_sell_condition:
                df.loc[df.index[i], 'signal'] = SignalType.SELL
                df.loc[df.index[i], 'signal_label'] = 'Sell reason'
        
        return df

# Register in STRATEGY_REGISTRY
STRATEGY_REGISTRY['my_custom'] = MyCustomStrategy
```

### 3. Backtest Engine (`backtest_engine.py`)

Handles all trading mechanics:
- **Position Management**: Opens and closes positions based on signals
- **P&L Calculation**: Tracks profit/loss for each trade
- **Performance Metrics**: Calculates win rate, profit factor, average win/loss
- **Trade History**: Records all buy and sell transactions

**Usage**:
```python
# Get strategy
strategy = get_strategy('mechanical_3day', df)

# Create engine
engine = BacktestEngine(strategy, initial_capital=100000)

# Run backtest
result = engine.run(symbol='NIFTY 50')

# Access results
print(f"Total P&L: {result.metrics['total_pnl']}")
print(f"Win Rate: {result.metrics['win_rate']}%")
```

### 4. API Integration (`main.py`)

The `/run_backtest` endpoint now:
1. Fetches market data via `DhanClient`
2. Instantiates the appropriate strategy
3. Creates a `BacktestEngine` with the strategy
4. Runs the backtest
5. Returns results to the frontend

**Backward Compatibility**: The old `GannStrategyEngine` is kept as a fallback to ensure no breaking changes during the transition.

## Benefits of This Architecture

### ✅ Easy Strategy Development
You can create and modify strategies without worrying about:
- Position management logic
- P&L calculation
- Trade execution details

Just focus on: "When should I buy? When should I sell?"

### ✅ Consistent Backtesting
All strategies use the same backtesting engine, ensuring:
- Fair comparison between strategies
- Consistent P&L calculation
- Standardized performance metrics

### ✅ Modular and Testable
Each component can be tested independently:
- Test strategies in isolation (signal generation only)
- Test backtesting engine with mock signals
- Easy unit testing

### ✅ Ad-hoc Strategy Testing
You can quickly:
1. Create a new strategy class
2. Register it in `STRATEGY_REGISTRY`
3. Test it immediately via the API
4. Compare results with other strategies

No need to duplicate backtesting logic!

## Migration Status

### Current Status
- ✅ New architecture implemented
- ✅ All existing strategies refactored
- ✅ API endpoints updated
- ✅ Backward compatibility maintained
- ✅ Old `gann_logic.py` kept as fallback

### Old vs New

**Old Way** (gann_logic.py):
```python
# Strategy mixed with execution
def run_mechanical_3day_swing(self):
    position = 0  # Position tracking in strategy!
    for row in df:
        if buy_condition and position == 0:
            position = 1  # Managing position
            trades.append(...)  # Creating trades
```

**New Way** (strategies.py + backtest_engine.py):
```python
# Strategy: Pure signal generation
def generate_signals(self):
    for row in df:
        if buy_condition:
            df['signal'] = SignalType.BUY  # Just signal
    return df

# Engine: Handles execution separately
engine = BacktestEngine(strategy)
result = engine.run()  # Position management happens here
```

## Files Overview

| File | Purpose |
|------|---------|
| `base_strategy.py` | Abstract base class for all strategies |
| `strategies.py` | Concrete strategy implementations |
| `backtest_engine.py` | Position management & P&L calculation |
| `main.py` | API endpoints using new architecture |
| `gann_logic.py` | ⚠️ Legacy - kept for backward compatibility |
| `dhan_client.py` | Data fetching (unchanged) |

## Next Steps

1. **Test thoroughly** - Verify backtest results match old system
2. **Add more strategies** - Take advantage of easy strategy creation
3. **Enhance metrics** - Add Sharpe ratio, max drawdown, etc.
4. **Remove fallback** - Once confident, remove old `GannStrategyEngine` dependency

## Example: Comparing Strategies

```python
# Fetch data once
df = client.fetch_data('NIFTY 50', '2025-12-20', '2025-12-26')

# Test Strategy 1
strategy1 = get_strategy('mechanical_3day', df)
result1 = BacktestEngine(strategy1).run()

# Test Strategy 2
strategy2 = get_strategy('gann_square_9', df)
result2 = BacktestEngine(strategy2).run()

# Compare
print(f"Strategy 1 P&L: {result1.metrics['total_pnl']}")
print(f"Strategy 2 P&L: {result2.metrics['total_pnl']}")
```

Clean, simple, and modular! 🚀
