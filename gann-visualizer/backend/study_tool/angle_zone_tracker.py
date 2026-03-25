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
    zone: str                     # e.g. "below_7_8", "between_7_8_and_3_4", "above_1_4"
    nearest_angle_above: Optional[str]   # fraction label of nearest angle above, e.g. "7/8"
    nearest_angle_below: Optional[str]   # fraction label of nearest angle below, e.g. None
    distance_to_above: Optional[float]   # price distance to nearest angle above
    distance_to_below: Optional[float]   # price distance to nearest angle below
    angle_prices: Dict[str, float]       # all angle line prices at this bar: {"7/8": 100.5, ...}

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
    if frac in FRACTION_LABELS:
        return FRACTION_LABELS[frac]
    return f"{frac:.3f}"


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
    
    Zones are defined by the ordered angle division lines. For a fan radiating
    downward from a high (bearish context), the zones from top to bottom are:
        above_7_8 → between_7_8_and_3_4 → between_3_4_and_1_2 → 
        between_1_2_and_1_4 → below_1_4
    
    For a fan radiating upward from a low (bullish context), the zones are
    the mirror: below_7_8 is the starting zone.
    """

    def __init__(self):
        # Per-fan zone history: fan_id -> last ZoneSnapshot
        self._last_zones: Dict[str, ZoneSnapshot] = {}
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
        close_price = float(current_candle.get('close', 0))
        timestamp = int(current_candle.get('time', 0))

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
        )

        # Check zone change BEFORE updating _last_zones
        previous = self._last_zones.get(fan.id)
        self._zone_changed = (previous is None or previous.zone != zone)

        # Track zone — update last known zone
        self._last_zones[fan.id] = snapshot
        return snapshot

    def _determine_zone(
        self,
        price: float,
        sorted_levels: List[tuple]
    ) -> str:
        """
        Determine which zone the price is in, given sorted (label, price) levels.
        
        The sorted_levels are in ascending price order.
        Zone naming: "below_{lowest}", "between_{a}_and_{b}", "above_{highest}"
        """
        if not sorted_levels:
            return "unknown"

        # Check if below all
        if price < sorted_levels[0][1]:
            return f"below_{sorted_levels[0][0]}"

        # Check if above all
        if price > sorted_levels[-1][1]:
            return f"above_{sorted_levels[-1][0]}"

        # Find which pair the price is between
        for i in range(len(sorted_levels) - 1):
            lower_label, lower_price = sorted_levels[i]
            upper_label, upper_price = sorted_levels[i + 1]
            if lower_price <= price <= upper_price:
                return f"between_{lower_label}_and_{upper_label}"

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

    def remove_fan(self, fan_id: str):
        """Clean up tracking when a fan is removed."""
        self._last_zones.pop(fan_id, None)

    def reset(self):
        """Clear all tracking state."""
        self._last_zones.clear()

    def get_state(self) -> Dict[str, Any]:
        """Serialize state for replay persistence."""
        return {
            'last_zones': {
                fid: snap.to_dict() for fid, snap in self._last_zones.items()
            }
        }

    def restore_state(self, state: Dict[str, Any]):
        """Restore state from serialized form."""
        self._last_zones.clear()
        if 'last_zones' in state:
            for fid, snap_dict in state['last_zones'].items():
                self._last_zones[fid] = ZoneSnapshot(**snap_dict)
