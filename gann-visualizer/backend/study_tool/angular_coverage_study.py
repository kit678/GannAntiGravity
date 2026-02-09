"""
Angular Price Coverage Study (v3.0 - Stack Persistence)

Main study orchestrator that implements Master Protocol v3.0:
1. Persistent Pivot Stacks (Inner/Outer)
2. Immediate Fan rendering on load
3. Configuration Gates (ShowRecursiveInnerFans, ShowRecursiveOuterFans)

This replaces the old Reactive/Scenario-based logic.
"""

from typing import Dict, List, Any, Optional
import os
import logging
from datetime import datetime
from .pivot_detector import PivotDetector
from .angle_engine import AngleEngine
from .pivot_selector import PivotSelector, PivotStacks


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
    'show_recursive_inner_fans': True,  # Draw all inner fans in stack
    'show_recursive_outer_fans': True,  # Draw all outer fans in stack
    'max_inner_fans': 5,
    'max_outer_fans': 3
}


class AngularPriceCoverageStudy:
    """
    Angular Price Coverage Study (v3.0)
    
    Persistently maintains PivotStacks (Inner/Outer) and renders fans
    immediately based on the active stack state.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the study with configuration.
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
        
        # Persistent State (v3.0)
        self.stacks: Optional[PivotStacks] = None
        self.active_fan_ids: Dict[str, str] = {}  # Map: pair_id -> fan_id
        self._initialized: bool = False  # Track whether initialize_history has been called
        
        # Setup File Logger
        log_dir = os.path.join(os.getcwd(), 'logs', 'study_debug')
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = os.path.join(log_dir, f'angular_study_{timestamp}.log')
        
        self.logger = logging.getLogger(f'AngularStudy_{timestamp}')
        self.logger.setLevel(logging.DEBUG)
        
        # Avoid duplicate handlers if re-initialized
        if not self.logger.handlers:
            fh = logging.FileHandler(log_file)
            fh.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
            self.logger.addHandler(fh)
        
        self.log(f"Initialized AngularPriceCoverageStudy. Config: {self.config}")

    def log(self, msg: str):
        """Helper to log to file (console disabled to prevent flooding)."""
        # print(msg)  # Disabled to prevent log flooding
        if hasattr(self, 'logger'):
            self.logger.info(msg)
    
    def initialize_history(self, candles: List[Dict[str, Any]]):
        """
        STEP 2: Immediate Historical Initialization.
        
        Scans ALL provided history to:
        1. Detect confirmed pivots up to the last candle.
        2. Build the initial PivotStacks (Active Context).
        """
        self.log(f"[Study] initialize_history called with {len(candles)} candles")
        
        # Optimization: We only need to run detection where it's possible
        start_idx = self.config['left_bars'] + self.config['right_bars']
        
        if len(candles) <= start_idx:
            self.log("[Study] Not enough candles for pivot detection")
            return

        # Explicitly reset detector before scanning history
        self.pivot_detector.reset()
        
        count_pivots_found = 0
        for i in range(start_idx, len(candles)):
            res = self.pivot_detector.detect_pivots(candles, i)
            if res.get('pivot_high') or res.get('pivot_low'):
                count_pivots_found += 1
            
        self.log(f"[Study] Historical detection complete. Found {len(self.pivot_detector.confirmed_pivots)} confirmed pivots.")
        
        # Build Stacks based on FINAL history state
        current_bar = candles[-1]
        last_pivot = self._get_last_pivot()
        
        if last_pivot:
            self.log(f"[Study] Last Pivot: {last_pivot.pivot_type} at {last_pivot.time}")
            self.stacks = PivotSelector.select_stacks(
                current_price=float(current_bar['close']),
                current_time=int(current_bar['time']),
                confirmed_pivots=self.pivot_detector.confirmed_pivots,
                last_pivot=last_pivot
            )
            if self.stacks:
                self.log(f"[Study] Stacks initialized: Anchor={self.stacks.anchor['time']}, Inner={len(self.stacks.inner_stack)}, Outer={len(self.stacks.outer_stack)}")
            else:
                self.log("[Study] select_stacks returned None")
        else:
            self.log("[Study] No Last Pivot found after scanning history.")
    
    def process_bar(
        self,
        candles: List[Dict[str, Any]],
        bar_index: int,
        state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process a single bar and return drawing updates.
        """
        # Restore state if provided (for Replay consistency)
        if state:
            self._restore_state(state)
        
        # Initialize history if this is the first call (and not yet initialized)
        # This handles the "Chart Load" scenario in Replay where we start at bar_index X
        if not self._initialized and len(candles) > self.config['left_bars'] + self.config['right_bars']:
            # We treat the history *up to this bar* as the initialization set
            # This ensures we don't look into the future during replay
            self.log(f"[Study] First process_bar call at index {bar_index}. Running initialize_history.")
            history_subset = candles[:bar_index+1]
            self.initialize_history(history_subset)
            self._initialized = True  # Mark as initialized

        result = {
            'type': 'drawing_update',
            'drawings': [],
            'pivot_markers': [],
            'remove_drawings': [],
            'state': {}
        }
        
        # 1. Detect Pivots at this new bar
        # (This might add a new pivot to pivot_detector.confirmed_pivots)
        detection_result = self.pivot_detector.detect_pivots(candles, bar_index)
        
        # 2. Update Context/Stacks
        # If a new pivot was confirmed, we MUST regenerate the Stacks
        # Or if the price broke structure (Kill Switch - Step 4, currently skipped)
        
        # For Step 2, we just rebuild stacks every bar to be safe/simple
        # Optimization can come later.
        
        current_bar = candles[bar_index]
        last_pivot = self._get_last_pivot()
        
        # Re-evaluate stacks at every step (State Persistence via Re-selection)
        # This ensures if a new pivot forms, the stack updates.
        if last_pivot:
             new_stacks = PivotSelector.select_stacks(
                current_price=float(current_bar['close']),
                current_time=int(current_bar['time']),
                confirmed_pivots=self.pivot_detector.confirmed_pivots,
                last_pivot=last_pivot
            )
             
             # Check if stacks changed significantly needed for redraw?
             # For now, we'll just update self.stacks
             # In Step 3 (Drawing), we will use this to draw fans.
             self.stacks = new_stacks

        # 3. Draw Fans (Placeholder for Step 3 - Currently NO OP to isolate Step 2)
        # self._update_drawings(result, candles)
        
        # 4. Markers (Visualize the pivots for debugging Step 2)
        if self.stacks:
             self._add_stack_markers(result)
        
        # Save state
        result['state'] = self._get_state()
        
        return result

    def _get_last_pivot(self):
        """Helper to get the last CONFIRMED pivot from detector."""
        if self.pivot_detector.confirmed_pivots:
            return self.pivot_detector.confirmed_pivots[-1]
        return None

    def _add_stack_markers(self, result: Dict[str, Any]):
        """Add markers for all pivots in the active stacks."""
        # Anchor
        if self.stacks.anchor:
            p = self.stacks.anchor
            result['pivot_markers'].append({
                'id': f"anchor_{p['time']}",
                'type': f"anchor_{p['type']}", # Special type for visual debugging?
                'time': p['time'],
                'price': p['price'],
                'bar_index': p.get('bar_index', 0),
                'text': 'A' # Label as Anchor
            })
            
        # Inner Stack
        for i, p in enumerate(self.stacks.inner_stack):
            result['pivot_markers'].append({
                'id': f"inner_{i}_{p['time']}",
                'type': f"pivot_{p['type']}",
                'time': p['time'],
                'price': p['price'],
                'bar_index': p.get('bar_index', 0),
                'text': f"I{i}"
            })

        # Outer Stack
        for i, p in enumerate(self.stacks.outer_stack):
            result['pivot_markers'].append({
                'id': f"outer_{i}_{p['time']}",
                'type': f"pivot_{p['type']}",
                'time': p['time'],
                'price': p['price'],
                'bar_index': p.get('bar_index', 0),
                'text': f"O{i}"
            })

    def _get_state(self) -> Dict[str, Any]:
        """Get combined state."""
        # We don't serialize 'stacks' directly because they are derived from pivots
        # But for efficiency we could.
        # For now, just serialize detector state.
        return {
            'pivot_detector': self.pivot_detector.get_state(),
            'config': self.config
        }
    
    def _restore_state(self, state: Dict[str, Any]):
        """Restore state."""
        if 'pivot_detector' in state:
            self.pivot_detector.restore_state(state['pivot_detector'])
        if 'config' in state:
            self.config = {**DEFAULT_CONFIG, **state['config']}
            
        # Note: self.stacks will be `None` after restore
        # It will be rebuilt in process_bar via initialize_history or re-select
        self.stacks = None

# Factory function
def create_study(config: Optional[Dict[str, Any]] = None) -> AngularPriceCoverageStudy:
    return AngularPriceCoverageStudy(config)
