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
    r"^\[(RETRO)\]\s*"  # optional RETRO prefix (group 1)
    r"\[Bar\s+(\d+)\]\s*"  # bar_index (group 2)
    r"\[(.*?)\]\s*"  # timestamp (group 3)
    r"\[O:([\d.]+),\s*H:([\d.]+),\s*L:([\d.]+),\s*C:([\d.]+)\]"  # OHLC (groups 4-7)
)

CANDLE_PATTERN_RE = re.compile(r"\[Pattern:\s*(\w+)\]")

EVENT_LINE_RE = re.compile(
    r"\[(Fan_\w+)\s+([\d.]+|horizontal)\s*@\s*([\d.]+)\]\s*"  # fan line @ price
)

NO_EVENT_LINE_RE = re.compile(
    r"\[(Fan_\w+)\]\s+Line\s+([\d.]+|horizontal)\s*@\s*([\d.]+)"  # active line info
)

DISTANCE_RE = re.compile(r"\(Distance:\s*([\d.]+)\)")

STATE_LINE_RE = re.compile(
    r"\[STATE\]\s+(\w+):\s*(.*)"
)

REST_COUNT_RE = re.compile(r"rest count (?:incremented|cleared|reset) to (\d+)")
