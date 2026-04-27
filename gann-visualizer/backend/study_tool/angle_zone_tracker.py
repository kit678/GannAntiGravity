"""
Angle Zone Tracker

For each active fan, tracks which "zone" the price is currently in —
i.e., which two adjacent angle lines the price sits between.

Emits ZoneSnapshot objects each bar for data collection during replay.
"""

from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional


@dataclass
class ZoneSnapshot:
    """Snapshot of price position relative to a fan's angle divisions at one bar."""
    fan_id: str
    bar_index: int
    timestamp: int
    current_price: float          # close price of the candle
    zone: str                     # e.g. "7/8_zone", "7/8-3/4", "3/4_zone"
    nearest_angle_above: Optional[str]   # fraction label of nearest angle above, e.g. "7/8"
    nearest_angle_below: Optional[str]   # fraction label of nearest angle below, e.g. None
    distance_to_above: Optional[float]   # price distance to nearest angle above
    distance_to_below: Optional[float]   # price distance to nearest angle below
    angle_prices: Dict[str, float]       # all angle line prices at this bar: {"7/8": 100.5, ...}
    zone_highest_close: Optional[float] = None  # maximum close while in this zone
    zone_lowest_close: Optional[float] = None   # minimum close while in this zone
    bars_in_zone: int = 0                # how many bars spent in this zone

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Human-readable labels for fraction values
FRACTION_LABELS = {
    0.25:  '1/4',
    0.375: '3/8',
    0.5:   '1/2',
    0.625: '5/8',
    0.75:  '3/4',
    0.875: '7/8',
    1.0:   '1/1',
}

# The key fractions we track for zone determination (ascending order)
# Price moves through these from one end to the other
TRACKED_FRACTIONS = [0.875, 0.75, 0.5, 0.25]  # 7/8, 3/4, 1/2, 1/4


def _fraction_label(frac: float) -> str:
    """Convert a fraction float to its human-readable label."""
    frac_float = float(frac)
    if frac_float in FRACTION_LABELS:
        return FRACTION_LABELS[frac_float]
    return f"{frac_float:.3f}"


def _line_price_at_bar(line, current_bar_idx: int) -> Optional[float]:
    """
    Extrapolate a line's price at the given bar index using slope.
    Mirrors the logic in IntersectionDetector.
    """
    bar_span = line.end_bar_index - line.start_bar_index
    if abs(bar_span) < 0.001:
        return None
    slope_per_bar = (line.end_price - line.start_price) / bar_span
    bars_from_origin = current_bar_idx - line.start_bar_index
    return line.start_price + bars_from_origin * slope_per_bar


class AngleZoneTracker:
    """
    Tracks which zone the price sits in relative to each fan's angle divisions.

    Zones are defined by the ordered angle division lines. Simplified naming:
        "7/8_zone" → "7/8-3/4" → "3/4-1/2" → "1/2-1/4" → "1/4_zone"

    Zone extremes track the highest and lowest CLOSE prices within each zone,
    not the wick extremes.
    """

    def __init__(self):
        # Per-fan zone history: fan_id -> last ZoneSnapshot
        self._last_zones: Dict[str, ZoneSnapshot] = {}
        # Per-fan structural extremes for the current zone
        self._zone_extremes: Dict[str, Dict[str, float]] = {}
        # Per-fan PRIOR zone extremes — saved before reset at zone change, used for ZEC capture
        self._prior_zone_extremes: Dict[str, Dict[str, float]] = {}
        # Per-fan entry bar index for calculating velocity
        self._zone_entry_bars: Dict[str, int] = {}
        self._zone_changed: bool = False

    def compute_snapshot(
        self,
        fan,   # AngleFan object
        current_candle: Dict[str, Any],
        current_bar_idx: int
    ) -> ZoneSnapshot:
        """
        Compute a ZoneSnapshot for the given fan at the current bar.
        
        Args:
            fan: AngleFan object with .lines, .id, etc.
            current_candle: Current OHLC candle dict
            current_bar_idx: Current bar index
            
        Returns:
            ZoneSnapshot describing price position relative to angles
        """
        close_price = float(current_candle.get('close', current_candle.get('Close', 0)))
        timestamp = int(current_candle.get('time', current_candle.get('Time', 0)))

        # Compute all angle line prices at this bar
        angle_prices: Dict[str, float] = {}
        for line in fan.lines:
            if line.fraction is None:
                continue  # skip main angle line / horizontal for zone calc
            price_at_bar = _line_price_at_bar(line, current_bar_idx)
            if price_at_bar is not None:
                label = _fraction_label(line.fraction)
                angle_prices[label] = price_at_bar

        # Sort tracked fraction prices for zone determination
        # We need them in a consistent order: determine whether angles go
        # up or down from the origin pivot
        sorted_levels = []
        for frac in TRACKED_FRACTIONS:
            label = _fraction_label(frac)
            if label in angle_prices:
                sorted_levels.append((label, angle_prices[label]))

        # Sort by price (ascending)
        sorted_levels.sort(key=lambda x: x[1])

        # Determine zone
        zone = self._determine_zone(close_price, sorted_levels)

        # Find nearest angle above and below
        nearest_above = None
        nearest_below = None
        dist_above = None
        dist_below = None

        for label, price in sorted_levels:
            if price >= close_price:
                if nearest_above is None or price < angle_prices.get(nearest_above, float('inf')):
                    nearest_above = label
                    dist_above = price - close_price
            if price <= close_price:
                if nearest_below is None or price > angle_prices.get(nearest_below, float('-inf')):
                    nearest_below = label
                    dist_below = close_price - price

        # Check zone change BEFORE updating _last_zones
        previous = self._last_zones.get(fan.id)
        self._zone_changed = (previous is None or previous.zone != zone)

        # Track close price extremes (not wick extremes)
        candle_high = float(current_candle.get('High', current_candle.get('high', close_price)))
        candle_low = float(current_candle.get('Low', current_candle.get('low', close_price)))
        candle_close = close_price

        # Calculate bars spent in the current zone (including current bar)
        bars_spent = 0
        if fan.id in self._zone_entry_bars:
            bars_spent = current_bar_idx - self._zone_entry_bars[fan.id] + 1

        if self._zone_changed or fan.id not in self._zone_extremes:
            # SAVE prior zone extremes BEFORE reset — needed for ZEC capture at zone change
            if fan.id in self._zone_extremes:
                self._prior_zone_extremes[fan.id] = dict(self._zone_extremes[fan.id])
            # Reset extremes for new zone
            self._zone_extremes[fan.id] = {'highest_close': candle_close, 'lowest_close': candle_close}
            self._zone_entry_bars[fan.id] = current_bar_idx
            bars_spent = 1  # First bar in zone counts as 1
        else:
            # Update extremes for current zone using CLOSE prices
            self._zone_extremes[fan.id]['highest_close'] = max(self._zone_extremes[fan.id]['highest_close'], candle_close)
            self._zone_extremes[fan.id]['lowest_close'] = min(self._zone_extremes[fan.id]['lowest_close'], candle_close)
            bars_spent = current_bar_idx - self._zone_entry_bars[fan.id] + 1

        snapshot = ZoneSnapshot(
            fan_id=fan.id,
            bar_index=current_bar_idx,
            timestamp=timestamp,
            current_price=close_price,
            zone=zone,
            nearest_angle_above=nearest_above,
            nearest_angle_below=nearest_below,
            distance_to_above=dist_above,
            distance_to_below=dist_below,
            angle_prices=angle_prices,
            zone_highest_close=self._zone_extremes[fan.id]['highest_close'],
            zone_lowest_close=self._zone_extremes[fan.id]['lowest_close'],
            bars_in_zone=bars_spent
        )

        # Track zone — update last known zone
        self._last_zones[fan.id] = snapshot
        
        if not hasattr(self, '_historical_zones'):
            self._historical_zones = {}
        if fan.id not in self._historical_zones:
            self._historical_zones[fan.id] = {}
        self._historical_zones[fan.id][current_bar_idx] = snapshot
        
        return snapshot

    def _determine_zone(
        self,
        price: float,
        sorted_levels: List[tuple]
    ) -> str:
        """
        Determine which zone the price is in, given sorted (label, price) levels.

        The sorted_levels are in ascending price order.
        Zone naming simplified:
        - Below lowest angle: "{label}_zone" (e.g., "7/8_zone")
        - Between two angles: "{lower}-{upper}" (e.g., "7/8-3/4")
        - Above highest angle: "{label}_zone" (e.g., "1/4_zone")
        """
        if not sorted_levels:
            return "unknown"

        # Below lowest angle
        if price < sorted_levels[0][1]:
            return f"{sorted_levels[0][0]}_zone"

        # Above highest angle
        if price > sorted_levels[-1][1]:
            return f"{sorted_levels[-1][0]}_zone"

        # Find which pair the price is between
        for i in range(len(sorted_levels) - 1):
            lower_label, lower_price = sorted_levels[i]
            upper_label, upper_price = sorted_levels[i + 1]
            if lower_price <= price <= upper_price:
                return f"{lower_label}-{upper_label}"

        return "unknown"

    def has_zone_changed(self, fan_id: str, new_zone: str) -> bool:
        """
        Check if the zone has changed for a fan.
        
        IMPORTANT: Call this AFTER compute_snapshot() — it uses the
        comparison result computed during that call. The new_zone argument
        is kept for backwards compatibility but the internal flag is
        authoritative.
        """
        return self._zone_changed

    def get_last_zone(self, fan_id: str) -> Optional[ZoneSnapshot]:
        """Get the last computed zone snapshot for a fan."""
        return self._last_zones.get(fan_id)

    def get_zone_at_bar(self, fan_id: str, bar_index: int) -> Optional[ZoneSnapshot]:
        """Get the zone snapshot for a specific historical bar."""
        if hasattr(self, '_historical_zones') and fan_id in self._historical_zones:
            return self._historical_zones[fan_id].get(bar_index)
        return None

    def remove_fan(self, fan_id: str):
        """Clean up tracking when a fan is removed."""
        self._last_zones.pop(fan_id, None)
        self._zone_extremes.pop(fan_id, None)
        self._zone_entry_bars.pop(fan_id, None)
        if hasattr(self, '_historical_zones'):
            self._historical_zones.pop(fan_id, None)

    def reset(self):
        """Clear all tracking state."""
        self._last_zones.clear()
        self._zone_extremes.clear()
        self._zone_entry_bars.clear()

    def get_state(self) -> Dict[str, Any]:
        """Serialize state for replay persistence."""
        return {
            'last_zones': {
                fid: snap.to_dict() for fid, snap in self._last_zones.items()
            },
            'zone_extremes': self._zone_extremes,
            'zone_entry_bars': self._zone_entry_bars,
            'historical_zones': {
                fid: {str(k): v.to_dict() for k, v in history.items()}
                for fid, history in getattr(self, '_historical_zones', {}).items()
            }
        }

    def restore_state(self, state: Dict[str, Any]):
        """Restore state from persistence."""
        self._last_zones.clear()
        for fid, snap_dict in state.get('last_zones', {}).items():
            self._last_zones[fid] = ZoneSnapshot(**snap_dict)
            
        self._zone_extremes = state.get('zone_extremes', {})
        self._zone_entry_bars = state.get('zone_entry_bars', {})
        
        self._historical_zones = {}
        for fid, history_dict in state.get('historical_zones', {}).items():
            self._historical_zones[fid] = {
                int(k): ZoneSnapshot(**v) for k, v in history_dict.items()
            }
