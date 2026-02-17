"""
Fan Manager Module (v4.0)

Implements the Unified Backward Traversal logic for identifying active fans.
Applies Rules 1-6 from Angular Price Coverage Strategy v4.0:
  1. Anchor Validity
  2. Geometric Validity
  3. Clear Path
  4. Breach Check
  5. Successive Geometry
  6. Global Fan Limit
"""

from typing import List, Dict, Any, Optional
from .pivot_detector import Pivot


class FanManager:
    """
    Stateless utility class that implements the unified backward traversal
    to find active fans from a list of confirmed pivots.
    """

    @staticmethod
    def find_active_fans(
        confirmed_pivots: List[Pivot],
        candles: List[Dict[str, Any]],
        current_bar_index: int = -1,
        max_fans: int = 3,
        breach_mode: str = 'wick'
    ) -> List[Dict[str, Any]]:
        """
        Unified backward traversal to find active fans.

        Args:
            confirmed_pivots: All detected pivots (time-ordered).
            candles: OHLC candle data.
            current_bar_index: Current bar index (-1 = last bar).
            max_fans: Maximum total active fans (configurable, default 3).
            breach_mode: 'wick' (use high/low) or 'close' (use close price).

        Returns:
            List of fan dicts with anchor, target, and priority info.
        """
        if not confirmed_pivots or not candles:
            return []

        # Determine the effective candle range
        if current_bar_index == -1 or current_bar_index >= len(candles):
            current_bar_index = len(candles) - 1

        valid_candles = candles[:current_bar_index + 1]
        current_price = float(valid_candles[-1]['close'])

        # Sort pivots by time (should already be sorted, but ensure)
        sorted_pivots = sorted(confirmed_pivots, key=lambda p: p.time)

        # Filter pivots that are within our candle range
        sorted_pivots = [p for p in sorted_pivots if p.bar_index <= current_bar_index]

        if not sorted_pivots:
            return []

        active_fans = []
        total_fans = 0

        # Iterate anchors: most recent pivot first
        for anchor_idx in range(len(sorted_pivots) - 1, -1, -1):
            if total_fans >= max_fans:
                break

            anchor = sorted_pivots[anchor_idx]

            # --- Rule 1: Anchor Validity ---
            if not FanManager._is_anchor_valid(anchor, sorted_pivots, anchor_idx, valid_candles, current_price):
                continue

            # Track the last accepted target price for Rule 5 (Successive Geometry)
            last_accepted_price = None

            # Iterate targets: scan backwards from just before the anchor
            for target_idx in range(anchor_idx - 1, -1, -1):
                if total_fans >= max_fans:
                    break

                target = sorted_pivots[target_idx]

                # --- Rule 2: Geometric Validity ---
                # Target must be opposite type
                if target.pivot_type == anchor.pivot_type:
                    continue

                # Target must be below High anchor / above Low anchor
                if anchor.pivot_type == 'high' and target.price >= anchor.price:
                    continue
                if anchor.pivot_type == 'low' and target.price <= anchor.price:
                    continue

                # --- Rule 3: Clear Path ---
                if not FanManager._is_path_clear(anchor, target, sorted_pivots, anchor_idx, target_idx):
                    continue

                # --- Rule 4: Breach Check ---
                if FanManager._is_target_breached(anchor, target, valid_candles, breach_mode):
                    continue  # Waterfall: skip to next target

                # --- Rule 5: Successive Geometry ---
                if last_accepted_price is not None:
                    if anchor.pivot_type == 'high':
                        # Lows must be successively lower
                        if target.price >= last_accepted_price:
                            continue
                    else:
                        # Highs must be successively higher
                        if target.price <= last_accepted_price:
                            continue

                # All rules passed — emit fan
                priority_label = ['Primary', 'Secondary', 'Tertiary'][total_fans] if total_fans < 3 else f'Fan_{total_fans + 1}'

                active_fans.append({
                    'anchor': {
                        'time': anchor.time,
                        'price': anchor.price,
                        'type': anchor.pivot_type,
                        'bar_index': anchor.bar_index
                    },
                    'target': {
                        'time': target.time,
                        'price': target.price,
                        'type': target.pivot_type,
                        'bar_index': target.bar_index
                    },
                    'priority': total_fans,
                    'priority_label': priority_label
                })

                last_accepted_price = target.price
                total_fans += 1

        return active_fans

    @staticmethod
    def _is_anchor_valid(
        anchor: Pivot,
        sorted_pivots: List[Pivot],
        anchor_idx: int,
        valid_candles: List[Dict[str, Any]],
        current_price: float
    ) -> bool:
        """
        Rule 1: Check if anchor is valid.
        - High Anchor: Invalid if any later High pivot is higher.
        - Low Anchor: Invalid if current price < anchor price (breached).
        """
        if anchor.pivot_type == 'high':
            # Check if any later HIGH pivot is higher
            for i in range(anchor_idx + 1, len(sorted_pivots)):
                if sorted_pivots[i].pivot_type == 'high' and sorted_pivots[i].price > anchor.price:
                    return False
            return True
        else:  # low anchor
            # Invalid if price has fallen below this low
            if current_price < anchor.price:
                return False
            # Also check if any later LOW pivot is lower
            for i in range(anchor_idx + 1, len(sorted_pivots)):
                if sorted_pivots[i].pivot_type == 'low' and sorted_pivots[i].price < anchor.price:
                    return False
            return True

    @staticmethod
    def _is_path_clear(
        anchor: Pivot,
        target: Pivot,
        sorted_pivots: List[Pivot],
        anchor_idx: int,
        target_idx: int
    ) -> bool:
        """
        Rule 3: Check that no intermediate pivot of the same type as the anchor
        is more extreme (higher High / lower Low) than the anchor.
        """
        for i in range(target_idx + 1, anchor_idx):
            intermediate = sorted_pivots[i]

            if anchor.pivot_type == 'high':
                # Check intermediate Highs
                if intermediate.pivot_type == 'high' and intermediate.price > anchor.price:
                    return False
            else:
                # Check intermediate Lows
                if intermediate.pivot_type == 'low' and intermediate.price < anchor.price:
                    return False

        return True

    @staticmethod
    def _is_target_breached(
        anchor: Pivot,
        target: Pivot,
        valid_candles: List[Dict[str, Any]],
        breach_mode: str = 'wick'
    ) -> bool:
        """
        Rule 4: Check if the target level has been breached by price action
        after the anchor formed.
        """
        # Get candles after the anchor
        after_anchor = [c for c in valid_candles if int(c['time']) > anchor.time]

        if not after_anchor:
            return False

        if target.pivot_type == 'low':
            # Low target: breached if price fell below target level
            if breach_mode == 'close':
                min_price = min(float(c['close']) for c in after_anchor)
            else:  # wick
                min_price = min(float(c['low']) for c in after_anchor)
            return min_price < target.price

        else:  # high target
            # High target: breached if price rose above target level
            if breach_mode == 'close':
                max_price = max(float(c['close']) for c in after_anchor)
            else:  # wick
                max_price = max(float(c['high']) for c in after_anchor)
            return max_price > target.price
