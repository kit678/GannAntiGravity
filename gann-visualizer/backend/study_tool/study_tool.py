"""
Study Tool - Main orchestrator for Angular Price Coverage analysis

This module integrates:
- Pivot detection
- Angle calculation
- Event logging
- Price-angle interaction tracking
"""

import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from .pivot_engine import PivotEngine, PivotPair, Pivot, PivotType, Scenario
from .angle_engine import AngleEngine, AngleSetup, AngleLine, HorizontalTarget
from .event_logger import EventLogger, EventType


@dataclass
class StudyConfig:
    """Configuration for the study tool"""
    pivot_lookback: int = 10
    angle_touch_tolerance: float = 0.1  # Percentage
    confirmation_closes: int = 2
    price_scale: float = 1.0
    time_scale: float = 1.0


@dataclass
class MomentumState:
    """Current momentum indicators state"""
    ema_9: Optional[float] = None
    ema_21: Optional[float] = None
    ema_signal: Optional[str] = None  # "bullish", "bearish", "neutral"
    rsi: Optional[float] = None
    rsi_signal: Optional[str] = None
    vwap: Optional[float] = None
    vwap_signal: Optional[str] = None
    overall_momentum: Optional[str] = None  # "bullish", "bearish", "neutral"
    confidence: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "ema_9": self.ema_9,
            "ema_21": self.ema_21,
            "ema_signal": self.ema_signal,
            "rsi": self.rsi,
            "rsi_signal": self.rsi_signal,
            "vwap": self.vwap,
            "vwap_signal": self.vwap_signal,
            "overall_momentum": self.overall_momentum,
            "confidence": self.confidence
        }


@dataclass
class StudyState:
    """Current state of the study"""
    current_index: int
    current_price: float
    current_time: int
    pivot_pairs: List[PivotPair]
    angle_setups: List[AngleSetup]
    momentum: MomentumState
    active_angle: Optional[str] = None  # Current angle price is near
    near_target: bool = False
    
    def to_dict(self) -> Dict:
        return {
            "current_index": self.current_index,
            "current_price": self.current_price,
            "current_time": self.current_time,
            "pivot_pairs": [pp.to_dict() for pp in self.pivot_pairs],
            "angle_setups": [ase.to_dict() for ase in self.angle_setups],
            "momentum": self.momentum.to_dict(),
            "active_angle": self.active_angle,
            "near_target": self.near_target
        }


class StudyTool:
    """
    Main study tool for Angular Price Coverage analysis.
    
    Usage for batch processing:
        tool = StudyTool(df, config)
        tool.initialize()
        results = tool.run_batch()
        tool.export_events("events.json")
    
    Usage for replay:
        tool = StudyTool(df, config)
        tool.initialize()
        for i in range(len(df)):
            state = tool.process_bar(i)
            # Update visualization with state
    """
    
    def __init__(
        self, 
        df: pd.DataFrame, 
        config: Optional[StudyConfig] = None
    ):
        """
        Initialize study tool.
        
        Args:
            df: DataFrame with OHLCV data
            config: Configuration settings
        """
        self.df = df.copy()
        self.config = config or StudyConfig()
        
        # Initialize engines
        self.pivot_engine = PivotEngine(df, lookback=self.config.pivot_lookback)
        self.event_logger = EventLogger()
        
        # State
        self.initialized = False
        self.pivot_pairs: List[PivotPair] = []
        self.angle_setups: List[AngleSetup] = []
        self.current_index = 0
        self._last_closes: List[float] = []
        
    def initialize(self, lookback_bars: int = 0):
        """
        Initialize the study tool.
        
        Args:
            lookback_bars: Number of bars to use for lookback (before study start)
        """
        # Detect all pivots
        self.pivot_engine.detect_pivots()
        
        # Create initial pivot pairs
        self.pivot_pairs = self.pivot_engine.create_pivot_pairs()
        
        # Calculate angle setups for each pair
        self.angle_setups = []
        for pair in self.pivot_pairs:
            engine = AngleEngine(
                pair,
                price_scale=self.config.price_scale,
                time_scale=self.config.time_scale
            )
            setup = engine.calculate_angle_setup()
            self.angle_setups.append(setup)
        
        self.initialized = True
        return self.get_current_state()
    
    def process_bar(self, bar_index: int) -> StudyState:
        """
        Process a single bar (for replay mode).
        
        Args:
            bar_index: Index of bar to process
            
        Returns:
            Current StudyState
        """
        if not self.initialized:
            self.initialize()
        
        self.current_index = bar_index
        row = self.df.iloc[bar_index]
        
        current_price = float(row['close'])
        current_time = int(row['timestamp'])
        
        # Track closes for confirmation
        self._last_closes.append(current_price)
        if len(self._last_closes) > 10:
            self._last_closes = self._last_closes[-10:]
        
        # Check for angle interactions
        active_angle = None
        near_target = False
        
        for setup in self.angle_setups:
            for angle_line in setup.angle_lines:
                # Get price at this time for the angle
                engine = AngleEngine(
                    setup.pivot_pair,
                    self.config.price_scale,
                    self.config.time_scale
                )
                angle_price = engine.get_price_at_time(
                    angle_line.angle_degrees, 
                    current_time
                )
                
                # Check if price is near this angle
                tolerance = abs(angle_price * self.config.angle_touch_tolerance / 100)
                if abs(current_price - angle_price) <= tolerance:
                    active_angle = angle_line.name
                    
                    # Log the touch
                    self.event_logger.log_angle_touch(
                        timestamp=current_time,
                        price=current_price,
                        angle_name=angle_line.name,
                        tolerance_percent=self.config.angle_touch_tolerance
                    )
                    
                    # Check for breach
                    if self._check_breach(current_price, angle_price, setup.pivot_pair.scenario):
                        direction = "up" if current_price > angle_price else "down"
                        close_count = self._count_consecutive_closes(direction)
                        
                        if close_count >= self.config.confirmation_closes:
                            self.event_logger.log_angle_breach(
                                timestamp=current_time,
                                price=current_price,
                                angle_name=angle_line.name,
                                direction=direction,
                                close_count=close_count
                            )
            
            # Check horizontal target
            if setup.horizontal_target:
                ht_tolerance = abs(setup.horizontal_target.price * self.config.angle_touch_tolerance / 100)
                if abs(current_price - setup.horizontal_target.price) <= ht_tolerance:
                    near_target = True
                    self.event_logger.log_event(
                        timestamp=current_time,
                        event_type=EventType.HORIZONTAL_TOUCH,
                        price=current_price
                    )
        
        # Calculate momentum (simplified - would use TradingView indicators in frontend)
        momentum = self._calculate_simple_momentum(bar_index)
        
        # Log indicator snapshot
        self.event_logger.log_indicator_snapshot(
            timestamp=current_time,
            indicators=momentum.to_dict()
        )
        
        return StudyState(
            current_index=bar_index,
            current_price=current_price,
            current_time=current_time,
            pivot_pairs=self.pivot_pairs,
            angle_setups=self.angle_setups,
            momentum=momentum,
            active_angle=active_angle,
            near_target=near_target
        )
    
    def run_batch(self) -> Dict:
        """
        Run study on all data (batch mode).
        
        Returns:
            Dictionary with results and statistics
        """
        if not self.initialized:
            self.initialize()
        
        # Process each bar
        for i in range(len(self.df)):
            self.process_bar(i)
        
        return {
            "total_bars": len(self.df),
            "pivot_pairs": [pp.to_dict() for pp in self.pivot_pairs],
            "angle_setups": [ase.to_dict() for ase in self.angle_setups],
            "event_statistics": self.event_logger.get_statistics()
        }
    
    def get_current_state(self) -> StudyState:
        """Get current study state"""
        if self.current_index >= len(self.df):
            self.current_index = len(self.df) - 1
        
        row = self.df.iloc[self.current_index]
        momentum = self._calculate_simple_momentum(self.current_index)
        
        return StudyState(
            current_index=self.current_index,
            current_price=float(row['close']),
            current_time=int(row['timestamp']),
            pivot_pairs=self.pivot_pairs,
            angle_setups=self.angle_setups,
            momentum=momentum
        )
    
    def get_drawing_data(self) -> Dict:
        """
        Get data needed for drawing angle lines on chart.
        
        Returns:
            Dictionary with drawing coordinates
        """
        drawings = {
            "pivots": [],
            "angle_lines": [],
            "horizontal_targets": []
        }
        
        # Get end time for lines
        end_time = int(self.df.iloc[-1]['timestamp'])
        
        for setup in self.angle_setups:
            # Pivot markers
            drawings["pivots"].append({
                "time": setup.pivot_pair.first_pivot.timestamp,
                "price": setup.pivot_pair.first_pivot.price,
                "type": setup.pivot_pair.first_pivot.pivot_type.value,
                "label": "First"
            })
            drawings["pivots"].append({
                "time": setup.pivot_pair.second_pivot.timestamp,
                "price": setup.pivot_pair.second_pivot.price,
                "type": setup.pivot_pair.second_pivot.pivot_type.value,
                "label": "Second"
            })
            
            # Angle lines
            engine = AngleEngine(
                setup.pivot_pair,
                self.config.price_scale,
                self.config.time_scale
            )
            
            for angle_line in setup.angle_lines:
                coords = engine.get_line_coordinates(angle_line, end_time)
                drawings["angle_lines"].append({
                    "name": angle_line.name,
                    "color": angle_line.color,
                    "points": coords,
                    "pair_type": setup.pivot_pair.pair_type
                })
            
            # Horizontal target
            if setup.horizontal_target:
                drawings["horizontal_targets"].append({
                    "price": setup.horizontal_target.price,
                    "start_time": setup.horizontal_target.vertical_time,
                    "end_time": end_time,
                    "pair_type": setup.pivot_pair.pair_type
                })
        
        return drawings
    
    def export_events(self, filepath: str, format: str = "json"):
        """
        Export logged events.
        
        Args:
            filepath: Output file path
            format: "json" or "csv"
        """
        if format == "csv":
            self.event_logger.export_csv(filepath)
        else:
            self.event_logger.export_json(filepath)
    
    def _check_breach(
        self, 
        current_price: float, 
        angle_price: float,
        scenario: Scenario
    ) -> bool:
        """Check if price has breached the angle level"""
        if scenario == Scenario.SCENARIO_1:
            # Rising from low - breach is when price goes above angle
            return current_price > angle_price
        else:
            # Falling from high - breach is when price goes below angle
            return current_price < angle_price
    
    def _count_consecutive_closes(self, direction: str) -> int:
        """Count consecutive closes in the same direction"""
        if len(self._last_closes) < 2:
            return 0
        
        count = 0
        for i in range(len(self._last_closes) - 1, 0, -1):
            if direction == "up" and self._last_closes[i] > self._last_closes[i-1]:
                count += 1
            elif direction == "down" and self._last_closes[i] < self._last_closes[i-1]:
                count += 1
            else:
                break
        
        return count
    
    def _calculate_simple_momentum(self, bar_index: int) -> MomentumState:
        """
        Calculate simple momentum indicators.
        
        Note: In production, these would be calculated by TradingView's
        built-in indicators on the frontend.
        """
        if bar_index < 21:
            return MomentumState()
        
        # Simple EMA calculations
        closes = self.df['close'].iloc[:bar_index+1].astype(float)
        
        ema_9 = closes.ewm(span=9, adjust=False).mean().iloc[-1]
        ema_21 = closes.ewm(span=21, adjust=False).mean().iloc[-1]
        
        # EMA signal
        if ema_9 > ema_21:
            ema_signal = "bullish"
        elif ema_9 < ema_21:
            ema_signal = "bearish"
        else:
            ema_signal = "neutral"
        
        # Simple RSI
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        
        rs = gain.iloc[-1] / loss.iloc[-1] if loss.iloc[-1] != 0 else 0
        rsi = 100 - (100 / (1 + rs)) if rs != 0 else 50
        
        if rsi > 50:
            rsi_signal = "bullish"
        elif rsi < 50:
            rsi_signal = "bearish"
        else:
            rsi_signal = "neutral"
        
        # Overall momentum
        bullish_count = sum(1 for s in [ema_signal, rsi_signal] if s == "bullish")
        bearish_count = sum(1 for s in [ema_signal, rsi_signal] if s == "bearish")
        
        if bullish_count >= 2:
            overall = "bullish"
            confidence = bullish_count / 2
        elif bearish_count >= 2:
            overall = "bearish"
            confidence = bearish_count / 2
        else:
            overall = "neutral"
            confidence = 0.5
        
        return MomentumState(
            ema_9=ema_9,
            ema_21=ema_21,
            ema_signal=ema_signal,
            rsi=rsi,
            rsi_signal=rsi_signal,
            overall_momentum=overall,
            confidence=confidence
        )
