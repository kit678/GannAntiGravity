"""
9/21 EMA Crossover Strategy

Simple two-line EMA crossover strategy:
- BUY when 9 EMA crosses ABOVE 21 EMA (bullish momentum)
- SELL when 9 EMA crosses BELOW 21 EMA (bearish momentum)
"""

import math
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from base_strategy import BaseStrategy, SignalType


def safe_float(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return 0.0
    return float(val)


class EMACrossoverStrategy(BaseStrategy):

    def __init__(self, df: pd.DataFrame, params: Optional[Dict[str, Any]] = None):
        super().__init__(df, params)
        self.fast_period = self.params.get('fast_period', 9)
        self.slow_period = self.params.get('slow_period', 21)

    def get_strategy_name(self) -> str:
        return "9/21 EMA Crossover Strategy"

    def get_strategy_description(self) -> str:
        return "Two-line EMA crossover on 9 and 21 periods"

    def extract_events(self, df: pd.DataFrame, bar_index: int) -> list:
        if bar_index < self.slow_period + 1 or bar_index >= len(df):
            return []
        required = {'timestamp', 'open', 'high', 'low', 'close', 'ema_9', 'ema_21'}
        if not required.issubset(df.columns):
            return []

        curr_9 = df['ema_9'].iloc[bar_index]
        curr_21 = df['ema_21'].iloc[bar_index]
        prev_9 = df['ema_9'].iloc[bar_index - 1]
        prev_21 = df['ema_21'].iloc[bar_index - 1]

        if pd.isna(curr_9) or pd.isna(curr_21) or pd.isna(prev_9) or pd.isna(prev_21):
            return []

        prev_9_above = prev_9 > prev_21
        curr_9_above = curr_9 > curr_21

        events = []
        ts = df['timestamp'].iloc[bar_index]
        time_val = int(ts.timestamp()) if hasattr(ts, 'timestamp') else int(ts)

        if not prev_9_above and curr_9_above:
            events.append({
                "time": time_val,
                "price": float(df['close'].iloc[bar_index]),
                "type": "EMA_CROSSOVER_UP",
                "details": f"9 EMA ({curr_9:.2f}) crossed above 21 EMA ({curr_21:.2f})",
                "open": safe_float(df['open'].iloc[bar_index]),
                "high": safe_float(df['high'].iloc[bar_index]),
                "low": safe_float(df['low'].iloc[bar_index]),
                "close": safe_float(df['close'].iloc[bar_index]),
                "strategy_data": {
                    "crossover_direction": "BUY",
                    "fast_ema_value": round(float(curr_9), 2),
                    "slow_ema_value": round(float(curr_21), 2),
                }
            })
        elif prev_9_above and not curr_9_above:
            events.append({
                "time": time_val,
                "price": float(df['close'].iloc[bar_index]),
                "type": "EMA_CROSSOVER_DOWN",
                "details": f"9 EMA ({curr_9:.2f}) crossed below 21 EMA ({curr_21:.2f})",
                "open": safe_float(df['open'].iloc[bar_index]),
                "high": safe_float(df['high'].iloc[bar_index]),
                "low": safe_float(df['low'].iloc[bar_index]),
                "close": safe_float(df['close'].iloc[bar_index]),
                "strategy_data": {
                    "crossover_direction": "SELL",
                    "fast_ema_value": round(float(curr_9), 2),
                    "slow_ema_value": round(float(curr_21), 2),
                }
            })

        return events

    def get_interaction_column_schema(self) -> list:
        return [
            {"key": "time",                              "label": "Time",         "width": "140px", "format": "datetime"},
            {"key": "strategy_data.crossover_direction", "label": "Direction",    "width": "80px",  "format": "text"},
            {"key": "strategy_data.fast_ema_value",      "label": "Fast EMA",     "width": "80px",  "format": "price"},
            {"key": "strategy_data.slow_ema_value",      "label": "Slow EMA",     "width": "80px",  "format": "price"},
            {"key": "type",                              "label": "Event",        "width": "110px", "format": "text"},
            {"key": "price",                             "label": "Price",        "width": "80px",  "format": "price"},
            {"key": "details",                           "label": "Details",      "width": "200px", "format": "text"},
            {"key": "open",                              "label": "Open",         "width": "70px",  "format": "price"},
            {"key": "high",                              "label": "High",         "width": "70px",  "format": "price"},
            {"key": "low",                               "label": "Low",          "width": "70px",  "format": "price"},
            {"key": "close",                             "label": "Close",        "width": "70px",  "format": "price"},
        ]

    def get_strategy_meta(self) -> dict:
        meta = super().get_strategy_meta()
        meta["filter_field"] = "strategy_data.crossover_direction"
        meta["filter_options"] = ["BUY", "SELL"]
        return meta

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
