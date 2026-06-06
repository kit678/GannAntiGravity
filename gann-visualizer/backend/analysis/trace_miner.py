"""
Trace Miner — Parses simulation_trace.log into a structured event DataFrame.

Usage:
    from analysis.trace_miner import parse_trace
    events_df, candles_df, line_prices = parse_trace("logs/backend/simulation_trace.log")
"""
import re
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime


# Regex patterns for parsing trace log lines
BAR_LINE_RE = re.compile(
    r"^(?:\[(RETRO)\]\s*)?"  # optional RETRO prefix (group 1)
    r"\[Bar\s+(\d+)\]\s*"  # bar_index (group 2)
    r"\[(.*?)\]\s*"  # timestamp (group 3)
    r"\[O:([\d.]+),\s*H:([\d.]+),\s*L:([\d.]+),\s*C:([\d.]+)\]"  # OHLC (groups 4-7)
)

CANDLE_PATTERN_RE = re.compile(r"\[Pattern:\s*(\w+)\]")

EVENT_LINE_RE = re.compile(
    r"\[([\w-]+)\s+([\d.]+|horizontal)\s*@\s*([\d.]+)\]\s*"  # fan line @ price
)

NO_EVENT_LINE_RE = re.compile(
    r"\[(Fan_\w+)\]\s+Line\s+([\d.]+|horizontal)\s*@\s*([\d.]+)"  # active line info
)

DISTANCE_RE = re.compile(r"\(Distance:\s*([\d.]+)\)")

STATE_LINE_RE = re.compile(
    r"\[STATE\]\s+(\w+):\s*(.*)"
)

REST_COUNT_RE = re.compile(r"rest count (?:incremented|cleared|reset) to (\d+)")


def parse_line(line: str) -> dict:
    """
    Parse a single trace log line into a structured dict.
    Returns None for lines that should be skipped entirely.
    Returns a dict with 'type' key: 'event', 'no_event', or 'state'.
    """
    line = line.strip()
    if not line or line.startswith("===") or line.startswith("Event Type"):
        return None

    # Extract bar-level info (OHLC, bar_index, timestamp, candle_pattern, is_retro)
    bar_match = BAR_LINE_RE.match(line)
    if not bar_match:
        return None

    is_retro = bar_match.group(1) is not None
    bar_index = int(bar_match.group(2))
    timestamp_str = bar_match.group(3)
    open_p = float(bar_match.group(4))
    high_p = float(bar_match.group(5))
    low_p = float(bar_match.group(6))
    close_p = float(bar_match.group(7))

    # Parse timestamp
    try:
        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M")
    except ValueError:
        timestamp = None

    # Candle pattern
    pattern_match = CANDLE_PATTERN_RE.search(line)
    candle_pattern = pattern_match.group(1) if pattern_match else ""

    result = {
        "bar_index": bar_index,
        "timestamp": timestamp,
        "open": open_p,
        "high": high_p,
        "low": low_p,
        "close": close_p,
        "candle_pattern": candle_pattern,
        "is_retro": is_retro,
    }

    # Determine line type
    if "No Intersection Detected" in line or "-> No Event" in line:
        result["type"] = "no_event"
        # Extract active line prices for this bar
        line_matches = NO_EVENT_LINE_RE.findall(line)
        lines = []
        for fan, frac, price_str in line_matches:
            dist_match = DISTANCE_RE.search(line)
            distance = float(dist_match.group(1)) if dist_match else None
            lines.append({
                "fan_id": fan,
                "line_fraction": frac,
                "line_price": float(price_str),
                "distance": distance,
            })
        result["active_lines"] = lines
        return result

    if "[STATE]" in line and "->" not in line:
        result["type"] = "state"
        state_match = STATE_LINE_RE.search(line)
        if state_match:
            result["state_type"] = state_match.group(1)
            result["state_detail"] = state_match.group(2)
        return result

    # It's an event line
    result["type"] = "event"

    # Extract event info
    event_match = EVENT_LINE_RE.search(line)
    if event_match:
        result["fan_id"] = event_match.group(1)
        result["line_fraction"] = event_match.group(2)
        result["line_price"] = float(event_match.group(3))
    else:
        result["fan_id"] = ""
        result["line_fraction"] = ""
        result["line_price"] = 0.0

    # Extract event type and detail from the "-> ... " portion
    arrow_idx = line.rfind("->")
    if arrow_idx >= 0:
        detail = line[arrow_idx + 2:].strip()
    else:
        detail = ""

    result["event_detail"] = detail

    # Classify event type
    event_type = "UNKNOWN"
    for et in ["BREACH_CONFIRMED_NO_ALPHA", "BREACH_CONFIRMED", "TARGET_HIT", "TARGET_FAILED",
               "RESISTANCE_REJECTION", "SUPPORT_BOUNCE",
               "RESISTANCE_TEST", "SUPPORT_TEST",
               "CROSS_UP", "CROSS_DOWN",
               "GAP_CROSS_UP", "GAP_CROSS_DOWN",
               "FAN_VALIDATED", "FAN_DEACTIVATED", "ZONE_CHANGE"]:
        if et in detail:
            event_type = et
            break

    result["event_type"] = event_type

    # Extract distance if present
    dist_match = DISTANCE_RE.search(line)
    result["distance"] = float(dist_match.group(1)) if dist_match else None

    # Extract rest count if present
    rest_match = REST_COUNT_RE.search(line)
    result["rest_count"] = int(rest_match.group(1)) if rest_match else None

    return result
