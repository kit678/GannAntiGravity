"""
Pivot Selector Module (v2.1 - Fixed Hierarchical Framework)

Implements the "Outer Container + Inner Sequence" logic for the Angular Price Coverage Strategy.

Key Concepts:
- Outer Container: The largest relevant swing bounding current price action
- Inner Sequence: Intermediate pivot pairs nested within the Outer Container
- CRITICAL: Fans ALWAYS connect opposite pivot types (High ↔ Low)

This module identifies BOTH the Outer pair and the sequence of Inner pairs,
enabling the visualization of nested Gann fans.

Logic based on Strategy Docs (Section 9 - Pivot Management).
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from .pivot_detector import Pivot


@dataclass
class PivotHierarchy:
    """
    Represents the complete hierarchical structure of pivots.
    
    Attributes:
        context: 'bullish' (price rising) or 'bearish' (price falling)
        outer_container: The Outer pair (largest bounding swing)
        inner_sequence: List of Inner pairs (nested within Outer)
        origin_pivot: The most recent pivot (starting point for analysis)
        inner_anchor: The pivot of opposite type used as anchor for inner fans
    """
    context: str
    outer_container: Optional[Dict[str, Any]] = None
    inner_sequence: List[Dict[str, Any]] = field(default_factory=list)
    origin_pivot: Optional[Dict[str, Any]] = None
    inner_anchor: Optional[Dict[str, Any]] = None  # The opposite-type pivot for inner fans


class PivotSelector:
    """
    Hierarchical Pivot Selector (v2.1 - Fixed)
    
    Implements the documented strategy for identifying:
    1. The Outer Container (persistent reference frame)
    2. The Inner Sequence (dynamic intermediate pivots)
    
    CRITICAL FIX: Fans always connect opposite pivot types (High ↔ Low).
    
    Supports both Bearish and Bullish retracement scenarios.
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
    def select_hierarchy(
        current_price: float,
        current_time: int,
        confirmed_pivots: List[Pivot],
        last_pivot: Optional[Pivot]
    ) -> Optional[PivotHierarchy]:
        """
        Identify the complete pivot hierarchy (Outer Container + Inner Sequence).
        
        Args:
            current_price: Current Close price
            current_time: Current timestamp
            confirmed_pivots: Full history of confirmed pivots (sorted by time)
            last_pivot: The most recent confirmed pivot
            
        Returns:
            PivotHierarchy object or None if insufficient data
        """
        if last_pivot:
            print(f"[PivotSelector] select_hierarchy called at {current_time}. Last Pivot: {last_pivot.pivot_type} at {last_pivot.price}")
        else:
            print(f"[PivotSelector] select_hierarchy called at {current_time}. Last Pivot: None")

        if not confirmed_pivots or not last_pivot:
            return None

        # Determine Context based on the LAST pivot type
        # If Last Pivot is LOW -> We are moving UP (Bullish Context)
        # If Last Pivot is HIGH -> We are moving DOWN (Bearish Context)
        context = 'bullish' if last_pivot.pivot_type == 'low' else 'bearish'
        
        origin_pivot = PivotSelector._pivot_to_dict(last_pivot)
        
        # Sort pivots by time (oldest first for sequential analysis)
        sorted_pivots = sorted(confirmed_pivots, key=lambda p: p.time)
        
        if context == 'bearish':
            return PivotSelector._select_bearish_hierarchy(
                current_price, origin_pivot, sorted_pivots
            )
        else:
            return PivotSelector._select_bullish_hierarchy(
                current_price, origin_pivot, sorted_pivots
            )

    @staticmethod
    def _select_bearish_hierarchy(
        current_price: float,
        origin_pivot: Dict[str, Any],
        sorted_pivots: List[Pivot]
    ) -> PivotHierarchy:
        """
        Bearish Scenario: Price is falling after a major High.
        
        The origin_pivot is a HIGH (that's what made context bearish).
        
        For Inner Fans, we need to:
        1. Find the most recent LOW as the "anchor" (fan destination)
        2. Find intermediate HIGHs that connect TO this LOW
        
        For Outer Container:
        1. Find Outer Low (A): Nearest Low BELOW current price
        2. Find Outer High (B): HIGHEST High between A and Now
        """
        hierarchy = PivotHierarchy(
            context='bearish',
            origin_pivot=origin_pivot
        )
        
        # Step 1: Find the most recent LOW to use as Inner Fan anchor
        # This is CRITICAL - we need the opposite type for valid fan construction
        inner_anchor_pivot = None
        for i in range(len(sorted_pivots) - 1, -1, -1):
            p = sorted_pivots[i]
            if p.pivot_type == 'low':
                inner_anchor_pivot = p
                break
        
        if inner_anchor_pivot:
            # FAN INVALIDATION RULE:
            # If current price is BELOW the anchor Low, the pivot is breached.
            # The structure C->E is no longer valid as an active reaction range.
            if current_price < inner_anchor_pivot.price:
                # print(f"[PivotSelector] Anchor Low {inner_anchor_pivot.price} breached by price {current_price}. Invalidating.")
                inner_anchor_pivot = None
            else:
                hierarchy.inner_anchor = PivotSelector._pivot_to_dict(inner_anchor_pivot)
        
        # Step 2: Find Outer Low (A) - nearest Low BELOW current price
        outer_low = None
        outer_low_index = -1
        
        for i in range(len(sorted_pivots) - 1, -1, -1):
            p = sorted_pivots[i]
            if p.pivot_type == 'low' and p.price < current_price:
                outer_low = p
                outer_low_index = i
                break
        
        if outer_low is None:
            # No valid Outer Low found - can't establish container
            return hierarchy
        
        # Step 3: Find Outer High (B) - HIGHEST High between A and Now
        outer_high = None
        highest_price = -float('inf')
        
        for i in range(outer_low_index + 1, len(sorted_pivots)):
            p = sorted_pivots[i]
            if p.pivot_type == 'high' and p.price > highest_price:
                highest_price = p.price
                outer_high = p
        
        if outer_high is None:
            return hierarchy
        
        # Create Outer Container (High → Low)
        hierarchy.outer_container = {
            'from': PivotSelector._pivot_to_dict(outer_high),  # Fan radiates FROM the High
            'to': PivotSelector._pivot_to_dict(outer_low),     # Fan points TO the Low
            'type': 'outer',
            'context': 'bearish'
        }
        
        # Step 4: Find Inner Sequence - intermediate HIGHs that connect to the recent LOW
        # Only if we have a valid inner anchor (a recent LOW)
        if inner_anchor_pivot is None:
            return hierarchy
        
        # Collect ALL candidate highs between outer_high and inner_anchor that are above current price
        candidate_highs = []
        
        for i in range(len(sorted_pivots) - 1, -1, -1):
            p = sorted_pivots[i]
            
            # Stop when we reach the outer low (before our active range)
            if p.time <= outer_low.time:
                break
            
            # Skip if this is the outer high (already covered by outer fan)
            if p.time == outer_high.time:
                continue
            
            if p.pivot_type == 'high':
                # This is an intermediate High - check if it's above current price
                # (still relevant as resistance)
                if p.price > current_price:
                    candidate_highs.append(p)
        
        # Sort candidate highs by TIME (oldest first) - iterate FROM outer TOWARD anchor
        # This ensures: earlier higher highs set the max, later lower highs get shadowed
        candidate_highs.sort(key=lambda p: p.time)
        
        # DEBUG: Log candidate highs in time order (oldest first)
        print(f"[PivotSelector] Bearish - Candidate highs above current price {current_price} (oldest first):")
        for h in candidate_highs:
            print(f"  - High at price {h.price}, time {h.time}")
        
        # ASCENDING STAIRCASE FILTER (corrected v3):
        # Iterate from OLDEST to NEWEST (outer toward anchor)
        # Only include a high if it's HIGHER than any EARLIER high we've seen
        # This way, a later high that's LOWER than an earlier one gets "shadowed" and skipped
        # CRITICAL: Start with outer_high price as baseline - any inner high must be HIGHER than outer_high
        inner_highs = []
        # FIX: Start with -infinity. Do NOT use outer_high as baseline, 
        # otherwise we reject legitimate Lower Highs in a downtrend.
        max_price_seen = -float('inf')
        
        for high in candidate_highs:
            # Only include if this high is HIGHER than any earlier high we've seen
            if high.price > max_price_seen:
                print(f"[PivotSelector] INCLUDED: High at {high.price} > max_earlier {max_price_seen}")
                inner_highs.append(high)
                max_price_seen = high.price
            else:
                print(f"[PivotSelector] SKIPPED: High at {high.price} <= max_earlier {max_price_seen} (shadowed by earlier higher pivot)")
        
        print(f"[PivotSelector] Final inner_highs count: {len(inner_highs)}")
        
        # Create Inner Sequence pairs (each High → the recent Low anchor)
        # ADDITIONAL FILTER: Skip fans where the start point (High) has been breached
        # If current_price > High, the fan is obsolete (angle completely traversed)
        for inner_high in inner_highs:
            if current_price > inner_high.price:
                print(f"[PivotSelector] SKIPPED FAN: High at {inner_high.price} breached by price {current_price} (angle traversed)")
                continue
            hierarchy.inner_sequence.append({
                'from': PivotSelector._pivot_to_dict(inner_high),           # Fan radiates FROM the High
                'to': PivotSelector._pivot_to_dict(inner_anchor_pivot),     # Fan points TO the recent Low
                'type': 'inner',
                'context': 'bearish'
            })
        
        return hierarchy

    @staticmethod
    def _select_bullish_hierarchy(
        current_price: float,
        origin_pivot: Dict[str, Any],
        sorted_pivots: List[Pivot]
    ) -> PivotHierarchy:
        """
        Bullish Scenario: Price is rising after a major Low.
        
        The origin_pivot is a LOW (that's what made context bullish).
        
        For Inner Fans, we need to:
        1. Find the most recent HIGH as the "anchor" (fan destination)
        2. Find intermediate LOWs that connect TO this HIGH
        
        For Outer Container:
        1. Find Outer High (A): Nearest High ABOVE current price
        2. Find Outer Low (B): LOWEST Low between A and Now
        """
        hierarchy = PivotHierarchy(
            context='bullish',
            origin_pivot=origin_pivot
        )
        
        # Step 1: Find the most recent HIGH to use as Inner Fan anchor
        # This is CRITICAL - we need the opposite type for valid fan construction
        inner_anchor_pivot = None
        for i in range(len(sorted_pivots) - 1, -1, -1):
            p = sorted_pivots[i]
            if p.pivot_type == 'high':
                inner_anchor_pivot = p
                break
        
        if inner_anchor_pivot:
            # FAN INVALIDATION RULE:
            # If current price is ABOVE the anchor High, the pivot is breached.
            # The structure Low->High is no longer valid as an active reaction range.
            if current_price > inner_anchor_pivot.price:
                # print(f"[PivotSelector] Anchor High {inner_anchor_pivot.price} breached by price {current_price}. Invalidating.")
                inner_anchor_pivot = None
            else:
                hierarchy.inner_anchor = PivotSelector._pivot_to_dict(inner_anchor_pivot)
                # print(f"  [Bullish] Inner Anchor Selected: {inner_anchor_pivot.price} at {inner_anchor_pivot.time}")
        else:
            print(f"  [Bullish] No valid Inner Anchor (High) found in sorted_pivots")
        
        # Step 2: Find Outer High (A) - nearest High ABOVE current price
        outer_high = None
        outer_high_index = -1
        
        for i in range(len(sorted_pivots) - 1, -1, -1):
            p = sorted_pivots[i]
            if p.pivot_type == 'high' and p.price > current_price:
                outer_high = p
                outer_high_index = i
                break
        
        if outer_high is None:
            return hierarchy
        
        # Step 3: Find Outer Low (B) - LOWEST Low between A and Now
        outer_low = None
        lowest_price = float('inf')
        
        for i in range(outer_high_index + 1, len(sorted_pivots)):
            p = sorted_pivots[i]
            if p.pivot_type == 'low' and p.price < lowest_price:
                lowest_price = p.price
                outer_low = p
        
        if outer_low is None:
            return hierarchy
        
        # Create Outer Container (Low → High)
        hierarchy.outer_container = {
            'from': PivotSelector._pivot_to_dict(outer_low),   # Fan radiates FROM the Low
            'to': PivotSelector._pivot_to_dict(outer_high),    # Fan points TO the High
            'type': 'outer',
            'context': 'bullish'
        }
        
        # Step 4: Find Inner Sequence - intermediate LOWs that connect to the recent HIGH
        # Only if we have a valid inner anchor (a recent HIGH)
        if inner_anchor_pivot is None:
            return hierarchy
        
        # Collect ALL candidate lows between outer_low and inner_anchor that are below current price
        candidate_lows = []
        
        for i in range(len(sorted_pivots) - 1, -1, -1):
            p = sorted_pivots[i]
            
            # Stop when we reach the outer high (before our active range)
            if p.time <= outer_high.time:
                break
            
            # Skip if this is the outer low (already covered by outer fan)
            if p.time == outer_low.time:
                continue
            
            if p.pivot_type == 'low':
                # This is an intermediate Low - check if it's below current price
                # (still relevant as support)
                if p.price < current_price:
                    candidate_lows.append(p)
        
        # Sort candidate lows by TIME (oldest first) - iterate FROM outer TOWARD anchor
        # This ensures: earlier lower lows set the min, later higher lows get shadowed
        candidate_lows.sort(key=lambda p: p.time)
        
        # DESCENDING STAIRCASE FILTER (corrected v3):
        # Iterate from OLDEST to NEWEST (outer toward anchor)
        # Only include a low if it's LOWER than any EARLIER low we've seen
        # This way, a later low that's HIGHER than an earlier one gets "shadowed" and skipped
        # CRITICAL: Start with outer_low price as baseline - any inner low must be LOWER than outer_low
        inner_lows = []
        # FIX: Start with infinity. Do NOT use outer_low as baseline,
        # otherwise we reject legitimate Higher Lows in an uptrend.
        min_price_seen = float('inf')
        
        for low in candidate_lows:
            # Only include if this low is LOWER than any earlier low we've seen
            if low.price < min_price_seen:
                inner_lows.append(low)
                min_price_seen = low.price
        
        # Create Inner Sequence pairs (each Low → the recent High anchor)
        # ADDITIONAL FILTER: Skip fans where the start point (Low) has been breached
        # If current_price < Low, the fan is obsolete (angle completely traversed)
        for inner_low in inner_lows:
            if current_price < inner_low.price:
                print(f"[PivotSelector] SKIPPED FAN: Low at {inner_low.price} breached by price {current_price} (angle traversed)")
                continue
            hierarchy.inner_sequence.append({
                'from': PivotSelector._pivot_to_dict(inner_low),            # Fan radiates FROM the Low
                'to': PivotSelector._pivot_to_dict(inner_anchor_pivot),     # Fan points TO the recent High
                'type': 'inner',
                'context': 'bullish'
            })
        
        return hierarchy

    # Keep legacy method for backward compatibility
    @staticmethod
    def select_active_pair(
        current_price: float,
        current_time: int,
        confirmed_pivots: List[Pivot],
        last_pivot: Optional[Pivot]
    ) -> Optional[Dict[str, Any]]:
        """
        Legacy method - returns only the Outer Container's pair.
        
        For full hierarchy support, use select_hierarchy() instead.
        """
        hierarchy = PivotSelector.select_hierarchy(
            current_price, current_time, confirmed_pivots, last_pivot
        )
        
        if hierarchy and hierarchy.outer_container:
            return hierarchy.outer_container
        
        return None
