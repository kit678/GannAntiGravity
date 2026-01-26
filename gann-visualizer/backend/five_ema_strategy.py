"""
5 EMA Breakout Strategy (Power of Stocks)

This module implements the 5 EMA strategy popularized by Subhasish Pani (Power of Stocks).
The core logic is based on mean reversion - when price extends too far from the 5 EMA
without touching it, a sharp reversal is expected.

Strategy Rules:
- SELL SETUP (5-min chart): Alert candle HIGH doesn't touch 5 EMA → Short on break below LOW
- BUY SETUP (15-min chart): Alert candle LOW doesn't touch 5 EMA → Long on break above HIGH
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from base_strategy import BaseStrategy, SignalType


class FiveEMAStrategy(BaseStrategy):
    """
    5 EMA Breakout Strategy
    
    SELL SETUP (Primary - works best on 5-min for Bank Nifty/Nifty):
    1. Find candle whose HIGH does NOT touch 5 EMA (Alert Candle)
    2. Entry: When next candle breaks BELOW the LOW of Alert Candle
    3. Stop Loss: HIGH of Alert Candle
    4. Target: Based on Risk-Reward ratio (default 1:3)
    
    BUY SETUP (works best on 15-min):
    1. Find candle whose LOW does NOT touch 5 EMA (Alert Candle)  
    2. Entry: When next candle breaks ABOVE the HIGH of Alert Candle
    3. Stop Loss: LOW of Alert Candle
    4. Target: Based on Risk-Reward ratio (default 1:3)
    """
    
    def __init__(self, df: pd.DataFrame, params: Optional[Dict[str, Any]] = None):
        super().__init__(df, params)
        
        # Strategy parameters
        self.ema_period = self.params.get('ema_period', 5)
        self.risk_reward_ratio = self.params.get('risk_reward_ratio', 3.0)
        
        # Trade direction: 'both', 'long_only', 'short_only'
        self.trade_direction = self.params.get('trade_direction', 'both')
        
        # Alert candle validity (how many candles after alert candle to wait for breakout)
        self.alert_validity_bars = self.params.get('alert_validity_bars', 3)
        
        # Option data configuration
        self.use_option_data = self.params.get('use_option_data', True)  # DEFAULT: Use option data
        self.underlying = self.params.get('underlying', 'NIFTY')
        self.dhan_client = self.params.get('dhan_client', None)
    
    def get_strategy_name(self) -> str:
        return "5 EMA Breakout Strategy"
    
    def get_strategy_description(self) -> str:
        return f"5 EMA breakout with {self.risk_reward_ratio}:1 reward-risk ratio"
    
    def _calculate_ema(self, series: pd.Series, period: int) -> pd.Series:
        """Calculate Exponential Moving Average"""
        return series.ewm(span=period, adjust=False).mean()
    
    def generate_signals(self) -> pd.DataFrame:
        """
        Generate buy/sell signals based on 5 EMA breakout logic.
        
        Logic:
        1. Calculate 5 EMA
        2. Find Alert Candles (High doesn't touch EMA for shorts, Low doesn't touch for longs)
        3. Wait for breakout of Alert Candle's high/low
        4. Track position with stop-loss and target
        """
        df = self.df.copy()
        
        # Calculate 5 EMA
        df['ema_5'] = self._calculate_ema(df['close'], self.ema_period)
        
        # Initialize columns
        df['signal'] = SignalType.HOLD
        df['signal_price'] = df['close']
        df['signal_label'] = ''
        
        # Track state
        in_position = False
        position_type = None  # 'long' or 'short'
        entry_price = 0.0
        stop_loss = 0.0
        target = 0.0
        
        # Alert candle tracking
        pending_short_alert = None  # (bar_index, high, low) - for short setups
        pending_long_alert = None   # (bar_index, high, low) - for long setups
        
        # Need at least ema_period bars for EMA to be valid
        for i in range(self.ema_period + 1, len(df)):
            current = df.iloc[i]
            prev = df.iloc[i - 1]
            ema_value = current['ema_5']
            
            # --- POSITION MANAGEMENT (if in trade) ---
            if in_position:
                current_close = current['close']
                
                if position_type == 'long':
                    # Check stop loss hit (close below SL)
                    if current_close <= stop_loss:
                        df.loc[df.index[i], 'signal'] = SignalType.SELL
                        df.loc[df.index[i], 'signal_label'] = f'Exit Long (SL Hit @ {stop_loss:.1f})'
                        in_position = False
                        position_type = None
                        continue
                    
                    # Check target hit (close above target)
                    if current_close >= target:
                        df.loc[df.index[i], 'signal'] = SignalType.SELL
                        df.loc[df.index[i], 'signal_label'] = f'Exit Long (Target @ {target:.1f})'
                        in_position = False
                        position_type = None
                        continue
                    
                    # Check EMA touch exit (alternative exit)
                    if current['low'] <= ema_value:
                        df.loc[df.index[i], 'signal'] = SignalType.SELL
                        df.loc[df.index[i], 'signal_label'] = 'Exit Long (EMA Touch)'
                        in_position = False
                        position_type = None
                        continue
                
                elif position_type == 'short':
                    # Check stop loss hit (close above SL)
                    if current_close >= stop_loss:
                        df.loc[df.index[i], 'signal'] = SignalType.BUY
                        df.loc[df.index[i], 'signal_label'] = f'Exit Short (SL Hit @ {stop_loss:.1f})'
                        in_position = False
                        position_type = None
                        continue
                    
                    # Check target hit (close below target)
                    if current_close <= target:
                        df.loc[df.index[i], 'signal'] = SignalType.BUY
                        df.loc[df.index[i], 'signal_label'] = f'Exit Short (Target @ {target:.1f})'
                        in_position = False
                        position_type = None
                        continue
                    
                    # Check EMA touch exit (alternative exit)
                    if current['high'] >= ema_value:
                        df.loc[df.index[i], 'signal'] = SignalType.BUY
                        df.loc[df.index[i], 'signal_label'] = 'Exit Short (EMA Touch)'
                        in_position = False
                        position_type = None
                        continue
                
                # Still in position, continue to next bar
                continue
            
            # --- ALERT CANDLE DETECTION (when not in trade) ---
            
            # SHORT SETUP: Previous candle's HIGH doesn't touch EMA (price is above EMA)
            if self.trade_direction in ['both', 'short_only']:
                prev_ema = prev['ema_5'] if 'ema_5' in prev else df.iloc[i-1]['ema_5']
                
                # Alert condition: HIGH doesn't touch EMA AND price is above EMA
                if prev['low'] > prev_ema:  # Entire candle is above EMA (gap condition)
                    pending_short_alert = {
                        'bar_index': i - 1,
                        'high': prev['high'],
                        'low': prev['low'],
                        'valid_until': i + self.alert_validity_bars
                    }
            
            # LONG SETUP: Previous candle's LOW doesn't touch EMA (price is below EMA)
            if self.trade_direction in ['both', 'long_only']:
                prev_ema = prev['ema_5'] if 'ema_5' in prev else df.iloc[i-1]['ema_5']
                
                # Alert condition: LOW doesn't touch EMA AND price is below EMA
                if prev['high'] < prev_ema:  # Entire candle is below EMA (gap condition)
                    pending_long_alert = {
                        'bar_index': i - 1,
                        'high': prev['high'],
                        'low': prev['low'],
                        'valid_until': i + self.alert_validity_bars
                    }
            
            # --- BREAKOUT DETECTION ---
            
            # Check for SHORT breakout
            if pending_short_alert and i <= pending_short_alert['valid_until']:
                alert_low = pending_short_alert['low']
                alert_high = pending_short_alert['high']
                
                # Breakout: Current candle breaks below Alert Candle's LOW
                if current['close'] < alert_low:
                    entry_price = current['close']
                    stop_loss = alert_high
                    risk = stop_loss - entry_price
                    target = entry_price - (risk * self.risk_reward_ratio)
                    
                    # Calculate ATM Option details (Simulated for Backtest)
                    strike = round(entry_price / 50) * 50
                    expiry = self._get_next_expiry(df.iloc[i]['timestamp'])
                    
                    df.loc[df.index[i], 'signal'] = SignalType.SELL
                    # Nifty Short -> Buy PE
                    df.loc[df.index[i], 'signal_label'] = f'Buy {strike} PE ({expiry}) | SL:{stop_loss:.0f}'
                    
                    in_position = True
                    position_type = 'short'
                    pending_short_alert = None
                    pending_long_alert = None  # Clear any pending long
                    continue
            
            # Check for LONG breakout
            if pending_long_alert and i <= pending_long_alert['valid_until']:
                alert_high = pending_long_alert['high']
                alert_low = pending_long_alert['low']
                
                # Breakout: Current candle breaks above Alert Candle's HIGH
                if current['close'] > alert_high:
                    entry_price = current['close']
                    stop_loss = alert_low
                    risk = entry_price - stop_loss
                    target = entry_price + (risk * self.risk_reward_ratio)
                    
                    # Calculate ATM Option details (Simulated for Backtest)
                    strike = round(entry_price / 50) * 50
                    expiry = self._get_next_expiry(df.iloc[i]['timestamp'])
                    
                    df.loc[df.index[i], 'signal'] = SignalType.BUY
                    # Nifty Long -> Buy CE
                    df.loc[df.index[i], 'signal_label'] = f'Buy {strike} CE ({expiry}) | SL:{stop_loss:.0f}'
                    
                    in_position = True
                    position_type = 'long'
                    pending_long_alert = None
                    pending_short_alert = None  # Clear any pending short
                    continue
            
            # Expire old alerts
            if pending_short_alert and i > pending_short_alert['valid_until']:
                pending_short_alert = None
            if pending_long_alert and i > pending_long_alert['valid_until']:
                pending_long_alert = None
        
        # OPTION DATA ENRICHMENT
        # Use unified OptionContractService for proper year inference and caching
        if self.use_option_data and self.dhan_client:
            try:
                print("[5 EMA] Enriching signals with historical option data...")
                from option_contract_service import OptionContractService
                
                service = OptionContractService(self.dhan_client)
                df = service.enrich_strategy_signals(
                    df,
                    underlying=self.underlying,
                    interval='5'  # Match strategy timeframe
                )
                
                print("[5 EMA] Option data enrichment complete!")
                print(f"[5 EMA] Service stats: {service.get_stats()}")
                
                # STRICT VALIDATION: Check for missing option prices
                # Note: SignalType is imported at file level (line 16)
                sig_mask = (df['signal'].isin([SignalType.BUY, SignalType.SELL]))
                missing_price_mask = sig_mask & (df['signal_price'].isna() | (df['signal_price'] <= 0))
                
                if missing_price_mask.any():
                    missing_count = missing_price_mask.sum()
                    first_missing_idx = df[missing_price_mask].index[0]
                    first_missing_label = df.loc[first_missing_idx, 'signal_label']
                    
                    error_msg = (
                        f"CRITICAL: Found {missing_count} signals with MISSING Option Prices.\n"
                        f"Example: {first_missing_label}\n"
                        "Aborting Backtest to prevent inaccurate PnL."
                    )
                    print(error_msg)
                    raise ValueError(error_msg)
                    
            except Exception as e:
                # STRICT MODE: Let it crash to identify root cause
                print(f"[5 EMA] CRITICAL ERROR during Option Data Enrichment: {e}")
                raise e
        
        return df

    def _get_next_expiry(self, timestamp) -> str:
        """
        Calculate next available Thursday expiry from timestamp.
        
        Returns format: 'DD-Mon' compatible with option data provider.
        For backtesting, we ensure the expiry is a valid future Thursday
        relative to the signal timestamp.
        """
        try:
            # Handle both numeric timestamp and string/datetime
            if isinstance(timestamp, (int, float)):
                dt = pd.to_datetime(timestamp, unit='s')
            else:
                dt = pd.to_datetime(timestamp)
            
            # Find the next Thursday (weekday 3)
            current_weekday = dt.weekday()
            
            if current_weekday == 3:  # Thursday
                # If it's Thursday after 15:30 (market close), use next week's Thursday
                # Check: hour > 15 OR (hour == 15 AND minute >= 30)
                if dt.hour > 15 or (dt.hour == 15 and dt.minute >= 30):
                    days_ahead = 7
                else:
                    # It's Thursday before market close, use this Thursday
                    days_ahead = 0
            else:
                # Calculate days until next Thursday
                days_ahead = (3 - current_weekday) % 7
                if days_ahead == 0:
                    days_ahead = 7  # If calculation gives 0 for non-Thursday, go to next week
            
            expiry_date = dt + pd.Timedelta(days=days_ahead)
            
            # Return in 'DD-Mon' format (e.g., '16-Jan')
            # The year is inferred from the context by the option data provider
            return expiry_date.strftime('%d-%b')
        except Exception as e:
            print(f"[5 EMA] Error calculating expiry: {e}")
            return "N/A"
