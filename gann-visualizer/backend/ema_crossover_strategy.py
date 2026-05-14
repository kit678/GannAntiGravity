"""
9/21 EMA Crossover Strategy

Simple two-line EMA crossover strategy:
- BUY when 9 EMA crosses ABOVE 21 EMA (bullish momentum)
- SELL when 9 EMA crosses BELOW 21 EMA (bearish momentum)
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from base_strategy import BaseStrategy, SignalType


class EMACrossoverStrategy(BaseStrategy):

    def __init__(self, df: pd.DataFrame, params: Optional[Dict[str, Any]] = None):
        super().__init__(df, params)
        self.fast_period = self.params.get('fast_period', 9)
        self.slow_period = self.params.get('slow_period', 21)

    def get_strategy_name(self) -> str:
        return "9/21 EMA Crossover Strategy"

    def get_strategy_description(self) -> str:
        return "Two-line EMA crossover on 9 and 21 periods"

    def get_indicator_series(self) -> Dict[str, list]:
        df = self.df.copy()
        df['ema_9'] = df['close'].ewm(span=self.fast_period, adjust=False).mean()
        df['ema_21'] = df['close'].ewm(span=self.slow_period, adjust=False).mean()

        def make_series(series, time_col):
            result = []
            for i in range(len(df)):
                if pd.notna(series.iloc[i]):
                    t = time_col.iloc[i]
                    ts = int(t.timestamp()) if hasattr(t, 'timestamp') else int(t)
                    result.append({'time': ts, 'value': float(series.iloc[i])})
            return result

        return {
            'ema_9': make_series(df['ema_9'], df['timestamp']),
            'ema_21': make_series(df['ema_21'], df['timestamp']),
        }

    def generate_signals(self) -> pd.DataFrame:
        df = self.df.copy()

        df['ema_9'] = df['close'].ewm(span=self.fast_period, adjust=False).mean()
        df['ema_21'] = df['close'].ewm(span=self.slow_period, adjust=False).mean()

        df['signal'] = SignalType.HOLD
        df['signal_price'] = df['close']
        df['signal_label'] = ''

        for i in range(self.slow_period + 1, len(df)):
            prev_9 = df['ema_9'].iloc[i - 1]
            prev_21 = df['ema_21'].iloc[i - 1]
            curr_9 = df['ema_9'].iloc[i]
            curr_21 = df['ema_21'].iloc[i]

            if pd.isna(prev_9) or pd.isna(prev_21) or pd.isna(curr_9) or pd.isna(curr_21):
                continue

            prev_9_above = prev_9 > prev_21
            curr_9_above = curr_9 > curr_21

            if not prev_9_above and curr_9_above:
                df.loc[df.index[i], 'signal'] = SignalType.BUY
                df.loc[df.index[i], 'signal_label'] = 'EMA Cross BUY (9↑21)'

            elif prev_9_above and not curr_9_above:
                df.loc[df.index[i], 'signal'] = SignalType.SELL
                df.loc[df.index[i], 'signal_label'] = 'EMA Cross SELL (9↓21)'

        return df
