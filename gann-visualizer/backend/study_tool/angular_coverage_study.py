"""
Angular Price Coverage Study

Main study orchestrator that combines pivot detection and angle drawing
for the Angular Price Coverage analysis tool.

This study processes candles bar-by-bar during replay and outputs
drawing commands for the frontend to render.
"""

from typing import Dict, List, Any, Optional
from .pivot_detector import PivotDetector
from .angle_engine import AngleEngine


# Default configuration
DEFAULT_CONFIG = {
    'left_bars': 5,
    'right_bars': 5,
    'fractions': [7/8, 3/4, 1/2, 1/4, 1/8],
    'fraction_colors': ['#c62828', '#ad1457', '#6a1b9a', '#283593', '#00695c'],
    'main_color': '#FF6600',
    'line_extension_bars': 50,
    'remove_completed_fans': True,
    'main_line_width': 3,
    'fraction_line_width': 2,
    'scale_ratio': 1.0  # Default scale ratio (price points per bar)
}


class AngularPriceCoverageStudy:
    """
    Angular Price Coverage Study
    
    Detects pivot highs and lows, draws Gann angle fans between alternating
    pivots, and optionally removes completed fans to declutter the chart.
    
    Usage:
        study = AngularPriceCoverageStudy(config)
        result = study.process_bar(candles, bar_index, state)
        # result contains drawings and updated state
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the study with configuration.
        
        Args:
            config: Optional configuration dict (uses defaults if not provided)
        """
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        
        # Initialize components
        self.pivot_detector = PivotDetector(
            left_bars=self.config['left_bars'],
            right_bars=self.config['right_bars']
        )
        
        self.angle_engine = AngleEngine(
            fractions=self.config['fractions'],
            fraction_colors=self.config['fraction_colors'],
            main_color=self.config['main_color'],
            line_extension_bars=self.config['line_extension_bars'],
            main_line_width=self.config['main_line_width'],
            fraction_line_width=self.config['fraction_line_width'],
            scale_ratio=self.config['scale_ratio']
        )
    
    def process_bar(
        self,
        candles: List[Dict[str, Any]],
        bar_index: int,
        state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process a single bar and return drawing updates.
        
        Args:
            candles: All candles up to and including current bar
            bar_index: Index of current bar being processed
            state: Previous state (for replay continuation)
            
        Returns:
            Dict with:
                - type: 'drawing_update'
                - drawings: List of drawing commands
                - pivot_markers: List of pivot marker commands
                - remove_drawings: List of drawing IDs to remove
                - state: Updated state for next bar
        """
        # Restore state if provided
        if state:
            self._restore_state(state)
        
        result = {
            'type': 'drawing_update',
            'drawings': [],
            'pivot_markers': [],
            'remove_drawings': [],
            'state': {}
        }
        
        # Detect pivots at this bar
        pivot_result = self.pivot_detector.detect_pivots(candles, bar_index)
        
        # Add pivot markers
        if pivot_result['pivot_high']:
            ph = pivot_result['pivot_high']
            result['pivot_markers'].append({
                'type': 'pivot_high',
                'time': ph.time,
                'price': ph.price,
                'bar_index': ph.bar_index
            })
        
        if pivot_result['pivot_low']:
            pl = pivot_result['pivot_low']
            result['pivot_markers'].append({
                'type': 'pivot_low',
                'time': pl.time,
                'price': pl.price,
                'bar_index': pl.bar_index
            })
        
        # Create new fan if pivot pair is complete
        if pivot_result['new_fan']:
            fan_data = pivot_result['new_fan']
            fan = self.angle_engine.create_fan(
                from_pivot=fan_data['from'],
                to_pivot=fan_data['to'],
                current_candles=candles
            )
            
            # Add drawing commands for this fan
            result['drawings'].extend(
                self.angle_engine.fan_to_drawing_commands(fan)
            )
        
        # Check for completed fans
        if self.config['remove_completed_fans'] and bar_index < len(candles):
            current_bar = candles[bar_index]
            completed_fan_ids = []
            
            for fan_id in list(self.angle_engine.active_fans.keys()):
                if self.angle_engine.check_fan_completion(fan_id, current_bar):
                    completed_fan_ids.append(fan_id)
            
            # Add remove commands for completed fans
            for fan_id in completed_fan_ids:
                fan = self.angle_engine.active_fans.get(fan_id)
                if fan:
                    for line in fan.lines:
                        result['remove_drawings'].append(line.id)
                    self.angle_engine.remove_fan(fan_id)
        
        # Save state for next bar
        result['state'] = self._get_state()
        
        return result
    
    def reset(self):
        """Reset study state (call on new symbol/interval)"""
        self.pivot_detector.reset()
        self.angle_engine.active_fans = {}
    
    def _get_state(self) -> Dict[str, Any]:
        """Get combined state from all components"""
        return {
            'pivot_detector': self.pivot_detector.get_state(),
            'angle_engine': self.angle_engine.get_state(),
            'config': self.config
        }
    
    def _restore_state(self, state: Dict[str, Any]):
        """Restore state to all components"""
        if 'pivot_detector' in state:
            self.pivot_detector.restore_state(state['pivot_detector'])
        
        if 'angle_engine' in state:
            self.angle_engine.restore_state(state['angle_engine'])
        
        if 'config' in state:
            self.config = {**DEFAULT_CONFIG, **state['config']}


# Factory function for easy instantiation
def create_study(config: Optional[Dict[str, Any]] = None) -> AngularPriceCoverageStudy:
    """
    Create an Angular Price Coverage Study instance.
    
    Args:
        config: Optional configuration overrides
        
    Returns:
        Configured study instance
    """
    return AngularPriceCoverageStudy(config)
