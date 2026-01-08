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
        
        Args:
            df: DataFrame with signal column from strategy
        """
        for idx, row in df.iterrows():
            timestamp = int(row['timestamp'])
            signal = row['signal']
            price = row['close']
            
            # Handle BUY signal
            if signal == SignalType.BUY and self.position is None:
                self._open_position(
                    entry_time=timestamp,
                    entry_price=price,
                    entry_label=row.get('signal_label', 'Buy signal')
                )
            
            # Handle SELL signal
            elif signal == SignalType.SELL and self.position is not None:
                self._close_position(
                    exit_time=timestamp,
                    exit_price=price,
                    exit_label=row.get('signal_label', 'Sell signal')
                )
    
    def _open_position(self, entry_time: int, entry_price: float, entry_label: str) -> None:
        """
        Open a new position (enter trade).
        
        Args:
            entry_time: Unix timestamp of entry
            entry_price: Entry price
            entry_label: Human-readable label for the entry
        """
        self.position = Position(
            entry_time=entry_time,
            entry_price=entry_price,
            entry_label=entry_label
        )
        
        # Record buy trade
        buy_trade = Trade(
            time=entry_time,
            type='buy',
            price=entry_price,
            label=entry_label,
            pnl=None
        )
        self.trades.append(buy_trade)
    
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
        
        # Calculate P&L
        pnl = exit_price - self.position.entry_price
        pnl_pct = (pnl / self.position.entry_price) * 100
        
        # Update capital
        self.current_capital += pnl
        
        # Record sell trade
        sell_trade = Trade(
            time=exit_time,
            type='sell',
            price=exit_price,
            label=f"{exit_label} (PnL: {pnl:.2f})",
            pnl=pnl
        )
        self.trades.append(sell_trade)
        
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
