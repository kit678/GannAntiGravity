"""
Tests for CandlestickPatternDetector module
"""
import sys
import os

# Add backend to path
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.candlestick_detector import CandlestickPatternDetector, PatternType


def test_doji_detection():
    """Doji: open == close, wicks dominate."""
    detector = CandlestickPatternDetector("/tmp/test_candle_patterns.log")
    ohlc = {'open': 100.0, 'high': 105.0, 'low': 95.0, 'close': 100.0}
    result = detector.detect(ohlc)
    assert result == PatternType.DOJI


def test_hammer_detection():
    """Hammer: small body, lower wick at least 2x body, no upper wick."""
    detector = CandlestickPatternDetector("/tmp/test_candle_patterns.log")
    ohlc = {'open': 100.0, 'high': 100.5, 'low': 95.0, 'close': 99.0}
    result = detector.detect(ohlc)
    assert result == PatternType.HAMMER


def test_no_pattern():
    """Normal candle with no recognizable pattern."""
    detector = CandlestickPatternDetector("/tmp/test_candle_patterns.log")
    ohlc = {'open': 100.0, 'high': 104.0, 'low': 98.0, 'close': 103.0}
    result = detector.detect(ohlc)
    assert result == PatternType.NO_PATTERN


def test_shooting_star():
    """Shooting Star: body near top of range, long upper wick, small lower wick."""
    detector = CandlestickPatternDetector("/tmp/test_candle_patterns.log")
    # O=100, H=115, L=95, C=96
    # body=|100-96|=4.5, upper_wick=115-max(100,96)=15, lower_wick=min(100,96)-95=1
    # upper_wick>=2*body: 15>=9 ✓, lower_wick<body: 1<4.5 ✓
    # body_position=(max(100,96)-95)/(115-95)=5/20=0.25<0.4 → SHOOTING_STAR
    ohlc = {'open': 100.0, 'high': 115.0, 'low': 95.0, 'close': 96.0}
    result = detector.detect(ohlc)
    assert result == PatternType.SHOOTING_STAR