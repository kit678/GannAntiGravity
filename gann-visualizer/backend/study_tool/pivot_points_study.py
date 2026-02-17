"""
Pivot Points Study

A standalone indicator that uses the robust PivotDetector (from Angular Price Coverage)
to identify and plot pivot highs and lows, without drawing fans or angles.

PATTERN: Follows the same architecture as AngularPriceCoverageStudy:
  - initialize_history() scans all history in one pass
  - process_bar() returns ALL confirmed pivots as markers (not just the delta)
  - _restore_state() / _get_state() for fast-path caching in main.py
"""

from typing import Dict, List, Any, Optional
from .pivot_detector import PivotDetector


class PivotPointsStudy:
    """
    Pivot Points Only Study
    
    Uses the shared PivotDetector logic to find market structures
    consistent with the Angular Price Coverage strategy.
    
    On every process_bar call, returns markers for ALL confirmed pivots
    (same pattern as AngularPriceCoverageStudy._add_stack_markers).
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.left_bars = self.config.get('left_bars', 5)
        self.right_bars = self.config.get('right_bars', 5)
        
        # Initialize the shared detector
        self.pivot_detector = PivotDetector(
            left_bars=self.left_bars,
            right_bars=self.right_bars
        )
        
        # State tracking
        self._initialized = False

    def initialize_history(self, candles: List[Dict], up_to_index: int = None):
        """
        Scan ALL provided history to detect confirmed pivots.
        Mirrors AngularPriceCoverageStudy.initialize_history().
        """
        if up_to_index is None:
            up_to_index = len(candles)
            
        start_idx = self.left_bars + self.right_bars
        
        if up_to_index <= start_idx:
            return
        
        self.pivot_detector.reset()
        
        for i in range(start_idx, up_to_index):
            self.pivot_detector.detect_pivots(candles, i)
        
        self._initialized = True

    def process_bar(self, candles: List[Dict], bar_index: int, state: Optional[Dict] = None) -> Dict:
        """
        Process a single bar to detect pivots.
        
        KEY DESIGN (matches Angular pattern):
        - On first call: runs initialize_history on candles[:bar_index+1]
        - Then detects pivot at current bar_index
        - Returns markers for ALL confirmed pivots (not just delta)
        """
        # Restore state if provided (fast path)
        if state:
            self.pivot_detector.restore_state(state.get('detector', {}))
            self._initialized = True
        
        # Auto-initialize history on first run (same as Angular lines 160-166)
        elif not self._initialized and len(candles) > self.left_bars + self.right_bars:
            history_subset = candles[:bar_index + 1]
            self.initialize_history(history_subset, len(history_subset))
            self._initialized = True

        # Run detection on current bar (may add a new confirmed pivot)
        self.pivot_detector.detect_pivots(candles, bar_index)
        
        # Build markers for ALL confirmed pivots (like Angular's _add_stack_markers)
        output_markers = self._build_all_markers()

        return {
            'type': 'drawing_update',
            'drawings': [], 
            'pivot_markers': output_markers,
            'remove_drawings': [],
            'state': self._get_state()
        }

    def _build_all_markers(self) -> List[Dict]:
        """
        Return markers for ALL confirmed pivots.
        This is the equivalent of AngularPriceCoverageStudy._add_stack_markers().
        """
        markers = []
        for p in self.pivot_detector.confirmed_pivots:
            is_high = p.pivot_type == 'high'
            markers.append({
                'id': f"{'ph' if is_high else 'pl'}_{p.time}",
                'type': 'pivot_high' if is_high else 'pivot_low',
                'time': p.time,
                'price': p.price,
                'bar_index': p.bar_index,
                'text': '',
                'color': '#26a69a' if is_high else '#ef5350',
                'shape': 'arrow_down' if is_high else 'arrow_up',
                'location': 'aboveBar' if is_high else 'belowBar'
            })
        return markers

    def restore_state(self, state: Dict):
        """Restore study state from serialized form (for fast-path caching)."""
        if not state:
            return
        detector_state = state.get('detector', {})
        if detector_state:
            self.pivot_detector.restore_state(detector_state)
        self._initialized = True

    def _get_state(self) -> Dict:
        return {
            'detector': self.pivot_detector.get_state(),
            'config': {
                'left_bars': self.left_bars,
                'right_bars': self.right_bars
            }
        }
