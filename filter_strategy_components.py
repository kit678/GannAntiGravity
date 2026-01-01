import json
import re

INPUT_FILE = "gann_library_raw.json"
OUTPUT_FILE = "strategy_params.json"

def filter_params():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    strategies = {
        "mechanical": {
            "time_periods": [],
            "stop_loss_rules": []
        },
        "geometry": {
            "angles": [],
            "support_resistance_concepts": []
        },
        "time": {
            "cycles": []
        }
    }

    print("Filtering components for strategy parameters...")

    for entry in data:
        text = entry.get("AlgorithmicDefinition", "").lower()
        ltype = entry.get("LogicType", "")

        # 1. Mechanical Rules (Look for numbers associated with days/weeks)
        if ltype == "MECHANICAL":
            # Extract "N-day" patterns
            days = re.findall(r"(\d+)\s*[- ]?days?", text)
            for d in days:
                if d not in strategies["mechanical"]["time_periods"]:
                    strategies["mechanical"]["time_periods"].append(int(d))
            
            if "stop loss" in text:
                strategies["mechanical"]["stop_loss_rules"].append(entry["AlgorithmicDefinition"])

        # 2. Geometry (Angles)
        if ltype == "GEOMETRY" or ltype == "VISUAL-LOGIC":
            # Extract angles
            angles = re.findall(r"(\d+)\s*degrees?", text)
            for a in angles:
                val = int(a)
                if val <= 360 and val not in strategies["geometry"]["angles"]:
                    strategies["geometry"]["angles"].append(val)

        # 3. Time Cycles
        if ltype == "TIME":
             # Extract cycles
            cycles = re.findall(r"(\d+)\s*(days?|weeks?|months?|years?)", text)
            for val, unit in cycles:
                item = f"{val} {unit}"
                if item not in strategies["time"]["cycles"]:
                    strategies["time"]["cycles"].append(item)

    # Clean and sort
    strategies["mechanical"]["time_periods"].sort()
    strategies["geometry"]["angles"].sort()
    
    # Save
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(strategies, f, indent=2)

    print(f"Extraction complete.")
    print(f"Found {len(strategies['mechanical']['time_periods'])} Mechanical time periods.")
    print(f"Found {len(strategies['geometry']['angles'])} Geometric angles.")
    print(f"Found {len(strategies['time']['cycles'])} Time cycles.")

if __name__ == "__main__":
    filter_params()
