import pandas as pd
import numpy as np

class GannStrategyEngine:
    def __init__(self, df):
        self.df = df
        # Ensure numeric type
        cols = ['open', 'high', 'low', 'close']
        for c in cols:
            self.df[c] = pd.to_numeric(self.df[c])

    def run_mechanical_3day_swing(self):
        """
        Strategy 1: Mechanical 3-Day Swing (Momentum)
        Logic: Buying after 3 consecutive higher highs.
        Adapted for 1-minute bars as '3-Period Swing' for intraday test.
        """
        df = self.df.copy()
        signals = []
        
        # We need a rolling window or iterrows. For visuals, we want specific trade points.
        # Logic: 
        # Buy if Low > Low[1] and High > High[1] for 3 consecutive bars? 
        # Or simpler: Close > High of previous 3 bars?
        # Gann's rule: "Moves of 3 days or more".
        # Implementation: If price breaks the High of the last 3 candles (Donchian Channel logic), Buy.
        
        # Let's use a Donchian breakout for "3 periods"
        df['hh_3'] = df['high'].rolling(window=3).max().shift(1)
        df['ll_3'] = df['low'].rolling(window=3).min().shift(1)
        
        position = 0 # 0 none, 1 long
        entry_price = 0
        
        trades = []

        for i, row in df.iterrows():
            if i < 4: continue
            
            # Timestamp handling
            # Assuming row['timestamp'] is usable logic
            ts = row['timestamp']
            
            # BUY SIGNAL
            if position == 0:
                if row['close'] > row['hh_3']:
                    position = 1
                    entry_price = row['close']
                    trades.append({
                        "time": ts,
                        "type": "buy",
                        "price": row['close'],
                        "label": "Buy 3-Bar Breakout"
                    })
            
            # SELL/EXIT SIGNAL
            elif position == 1:
                # Exit if we break the low of the 3-day swing (trailing stop)
                if row['close'] < row['ll_3']:
                    position = 0
                    profit = row['close'] - entry_price
                    trades.append({
                        "time": ts,
                        "type": "sell",
                        "price": row['close'],
                        "label": f"Sell (PnL: {profit:.2f})",
                        "pnl": profit
                    })

        return trades

    def run_square_of_9_reversion(self):
        """
        Strategy 2: Square of 9 Reversion
        Logic: Levels based on Open Price.
        """
        df = self.df.copy()
        if len(df) == 0: return []
        
        trades = []
        
        # Calculate levels based on the very first candle of the dataset (approx Open)
        # Ideally this resets daily, but for backtest segment we take the start.
        start_price = df.iloc[0]['open']
        root = np.sqrt(start_price)
        
        # Gann Levels (45, 90, 180 degrees)
        # 180 deg = +1 to root? No, 360 deg is +2 to root usually in basic Sq9 wheel logic?
        # Simplification: Step of 0.125 for 45 deg, 0.25 for 90 deg?
        # Gann Wheel: (sqrt(P) + n)^2. 360deg = +2. So 45deg = +0.25
        
        level_45 = (root + 0.25) ** 2
        level_90 = (root + 0.50) ** 2
        level_135 = (root + 0.75) ** 2
        
        levels = [level_45, level_90, level_135]
        
        position = 0
        
        for i, row in df.iterrows():
            if i < 1: continue
            
            # Simple interaction: If price crosses FROM ABOVE to BELOW a level -> Buy Support (Reversion)
            # Or if price hits FROM BELOW and rejects -> Short
            
            # Let's try Support Buying
            for lvl in levels:
                # Check near match (within 0.1%)
                if abs(row['low'] - lvl) < (lvl * 0.001):
                    # Potential bounce
                    if position == 0:
                         trades.append({
                            "time": row['timestamp'],
                            "type": "buy",
                            "price": row['close'],
                            "label": f"Sq9 Support {lvl:.1f}"
                        })
                         position = 1
            
            # Close trade after fixed bars for scalping?
            if position == 1:
                 # Simple exit after 5 candles
                 # This needs a better state tracking than just loop, but works for visualization
                 pass 
                 
        return trades

    def run_time_cycle_breakout(self):
        # Placeholder for Time Strategy
        return []

