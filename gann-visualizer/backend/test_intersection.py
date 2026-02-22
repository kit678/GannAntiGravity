import sys
import os

# Add backend to path
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.intersection_detector import IntersectionDetector, IntersectionEvent
from study_tool.angle_engine import AngleFan, AngleLine

def test():
    # Create mock Primary Fan
    p_fan = AngleFan(
        id="fan_primary",
        from_pivot={"time": 100, "price": 100},
        to_pivot={"time": 200, "price": 200},
        lines=[
            AngleLine(id="fan_primary_0.5", start_time=100, start_price=100, end_time=300, end_price=300, color="orange", width=1, fraction=0.5, fan_id="fan_primary")
        ],
        is_completed=False,
        priority_label="Primary"
    )

    # Create mock Secondary Fan
    s_fan = AngleFan(
        id="fan_secondary",
        from_pivot={"time": 120, "price": 120},
        to_pivot={"time": 200, "price": 200},
        lines=[
            AngleLine(id="fan_secondary_0.5", start_time=120, start_price=120, end_time=300, end_price=340, color="orange", width=1, fraction=0.5, fan_id="fan_secondary")
        ],
        is_completed=False,
        priority_label="Secondary"
    )

    detector = IntersectionDetector()

    # Candle that overlaps both lines
    active_fans = {"fan_primary": p_fan, "fan_secondary": s_fan}
    candle = {"time": 250, "high": 400, "low": 50, "close": 240}

    events = detector.detect(candle, active_fans, 25)
    
    print("Detected Events:")
    for e in events:
        print(f"- {e.priority_label} | {e.line_id} at price {e.price}")

if __name__ == "__main__":
    test()
