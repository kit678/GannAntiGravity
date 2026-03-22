import math
from typing import Dict, List, Any, Set, Tuple

class IntersectionEvent:
    def __init__(self, fan_id: str, line_id: str, priority_label: str, fraction: float, time: int, price: float, hit_type: str = 'cross'):
        self.fan_id = fan_id
        self.line_id = line_id
        self.priority_label = priority_label
        self.fraction = fraction
        self.time = time
        self.price = price
        self.hit_type = hit_type # 'cross', 'touch'
        
    def to_dict(self):
        return {
            'fan_id': self.fan_id,
            'line_id': self.line_id,
            'priority_label': self.priority_label,
            'fraction': self.fraction,
            'time': self.time,
            'price': self.price,
            'hit_type': self.hit_type
        }

class IntersectionDetector:
    def __init__(self):
        # Tracking set to prevent duplicate alerts for the same line on the same candle timestamp
        # Format: f"{fan_id}_{line_id}_{candle_time}"
        self._processed_hits: Set[str] = set()
        
    def detect(self, current_candle: Dict[str, Any], active_fans: Dict[str, Any], current_bar_idx: int) -> List[IntersectionEvent]:
        """
        Detects if the current candle intersects with any active line in any active fan.
        Lines are treated as RAYS — they extend infinitely beyond their drawn endpoint.
        """
        import datetime
        events = []
        c_time = int(current_candle['time'])
        c_high = float(current_candle['high'])
        c_low = float(current_candle['low'])
        c_close = float(current_candle.get('close', 0))
        
        ts_str = datetime.datetime.fromtimestamp(c_time).strftime('%Y-%m-%d %H:%M')
        
        fan_count = len(active_fans)
        total_lines = sum(len(fan.lines) for fan in active_fans.values())
        
        # Log summary every candle (compact)
        print(f"[IntDet] Bar {current_bar_idx} | {ts_str} | H={c_high:.2f} L={c_low:.2f} C={c_close:.2f} | Fans={fan_count} Lines={total_lines}")
        
        for fan_id, fan in active_fans.items():
            for line in fan.lines:
                frac_str = f"{line.fraction}" if line.fraction is not None else "main"
                
                # 1. Skip if candle is BEFORE the line's start
                if c_time < line.start_time:
                    continue
                    
                # Skip the origin candle itself
                if c_time == line.start_time:
                    continue
                
                # Dedup check
                tracking_key = f"{fan.id}_{line.id}_{c_time}"
                if tracking_key in self._processed_hits:
                    continue
                    
                # 2. Calculate line price at this bar using SLOPE EXTRAPOLATION
                bar_span = line.end_bar_index - line.start_bar_index
                if abs(bar_span) < 0.001:
                    print(f"  [{fan.priority_label}] {frac_str} SKIP degenerate (bar_span={bar_span:.4f})")
                    continue
                
                slope_per_bar = (line.end_price - line.start_price) / bar_span
                bars_from_origin = current_bar_idx - line.start_bar_index
                line_price_at_t = line.start_price + bars_from_origin * slope_per_bar
                
                # Compute gap (how far the line price is from candle range)
                if line_price_at_t > c_high:
                    gap = line_price_at_t - c_high
                    gap_dir = "ABOVE"
                elif line_price_at_t < c_low:
                    gap = c_low - line_price_at_t
                    gap_dir = "BELOW"
                else:
                    gap = 0
                    gap_dir = "HIT"
                
                # Log every fractional line check (verbose but essential for debugging)
                print(f"  [{fan.priority_label}] {frac_str}: lineP={line_price_at_t:.2f} | bars_from_origin={bars_from_origin:.1f} slope={slope_per_bar:.4f} | {gap_dir} gap={gap:.2f}")
                
                # 3. Collision Check (Bounding Box)
                if c_low <= line_price_at_t <= c_high:
                    hit_event = IntersectionEvent(
                        fan_id=fan.id,
                        line_id=line.id,
                        priority_label=fan.priority_label,
                        fraction=line.fraction,
                        time=c_time,
                        price=line_price_at_t,
                        hit_type='cross'
                    )
                    events.append(hit_event)
                    self._processed_hits.add(tracking_key)
                    print(f"    >>> HIT RECORDED: {fan.priority_label} frac={frac_str} @ {line_price_at_t:.2f}")
        
        if events:
            print(f"  [IntDet] Total hits this bar: {len(events)}")
                    
        return events
        
    def reset(self):
        self._processed_hits.clear()

    def get_state(self) -> Dict[str, Any]:
        return {
            'processed_hits': list(self._processed_hits)
        }
        
    def restore_state(self, state: Dict[str, Any]):
        if 'processed_hits' in state:
            self._processed_hits = set(state['processed_hits'])
    
    def retroactive_sweep(
        self, 
        fan: Any, 
        candles: List[Dict[str, Any]], 
        anchor_bar_idx: int, 
        current_bar_idx: int
    ) -> List[IntersectionEvent]:
        """
        Retroactively sweep through historical candles from anchor to current-1 bar
        to detect all intersections with a newly created fan's angle lines.
        
        This builds the correct historical context for the fan before live trading begins.
        
        Args:
            fan: The newly created fan object
            candles: List of all candles
            anchor_bar_idx: The bar index where the fan's anchor pivot is located
            current_bar_idx: The current bar index (fan was created at this bar)
            
        Returns:
            List of IntersectionEvents found in the historical range
        """
        import datetime
        events = []
        
        # Process all bars from anchor to current-1 (exclude current bar as it's already processed)
        for bar_idx in range(anchor_bar_idx, current_bar_idx):
            if bar_idx >= len(candles):
                break
                
            candle = candles[bar_idx]
            c_time = int(candle['time'])
            c_high = float(candle['high'])
            c_low = float(candle['low'])
            c_close = float(candle.get('close', 0))
            
            for line in fan.lines:
                frac_str = f"{line.fraction}" if line.fraction is not None else "main"
                
                # Skip if candle is BEFORE the line's start
                if c_time < line.start_time:
                    continue
                    
                # Skip the origin candle itself
                if c_time == line.start_time:
                    continue
                
                # Dedup check
                tracking_key = f"{fan.id}_{line.id}_{c_time}"
                if tracking_key in self._processed_hits:
                    continue
                    
                # Calculate line price at this bar using SLOPE EXTRAPOLATION
                bar_span = line.end_bar_index - line.start_bar_index
                if abs(bar_span) < 0.001:
                    continue
                
                slope_per_bar = (line.end_price - line.start_price) / bar_span
                bars_from_origin = bar_idx - line.start_bar_index
                line_price_at_t = line.start_price + bars_from_origin * slope_per_bar
                
                # Collision Check (Bounding Box)
                if c_low <= line_price_at_t <= c_high:
                    hit_event = IntersectionEvent(
                        fan_id=fan.id,
                        line_id=line.id,
                        priority_label=fan.priority_label,
                        fraction=line.fraction,
                        time=c_time,
                        price=line_price_at_t,
                        hit_type='cross'
                    )
                    events.append(hit_event)
                    self._processed_hits.add(tracking_key)
                    ts_str = datetime.datetime.fromtimestamp(c_time).strftime('%Y-%m-%d %H:%M')
                    print(f"  [RetroSweep] HIT: {fan.priority_label} frac={frac_str} @ {line_price_at_t:.2f} | Bar {bar_idx} ({ts_str})")
        
        if events:
            print(f"  [RetroSweep] Total historical hits for {fan.id}: {len(events)}")
        else:
            print(f"  [RetroSweep] No historical hits found for {fan.id}")
                    
        return events
