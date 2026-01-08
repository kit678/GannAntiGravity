"""
Refactored Gann Strategy Implementations

All strategies now inherit from BaseStrategy and focus ONLY on signal generation.
Position management and P&L calculation are handled by the BacktestEngine.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from base_strategy import BaseStrategy, SignalType


class Mechanical3DaySwingStrategy(BaseStrategy):
    """
    Mechanical 3-Day Swing Strategy (Momentum-based)
    
    Logic: Donchian Channel breakout - buy when price breaks above the 3-period high,
    sell when price breaks below the 3-period low.
    
    Adapted for intraday: Works on any timeframe as "3-Period Swing"
    """
    
    def __init__(self, df: pd.DataFrame, params: Optional[Dict[str, Any]] = None):
        super().__init__(df, params)
        self.lookback_period = self.params.get('lookback_period', 3)
    
    def get_strategy_name(self) -> str:
        return "Mechanical 3-Day Swing"
    
    def get_strategy_description(self) -> str:
        return f"3-period Donchian breakout with {self.lookback_period} period lookback"
    
    def generate_signals(self) -> pd.DataFrame:
        """
        Generate buy/sell signals based on Donchian channel breakouts.
        
        Buy: Close > Highest High of last N periods
        Sell: Close < Lowest Low of last N periods
        """
        df = self.df.copy()
        
        # Calculate Donchian channels
        df['hh_n'] = df['high'].rolling(window=self.lookback_period).max().shift(1)
        df['ll_n'] = df['low'].rolling(window=self.lookback_period).min().shift(1)
        
        # Initialize signal columns
        df['signal'] = SignalType.HOLD
        df['signal_price'] = df['close']
        df['signal_label'] = ''
        
        # Generate signals
        # We need to track position state to generate proper entry/exit signals
        in_position = False
        
        for i in range(self.lookback_period + 1, len(df)):
            # BUY SIGNAL - breakout above high
            if not in_position and df.iloc[i]['close'] > df.iloc[i]['hh_n']:
                df.loc[df.index[i], 'signal'] = SignalType.BUY
                df.loc[df.index[i], 'signal_label'] = f'Buy {self.lookback_period}-Bar Breakout'
                in_position = True
            
            # SELL SIGNAL - breakdown below low
            elif in_position and df.iloc[i]['close'] < df.iloc[i]['ll_n']:
                df.loc[df.index[i], 'signal'] = SignalType.SELL
                df.loc[df.index[i], 'signal_label'] = 'Sell (Stop Loss)'
                in_position = False
        
        return df


class SquareOf9ReversionStrategy(BaseStrategy):
    """
    Gann Square of 9 Reversion Strategy
    
    Logic: Calculate Gann levels based on the opening price using Square of 9 wheel.
    Buy when price touches support levels, sell on bounce/time exit.
    
    Square of 9 formula: Level = (sqrt(price) + degrees/360)^2
    """
    
    def __init__(self, df: pd.DataFrame, params: Optional[Dict[str, Any]] = None):
        super().__init__(df, params)
        self.level_tolerance = self.params.get('level_tolerance', 0.001)  # 0.1% tolerance
        self.hold_periods = self.params.get('hold_periods', 5)  # Hold for N periods after entry
    
    def get_strategy_name(self) -> str:
        return "Gann Square of 9 Reversion"
    
    def get_strategy_description(self) -> str:
        return "Support/resistance based on Gann Square of 9 mathematical levels"
    
    def generate_signals(self) -> pd.DataFrame:
        """
        Generate buy/sell signals based on Gann Square of 9 levels.
        
        Buy: Price touches calculated support level
        Sell: After holding for N periods (scalping exit)
        """
        df = self.df.copy()
        
        if len(df) == 0:
            return df
        
        # Calculate Gann levels based on opening price
        start_price = df.iloc[0]['open']
        root = np.sqrt(start_price)
        
        # Calculate levels (45°, 90°, 135° increments on the wheel)
        # 360° = +2 to root, so 45° = +0.25, 90° = +0.5, 135° = +0.75
        levels = {
            '45deg': (root + 0.25) ** 2,
            '90deg': (root + 0.50) ** 2,
            '135deg': (root + 0.75) ** 2,
            '180deg': (root + 1.00) ** 2
        }
        
        # Initialize signal columns
        df['signal'] = SignalType.HOLD
        df['signal_price'] = df['close']
        df['signal_label'] = ''
        
        # Track position entry for time-based exit
        entry_index = None
        
        for i in range(1, len(df)):
            current_row = df.iloc[i]
            
            # If not in position, look for support bounces
            if entry_index is None:
                for level_name, level_price in levels.items():
                    # Check if low touched the level (within tolerance)
                    if abs(current_row['low'] - level_price) < (level_price * self.level_tolerance):
                        df.loc[df.index[i], 'signal'] = SignalType.BUY
                        df.loc[df.index[i], 'signal_label'] = f'Sq9 Support @{level_price:.1f}'
                        entry_index = i
                        break
            
            # If in position, check for time-based exit
            elif entry_index is not None:
                if i >= entry_index + self.hold_periods:
                    df.loc[df.index[i], 'signal'] = SignalType.SELL
                    df.loc[df.index[i], 'signal_label'] = 'Exit (Time-based)'
                    entry_index = None
        
        return df


class TimeCycleBreakoutStrategy(BaseStrategy):
    """
    Gann Time Cycle Breakout Strategy
    
    Logic: Trade based on time cycles and price patterns.
    This is a placeholder for future implementation.
    """
    
    def get_strategy_name(self) -> str:
        return "Time Cycle Breakout"
    
    def get_strategy_description(self) -> str:
        return "Gann time cycle analysis (placeholder implementation)"
    
    def generate_signals(self) -> pd.DataFrame:
        """
        Placeholder: Returns no signals.
        TODO: Implement time cycle analysis
        """
        df = self.df.copy()
        df['signal'] = SignalType.HOLD
        df['signal_price'] = df['close']
        df['signal_label'] = ''
        return df


# Strategy registry - maps strategy names to classes
STRATEGY_REGISTRY = {
    'mechanical_3day': Mechanical3DaySwingStrategy,
    'gann_square_9': SquareOf9ReversionStrategy,
    'time_cycle_breakout': TimeCycleBreakoutStrategy,
    'ichimoku_cloud': TimeCycleBreakoutStrategy,  # Placeholder
}


def get_strategy(strategy_name: str, df: pd.DataFrame, params: Optional[Dict[str, Any]] = None) -> BaseStrategy:
    """
    Factory function to get a strategy instance by name.
    
    Args:
        strategy_name: Name of the strategy
        df: Market data DataFrame
        params: Optional parameters for the strategy
        
    Returns:
        Strategy instance
        
    Raises:
        ValueError: If strategy name is not recognized
    """
    if strategy_name not in STRATEGY_REGISTRY:
        raise ValueError(f"Unknown strategy: {strategy_name}. Available: {list(STRATEGY_REGISTRY.keys())}")
    
    strategy_class = STRATEGY_REGISTRY[strategy_name]
    return strategy_class(df, params)
