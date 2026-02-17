"""
Angular Price Coverage Study (v4.0 - Unified Backward Traversal)

Main study orchestrator that implements Strategy v4.0:
1. Detect all pivots in historical data
2. Unified backward traversal to find active fans (Rules 1-6)
3. Sync fans with AngleEngine for rendering
4. Re-scan on every bar for live/replay propagation
"""

from typing import Dict, List, Any, Optional
import os
import logging
from datetime import datetime
from .pivot_detector import PivotDetector
from .angle_engine import AngleEngine
from .fan_manager import FanManager


# Default configuration
DEFAULT_CONFIG = {
    'left_bars': 5,
    'right_bars': 5,
    'fractions': [7/8, 3/4, 1/2, 1/4, 1/8],
    'fraction_colors': ['#c62828', '#ad1457', '#6a1b9a', '#283593', '#00695c'],
    'main_color': '#FF6600',
    'line_extension_bars': 50,
    'remove_completed_fans': True,
    'main_line_width': 1,
    'fraction_line_width': 2,
    'scale_ratio': 1.0,
    'max_fans': 3,              # Global fan limit (Rule 6)
    'breach_mode': 'wick',      # 'wick' or 'close' (Rule 4)
}


class AngularPriceCoverageStudy:
    """
    Angular Price Coverage Study (v4.0)

    Uses FanManager for unified backward traversal and AngleEngine for rendering.
    Same logic applies to chart load (history) and live/replay (forward propagation).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
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

        # Track active fan keys for diffing (old vs new set)
        self._active_fan_keys: Dict[str, str] = {}  # fan_key -> engine_fan_id
        self._initialized: bool = False

        # Setup File Logger
        log_dir = os.path.join(os.getcwd(), 'logs', 'study_debug')
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = os.path.join(log_dir, f'angular_study_{timestamp}.log')

        self.logger = logging.getLogger(f'AngularStudy_{timestamp}')
        self.logger.setLevel(logging.DEBUG)

        if not self.logger.handlers:
            fh = logging.FileHandler(log_file)
            fh.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
            self.logger.addHandler(fh)

        self.log(f"Initialized AngularPriceCoverageStudy v4.0. Config: {self.config}")

    def log(self, msg: str):
        """Helper to log to file."""
        if hasattr(self, 'logger'):
            self.logger.info(msg)

    def initialize_history(self, candles: List[Dict[str, Any]]):
        """
        Step 1: Detect all pivots from historical candle data.
        Then run the unified scan to find initial active fans.
        """
        self.log(f"[Study] initialize_history called with {len(candles)} candles")

        start_idx = self.config['left_bars'] + self.config['right_bars']

        if len(candles) <= start_idx:
            self.log("[Study] Not enough candles for pivot detection")
            return

        # Reset detector and scan entire history
        self.pivot_detector.reset()

        for i in range(start_idx, len(candles)):
            self.pivot_detector.detect_pivots(candles, i)

        self.log(f"[Study] Historical detection complete. Found {len(self.pivot_detector.confirmed_pivots)} confirmed pivots.")

    def process_bar(
        self,
        candles: List[Dict[str, Any]],
        bar_index: int,
        state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process a single bar: detect pivots, find active fans, sync drawings.
        Same logic for history and replay/live.
        """
        # Restore state if provided
        if state:
            self._restore_state(state)

        # Initialize history on first call
        if not self._initialized and len(candles) > self.config['left_bars'] + self.config['right_bars']:
            self.log(f"[Study] First process_bar at index {bar_index}. Running initialize_history.")
            history_subset = candles[:bar_index + 1]
            self.initialize_history(history_subset)
            self._initialized = True

        result = {
            'type': 'drawing_update',
            'drawings': [],
            'pivot_markers': [],
            'remove_drawings': [],
            'state': {}
        }

        # 1. Detect pivots at this bar
        self.pivot_detector.detect_pivots(candles, bar_index)

        # 2. Run unified backward traversal (same logic every bar)
        self._sync_fans(candles, bar_index, result)

        # 3. Save state
        result['state'] = self._get_state()

        return result

    def _sync_fans(
        self,
        candles: List[Dict[str, Any]],
        current_bar_index: int,
        result: Dict[str, Any]
    ):
        """
        Core sync: run FanManager, diff with current engine state,
        remove invalidated fans, create new ones.
        """
        # Get logically active fans from unified traversal
        logical_fans = FanManager.find_active_fans(
            confirmed_pivots=self.pivot_detector.confirmed_pivots,
            candles=candles,
            current_bar_index=current_bar_index,
            max_fans=self.config['max_fans'],
            breach_mode=self.config['breach_mode']
        )

        # Build new fan key map
        new_fan_map = {}
        for fan in logical_fans:
            key = f"{fan['anchor']['time']}_{fan['target']['time']}"
            new_fan_map[key] = fan

        new_keys = set(new_fan_map.keys())
        old_keys = set(self._active_fan_keys.keys())

        # Remove invalidated fans (in old set but not in new)
        for key in old_keys - new_keys:
            engine_fan_id = self._active_fan_keys[key]
            self.log(f"[Study] Removing fan: {key} (engine_id={engine_fan_id})")

            # Add removal commands for all lines in this fan
            if engine_fan_id in self.angle_engine.active_fans:
                fan_obj = self.angle_engine.active_fans[engine_fan_id]
                for line in fan_obj.lines:
                    result['remove_drawings'].append(line.id)
                self.angle_engine.remove_fan(engine_fan_id)

            del self._active_fan_keys[key]

        # Create new fans (in new set but not in old)
        for key in new_keys - old_keys:
            fan_data = new_fan_map[key]
            self.log(f"[Study] Creating fan: {key} ({fan_data['priority_label']})")

            fan_obj = self.angle_engine.create_fan(
                from_pivot=fan_data['target'],   # Target is the "from" (left pivot)
                to_pivot=fan_data['anchor'],      # Anchor is the "to" (right pivot)
                current_candles=candles[:current_bar_index + 1]
            )

            # Store mapping
            self._active_fan_keys[key] = fan_obj.id

            # Generate drawing commands
            drawings = self.angle_engine.fan_to_drawing_commands(fan_obj)
            result['drawings'].extend(drawings)

        # Add pivot markers for debugging
        self._add_fan_markers(logical_fans, result)

    def _add_fan_markers(self, logical_fans: List[Dict[str, Any]], result: Dict[str, Any]):
        """Add pivot markers for all active fan pivots."""
        seen = set()
        for fan in logical_fans:
            # Anchor marker
            a = fan['anchor']
            a_key = f"anchor_{a['time']}"
            if a_key not in seen:
                seen.add(a_key)
                result['pivot_markers'].append({
                    'id': a_key,
                    'type': f"pivot_{a['type']}",
                    'time': a['time'],
                    'price': a['price'],
                    'bar_index': a.get('bar_index', 0),
                    'text': 'A'
                })

            # Target marker
            t = fan['target']
            t_key = f"target_{t['time']}"
            if t_key not in seen:
                seen.add(t_key)
                result['pivot_markers'].append({
                    'id': t_key,
                    'type': f"pivot_{t['type']}",
                    'time': t['time'],
                    'price': t['price'],
                    'bar_index': t.get('bar_index', 0),
                    'text': fan['priority_label'][0]  # P, S, T
                })

    def get_state(self) -> Dict[str, Any]:
        """Public interface for state serialization (called by main.py)."""
        return self._get_state()

    def restore_state(self, state: Dict[str, Any]):
        """Public interface for state restoration (called by main.py)."""
        self._restore_state(state)

    def _get_state(self) -> Dict[str, Any]:
        """Get combined state for serialization."""
        return {
            'pivot_detector': self.pivot_detector.get_state(),
            'angle_engine': self.angle_engine.get_state(),
            'active_fan_keys': dict(self._active_fan_keys),
            'config': self.config
        }

    def _restore_state(self, state: Dict[str, Any]):
        """Restore state from serialized form."""
        if 'pivot_detector' in state:
            self.pivot_detector.restore_state(state['pivot_detector'])
        if 'angle_engine' in state:
            self.angle_engine.restore_state(state['angle_engine'])
        if 'active_fan_keys' in state:
            self._active_fan_keys = state['active_fan_keys']
        if 'config' in state:
            self.config = {**DEFAULT_CONFIG, **state['config']}


# Factory function
def create_study(config: Optional[Dict[str, Any]] = None) -> AngularPriceCoverageStudy:
    return AngularPriceCoverageStudy(config)
