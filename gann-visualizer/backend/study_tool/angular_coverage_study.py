"""
Angular Price Coverage Study (v2.0 - Hierarchical Framework)

Main study orchestrator that combines pivot detection and angle drawing
for the Angular Price Coverage analysis tool.

Key Features (v2.0):
- Supports Outer Container + Inner Sequence visualization
- Multiple simultaneous fans (Outer fan + Inner fans)
- Sequential promotion as horizontals are breached
- Proper cleanup when fans become irrelevant

This study processes candles bar-by-bar during replay and outputs
drawing commands for the frontend to render.
"""

from typing import Dict, List, Any, Optional
from .pivot_detector import PivotDetector
from .angle_engine import AngleEngine
from .pivot_selector import PivotSelector, PivotHierarchy


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
    'scale_ratio': 1.0,  # Default scale ratio (price points per bar)
    'max_inner_fans': 3,  # Maximum inner fans to display simultaneously
    'show_outer_fan': True,  # Whether to show the outer container fan
    'show_inner_fans': True,  # Whether to show inner sequence fans
    'outer_fan_opacity': 0.5,  # Opacity for outer fan lines (for visual distinction)
    'inner_fan_colors': ['#4CAF50', '#2196F3', '#9C27B0']  # Colors for inner fans
}


class AngularPriceCoverageStudy:
    """
    Angular Price Coverage Study (v2.0)
    
    Detects pivot highs and lows, draws Gann angle fans for BOTH the Outer
    Container and the Inner Sequence, providing a complete visualization
    of market structure.
    
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
        
        # Track current hierarchy state
        self.current_hierarchy: Optional[PivotHierarchy] = None
        self.active_fan_ids: Dict[str, str] = {}  # Map: pair_id -> fan_id
    
    def _get_last_pivot(self):
        """Get the most recent confirmed pivot."""
        last_pivot = None
        if self.pivot_detector.last_high_pivot and self.pivot_detector.last_low_pivot:
            if self.pivot_detector.last_high_pivot.time > self.pivot_detector.last_low_pivot.time:
                last_pivot = self.pivot_detector.last_high_pivot
            else:
                last_pivot = self.pivot_detector.last_low_pivot
        elif self.pivot_detector.last_high_pivot:
            last_pivot = self.pivot_detector.last_high_pivot
        elif self.pivot_detector.last_low_pivot:
            last_pivot = self.pivot_detector.last_low_pivot
        return last_pivot
    
    def _generate_pair_id(self, pair: Dict[str, Any]) -> str:
        """Generate a unique ID for a pivot pair."""
        return f"{pair['from']['time']}_{pair['to']['time']}_{pair.get('type', 'unknown')}"
    
    def _clear_all_fans(self, result: Dict[str, Any]):
        """Clear all active fans and their markers."""
        for fid in list(self.angle_engine.active_fans.keys()):
            fan = self.angle_engine.active_fans[fid]
            # Remove Lines
            for line in fan.lines:
                result['remove_drawings'].append(line.id)
            # Remove Linked Markers
            if 'marker_ids' in fan.config:
                for mid in fan.config['marker_ids']:
                    result['remove_drawings'].append(mid)
            self.angle_engine.remove_fan(fid)
        
        self.active_fan_ids = {}
    
    def _create_fan_for_pair(
        self,
        pair: Dict[str, Any],
        candles: List[Dict[str, Any]],
        result: Dict[str, Any],
        is_outer: bool = False
    ) -> Optional[str]:
        """
        Create a fan for a pivot pair and add to result.
        
        Args:
            pair: The pivot pair dict
            candles: Current candle data
            result: Result dict to append drawings to
            is_outer: Whether this is the Outer container fan
            
        Returns:
            The fan ID if created, None otherwise
        """
        pair_id = self._generate_pair_id(pair)
        
        # Check if we already have this fan active
        if pair_id in self.active_fan_ids:
            return self.active_fan_ids[pair_id]
        
        # Create the fan
        fan = self.angle_engine.create_fan(
            from_pivot=pair['from'],
            to_pivot=pair['to'],
            current_candles=candles
        )
        
        fan.config['pair_id'] = pair_id
        fan.config['is_outer'] = is_outer
        fan.config['pair_type'] = pair.get('type', 'unknown')
        
        # Add drawing commands
        result['drawings'].extend(
            self.angle_engine.fan_to_drawing_commands(fan)
        )
        
        self.active_fan_ids[pair_id] = fan.id
        
        return fan.id
    
    def _add_pivot_markers(
        self,
        hierarchy: PivotHierarchy,
        result: Dict[str, Any]
    ) -> List[str]:
        """
        Add markers for all relevant pivots in the hierarchy.
        
        Returns:
            List of marker IDs for cleanup tracking
        """
        marker_ids = []
        marked_times = set()  # Avoid duplicate markers
        
        # Mark Origin pivot
        if hierarchy.origin_pivot:
            p = hierarchy.origin_pivot
            if p['time'] not in marked_times:
                pid = f"pm_{p['time']}_{p['type']}"
                marker_ids.append(pid)
                result['pivot_markers'].append({
                    'id': pid,
                    'type': f"pivot_{p['type']}",
                    'time': p['time'],
                    'price': p['price'],
                    'bar_index': p.get('bar_index', 0)
                })
                marked_times.add(p['time'])
        
        # Mark Outer Container pivots
        if hierarchy.outer_container:
            for key in ['from', 'to']:
                p = hierarchy.outer_container[key]
                if p['time'] not in marked_times:
                    pid = f"pm_{p['time']}_{p['type']}"
                    marker_ids.append(pid)
                    result['pivot_markers'].append({
                        'id': pid,
                        'type': f"pivot_{p['type']}",
                        'time': p['time'],
                        'price': p['price'],
                        'bar_index': p.get('bar_index', 0)
                    })
                    marked_times.add(p['time'])
        
        # Mark Inner Anchor pivot (the opposite-type pivot used for inner fans)
        if hierarchy.inner_anchor:
            p = hierarchy.inner_anchor
            if p['time'] not in marked_times:
                pid = f"pm_{p['time']}_{p['type']}"
                marker_ids.append(pid)
                result['pivot_markers'].append({
                    'id': pid,
                    'type': f"pivot_{p['type']}",
                    'time': p['time'],
                    'price': p['price'],
                    'bar_index': p.get('bar_index', 0)
                })
                marked_times.add(p['time'])
        
        # Mark Inner Sequence pivots (just the 'from' pivot of each)
        for inner_pair in hierarchy.inner_sequence[:self.config['max_inner_fans']]:
            p = inner_pair['from']
            if p['time'] not in marked_times:
                pid = f"pm_{p['time']}_{p['type']}"
                marker_ids.append(pid)
                result['pivot_markers'].append({
                    'id': pid,
                    'type': f"pivot_{p['type']}",
                    'time': p['time'],
                    'price': p['price'],
                    'bar_index': p.get('bar_index', 0)
                })
                marked_times.add(p['time'])
        
        return marker_ids
    
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
        
        # Get current bar info
        current_bar = candles[bar_index]
        current_time = int(current_bar['time'])
        current_close = float(current_bar['close'])
        
        # Get the most recent confirmed pivot
        last_pivot = self._get_last_pivot()
        
        # Use PivotSelector to identify the complete hierarchy
        # Primary Hierarchy: Based on the LAST pivot (Future facing)
        hierarchy = PivotSelector.select_hierarchy(
            current_price=current_close,
            current_time=current_time,
            confirmed_pivots=self.pivot_detector.confirmed_pivots,
            last_pivot=last_pivot
        )
        
        # Secondary Hierarchy: Based on PREVIOUS pivot (Past facing / Completed Leg)
        # This ensures that when we form a new Low, we still see the Fan coming down from the High.
        secondary_hierarchy = None
        prev_pivot = None
        if last_pivot:
            # Find the pivot immediately preceding last_pivot
            # Confirmed pivots are a list; identifying index
            pivots = self.pivot_detector.confirmed_pivots
            if len(pivots) >= 2:
                # Assuming simple chronological order in list (usually append order)
                # But let's be safe and verify timestamps
                sorted_pivots = sorted(pivots, key=lambda p: p.time)
                if sorted_pivots[-1].time == last_pivot.time:
                    prev_pivot = sorted_pivots[-2]
                
        if prev_pivot:
             secondary_hierarchy = PivotSelector.select_hierarchy(
                current_price=current_close,
                current_time=current_time,
                confirmed_pivots=self.pivot_detector.confirmed_pivots,
                last_pivot=prev_pivot
            )

        # Merge hierarchies for display? 
        # Check if hierarchy changed (primary or secondary)
        # For simplicity, we clear fans if PRIMARY changes. 
        # Ideally, we should track both independently.
        
        hierarchy_changed = self._check_hierarchy_changed(hierarchy)
        
        if hierarchy_changed:
            self._clear_all_fans(result)
        
        hierarchies_to_process = []
        if hierarchy: hierarchies_to_process.append((hierarchy, True)) # True = Primary
        if secondary_hierarchy: hierarchies_to_process.append((secondary_hierarchy, False)) # False = Secondary

        if hierarchies_to_process:
            self.current_hierarchy = hierarchy # Track primary
            
            for h_obj, is_primary in hierarchies_to_process:
                # Track pairs to draw
                pairs_to_draw = []
                
                # Outer Container
                if h_obj.outer_container and self.config['show_outer_fan']:
                    pairs_to_draw.append((h_obj.outer_container, True))
                
                # Inner Sequence
                if h_obj.inner_sequence and self.config['show_inner_fans']:
                    for inner_pair in h_obj.inner_sequence[:self.config['max_inner_fans']]:
                        pairs_to_draw.append((inner_pair, False))
                
                # Draw them
                created_fans = []
                for pair, is_outer in pairs_to_draw:
                    fan_id = self._create_fan_for_pair(pair, candles, result, is_outer)
                    if fan_id:
                        created_fans.append(fan_id)
                
                # Markers
                if result['drawings'] or not is_primary or is_primary: 
                    # Always update markers for ANY active hierarchy
                    marker_ids = self._add_pivot_markers(h_obj, result)
                    
                    if created_fans:
                        first_fan = self.angle_engine.active_fans.get(created_fans[0])
                        if first_fan:
                            first_fan.config['marker_ids'] = marker_ids
        else:
            self._clear_all_fans(result)
            self.current_hierarchy = None

        # CRITICAL: Ensure the raw LAST PIVOT is always marked if it exists,
        # even if it's not yet part of any hierarchy (e.g. the very latest formed pivot)
        # This matches the "Force Add" logic that was previously working.
        if last_pivot:
            lp_dict = PivotSelector._pivot_to_dict(last_pivot)
            pid = f"pm_{lp_dict['time']}_{lp_dict['type']}"
            # Check if we already added it in the hierarchy loops above
            already_added = any(m['id'] == pid for m in result['pivot_markers'])
            
            if not already_added:
                result['pivot_markers'].append({
                    'id': pid,
                    'type': f"pivot_{lp_dict['type']}",
                    'time': lp_dict['time'],
                    'price': lp_dict['price'],
                    'bar_index': lp_dict.get('bar_index', 0)
                })
        
        # Check for completed fans
        if self.config['remove_completed_fans'] and bar_index < len(candles):
            completed_fan_ids = []
            
            for fan_id in list(self.angle_engine.active_fans.keys()):
                if self.angle_engine.check_fan_completion(fan_id, current_bar):
                    completed_fan_ids.append(fan_id)
            
            # Remove completed fans
            for fan_id in completed_fan_ids:
                fan = self.angle_engine.active_fans.get(fan_id)
                if fan:
                    for line in fan.lines:
                        result['remove_drawings'].append(line.id)
                    # Remove from tracking
                    pair_id = fan.config.get('pair_id')
                    if pair_id and pair_id in self.active_fan_ids:
                        del self.active_fan_ids[pair_id]
                    self.angle_engine.remove_fan(fan_id)
        
        # Save state for next bar
        result['state'] = self._get_state()
        
        return result
    
    def _check_hierarchy_changed(self, new_hierarchy: Optional[PivotHierarchy]) -> bool:
        """
        Check if the hierarchy has changed significantly enough to redraw.
        """
        if self.current_hierarchy is None and new_hierarchy is None:
            return False
        
        if self.current_hierarchy is None or new_hierarchy is None:
            return True
        
        # Check if context changed
        if self.current_hierarchy.context != new_hierarchy.context:
            return True
        
        # Check if outer container changed
        old_outer = self.current_hierarchy.outer_container
        new_outer = new_hierarchy.outer_container
        
        if (old_outer is None) != (new_outer is None):
            return True
        
        if old_outer and new_outer:
            if old_outer['from']['time'] != new_outer['from']['time']:
                return True
            if old_outer['to']['time'] != new_outer['to']['time']:
                return True
        
        # Check if inner sequence changed significantly
        old_inner = self.current_hierarchy.inner_sequence
        new_inner = new_hierarchy.inner_sequence
        
        if len(old_inner) != len(new_inner):
            return True
        
        for i in range(min(len(old_inner), len(new_inner))):
            if old_inner[i]['from']['time'] != new_inner[i]['from']['time']:
                return True
        
        return False
    
    def reset(self):
        """Reset study state (call on new symbol/interval)"""
        self.pivot_detector.reset()
        self.angle_engine.active_fans = {}
        self.current_hierarchy = None
        self.active_fan_ids = {}
    
    def _get_state(self) -> Dict[str, Any]:
        """Get combined state from all components"""
        # Serialize current_hierarchy if it exists
        hierarchy_data = None
        if self.current_hierarchy:
            hierarchy_data = {
                'context': self.current_hierarchy.context,
                'outer_container': self.current_hierarchy.outer_container,
                'inner_sequence': self.current_hierarchy.inner_sequence,
                'origin_pivot': self.current_hierarchy.origin_pivot,
                'inner_anchor': self.current_hierarchy.inner_anchor
            }
        
        return {
            'pivot_detector': self.pivot_detector.get_state(),
            'angle_engine': self.angle_engine.get_state(),
            'config': self.config,
            'active_fan_ids': self.active_fan_ids,
            'current_hierarchy': hierarchy_data
        }
    
    def _restore_state(self, state: Dict[str, Any]):
        """Restore state from a state dict."""
        if 'pivot_detector' in state:
            self.pivot_detector.restore_state(state['pivot_detector'])
        
        if 'angle_engine' in state:
            self.angle_engine.restore_state(state['angle_engine'])
        
        if 'config' in state:
            self.config = {**DEFAULT_CONFIG, **state['config']}
        
        if 'active_fan_ids' in state:
            self.active_fan_ids = state['active_fan_ids']
        
        # Restore current_hierarchy
        if 'current_hierarchy' in state and state['current_hierarchy']:
            h = state['current_hierarchy']
            self.current_hierarchy = PivotHierarchy(
                context=h['context'],
                outer_container=h.get('outer_container'),
                inner_sequence=h.get('inner_sequence', []),
                origin_pivot=h.get('origin_pivot'),
                inner_anchor=h.get('inner_anchor')
            )
        else:
            self.current_hierarchy = None
    
    def restore_state(self, state: Dict[str, Any]):
        """Public method to restore state (for backward compatibility)."""
        self._restore_state(state)


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
