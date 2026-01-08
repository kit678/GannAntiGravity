"""
Base Strategy Interface for Trading Strategies

This module defines the abstract base class that all trading strategies must inherit from.
Strategies should focus ONLY on signal generation, not position management or P&L calculation.
"""

from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Any, Optional


class SignalType:
    """Signal types that strategies can generate"""
    BUY = 1
    SELL = -1
    HOLD = 0


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    
    Strategies must implement generate_signals() which returns a DataFrame
    with a 'signal' column indicating buy (1), sell (-1), or hold (0) signals.
    
    The strategy should NOT:
    - Track positions
    - Calculate P&L
    - Manage trades
    - Make execution decisions
    
    The strategy SHOULD:
    - Analyze price data
    - Generate signals based on strategy logic
    - Return clear buy/sell signals
    """
    
    def __init__(self, df: pd.DataFrame, params: Optional[Dict[str, Any]] = None):
        """
        Initialize strategy with market data and optional parameters.
        
        Args:
            df: DataFrame with OHLCV data (columns: timestamp, open, high, low, close, volume)
            params: Optional dictionary of strategy-specific parameters
        """
        self.df = df.copy()
        self.params = params or {}
        
        # Ensure numeric types for price columns
        price_cols = ['open', 'high', 'low', 'close']
        for col in price_cols:
            if col in self.df.columns:
                self.df[col] = pd.to_numeric(self.df[col], errors='coerce')
        
        # Initialize signal column
        self.df['signal'] = SignalType.HOLD
        self.df['signal_price'] = 0.0
        self.df['signal_label'] = ''
        
    @abstractmethod
    def generate_signals(self) -> pd.DataFrame:
        """
        Generate buy/sell signals based on strategy logic.
        
        Returns:
            DataFrame with added columns:
                - signal: 1 (buy), -1 (sell), 0 (hold)
                - signal_price: price at which signal was generated
                - signal_label: human-readable description of the signal
        """
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """Return the name of this strategy"""
        pass
    
    def get_strategy_description(self) -> str:
        """Return a description of the strategy (optional override)"""
        return f"{self.get_strategy_name()} - No description provided"
    
    def validate_data(self) -> bool:
        """
        Validate that the input data has the required columns and format.
        
        Returns:
            True if data is valid, False otherwise
        """
        required_cols = ['timestamp', 'open', 'high', 'low', 'close']
        
        for col in required_cols:
            if col not in self.df.columns:
                raise ValueError(f"Missing required column: {col}")
        
        if len(self.df) == 0:
            raise ValueError("DataFrame is empty")
        
        return True
