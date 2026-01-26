"""
Test suite for Study Tool modules
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from study_tool.pivot_engine import PivotEngine, PivotType, Scenario
from study_tool.angle_engine import AngleEngine
from study_tool.event_logger import EventLogger, EventType
from study_tool.study_tool import StudyTool, StudyConfig


def create_sample_data(bars: int = 100) -> pd.DataFrame:
    """Create sample OHLCV data with clear swings"""
    np.random.seed(42)
    
    base_time = int(datetime(2024, 1, 1).timestamp())
    timestamps = [base_time + i * 60 for i in range(bars)]  # 1-minute bars
    
    # Create price with clear swing pattern
    prices = []
    base_price = 100.0
    
    for i in range(bars):
        # Create oscillating pattern
        cycle = (i // 20) % 2
        progress = (i % 20) / 20.0
        
        if cycle == 0:
            # Rising
            price = base_price + progress * 10
        else:
            # Falling
            price = base_price + 10 - progress * 10
        
        prices.append(price)
    
    # Add some noise
    prices = [p + np.random.randn() * 0.5 for p in prices]
    
    data = {
        'timestamp': timestamps,
        'open': [p - 0.1 for p in prices],
        'high': [p + 0.5 for p in prices],
        'low': [p - 0.5 for p in prices],
        'close': prices,
        'volume': [1000 + np.random.randint(0, 500) for _ in range(bars)]
    }
    
    return pd.DataFrame(data)


class TestPivotEngine:
    """Tests for PivotEngine"""
    
    def test_detect_pivots(self):
        """Test pivot detection"""
        df = create_sample_data(100)
        engine = PivotEngine(df, lookback=5)
        
        pivots = engine.detect_pivots()
        
        assert len(pivots) > 0
        assert all(p.pivot_type in [PivotType.HIGH, PivotType.LOW] for p in pivots)
    
    def test_create_pivot_pairs(self):
        """Test pivot pair creation"""
        df = create_sample_data(100)
        engine = PivotEngine(df, lookback=5)
        engine.detect_pivots()
        
        pairs = engine.create_pivot_pairs()
        
        assert len(pairs) >= 1
        assert pairs[0].pair_type == "inner"
        assert pairs[0].scenario in [Scenario.SCENARIO_1, Scenario.SCENARIO_2]
    
    def test_scenario_categorization(self):
        """Test scenario is correctly categorized based on temporal order"""
        df = create_sample_data(100)
        engine = PivotEngine(df, lookback=5)
        engine.detect_pivots()
        
        pairs = engine.create_pivot_pairs()
        inner = pairs[0]
        
        # First pivot should have earlier timestamp
        assert inner.first_pivot.timestamp < inner.second_pivot.timestamp


class TestAngleEngine:
    """Tests for AngleEngine"""
    
    def test_calculate_full_angle(self):
        """Test angle calculation"""
        df = create_sample_data(100)
        pivot_engine = PivotEngine(df, lookback=5)
        pivot_engine.detect_pivots()
        pairs = pivot_engine.create_pivot_pairs()
        
        if pairs:
            angle_engine = AngleEngine(pairs[0])
            degrees, radians = angle_engine.calculate_full_angle()
            
            assert 0 <= degrees <= 90
            assert 0 <= radians <= np.pi / 2
    
    def test_angle_divisions(self):
        """Test angle divisions are correct"""
        df = create_sample_data(100)
        pivot_engine = PivotEngine(df, lookback=5)
        pivot_engine.detect_pivots()
        pairs = pivot_engine.create_pivot_pairs()
        
        if pairs:
            angle_engine = AngleEngine(pairs[0])
            degrees, _ = angle_engine.calculate_full_angle()
            divisions = angle_engine.calculate_angle_divisions(degrees)
            
            assert divisions["7/8θ"] == degrees * 7/8
            assert divisions["3/4θ"] == degrees * 3/4
            assert divisions["1/2θ"] == degrees * 1/2
            assert divisions["1/4θ"] == degrees * 1/4
    
    def test_angle_setup(self):
        """Test complete angle setup"""
        df = create_sample_data(100)
        pivot_engine = PivotEngine(df, lookback=5)
        pivot_engine.detect_pivots()
        pairs = pivot_engine.create_pivot_pairs()
        
        if pairs:
            angle_engine = AngleEngine(pairs[0])
            setup = angle_engine.calculate_angle_setup()
            
            assert setup.full_angle_degrees >= 0
            assert len(setup.angle_lines) == 5  # full + 4 divisions
            assert setup.full_coverage_target == pairs[0].first_pivot.price


class TestEventLogger:
    """Tests for EventLogger"""
    
    def test_log_event(self):
        """Test basic event logging"""
        logger = EventLogger()
        
        event = logger.log_event(
            timestamp=1704067200,
            event_type=EventType.ANGLE_TOUCH,
            angle_name="7/8θ",
            price=100.5
        )
        
        assert len(logger.events) == 1
        assert event.angle_name == "7/8θ"
    
    def test_log_angle_breach(self):
        """Test breach logging"""
        logger = EventLogger()
        
        logger.log_angle_breach(
            timestamp=1704067200,
            price=101.0,
            angle_name="3/4θ",
            direction="up",
            close_count=2
        )
        
        assert len(logger.events) == 1
        assert logger.events[0].event_type == EventType.ANGLE_BREACH
        assert logger.events[0].direction == "up"
    
    def test_get_statistics(self):
        """Test statistics calculation"""
        logger = EventLogger()
        
        logger.log_angle_touch(1704067200, 100.0, "7/8θ")
        logger.log_angle_touch(1704067260, 100.5, "7/8θ")
        logger.log_angle_breach(1704067320, 101.0, "7/8θ", "up")
        
        stats = logger.get_statistics()
        
        assert stats["total_events"] == 3
        assert stats["events_by_type"]["angle_touch"] == 2
        assert stats["events_by_type"]["angle_breach"] == 1


class TestStudyTool:
    """Tests for StudyTool"""
    
    def test_initialize(self):
        """Test study tool initialization"""
        df = create_sample_data(100)
        tool = StudyTool(df)
        
        state = tool.initialize()
        
        assert tool.initialized
        assert len(tool.pivot_pairs) >= 1
        assert len(tool.angle_setups) >= 1
    
    def test_process_bar(self):
        """Test bar processing"""
        df = create_sample_data(100)
        tool = StudyTool(df)
        tool.initialize()
        
        state = tool.process_bar(50)
        
        assert state.current_index == 50
        assert state.momentum is not None
    
    def test_run_batch(self):
        """Test batch processing"""
        df = create_sample_data(50)  # Smaller for speed
        tool = StudyTool(df)
        
        results = tool.run_batch()
        
        assert results["total_bars"] == 50
        assert "event_statistics" in results
    
    def test_get_drawing_data(self):
        """Test drawing data generation"""
        df = create_sample_data(100)
        tool = StudyTool(df)
        tool.initialize()
        
        drawings = tool.get_drawing_data()
        
        assert "pivots" in drawings
        assert "angle_lines" in drawings
        assert "horizontal_targets" in drawings
        assert len(drawings["angle_lines"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
