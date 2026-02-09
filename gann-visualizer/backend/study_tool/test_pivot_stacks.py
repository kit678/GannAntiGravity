
import pytest
from study_tool.pivot_detector import Pivot
from study_tool.pivot_selector import PivotSelector

def test_pivot_stack_selection_bearish():
    # Setup: Bearish Context (Last pivot is High)
    # Price dropping from 100 -> 90 -> 80
    
    # History of Pivots (Oldest to Newest)
    # We want a Lower Low structure for Outer Stack
    # And Higher High structure for Inner Stack
    
    # Outer Structure (Lows): 50(A-2) -> 40(A-1) -> 30(A) -> ... Wait, Outer is Lows BEHIND the Structure High.
    # Inner Structure (Highs): 120(B) -> 110(C) -> 100(D: Last Pivot)
    # Anchor (Low): 60 (Before B?) Or 20 (Recent)?
    
    # Let's define a sequence:
    # Time 10: Low at 50 (Outer A)
    # Time 20: High at 120 (Peak B) - Deepest High
    # Time 30: Low at 60 (Intermediate Low)
    # Time 40: High at 110 (Peak C) - Lower High
    # Time 50: Low at 70 (Intermediate Low)
    # Time 60: High at 100 (Peak D - Last Pivot)
    
    # Wait, "Successively Higher Highs" means D < C < B. 
    # Yes, 100 < 110 < 120. This is a valid stack.
    
    # Anchor: We need a LOW. 
    # In Bearish context (Last=High), we look for an Anchor LOW.
    # The most recent Low is at Time 50 (Price 70).
    
    # Inputs
    pivots = [
        Pivot(10, 50.0, 10, 'low'),   # Outer A
        Pivot(20, 120.0, 20, 'high'), # Inner B
        Pivot(30, 60.0, 30, 'low'), 
        Pivot(40, 110.0, 40, 'high'), # Inner C
        Pivot(50, 70.0, 50, 'low'),   # Anchor X
        Pivot(60, 100.0, 60, 'high')  # Last Pivot D
    ]
    
    last_pivot = pivots[-1] # D
    current_price = 95.0
    current_time = 70
    
    stacks = PivotSelector.select_stacks(current_price, current_time, pivots, last_pivot)
    
    assert stacks is not None
    assert stacks.context == 'bearish'
    
    # Check Anchor
    assert stacks.anchor['time'] == 50
    assert stacks.anchor['price'] == 70.0
    
    # Check Inner Stack (Highs)
    # Should contain D(100), C(110), B(120)
    # Logic: Scan back from Anchor(70) -> Look for Highs
    # 1. Found High(110) at T40. Add. Max=110.
    # 2. Found High(120) at T20. 120 > 110. Add. Max=120.
    # Note: D(100) is AFTER the Anchor?
    # Wait. My manual test data has D(T60) AFTER Anchor(T50).
    # If D is AFTER Anchor, D cannot connect to Anchor?
    # Fan connects High -> Low. Time(High) < Time(Low).
    # If High is NEWER, we can't draw a fan to an OLDER Low?
    # Actually, we CAN. That's a "projection" backwards? No.
    
    # Standard Gann Fan: Origin is earlier.
    # So if Anchor is T50, we look for Highs BEFORE T50.
    # So High D(T60) is NOT in the stack for Anchor(T50)?
    # Correct. D needs a NEWER Low to connect to.
    
    # So Inner Stack should have C(110) and B(120).
    ids = [p['price'] for p in stacks.inner_stack]
    assert 110.0 in ids
    assert 120.0 in ids
    
    # If logic was correct, 100 should NOT be there
    assert 100.0 not in ids 
    
    # Check Outer Stack (Lows)
    # Starts from Deepest High (B at T20) -> looking back for Lows < Anchor?
    # No, Lows < Previous Low.
    # Look back from T20:
    # Found Low(50) at T10. 
    # Is 50 < Anchor(70)? Yes. Valid "Outer A".
    
    oids = [p['price'] for p in stacks.outer_stack]
    assert 50.0 in oids

def test_pivot_stack_bullish():
    # Bullish Context (Last is Low)
    # Highs need to be successively Higher? No, Outer uses that.
    # Inner (Lows) need to be successively Lower.
    
    # Time 10: High 150 (Outer A)
    # Time 20: Low 80 (Deep Low B)
    # Time 30: High 140 (Anchor X)
    # Time 40: Low 100 (Last Pivot D)
    
    # Anchor: High at T30.
    # Inner Stack (Lows BEFORE T30):
    # Found Low(80) at T20.
    # Stack = [80].
    
    pivots = [
        Pivot(10, 150.0, 10, 'high'),
        Pivot(20, 80.0, 20, 'low'),
        Pivot(30, 140.0, 30, 'high'), # Anchor
        Pivot(40, 100.0, 40, 'low')   # Last
    ]
    
    stacks = PivotSelector.select_stacks(105.0, 50, pivots, pivots[-1])
    
    assert stacks.context == 'bullish'
    assert stacks.anchor['price'] == 140.0
    
    # Inner Stack
    # Lows before T30
    # Found 80.
    iids = [p['price'] for p in stacks.inner_stack]
    assert 80.0 in iids
    
    # Outer Stack
    # Highs before T20 (Deep Low)
    # Found 150.
    # Is 150 > Anchor(140)? Yes.
    oids = [p['price'] for p in stacks.outer_stack]
    assert 150.0 in oids
