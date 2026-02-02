"""
Angle Engine Module

Calculates Gann angle lines (fan lines) from pivot pairs.
Generates line definitions for fractional divisions of the main angle.

Based on reference implementation from PivotFanBus.js
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
import uuid


# Default Gann angle fractions
DEFAULT_FRACTIONS = [7/8, 3/4, 1/2, 1/4, 1/8]

# Default colors for fraction lines (from reference)
DEFAULT_FRACTION_COLORS = ['#c62828', '#ad1457', '#6a1b9a', '#283593', '#00695c']

# Main angle line color
MAIN_ANGLE_COLOR = '#FF6600'


@dataclass
class AngleLine:
    """Represents a single angle line to be drawn"""
    id: str                 # Unique identifier for this line
    start_time: int         # Unix timestamp (seconds)
    start_price: float      # Price at start
    end_time: int           # Unix timestamp (seconds)
    end_price: float        # Price at end
    color: str              # Line color (hex)
    width: int              # Line width in pixels
    fraction: Optional[float]  # Fraction value (None for main angle)
    fan_id: str             # Parent fan identifier


@dataclass
class AngleFan:
    """Represents a complete angle fan with main line and fraction lines"""
    id: str                 # Unique fan identifier
    from_pivot: Dict        # Source pivot {time, price, type}
    to_pivot: Dict          # Destination pivot {time, price, type}
    lines: List[AngleLine]  # All lines in this fan
    is_completed: bool      # True if price has covered all angles
    config: Dict[str, Any] = field(default_factory=dict)  # Metadata


class AngleEngine:
    """
    Calculates Gann angle lines from pivot pairs.
    
    Given two pivots, generates:
    - Main angle line connecting the pivots
    - Fractional division lines (7/8, 3/4, 1/2, 1/4, 1/8 of the slope)
    
    All lines extend to a configurable bar count or time duration.
    """
    
    def __init__(
        self,
        fractions: List[float] = None,
        fraction_colors: List[str] = None,
        main_color: str = MAIN_ANGLE_COLOR,
        line_extension_bars: int = 50,
        main_line_width: int = 3,
        fraction_line_width: int = 2,
        scale_ratio: float = 1.0  # Added scale ratio parameter
    ):
        """
        Initialize the angle engine.
        
        Args:
            fractions: List of fraction values for division lines
            fraction_colors: Colors for each fraction line
            main_color: Color for the main angle line
            line_extension_bars: How many bars to extend lines beyond pivot
            main_line_width: Width of main angle line
            fraction_line_width: Width of fraction lines
        """
        self.fractions = fractions or DEFAULT_FRACTIONS
        self.fraction_colors = fraction_colors or DEFAULT_FRACTION_COLORS
        self.main_color = main_color
        self.line_extension_bars = line_extension_bars
        self.main_line_width = main_line_width
        self.fraction_line_width = fraction_line_width
        self.scale_ratio = scale_ratio
        
        # Active fans for tracking completion
        self.active_fans: Dict[str, AngleFan] = {}
    
    def create_fan(
        self,
        from_pivot: Dict[str, Any],
        to_pivot: Dict[str, Any],
        current_candles: List[Dict[str, Any]]
    ) -> AngleFan:
        """
        Create an angle fan from two pivots using EXPLICIT ANGLE DIVISION.
        
        Per User Request:
        - Measure the specific angle θ formed by the pivot pair (in data units)
        - θ = arctan(price_change / time_change)
        - Divide THAT specific angle by fractions (7/8, 3/4, 1/2, 1/4)
        - Sub-slopes = tan(θ * fraction)
        
        Args:
            from_pivot: Source pivot {time, price, bar_index, type}
            to_pivot: Destination pivot {time, price, bar_index, type}
            current_candles: All candles for time calculations
            
        Returns:
            AngleFan with all lines calculated
        """
        import math
        
        fan_id = str(uuid.uuid4())[:8]
        lines = []
        
        # Extract pivot data
        t0 = int(from_pivot['time'])
        p0 = float(from_pivot['price'])
        t1 = int(to_pivot['time'])
        p1 = float(to_pivot['price'])
        
        # Calculate time delta and price delta
        dt = max(1, t1 - t0)
        dp = p1 - p0
        
        # --- FIXED SCALE RATIO LOGIC ---
        # To match the Manual Trend Angle tool, we must account for the 
        # "Price to Bar Ratio" (points per bar).
        # Default Ratio = 1.0 (User must lock chart scale to 1.0 to match)
        
        scale_ratio = self.scale_ratio
        
        # Per Strategy Doc (Lines 165-168, 185-188):
        # Angles must radiate FROM the temporally FIRST pivot.
        # Determine which pivot formed first based on time.
        
        if t0 <= t1:
            # from_pivot is temporally first -> angles radiate FROM from_pivot
            origin_time = t0
            origin_price = p0
            origin_bar = from_pivot.get('bar_index', 0)
            target_bar = to_pivot.get('bar_index', 0)
        else:
            # to_pivot is temporally first -> angles radiate FROM to_pivot
            origin_time = t1
            origin_price = p1
            origin_bar = to_pivot.get('bar_index', 0)
            target_bar = from_pivot.get('bar_index', 0)
        
        db = max(1, abs(target_bar - origin_bar))
        
        # Calculate Slope in "Price per Bar"
        # dp is always p1-p0 (to_price - from_price)
        # For slope, we need (target_price - origin_price) / bars
        target_price = p1 if t0 <= t1 else p0
        dp_from_origin = target_price - origin_price
        slope_per_bar = dp_from_origin / db
        
        # Apply Scale Ratio
        visual_slope = slope_per_bar / (scale_ratio if scale_ratio else 1.0)
        
        # Calculate Theta (Visual Angle at 1:1)
        theta_radians = math.atan(visual_slope)
        theta_deg = math.degrees(theta_radians)
        
        # DEBUG: Log scale ratio and angle calculation
        print(f"[AngleEngine] scale_ratio={scale_ratio}, slope_per_bar={slope_per_bar:.4f}, visual_slope={visual_slope:.4f}, theta={theta_deg:.2f}°")
        
        # Helper to ensure finite float values for JSON
        def _safe_float(val, default=0.0):
            if not math.isfinite(val):
                return default
            # Clip extreme values to prevent overflow in frontend
            return max(-1e9, min(1e9, val))

        # Create main angle line - Gray dotted
        # Drawn from origin (first pivot) to target (second pivot)
        main_line = AngleLine(
            id=f"{fan_id}_main",
            start_time=origin_time,
            start_price=_safe_float(origin_price),
            end_time=t1 if t0 <= t1 else t0,  # target time
            end_price=_safe_float(target_price),
            color='#808080',  # Gray for full angle
            width=2,
            fraction=None,
            fan_id=fan_id
        )
        lines.append(main_line)
        
        # Fractional angles per strategy
        angle_fractions = [7/8, 3/4, 1/2, 1/4]
        angle_colors = ['#2196F3', '#4CAF50', '#FF9800', '#F44336']
        
        # Target time for fractional lines (same as main line end)
        target_time = t1 if t0 <= t1 else t0
        
        for i, fraction in enumerate(angle_fractions):
            # Calculate Fractional Theta
            frac_theta = theta_radians * fraction
            
            # Convert back to Slope (Visual)
            frac_visual_slope = math.tan(frac_theta)
            
            # Convert back to Price Slope (Price per Bar)
            frac_slope_per_bar = frac_visual_slope * scale_ratio
            
            # Calculate fractional price change over the same bar distance
            total_price_change = frac_slope_per_bar * db
            frac_end_price = origin_price + total_price_change
            
            color = angle_colors[i] if i < len(angle_colors) else '#888888'
            
            frac_line = AngleLine(
                id=f"{fan_id}_f{i}",
                start_time=origin_time,
                start_price=_safe_float(origin_price),
                end_time=target_time,
                end_price=_safe_float(frac_end_price),
                color=color,
                width=2,
                fraction=fraction,
                fan_id=fan_id
            )
            lines.append(frac_line)
        
        fan = AngleFan(
            id=fan_id,
            from_pivot=from_pivot,
            to_pivot=to_pivot,
            lines=lines,
            is_completed=False
        )
        
        # Track active fan
        self.active_fans[fan_id] = fan
        
        return fan
    
    def check_fan_completion(
        self,
        fan_id: str,
        current_bar: Dict[str, Any]
    ) -> bool:
        """
        Check if price has covered all angle lines in a fan.
        
        A fan is "completed" when price closes beyond the most extreme
        fraction line (1/8 in an uptrend, 7/8 in a downtrend).
        
        Args:
            fan_id: ID of the fan to check
            current_bar: Current candle data
            
        Returns:
            True if fan is now completed, False otherwise
        """
        if fan_id not in self.active_fans:
            return False
        
        fan = self.active_fans[fan_id]
        if fan.is_completed:
            return True
        
        current_time = int(current_bar['time'])
        current_close = float(current_bar['close'])
        
        # Find the most extreme fraction line
        # For uptrend (from low to high): 1/8 is the mildest slope
        # For downtrend (from high to low): 1/8 is the mildest slope (least negative)
        
        is_uptrend = float(fan.to_pivot['price']) > float(fan.from_pivot['price'])
        
        
        # Check if ALL active lines are covered (broked through)
        # Up Fan (Support): Covered if Close < Line
        # Down Fan (Resistance): Covered if Close > Line
        
        active_lines_count = 0
        covered_lines_count = 0
        
        for line in fan.lines:
            if line.fraction is None:
                continue  # Skip main line
            
            # Interpolate line price at current time
            if current_time < line.start_time or current_time > line.end_time:
                continue
            
            active_lines_count += 1
            
            time_ratio = (current_time - line.start_time) / max(1, line.end_time - line.start_time)
            line_price_at_current = line.start_price + time_ratio * (line.end_price - line.start_price)
            
            # Check if price has crossed this line (COVERAGE check)
            if is_uptrend:
                # Up Fan (Support line beneath price)
                # Covered/Broken if price passes BELOW it
                if current_close < line_price_at_current:
                    covered_lines_count += 1
            else:
                # Down Fan (Resistance line above price)
                # Covered/Broken if price passes ABOVE it
                if current_close > line_price_at_current:
                    covered_lines_count += 1
        
        # If no lines are active (e.g. time expired), consider it done
        if active_lines_count == 0:
            fan.is_completed = True
            return True
            
        # If all active fractional lines are covered, fan is complete
        if covered_lines_count == active_lines_count:
            fan.is_completed = True
            return True
            
        return False
    
    def get_completed_fans(self) -> List[str]:
        """Get list of completed fan IDs"""
        return [fan_id for fan_id, fan in self.active_fans.items() if fan.is_completed]
    
    def remove_fan(self, fan_id: str):
        """Remove a fan from tracking"""
        if fan_id in self.active_fans:
            del self.active_fans[fan_id]
    
    def fan_to_drawing_commands(self, fan: AngleFan) -> List[Dict[str, Any]]:
        """
        Convert an AngleFan to frontend drawing commands.
        
        Returns:
            List of drawing command dicts for the frontend
        """
        commands = []
        
        for line in fan.lines:
            cmd = {
                'type': 'trend_line',
                'id': line.id,
                'points': [
                    {'time': line.start_time, 'price': line.start_price},
                    {'time': line.end_time, 'price': line.end_price}
                ],
                'options': {
                    'linecolor': line.color,
                    'linewidth': line.width,
                    'extendLeft': False,
                    'extendRight': False
                }
            }
            commands.append(cmd)
        
        return commands
    
    def get_state(self) -> Dict[str, Any]:
        """Get engine state for serialization"""
        return {
            'active_fans': {
                fan_id: {
                    'id': fan.id,
                    'from_pivot': fan.from_pivot,
                    'to_pivot': fan.to_pivot,
                    'is_completed': fan.is_completed,
                    'lines': [
                        {
                            'id': line.id,
                            'start_time': line.start_time,
                            'start_price': line.start_price,
                            'end_time': line.end_time,
                            'end_price': line.end_price,
                            'color': line.color,
                            'width': line.width,
                            'fraction': line.fraction,
                            'fan_id': line.fan_id
                        }
                        for line in fan.lines
                    ]
                }
                for fan_id, fan in self.active_fans.items()
            }
        }
    
    def restore_state(self, state: Dict[str, Any]):
        """Restore engine state from serialized form"""
        self.active_fans = {}
        
        for fan_id, fan_data in state.get('active_fans', {}).items():
            lines = [
                AngleLine(
                    id=line['id'],
                    start_time=line['start_time'],
                    start_price=line['start_price'],
                    end_time=line['end_time'],
                    end_price=line['end_price'],
                    color=line['color'],
                    width=line['width'],
                    fraction=line['fraction'],
                    fan_id=line['fan_id']
                )
                for line in fan_data.get('lines', [])
            ]
            
            fan = AngleFan(
                id=fan_data['id'],
                from_pivot=fan_data['from_pivot'],
                to_pivot=fan_data['to_pivot'],
                lines=lines,
                is_completed=fan_data.get('is_completed', False)
            )
            self.active_fans[fan_id] = fan

