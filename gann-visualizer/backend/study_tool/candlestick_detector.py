"""
Candlestick Pattern Detector - Single-candle pattern detection wrapper.
"""
from enum import Enum
from typing import Dict, Optional
import datetime
import os


class PatternType(Enum):
    DOJI = "doji"
    PINBAR = "pinbar"
    SHOOTING_STAR = "shooting_star"
    INVERTED_HAMMER = "inverted_hammer"
    SPINNING_TOP = "spinning_top"
    MARUBOZU = "marubozu"
    NO_PATTERN = "no_pattern"


class CandlestickPatternDetector:
    """
    Wrapper class that detects single-candle patterns.

    Uses CandleKit internally but can be swapped for TA-Lib or custom
    logic without changing the calling code.
    """

    # Rule-based detection thresholds
    DOJI_BODY_RATIO = 0.1          # body / total_range < this
    MARUBOZU_WICK_RATIO = 0.05    # wick / total_range < this for both wicks
    WICK_TO_BODY_MULTIPLIER = 2    # wick must be >= this * body
    SPINNING_TOP_BODY_RATIO = 0.3  # body / total_range < this
    # Body position for Shooting Star vs Inverted Hammer (0=bottom, 1=top)
    # body_position < this -> SHOOTING_STAR, else -> INVERTED_HAMMER
    BODY_POSITION_THRESHOLD = 0.4

    def __init__(self, pattern_log_path: str):
        self.pattern_log_path = pattern_log_path
        os.makedirs(os.path.dirname(pattern_log_path), exist_ok=True)

    def detect(self, ohlc: Dict[str, float]) -> PatternType:
        """
        Detect single-candle pattern from OHLC data.

        Args:
            ohlc: Dict with keys 'open', 'high', 'low', 'close'

        Returns:
            PatternType enum value
        """
        pattern = self._detect_candlekit(ohlc)
        self._log_to_file(ohlc, pattern)
        return pattern

    def _detect_candlekit(self, ohlc: Dict[str, float]) -> PatternType:
        """
        Detect using CandleKit library.

        CandleKit expects a pandas DataFrame. We construct it inline.
        Any runtime errors (type mismatch, etc.) fall through to fallback.
        """
        try:
            import candlekit
            import pandas as pd

            df = pd.DataFrame([{
                'open': ohlc['open'],
                'high': ohlc['high'],
                'low': ohlc['low'],
                'close': ohlc['close']
            }])
            results = candlekit.detect_pattern(df)
            if results and len(results) > 0:
                return self._map_candlekit_result(results[0])
        except ImportError:
            pass

        # Fallback: rule-based detection if CandleKit unavailable
        return self._rule_based_detect(ohlc)

    def _map_candlekit_result(self, pattern_name: str) -> PatternType:
        """Map CandleKit pattern name to PatternType enum."""
        name_lower = pattern_name.lower()
        mapping = {
            'doji': PatternType.DOJI,
            'hammer': PatternType.PINBAR,
            'hanging man': PatternType.PINBAR,
            'shooting star': PatternType.SHOOTING_STAR,
            'inverted hammer': PatternType.INVERTED_HAMMER,
            'spinning top': PatternType.SPINNING_TOP,
            'marubozu': PatternType.MARUBOZU,
        }
        return mapping.get(name_lower, PatternType.NO_PATTERN)

    def _rule_based_detect(self, ohlc: Dict[str, float]) -> PatternType:
        """
        Rule-based fallback detection.

        Pure Python implementation of common single-candle patterns.
        Used when CandleKit is not available.
        """
        o = ohlc['open']
        h = ohlc['high']
        l = ohlc['low']
        c = ohlc['close']

        body = abs(c - o)
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        total_range = h - l

        if total_range == 0:
            return PatternType.NO_PATTERN

        # Doji: body is negligible compared to range
        if body / total_range < self.DOJI_BODY_RATIO:
            return PatternType.DOJI

        # Marubozu: almost no upper or lower wicks
        if (upper_wick / total_range < self.MARUBOZU_WICK_RATIO
                and lower_wick / total_range < self.MARUBOZU_WICK_RATIO):
            return PatternType.MARUBOZU

        # Pinbar: small body at top, long lower wick (2x+ body), minimal upper wick
        # Valid in both uptrends and downtrends — direction determined by context.
        if (lower_wick >= self.WICK_TO_BODY_MULTIPLIER * body
                and upper_wick < body):
            return PatternType.PINBAR

        # Shooting Star / Inverted Hammer: upper wick >= 2x body, lower wick < body
        # Distinguish by where the body closes within the range:
        #   - SHOOTING_STAR: close near the low (bearish context)
        #   - INVERTED_HAMMER: close near the high (bullish context)
        if (upper_wick >= self.WICK_TO_BODY_MULTIPLIER * body
                and lower_wick < body):
            body_position = (max(o, c) - l) / total_range  # 0 = bottom, 1 = top
            if body_position < self.BODY_POSITION_THRESHOLD:
                return PatternType.SHOOTING_STAR
            else:
                return PatternType.INVERTED_HAMMER

        # Spinning Top: body small but notable, wicks larger than body
        if (body / total_range < self.SPINNING_TOP_BODY_RATIO
                and upper_wick > body and lower_wick > body):
            return PatternType.SPINNING_TOP

        return PatternType.NO_PATTERN

    def _log_to_file(self, ohlc: Dict, pattern: PatternType):
        """Append pattern detection to dedicated log file."""
        dt = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(self.pattern_log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{dt}] O:{ohlc['open']:.2f} H:{ohlc['high']:.2f} L:{ohlc['low']:.2f} C:{ohlc['close']:.2f} -> {pattern.value}\n")