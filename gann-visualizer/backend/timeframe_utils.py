"""
Shared timeframe aggregation utilities.

Used by data source clients (YFinanceClient, BinanceClient) to synthesize
timeframes that are not natively available from the underlying API by
aggregating lower-timeframe bars.

Currently supports: 4m (aggregate 4 × 1m bars), 4H (aggregate 4 × 1H bars)
"""

from typing import List, Dict, Any
import pandas as pd


def aggregate_1m_to_4m(bars: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate 1-minute OHLC bars into 4-minute candles.

    Groups every 4 consecutive bars into one 4m candle:
      - open   = first bar's open
      - high   = max of 4 highs
      - low    = min of 4 lows
      - close  = last bar's close
      - volume = sum of 4 volumes
      - timestamp = first bar's timestamp

    Args:
        bars: DataFrame with columns [timestamp, open, high, low, close, volume],
              sorted by timestamp ascending.

    Returns:
        DataFrame with the same columns, containing aggregated 4m candles.
    """
    if bars.empty:
        return bars

    required = {"timestamp", "open", "high", "low", "close"}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = bars.sort_values("timestamp").reset_index(drop=True)
    aggregated_rows = []

    for chunk_start in range(0, len(df), 4):
        chunk = df.iloc[chunk_start:chunk_start + 4]
        if len(chunk) == 0:
            continue

        aggregated_rows.append(
            {
                "timestamp": int(chunk["timestamp"].iloc[0]),
                "open": float(chunk["open"].iloc[0]),
                "high": float(chunk["high"].max()),
                "low": float(chunk["low"].min()),
                "close": float(chunk["close"].iloc[-1]),
                # Volume is optional: some index feeds omit it entirely.
                "volume": int(chunk["volume"].sum())
                if "volume" in chunk.columns
                else 0,
            }
        )


    result = pd.DataFrame(aggregated_rows)
    return result.sort_values("timestamp").reset_index(drop=True)


def aggregate_to_4x(bars: pd.DataFrame) -> pd.DataFrame:
    """
    Generic 4x aggregation — groups every 4 consecutive bars into one.

    Works for any source resolution: 1m → 4m, 1H → 4H, etc.
    Same OHLC logic as aggregate_1m_to_4m.

    Args:
        bars: DataFrame with columns [timestamp, open, high, low, close, volume],
              sorted by timestamp ascending.

    Returns:
        DataFrame with the same columns, containing aggregated 4x candles.
    """
    return aggregate_1m_to_4m(bars)
