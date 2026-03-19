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
from .breach_analyzer import BreachAnalyzer
from .fan_validator import FanValidator
from .target_progression import TargetProgression
from .event_logger import EventLogger, EventType

# --- LOGGING CONFIGURATION (Unified Strategy) ---
# We maintain single files for both debug logs and intersection data per backend process run.
# Old logs are cleaned up on startup, matching the behavior of backend_session_*.log in main.py.

_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_log_dir = os.path.join(_backend_dir, 'logs', 'study_debug')
_csv_dir = os.path.join(_backend_dir, 'logs')

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
        self.breach_analyzer = BreachAnalyzer({
            'successive_closes_required': self.config.get('successive_closes_required', 2),
            'rest_tolerance_percent': self.config.get('rest_tolerance_percent', 0.15),
        })
        self.fan_validator = FanValidator()
        self.target_progression = TargetProgression()
        self.event_logger = EventLogger()

        # Track active fan keys for diffing (old vs new set)
        self._active_fan_keys: Dict[str, str] = {}  # fan_key -> engine_fan_id
        
        # State machine persistent roster: fan_id -> fan_data
        self._persisted_fans: Dict[str, Dict] = {}
        self._active_marker_ids: set = set()
        self._is_initialized = False

        self._initialized: bool = False

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

        # 1. Detect pivots at this bar
        self.pivot_detector.detect_pivots(candles, bar_index)

        # 2. Run unified backward traversal (same logic every bar)
        self._sync_fans(candles, bar_index, result)

        # 2.5 Dynamically extend active fans if price action is approaching their current end
        self._extend_active_fans(candles, bar_index, result)

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

                    # --- POPULATE UI EVENT ---
                    if 'intersection_events' not in result:
                        result['intersection_events'] = []
                    
                    # Determine fraction name
                    if event.fraction is None:
                        frac_name = "Horizontal"
                    else:
                        # Simple lookup or format
                        frac_map = {0.125: '1/8', 0.25: '1/4', 0.375: '3/8', 0.5: '1/2', 0.625: '5/8', 0.75: '3/4', 0.875: '7/8', 1.0: '1/1'}
                        closest_frac = min(frac_map.keys(), key=lambda k: abs(k - event.fraction))
                        if abs(closest_frac - event.fraction) < 0.01:
                            frac_name = frac_map[closest_frac]
                        else:
                            frac_name = f"{event.fraction:.2f}"
                    fan_display_name = event.fan_id.replace("Fan_", "").replace("_", "-")
                    
                    c_open = float(current_candle.get('open', 0))
                    c_close = float(current_candle.get('close', 0))
                    c_low = float(current_candle.get('low', 0))
                    c_high = float(current_candle.get('high', 0))
                    
                    prev_close = c_open
                    if bar_index > 0:
                        prev_close = float(candles[bar_index - 1].get('close', 0))
                    
                    hit_type = 'TOUCH'
                    details = 'Angle Test'
                    
                    if c_open < event.price and c_close > event.price:
                        hit_type = 'CROSS_UP'
                        details = 'Breakout Attempt'
                    elif c_open > event.price and c_close < event.price:
                        hit_type = 'CROSS_DOWN'
                        details = 'Breakdown Attempt'
                    elif prev_close > event.price and c_low <= event.price and c_close > event.price:
                        hit_type = 'SUPPORT_TEST'
                        details = 'Resting / Throwback'
                    elif prev_close < event.price and c_high >= event.price and c_close < event.price:
                        hit_type = 'RESISTANCE_TEST'
                        details = 'Rejection / Pullback'
                    
                    ui_event = {
                        'time': event.time,
                        'fan': event.priority_label,
                        'fanIdentity': fan_display_name,
                        'fraction': frac_name,
                        'price': event.price,
                        'type': hit_type,
                        'details': details
                    }
                    result['intersection_events'].append(ui_event)
                    self.log(f"[Study] Emitting intersection event (DIRECT): {ui_event}")
                    
                    # --- LOG TO EVENT LOGGER SO IT APPEARS IN CSV ---
                    # Map the UI hit_type to the EventType enum
                    # Now we use direct mapping to aligned types for easier validation
                    event_type_map = {
                        'TOUCH': EventType.TOUCH,
                        'CROSS_UP': EventType.CROSS_UP,
                        'CROSS_DOWN': EventType.CROSS_DOWN,
                        'SUPPORT_TEST': EventType.SUPPORT_TEST,
                        'RESISTANCE_TEST': EventType.RESISTANCE_TEST
                    }
                    
                    direction = None
                    if hit_type == 'CROSS_UP':
                        direction = 'up'
                    elif hit_type == 'CROSS_DOWN':
                        direction = 'down'
                        
                    self.event_logger.log_event(
                        timestamp=event.time,
                        event_type=event_type_map.get(hit_type, EventType.TOUCH),
                        angle_name=frac_name,
                        price=event.price,
                        direction=direction,
                        details={
                            'fan_id': event.fan_id,
                            'ui_type': hit_type,
                            'ui_details': details
                        }
                    )
                    # ------------------------------------------------

                    try:
                        frac_str = str(event.fraction) if event.fraction is not None else "Horizontal"
                        log_line = f"{event.time},{event.priority_label},{frac_str},{event.price}\n"
                        with open(_intersections_csv, 'a', encoding='utf-8') as f:
                            f.write(log_line)
                    except Exception as e:
                        print(f"Failed to log intersection: {e}")


        # 4. Price movement tracking pipeline
        self._process_tracking_modules(current_candle, bar_index, events or [], result)

        # 5. Save state
        result['state'] = self._get_state()

        return result

    def _process_tracking_modules(
        self,
        current_candle: Dict[str, Any],
        bar_index: int,
        intersection_events: list,
        result: Dict[str, Any]
    ):
        """
        Run the price movement tracking pipeline:
        1. FanValidator — check for 7/8 interactions
        2. BreachAnalyzer — start/update breach tracking
        3. AngleZoneTracker — compute zone snapshots
        4. TargetProgression — advance targets on confirmed breaches
        All results feed into EventLogger for data collection.
        """
        timestamp = int(current_candle.get('time', 0))
        close_price = float(current_candle.get('close', 0))

        # 4a. Fan validation (7/8 interaction check)
        new_validations = self.fan_validator.process_intersections(
            intersection_events, current_candle, bar_index
        )
        for validation in new_validations:
            self.target_progression.activate_fan(validation.fan_id)
            self.event_logger.log_event(
                timestamp=timestamp,
                event_type=EventType.FAN_VALIDATED,
                angle_name='7/8',
                price=validation.validation_price,
                details={
                    'fan_id': validation.fan_id,
                    'validation_type': validation.validation_type,
                    'validation_bar': validation.validation_bar,
                }
            )
            self.log(f"[Tracking] Fan validated: {validation.fan_id} via {validation.validation_type} at bar {bar_index}")

            # --- ADD THIS UI EVENT PUSH ---
            if 'intersection_events' not in result:
                result['intersection_events'] = []
            fan_display = validation.fan_id.replace("Fan_", "").replace("_", "-")
            fan_obj = self.angle_engine.active_fans.get(validation.fan_id)
            priority_label = fan_obj.priority_label if fan_obj else fan_display
            result['intersection_events'].append({
                'time': timestamp,
                'fan': priority_label,
                'fanIdentity': fan_display,
                'fraction': '7/8',
                'price': validation.validation_price,
                'type': 'FAN_VALIDATED',
                'details': f"Via {validation.validation_type}"
            })
            # ------------------------------

        # 4b. Breach analysis (successive close counting)
        breach_results = self.breach_analyzer.process_bar(
            current_candle, bar_index,
            intersection_events, self.angle_engine.active_fans
        )

        for confirmation in breach_results['confirmations']:
            self.event_logger.log_event(
                timestamp=timestamp,
                event_type=EventType.BREACH_CONFIRMED,
                angle_name=confirmation.angle_name,
                price=confirmation.confirmation_price,
                direction=confirmation.breach_direction,
                details={
                    'fan_id': confirmation.fan_id,
                    'bars_elapsed': confirmation.bars_elapsed,
                    'first_breach_bar': confirmation.first_breach_bar,
                    'confirmation_bar': confirmation.confirmation_bar,
                }
            )
            self.log(f"[Tracking] Breach CONFIRMED: {confirmation.fan_id} {confirmation.angle_name} {confirmation.breach_direction} (T+{confirmation.bars_elapsed} bars)")

            # --- ADD THIS UI EVENT PUSH ---
            if 'intersection_events' not in result:
                result['intersection_events'] = []
            fan_display = confirmation.fan_id.replace("Fan_", "").replace("_", "-")
            fan_obj = self.angle_engine.active_fans.get(confirmation.fan_id)
            priority_label = fan_obj.priority_label if fan_obj else fan_display
            result['intersection_events'].append({
                'time': timestamp,
                'fan': priority_label,
                'fanIdentity': fan_display,
                'fraction': confirmation.angle_name,
                'price': confirmation.confirmation_price,
                'type': 'BREACH_CONFIRMED',
                'details': f"{confirmation.breach_direction.upper()} (T+{confirmation.bars_elapsed} bars)"
            })
            # ------------------------------

            # Advance target progression
            target_hit = self.target_progression.on_breach_confirmed(
                fan_id=confirmation.fan_id,
                angle_name=confirmation.angle_name,
                bar_index=bar_index,
                price=confirmation.confirmation_price,
            )
            if target_hit:
                self.event_logger.log_event(
                    timestamp=timestamp,
                    event_type=EventType.TARGET_HIT,
                    angle_name=target_hit.target_name,
                    price=target_hit.hit_price,
                    details={
                        'fan_id': target_hit.fan_id,
                        'hit_bar': target_hit.hit_bar,
                    }
                )
                self.log(f"[Tracking] Target HIT: {target_hit.fan_id} {target_hit.target_name}")

                # --- ADD THIS UI EVENT PUSH ---
                result['intersection_events'].append({
                    'time': timestamp,
                    'fan': priority_label,
                    'fanIdentity': fan_display,
                    'fraction': target_hit.target_name,
                    'price': target_hit.hit_price,
                    'type': 'TARGET_HIT',
                    'details': f"Target Reached"
                })
                # ------------------------------

        for fake_out in breach_results['fake_outs']:
            close_price = float(current_candle['close'])
            self.event_logger.log_event(
                timestamp=timestamp,
                event_type=EventType.FAKE_OUT,
                angle_name=fake_out.angle_name,
                price=close_price,
                direction=fake_out.attempted_direction,
                details={
                    'fan_id': fake_out.fan_id,
                    'bars_elapsed': fake_out.bars_elapsed,
                    'fake_out_bar': fake_out.reversal_bar,
                }
            )
            self.log(f"[Tracking] FAKE OUT: {fake_out.fan_id} {fake_out.angle_name} (T+{fake_out.bars_elapsed} bars)")

            # --- POPULATE UI EVENT (Fake-out) ---
            if 'intersection_events' not in result:
                result['intersection_events'] = []
            
            fan_display = fake_out.fan_id.replace("Fan_", "").replace("_", "-")
            fan_obj = self.angle_engine.active_fans.get(fake_out.fan_id)
            priority_label = fan_obj.priority_label if fan_obj else fan_display
            
            fake_out_event = {
                'time': timestamp,
                'fan': priority_label,
                'fanIdentity': fan_display,
                'fraction': fake_out.angle_name,
                'price': close_price,
                'type': 'FAKE_OUT',
                'details': f"Failed {fake_out.attempted_direction.upper()} (T+{fake_out.bars_elapsed} bars)"
            }
            result['intersection_events'].append(fake_out_event)
            # ------------------------------------

        for rest in breach_results['rest_events']:
            self.event_logger.log_event(
                timestamp=timestamp,
                event_type=EventType.REST_ON_ANGLE,
                angle_name=rest.angle_name,
                price=rest.rest_price,
                details={
                    'fan_id': rest.fan_id,
                    'bars_elapsed': rest.bars_elapsed,
                    'rest_bar': rest.rest_bar,
                }
            )

            # --- POPULATE UI EVENT (Resting) ---
            if 'intersection_events' not in result:
                result['intersection_events'] = []
            
            fan_display = rest.fan_id.replace("Fan_", "").replace("_", "-")
            fan_obj = self.angle_engine.active_fans.get(rest.fan_id)
            priority_label = fan_obj.priority_label if fan_obj else fan_display
            
            rest_event = {
                'time': timestamp,
                'fan': priority_label,
                'fanIdentity': fan_display,
                'fraction': rest.angle_name,
                'price': rest.rest_price,
                'type': 'REST_ON_ANGLE',
                'details': f"Resting (T+{rest.bars_elapsed} bars)"
            }
            result['intersection_events'].append(rest_event)
            # -----------------------------------

        # 4c. Zone tracking
        for fan_id, fan_obj in self.angle_engine.active_fans.items():
            snapshot = self.zone_tracker.compute_snapshot(
                fan_obj, current_candle, bar_index
            )
            if self.zone_tracker.has_zone_changed(fan_id, snapshot.zone):
                self.event_logger.log_event(
                    timestamp=timestamp,
                    event_type=EventType.ZONE_CHANGE,
                    price=close_price,
                    details={
                        'fan_id': fan_id,
                        'new_zone': snapshot.zone,
                        'angle_prices': snapshot.angle_prices,
                    }
                )

    def _extend_active_fans(self, candles: List[Dict[str, Any]], current_bar_index: int, result: Dict[str, Any]):
        """
        Dynamically extends fan lines if the price action is approaching the current line ends.
        Disabled: We now use TradingView's native extendRight: true to avoid time-warp bugs.
        """
        pass

    def _sync_fans(
        self,
        candles: List[Dict[str, Any]],
        current_bar_index: int,
        result: Dict[str, Any]
    ):
        """
        Core sync: run FanManager, strictly update engine state,
        remove invalidated fans, create new ones.
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
        current_valid_fan_ids = set()
        
        # Apply Priority Labels based on sorted order
        for i, fan_data in enumerate(logical_fans):
            # Cap max fans here if needed, but FanManager usually handles finding candidates
            # We enforce strict limit of active fans
            if i >= self.config.get('max_historical_fans', 3):
                break
                
            fan_id = fan_data['fan_id']
            current_valid_fan_ids.add(fan_id)
            
            fan_data['priority'] = i
            # Embed the full fan identity in the priority label so it propagates to UI controls
            fan_display_name = fan_id.replace("Fan_", "").replace("_", "-")
            fan_data['priority_label'] = f"P{i + 1} ({fan_display_name})"
            
            # Persist fan data (create or update)
            self._persisted_fans[fan_id] = fan_data

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
                self.breach_analyzer.remove_fan(fan_id)
                self.fan_validator.remove_fan(fan_id)
                self.target_progression.remove_fan(fan_id)
                
                # CRITICAL FIX: Release pivots so they can form new fans with new labels
                # This ensures that H1-L1 fan (invalidated) + new H pivot = H2-L1 fan (not H1-L1)
                if fan_id in self._persisted_fans:
                    fan_data = self._persisted_fans[fan_id]
                    if 'anchor' in fan_data:
                        anchor_time = fan_data['anchor'].get('time')
                        anchor_type = fan_data['anchor'].get('type')
                        if anchor_time and anchor_type:
                            self.pivot_detector.release_pivot(anchor_time, anchor_type)
                    if 'target' in fan_data:
                        target_time = fan_data['target'].get('time')
                        target_type = fan_data['target'].get('type')
                        if target_time and target_type:
                            self.pivot_detector.release_pivot(target_time, target_type)
                
                # Remove from persistence
                del self._persisted_fans[fan_id]

        # --- SYNC: Create or Update Valid Fans ---
        for fan_id in current_valid_fan_ids:
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
                
                # Store mapping
                self._active_fan_keys[fan_id] = fan_obj.id
                
                # Register with tracking
                self.fan_validator.register_fan(fan_obj.id)
                self.target_progression.register_fan(
                    fan_id=fan_obj.id,
                    horizontal_target_price=self._get_horizontal_target_price(fan_obj),
                    full_coverage_target_price=float(fan_data['target'].get('price', 0)),
                )
                
                # Generate drawings
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
            a_key = f"anchor_{a['time']}"
            if a_key not in seen:
                seen.add(a_key)
                current_marker_ids.add(a_key)
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
                current_marker_ids.add(t_key)
                result['pivot_markers'].append({
                    'id': t_key,
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

    def _get_horizontal_target_price(self, fan_obj) -> Optional[float]:
        """
        Extract the horizontal target price from a fan's lines.
        The horizontal target line has fraction=None.
        """
        for line in fan_obj.lines:
            if line.fraction is None and 'horizontal' in line.id.lower():
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
            'breach_analyzer': self.breach_analyzer.get_state(),
            'fan_validator': self.fan_validator.get_state(),
            'target_progression': self.target_progression.get_state(),
            'event_logger': {
                'events': [e.to_dict() for e in self.event_logger.events],
                'indicator_snapshots': self.event_logger.indicator_snapshots
            },
            'active_fan_keys': dict(self._active_fan_keys),
            'persisted_fans': dict(self._persisted_fans),
            'active_marker_ids': list(self._active_marker_ids),
            'is_initialized': self._is_initialized,
            'initialized': self._initialized,
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
        if 'zone_tracker' in state:
            self.zone_tracker.restore_state(state['zone_tracker'])
        if 'breach_analyzer' in state:
            self.breach_analyzer.restore_state(state['breach_analyzer'])
        if 'fan_validator' in state:
            self.fan_validator.restore_state(state['fan_validator'])
        if 'target_progression' in state:
            self.target_progression.restore_state(state['target_progression'])
        if 'event_logger' in state:
            # Restore event logger state
            logger_state = state['event_logger']
            self.event_logger.events = []
            for evt_dict in logger_state.get('events', []):
                # Reconstruct Event object
                # Convert string event_type back to Enum
                try:
                    evt_type = EventType(evt_dict['event_type'])
                    
                    # Import Event explicitly here if needed or rely on module scope
                    # Assuming Event is available in module scope or from event_logger import
                    from .event_logger import Event
                    
                    self.event_logger.events.append(Event(
                        timestamp=evt_dict['timestamp'],
                        event_type=evt_type,
                        angle_name=evt_dict.get('angle_name'),
                        price=evt_dict.get('price'),
                        direction=evt_dict.get('direction'),
                        details=evt_dict.get('details')
                    ))
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


# Factory function
def create_study(config: Optional[Dict[str, Any]] = None) -> AngularPriceCoverageStudy:
    return AngularPriceCoverageStudy(config)
