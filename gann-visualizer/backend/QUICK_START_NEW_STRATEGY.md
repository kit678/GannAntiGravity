# Quick Reference: Adding a New Strategy

## Step-by-Step Guide

### 1. Create Your Strategy Class

Edit `strategies.py` and add:

```python
class YourStrategyName(BaseStrategy):
    """
    Brief description of your strategy logic.
    """
    
    def __init__(self, df: pd.DataFrame, params: Optional[Dict[str, Any]] = None):
        super().__init__(df, params)
        # Optional: Extract parameters
        self.param1 = self.params.get('param1', default_value)
    
    def get_strategy_name(self) -> str:
        return "Your Strategy Display Name"
    
    def get_strategy_description(self) -> str:
        return "Detailed description of what this strategy does"
    
    def generate_signals(self) -> pd.DataFrame:
        """
        Generate buy/sell signals.
        
        IMPORTANT RULES:
        - Only analyze data and generate signals
        - Do NOT track positions
        - Do NOT calculate P&L
        - Do NOT manage trades
        
        Returns:
            DataFrame with columns:
            - signal: SignalType.BUY (1), SignalType.SELL (-1), or SignalType.HOLD (0)
            - signal_label: Human-readable reason for the signal
        """
        df = self.df.copy()
        
        # Your analysis logic here
        
        # Example: Simple indicator-based strategy
        df['ma_fast'] = df['close'].rolling(window=10).mean()
        df['ma_slow'] = df['close'].rolling(window=30).mean()
        
        # Track state for entry/exit logic
        in_position = False
        
        for i in range(30, len(df)):  # Start after indicator warmup
            # BUY SIGNAL
            if not in_position:
                if df.iloc[i]['ma_fast'] > df.iloc[i]['ma_slow']:
                    df.loc[df.index[i], 'signal'] = SignalType.BUY
                    df.loc[df.index[i], 'signal_label'] = 'MA Crossover Up'
                    in_position = True
            
            # SELL SIGNAL
            elif in_position:
                if df.iloc[i]['ma_fast'] < df.iloc[i]['ma_slow']:
                    df.loc[df.index[i], 'signal'] = SignalType.SELL
                    df.loc[df.index[i], 'signal_label'] = 'MA Crossover Down'
                    in_position = False
        
        return df
```

### 2. Register Your Strategy

In `strategies.py`, add to the registry at the bottom:

```python
STRATEGY_REGISTRY = {
    'mechanical_3day': Mechanical3DaySwingStrategy,
    'gann_square_9': SquareOf9ReversionStrategy,
    'time_cycle_breakout': TimeCycleBreakoutStrategy,
    'ichimoku_cloud': TimeCycleBreakoutStrategy,
    'your_strategy': YourStrategyName,  # Add this line
}
```

### 3. Test Your Strategy

#### Option A: Using Test Script
```bash
cd backend
python test_architecture.py
```

#### Option B: Manual Python Test
```python
from strategies import get_strategy
from backtest_engine import BacktestEngine
from dhan_client import DhanClient

# Fetch data
client = DhanClient()
df = client.fetch_data('NIFTY 50', '2025-12-20', '2025-12-26', interval='1')

# Test your strategy
strategy = get_strategy('your_strategy', df)
engine = BacktestEngine(strategy, initial_capital=100000)
result = engine.run(symbol='NIFTY 50')

# View results
print(f"Total Trades: {result.metrics['total_trades']}")
print(f"Win Rate: {result.metrics['win_rate']}%")
print(f"Total P&L: {result.metrics['total_pnl']}")
```

#### Option C: Via API
```bash
curl -X POST http://localhost:8001/run_backtest \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": "your_strategy",
    "symbol": "NIFTY 50",
    "from_date": "2025-12-20",
    "to_date": "2025-12-26",
    "resolution": "1"
  }'
```

### 4. Use in Frontend

Your strategy is now available in the dropdown automatically!

---

## Common Patterns

### Pattern 1: Indicator-Based Entry/Exit
```python
def generate_signals(self) -> pd.DataFrame:
    df = self.df.copy()
    
    # Calculate indicators
    df['rsi'] = calculate_rsi(df['close'])
    
    in_position = False
    for i in range(len(df)):
        if not in_position and df.iloc[i]['rsi'] < 30:  # Oversold
            df.loc[df.index[i], 'signal'] = SignalType.BUY
            in_position = True
        elif in_position and df.iloc[i]['rsi'] > 70:  # Overbought
            df.loc[df.index[i], 'signal'] = SignalType.SELL
            in_position = False
    
    return df
```

### Pattern 2: Price Pattern Recognition
```python
def generate_signals(self) -> pd.DataFrame:
    df = self.df.copy()
    
    in_position = False
    for i in range(3, len(df)):
        # Check for bullish engulfing
        if not in_position:
            prev = df.iloc[i-1]
            curr = df.iloc[i]
            if is_bullish_engulfing(prev, curr):
                df.loc[df.index[i], 'signal'] = SignalType.BUY
                in_position = True
    
    return df
```

### Pattern 3: Multiple Timeframe Analysis
```python
def generate_signals(self) -> pd.DataFrame:
    df = self.df.copy()
    
    # Resample to higher timeframe
    df_daily = resample_to_daily(df)
    daily_trend = calculate_trend(df_daily)
    
    # Map daily trend back to minute data
    df['daily_trend'] = map_to_minute_bars(daily_trend, df)
    
    # Only trade intraday signals in direction of daily trend
    in_position = False
    for i in range(len(df)):
        if df.iloc[i]['daily_trend'] == 'bullish':
            if not in_position and your_entry_condition:
                df.loc[df.index[i], 'signal'] = SignalType.BUY
                in_position = True
    
    return df
```

---

## Key Principles

### ✅ DO:
- Focus on signal generation logic
- Use parameters for flexibility
- Add clear signal labels
- Track entry/exit state in your loop
- Validate your logic with test data

### ❌ DON'T:
- Track position P&L (engine does this)
- Manage capital allocation (engine does this)
- Create trade records (engine does this)
- Calculate performance metrics (engine does this)

---

## Debugging Tips

### Print Signals Generated
```python
signals_with_action = df[df['signal'] != 0]
print(f"Generated {len(signals_with_action)} signals")
print(signals_with_action[['timestamp', 'signal', 'signal_label', 'close']])
```

### Visualize on Chart
The frontend automatically plots your signals as buy/sell markers.

### Check Backtest Metrics
```python
result = engine.run()
if result.metrics['total_trades'] == 0:
    print("⚠️ No trades generated - check your strategy logic")
else:
    print(f"✓ Generated {result.metrics['total_trades']} trades")
```

---

## Need Help?

1. **Read ARCHITECTURE.md** - Full architecture explanation
2. **Read existing strategies** - See examples in `strategies.py`
3. **Run tests** - `python test_architecture.py`
4. **Check console logs** - Backend prints signal generation info

---

**Remember**: Your strategy's ONLY job is to answer: "At this candle, should I buy, sell, or hold?"

Everything else is handled by the BacktestEngine!
