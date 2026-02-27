"""
Target Progression

Manages the sequential target list for each fan and tracks progress
through targets as price moves.

Target sequence per fan:
    7/8 → 3/4 → 1/2 → [horizontal_target | 1/4] → full_coverage

Special rules:
- Fan is only active for progression after FanValidator marks it validated
- After 1/2 breach, if 1/4 is reached before horizontal target,
  horizontal target is cancelled
- After horizontal target breach, final target is the other pivot's price
  (Michael Jenkins secret angle method — full angular coverage)
"""

from dataclasses import dataclass, asdict, field
from typing import Dict, List, Any, Optional


@dataclass
class TargetHit:
    """Records when a target in the sequence is hit."""
    fan_id: str
    target_name: str      # "7/8", "3/4", "1/2", "horizontal", "1/4", "full_coverage"
    hit_bar: int          # bar index when confirmed
    hit_price: float      # price when confirmed

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FanTargetState:
    """
    Complete target tracking state for one fan.
    
    This is the core state machine that tracks which target we're
    working towards and what has been achieved.
    """
    fan_id: str
    is_validated: bool = False                  # set by FanValidator
    current_target: Optional[str] = None        # current target name
    targets_hit: List[str] = field(default_factory=list)
    targets_remaining: List[str] = field(default_factory=list)
    horizontal_target_active: bool = True       # can be cancelled by 1/4
    horizontal_target_price: Optional[float] = None  # price level of horizontal
    full_coverage_target_price: Optional[float] = None  # other pivot's price
    completed: bool = False                     # all targets hit

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Default target sequence (before 1/2 nuance is applied)
BASE_TARGET_SEQUENCE = ['7/8', '3/4', '1/2']
# After 1/2, sequence depends on which is reached first
POST_HALF_TARGETS = ['horizontal', '1/4']
FINAL_TARGET = 'full_coverage'


class TargetProgression:
    """
    Manages target progression for all active fans.
    
    Each fan has an independent target sequence. The progression
    only starts after the fan is validated by FanValidator.
    
    When BreachAnalyzer confirms a breach at the current target,
    this module advances to the next target in the sequence.
    """

    def __init__(self):
        # fan_id -> FanTargetState
        self._fan_states: Dict[str, FanTargetState] = {}
        # History of all target hits across all fans
        self._target_hits: List[TargetHit] = []

    def register_fan(
        self,
        fan_id: str,
        horizontal_target_price: Optional[float] = None,
        full_coverage_target_price: Optional[float] = None
    ):
        """
        Register a new fan for target tracking.
        
        Args:
            fan_id: Unique fan identifier
            horizontal_target_price: Price level of the horizontal target
                (derived from 1/2 angle ∩ vertical at second pivot)
            full_coverage_target_price: Price of the other (non-anchor) pivot
        """
        if fan_id in self._fan_states:
            return  # already registered

        state = FanTargetState(
            fan_id=fan_id,
            targets_remaining=list(BASE_TARGET_SEQUENCE),
            current_target='7/8',
            horizontal_target_price=horizontal_target_price,
            full_coverage_target_price=full_coverage_target_price,
        )
        self._fan_states[fan_id] = state

    def activate_fan(self, fan_id: str):
        """
        Mark a fan as validated (called when FanValidator confirms 7/8 interaction).
        The fan can now participate in target progression.
        """
        state = self._fan_states.get(fan_id)
        if state:
            state.is_validated = True

    def on_breach_confirmed(
        self,
        fan_id: str,
        angle_name: str,
        bar_index: int,
        price: float
    ) -> Optional[TargetHit]:
        """
        Called when BreachAnalyzer confirms a breach at a specific angle.
        
        If the breached angle matches the current target, advance the
        progression to the next target.
        
        Args:
            fan_id: Fan where breach occurred
            angle_name: Angle label that was breached (e.g., "7/8")
            bar_index: Bar index of breach confirmation
            price: Price at breach confirmation
            
        Returns:
            TargetHit if this breach advanced the progression, None otherwise
        """
        state = self._fan_states.get(fan_id)
        if state is None or state.completed:
            return None

        # Only process if this is the current target
        if state.current_target != angle_name:
            # Special case: 1/4 reached before horizontal
            if angle_name == '1/4' and state.current_target == 'horizontal':
                return self._handle_quarter_before_horizontal(state, bar_index, price)
            return None

        # Record the hit
        hit = TargetHit(
            fan_id=fan_id,
            target_name=angle_name,
            hit_bar=bar_index,
            hit_price=price,
        )
        self._target_hits.append(hit)
        state.targets_hit.append(angle_name)

        # Remove from remaining and advance
        if angle_name in state.targets_remaining:
            state.targets_remaining.remove(angle_name)

        # Determine next target
        self._advance_target(state, angle_name)

        return hit

    def _advance_target(self, state: FanTargetState, just_hit: str):
        """Advance to the next target based on what was just hit."""
        if state.targets_remaining:
            state.current_target = state.targets_remaining[0]
            return

        # Base sequence exhausted — handle post-1/2 logic
        if just_hit == '1/2':
            # After 1/2, next targets are horizontal and 1/4
            # Horizontal is the primary target; 1/4 could cancel it
            if state.horizontal_target_active and state.horizontal_target_price is not None:
                state.current_target = 'horizontal'
                state.targets_remaining = ['horizontal']
            else:
                state.current_target = '1/4'
                state.targets_remaining = ['1/4']
            return

        if just_hit == 'horizontal':
            # After horizontal breach, target is full coverage
            # (Michael Jenkins secret angle method)
            state.current_target = FINAL_TARGET
            state.targets_remaining = [FINAL_TARGET]
            return

        if just_hit == '1/4':
            # 1/4 was the last target if horizontal was cancelled
            if 'horizontal' not in state.targets_hit:
                # 1/4 reached but horizontal wasn't — no more targets
                state.current_target = None
                state.completed = True
            else:
                # Both horizontal and 1/4 were hit — proceed to full coverage
                state.current_target = FINAL_TARGET
                state.targets_remaining = [FINAL_TARGET]
            return

        if just_hit == FINAL_TARGET:
            state.current_target = None
            state.completed = True
            return

        # Default: no more targets
        state.current_target = None
        state.completed = True

    def _handle_quarter_before_horizontal(
        self, state: FanTargetState, bar_index: int, price: float
    ) -> Optional[TargetHit]:
        """
        Handle the case where 1/4 is reached before horizontal target.
        
        Per strategy rules: if price reacts from 1/4 before reaching
        the horizontal target, the horizontal target is INVALIDATED.
        We have no further targets unless price re-engages through 1/2.
        """
        # Cancel horizontal target
        state.horizontal_target_active = False
        
        hit = TargetHit(
            fan_id=state.fan_id,
            target_name='1/4',
            hit_bar=bar_index,
            hit_price=price,
        )
        self._target_hits.append(hit)
        state.targets_hit.append('1/4')
        
        # No more targets — progression paused
        state.current_target = None
        state.targets_remaining.clear()
        state.completed = True

        return hit

    def get_fan_state(self, fan_id: str) -> Optional[FanTargetState]:
        """Get the current target state for a fan."""
        return self._fan_states.get(fan_id)

    def get_current_target(self, fan_id: str) -> Optional[str]:
        """Get the current target angle for a fan."""
        state = self._fan_states.get(fan_id)
        return state.current_target if state else None

    def is_fan_completed(self, fan_id: str) -> bool:
        """Check if a fan has completed all its targets."""
        state = self._fan_states.get(fan_id)
        return state.completed if state else False

    def get_all_target_hits(self) -> List[TargetHit]:
        """Get all target hits across all fans."""
        return list(self._target_hits)

    def remove_fan(self, fan_id: str):
        """Clean up when a fan is removed."""
        self._fan_states.pop(fan_id, None)

    def reset(self):
        """Clear all state."""
        self._fan_states.clear()
        self._target_hits.clear()

    def get_state(self) -> Dict[str, Any]:
        """Serialize state for replay persistence."""
        return {
            'fan_states': {
                fid: s.to_dict() for fid, s in self._fan_states.items()
            },
            'target_hits': [h.to_dict() for h in self._target_hits],
        }

    def restore_state(self, state: Dict[str, Any]):
        """Restore state from serialized form."""
        self._fan_states.clear()
        self._target_hits.clear()

        if 'fan_states' in state:
            for fid, s_dict in state['fan_states'].items():
                self._fan_states[fid] = FanTargetState(**s_dict)

        if 'target_hits' in state:
            self._target_hits = [TargetHit(**h) for h in state['target_hits']]
