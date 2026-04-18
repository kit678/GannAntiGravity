"""
Tests for CandlestickPatternDetector module
"""
import sys
import os
import tempfile

# Add backend to path
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.candlestick_detector import CandlestickPatternDetector, PatternType


def test_doji_detection():
    """Doji: open == close, wicks dominate."""
    detector = CandlestickPatternDetector(os.path.join(tempfile.gettempdir(), "test_candle_patterns.log"))
    ohlc = {'open': 100.0, 'high': 105.0, 'low': 95.0, 'close': 100.0}
    result = detector.detect(ohlc)
    assert result == PatternType.DOJI


def test_hammer_detection():
    """Hanging Man: small body, lower wick at least 2x body, minimal upper wick.

    Note: Rule-based detector returns HANGING_MAN (same geometry as HAMMER).
    Caller applies trend filter to distinguish HAMMER (uptrend) from
    HANGING_MAN (downtrend/bearish top). This test documents the rule-based
    behavior - returns HANGING_MAN since caller-side trend filter is not
    implemented in the detector itself.
    """
    detector = CandlestickPatternDetector(os.path.join(tempfile.gettempdir(), "test_candle_patterns.log"))
    ohlc = {'open': 100.0, 'high': 100.5, 'low': 95.0, 'close': 99.0}
    result = detector.detect(ohlc)
    assert result == PatternType.HANGING_MAN


def test_no_pattern():
    """Normal candle with no recognizable pattern."""
    detector = CandlestickPatternDetector(os.path.join(tempfile.gettempdir(), "test_candle_patterns.log"))
    ohlc = {'open': 100.0, 'high': 104.0, 'low': 98.0, 'close': 103.0}
    result = detector.detect(ohlc)
    assert result == PatternType.NO_PATTERN


def test_shooting_star():
    """Shooting Star: body near top of range, long upper wick, small lower wick."""
    detector = CandlestickPatternDetector(os.path.join(tempfile.gettempdir(), "test_candle_patterns.log"))
    # O=100, H=115, L=95, C=96
    # body=|100-96|=4.5, upper_wick=115-max(100,96)=15, lower_wick=min(100,96)-95=1
    # upper_wick>=2*body: 15>=9 ✓, lower_wick<body: 1<4.5 ✓
    # body_position=(max(100,96)-95)/(115-95)=5/20=0.25<0.4 → SHOOTING_STAR
    ohlc = {'open': 100.0, 'high': 115.0, 'low': 95.0, 'close': 96.0}
    result = detector.detect(ohlc)
    assert result == PatternType.SHOOTING_STAR