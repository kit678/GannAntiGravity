"""
Fan Validator

Determines whether a fan is "trading-valid" based on the 7/8 angle
interaction rule.

Key Rule: A fan is only valid for trading decisions AFTER price interacts
with its 7/8 angle line. Before that, the fan is drawn but no trading
signals should be generated from it.

The 7/8 interaction is the first confirmation that price respects this
particular fan's geometry.
"""

from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional


FRACTION_LABELS = {
    0.25: '1/4',
    0.5: '1/2', 0.75: '3/4',
    0.875: '7/8', 1.0: '1/1',
}


@dataclass
class FanValidation:
    """Records the validation event for a fan."""
    fan_id: str
    validated: bool
    validation_bar: int           # bar where 7/8 was first interacted with
    validation_type: str          # "reversal", "breach", "touch"
    validation_price: float       # price at which interaction occurred

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _fraction_to_label(frac: Any) -> str:
    if frac is None:
        return "horizontal"
    if isinstance(frac, str):
        try:
            frac = float(frac)
        except ValueError:
            return frac
            
    if frac in FRACTION_LABELS:
        return FRACTION_LABELS[frac]
    closest = min(FRACTION_LABELS.keys(), key=lambda k: abs(k - frac))
    if abs(closest - frac) < 0.01:
        return FRACTION_LABELS[closest]
    return f"{frac:.3f}"


class FanValidator:
    """
    Validates fans for trading based on 7/8 angle interaction.
    
    A fan starts as unvalidated when first drawn. It becomes validated
    when price first interacts with the 7/8 angle line. The type of
    interaction (reversal, breach, touch) is also recorded as the first
    data point about the fan's reliability.
    """

    def __init__(self):
        # fan_id -> FanValidation (only for validated fans)
        self._validations: Dict[str, FanValidation] = {}
        # fan_id -> True (tracking set for unvalidated fans)
        self._tracked_fans: set = set()

    def register_fan(self, fan_id: str):
        """
        Register a new fan for validation tracking.
        Called when a new fan is created by the orchestrator.
        """
        if fan_id not in self._validations:
            self._tracked_fans.add(fan_id)

    def process_intersections(
        self,
        intersection_events: List[Any],
        current_candle: Dict[str, Any],
        current_bar_idx: int
    ) -> List[FanValidation]:
        """
        Check intersection events for 7/8 angle interactions.
        
        Args:
            intersection_events: Events from IntersectionDetector
            current_candle: Current OHLC candle
            current_bar_idx: Current bar index
            
        Returns:
            List of new FanValidation events (for fans just validated)
        """
        new_validations = []

        for event in intersection_events:
            # Only look for 7/8 fraction interactions
            angle_label = _fraction_to_label(event.fraction)
            if angle_label != '7/8':
                continue

            fan_id = event.fan_id

            # Skip if already validated or not being tracked
            if fan_id in self._validations:
                continue
            if fan_id not in self._tracked_fans:
                continue

            # Classify the type of interaction
            interaction_type = self._classify_interaction(
                current_candle, event.price
            )

            validation = FanValidation(
                fan_id=fan_id,
                validated=True,
                validation_bar=current_bar_idx,
                validation_type=interaction_type,
                validation_price=event.price,
            )

            self._validations[fan_id] = validation
            self._tracked_fans.discard(fan_id)
            new_validations.append(validation)

        return new_validations

    def _classify_interaction(
        self,
        candle: Dict[str, Any],
        line_price: float
    ) -> str:
        """
        Classify the type of 7/8 interaction based on candle shape.
        
        - "reversal": candle body is mostly on one side, wick touches the line
          (long wick rejection)
        - "breach": candle close is on the opposite side of the line from open
        - "touch": candle high/low touches the line but body doesn't cross
        """
        open_price = float(candle.get('open', 0))
        close_price = float(candle.get('close', 0))
        high_price = float(candle.get('high', 0))
        low_price = float(candle.get('low', 0))

        body_top = max(open_price, close_price)
        body_bottom = min(open_price, close_price)

        # Did the body cross the line?
        body_crossed = body_bottom < line_price < body_top

        if body_crossed:
            # Close is on the opposite side from where price approached
            return "breach"

        # Did only the wick touch the line?
        wick_touched = (low_price <= line_price <= high_price)
        if wick_touched and not body_crossed:
            # Check wick length vs body length for reversal classification
            body_len = body_top - body_bottom
            if line_price > body_top:
                wick_len = high_price - body_top
            else:
                wick_len = body_bottom - low_price
            
            if body_len > 0 and wick_len / body_len > 0.5:
                return "reversal"
            return "touch"

        return "touch"

    def is_validated(self, fan_id: str) -> bool:
        """Check if a fan has been validated for trading."""
        return fan_id in self._validations

    def get_validation(self, fan_id: str) -> Optional[FanValidation]:
        """Get the validation record for a fan."""
        return self._validations.get(fan_id)

    def get_all_validations(self) -> List[FanValidation]:
        """Get all fan validations."""
        return list(self._validations.values())

    def remove_fan(self, fan_id: str):
        """Clean up tracking when a fan is removed."""
        self._validations.pop(fan_id, None)
        self._tracked_fans.discard(fan_id)

    def reset(self):
        """Clear all state."""
        self._validations.clear()
        self._tracked_fans.clear()

    def get_state(self) -> Dict[str, Any]:
        """Serialize state for replay persistence."""
        return {
            'validations': {
                fid: v.to_dict() for fid, v in self._validations.items()
            },
            'tracked_fans': list(self._tracked_fans),
        }

    def restore_state(self, state: Dict[str, Any]):
        """Restore state from serialized form."""
        self._validations.clear()
        self._tracked_fans.clear()

        if 'validations' in state:
            for fid, v_dict in state['validations'].items():
                self._validations[fid] = FanValidation(**v_dict)

        if 'tracked_fans' in state:
            self._tracked_fans = set(state['tracked_fans'])
