"""
Backtesting Engine - Handles Position Management and Trade Execution

This module is responsible for:
- Taking signals from strategies
- Managing positions (entries/exits)
- Calculating P&L
- Tracking trade history
- Generating performance metrics

The engine is strategy-agnostic and works with any strategy that implements BaseStrategy.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from base_strategy import BaseStrategy, SignalType


@dataclass
class Trade:
    """Represents a single trade (entry or exit)"""
    time: int  # Unix timestamp
    type: str  # 'buy' or 'sell'
    price: float
    label: str
    option_price: Optional[float] = None  # Price for UI display
    pnl: Optional[float] = None  # Only set for sell trades
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


@dataclass
class Position:
    """Represents an open position"""
    entry_time: int
    entry_price: float
    entry_label: str
    position_type: str = 'long'  # 'long' or 'short'
    quantity: int = 1


@dataclass
class BacktestResult:
    """Results from a backtest run"""
    trades: List[Trade]
    metrics: Dict[str, Any]
    strategy_name: str
    symbol: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'trades': [t.to_dict() for t in self.trades],
            'metrics': self.metrics,
            'strategy': self.strategy_name,
            'symbol': self.symbol
        }


class BacktestEngine:
    """
    Backtesting engine that executes strategy signals and tracks performance.
    
    This engine is completely separate from strategy logic - it only consumes
    signals and manages the trading mechanics.
    """
    
    def __init__(
        self,
        strategy: BaseStrategy,
        initial_capital: float = 100000.0,
        commission: float = 0.0,
        slippage: float = 0.0
    ):
        """
        Initialize backtesting engine.
        
        Args:
            strategy: Strategy instance that generates signals
            initial_capital: Starting capital for backtest
            commission: Commission per trade (flat fee or percentage)
            slippage: Slippage per trade (percentage)
        """
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        
        # Trading state
        self.position: Optional[Position] = None
        self.trades: List[Trade] = []
        self.equity_curve: List[float] = []
        self.current_capital = initial_capital
        
    def run(self, symbol: str = "UNKNOWN") -> BacktestResult:
        """
        Run the backtest by executing strategy signals.
        
        Args:
            symbol: Symbol being traded (for reporting)
            
        Returns:
            BacktestResult with trades and performance metrics
        """
        # Validate strategy data
        self.strategy.validate_data()
        
        # Generate signals from strategy
        signals_df = self.strategy.generate_signals()
        
        # Execute signals
        self._execute_signals(signals_df)
        
        # Close any open position at the end
        if self.position is not None:
            last_row = signals_df.iloc[-1]
            self._close_position(
                exit_time=int(last_row['timestamp']),
                exit_price=last_row['close'],
                exit_label="End of backtest period"
            )
        
        # Calculate metrics
        metrics = self._calculate_metrics()
        
        return BacktestResult(
            trades=self.trades,
            metrics=metrics,
            strategy_name=self.strategy.get_strategy_name(),
            symbol=symbol
        )
    
    def _execute_signals(self, df: pd.DataFrame) -> None:
        """
        Execute trading signals from the strategy DataFrame.
        
        The 5 EMA strategy uses:
        - SignalType.SELL for short entries AND long exits
        - SignalType.BUY for long entries AND short exits
        
        We parse the signal_label to determine the actual intent:
        - "Buy X CE" or "Buy X Call" = Long entry
        - "Buy X PE" or "Buy X Put" = Short entry  
        - "Exit Long" = Close long
        - "Exit Short" = Close short
        
        Args:
            df: DataFrame with signal column from strategy
        """
        for idx, row in df.iterrows():
            timestamp = int(row['timestamp'])
            signal = row['signal']
            label = str(row.get('signal_label', ''))  # BUGFIX: Move label definition BEFORE usage
            
            # Prioritize signal_price (Option Premium) if available, else fallback to Spot Close
            price = row.get('signal_price')
            
            # DEBUG LOGGING for Price Source (only for entry signals)
            is_entry_signal = signal != SignalType.HOLD and 'Buy' in label
            if is_entry_signal:
                print(f"[BacktestEngine] Processing Signal: {label} @ {timestamp}")
                print(f"  > Signal Price (Option): {price}")
                print(f"  > Spot Close: {row['close']}")

            if pd.isna(price) or price <= 0:
                price = row['close']
                if is_entry_signal:
                     print("  > Fallback to Spot Close")
            
            # Skip if no signal
            if signal == SignalType.HOLD:
                continue
            
            # Parse the label to determine action type
            is_entry = 'Buy ' in label and (' CE ' in label or ' PE ' in label)
            is_exit = 'Exit' in label
            is_long_entry = is_entry and ' CE ' in label
            is_short_entry = is_entry and ' PE ' in label
            is_long_exit = is_exit and 'Long' in label
            is_short_exit = is_exit and 'Short' in label
            
            # Handle LONG ENTRY (BUY signal, CE option)
            if signal == SignalType.BUY and is_long_entry and self.position is None:
                self._open_position(
                    entry_time=timestamp,
                    entry_price=price,
                    entry_label=label,
                    position_type='long'
                )
            
            # Handle SHORT ENTRY (SELL signal, PE option)
            elif signal == SignalType.SELL and is_short_entry and self.position is None:
                self._open_position(
                    entry_time=timestamp,
                    entry_price=price,
                    entry_label=label,
                    position_type='short'
                )
            
            # Handle LONG EXIT (SELL signal when in long position)
            elif signal == SignalType.SELL and is_long_exit and self.position is not None:
                self._close_position(
                    exit_time=timestamp,
                    exit_price=price,
                    exit_label=label
                )
            
            # Handle SHORT EXIT (BUY signal when in short position)
            elif signal == SignalType.BUY and is_short_exit and self.position is not None:
                self._close_position(
                    exit_time=timestamp,
                    exit_price=price,
                    exit_label=label
                )
            
            # FALLBACK for legacy strategies (simple BUY/SELL alternating)
            elif signal == SignalType.BUY and self.position is None and not is_exit:
                # Legacy: BUY when no position = enter long
                self._open_position(
                    entry_time=timestamp,
                    entry_price=price,
                    entry_label=label if label else 'Buy signal',
                    position_type='long'
                )
            elif signal == SignalType.SELL and self.position is not None and not is_entry:
                # Legacy: SELL when in position = exit
                self._close_position(
                    exit_time=timestamp,
                    exit_price=price,
                    exit_label=label if label else 'Sell signal'
                )
    
    def _open_position(self, entry_time: int, entry_price: float, entry_label: str, position_type: str = 'long') -> None:
        """
        Open a new position (enter trade).
        
        Args:
            entry_time: Unix timestamp of entry
            entry_price: Entry price
            entry_label: Human-readable label for the entry
            position_type: 'long' or 'short'
        """
        self.position = Position(
            entry_time=entry_time,
            entry_price=entry_price,
            entry_label=entry_label,
            position_type=position_type
        )
        
        # Record entry trade (labeled appropriately for direction)
        trade_type = 'buy' if position_type == 'long' else 'sell'
        entry_trade = Trade(
            time=entry_time,
            type=trade_type,
            price=entry_price,
            label=entry_label,
            option_price=entry_price,
            pnl=None
        )
        self.trades.append(entry_trade)
    
    def _close_position(self, exit_time: int, exit_price: float, exit_label: str) -> None:
        """
        Close the current position (exit trade).
        
        Args:
            exit_time: Unix timestamp of exit
            exit_price: Exit price
            exit_label: Human-readable label for the exit
        """
        if self.position is None:
            return
        
        # Calculate P&L based on position direction
        if self.position.position_type == 'long':
            # Long position: profit when price goes UP
            pnl = exit_price - self.position.entry_price
        else:
            # Short position: profit when price goes DOWN
            pnl = self.position.entry_price - exit_price
        
        pnl_pct = (pnl / self.position.entry_price) * 100 if self.position.entry_price > 0 else 0
        
        # DEBUG LOGGING for PnL Calculation
        print(f"[BacktestEngine] Closing {self.position.position_type.upper()} position:")
        print(f"  > Entry: {self.position.entry_price:.2f} @ {self.position.entry_time}")
        print(f"  > Exit: {exit_price:.2f} @ {exit_time}")
        print(f"  > PnL: {pnl:.2f} ({pnl_pct:.2f}%)")
        print(f"  > Label: {exit_label}")
        
        # Update capital
        self.current_capital += pnl
        
        # Record exit trade (labeled appropriately for direction)
        trade_type = 'sell' if self.position.position_type == 'long' else 'buy'
        exit_trade = Trade(
            time=exit_time,
            type=trade_type,
            price=exit_price,
            label=f"{exit_label} (PnL: {pnl:.2f})",
            option_price=exit_price,
            pnl=pnl
        )
        self.trades.append(exit_trade)
        
        # Clear position
        self.position = None
    
    def _calculate_metrics(self) -> Dict[str, Any]:
        """
        Calculate performance metrics from trade history.
        
        Returns:
            Dictionary of performance metrics
        """
        if not self.trades:
            return {
                'total_trades': 0,
                'completed_trades': 0,
                'wins': 0,
                'losses': 0,
                'total_pnl': 0.0,
                'win_rate': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
                'return_pct': 0.0
            }
        
        # Separate buy and sell trades
        buy_trades = [t for t in self.trades if t.type == 'buy']
        sell_trades = [t for t in self.trades if t.type == 'sell']
        
        # Calculate P&L stats
        total_pnl = sum(t.pnl for t in sell_trades if t.pnl is not None)
        wins = [t.pnl for t in sell_trades if t.pnl is not None and t.pnl > 0]
        losses = [t.pnl for t in sell_trades if t.pnl is not None and t.pnl <= 0]
        
        win_count = len(wins)
        loss_count = len(losses)
        completed_trades = win_count + loss_count
        
        # Win rate
        win_rate = (win_count / completed_trades * 100) if completed_trades > 0 else 0.0
        
        # Average win/loss
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        
        # Profit factor
        total_wins = sum(wins) if wins else 0.0
        total_losses = abs(sum(losses)) if losses else 0.0
        profit_factor = total_wins / total_losses if total_losses > 0 else 0.0
        
        return {
            'total_trades': len(self.trades),
            'completed_trades': completed_trades,
            'wins': win_count,
            'losses': loss_count,
            'total_pnl': round(total_pnl, 2),
            'win_rate': round(win_rate, 1),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2),
            'return_pct': round((total_pnl / self.initial_capital) * 100, 2)
        }
