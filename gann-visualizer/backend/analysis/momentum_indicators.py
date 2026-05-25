"""
Momentum indicators for Target Progression strategy entry classification.

At BREACH_CONFIRMED, classify the market state as:
  'momentum'  — continuation likely, enter immediately
  'exhaustion' — reversal likely, wait for retest
  'neutral'    — unclear, skip or retest-based entry

Computed from OHLC candles using standard formulas:
  ADX (14): trend strength (no direction)
  RSI (14): overbought/oversold + divergence detection
  MACD (12,26,9): momentum histogram expansion/contraction
"""

from typing import List, Dict, Optional, Tuple
import math


def _sma(values: List[float], period: int) -> float:
    if len(values) < period:
        return values[-1] if values else 0.0
    return sum(values[-period:]) / period


def _ema(prev_ema: float, current_val: float, period: int) -> float:
    alpha = 2.0 / (period + 1)
    return (current_val - prev_ema) * alpha + prev_ema


def _tr(high: float, low: float, prev_close: float) -> float:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def compute_rsi(candles: List[Dict], period: int = 14, limit: int = 50) -> List[float]:
    """
    Compute RSI values for the last `limit` bars.
    Returns list of RSI values, same length as input candles (truncated).
    """
    if len(candles) < period + 1:
        return []

    closes = [c["close"] for c in candles]
    gains = []
    losses = []

    for i in range(1, min(len(closes), limit + period + 1)):
        delta = closes[i] - closes[i - 1]
        if delta >= 0:
            gains.append(delta)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(delta))

    rsi_values = []
    avg_gain = _sma(gains[:period], period)
    avg_loss = _sma(losses[:period], period)

    if avg_loss == 0:
        rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi_values.append(rsi)

    for i in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))
        rsi_values.append(rsi)

    return rsi_values


def compute_adx(candles: List[Dict], period: int = 14, limit: int = 50) -> Tuple[List[float], List[float], List[float]]:
    """
    Compute ADX, +DI, -DI for the last `limit` bars.
    Returns (adx_list, plus_di_list, minus_di_list).
    """
    if len(candles) < period * 2:
        return [], [], []

    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]
    n = min(len(candles), limit + period * 2)

    tr_list = []
    plus_dm_list = []
    minus_dm_list = []

    for i in range(1, n):
        tr_val = _tr(highs[i], lows[i], closes[i - 1])
        tr_list.append(tr_val)

        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]

        if up_move > down_move and up_move > 0:
            plus_dm_list.append(up_move)
        else:
            plus_dm_list.append(0.0)

        if down_move > up_move and down_move > 0:
            minus_dm_list.append(down_move)
        else:
            minus_dm_list.append(0.0)

    if len(tr_list) < period:
        return [], [], []

    atr = _sma(tr_list[:period], period)
    plus_di = 0.0
    minus_di = 0.0
    adx_values = []
    plus_di_values = []
    minus_di_values = []
    dx_list = []

    for i in range(period - 1, len(tr_list)):
        atr = ((atr * (period - 1)) + tr_list[i]) / period

        if i < len(plus_dm_list):
            pdm = sum(plus_dm_list[i - period + 1:i + 1])
            mdm = sum(minus_dm_list[i - period + 1:i + 1])

            plus_di = (pdm / atr) * 100 if atr > 0 else 0
            minus_di = (mdm / atr) * 100 if atr > 0 else 0

        plus_di_values.append(plus_di)
        minus_di_values.append(minus_di)

        if plus_di + minus_di > 0:
            dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
        else:
            dx = 0.0
        dx_list.append(dx)

    if not dx_list:
        return [], plus_di_values, minus_di_values

    dx_ema = _sma(dx_list[:period], period) if len(dx_list) >= period else dx_list[-1]
    adx_values.append(dx_ema)

    for i in range(period, len(dx_list)):
        dx_ema = ((dx_ema * (period - 1)) + dx_list[i]) / period
        adx_values.append(dx_ema)

    return adx_values, plus_di_values, minus_di_values


def compute_macd(
    candles: List[Dict],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    limit: int = 100,
) -> Tuple[List[float], List[float], List[float]]:
    """
    Compute MACD line, signal line, and histogram for the last `limit` bars.
    Returns (macd_list, signal_list, histogram_list).
    """
    closes = [c["close"] for c in candles]
    n = min(len(closes), limit + slow)

    if n < slow:
        return [], [], []

    ema_fast = closes[0]
    ema_slow = closes[0]
    macd_list = []
    signal_list = []
    histogram_list = []

    for i in range(1, n):
        ema_fast = _ema(ema_fast, closes[i], fast)
        ema_slow = _ema(ema_slow, closes[i], slow)
        macd_list.append(ema_fast - ema_slow)

    if len(macd_list) < signal:
        return macd_list, [], []

    sig_ema = macd_list[0]
    for i, macd_val in enumerate(macd_list):
        if i == 0:
            sig_ema = macd_val
        else:
            sig_ema = _ema(sig_ema, macd_val, signal)
        signal_list.append(sig_ema)

    for i in range(len(macd_list)):
        if i < len(signal_list):
            histogram_list.append(macd_list[i] - signal_list[i])

    return macd_list, signal_list, histogram_list


def detect_rsi_divergence(candles: List[Dict], rsi_values: List[float], lookback: int = 5) -> str:
    """
    Detect bearish or bullish RSI divergence over the last `lookback` bars.
    Returns 'bearish', 'bullish', or 'none'.
    """
    if len(candles) < lookback + 1 or len(rsi_values) < lookback + 1:
        return "none"

    recent_closes = [c["close"] for c in candles[-lookback - 1:]]
    recent_rsi = rsi_values[-lookback - 1:]

    close_high = max(recent_closes[:-1])
    close_low = min(recent_closes[:-1])
    rsi_high = max(recent_rsi[:-1])
    rsi_low = min(recent_rsi[:-1])

    current_close = recent_closes[-1]
    current_rsi = recent_rsi[-1]

    if current_close >= close_high and current_rsi < rsi_high:
        return "bearish"

    if current_close <= close_low and current_rsi > rsi_low:
        return "bullish"

    return "none"


def classify_momentum(
    candles: List[Dict],
    bar_index: int,
    breach_direction: str,
) -> Dict[str, float]:
    """
    Classify momentum state at a given bar_index.
    Returns dict with:
      - 'state': 'momentum' | 'exhaustion' | 'neutral'
      - 'adx': float
      - 'rsi': float
      - 'rsi_divergence': str
      - 'macd_histogram_slope': float (positive = expanding, negative = contracting)
    """
    if bar_index < 30 or bar_index >= len(candles):
        return {"state": "neutral", "adx": 0.0, "rsi": 0.0, "rsi_divergence": "none", "macd_histogram_slope": 0.0}

    window = candles[:bar_index + 1]

    rsi_vals = compute_rsi(window)
    adx_vals, _, _ = compute_adx(window)
    _, _, hist_vals = compute_macd(window)
    divergence = detect_rsi_divergence(window, rsi_vals)

    adx = adx_vals[-1] if adx_vals else 0.0
    rsi = rsi_vals[-1] if rsi_vals else 0.0

    hist_slope = 0.0
    if len(hist_vals) >= 3:
        recent_hist = hist_vals[-3:]
        if len(recent_hist) >= 3 and recent_hist[0] != 0:
            hist_slope = (recent_hist[-1] - recent_hist[0]) / abs(recent_hist[0])

    if adx < 20:
        state = "neutral"
    elif divergence in ("bearish", "bullish"):
        state = "exhaustion"
    elif adx > 40:
        state = "exhaustion"
    elif adx >= 25 and hist_slope > 0:
        state = "momentum"
    elif adx >= 20 and hist_slope > 0:
        state = "momentum"
    elif hist_slope < -0.3:
        state = "exhaustion"
    else:
        state = "neutral"

    return {
        "state": state,
        "adx": round(adx, 2),
        "rsi": round(rsi, 2),
        "rsi_divergence": divergence,
        "macd_histogram_slope": round(hist_slope, 4),
    }


def compute_atr(candles: List[Dict], period: int = 14, limit: int = 50) -> List[float]:
    """
    Compute Average True Range (ATR) for the last `limit` bars.
    Returns list of ATR values.
    """
    if len(candles) < period + 1:
        return []

    tr_list = []
    # limit calculation to the needed window for performance
    n = min(len(candles), limit + period * 2)
    start_idx = max(1, len(candles) - n)

    for i in range(start_idx, len(candles)):
        tr_val = _tr(candles[i]["high"], candles[i]["low"], candles[i-1]["close"])
        tr_list.append(tr_val)

    if len(tr_list) < period:
        return []

    atr_values = []
    atr = _sma(tr_list[:period], period)
    atr_values.append(atr)

    for i in range(period, len(tr_list)):
        atr = ((atr * (period - 1)) + tr_list[i]) / period
        atr_values.append(atr)

    return atr_values

def compute_atr(candles: List[Dict], period: int = 14, limit: int = 50) -> List[float]:
    """
    Compute Average True Range (ATR) for the last `limit` bars.
    Returns list of ATR values.
    """
    if len(candles) < period + 1:
        return []

    tr_list = []
    # limit calculation to the needed window for performance
    n = min(len(candles), limit + period * 2)
    start_idx = max(1, len(candles) - n)

    for i in range(start_idx, len(candles)):
        tr_val = _tr(candles[i]["high"], candles[i]["low"], candles[i-1]["close"])
        tr_list.append(tr_val)

    if len(tr_list) < period:
        return []

    atr_values = []
    atr = _sma(tr_list[:period], period)
    atr_values.append(atr)

    for i in range(period, len(tr_list)):
        atr = ((atr * (period - 1)) + tr_list[i]) / period
        atr_values.append(atr)

    return atr_values
