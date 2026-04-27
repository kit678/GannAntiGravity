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
DEFAULT_FRACTIONS = [7/8, 3/4, 1/2, 1/4]

# Default colors for fraction lines (from reference)
DEFAULT_FRACTION_COLORS = ['#c62828', '#ad1457', '#6a1b9a', '#283593']

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
    start_bar_index: float = 0.0 # Origin bar index for accurate intersection
    end_bar_index: float = 0.0   # End bar index for accurate intersection


@dataclass
class AngleFan:
    """Represents a complete angle fan with main line and fraction lines"""
    id: str                 # Unique fan identifier
    from_pivot: Dict        # Source pivot {time, price, type}
    to_pivot: Dict          # Destination pivot {time, price, type}
    lines: List[AngleLine]  # All lines in this fan
    is_completed: bool      # True if price has covered all angles
    priority_label: str = "Unknown" # Fan priority (Primary, Secondary, etc.)
    anchor_type: str = ""   # "low" or "high" — determines breach direction
    config: Dict[str, Any] = field(default_factory=dict)  # Metadata
    intersections: List[Any] = field(default_factory=list) # Store IntersectionEvent objects
    label_ids: List[str] = field(default_factory=list)     # Store drawing IDs


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
        scale_ratio: float = 1.0,  # Added scale ratio parameter
        resolution: str = None,
        symbol: str = None
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
            symbol: Ticker symbol, used to determine market timezone
        """
        self.fractions = fractions or DEFAULT_FRACTIONS
        self.fraction_colors = fraction_colors or DEFAULT_FRACTION_COLORS
        self.main_color = main_color
        self.line_extension_bars = line_extension_bars
        self.main_line_width = main_line_width
        self.fraction_line_width = fraction_line_width
        self.scale_ratio = scale_ratio
        self.resolution = resolution
        self.symbol = symbol or ''
        
        # Determine market timezone from symbol
        import pytz
        sym_upper = self.symbol.upper()
        if '.NS' in sym_upper or '.BO' in sym_upper or sym_upper.startswith('^NSE') or 'NIFTY' in sym_upper or 'NSEI' in sym_upper:
            self.market_tz = pytz.timezone('Asia/Kolkata')
        else:
            self.market_tz = pytz.timezone('America/New_York')
        
        # Active fans for tracking completion
        self.active_fans: Dict[str, AngleFan] = {}
    
    def _get_time_for_bar_index(self, bar_idx: float, current_candles: List[Dict[str, Any]]) -> int:
        """Helper to project time for a given bar index based on market schedule."""
        import datetime
        from collections import Counter

        bar_idx = int(round(bar_idx))
        if not current_candles:
            return 0
            
        # 1. If index exists in history, use exact timestamp
        if 0 <= bar_idx < len(current_candles):
             return int(current_candles[bar_idx]['time'])
        
        # Determine valid slots
        sample_candles = current_candles[-200:] if len(current_candles) > 200 else current_candles
        time_slots_counter = Counter()
        for c in sample_candles:
            dt = datetime.datetime.fromtimestamp(int(c['time']), tz=self.market_tz)
            time_slots_counter[(dt.hour, dt.minute)] += 1
            
        if time_slots_counter:
            max_count = time_slots_counter.most_common(1)[0][1]
            threshold = max_count * 0.3
            valid_slots = [slot for slot, count in time_slots_counter.items() if count >= threshold]
            valid_slots.sort()
        else:
            valid_slots = [(9, 15), (10, 15), (11, 15), (12, 15), (13, 15), (14, 15), (15, 15)]

        # 2. If index is in future, project
        last_idx = len(current_candles) - 1
        last_time = int(current_candles[-1]['time'])
        
        if bar_idx > last_idx:
            delta_bars = bar_idx - last_idx
            
            # Simple linear time projection: Add (delta * interval)
            # This is cleaner for short-term projections and avoids the complex slot/holiday logic 
            # which can drift significantly when projecting from Bar 0 into empty space.
            interval_seconds = 900 if self.resolution == '15' else 3600
            if self.resolution == '1': interval_seconds = 60
            elif self.resolution == '4': interval_seconds = 240
            elif self.resolution == '5': interval_seconds = 300
            elif self.resolution == '30': interval_seconds = 1800
            elif self.resolution == '240': interval_seconds = 14400
            elif self.resolution == 'D': interval_seconds = 86400
            
            return last_time + (int(delta_bars) * interval_seconds)
        
        # 3. Before history
        first_time = int(current_candles[0]['time'])
        delta_bars = 0 - bar_idx
        interval_seconds = 900 if self.resolution == '15' else 3600
        return first_time - (delta_bars * interval_seconds)

    def extend_fan(self, fan: AngleFan, target_bar_index: float, current_candles: List[Dict[str, Any]]):
        """
        Dynamically extend the lines of a fan to a new target bar index.
        Calculates the new end_time and end_price using linear projection.
        """
        for line in fan.lines:
            # Skip if line already extends beyond target
            if line.end_bar_index >= target_bar_index:
                continue
                
            db = line.end_bar_index - line.start_bar_index
            if db <= 0:
                continue
                
            # Calculate slope per bar
            slope_per_bar = (line.end_price - line.start_price) / db
            
            # Project to new bar index
            new_db = target_bar_index - line.start_bar_index
            new_end_price = line.start_price + (slope_per_bar * new_db)
            new_end_time = int(self._get_time_for_bar_index(target_bar_index, current_candles))
            
            # Update line properties
            line.end_bar_index = float(target_bar_index)
            line.end_price = new_end_price
            line.end_time = new_end_time

    def create_fan(
        self,
        from_pivot: Dict[str, Any],
        to_pivot: Dict[str, Any],
        current_candles: List[Dict[str, Any]],
        fan_id: Optional[str] = None,
        priority_label: str = "Unknown"
    ) -> AngleFan:
        """
        Create an angle fan from two pivots using EXPLICIT ANGLE DIVISION.
        
        Per User Request:
        - Measure the specific angle θ formed by the pivot pair (in data units)
        - θ = arctan(price_change / time_change)
        - Divide THAT specific angle by fractions (7/8, 3/4, 1/2, 1/4)
        - Sub-slopes = tan(θ * fraction)
        - Lines should be dotted.
        - 1/2 angle line should be double thickness.
        
        Args:
            from_pivot: Source pivot {time, price, bar_index, type}
            to_pivot: Destination pivot {time, price, bar_index, type}
            current_candles: All candles for time calculations
            priority_label: Label for fan priority (Primary, Secondary, etc.)
            
        Returns:
            AngleFan with all lines calculated
        """
        import math
        
        if fan_id is None:
            fan_id = str(uuid.uuid4())[:8]
            
        lines = []
        
        # Extract pivot data
        # For the main angle line: use the actual pivot PRICE (high for highs, low for lows).
        # This is the fundamental Gann fan rule: main angle joins low of low pivot with high of high pivot.
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
            target_time = t1
            target_bar = to_pivot.get('bar_index', 0)
        else:
            # to_pivot is temporally first -> angles radiate FROM to_pivot
            origin_time = t1
            origin_price = p1
            origin_bar = to_pivot.get('bar_index', 0)
            target_time = t0
            target_bar = from_pivot.get('bar_index', 0)
        
        db = max(1, abs(target_bar - origin_bar))
        
        # --- FIXED SCALE RATIO LOGIC ---
        # To match the Manual Trend Angle tool, we must account for the 
        # "Price to Bar Ratio" (points per bar).
        # Default Ratio = 1.0 (User must lock chart scale to 1.0 to match)
        # For NSEI 4H: pass scale_ratio=22. For AAPL: pass scale_ratio=0.22.
        
        # Calculate Slope in "Price per Bar"
        target_price = p1 if t0 <= t1 else p0
        dp_from_origin = target_price - origin_price
        slope_per_bar = dp_from_origin / db
        
        # Apply Scale Ratio
        visual_slope = slope_per_bar / (scale_ratio if scale_ratio else 1.0)
        
        # Calculate Theta (Visual Angle at 1:1)
        theta_radians = math.atan(visual_slope)
        theta_deg = math.degrees(theta_radians)
        
        # DEBUG: Log scale ratio and angle calculation
        print(f"[AngleEngine] scale_ratio={scale_ratio}, slope_per_bar={slope_per_bar:.4f}, visual_slope={visual_slope:.4f}, theta={theta_deg:.2f} deg")
        
        # Helper to ensure finite float values for JSON
        def _safe_float(val, default=0.0):
            if not math.isfinite(val):
                return default
            # Clip extreme values to prevent overflow in frontend
            return max(-1e9, min(1e9, val))

        # Calculate Radius in Visual Units (Bars) based on PA segment
        # visual_height = price_change / scale_ratio
        # radius = sqrt(bars^2 + visual_height^2)
        visual_height_total = dp_from_origin / (scale_ratio if scale_ratio else 1.0)
        radius = math.hypot(db, visual_height_total)

        import datetime
        from collections import Counter

        # Use the correct market timezone for this symbol.
        # This is critical: without it, datetime.fromtimestamp() uses the
        # server's local timezone (e.g. IST), which corrupts slot detection
        # and future bar projection for US stocks like AAPL.
        market_tz = self.market_tz

        # Extract modal daily schedule from recent history to map perfect 1:1 visual bars
        # This prevents TradingView from squishing overnight gaps (e.g., treating 18 hrs as 18 bars)
        
        # --- EQUAL BAR SPAN (NO RADIUS) ---
        # Evaluate all lines at exactly x = db (target_bar).
        # This guarantees both start_time and end_time fall on real historical bars,
        # preventing TradingView from warping the slope due to weekend/overnight gaps.
        # We will use 'extendRight: True' in the frontend to infinitely project the rays.
        
        # 1. Main Angle Line
        main_dx_bars = db
        main_end_price = target_price
        main_end_time = target_time

        main_line = AngleLine(
            id=f"{fan_id}_main",
            start_time=origin_time,
            start_price=_safe_float(origin_price),
            end_time=int(main_end_time),
            end_price=_safe_float(main_end_price),
            color='#808080',  # Gray for full angle
            width=2,
            fraction=None,
            fan_id=fan_id,
            start_bar_index=float(origin_bar),
            end_bar_index=float(origin_bar + main_dx_bars)
        )
        lines.append(main_line)
        
        # Fractional angles per strategy
        angle_fractions = [7/8, 3/4, 1/2, 1/4]
        angle_colors = ['#2196F3', '#4CAF50', '#FF9800', '#F44336']
        
        for i, fraction in enumerate(angle_fractions):
            # Calculate Fractional Theta (Angle of the line in visual space)
            frac_theta = theta_radians * fraction
            
            # Evaluate exactly at x = db
            dx_bars = db
            dy_visual = db * math.tan(frac_theta)
            
            frac_end_price = origin_price + (dy_visual * scale_ratio)
            frac_end_time = target_time
            
            color = angle_colors[i] if i < len(angle_colors) else '#888888'
            
            # Thickness Rule: 1/2 angle line is double thickness
            line_width = self.fraction_line_width * 2 if fraction == 0.5 else self.fraction_line_width
            
            frac_line = AngleLine(
                id=f"{fan_id}_f{i}",
                start_time=origin_time,
                start_price=_safe_float(origin_price),
                end_time=int(frac_end_time),
                end_price=_safe_float(frac_end_price),
                color=color,
                width=line_width,
                fraction=fraction,
                fan_id=fan_id,
                start_bar_index=float(origin_bar),
                end_bar_index=float(origin_bar + dx_bars)
            )
            lines.append(frac_line)
            
        # --- HORIZONTAL TARGET (1/2 Angle Intersection) ---
        # The horizontal target originates where the 1/2 fractional line intersects
        # the vertical time axis of the ANCHOR pivot.
        
        # 1. Determine intersection coordinates (Y intercept)
        db_anchor = abs(target_bar - origin_bar) # distance to anchor
        frac_theta_half = theta_radians * 0.5    # 1/2 Angle
        
        # Calculate visual height at anchor intersection
        y_visual_intercept = db_anchor * math.tan(frac_theta_half)
        intercept_price = origin_price + (y_visual_intercept * scale_ratio)
        intercept_time = self._get_time_for_bar_index(origin_bar + db_anchor, current_candles) # This is strictly the Anchor's Time
        
        # 2. Determine end coordinates (Circle Edge)
        # Using Pythagoras: x^2 + y^2 = r^2 -> x = sqrt(r^2 - y^2)
        # We must clamp y_visual_intercept to radius to prevent domain errors
        clamped_y_visual = min(y_visual_intercept, radius)
        
        # Calculate horizontal distance from origin to circle edge at this Y height
        x_visual_edge = math.sqrt(max(0, radius**2 - clamped_y_visual**2))
        end_edge_time = self._get_time_for_bar_index(origin_bar + x_visual_edge, current_candles)
        
        # Only draw if the intersection point is actually BEFORE the circle edge,
        # otherwise the horizontal line would have negative/zero length.
        if x_visual_edge > db_anchor:
            horizontal_line = AngleLine(
                id=f"{fan_id}_htarget",
                start_time=int(intercept_time),
                start_price=_safe_float(intercept_price),
                end_time=int(end_edge_time),
                end_price=_safe_float(intercept_price), # Perfectly flat
                color='#FFFFFF', # White Dotted per screenshot
                width=1,
                fraction=None,
                fan_id=fan_id,
                start_bar_index=float(origin_bar + db_anchor),
                end_bar_index=float(origin_bar + x_visual_edge)
            )
            # We must explicitly tag this inside angular_coverage_study.py or StudyDrawingUtils.js
            # to remain dotted if we want 'options.linestyle: 1', but passing through standard AngleLine
            # it will adopt the trend_line shape. We will handle styling overrides in fan_to_drawing_commands.
            lines.append(horizontal_line)
        fan = AngleFan(
            id=fan_id,
            from_pivot=from_pivot,
            to_pivot=to_pivot,
            lines=lines,
            is_completed=False,
            priority_label=priority_label
        )
        
        # Track active fan
        self.active_fans[fan_id] = fan
        
        print(f"--- [AngleEngine] Fan Created: {fan_id} ---")
        print(f"  Origin: Bar {origin_bar}, Time {origin_time}, Price {origin_price}")
        print(f"  Target: Bar {target_bar}, Time {t1 if t0 <= t1 else t0}, Price {target_price}")
        print(f"  Delta: db={db}, dp_origin={dp_from_origin:.2f}")
        print(f"  Scale Params: Ratio={scale_ratio}, Radius={radius:.2f} bars, Slope/Bar={slope_per_bar:.4f}")
        
        for line in lines:
            if line.fraction is not None:
                print(f"  Line {line.fraction}: EndBar={line.end_time} (approx), EndPrice={line.end_price:.2f}")
                # Note: line.end_time is the estimated timestamp, not bar index. 
                # We can't log the exact bar index here unless we stored it in AngleLine, 
                # but the timestamp is what the frontend sees.

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
                    'linestyle': 1,  # 1 = Dotted. All lines dotted per screenshot.
                    'fanLabel': fan.priority_label,
                    'fanIdentity': fan.id.replace("Fan_", "").replace("_", "-"),
                    'extendLeft': False,
                    'extendRight': True  # Let TradingView handle the infinite visual extension
                }
            }
            commands.append(cmd)
        
        return commands
    
    def get_state(self) -> Dict[str, Any]:
        """Get engine state for serialization"""
        return {
            'active_fan_order': list(self.active_fans.keys()),
            'active_fans': {
                fan_id: {
                    'id': fan.id,
                    'from_pivot': fan.from_pivot,
                    'to_pivot': fan.to_pivot,
                    'is_completed': fan.is_completed,
                    'priority_label': fan.priority_label,
                    'anchor_type': fan.anchor_type,
                    'intersections': [event.to_dict() for event in fan.intersections] if hasattr(fan, 'intersections') else [],
                    'label_ids': fan.label_ids if hasattr(fan, 'label_ids') else [],
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
                            'fan_id': line.fan_id,
                            'start_bar_index': line.start_bar_index,
                            'end_bar_index': line.end_bar_index
                        }
                        for line in fan.lines
                    ]
                }
                for fan_id, fan in self.active_fans.items()
            }
        }
    
    def restore_state(self, state: Dict[str, Any]):
        """Restore engine state from serialized form"""
        from .intersection_detector import IntersectionEvent
        self.active_fans = {}
        
        fan_order = state.get('active_fan_order', list(state.get('active_fans', {}).keys()))
        
        for fan_id in fan_order:
            if fan_id not in state.get('active_fans', {}):
                continue
            fan_data = state['active_fans'][fan_id]
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
                    fan_id=line['fan_id'],
                    start_bar_index=line.get('start_bar_index', 0.0),
                    end_bar_index=line.get('end_bar_index', 0.0)
                )
                for line in fan_data.get('lines', [])
            ]
            
            intersections_data = fan_data.get('intersections', [])
            intersections = [IntersectionEvent(**ev) for ev in intersections_data]
            
            fan = AngleFan(
                id=fan_data['id'],
                from_pivot=fan_data['from_pivot'],
                to_pivot=fan_data['to_pivot'],
                lines=lines,
                is_completed=fan_data.get('is_completed', False),
                priority_label=fan_data.get('priority_label', 'Unknown'),
                anchor_type=fan_data.get('anchor_type', ''),
                intersections=intersections,
                label_ids=fan_data.get('label_ids', [])
            )
            self.active_fans[fan_id] = fan

