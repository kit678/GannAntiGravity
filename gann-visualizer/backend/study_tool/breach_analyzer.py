"""
Breach Analyzer (State Machine Approach)

Detects and confirms breaches of angle lines and horizontal targets using
market structure logic (Higher Highs / Lower Lows) rather than strict
consecutive candle counting.

Breach direction is FIXED by the fan's anchor type:
- Low-anchored fan -> breach direction is "up" (price overcoming resistance)
- High-anchored fan -> breach direction is "down" (price breaking support)

State Machine Logic per intersection:
1. IDLE -> TRACKING_BREACH (Trigger: Close crosses line in expected direction)
2. TRACKING_BREACH -> CONFIRMED (Trigger: Close breaks previous extreme)
3. TRACKING_BREACH -> TRACKING_REVERSAL (Trigger: Close crosses back across line)
4. TRACKING_REVERSAL -> REVERSAL_CONFIRMED (Trigger: Close breaks opposite extreme)
5. TRACKING_REVERSAL -> TRACKING_BREACH (Trigger: Close crosses back to breach side)
"""

from dataclasses import dataclass, asdict, field
from typing import Dict, List, Any, Optional
from enum import Enum


# ─── Data Models ─────────────────────────────────────────────────────────────

@dataclass
class BreachConfirmation:
    """Emitted when a breach is confirmed via market structure (new extreme)."""
    fan_id: str
    angle_name: str
    breach_direction: str     # "up" or "down"
    first_breach_bar: int
    confirmation_bar: int
    bars_elapsed: int         # New metric: time delta for ML
    breach_price: float
    confirmation_price: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AngleReversal:
    """Emitted when a reversal is confirmed (failed breach leads to opposite extreme)."""
    fan_id: str
    angle_name: str
    attempted_direction: str  # The direction of the failed breach
    reversal_bar: int
    bars_elapsed: int         # Time spent tracking before reversal confirmed
    reversal_price: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RestEvent:
    """Emitted when price rests near the angle without confirming breach or reversal."""
    fan_id: str
    angle_name: str
    rest_bar: int
    rest_price: float
    bars_elapsed: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BreachState(Enum):
    """State of a pending interaction for a particular angle line."""
    TRACKING_BREACH = "tracking_breach"
    TRACKING_REVERSAL = "tracking_reversal"
    CONFIRMED = "confirmed"
    REVERSAL_CONFIRMED = "reversal_confirmed"


@dataclass
class _InteractionTracker:
    """Internal State Machine tracker for an interaction."""
    fan_id: str
    angle_name: str
    expected_direction: str     # "up" or "down" (fixed by fan geometry)
    start_bar: int
    start_price: float
    
    # State
    state: BreachState
    
    # Anchors for market structure checks
    extreme_breach_close: float = 0.0   # Highest high close (up) or lowest low close (down)
    extreme_reversal_close: float = 0.0 # Lowest close (up-breach failed) or highest close (down-breach failed)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['state'] = self.state.value
        return d


# ─── Configuration ───────────────────────────────────────────────────────────

DEFAULT_BREACH_CONFIG = {
    'rest_tolerance_percent': 0.15,    # how close to angle counts as "resting" (%)
}


# ─── Fraction label helpers ──────────────────────────────────────────────────

FRACTION_LABELS = {
    0.125: '1/8', 0.25: '1/4', 0.375: '3/8',
    0.5: '1/2', 0.625: '5/8', 0.75: '3/4',
    0.875: '7/8', 1.0: '1/1',
}

def _fraction_to_label(frac: Optional[float]) -> str:
    if frac is None:
        return "horizontal"
    if frac in FRACTION_LABELS:
        return FRACTION_LABELS[frac]
    closest = min(FRACTION_LABELS.keys(), key=lambda k: abs(k - frac))
    if abs(closest - frac) < 0.01:
        return FRACTION_LABELS[closest]
    return f"{frac:.3f}"

def _line_price_at_bar(line, bar_idx: int) -> Optional[float]:
    bar_span = line.end_bar_index - line.start_bar_index
    if abs(bar_span) < 0.001:
        return None
    slope = (line.end_price - line.start_price) / bar_span
    return line.start_price + (bar_idx - line.start_bar_index) * slope

def _get_breach_direction(fan) -> Optional[str]:
    anchor_type = getattr(fan, 'anchor_type', None)
    if anchor_type == 'low':
        return 'up'
    elif anchor_type == 'high':
        return 'down'
    to_pivot = getattr(fan, 'to_pivot', None)
    if to_pivot and isinstance(to_pivot, dict):
        ptype = to_pivot.get('type', '')
        if ptype == 'low': return 'up'
        elif ptype == 'high': return 'down'
    return None


# ─── Main Class ──────────────────────────────────────────────────────────────

class BreachAnalyzer:
    """
    Analyzes price interactions using a State Machine based on market structure.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = {**DEFAULT_BREACH_CONFIG, **(config or {})}
        
        # Trackers: key = "{fan_id}_{angle_name}" -> _InteractionTracker
        self._trackers: Dict[str, _InteractionTracker] = {}
        
        # Confirmed history (used by other modules like target progression)
        self._confirmed_breaches: Dict[str, BreachConfirmation] = {}
        
        # Append-only history lists for serialization/export
        self._history_confirmations: List[BreachConfirmation] = []
        self._history_reversals: List[AngleReversal] = []
        self._history_rests: List[RestEvent] = []

    def process_bar(
        self,
        current_candle: Dict[str, Any],
        current_bar_idx: int,
        intersection_events: List[Any],
        active_fans: Dict[str, Any]
    ) -> Dict[str, List]:
        """Process one bar, returning newly emitted events."""
        results = {'confirmations': [], 'reversals': [], 'rest_events': []}
        close_price = float(current_candle.get('close', 0))
        
        # DEBUG: Print active trackers
        if self._trackers:
            print(f"[BreachAnalyzer] Bar {current_bar_idx} | Active Trackers: {len(self._trackers)} | Close: {close_price}")
        
        # 1. Start new trackers from intersections
        for event in intersection_events:
            angle_label = _fraction_to_label(event.fraction)
            tracker_key = f"{event.fan_id}_{angle_label}"
            
            # Skip if already tracking or already confirmed breached
            if tracker_key in self._trackers or tracker_key in self._confirmed_breaches:
                continue
            
            fan = active_fans.get(event.fan_id)
            if not fan: continue
            direction = _get_breach_direction(fan)
            if not direction: continue
            
            # Get current angle price to determine initial state
            angle_price = self._get_angle_price_at_bar(event.fan_id, angle_label, current_bar_idx, active_fans)
            if angle_price is None: angle_price = event.price
            
            # Did it close on the breach side or reversal side?
            is_breached_side = (direction == 'up' and close_price > angle_price) or \
                               (direction == 'down' and close_price < angle_price)
            
            initial_state = BreachState.TRACKING_BREACH if is_breached_side else BreachState.TRACKING_REVERSAL
            
            self._trackers[tracker_key] = _InteractionTracker(
                fan_id=event.fan_id,
                angle_name=angle_label,
                expected_direction=direction,
                start_bar=current_bar_idx,
                start_price=angle_price,
                state=initial_state,
                extreme_breach_close=close_price if is_breached_side else (0.0 if direction == 'up' else float('inf')),
                extreme_reversal_close=close_price if not is_breached_side else (float('inf') if direction == 'up' else 0.0)
            )

        # 2. Update existing trackers state machine
        keys_to_remove = []
        for key, tracker in self._trackers.items():
            if current_bar_idx == tracker.start_bar:
                continue # Skip the bar that triggered it

            angle_price = self._get_angle_price_at_bar(tracker.fan_id, tracker.angle_name, current_bar_idx, active_fans)
            if angle_price is None:
                continue

            # Determine where the close is relative to the line
            is_above_line = close_price > angle_price
            
            # State: TRACKING_BREACH
            if tracker.state == BreachState.TRACKING_BREACH:
                if tracker.expected_direction == 'up':
                    if close_price > tracker.extreme_breach_close:
                        # CONFIRMED! Made a higher close
                        conf = self._emit_breach(tracker, current_bar_idx, close_price, angle_price)
                        results['confirmations'].append(conf)
                        keys_to_remove.append(key)
                    elif not is_above_line:
                        # Dropped below line - switch to reversal tracking
                        tracker.state = BreachState.TRACKING_REVERSAL
                        tracker.extreme_reversal_close = close_price
                    else:
                        # Resting / Consolidating above line
                        self._check_rest(tracker, current_bar_idx, close_price, angle_price, results)
                        
                elif tracker.expected_direction == 'down':
                    if close_price < tracker.extreme_breach_close:
                        # CONFIRMED! Made a lower close
                        conf = self._emit_breach(tracker, current_bar_idx, close_price, angle_price)
                        results['confirmations'].append(conf)
                        keys_to_remove.append(key)
                    elif is_above_line:
                        # Popped above line - switch to reversal tracking
                        tracker.state = BreachState.TRACKING_REVERSAL
                        tracker.extreme_reversal_close = close_price
                    else:
                        self._check_rest(tracker, current_bar_idx, close_price, angle_price, results)

            # State: TRACKING_REVERSAL
            elif tracker.state == BreachState.TRACKING_REVERSAL:
                if tracker.expected_direction == 'up':
                    # Waiting for lower close below the line
                    if close_price < tracker.extreme_reversal_close:
                        # REVERSAL CONFIRMED!
                        rev = self._emit_reversal(tracker, current_bar_idx, close_price)
                        results['reversals'].append(rev)
                        keys_to_remove.append(key)
                    elif is_above_line:
                        # Popped back above line - switch to breach tracking
                        tracker.state = BreachState.TRACKING_BREACH
                        tracker.extreme_breach_close = close_price
                    else:
                        self._check_rest(tracker, current_bar_idx, close_price, angle_price, results)
                        
                elif tracker.expected_direction == 'down':
                    if close_price > tracker.extreme_reversal_close:
                        # REVERSAL CONFIRMED!
                        rev = self._emit_reversal(tracker, current_bar_idx, close_price)
                        results['reversals'].append(rev)
                        keys_to_remove.append(key)
                    elif not is_above_line:
                        # Dropped back below line
                        tracker.state = BreachState.TRACKING_BREACH
                        tracker.extreme_breach_close = close_price
                    else:
                        self._check_rest(tracker, current_bar_idx, close_price, angle_price, results)

        # Cleanup completed trackers
        for k in keys_to_remove:
            self._trackers.pop(k, None)

        # DEBUG: Log emitted events
        if results['confirmations']:
            print(f"[BreachAnalyzer] >>> BREACH CONFIRMED: {[(c.fan_id, c.angle_name, c.bars_elapsed) for c in results['confirmations']]}")
        if results['reversals']:
            print(f"[BreachAnalyzer] >>> ANGLE REVERSAL: {[(r.fan_id, r.angle_name, r.bars_elapsed) for r in results['reversals']]}")
        if results['rest_events']:
            print(f"[BreachAnalyzer] >>> REST ON ANGLE: {[(r.fan_id, r.angle_name, r.bars_elapsed) for r in results['rest_events']]}")

        return results

    def _emit_breach(self, tracker: _InteractionTracker, bar_idx: int, close_price: float, angle_price: float) -> BreachConfirmation:
        conf = BreachConfirmation(
            fan_id=tracker.fan_id,
            angle_name=tracker.angle_name,
            breach_direction=tracker.expected_direction,
            first_breach_bar=tracker.start_bar,
            confirmation_bar=bar_idx,
            bars_elapsed=bar_idx - tracker.start_bar,
            breach_price=tracker.start_price,
            confirmation_price=close_price
        )
        self._history_confirmations.append(conf)
        self._confirmed_breaches[f"{tracker.fan_id}_{tracker.angle_name}"] = conf
        return conf

    def _emit_reversal(self, tracker: _InteractionTracker, bar_idx: int, close_price: float) -> AngleReversal:
        rev = AngleReversal(
            fan_id=tracker.fan_id,
            angle_name=tracker.angle_name,
            attempted_direction=tracker.expected_direction,
            reversal_bar=bar_idx,
            bars_elapsed=bar_idx - tracker.start_bar,
            reversal_price=close_price
        )
        self._history_reversals.append(rev)
        return rev

    def _check_rest(self, tracker: _InteractionTracker, bar_idx: int, close_price: float, angle_price: float, results: dict):
        tolerance = angle_price * (self.config['rest_tolerance_percent'] / 100.0)
        if abs(close_price - angle_price) <= tolerance:
            rest = RestEvent(
                fan_id=tracker.fan_id,
                angle_name=tracker.angle_name,
                rest_bar=bar_idx,
                rest_price=close_price,
                bars_elapsed=bar_idx - tracker.start_bar
            )
            self._history_rests.append(rest)
            results['rest_events'].append(rest)

    def _get_angle_price_at_bar(self, fan_id: str, angle_name: str, bar_idx: int, active_fans: Dict[str, Any]) -> Optional[float]:
        fan = active_fans.get(fan_id)
        if not fan: return None
        for line in fan.lines:
            if _fraction_to_label(line.fraction) == angle_name:
                return _line_price_at_bar(line, bar_idx)
        return None

    def is_angle_breached(self, fan_id: str, angle_name: str) -> bool:
        return f"{fan_id}_{angle_name}" in self._confirmed_breaches

    def get_breach_confirmation(self, fan_id: str, angle_name: str) -> Optional[BreachConfirmation]:
        return self._confirmed_breaches.get(f"{fan_id}_{angle_name}")

    def remove_fan(self, fan_id: str):
        keys = [k for k in self._trackers if k.startswith(f"{fan_id}_")]
        for k in keys: del self._trackers[k]
        keys = [k for k in self._confirmed_breaches if k.startswith(f"{fan_id}_")]
        for k in keys: del self._confirmed_breaches[k]

    def get_state(self) -> Dict[str, Any]:
        return {
            'trackers': {k: v.to_dict() for k, v in self._trackers.items()},
            'confirmed_breaches': {k: v.to_dict() for k, v in self._confirmed_breaches.items()},
            'history_confirmations': [c.to_dict() for c in self._history_confirmations],
            'history_reversals': [r.to_dict() for r in self._history_reversals],
            'history_rests': [r.to_dict() for r in self._history_rests],
        }

    def restore_state(self, state: Dict[str, Any]):
        self._trackers.clear()
        self._confirmed_breaches.clear()
        self._history_confirmations.clear()
        self._history_reversals.clear()
        self._history_rests.clear()

        if 'trackers' in state:
            for k, v in state['trackers'].items():
                v['state'] = BreachState(v['state'])
                self._trackers[k] = _InteractionTracker(**v)
        if 'confirmed_breaches' in state:
            for k, v in state['confirmed_breaches'].items():
                self._confirmed_breaches[k] = BreachConfirmation(**v)
        if 'history_confirmations' in state:
            self._history_confirmations = [BreachConfirmation(**c) for c in state['history_confirmations']]
        if 'history_reversals' in state:
            self._history_reversals = [AngleReversal(**r) for r in state['history_reversals']]
        if 'history_rests' in state:
            self._history_rests = [RestEvent(**r) for r in state['history_rests']]
