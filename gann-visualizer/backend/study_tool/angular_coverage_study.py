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
from .intersection_detector import IntersectionDetector


# Default configuration
DEFAULT_CONFIG = {
    'left_bars': 5,
    'right_bars': 5,
    'line_extension_bars': 100, # Initial extension, will be adaptive
    'fraction_colors': {
        1/8: '#FF5252', 1/4: '#FF5252', 3/8: '#FF5252', 
        1/2: '#2196F3', 
        5/8: '#4CAF50', 3/4: '#4CAF50', 7/8: '#4CAF50',
        1.0: '#FFFFFF'
    },
    'main_color': '#FFFFFF',
    'main_line_width': 1,
    'fraction_line_width': 2,
    'scale_ratio': 1.0,
    'breach_mode': 'wick',      # 'wick' or 'close' (Rule 4)
    'show_intersection_labels': False, # Whether to draw price text on hit
    'max_historical_fans': 3,   # Cap on fans when looking backwards for context
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
            # fractions=self.config['fractions'], # Fractions are now derived from fraction_colors keys
            fraction_colors=self.config['fraction_colors'],
            main_color=self.config['main_color'],
            line_extension_bars=self.config['line_extension_bars'],
            main_line_width=self.config['main_line_width'],
            fraction_line_width=self.config['fraction_line_width'],
            scale_ratio=self.config['scale_ratio']
        )
        
        self.intersection_detector = IntersectionDetector()

        # Track active fan keys for diffing (old vs new set)
        self._active_fan_keys: Dict[str, str] = {}  # fan_key -> engine_fan_id
        
        # State machine persistent roster: fan_id -> fan_data
        self._persisted_fans: Dict[str, Dict] = {}
        self._is_initialized = False

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

        # 3. Detect intersections for this bar
        current_candle = candles[bar_index]
        events = self.intersection_detector.detect(current_candle, self.angle_engine.active_fans, bar_index)
        if events:
            for event in events:
                if event.fan_id in self.angle_engine.active_fans:
                    fan_obj = self.angle_engine.active_fans[event.fan_id]
                    # Store the event and label ID in the fan object
                    fan_obj.intersections.append(event)
                    
                    label_id = f"hit_{event.fan_id}_{event.line_id}_{event.time}_{event.price}"
                    fan_obj.label_ids.append(label_id)

                    try:
                        import os
                        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
                        os.makedirs(log_dir, exist_ok=True)
                        log_file = os.path.join(log_dir, 'intersections.csv')
                        
                        frac_str = str(event.fraction) if event.fraction is not None else "Horizontal"
                        log_line = f"{event.time},{event.priority_label},{frac_str},{event.price}\n"
                        
                        if not os.path.exists(log_file):
                            with open(log_file, 'w') as f:
                                f.write("Timestamp,FanIdentity,Fraction,Price\n")
                        with open(log_file, 'a') as f:
                            f.write(log_line)
                    except Exception as e:
                        print(f"Failed to log intersection: {e}")

                    # Compute fraction display name and color
                    if event.fraction is None:
                        frac_name = "Horizontal"
                        color = '#FFFFFF'
                    else:
                        frac_map = {0.125: '1/8', 0.25: '1/4', 0.375: '3/8', 0.5: '1/2', 0.625: '5/8', 0.75: '3/4', 0.875: '7/8', 1.0: '1/1'}
                        closest_frac = min(frac_map.keys(), key=lambda k: abs(k - event.fraction))
                        if abs(closest_frac - event.fraction) < 0.01:
                            frac_name = frac_map[closest_frac]
                        else:
                            frac_name = f"{event.fraction:.2f}"
                        color = '#FFEB3B'

                    fan_display_name = event.fan_id.replace("Fan_", "").replace("_", "-")

                    # ALWAYS emit intersection event data for the Price Interactions tab
                    if 'intersection_events' not in result:
                        result['intersection_events'] = []
                    result['intersection_events'].append({
                        'time': event.time,
                        'fan': event.priority_label,
                        'fanIdentity': fan_display_name,
                        'fraction': frac_name,
                        'price': event.price
                    })

                    # Optionally draw price_label on chart (cosmetic toggle)
                    if self.config.get('show_intersection_labels', False):
                        text = f"{event.priority_label} Hit {frac_name}"
                        result['drawings'].append({
                            'type': 'price_label',
                            'id': label_id,
                            'points': [{'time': event.time, 'price': event.price}],
                            'options': {
                                'text': text,
                                'fanLabel': event.priority_label,
                                'fanIdentity': fan_display_name,
                                'color': color, 
                                'textcolor': '#000000'
                            }
                        })

        # 4. Save state
        result['state'] = self._get_state()
        
        if len(result['drawings']) > 0 or len(result['remove_drawings']) > 0:
            self.log(f"[Study] process_bar sending {len(result['drawings'])} drawings, {len(result['remove_drawings'])} removes")

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
        # Generate raw un-capped logical fans
        logical_fans = FanManager.find_active_fans(
            confirmed_pivots=self.pivot_detector.confirmed_pivots,
            candles=candles,
            current_bar_index=current_bar_index,
            breach_mode=self.config['breach_mode']
        )

        logical_fan_map = {f['fan_id']: f for f in logical_fans}

        # Initialize State Machine if this is the first sync
        if not self._is_initialized:
            # On first load, only grab up to max_historical_fans to prevent clutter
            limit = self.config.get('max_historical_fans', 3)
            for i, fan in enumerate(logical_fans):
                if i >= limit:
                    break
                self._persisted_fans[fan['fan_id']] = fan
            self._is_initialized = True
        else:
            # 1. Cull fans that broke mathematical/breach validity
            keys_to_remove = []
            for fan_id in self._persisted_fans:
                if fan_id not in logical_fan_map:
                    keys_to_remove.append(fan_id)
            
            for key in keys_to_remove:
                del self._persisted_fans[key]
                
            # 2. Add brand new fans (Anchor must be the absolutely most recent pivot)
            if self.pivot_detector.confirmed_pivots:
                latest_pivot = self.pivot_detector.confirmed_pivots[-1]
                for fan in logical_fans:
                    if fan['anchor']['label'] == latest_pivot.label:
                        self._persisted_fans[fan['fan_id']] = fan

        # Re-sort persistent roster by anchor timestamp (descending) to assign correct P-labels
        sorted_roster = sorted(
            self._persisted_fans.values(),
            key=lambda f: f['anchor']['time'],
            reverse=True
        )

        # Build final map for AngleEngine syncing
        new_fan_map = {}
        for priority_idx, fan in enumerate(sorted_roster):
            # Update the priority tracking info so line labels stay accurate
            fan['priority'] = priority_idx
            
            # Embed the full fan identity in the priority label so it propagates to UI controls
            fan_display_name = fan['fan_id'].replace("Fan_", "").replace("_", "-")
            fan['priority_label'] = f"P{priority_idx + 1} ({fan_display_name})"
            new_fan_map[fan['fan_id']] = fan

        new_keys = set(new_fan_map.keys())
        old_keys = set(self._active_fan_keys.keys())

        # Remove invalidated fans (in old set but not in new)
        for key in old_keys - new_keys:
            engine_fan_id = self._active_fan_keys[key]
            self.log(f"[Study] Removing fan: {key}")

            # Add removal commands for all lines in this fan
            if engine_fan_id in self.angle_engine.active_fans:
                fan_obj = self.angle_engine.active_fans[engine_fan_id]
                for line in fan_obj.lines:
                    result['remove_drawings'].append(line.id)
                for label_id in fan_obj.label_ids:
                    result['remove_drawings'].append(label_id)
                self.angle_engine.remove_fan(engine_fan_id)

            del self._active_fan_keys[key]

        # Create new fans (in new set but not in old)
        for key in new_keys - old_keys:
            fan_data = new_fan_map[key]
            self.log(f"[Study] Creating fan: {key} ({fan_data['priority_label']})")

            fan_obj = self.angle_engine.create_fan(
                from_pivot=fan_data['target'],   # Target is the "from" (left pivot)
                to_pivot=fan_data['anchor'],      # Anchor is the "to" (right pivot)
                current_candles=candles[:current_bar_index + 1],
                fan_id=fan_data['fan_id'],
                priority_label=fan_data['priority_label']
            )

            # Store mapping
            self._active_fan_keys[key] = fan_obj.id

            # Generate drawing commands
            drawings = self.angle_engine.fan_to_drawing_commands(fan_obj)
            result['drawings'].extend(drawings)
            


        # Update existing fans if their priority label changed
        for key in new_keys & old_keys:
            fan_data = new_fan_map[key]
            engine_fan_id = self._active_fan_keys[key]
            if engine_fan_id in self.angle_engine.active_fans:
                fan_obj = self.angle_engine.active_fans[engine_fan_id]
                if fan_obj.priority_label != fan_data['priority_label']:
                    self.log(f"[Study] Promoting fan: {key} from {fan_obj.priority_label} to {fan_data['priority_label']}")
                    fan_obj.priority_label = fan_data['priority_label']
                    
                    # We need to re-send to frontend because options.fanLabel is used for visibility
                    # First, queue the old lines for removal
                    for line in fan_obj.lines:
                        result['remove_drawings'].append(line.id)
                        
                    # Queue old labels for removal
                    for label_id in fan_obj.label_ids:
                        result['remove_drawings'].append(label_id)
                    fan_obj.label_ids.clear()
                        
                    # Then generate and append the new lines with the updated label
                    drawings = self.angle_engine.fan_to_drawing_commands(fan_obj)
                    result['drawings'].extend(drawings)
                    
                    # Re-generate the updated labels
                    for event in fan_obj.intersections:
                        event.priority_label = fan_obj.priority_label
                        
                        label_id = f"hit_{event.fan_id}_{event.line_id}_{event.time}_{event.price}"
                        fan_obj.label_ids.append(label_id)

                        if event.fraction is None:
                            frac_name = "Horizontal"
                            color = '#FFFFFF'
                        else:
                            frac_map = {0.125: '1/8', 0.25: '1/4', 0.375: '3/8', 0.5: '1/2', 0.625: '5/8', 0.75: '3/4', 0.875: '7/8', 1.0: '1/1'}
                            closest_frac = min(frac_map.keys(), key=lambda k: abs(k - event.fraction))
                            if abs(closest_frac - event.fraction) < 0.01:
                                frac_name = frac_map[closest_frac]
                            else:
                                frac_name = f"{event.fraction:.2f}"
                            color = '#FFEB3B'
                            
                        # Extract pure fan name (e.g., "Fan_H5_L2" -> "H5-L2")
                        fan_display_name = event.fan_id.replace("Fan_", "").replace("_", "-")
                            
                        # Only draw chart labels if toggle is on
                        if self.config.get('show_intersection_labels', False):
                            text = f"{event.priority_label} Hit {frac_name}"
                            result['drawings'].append({
                                'type': 'price_label',
                                'id': label_id,
                                'points': [{'time': event.time, 'price': event.price}],
                                'options': {
                                    'text': text,
                                    'fanLabel': event.priority_label,
                                    'fanIdentity': fan_display_name,
                                    'color': color, 
                                    'textcolor': '#000000'
                                }
                            })

        # Add pivot markers for debugging
        self._add_fan_markers(result)

    def _add_fan_markers(self, result: Dict[str, Any]):
        """Add pivot markers ONLY for active persisted fan pivots."""
        seen = set()
        for fan in self._persisted_fans.values():
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
                    'text': a.get('label', 'A')
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
                    'text': t.get('label', 'T')
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
            'intersection_detector': self.intersection_detector.get_state(),
            'active_fan_keys': dict(self._active_fan_keys),
            'persisted_fans': dict(self._persisted_fans),
            'is_initialized': self._is_initialized,
            'config': self.config
        }

    def _restore_state(self, state: Dict[str, Any]):
        """Restore state from serialized form."""
        if 'pivot_detector' in state:
            self.pivot_detector.restore_state(state['pivot_detector'])
        if 'angle_engine' in state:
            self.angle_engine.restore_state(state['angle_engine'])
        if 'intersection_detector' in state:
            self.intersection_detector.restore_state(state['intersection_detector'])
        if 'active_fan_keys' in state:
            self._active_fan_keys = state['active_fan_keys']
        if 'persisted_fans' in state:
            self._persisted_fans = state['persisted_fans']
        if 'is_initialized' in state:
            self._is_initialized = state['is_initialized']
        if 'config' in state:
            self.config = {**DEFAULT_CONFIG, **state['config']}


# Factory function
def create_study(config: Optional[Dict[str, Any]] = None) -> AngularPriceCoverageStudy:
    return AngularPriceCoverageStudy(config)
