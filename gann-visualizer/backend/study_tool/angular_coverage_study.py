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
from .angle_zone_tracker import AngleZoneTracker
from .fan_validator import FanValidator
from analysis.target_progression import TargetProgression
from .event_logger import EventLogger, EventType
from .unified_state_machine import UnifiedStateMachine, EventOutput
from .cluster_detector import ClusterDetector
from study_tool.event_pipeline import EventPipeline

# --- LOGGING CONFIGURATION (Unified Strategy) ---
# We maintain single files for both debug logs and intersection data per backend process run.
# Old logs are cleaned up on startup, matching the behavior of backend_session_*.log in main.py.
# Log files are now written to logs/backend/ (relative to project root).

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_log_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "logs", "backend", "study_debug"
)
_csv_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "logs", "backend"
)

os.makedirs(_log_dir, exist_ok=True)
os.makedirs(_csv_dir, exist_ok=True)

# 1. Clean up old study logs
for filename in os.listdir(_log_dir):
    if filename.startswith("angular_study_") and filename.endswith(".log"):
        try: os.remove(os.path.join(_log_dir, filename))
        except: pass

# 2. Clean up old intersection CSVs
for filename in os.listdir(_csv_dir):
    if filename.startswith("intersections_") and filename.endswith(".csv"):
        try: os.remove(os.path.join(_csv_dir, filename))
        except: pass
    # Also clean up legacy "intersections.csv"
    if filename == "intersections.csv":
        try: os.remove(os.path.join(_csv_dir, filename))
        except: pass

# 3. Establish session-level globals
_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
_study_log_file = os.path.join(_log_dir, f'angular_study_{_timestamp}.log')
_intersections_csv = os.path.join(_csv_dir, f'intersections_{_timestamp}.csv')

# Configure single shared logger for all AngularPriceCoverageStudy instances in this process
_logger = logging.getLogger(f'AngularStudy_{_timestamp}')
_logger.setLevel(logging.DEBUG)
if not _logger.handlers:
    _fh = logging.FileHandler(_study_log_file, encoding='utf-8', mode='w')
    _fh.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    _logger.addHandler(_fh)

# Initialize the intersection CSV with headers
with open(_intersections_csv, 'w', encoding='utf-8') as f:
    f.write("Timestamp,FanIdentity,Fraction,Price\n")



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
    'bounce_threshold_percent': 0.3,  # Threshold for confirming SUPPORT_BOUNCE
    'rejection_lookback_bars': 5,      # Bars to look for RESISTANCE_REJECTION after test
    'rest_required_bars': 3,           # Consecutive bars required for REST_ON_ANGLE
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
            right_bars=self.config['right_bars'],
            symbol=self.config.get('symbol'),
            resolution=self.config.get('resolution')
        )

        self.angle_engine = AngleEngine(
            # fractions=self.config['fractions'], # Fractions are now derived from fraction_colors keys
            fraction_colors=self.config['fraction_colors'],
            main_color=self.config['main_color'],
            line_extension_bars=self.config['line_extension_bars'],
            main_line_width=self.config['main_line_width'],
            fraction_line_width=self.config['fraction_line_width'],
            scale_ratio=self.config['scale_ratio'],
            resolution=self.config.get('resolution'),
            symbol=self.config.get('symbol')
        )
        
        self.intersection_detector = IntersectionDetector()

        # Price movement tracking modules
        self.zone_tracker = AngleZoneTracker()
        self.fan_validator = FanValidator()
        self.target_progression = TargetProgression()
        self.event_logger = EventLogger()
        self.cluster_detector = ClusterDetector()
        timezone_val = self.config.get('timezone', 'UTC')
        if not isinstance(timezone_val, str):
            timezone_val = 'UTC'
        event_pipeline_config = {
            'bounce_threshold_percent': self.config.get('bounce_threshold_percent', 0.3),
            'rejection_lookback_bars': self.config.get('rejection_lookback_bars', 5),
            'rest_tolerance_percent': self.config.get('rest_tolerance_percent', 0.15),
            'rest_required_bars': self.config.get('rest_required_bars', 3),
            'run_mode': self.config.get('run_mode', 'simulation'),
            'timezone': timezone_val,
        }
        self.event_pipeline = EventPipeline(event_pipeline_config)
        self.state_machine = UnifiedStateMachine({
            'bounce_threshold_percent': self.config.get('bounce_threshold_percent', 0.3),
            'rejection_lookback_bars': self.config.get('rejection_lookback_bars', 5),
            'rest_tolerance_percent': self.config.get('rest_tolerance_percent', 0.15),
            'rest_required_bars': self.config.get('rest_required_bars', 3),
            'run_mode': self.config.get('run_mode', 'simulation'),
            'is_new_replay': self.config.get('is_new_replay', False)
        })

        # Track active fan keys for diffing (old vs new set)
        self._active_fan_keys: Dict[str, str] = {}  # fan_key -> engine_fan_id
        
        # State machine persistent roster: fan_id -> fan_data
        self._persisted_fans: Dict[str, Dict] = {}
        self._active_marker_ids: set = set()
        self._is_initialized = False

        self._initialized: bool = False
        
        # Track retroactive events pending processing (for fans that might get deactivated)
        self._pending_retro_events: Dict[str, Dict] = {}

        # Use shared session-level logger
        self.logger = _logger
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
        # Force a hard reset of the registry because we are starting fresh from history
        self.pivot_detector.reset(clear_registry=True)
        self.cluster_detector._reset()
        self._historical_clusters = []

        import pandas as pd
        for i in range(len(candles)):
            # Update Cluster Detector for every single historical candle
            c = candles[i]
            c_open = float(c.get('Open') if c.get('Open') is not None else c.get('open', 0))
            c_high = float(c.get('High') if c.get('High') is not None else c.get('high', 0))
            c_low = float(c.get('Low') if c.get('Low') is not None else c.get('low', 0))
            c_close = float(c.get('Close') if c.get('Close') is not None else c.get('close', 0))
            
            candle_series = pd.Series({
                'Open': c_open,
                'High': c_high,
                'Low': c_low,
                'Close': c_close
            })
            self.cluster_detector.process_candle(candle_series, i)
            
            while len(self._historical_clusters) <= i:
                self._historical_clusters.append(False)
            self._historical_clusters[i] = self.cluster_detector.get_state()['in_cluster']

            # Pivot detection
            if i >= start_idx:
                self.pivot_detector.detect_pivots(candles, i)

        self.log(f"[Study] Historical detection complete. Found {len(self.pivot_detector.confirmed_pivots)} confirmed pivots.")

    def process_bar(
        self,
        candles: List[Dict[str, Any]],
        bar_index: int,
        state: Optional[Dict[str, Any]] = None,
        is_closed: bool = True
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
            # Pass history up to PREVIOUS bar to avoid double-processing current bar
            history_subset = candles[:bar_index]
            self.initialize_history(history_subset)
            self._initialized = True

        result = {
            'type': 'drawing_update',
            'drawings': [],
            'pivot_markers': [],
            'remove_drawings': [],
            'state': {}
        }

        current_candle = candles[bar_index]

        # 0. Detect candlestick pattern for frontend chart labels
        c_open = float(current_candle.get('Open') if current_candle.get('Open') is not None else current_candle.get('open', 0))
        c_high = float(current_candle.get('High') if current_candle.get('High') is not None else current_candle.get('high', 0))
        c_low = float(current_candle.get('Low') if current_candle.get('Low') is not None else current_candle.get('low', 0))
        c_close = float(current_candle.get('Close') if current_candle.get('Close') is not None else current_candle.get('close', 0))
        pattern = self.state_machine.pattern_detector.detect({
            'open': c_open, 'high': c_high, 'low': c_low, 'close': c_close
        })
        if pattern.name != 'NO_PATTERN':
            result['candle_pattern'] = pattern.name

        # 0. Global chronological state updates (e.g. Cluster Detector)
        # We must do this exactly once per chronological bar, NEVER during retroactive sweeps
        import pandas as pd
        
        candle_series = pd.Series({
            'Open': c_open,
            'High': c_high,
            'Low': c_low,
            'Close': c_close
        })
        self.cluster_detector.process_candle(candle_series, bar_index)
        
        # Store historical cluster state for retroactive sweeps
        if not hasattr(self, '_historical_clusters'):
            self._historical_clusters = []
        while len(self._historical_clusters) <= bar_index:
            self._historical_clusters.append(False)
        self._historical_clusters[bar_index] = self.cluster_detector.get_state()['in_cluster']

        # 1. Detect pivots at this bar
        if is_closed:
            self.pivot_detector.detect_pivots(candles, bar_index)

            # 2. Run unified backward traversal (same logic every bar) - BUILD PHASE ONLY
            self._sync_fans_build(candles, bar_index, result)
        
        # 2.5 Process Zone Tracking for ALL active fans for the LIVE bar
        for fan_id, fan_obj in self.angle_engine.active_fans.items():
            if getattr(fan_obj, '_zone_caught_up_to', -1) < bar_index:
                snapshot = self.zone_tracker.compute_snapshot(fan_obj, current_candle, bar_index)
                fan_obj._zone_caught_up_to = bar_index
                
                if self.zone_tracker.has_zone_changed(fan_id, snapshot.zone):
                    # For zone change, use the NEW snapshot's extremes
                    # Get fan geometry context from persisted fans
                    fan_data = self._persisted_fans.get(fan_id, {})
                    fan_geom = fan_data.get('anchor', {})
                    fan_obj = self.angle_engine.active_fans.get(fan_id)
                    # Origin: where fan lines radiate from (temporally first pivot)
                    origin_bar_index = int(fan_obj.from_pivot.get('bar_index', 0)) if fan_obj else int(fan_data.get('from_pivot', {}).get('bar_index', 0))
                    origin_price = float(fan_obj.from_pivot.get('price', 0.0)) if fan_obj else float(fan_data.get('from_pivot', {}).get('price', 0.0))
                    fan_geometry = None
                    if fan_obj and fan_obj.lines:
                        fan_geometry = {
                            "origin": {"bar_index": int(fan_obj.from_pivot.get("bar_index", 0)), "time": int(fan_obj.from_pivot.get("time", 0)), "price": float(fan_obj.from_pivot.get("price", 0.0)), "label": str(fan_obj.from_pivot.get("type", ""))},
                            "anchor": {"bar_index": int(fan_obj.to_pivot.get("bar_index", 0)), "time": int(fan_obj.to_pivot.get("time", 0)), "price": float(fan_obj.to_pivot.get("price", 0.0)), "label": str(fan_obj.to_pivot.get("type", ""))},
                            "rays": [{"id": line.id, "fraction": line.fraction, "points": [{"time": line.start_time, "price": line.start_price}, {"time": line.end_time, "price": line.end_price}], "color": line.color, "width": line.width} for line in fan_obj.lines]
                        }
                    self.event_logger.log_event(
                        timestamp=current_candle['time'],
                        event_type=EventType.ZONE_CHANGE,
                        price=c_close,
                        open_price=c_open,
                        high_price=c_high,
                        low_price=c_low,
                        close_price=c_close,
                        active_angle_prices=snapshot.angle_prices,
                        cluster_state=self._historical_clusters[bar_index],
                        current_zone=snapshot.zone,
                        zone_highest_close=snapshot.zone_highest_close,
                        zone_lowest_close=snapshot.zone_lowest_close,
                        anchor_bar_index=fan_geom.get('bar_index', 0),
                        scale_ratio=self.config.get('scale_ratio', 1.0),
                        anchor_price=fan_geom.get('price', 0),
                        origin_bar_index=origin_bar_index,
                        origin_price=origin_price,
                        fan_geometry=fan_geometry,
                        details={
                            'fan_id': fan_id,
                            'new_zone': snapshot.zone,
                            'angle_prices': snapshot.angle_prices,
                        }
                    )
        
        # Process retroactive events only for fans that remain active after sync
        # We need to process them chronologically by bar_index so the state machine works correctly
        if self._pending_retro_events:
            # We need to track the min anchor bar index to know where to start the sweep
            min_anchor_idx = bar_index
            
            for fan_id, retro_data in self._pending_retro_events.items():
                if fan_id in self._persisted_fans:
                    anchor_idx = retro_data.get('anchor_idx', bar_index)
                    min_anchor_idx = min(min_anchor_idx, anchor_idx)
            
            # Process chronologically for EVERY bar from min_anchor_idx to current bar_index - 1
            if min_anchor_idx < bar_index:
                retro_fan_ids = [fid for fid in self._pending_retro_events.keys() if fid in self._persisted_fans]
                retro_fans = {fid: self.angle_engine.active_fans[fid] for fid in retro_fan_ids if fid in self.angle_engine.active_fans}
                
                for b_idx in range(min_anchor_idx, bar_index):
                    r_candle = candles[b_idx]
                    r_prev_candle = candles[b_idx - 1] if b_idx > 0 else None
                    
                    # Detect intersections for the retro fans on this historical bar
                    r_events = self.intersection_detector.detect(r_candle, r_prev_candle, retro_fans, b_idx)
                    
                    if r_events:
                        for event in r_events:
                            if event.fan_id in retro_fans:
                                fan_obj = retro_fans[event.fan_id]
                                fan_obj.intersections.append(event)
                                label_id = f"hit_{event.fan_id}_{event.line_id}_{event.time}_{event.price}"
                                fan_obj.label_ids.append(label_id)
                    
                    ui_events = []
                    self._process_tracking_modules(
                        r_candle, r_prev_candle, b_idx, r_events, ui_events, candles,
                        is_retro=True, retro_fan_ids=retro_fan_ids
                    )
                    
                    if ui_events:
                        for ui_event in ui_events:
                            ui_event['details'] = f"[Retro] {ui_event['details']}"
                            print(f"[RetroSweep] Emitting retroactive event: {ui_event}")
                            
                        if 'intersection_events' not in result:
                            result['intersection_events'] = []
                        result['intersection_events'].extend(ui_events)
                    
            # Clean up pending retro events
            self._pending_retro_events.clear()

        # 2.5 Dynamically extend active fans if price action is approaching their current end
        self._extend_active_fans(candles, bar_index, result)

        # 3. Detect intersections for this bar
        current_candle = candles[bar_index]
        prev_candle = candles[bar_index - 1] if bar_index > 0 else None
        
        events = self.intersection_detector.detect(current_candle, prev_candle, self.angle_engine.active_fans, bar_index)
        
        # We'll collect all events (from validations, state machine, targets) in a list to format for UI
        ui_events = []
        
        if events:
            for event in events:
                if event.fan_id in self.angle_engine.active_fans:
                    fan_obj = self.angle_engine.active_fans[event.fan_id]
                    # Store the event and label ID in the fan object
                    fan_obj.intersections.append(event)
                    
                    label_id = f"hit_{event.fan_id}_{event.line_id}_{event.time}_{event.price}"
                    fan_obj.label_ids.append(label_id)

                    try:
                        frac_str = str(event.fraction) if event.fraction is not None else "Horizontal"
                        log_line = f"{event.time},{event.priority_label},{frac_str},{event.price}\n"
                        with open(_intersections_csv, 'a', encoding='utf-8') as f:
                            f.write(log_line)
                    except Exception as e:
                        print(f"Failed to log intersection: {e}")

        # 4. Price movement tracking pipeline (State Machine)
        self._process_tracking_modules(current_candle, prev_candle, bar_index, events or [], ui_events, candles)
        
        if ui_events:
            if 'intersection_events' not in result:
                result['intersection_events'] = []
            result['intersection_events'].extend(ui_events)

        # 5. Run unified backward traversal - TEARDOWN PHASE ONLY
        if is_closed:
            self._sync_fans_teardown(candles, bar_index, result)

        # 6. Save state
        result['state'] = self._get_state()

        return result

    # (Removed _process_intersection_event as it's now inline)

    def _process_tracking_modules(
        self,
        current_candle: Dict[str, Any],
        prev_candle: Dict[str, Any],
        bar_index: int,
        intersection_events: list,
        ui_events: list,
        candles: list,
        is_retro: bool = False,
        retro_fan_ids: list = None
    ):
        """
        Run the price movement tracking pipeline:
        1. FanValidator — check for 7/8 interactions
        2. UnifiedStateMachine — processes wicks, closes, tests, breaches, fakeouts, and rests
        3. TargetProgression — advance targets on confirmed breaches
        4. AngleZoneTracker — compute zone snapshots
        """
        timestamp = int(current_candle.get('time', current_candle.get('Time', 0)))
        close_price = float(current_candle.get('Close', current_candle.get('close', 0)))

        # Add OHLC and Active Angles to the event logging
        # Handle both 'Open' (yfinance) and 'open' (internal) keys
        c_open = float(current_candle.get('Open') if current_candle.get('Open') is not None else current_candle.get('open', 0))
        c_high = float(current_candle.get('High') if current_candle.get('High') is not None else current_candle.get('high', 0))
        c_low = float(current_candle.get('Low') if current_candle.get('Low') is not None else current_candle.get('low', 0))
        
        # 0. Check Cluster Detector from historical state
        is_cluster = False
        if hasattr(self, '_historical_clusters') and bar_index < len(self._historical_clusters):
            is_cluster = self._historical_clusters[bar_index]

        # Calculate current prices for all angles in active fans
        active_angle_prices = {}
        for f_id, fan in self.angle_engine.active_fans.items():
            if not fan.lines:
                continue

            # Use the first line's start time as the fan's origin time
            origin_time = fan.lines[0].start_time
            if timestamp >= origin_time:
                # Helper to calculate price at current bar
                for line in fan.lines:
                    bar_span = line.end_bar_index - line.start_bar_index
                    if bar_span > 0:
                        bars_from_origin = bar_index - line.start_bar_index
                        slope = (line.end_price - line.start_price) / bar_span
                        price_at_t = line.start_price + bars_from_origin * slope

                        if line.fraction is not None:
                            frac_str = str(line.fraction)
                        elif "htarget" in line.id:
                            frac_str = "horizontal"
                        else:
                            frac_str = "main"

                        active_angle_prices[f"{f_id}_{frac_str}"] = round(price_at_t, 2)

        def get_target_info_for_event(fan_id: str) -> Dict[str, Any]:
            """Get target progression info for a specific fan."""
            return self.target_progression.get_target_info(fan_id)

        # 1. Fan validation (7/8 interaction check)
        new_validations = self.fan_validator.process_intersections(
            intersection_events, current_candle, bar_index
        )
        for validation in new_validations:
            self.target_progression.activate_fan(validation.fan_id)
            self.target_progression.on_angle_touched(validation.fan_id, '7/8', bar_index)
            target_info = get_target_info_for_event(validation.fan_id)

            # Get zone context using historical state
            last_zone = self.zone_tracker.get_zone_at_bar(validation.fan_id, bar_index)
            if not last_zone:
                last_zone = self.zone_tracker.get_last_zone(validation.fan_id)
                
            current_zone_str = last_zone.zone if last_zone else None
            z_extremes = {'highest_close': last_zone.zone_highest_close, 'lowest_close': last_zone.zone_lowest_close} if last_zone else None
            b_in_zone = last_zone.bars_in_zone if last_zone else None

            # Get fan geometry context
            fan_obj = self.angle_engine.active_fans.get(validation.fan_id)
            fan_data = self._persisted_fans.get(validation.fan_id, {})
            fan_geom = fan_data.get('anchor', {})
            # Origin: where fan lines radiate from (temporally first pivot)
            origin_bar_index = int(fan_obj.from_pivot.get('bar_index', 0)) if fan_obj else int(fan_data.get('from_pivot', {}).get('bar_index', 0))
            origin_price = float(fan_obj.from_pivot.get('price', 0.0)) if fan_obj else float(fan_data.get('from_pivot', {}).get('price', 0.0))
            fan_geometry = None
            if fan_obj and fan_obj.lines:
                fan_geometry = {
                    "origin": {"bar_index": int(fan_obj.from_pivot.get("bar_index", 0)), "time": int(fan_obj.from_pivot.get("time", 0)), "price": float(fan_obj.from_pivot.get("price", 0.0)), "label": str(fan_obj.from_pivot.get("type", ""))},
                    "anchor": {"bar_index": int(fan_obj.to_pivot.get("bar_index", 0)), "time": int(fan_obj.to_pivot.get("time", 0)), "price": float(fan_obj.to_pivot.get("price", 0.0)), "label": str(fan_obj.to_pivot.get("type", ""))},
                    "rays": [{"id": line.id, "fraction": line.fraction, "points": [{"time": line.start_time, "price": line.start_price}, {"time": line.end_time, "price": line.end_price}], "color": line.color, "width": line.width} for line in fan_obj.lines]
                }

            self.event_logger.log_event(
                timestamp=timestamp,
                event_type=EventType.FAN_VALIDATED,
                angle_name='7/8',
                price=validation.validation_price,
                open_price=c_open,
                high_price=c_high,
                low_price=c_low,
                close_price=close_price,
                active_angle_prices=active_angle_prices,
                cluster_state=is_cluster,
                current_zone=current_zone_str,
                zone_highest_close=z_extremes.get('highest_close') if z_extremes else None,
                zone_lowest_close=z_extremes.get('lowest_close') if z_extremes else None,
                next_angle_line=target_info.get('next_angle_line'),
                anchor_bar_index=fan_geom.get('bar_index', 0) if fan_obj is None else getattr(fan_obj, 'anchor_bar_index', fan_geom.get('bar_index', 0)),
                scale_ratio=self.config.get('scale_ratio', 1.0),
                anchor_price=fan_geom.get('price', 0),
                origin_bar_index=origin_bar_index,
                origin_price=origin_price,
                fan_geometry=fan_geometry,
                details={
                    'fan_id': validation.fan_id,
                    'validation_type': validation.validation_type,
                    'validation_bar': validation.validation_bar,
                }
            )
            self.state_machine.emit_fan_validated_state(
                bar_index=bar_index,
                fan_id=validation.fan_id,
                origin_bar=bar_index,
                breach_close=close_price
            )
            self.log(f"[Tracking] Fan validated: {validation.fan_id} via {validation.validation_type} at bar {bar_index}")

            fan_display = validation.fan_id.replace("Fan_", "").replace("_", "-")
            fan_obj = self.angle_engine.active_fans.get(validation.fan_id)
            priority_label = fan_obj.priority_label if fan_obj else fan_display
            ui_events.append({
                'time': timestamp,
                'fan': priority_label,
                'fanIdentity': fan_display,
                'fraction': '-',
                'price': validation.validation_price,
                'type': 'FAN_VALIDATED',
                'details': f"Via {validation.validation_type}",
                'open': c_open,
                'high': c_high,
                'low': c_low,
                'close': close_price,
                'activeAngles': active_angle_prices,
                'cluster': is_cluster,
                'zone': current_zone_str or "",
                'zoneExtremes': z_extremes or "",
                'bar_index': bar_index,
                'nextAngleLine': target_info.get('next_angle_line') or "",
                # Fan geometry for angular fan ray reconstruction
                'anchor_bar_index': fan_geom.get('bar_index', 0) if fan_obj is None else getattr(fan_obj, 'anchor_bar_index', fan_geom.get('bar_index', 0)),
                'scale_ratio': self.config.get('scale_ratio', 1.0),
                'anchor_price': fan_geom.get('price', 0),
                'origin_bar_index': int(fan_obj.from_pivot.get('bar_index', 0)) if fan_obj else int(fan_data.get('from_pivot', {}).get('bar_index', 0)),
                'origin_price': float(fan_obj.from_pivot.get('price', 0.0)) if fan_obj else float(fan_data.get('from_pivot', {}).get('price', 0.0)),
                'horizontalTargetPrice': self._get_horizontal_target_price(fan_obj) if fan_obj else None,
                'fullCoverageTargetPrice': float(fan_data.get('target', {}).get('price', 0)) if fan_data else None,
            })

        # Provide the correct ZEC context using historical zone state BEFORE calling state machine.
        # ZEC represents the extreme close in the zone the price was in IMMEDIATELY PRIOR to the cross.
        # So we query the zone_tracker for the snapshot at bar_index - 1.
        actual_zec_info = {}
        for fan_id in self.angle_engine.active_fans.keys():
            prev_snapshot = self.zone_tracker.get_zone_at_bar(fan_id, bar_index - 1)
            if prev_snapshot:
                actual_zec_info[fan_id] = {
                    'zec_high': prev_snapshot.zone_highest_close,
                    'zec_low': prev_snapshot.zone_lowest_close,
                    'prior_zone_fraction': prev_snapshot.zone
                }

        # 2. Unified State Machine (Breaches, Tests, Fake-outs, Rests, Bounces)
        state_events = self.state_machine.process_bar(
            current_candle, prev_candle, bar_index,
            intersection_events, self.angle_engine.active_fans, candles, is_retro, retro_fan_ids,
            zec_info=actual_zec_info
        )

        for state_event in state_events:
            # Map string to EventType enum
            try:
                # First try by name (e.g. EventType["BREACH_CONFIRMED"])
                evt_enum = EventType[state_event.event_type]
            except KeyError:
                try:
                    # Then try by value (e.g. EventType("CROSS_UP"))
                    evt_enum = EventType(state_event.event_type)
                except ValueError:
                    evt_enum = EventType.CROSS_UP
                
            # Get zone context using historical state
            last_zone = self.zone_tracker.get_zone_at_bar(state_event.fan_id, bar_index)
            if not last_zone:
                last_zone = self.zone_tracker.get_last_zone(state_event.fan_id)
                
            current_zone_str = last_zone.zone if last_zone else None
            z_extremes = {'highest_close': last_zone.zone_highest_close, 'lowest_close': last_zone.zone_lowest_close} if last_zone else None
            b_in_zone = last_zone.bars_in_zone if last_zone else None

            # Record first contact for target progression
            # TARGET_HIT fires on the VERY FIRST contact with any angle line - regardless of event type
            target_hit = None
            target_hit = self.target_progression.on_angle_contact(
                fan_id=state_event.fan_id,
                angle_name=str(state_event.fraction),
                bar_index=bar_index,
                price=state_event.price,
            )

            # Update last_touched_line on ANY intersection event
            # For CROSS events, nextAngleLine will be set to the NEXT line in sequence
            self.target_progression.on_angle_touched(
                fan_id=state_event.fan_id,
                angle_name=str(state_event.fraction),
                bar_index=bar_index,
                event_type=state_event.event_type
            )

            target_info = get_target_info_for_event(state_event.fan_id)

            # Get fan geometry context
            fan_obj_sm = self.angle_engine.active_fans.get(state_event.fan_id)
            fan_data_sm = self._persisted_fans.get(state_event.fan_id, {})
            fan_geom_sm = fan_data_sm.get('anchor', {})
            # Origin: where fan lines radiate from (temporally first pivot)
            origin_bar_index = int(fan_obj_sm.from_pivot.get('bar_index', 0)) if fan_obj_sm else int(fan_data_sm.get('from_pivot', {}).get('bar_index', 0))
            origin_price = float(fan_obj_sm.from_pivot.get('price', 0.0)) if fan_obj_sm else float(fan_data_sm.get('from_pivot', {}).get('price', 0.0))
            fan_geometry = None
            if fan_obj_sm and fan_obj_sm.lines:
                fan_geometry = {
                    "origin": {"bar_index": int(fan_obj_sm.from_pivot.get("bar_index", 0)), "time": int(fan_obj_sm.from_pivot.get("time", 0)), "price": float(fan_obj_sm.from_pivot.get("price", 0.0)), "label": str(fan_obj_sm.from_pivot.get("type", ""))},
                    "anchor": {"bar_index": int(fan_obj_sm.to_pivot.get("bar_index", 0)), "time": int(fan_obj_sm.to_pivot.get("time", 0)), "price": float(fan_obj_sm.to_pivot.get("price", 0.0)), "label": str(fan_obj_sm.to_pivot.get("type", ""))},
                    "rays": [{"id": line.id, "fraction": line.fraction, "points": [{"time": line.start_time, "price": line.start_price}, {"time": line.end_time, "price": line.end_price}], "color": line.color, "width": line.width} for line in fan_obj_sm.lines]
                }

            self.event_logger.log_event(
                timestamp=timestamp,
                event_type=evt_enum,
                angle_name=state_event.fraction,
                price=state_event.price,
                direction=state_event.direction,
                open_price=c_open,
                high_price=c_high,
                low_price=c_low,
                close_price=close_price,
                active_angle_prices=active_angle_prices,
                cluster_state=is_cluster,
                current_zone=current_zone_str,
                zone_highest_close=z_extremes.get('highest_close') if z_extremes else None,
                zone_lowest_close=z_extremes.get('lowest_close') if z_extremes else None,
                next_angle_line=target_info.get('next_angle_line'),
                anchor_bar_index=fan_geom_sm.get('bar_index', 0) if fan_obj_sm is None else getattr(fan_obj_sm, 'anchor_bar_index', fan_geom_sm.get('bar_index', 0)),
                scale_ratio=self.config.get('scale_ratio', 1.0),
                anchor_price=fan_geom_sm.get('price', 0),
                origin_bar_index=origin_bar_index,
                origin_price=origin_price,
                fan_geometry=fan_geometry,
                details={
                    'fan_id': state_event.fan_id,
                    'ui_type': state_event.event_type,
                    'ui_details': state_event.details,
                }
            )

            ui_events.append({
                'time': timestamp,
                'fan': state_event.priority_label,
                'fanIdentity': state_event.fan_identity,
                'fraction': state_event.fraction,
                'price': state_event.price,
                'type': state_event.event_type,
                'details': state_event.details,
                'open': c_open,
                'high': c_high,
                'low': c_low,
                'close': close_price,
                'activeAngles': active_angle_prices,
                'cluster': is_cluster,
                'zone': current_zone_str or "",
                'zoneExtremes': z_extremes or "",
                'bar_index': state_event.bar_index,
                'nextAngleLine': target_info.get('next_angle_line') or "",
                # Fan geometry for angular fan ray reconstruction
                'anchor_bar_index': fan_geom_sm.get('bar_index', 0) if fan_obj_sm is None else getattr(fan_obj_sm, 'anchor_bar_index', fan_geom_sm.get('bar_index', 0)),
                'scale_ratio': self.config.get('scale_ratio', 1.0),
                'anchor_price': fan_geom_sm.get('price', 0),
                'origin_bar_index': origin_bar_index,
                'origin_price': origin_price,
            })

            # Emit target hit event if applicable
            if target_hit:
                # Get zone context using historical state
                last_zone = self.zone_tracker.get_zone_at_bar(target_hit.fan_id, bar_index)
                if not last_zone:
                    last_zone = self.zone_tracker.get_last_zone(target_hit.fan_id)
                    
                current_zone_str = last_zone.zone if last_zone else None
                z_extremes = {'highest_close': last_zone.zone_highest_close, 'lowest_close': last_zone.zone_lowest_close} if last_zone else None
                b_in_zone = last_zone.bars_in_zone if last_zone else None
                target_info = get_target_info_for_event(state_event.fan_id)

                # Get fan geometry context
                target_fan_obj = self.angle_engine.active_fans.get(target_hit.fan_id)
                target_fan_data = self._persisted_fans.get(target_hit.fan_id, {})
                target_fan_geom = target_fan_data.get('anchor', {})
                # Origin: where fan lines radiate from (temporally first pivot)
                origin_bar_index = int(target_fan_obj.from_pivot.get('bar_index', 0)) if target_fan_obj else int(target_fan_data.get('from_pivot', {}).get('bar_index', 0))
                origin_price = float(target_fan_obj.from_pivot.get('price', 0.0)) if target_fan_obj else float(target_fan_data.get('from_pivot', {}).get('price', 0.0))
                fan_geometry = None
                if target_fan_obj and target_fan_obj.lines:
                    fan_geometry = {
                        "origin": {"bar_index": int(target_fan_obj.from_pivot.get("bar_index", 0)), "time": int(target_fan_obj.from_pivot.get("time", 0)), "price": float(target_fan_obj.from_pivot.get("price", 0.0)), "label": str(target_fan_obj.from_pivot.get("type", ""))},
                        "anchor": {"bar_index": int(target_fan_obj.to_pivot.get("bar_index", 0)), "time": int(target_fan_obj.to_pivot.get("time", 0)), "price": float(target_fan_obj.to_pivot.get("price", 0.0)), "label": str(target_fan_obj.to_pivot.get("type", ""))},
                        "rays": [{"id": line.id, "fraction": line.fraction, "points": [{"time": line.start_time, "price": line.start_price}, {"time": line.end_time, "price": line.end_price}], "color": line.color, "width": line.width} for line in target_fan_obj.lines]
                    }

                self.event_logger.log_event(
                    timestamp=timestamp,
                    event_type=EventType.TARGET_HIT,
                    angle_name=target_hit.target_name,
                    price=target_hit.hit_price,
                    open_price=c_open,
                    high_price=c_high,
                    low_price=c_low,
                    close_price=close_price,
                    active_angle_prices=active_angle_prices,
                    cluster_state=is_cluster,
                    current_zone=current_zone_str,
                    zone_highest_close=z_extremes.get('highest_close') if z_extremes else None,
                    zone_lowest_close=z_extremes.get('lowest_close') if z_extremes else None,
                    anchor_bar_index=target_fan_geom.get('bar_index', 0) if target_fan_obj is None else getattr(target_fan_obj, 'anchor_bar_index', target_fan_geom.get('bar_index', 0)),
                    scale_ratio=self.config.get('scale_ratio', 1.0),
                    anchor_price=target_fan_geom.get('price', 0),
                    origin_bar_index=origin_bar_index,
                    origin_price=origin_price,
                    fan_geometry=fan_geometry,
                    details={
                        'fan_id': target_hit.fan_id,
                        'hit_bar': target_hit.hit_bar,
                    }
                )
                self.state_machine.emit_target_hit_state(
                    bar_index=bar_index,
                    fan_id=target_hit.fan_id,
                    fraction=str(target_hit.target_name) if target_hit.target_name else 'main',
                    target_value=str(target_hit.target_name) if target_hit.target_name else 'main',
                    hit_bar=bar_index
                )
                self.log(f"[Tracking] Target HIT: {target_hit.fan_id} {target_hit.target_name}")
                target_info = get_target_info_for_event(target_hit.fan_id)

                # Intra-bar BREACH_CONFIRMED: If TARGET_HIT fires on line N+1 and the previous line N
                # had a pending breach (CROSS_UP/CROSS_DOWN) created in the same bar, confirm it immediately.
                # This handles the case where price crosses line N and touches line N+1 in the same bar.
                self._confirm_pending_breach_if_valid(
                    fan_id=target_hit.fan_id,
                    target_name=target_hit.target_name,
                    bar_index=bar_index,
                    timestamp=timestamp,
                    c_open=c_open, c_high=c_high, c_low=c_low, c_close=close_price,
                    active_angle_prices=active_angle_prices, is_cluster=is_cluster,
                    last_zone=last_zone,
                    ui_events=ui_events,
                    state_event=state_event
                )

                # (Deferred breaches flush logic moved to the end of _process_tracking_modules)
                
                ui_events.append({
                    'time': timestamp,
                    'fan': state_event.priority_label,
                    'fanIdentity': state_event.fan_identity,
                    'fraction': target_hit.target_name,
                    'price': target_hit.hit_price,
                    'type': 'TARGET_HIT',
                    'details': f"Target Reached",
                    'open': c_open,
                    'high': c_high,
                    'low': c_low,
                    'close': close_price,
                    'activeAngles': active_angle_prices,
                    'cluster': is_cluster,
                    'zone': current_zone_str or "",
                    'zoneExtremes': z_extremes or "",
                    'bar_index': bar_index,
                    'nextAngleLine': target_info.get('next_angle_line') or "",
                    # Fan geometry for angular fan ray reconstruction
                    'anchor_bar_index': target_fan_geom.get('bar_index', 0) if target_fan_obj is None else getattr(target_fan_obj, 'anchor_bar_index', target_fan_geom.get('bar_index', 0)),
                    'scale_ratio': self.config.get('scale_ratio', 1.0),
                    'anchor_price': target_fan_geom.get('price', 0),
                    'origin_bar_index': origin_bar_index,
                    'origin_price': origin_price,
                })
            elif state_event.event_type in ('CROSS_UP', 'CROSS_DOWN'):
                target_failed = self.target_progression.on_cross(
                    fan_id=state_event.fan_id,
                    angle_name=state_event.fraction,
                    bar_index=bar_index,
                    price=state_event.price,
                )
                if target_failed:
                    # Get zone context using historical state
                    last_zone = self.zone_tracker.get_zone_at_bar(state_event.fan_id, bar_index)
                    if not last_zone:
                        last_zone = self.zone_tracker.get_last_zone(state_event.fan_id)
                        
                    current_zone_str = last_zone.zone if last_zone else None
                    z_extremes = {'highest_close': last_zone.zone_highest_close, 'lowest_close': last_zone.zone_lowest_close} if last_zone else None
                    b_in_zone = last_zone.bars_in_zone if last_zone else None

                    # Get fan geometry context
                    failed_fan_obj = self.angle_engine.active_fans.get(state_event.fan_id)
                    failed_fan_data = self._persisted_fans.get(state_event.fan_id, {})
                    failed_fan_geom = failed_fan_data.get('anchor', {})
                    # Origin: where fan lines radiate from (temporally first pivot)
                    origin_bar_index = int(failed_fan_obj.from_pivot.get('bar_index', 0)) if failed_fan_obj else int(failed_fan_data.get('from_pivot', {}).get('bar_index', 0))
                    origin_price = float(failed_fan_obj.from_pivot.get('price', 0.0)) if failed_fan_obj else float(failed_fan_data.get('from_pivot', {}).get('price', 0.0))
                    fan_geometry = None
                    if failed_fan_obj and failed_fan_obj.lines:
                        fan_geometry = {
                            "origin": {"bar_index": int(failed_fan_obj.from_pivot.get("bar_index", 0)), "time": int(failed_fan_obj.from_pivot.get("time", 0)), "price": float(failed_fan_obj.from_pivot.get("price", 0.0)), "label": str(failed_fan_obj.from_pivot.get("type", ""))},
                            "anchor": {"bar_index": int(failed_fan_obj.to_pivot.get("bar_index", 0)), "time": int(failed_fan_obj.to_pivot.get("time", 0)), "price": float(failed_fan_obj.to_pivot.get("price", 0.0)), "label": str(failed_fan_obj.to_pivot.get("type", ""))},
                            "rays": [{"id": line.id, "fraction": line.fraction, "points": [{"time": line.start_time, "price": line.start_price}, {"time": line.end_time, "price": line.end_price}], "color": line.color, "width": line.width} for line in failed_fan_obj.lines]
                        }

                    self.event_logger.log_event(
                        timestamp=timestamp,
                        event_type=EventType.TARGET_FAILED,
                        angle_name=state_event.fraction,
                        price=state_event.price,
                        open_price=c_open,
                        high_price=c_high,
                        low_price=c_low,
                        close_price=close_price,
                        active_angle_prices=active_angle_prices,
                        cluster_state=is_cluster,
                        current_zone=current_zone_str,
                        zone_highest_close=z_extremes.get('highest_close') if z_extremes else None,
                        zone_lowest_close=z_extremes.get('lowest_close') if z_extremes else None,
                        anchor_bar_index=failed_fan_geom.get('bar_index', 0) if failed_fan_obj is None else getattr(failed_fan_obj, 'anchor_bar_index', failed_fan_geom.get('bar_index', 0)),
                        scale_ratio=self.config.get('scale_ratio', 1.0),
                        anchor_price=failed_fan_geom.get('price', 0),
                        origin_bar_index=origin_bar_index,
                        origin_price=origin_price,
                        fan_geometry=fan_geometry,
                        details={
                            'fan_id': state_event.fan_id,
                            'fail_bar': bar_index,
                        }
                    )
                    self.log(f"[Tracking] Target FAILED: {state_event.fan_id} crossed back over {state_event.fraction}")

                    ui_events.append({
                        'time': timestamp,
                        'fan': state_event.priority_label,
                        'fanIdentity': state_event.fan_identity,
                        'fraction': state_event.fraction,
                        'price': state_event.price,
                        'type': 'TARGET_FAILED',
                        'details': f"Progression Failed",
                        'open': c_open,
                        'high': c_high,
                        'low': c_low,
                        'close': close_price,
                        'activeAngles': active_angle_prices,
                        'cluster': is_cluster,
                        'zone': current_zone_str or "",
                        'zoneExtremes': z_extremes or "",
                        'nextAngleLine': target_info.get('next_angle_line') or "",
                        # Fan geometry for angular fan ray reconstruction
                        'anchor_bar_index': failed_fan_geom.get('bar_index', 0) if failed_fan_obj is None else getattr(failed_fan_obj, 'anchor_bar_index', failed_fan_geom.get('bar_index', 0)),
                        'scale_ratio': self.config.get('scale_ratio', 1.0),
                        'anchor_price': failed_fan_geom.get('price', 0),
                        'origin_bar_index': origin_bar_index,
                        'origin_price': origin_price,
                    })

        # Flush deferred BREACH_CONFIRMED events now that TARGET_HIT has had a chance
        # to set skip_section2=True on any pending breach (including intra-bar and cross-bar logic)
        deferred_results = self.state_machine.flush_confirmed_breaches()
        for evt in deferred_results:
            last_zone = self.zone_tracker.get_zone_at_bar(evt.fan_id, bar_index)
            if not last_zone:
                last_zone = self.zone_tracker.get_last_zone(evt.fan_id)
            
            c_zone_str = last_zone.zone if last_zone else None
            z_ext = {'highest_close': last_zone.zone_highest_close, 'lowest_close': last_zone.zone_lowest_close} if last_zone else None

            # Map the event type to enum
            try:
                evt_enum = EventType[evt.event_type]
            except KeyError:
                try:
                    evt_enum = EventType(evt.event_type)
                except ValueError:
                    evt_enum = EventType.BREACH_CONFIRMED

            # Get fan geometry context
            def_fan_obj = self.angle_engine.active_fans.get(evt.fan_id)
            def_fan_data = self._persisted_fans.get(evt.fan_id, {})
            def_fan_geom = def_fan_data.get('anchor', {})
            # Origin: where fan lines radiate from (temporally first pivot)
            origin_bar_index = int(def_fan_obj.from_pivot.get('bar_index', 0)) if def_fan_obj else int(def_fan_data.get('from_pivot', {}).get('bar_index', 0))
            origin_price = float(def_fan_obj.from_pivot.get('price', 0.0)) if def_fan_obj else float(def_fan_data.get('from_pivot', {}).get('price', 0.0))
            fan_geometry = None
            if def_fan_obj and def_fan_obj.lines:
                fan_geometry = {
                    "origin": {"bar_index": int(def_fan_obj.from_pivot.get("bar_index", 0)), "time": int(def_fan_obj.from_pivot.get("time", 0)), "price": float(def_fan_obj.from_pivot.get("price", 0.0)), "label": str(def_fan_obj.from_pivot.get("type", ""))},
                    "anchor": {"bar_index": int(def_fan_obj.to_pivot.get("bar_index", 0)), "time": int(def_fan_obj.to_pivot.get("time", 0)), "price": float(def_fan_obj.to_pivot.get("price", 0.0)), "label": str(def_fan_obj.to_pivot.get("type", ""))},
                    "rays": [{"id": line.id, "fraction": line.fraction, "points": [{"time": line.start_time, "price": line.start_price}, {"time": line.end_time, "price": line.end_price}], "color": line.color, "width": line.width} for line in def_fan_obj.lines]
                }

            self.event_logger.log_event(
                timestamp=timestamp,
                event_type=evt_enum,
                angle_name=evt.fraction,
                price=evt.price,
                direction=evt.direction,
                open_price=c_open,
                high_price=c_high,
                low_price=c_low,
                close_price=close_price,
                active_angle_prices=active_angle_prices,
                cluster_state=is_cluster,
                current_zone=c_zone_str,
                zone_highest_close=z_ext.get('highest_close') if z_ext else None,
                zone_lowest_close=z_ext.get('lowest_close') if z_ext else None,
                anchor_bar_index=def_fan_geom.get('bar_index', 0) if def_fan_obj is None else getattr(def_fan_obj, 'anchor_bar_index', def_fan_geom.get('bar_index', 0)),
                scale_ratio=self.config.get('scale_ratio', 1.0),
                anchor_price=def_fan_geom.get('price', 0),
                origin_bar_index=origin_bar_index,
                origin_price=origin_price,
                fan_geometry=fan_geometry,
                details={
                    'fan_id': evt.fan_id,
                    'bars_elapsed': evt.details.split('(')[-1].replace(')', '').strip() if 'bars)' in evt.details else evt.details
                }
            )

            ui_events.append({
                'time': timestamp,
                'fan': evt.priority_label,
                'fanIdentity': evt.fan_identity,
                'fraction': evt.fraction,
                'price': evt.price,
                'type': evt.event_type,
                'details': evt.details,
                'open': c_open,
                'high': c_high,
                'low': c_low,
                'close': close_price,
                'activeAngles': active_angle_prices,
                'cluster': is_cluster,
                'zone': c_zone_str or "",
                'zoneExtremes': z_ext or "",
                'bar_index': evt.bar_index,
                'nextAngleLine': '',
                # Fan geometry for angular fan ray reconstruction
                'anchor_bar_index': def_fan_geom.get('bar_index', 0) if def_fan_obj is None else getattr(def_fan_obj, 'anchor_bar_index', def_fan_geom.get('bar_index', 0)),
                'scale_ratio': self.config.get('scale_ratio', 1.0),
                'anchor_price': def_fan_geom.get('price', 0),
                'origin_bar_index': origin_bar_index,
                'origin_price': origin_price,
            })

        # CRITICAL FIX: If this is the EXACT bar where the fan was created, the trader 
        # still couldn't see the fan until the bar closed. Therefore, any target hits 
        # or breaches that happen ON the creation bar are untradeable and must be 
        # flagged as [Retro].
        for ui_event in ui_events:
            fan_id = "Fan_" + ui_event['fanIdentity'].replace("-", "_")
            if fan_id in self._persisted_fans:
                creation_bar = self._persisted_fans[fan_id].get('creation_bar_index', -1)
                # If the event occurred at or before the bar where the fan was created, it's retro
                if not ui_event['details'].startswith("[Retro]") and bar_index <= creation_bar:
                    ui_event['details'] = f"[Retro] {ui_event['details']}"
                    
                    # Update it in the actual event_logger output as well so events.csv gets the [Retro] flag
                    # This relies on the fact that event_logger.events list is updated chronologically
                    # We just modify the last few events that match
                    for logged_evt in reversed(self.event_logger.events):
                        if logged_evt.timestamp == timestamp and logged_evt.event_type.value == ui_event['type']:
                            # Ensure it has the details dict
                            if hasattr(logged_evt, 'details') and isinstance(logged_evt.details, dict):
                                if 'ui_details' in logged_evt.details:
                                    if not logged_evt.details['ui_details'].startswith("[Retro]"):
                                        logged_evt.details['ui_details'] = f"[Retro] {logged_evt.details['ui_details']}"
                                elif 'deactivation_reason' in logged_evt.details:
                                    pass # target failed etc
                                # The CSV export uses logged_evt.details directly as a string or gets it from dict
                                # In event_logger.py, export_to_csv writes `evt.details`. We need to prepend it there.
                                if 'details_str' not in logged_evt.details:
                                    logged_evt.details['details_str'] = ui_event['details']
                            break

        try:
            pipeline_output = self.event_pipeline.process_bar(
                candles=candles,
                bar_index=bar_index,
                active_fans=self.angle_engine.active_fans,
                fan_validator=self.fan_validator,
            )
            for i, pie in enumerate(pipeline_output.events):
                if i < len(intersection_events):
                    setattr(intersection_events[i], "_typed_event", pie)
        except Exception:
            pass

    def _extend_active_fans(self, candles: List[Dict[str, Any]], current_bar_index: int, result: Dict[str, Any]):
        """
        Dynamically extends fan lines if the price action is approaching the current line ends.
        Disabled: We now use TradingView's native extendRight: true to avoid time-warp bugs.
        """
        pass

    def _sync_fans_build(
        self,
        candles: List[Dict[str, Any]],
        current_bar_index: int,
        result: Dict[str, Any]
    ):
        """
        Core sync build phase: run FanManager, strictly update engine state,
        create new fans. Does NOT remove invalidated fans yet.
        """
        # Generate raw un-capped logical fans
        logical_fans = FanManager.find_active_fans(
            confirmed_pivots=self.pivot_detector.confirmed_pivots,
            candles=candles,
            current_bar_index=current_bar_index,
            breach_mode=self.config['breach_mode']
        )
        
        # Sort by Anchor Time (Descending) -> P1 is most recent
        logical_fans.sort(key=lambda f: f['anchor']['time'], reverse=True)

        # Build map of CURRENT valid fans
        self._current_valid_fan_ids = set()
        
        # Apply Priority Labels based on sorted order
        for i, fan_data in enumerate(logical_fans):
            # Cap max fans here if needed, but FanManager usually handles finding candidates
            # We enforce strict limit of active fans
            if i >= self.config.get('max_historical_fans', 3):
                break
                
            fan_id = fan_data['fan_id']
            self._current_valid_fan_ids.add(fan_id)
            
            fan_data['priority'] = i
            # Embed the full fan identity in the priority label so it propagates to UI controls
            fan_display_name = fan_id.replace("Fan_", "").replace("_", "-")
            fan_data['priority_label'] = f"P{i + 1} ({fan_display_name})"
            
            # Persist fan data (create or update)
            if fan_id not in self._persisted_fans:
                fan_data['creation_bar_index'] = current_bar_index
                fan_data['_coords_changed'] = False
            else:
                old_fan = self._persisted_fans[fan_id]
                fan_data['creation_bar_index'] = old_fan.get('creation_bar_index', current_bar_index)
                
                coords_changed = (
                    fan_data['anchor']['time'] != old_fan['anchor']['time'] or
                    fan_data['anchor']['price'] != old_fan['anchor']['price'] or
                    fan_data['target']['time'] != old_fan['target']['time'] or
                    fan_data['target']['price'] != old_fan['target']['price']
                )
                fan_data['_coords_changed'] = coords_changed
                
            self._persisted_fans[fan_id] = fan_data

        # --- SYNC: Create or Update Valid Fans ---
        for fan_id in self._current_valid_fan_ids:
            fan_data = self._persisted_fans[fan_id]
            
            # Check if fan exists in engine
            if fan_id in self._active_fan_keys:
                # UPDATE existing fan (check priority change OR coordinate change)
                engine_fan_id = self._active_fan_keys[fan_id]
                if engine_fan_id in self.angle_engine.active_fans:
                    fan_obj = self.angle_engine.active_fans[engine_fan_id]
                    
                    # If coordinates changed, we must recreate the fan lines
                    if fan_data.get('_coords_changed', False):
                        self.log(f"[Study] Updating fan coordinates for: {fan_id}")
                        
                        # Queue old lines for removal
                        for line in fan_obj.lines:
                            result['remove_drawings'].append(line.id)
                        for label_id in fan_obj.label_ids:
                            result['remove_drawings'].append(label_id)
                        fan_obj.label_ids.clear()
                        
                        # We must completely replace the fan in the engine to recalculate slopes
                        self.angle_engine.remove_fan(engine_fan_id)
                        
                        new_fan_obj = self.angle_engine.create_fan(
                            from_pivot=fan_data['target'],
                            to_pivot=fan_data['anchor'],
                            current_candles=candles[:current_bar_index + 1],
                            fan_id=fan_data['fan_id'],
                            priority_label=fan_obj.priority_label
                        )
                        new_fan_obj.anchor_type = fan_data['anchor'].get('type', '')
                        new_fan_obj.anchor_bar_index = fan_data['anchor'].get('bar_index', 0)
                        
                        # Catch up zone tracker
                        anchor_bar_idx = new_fan_obj.anchor_bar_index
                        for b_idx in range(anchor_bar_idx, current_bar_index + 1):
                            self.zone_tracker.compute_snapshot(new_fan_obj, candles[b_idx], b_idx)
                        new_fan_obj._zone_caught_up_to = current_bar_index
                        
                        # Re-assign object
                        fan_obj = new_fan_obj
                        self._active_fan_keys[fan_id] = fan_obj.id
                        
                        drawings = self.angle_engine.fan_to_drawing_commands(fan_obj)
                        result['drawings'].extend(drawings)
                        
                    # If priority label changed, we must update drawings
                    elif fan_obj.priority_label != fan_data['priority_label']:
                        self.log(f"[Study] Updating fan priority: {fan_id} -> {fan_data['priority_label']}")
                        fan_obj.priority_label = fan_data['priority_label']
                        
                        # Queue old lines for removal
                        for line in fan_obj.lines:
                            result['remove_drawings'].append(line.id)
                        for label_id in fan_obj.label_ids:
                            result['remove_drawings'].append(label_id)
                        fan_obj.label_ids.clear()
                            
                        # Generate new lines with updated label
                        drawings = self.angle_engine.fan_to_drawing_commands(fan_obj)
                        result['drawings'].extend(drawings)
                        
                        # Re-generate intersection labels
                        for event in fan_obj.intersections:
                            event.priority_label = fan_obj.priority_label
            else:
                # CREATE new fan
                self.log(f"[Study] Creating new fan: {fan_id} ({fan_data['priority_label']})")
                
                fan_obj = self.angle_engine.create_fan(
                    from_pivot=fan_data['target'],   # Target is "from"
                    to_pivot=fan_data['anchor'],      # Anchor is "to"
                    current_candles=candles[:current_bar_index + 1],
                    fan_id=fan_data['fan_id'],
                    priority_label=fan_data['priority_label']
                )
                
                fan_obj.anchor_type = fan_data['anchor'].get('type', '')
                fan_obj.anchor_bar_index = fan_data['anchor'].get('bar_index', 0)
                
                # CRITICAL: Catch up AngleZoneTracker for this new fan
                anchor_bar_idx = fan_obj.anchor_bar_index
                current_bar_idx = current_bar_index
                for b_idx in range(anchor_bar_idx, current_bar_idx + 1):
                    self.zone_tracker.compute_snapshot(fan_obj, candles[b_idx], b_idx)
                fan_obj._zone_caught_up_to = current_bar_idx
                
                # Store mapping
                self._active_fan_keys[fan_id] = fan_obj.id
                
                # Register with tracking
                self.fan_validator.register_fan(fan_obj.id)
                self.target_progression.register_fan(
                    fan_id=fan_obj.id,
                    horizontal_target_price=self._get_horizontal_target_price(fan_obj),
                    full_coverage_target_price=float(fan_data['target'].get('price', 0)),
                )

                # Output drawings for new fan
                drawings = self.angle_engine.fan_to_drawing_commands(fan_obj)
                result['drawings'].extend(drawings)
                
                # Setup retroactive sweep parameters (used later in _process_tracking_modules)
                self._pending_retro_events[fan_id] = {
                    'anchor_idx': anchor_bar_idx,
                    'events': [] # populated by retroactive scan
                }

    def _sync_fans_teardown(
        self,
        candles: List[Dict[str, Any]],
        current_bar_index: int,
        result: Dict[str, Any]
    ):
        """
        Core sync teardown phase: Remove invalidated fans AFTER they have processed the current bar.
        """
        current_valid_fan_ids = getattr(self, '_current_valid_fan_ids', set())
        
        # --- SYNC: Remove Invalid Fans ---
        # Identify fans in our persisted state that are NO LONGER valid
        # (or pushed out of the top N limit)
        existing_fan_ids = list(self._persisted_fans.keys())
        for fan_id in existing_fan_ids:
            if fan_id not in current_valid_fan_ids:
                self.log(f"[Study] Removing invalidated/excess fan: {fan_id}")
                
                # If it has an engine representation, remove it
                if fan_id in self._active_fan_keys:
                    engine_fan_id = self._active_fan_keys[fan_id]
                    if engine_fan_id in self.angle_engine.active_fans:
                        fan_obj = self.angle_engine.active_fans[engine_fan_id]
                        # Queue lines for removal
                        for line in fan_obj.lines:
                            result['remove_drawings'].append(line.id)
                        for label_id in fan_obj.label_ids:
                            result['remove_drawings'].append(label_id)
                        self.angle_engine.remove_fan(engine_fan_id)
                    
                    del self._active_fan_keys[fan_id]

                # Clean up tracking modules
                self.zone_tracker.remove_fan(fan_id)
                self.fan_validator.remove_fan(fan_id)

                # TARGET_FAILED: Get pending progression info BEFORE removing fan state
                pending_state = None
                if self.target_progression.has_pending_progression(fan_id):
                    pending_state = self.target_progression._fan_states.get(fan_id)

                self.target_progression.remove_fan(fan_id)
                self.state_machine.remove_fan(fan_id)

                # CRITICAL FIX: Release pivots so they can form new fans with new labels
                # This ensures that H1-L1 fan (deactivated) + new H pivot = H2-L1 fan (not H1-L1)
                if fan_id in self._persisted_fans:
                    fan_data = self._persisted_fans[fan_id]
                    anchor_time = fan_data.get('anchor', {}).get('time', 0)
                    anchor_price = fan_data.get('anchor', {}).get('price', 0)
                    target_time = fan_data.get('target', {}).get('time', 0)
                    target_price = fan_data.get('target', {}).get('price', 0)
                    fan_priority = fan_data.get('priority_label', fan_id)
                    
                    current_candle = candles[current_bar_index]
                    current_time = int(current_candle['time'])
                    current_close = float(current_candle['close'])

                    # Initialize intersection_events if missing
                    if 'intersection_events' not in result:
                        result['intersection_events'] = []

                    # TARGET_FAILED: Emit if there was an in-flight progression when fan got invalidated
                    # (breach confirmed on origin_angle but next target wasn't reached)
                    if pending_state:
                        # Check if the invalidation was actually a full_coverage hit
                        is_full_coverage_hit = False
                        fc_price = pending_state.full_coverage_target_price
                        if pending_state.current_target == 'full_coverage' and fc_price is not None:
                            c_high = float(current_candle.get('high', 0))
                            c_low = float(current_candle.get('low', 0))
                            fan_dir = 'up' if fan_data.get('anchor', {}).get('type') == 'low' else 'down'
                            
                            # Fan dir 'up' means anchor is low, target is high.
                            # Full coverage hit if current high >= fc_price
                            if fan_dir == 'up' and c_high >= fc_price:
                                is_full_coverage_hit = True
                            elif fan_dir == 'down' and c_low <= fc_price:
                                is_full_coverage_hit = True

                        if is_full_coverage_hit:
                            # Log TARGET_HIT instead of TARGET_FAILED
                            # Origin: from persisted fan data
                            origin_bar_index = int(fan_data.get('from_pivot', {}).get('bar_index', 0))
                            origin_price = float(fan_data.get('from_pivot', {}).get('price', 0.0))
                            fc_fan_obj = self.angle_engine.active_fans.get(fan_id)
                            fan_geometry = None
                            if fc_fan_obj and fc_fan_obj.lines:
                                fan_geometry = {
                                    "origin": {"bar_index": int(fc_fan_obj.from_pivot.get("bar_index", 0)), "time": int(fc_fan_obj.from_pivot.get("time", 0)), "price": float(fc_fan_obj.from_pivot.get("price", 0.0)), "label": str(fc_fan_obj.from_pivot.get("type", ""))},
                                    "anchor": {"bar_index": int(fc_fan_obj.to_pivot.get("bar_index", 0)), "time": int(fc_fan_obj.to_pivot.get("time", 0)), "price": float(fc_fan_obj.to_pivot.get("price", 0.0)), "label": str(fc_fan_obj.to_pivot.get("type", ""))},
                                    "rays": [{"id": line.id, "fraction": line.fraction, "points": [{"time": line.start_time, "price": line.start_price}, {"time": line.end_time, "price": line.end_price}], "color": line.color, "width": line.width} for line in fc_fan_obj.lines]
                                }
                            self.event_logger.log_event(
                                timestamp=current_time,
                                event_type=EventType.TARGET_HIT,
                                angle_name='full_coverage',
                                price=fc_price,
                                open_price=float(current_candle['open']),
                                high_price=float(current_candle['high']),
                                low_price=float(current_candle['low']),
                                close_price=current_close,
                                active_angle_prices={},
                                cluster_state=False,
                                current_zone="",
                                zone_highest_close=None,
                                zone_lowest_close=None,
                                next_angle_line=None,
                                anchor_bar_index=fan_data.get('anchor', {}).get('bar_index', 0),
                                scale_ratio=self.config.get('scale_ratio', 1.0),
                                anchor_price=fan_data.get('anchor', {}).get('price', 0),
                                origin_bar_index=origin_bar_index,
                                origin_price=origin_price,
                                fan_geometry=fan_geometry,
                                details={
                                    'fan_id': fan_id,
                                    'fan_label': fan_priority,
                                    'ui_type': 'TARGET_HIT',
                                    'ui_details': 'Full Coverage Reached',
                                }
                            )
                            ui_event_dict = {
                                'time': current_time,
                                'fan': fan_priority,
                                'fanIdentity': fan_id.replace("Fan_", "").replace("_", "-"),
                                'fraction': 'full_coverage',
                                'price': fc_price,
                                'type': 'TARGET_HIT',
                                'details': "Full Coverage Reached",
                                'open': float(current_candle['open']),
                                'high': float(current_candle['high']),
                                'low': float(current_candle['low']),
                                'close': current_close,
                                'activeAngles': {},
                                'cluster': False,
                                'zone': "",
                                'zoneExtremes': {},
                                'bar_index': current_bar_index,
                                'nextAngleLine': '',
                                # Fan geometry for angular fan ray reconstruction
                                'anchor_bar_index': fan_data.get('anchor', {}).get('bar_index', 0),
                                'scale_ratio': self.config.get('scale_ratio', 1.0),
                                'anchor_price': fan_data.get('anchor', {}).get('price', 0),
                            }
                            # Apply Retro flag if needed
                            creation_bar = fan_data.get('creation_bar_index', -1)
                            if current_bar_index <= creation_bar:
                                ui_event_dict['details'] = f"[Retro] {ui_event_dict['details']}"
                                # Also update the logger
                                for logged_evt in reversed(self.event_logger.events):
                                    if logged_evt.timestamp == current_time and logged_evt.event_type.value == 'TARGET_HIT':
                                        if hasattr(logged_evt, 'details') and isinstance(logged_evt.details, dict):
                                            if 'ui_details' in logged_evt.details:
                                                if not logged_evt.details['ui_details'].startswith("[Retro]"):
                                                    logged_evt.details['ui_details'] = f"[Retro] {logged_evt.details['ui_details']}"
                                            if 'details_str' not in logged_evt.details:
                                                logged_evt.details['details_str'] = ui_event_dict['details']
                                        break
                                        
                            result['intersection_events'].append(ui_event_dict)
                            self.log(f"[Tracking] Target HIT: {fan_id} reached full_coverage!")
                        else:
                            origin_bar_index = int(fan_data.get('from_pivot', {}).get('bar_index', 0))
                            origin_price = float(fan_data.get('from_pivot', {}).get('price', 0.0))
                            tf_fan_obj = self.angle_engine.active_fans.get(fan_id)
                            fan_geometry = None
                            if tf_fan_obj and tf_fan_obj.lines:
                                fan_geometry = {
                                    "origin": {"bar_index": int(tf_fan_obj.from_pivot.get("bar_index", 0)), "time": int(tf_fan_obj.from_pivot.get("time", 0)), "price": float(tf_fan_obj.from_pivot.get("price", 0.0)), "label": str(tf_fan_obj.from_pivot.get("type", ""))},
                                    "anchor": {"bar_index": int(tf_fan_obj.to_pivot.get("bar_index", 0)), "time": int(tf_fan_obj.to_pivot.get("time", 0)), "price": float(tf_fan_obj.to_pivot.get("price", 0.0)), "label": str(tf_fan_obj.to_pivot.get("type", ""))},
                                    "rays": [{"id": line.id, "fraction": line.fraction, "points": [{"time": line.start_time, "price": line.start_price}, {"time": line.end_time, "price": line.end_price}], "color": line.color, "width": line.width} for line in tf_fan_obj.lines]
                                }
                            self.event_logger.log_event(
                                timestamp=current_time,
                                event_type=EventType.TARGET_FAILED,
                                angle_name=pending_state.origin_angle,
                                price=current_close,
                                direction='down' if fan_data.get('anchor', {}).get('type') == 'high' else 'up',
                                anchor_bar_index=fan_data.get('anchor', {}).get('bar_index', 0),
                                scale_ratio=self.config.get('scale_ratio', 1.0),
                                anchor_price=fan_data.get('anchor', {}).get('price', 0),
                                origin_bar_index=origin_bar_index,
                                origin_price=origin_price,
                                fan_geometry=fan_geometry,
                                details={
                                    'fan_id': fan_id,
                                    'fan_label': fan_priority,
                                    'deactivation_reason': 'fan_invalidated',
                                    'pending_target': pending_state.current_target,
                                    'targets_hit': pending_state.targets_hit,
                                }
                            )
                            
                            ui_event_dict = {
                                'time': current_time,
                                'fan': fan_priority,
                                'fanIdentity': fan_id.replace("Fan_", "").replace("_", "-"),
                                'fraction': pending_state.origin_angle,
                                'price': current_close,
                                'type': 'TARGET_FAILED',
                                'details': f"Progression Failed (fan invalidated)",
                                'open': float(current_candle['open']),
                                'high': float(current_candle['high']),
                                'low': float(current_candle['low']),
                                'close': current_close,
                                'activeAngles': {},
                                'cluster': False,
                                'zone': "",
                                'zoneExtremes': {},
                                'bar_index': current_bar_index,
                                'nextAngleLine': pending_state.current_target or "",
                                # Fan geometry for angular fan ray reconstruction
                                'anchor_bar_index': fan_data.get('anchor', {}).get('bar_index', 0),
                                'scale_ratio': self.config.get('scale_ratio', 1.0),
                                'anchor_price': fan_data.get('anchor', {}).get('price', 0),
                            }
                            # Apply Retro flag if needed
                            creation_bar = fan_data.get('creation_bar_index', -1)
                            if current_bar_index <= creation_bar:
                                ui_event_dict['details'] = f"[Retro] {ui_event_dict['details']}"
                                # Also update the logger
                                for logged_evt in reversed(self.event_logger.events):
                                    if logged_evt.timestamp == current_time and logged_evt.event_type.value == 'TARGET_FAILED':
                                        if hasattr(logged_evt, 'details') and isinstance(logged_evt.details, dict):
                                            if 'ui_details' in logged_evt.details:
                                                if not logged_evt.details['ui_details'].startswith("[Retro]"):
                                                    logged_evt.details['ui_details'] = f"[Retro] {logged_evt.details['ui_details']}"
                                            if 'details_str' not in logged_evt.details:
                                                logged_evt.details['details_str'] = ui_event_dict['details']
                                        break
                            
                            result['intersection_events'].append(ui_event_dict)
                            
                            self.log(f"[Tracking] Target FAILED: {fan_id} ({pending_state.origin_angle}) - fan invalidated with pending progression")

                    # Log FAN_DEACTIVATED event
                    if anchor_time:
                        try:
                            # Get fan geometry context
                            deact_anchor = fan_data.get('anchor', {})
                            origin_bar_index = int(fan_data.get('from_pivot', {}).get('bar_index', 0))
                            origin_price = float(fan_data.get('from_pivot', {}).get('price', 0.0))
                            deact_fan_obj = self.angle_engine.active_fans.get(fan_id)
                            fan_geometry = None
                            if deact_fan_obj and deact_fan_obj.lines:
                                fan_geometry = {
                                    "origin": {"bar_index": int(deact_fan_obj.from_pivot.get("bar_index", 0)), "time": int(deact_fan_obj.from_pivot.get("time", 0)), "price": float(deact_fan_obj.from_pivot.get("price", 0.0)), "label": str(deact_fan_obj.from_pivot.get("type", ""))},
                                    "anchor": {"bar_index": int(deact_fan_obj.to_pivot.get("bar_index", 0)), "time": int(deact_fan_obj.to_pivot.get("time", 0)), "price": float(deact_fan_obj.to_pivot.get("price", 0.0)), "label": str(deact_fan_obj.to_pivot.get("type", ""))},
                                    "rays": [{"id": line.id, "fraction": line.fraction, "points": [{"time": line.start_time, "price": line.start_price}, {"time": line.end_time, "price": line.end_price}], "color": line.color, "width": line.width} for line in deact_fan_obj.lines]
                                }
                            self.event_logger.log_event(
                                timestamp=current_time,
                                event_type=EventType.FAN_DEACTIVATED,
                                price=current_close,
                                anchor_bar_index=deact_anchor.get('bar_index', 0),
                                scale_ratio=self.config.get('scale_ratio', 1.0),
                                anchor_price=deact_anchor.get('price', 0),
                                origin_bar_index=origin_bar_index,
                                origin_price=origin_price,
                                fan_geometry=fan_geometry,
                                details={
                                    'fan_id': fan_id,
                                    'fan_label': fan_priority,
                                    'deactivation_reason': 'completed'
                                }
                            )
                            
                            ui_event_dict = {
                                'time': current_time,
                                'fan': fan_priority,
                                'fanIdentity': fan_id.replace("Fan_", "").replace("_", "-"),
                                'fraction': '-',
                                'price': current_close,
                                'type': 'FAN_DEACTIVATED',
                                'details': f"Fan Invalidated",
                                'open': float(current_candle['open']),
                                'high': float(current_candle['high']),
                                'low': float(current_candle['low']),
                                'close': current_close,
                                'activeAngles': {},
                                'cluster': False,
                                'zone': "",
                                'zoneExtremes': {},
                                'bar_index': current_bar_index,
                                'nextAngleLine': '',
                                # Fan geometry for angular fan ray reconstruction
                                'anchor_bar_index': deact_anchor.get('bar_index', 0),
                                'scale_ratio': self.config.get('scale_ratio', 1.0),
                                'anchor_price': deact_anchor.get('price', 0),
                            }
                            # Apply Retro flag if needed
                            creation_bar = fan_data.get('creation_bar_index', -1)
                            if current_bar_index <= creation_bar:
                                ui_event_dict['details'] = f"[Retro] {ui_event_dict['details']}"
                                # Also update the logger
                                for logged_evt in reversed(self.event_logger.events):
                                    if logged_evt.timestamp == current_time and logged_evt.event_type.value == 'FAN_DEACTIVATED':
                                        if hasattr(logged_evt, 'details') and isinstance(logged_evt.details, dict):
                                            if 'ui_details' in logged_evt.details:
                                                if not logged_evt.details['ui_details'].startswith("[Retro]"):
                                                    logged_evt.details['ui_details'] = f"[Retro] {logged_evt.details['ui_details']}"
                                            if 'details_str' not in logged_evt.details:
                                                logged_evt.details['details_str'] = ui_event_dict['details']
                                        break
                                        
                            result['intersection_events'].append(ui_event_dict)
                            
                            self.state_machine.emit_fan_deactivated_state(
                                bar_index=current_bar_index,
                                fan_id=fan_id,
                                reason='COMPLETED'
                            )
                        except Exception as e:
                            print(f"Failed to log FAN_DEACTIVATED: {e}")

                    # DO NOT RELEASE PIVOTS! Releasing pivots breaks the successive filtering 
                    # logic in PivotDetector, causing duplicate pivots to be added rather than replaced.
                    # if 'anchor' in fan_data:
                    #     anchor_time = fan_data['anchor'].get('time')
                    #     anchor_type = fan_data['anchor'].get('type')
                    #     if anchor_time and anchor_type:
                    #         self.pivot_detector.release_pivot(anchor_time, anchor_type)
                    # if 'target' in fan_data:
                    #     target_time = fan_data['target'].get('time')
                    #     target_type = fan_data['target'].get('type')
                    #     if target_time and target_type:
                    #         self.pivot_detector.release_pivot(target_time, target_type)

                    # Remove from persistence
                del self._persisted_fans[fan_id]
        for fan_id in self._current_valid_fan_ids:
            fan_data = self._persisted_fans[fan_id]
            
            # Check if fan exists in engine
            if fan_id in self._active_fan_keys:
                # UPDATE existing fan (check priority change)
                engine_fan_id = self._active_fan_keys[fan_id]
                if engine_fan_id in self.angle_engine.active_fans:
                    fan_obj = self.angle_engine.active_fans[engine_fan_id]
                    
                    # If priority label changed, we must update drawings
                    if fan_obj.priority_label != fan_data['priority_label']:
                        self.log(f"[Study] Updating fan priority: {fan_id} -> {fan_data['priority_label']}")
                        fan_obj.priority_label = fan_data['priority_label']
                        
                        # Queue old lines for removal
                        for line in fan_obj.lines:
                            result['remove_drawings'].append(line.id)
                        for label_id in fan_obj.label_ids:
                            result['remove_drawings'].append(label_id)
                        fan_obj.label_ids.clear()
                            
                        # Generate new lines with updated label
                        drawings = self.angle_engine.fan_to_drawing_commands(fan_obj)
                        result['drawings'].extend(drawings)
                        
                        # Re-generate intersection labels
                        for event in fan_obj.intersections:
                            event.priority_label = fan_obj.priority_label
            else:
                # CREATE new fan
                self.log(f"[Study] Creating new fan: {fan_id} ({fan_data['priority_label']})")
                
                fan_obj = self.angle_engine.create_fan(
                    from_pivot=fan_data['target'],   # Target is "from"
                    to_pivot=fan_data['anchor'],      # Anchor is "to"
                    current_candles=candles[:current_bar_index + 1],
                    fan_id=fan_data['fan_id'],
                    priority_label=fan_data['priority_label']
                )
                
                fan_obj.anchor_type = fan_data['anchor'].get('type', '')
                fan_obj.anchor_bar_index = fan_data['anchor'].get('bar_index', 0)
                
                # CRITICAL: Catch up AngleZoneTracker for this new fan
                anchor_bar_idx = fan_obj.anchor_bar_index
                current_bar_idx = current_bar_index
                for b_idx in range(anchor_bar_idx, current_bar_idx + 1):
                    self.zone_tracker.compute_snapshot(fan_obj, candles[b_idx], b_idx)
                fan_obj._zone_caught_up_to = current_bar_idx
                
                # Store mapping
                self._active_fan_keys[fan_id] = fan_obj.id
                
                # Register with tracking
                self.fan_validator.register_fan(fan_obj.id)
                self.target_progression.register_fan(
                    fan_id=fan_obj.id,
                    horizontal_target_price=self._get_horizontal_target_price(fan_obj),
                    full_coverage_target_price=float(fan_data['target'].get('price', 0)),
                )
                
                # CRITICAL FIX: Perform Retroactive Sweep
                # When a new fan is created, we must look back to the anchor bar
                # and retroactively detect all historical intersections with the new angle lines.
                # This builds correct state machine context for retro events.
                anchor_bar_idx = fan_data['anchor'].get('bar_index', 0)
                current_bar_idx = current_bar_index
                
                print(f"[RetroSweep] New fan {fan_obj.id} created. Anchor at bar {anchor_bar_idx}, current bar {current_bar_idx}")
                retro_events = self.intersection_detector.retroactive_sweep(
                    fan=fan_obj,
                    candles=candles,
                    anchor_bar_idx=anchor_bar_idx,
                    current_bar_idx=current_bar_idx
                )
                
                # Store retro events temporarily - we'll process them after knowing if fan stays active
                if not hasattr(self, '_pending_retro_events'):
                    self._pending_retro_events = {}
                self._pending_retro_events[fan_obj.id] = {
                    'events': retro_events,
                    'anchor_idx': anchor_bar_idx
                }
                
                # Generate drawings (these will be removed later if fan gets deactivated)
                drawings = self.angle_engine.fan_to_drawing_commands(fan_obj)
                result['drawings'].extend(drawings)

        # Add pivot markers for debugging
        self._add_fan_markers(result)

    def _add_fan_markers(self, result: Dict[str, Any]):
        """Add pivot markers ONLY for active persisted fan pivots."""
        seen = set()
        current_marker_ids = set()

        for fan in self._persisted_fans.values():
            # Anchor marker
            a = fan['anchor']
            p_key_a = f"pivot_marker_{a['time']}"
            if p_key_a not in seen:
                seen.add(p_key_a)
                current_marker_ids.add(p_key_a)
                result['pivot_markers'].append({
                    'id': p_key_a,
                    'type': f"pivot_{a['type']}",
                    'time': a['time'],
                    'price': a['price'],
                    'bar_index': a.get('bar_index', 0),
                    'text': a.get('label', 'A')
                })

            # Target marker
            t = fan['target']
            p_key_t = f"pivot_marker_{t['time']}"
            if p_key_t not in seen:
                seen.add(p_key_t)
                current_marker_ids.add(p_key_t)
                result['pivot_markers'].append({
                    'id': p_key_t,
                    'type': f"pivot_{t['type']}",
                    'time': t['time'],
                    'price': t['price'],
                    'bar_index': t.get('bar_index', 0),
                    'text': t.get('label', 'T')
                })
        
        # Diff with previous state to find markers to remove
        for old_id in self._active_marker_ids:
            if old_id not in current_marker_ids:
                result['remove_drawings'].append(old_id)
        
        # Update state
        self._active_marker_ids = current_marker_ids

    def _confirm_pending_breach_if_valid(
        self,
        fan_id: str,
        target_name: str,
        bar_index: int,
        timestamp: int,
        c_open: float, c_high: float, c_low: float, c_close: float,
        active_angle_prices: Dict[str, float],
        is_cluster: bool,
        last_zone: Any,
        ui_events: list,
        state_event: Any
    ):
        """
        Confirm the previous line's pending breach when TARGET_HIT fires on the next line.

        This handles two cases:
        1. Intra-bar (same bar): price crosses line N and touches line N+1 in the same bar.
           In this case first_breach_bar == bar_index.
        2. Cross-bar: pending breach on line N was created on an earlier bar, price advances
           to line N+1 and TARGET_HIT fires before the pending breach confirms. In this
           case first_breach_bar < bar_index, but we still confirm the prior pending breach
           as BREACH_CONFIRMED_NO_ALPHA (no tradeable alpha since the progression advanced
           without the prior breach resolving normally).
        """
        state_machine_state = self.state_machine.pending_breaches

        # Build prev_line based on which target was just hit
        # After 0.5, horizontal is reached from 0.5
        if target_name in ('horizontal', '0.25'):
            prev_line = '0.5'
        elif target_name in ('0.875', '0.75'):
            target_sequence = ['0.875', '0.75', '0.5']
            target_idx = target_sequence.index(target_name)
            prev_line = target_sequence[target_idx - 1]
        elif target_name == '0.5':
            prev_line = '0.75'
        else:
            return  # main or unknown - no intra-bar confirmation

        # Search pending_breaches for this fan and previous line (no bar-index restriction)
        # Removed first_breach_bar == bar_index so cross-bar TARGET_HIT also confirms
        prev_state_key = None
        prev_line_str = str(prev_line)
        for key in state_machine_state:
            if key.startswith(f"{fan_id}_"):
                state = state_machine_state[key]
                stored_frac = state.get('fraction')
                frac_str = str(stored_frac) if stored_frac is not None else None
                if frac_str == prev_line_str:
                    prev_state_key = key
                    self.log(f"[Tracking] BREACH_CONFIRMED_NO_ALPHA: found pending on {key} "
                             f"fraction={frac_str} bar={bar_index} (cross-bar)")
                    break

        if not prev_state_key:
            self.log(f"[Tracking] BREACH_CONFIRMED_NO_ALPHA: no pending found for fan={fan_id} prev_line={prev_line}")
            return

        state = state_machine_state[prev_state_key]

        # Mark it so section 2 skips its BREACH_CONFIRMED emission
        # Mark it so section 2 skips its BREACH_CONFIRMED emission
        state['skip_section2'] = True

        # Delete from pending_breaches so flush_confirmed_breaches() ignores it completely.
        # We will handle ALL emissions for this NO_ALPHA event right here.
        del self.state_machine.pending_breaches[prev_state_key]
        self.state_machine.mark_breach_confirmed(fan_id, prev_line)

        # 1. Emit to Event Logger (CSV)
        # Get fan geometry context
        noalpha_fan_data = self._persisted_fans.get(fan_id, {})
        noalpha_fan_geom = noalpha_fan_data.get('anchor', {})
        noalpha_fan_obj = self.angle_engine.active_fans.get(fan_id)
        # Origin: where fan lines radiate from (temporally first pivot)
        origin_bar_index = int(noalpha_fan_obj.from_pivot.get('bar_index', 0)) if noalpha_fan_obj else int(noalpha_fan_data.get('from_pivot', {}).get('bar_index', 0))
        origin_price = float(noalpha_fan_obj.from_pivot.get('price', 0.0)) if noalpha_fan_obj else float(noalpha_fan_data.get('from_pivot', {}).get('price', 0.0))
        fan_geometry = None
        if noalpha_fan_obj and noalpha_fan_obj.lines:
            fan_geometry = {
                "origin": {"bar_index": int(noalpha_fan_obj.from_pivot.get("bar_index", 0)), "time": int(noalpha_fan_obj.from_pivot.get("time", 0)), "price": float(noalpha_fan_obj.from_pivot.get("price", 0.0)), "label": str(noalpha_fan_obj.from_pivot.get("type", ""))},
                "anchor": {"bar_index": int(noalpha_fan_obj.to_pivot.get("bar_index", 0)), "time": int(noalpha_fan_obj.to_pivot.get("time", 0)), "price": float(noalpha_fan_obj.to_pivot.get("price", 0.0)), "label": str(noalpha_fan_obj.to_pivot.get("type", ""))},
                "rays": [{"id": line.id, "fraction": line.fraction, "points": [{"time": line.start_time, "price": line.start_price}, {"time": line.end_time, "price": line.end_price}], "color": line.color, "width": line.width} for line in noalpha_fan_obj.lines]
            }

        self.event_logger.log_event(
            timestamp=timestamp,
            event_type=EventType.BREACH_CONFIRMED_NO_ALPHA,
            angle_name=prev_line,
            price=c_close,
            direction='up' if state.get('direction') == 'up' else 'down',
            open_price=c_open,
            high_price=c_high,
            low_price=c_low,
            close_price=c_close,
            active_angle_prices=active_angle_prices,
            cluster_state=is_cluster,
            current_zone=last_zone.zone if last_zone else None,
            zone_highest_close=last_zone.zone_highest_close if last_zone else None,
            zone_lowest_close=last_zone.zone_lowest_close if last_zone else None,
            anchor_bar_index=noalpha_fan_geom.get('bar_index', 0),
            scale_ratio=self.config.get('scale_ratio', 1.0),
            anchor_price=noalpha_fan_geom.get('price', 0),
            origin_bar_index=origin_bar_index,
            origin_price=origin_price,
            fan_geometry=fan_geometry,
            details={
                'fan_id': fan_id,
                'cross_bar': True
            }
        )

        # 2. Write to Trace Log directly
        dir_str = 'UP' if state.get('direction') == 'up' else 'DOWN'
        pending_bar = state.get('first_breach_bar', bar_index)
        bec = float(state.get('bec_close', c_close))
        zec_h = float(state.get('zec_high', c_close))
        zec_l = float(state.get('zec_low', c_close))
        state_str = (
            f"[STATE] pending_breach: fan={fan_id} line={prev_line} direction={dir_str} "
            f"bec_close={bec:.2f} zec_high={zec_h:.2f} zec_low={zec_l:.2f} "
            f"pending_bar={pending_bar} outcome=BREACH_CONFIRMED_NO_ALPHA"
        )
        import datetime
        dt_str = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')
        with open(self.state_machine.trace_log_path, 'a', encoding='utf-8') as f:
            f.write(f"[Bar {bar_index}] [{dt_str}] [O:{c_open:.2f}, H:{c_high:.2f}, L:{c_low:.2f}, C:{c_close:.2f}]  -> {state_str}\n")

        # 3. Append to UI Events
        ui_events.append({
            'time': timestamp,
            'fan': state_event.priority_label if hasattr(state_event, 'priority_label') else fan_id,
            'fanIdentity': state_event.fan_identity if hasattr(state_event, 'fan_identity') else fan_id.split('_')[-1],
            'fraction': prev_line,
            'price': c_close,
            'type': 'BREACH_CONFIRMED_NO_ALPHA',
            'details': 'Target hit before breach confirmation (cross-bar)',
            'open': c_open,
            'high': c_high,
            'low': c_low,
            'close': c_close,
            'activeAngles': active_angle_prices,
            'cluster': is_cluster,
            'zone': last_zone.zone if last_zone else None,
            'zoneExtremes': {
                'highest_close': last_zone.zone_highest_close if last_zone else None,
                'lowest_close': last_zone.zone_lowest_close if last_zone else None
            },
            'bar_index': bar_index,
            'nextAngleLine': '',
            # Fan geometry for angular fan ray reconstruction
            'anchor_bar_index': noalpha_fan_geom.get('bar_index', 0),
            'scale_ratio': self.config.get('scale_ratio', 1.0),
            'anchor_price': noalpha_fan_geom.get('price', 0),
            'origin_bar_index': origin_bar_index,
            'origin_price': origin_price,
        })

        self.log(f"[Tracking] BREACH_CONFIRMED_NO_ALPHA (via target progression): {fan_id} {prev_line}")

    def _get_horizontal_target_price(self, fan_obj) -> Optional[float]:
        """
        Extract the horizontal target price from a fan's lines.
        The horizontal target line has fraction=None (uniquely identified).
        """
        for line in fan_obj.lines:
            if line.fraction is None:
                return line.end_price
        return None

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
            'zone_tracker': self.zone_tracker.get_state(),
            'fan_validator': self.fan_validator.get_state(),
            'target_progression': self.target_progression.get_state(),
            'state_machine': self.state_machine.get_state(),
            'cluster_detector': self.cluster_detector.get_state(),
            'historical_clusters': getattr(self, '_historical_clusters', []),
            'event_logger': {
                'events': [e.to_dict() for e in self.event_logger.events],
                'indicator_snapshots': self.event_logger.indicator_snapshots
            },
            'active_fan_keys': dict(self._active_fan_keys),
            'persisted_fans': dict(self._persisted_fans),
            'active_marker_ids': list(self._active_marker_ids),
            'is_initialized': self._is_initialized,
            'initialized': self._initialized,
            'config': self.config,
            'pending_retro_events': dict(self._pending_retro_events)
        }

    def _restore_state(self, state: Dict[str, Any]):
        """Restore state from serialized form."""
        if 'pivot_detector' in state:
            self.pivot_detector.restore_state(state['pivot_detector'])
        if 'angle_engine' in state:
            self.angle_engine.restore_state(state['angle_engine'])
        if 'intersection_detector' in state:
            self.intersection_detector.restore_state(state['intersection_detector'])
        if 'zone_tracker' in state:
            self.zone_tracker.restore_state(state['zone_tracker'])
        if 'state_machine' in state:
            self.state_machine.restore_state(state['state_machine'])
        if 'fan_validator' in state:
            self.fan_validator.restore_state(state['fan_validator'])
        if 'target_progression' in state:
            self.target_progression.restore_state(state['target_progression'])
        if 'cluster_detector' in state:
            self.cluster_detector.restore_state(state['cluster_detector'])
        if 'historical_clusters' in state:
            self._historical_clusters = list(state['historical_clusters'])
        if 'event_logger' in state:
            # Restore event logger state
            logger_state = state['event_logger']
            self.event_logger.events = []
            for evt_dict in logger_state.get('events', []):
                # Reconstruct Event object using from_dict
                try:
                    from .event_logger import Event
                    self.event_logger.events.append(Event.from_dict(evt_dict))
                except Exception as e:
                    self.log(f"[Study] Failed to restore event: {e}")
            
            self.event_logger.indicator_snapshots = logger_state.get('indicator_snapshots', [])
            
        if 'active_fan_keys' in state:
            self._active_fan_keys = state['active_fan_keys']
        if 'persisted_fans' in state:
            self._persisted_fans = state['persisted_fans']
        if 'active_marker_ids' in state:
            self._active_marker_ids = set(state['active_marker_ids'])
        if 'is_initialized' in state:
            self._is_initialized = state['is_initialized']
        if 'initialized' in state:
            self._initialized = state['initialized']
        if 'config' in state:
            self.config = {**DEFAULT_CONFIG, **state['config']}
        if 'pending_retro_events' in state:
            self._pending_retro_events = dict(state['pending_retro_events'])


# Factory function
def create_study(config: Optional[Dict[str, Any]] = None) -> AngularPriceCoverageStudy:
    return AngularPriceCoverageStudy(config)
