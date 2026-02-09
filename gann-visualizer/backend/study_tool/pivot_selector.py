"""
Pivot Selector Module (v3.1 - Corrected Stack-Based Framework)

Implements the "Master Protocol v3.0" logic with corrected context determination:

Context Logic:
- Anchor = most recent confirmed pivot
- If Anchor is HIGH → Context = BEARISH (price is falling FROM that high)
- If Anchor is LOW → Context = BULLISH (price is rising FROM that low)

Stack Logic:
- Single backward traversal from anchor, pivot-by-pivot
- Inner Stack: Opposite type to anchor, successively deeper
- Outer Stack: Same type as anchor, successive (below/above anchor price)
- STOP at 2nd successive outer pivot
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from .pivot_detector import Pivot


@dataclass
class PivotStacks:
    """
    Represents the active pivot stacks for the current market state.
    
    Attributes:
        context: 'bullish' (anchor=low, price rising) or 'bearish' (anchor=high, price falling)
        anchor: The most recent confirmed pivot (starting point for traversal)
        inner_stack: Pivots of OPPOSITE type to anchor, successively deeper
        outer_stack: Pivots of SAME type as anchor, below/above anchor price
    """
    context: str
    anchor: Optional[Dict[str, Any]] = None
    inner_stack: List[Dict[str, Any]] = field(default_factory=list)
    outer_stack: List[Dict[str, Any]] = field(default_factory=list)


class PivotSelector:
    """
    Hierarchical Pivot Selector (v3.1 - Corrected)
    
    Key fixes:
    1. Context determined by anchor type: HIGH=bearish, LOW=bullish
    2. Single backward traversal with unified stopping at 2nd outer pivot
    3. Anchor IS the most recent pivot (not searched for by opposite type)
    """

    @staticmethod
    def _pivot_to_dict(pivot: Pivot) -> Dict[str, Any]:
        """Convert a Pivot object to a dictionary."""
        return {
            'time': pivot.time,
            'price': pivot.price,
            'bar_index': pivot.bar_index,
            'type': pivot.pivot_type
        }

    @staticmethod
    def select_stacks(
        current_price: float,
        current_time: int,
        confirmed_pivots: List[Pivot],
        last_pivot: Optional[Pivot]
    ) -> Optional[PivotStacks]:
        """
        Identify the complete pivot stacks (Inner + Outer) for the current moment.
        
        Logic:
        1. Anchor = most recent confirmed pivot (last_pivot)
        2. Context from anchor type: HIGH=bearish, LOW=bullish
        3. Traverse backwards from anchor, pivot-by-pivot
        4. Build Inner Stack (opposite type, successive)
        5. Build Outer Stack (same type, successive, below/above anchor)
        6. STOP at 2nd successive outer pivot
        
        Args:
            current_price: Current Close price
            current_time: Current timestamp
            confirmed_pivots: Full history of confirmed pivots
            last_pivot: The most recent confirmed pivot (becomes anchor)
            
        Returns:
            PivotStacks object or None if insufficient data
        """
        if not confirmed_pivots or not last_pivot:
            return None

        # Anchor = most recent confirmed pivot
        anchor = last_pivot
        
        # Context from anchor type:
        # - Anchor HIGH → price is falling FROM it → BEARISH
        # - Anchor LOW → price is rising FROM it → BULLISH
        context = 'bearish' if anchor.pivot_type == 'high' else 'bullish'
        
        # Sort pivots by time
        sorted_pivots = sorted(confirmed_pivots, key=lambda p: p.time)
        
        # Find anchor index in sorted list
        anchor_index = -1
        for i in range(len(sorted_pivots) - 1, -1, -1):
            if (sorted_pivots[i].time == anchor.time and 
                sorted_pivots[i].pivot_type == anchor.pivot_type):
                anchor_index = i
                break
        
        if anchor_index == -1:
            return None
        
        # Initialize Stacks
        stacks = PivotStacks(
            context=context,
            anchor=PivotSelector._pivot_to_dict(anchor)
        )
        
        # Build stacks based on context
        # Pass current_price for outer pivot comparison
        if context == 'bearish':
            PivotSelector._build_bearish_stacks(stacks, sorted_pivots, anchor_index, current_price)
        else:
            PivotSelector._build_bullish_stacks(stacks, sorted_pivots, anchor_index, current_price)

        return stacks

    @staticmethod
    def _build_bearish_stacks(
        stacks: PivotStacks, 
        sorted_pivots: List[Pivot], 
        anchor_index: int,
        current_price: float
    ):
        """
        Bearish Context (Anchor = HIGH, price falling):
        
        Traverse backwards from anchor:
        - Inner Stack: HIGHS that are successively HIGHER going back (resistance levels)
        - Outer Stack: LOWS below CURRENT PRICE, successively LOWER going back (support/target levels)
        - STOP at 2nd outer pivot
        
        Key: Outer LOWs are compared against CURRENT_PRICE, not anchor price.
        This ensures intermediate pullback lows (above current price) are not included.
        """
        inner_stack = []
        outer_stack = []
        
        # Get anchor price for inner stack comparison
        anchor_price = sorted_pivots[anchor_index].price
        
        # Track successive values
        inner_max = anchor_price   # First inner high must be higher than anchor
        outer_min = current_price  # Outer lows must be below CURRENT PRICE
        
        # Single backward traversal
        for i in range(anchor_index - 1, -1, -1):
            p = sorted_pivots[i]
            
            if p.pivot_type == 'high':
                # Inner Stack: HIGHS successively HIGHER
                if p.price > inner_max:
                    inner_stack.append(p)
                    inner_max = p.price
                    
            elif p.pivot_type == 'low':
                # Outer Stack: LOWS below CURRENT PRICE, successively LOWER
                if p.price < outer_min:
                    outer_stack.append(p)
                    outer_min = p.price
                    
                    # STOP at 3rd outer pivot (1 primary + 2 successive)
                    if len(outer_stack) >= 3:
                        break
        
        stacks.inner_stack = [PivotSelector._pivot_to_dict(p) for p in inner_stack]
        stacks.outer_stack = [PivotSelector._pivot_to_dict(p) for p in outer_stack]

    @staticmethod
    def _build_bullish_stacks(
        stacks: PivotStacks, 
        sorted_pivots: List[Pivot], 
        anchor_index: int,
        current_price: float
    ):
        """
        Bullish Context (Anchor = LOW, price rising):
        
        Traverse backwards from anchor:
        - Inner Stack: LOWS that are successively LOWER going back (support levels)
        - Outer Stack: HIGHS above CURRENT PRICE, successively HIGHER going back (resistance/target levels)
        - STOP at 2nd outer pivot
        
        Key: Outer HIGHs are compared against CURRENT_PRICE, not anchor price.
        This ensures intermediate pullback highs (below current price) are not included.
        """
        inner_stack = []
        outer_stack = []
        
        # Get anchor price for inner stack comparison
        anchor_price = sorted_pivots[anchor_index].price
        
        # Track successive values
        inner_min = anchor_price   # First inner low must be lower than anchor
        outer_max = current_price  # Outer highs must be above CURRENT PRICE
        
        # Single backward traversal
        for i in range(anchor_index - 1, -1, -1):
            p = sorted_pivots[i]
            
            if p.pivot_type == 'low':
                # Inner Stack: LOWS successively LOWER
                if p.price < inner_min:
                    inner_stack.append(p)
                    inner_min = p.price
                    
            elif p.pivot_type == 'high':
                # Outer Stack: HIGHS above CURRENT PRICE, successively HIGHER
                if p.price > outer_max:
                    outer_stack.append(p)
                    outer_max = p.price
                    
                    # STOP at 3rd outer pivot (1 primary + 2 successive)
                    if len(outer_stack) >= 3:
                        break
        
        stacks.inner_stack = [PivotSelector._pivot_to_dict(p) for p in inner_stack]
        stacks.outer_stack = [PivotSelector._pivot_to_dict(p) for p in outer_stack]
