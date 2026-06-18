"""
Trace Miner — Parses simulation_trace.log into a structured event DataFrame.

Usage:
    from analysis.trace_miner import parse_trace
    events_df, candles_df, fan_line_catalog = parse_trace("logs/backend/simulation_trace.log")
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


def parse_trace(trace_path: str):
    """
    Parse the full simulation trace log.

    Args:
        trace_path: Path to simulation_trace.log

    Returns:
        events_df: DataFrame of deduplicated events
        candles_df: DataFrame of all bars with OHLC
        fan_line_catalog: dict of {fan_id: {bar_index: [(fraction, price), ...]}}
    """
    trace_path = Path(trace_path)
    if not trace_path.exists():
        raise FileNotFoundError(f"Trace log not found: {trace_path}")

    all_rows = []
    candles_rows = []
    seen_bars = set()
    fan_line_catalog = {}  # fan_id -> {bar_index: [(fraction, price), ...]}

    with open(trace_path, "r", encoding="utf-8") as f:
        for line in f:
            parsed = parse_line(line)
            if parsed is None:
                continue

            # Collect candle data (once per bar, from non-RETRO lines)
            if not parsed.get("is_retro") and parsed["bar_index"] not in seen_bars:
                seen_bars.add(parsed["bar_index"])
                candles_rows.append({
                    "bar_index": parsed["bar_index"],
                    "timestamp": parsed["timestamp"],
                    "open": parsed["open"],
                    "high": parsed["high"],
                    "low": parsed["low"],
                    "close": parsed["close"],
                })

            if parsed["type"] == "no_event":
                # Populate fan_line_catalog from no_event lines (all fans at this bar)
                bar_idx = parsed["bar_index"]
                for ln in parsed.get("active_lines", []):
                    fan_id = ln["fan_id"]
                    if fan_id not in fan_line_catalog:
                        fan_line_catalog[fan_id] = {}
                    if bar_idx not in fan_line_catalog[fan_id]:
                        fan_line_catalog[fan_id][bar_idx] = []
                    fan_line_catalog[fan_id][bar_idx].append(
                        (float(ln["line_fraction"]) if ln["line_fraction"] != "horizontal" else 0.0,
                         ln["line_price"])
                    )
                continue

            if parsed["type"] == "state":
                continue

            # It's an event
            row = {
                "bar_index": parsed["bar_index"],
                "timestamp": parsed["timestamp"],
                "open": parsed["open"],
                "high": parsed["high"],
                "low": parsed["low"],
                "close": parsed["close"],
                "candle_pattern": parsed["candle_pattern"],
                "is_retro": parsed["is_retro"],
                "fan_id": parsed.get("fan_id", ""),
                "line_fraction": parsed.get("line_fraction", ""),
                "line_price": parsed.get("line_price", 0.0),
                "event_type": parsed.get("event_type", "UNKNOWN"),
                "event_detail": parsed.get("event_detail", ""),
                "distance": parsed.get("distance"),
                "rest_count": parsed.get("rest_count"),
            }
            all_rows.append(row)

            # Populate fan_line_catalog from event lines (single fan at this bar)
            fan_id = parsed.get("fan_id", "")
            if fan_id:
                bar_idx = parsed["bar_index"]
                if fan_id not in fan_line_catalog:
                    fan_line_catalog[fan_id] = {}
                if bar_idx not in fan_line_catalog[fan_id]:
                    fan_line_catalog[fan_id][bar_idx] = []
                frac_val = float(parsed["line_fraction"]) if parsed.get("line_fraction") != "horizontal" else 0.0
                price_val = parsed.get("line_price", 0.0)
                # Only add if not already present (avoid duplicates from no_event + event at same bar)
                existing = fan_line_catalog[fan_id][bar_idx]
                if not any(abs(f - frac_val) < 0.001 and abs(p - price_val) < 0.01 for f, p in existing):
                    fan_line_catalog[fan_id][bar_idx].append((frac_val, price_val))

    # Sort line fractions ascending within each bar for each fan
    for fan_id in fan_line_catalog:
        for bar_idx in fan_line_catalog[fan_id]:
            fan_line_catalog[fan_id][bar_idx].sort(key=lambda x: x[0])

    if not all_rows:
        raise ValueError("No events found in trace log")

    events_df = pd.DataFrame(all_rows)

    # Deduplicate: group by (bar_index, fan_id, line_fraction, event_type)
    # Prefer non-RETRO; keep RETRO only if no non-RETRO exists
    events_df["_key"] = (
        events_df["bar_index"].astype(str) + "|" +
        events_df["fan_id"] + "|" +
        events_df["line_fraction"].astype(str) + "|" +
        events_df["event_type"]
    )
    events_df["_sort"] = events_df["is_retro"].astype(int)
    events_df = events_df.sort_values("_sort").drop_duplicates(subset="_key", keep="first")
    events_df = events_df.drop(columns=["_key", "_sort"])
    events_df = events_df.sort_values("bar_index").reset_index(drop=True)

    candles_df = pd.DataFrame(candles_rows).sort_values("bar_index").reset_index(drop=True)

    return events_df, candles_df, fan_line_catalog


def build_sequences(events_df: pd.DataFrame) -> dict:
    """
    Group events by (fan_id, line_fraction) into ordered event sequences.
    
    Returns:
        dict of {(fan_id, line_fraction): list of event_type strings in bar_index order}
    """
    sequences = {}
    grouped = events_df.groupby(["fan_id", "line_fraction"])
    for (fan, frac), group in grouped:
        group = group.sort_values("bar_index")
        seq = group["event_type"].tolist()
        sequences[(fan, frac)] = seq
    return sequences


def build_fan_sequences(events_df: pd.DataFrame) -> dict:
    """
    Group events by fan_id only into ordered sequences with full event data.

    Unlike build_sequences() which groups by (fan_id, line_fraction), this groups
    by fan_id alone — so events at different line fractions on the same fan are
    part of the same sequence. Used for cross-line 2-event sequence mining.

    Returns:
        dict of {fan_id: [list of event dicts sorted by bar_index]}
        Each event dict has: bar_index, event_type, line_fraction, candle_pattern,
                              is_retro, open, high, low, close
    """
    non_retro = events_df[~events_df["is_retro"]]
    sequences = {}

    for fan_id, group in non_retro.groupby("fan_id"):
        group = group.sort_values("bar_index")
        seq = group[["bar_index", "event_type", "line_fraction", "candle_pattern",
                      "is_retro", "open", "high", "low", "close"]].to_dict("records")
        sequences[fan_id] = seq

    return sequences


def verify_parser(events_df: pd.DataFrame, candles_df: pd.DataFrame, trace_path: str) -> dict:
    """
    Run verification checks on parsed data.
    
    Returns:
        dict with 'passed': bool and 'checks': list of check result dicts
    """
    checks = []

    # Check 1: Event count is non-zero
    n_events = len(events_df)
    checks.append({
        "name": "event_count",
        "passed": n_events > 0,
        "detail": f"Total events: {n_events}"
    })

    # Check 2: Event type distribution has expected types
    expected_types = {"SUPPORT_TEST", "RESISTANCE_TEST", "CROSS_UP", "CROSS_DOWN", "BREACH_CONFIRMED"}
    actual_types = set(events_df["event_type"].unique())
    missing = expected_types - actual_types
    checks.append({
        "name": "event_types",
        "passed": len(missing) == 0,
        "detail": f"Missing types: {missing}" if missing else f"Found all expected types. Actual: {sorted(actual_types)}"
    })

    # Check 3: Bar coverage — no large gaps
    bar_indices = sorted(events_df["bar_index"].unique())
    gaps = []
    for i in range(1, len(bar_indices)):
        gap = bar_indices[i] - bar_indices[i - 1]
        if gap > 5:
            gaps.append((bar_indices[i - 1], bar_indices[i], gap))
    checks.append({
        "name": "bar_coverage",
        "passed": True,  # Gaps are expected — events only fire when price interacts with lines
        "detail": f"Bar range: {bar_indices[0]}-{bar_indices[-1]}. Gaps > 5 bars: {len(gaps)}" if gaps else f"Bar range: {bar_indices[0]}-{bar_indices[-1]}. No large gaps."
    })

    # Check 4: Spot-check 5 random events against raw log
    import random
    raw_lines = {}
    with open(trace_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip() and not line.startswith("===") and not line.startswith("Event Type"):
                parsed = parse_line(line)
                if parsed and parsed["type"] == "event":
                    key = (parsed["bar_index"], parsed.get("event_type", ""))
                    if key not in raw_lines:
                        raw_lines[key] = line.strip()

    sample_n = min(5, n_events)
    sample = events_df.sample(n=sample_n, random_state=42)
    spot_checks = []
    for _, row in sample.iterrows():
        key = (row["bar_index"], row["event_type"])
        raw = raw_lines.get(key, "NOT FOUND")
        spot_checks.append({
            "bar_index": row["bar_index"],
            "event_type": row["event_type"],
            "fan_id": row["fan_id"],
            "line_fraction": row["line_fraction"],
            "found_in_raw": raw != "NOT FOUND",
            "raw_line": raw[:120] + "..." if len(raw) > 120 else raw,
        })
    all_found = all(sc["found_in_raw"] for sc in spot_checks)
    checks.append({
        "name": "spot_check",
        "passed": all_found,
        "detail": f"{sum(1 for sc in spot_checks if sc['found_in_raw'])}/{len(spot_checks)} spot-checks found in raw log"
    })

    # Check 5: Forward return sanity for 5 events
    if "fwd_mfe_10" in events_df.columns and len(events_df) >= 5:
        sample5 = events_df.dropna(subset=["fwd_mfe_10"]).sample(n=min(5, n_events), random_state=99)
        sanity_pass = 0
        for _, row in sample5.iterrows():
            expected_mfe = row["fwd_mfe_10"]
            if not np.isnan(expected_mfe):
                direction = get_event_direction(row)
                candle_window = candles_df[
                    (candles_df["bar_index"] > row["bar_index"]) &
                    (candles_df["bar_index"] <= row["bar_index"] + 10)
                ]
                if not candle_window.empty:
                    if direction == "UP":
                        manual_mfe = (candle_window["high"].max() - row["close"]) / row["close"] * 100
                    else:
                        manual_mfe = (row["close"] - candle_window["low"].min()) / row["close"] * 100
                    if abs(manual_mfe - expected_mfe) < 0.02:
                        sanity_pass += 1
        checks.append({
            "name": "fwd_return_sanity",
            "passed": sanity_pass >= len(sample5) * 0.8,
            "detail": f"{sanity_pass}/{len(sample5)} manual computations match (within 0.02%)"
        })
    else:
        checks.append({
            "name": "fwd_return_sanity",
            "passed": False,
            "detail": "Enrichment not yet run or insufficient data"
        })

    all_passed = all(c["passed"] for c in checks)
    return {"passed": all_passed, "checks": checks}


# Direction mapping: which event types imply UP vs DOWN expectation
UP_EVENTS = {"CROSS_UP", "SUPPORT_TEST", "SUPPORT_BOUNCE", "TARGET_HIT"}
DOWN_EVENTS = {"CROSS_DOWN", "RESISTANCE_TEST", "RESISTANCE_REJECTION", "GAP_CROSS_DOWN"}


def get_event_direction(row: pd.Series) -> str:
    """Return 'UP', 'DOWN', or 'NEUTRAL' for an event."""
    et = row["event_type"]
    if et in UP_EVENTS:
        return "UP"
    if et in DOWN_EVENTS:
        return "DOWN"
    if et in ("BREACH_CONFIRMED", "BREACH_CONFIRMED_NO_ALPHA"):
        detail = str(row.get("event_detail", ""))
        if "UP" in detail:
            return "UP"
        elif "DOWN" in detail:
            return "DOWN"
    return "NEUTRAL"


def enrich_forward_returns(events_df: pd.DataFrame, candles_df: pd.DataFrame, horizons: list = None):
    """
    Compute forward MFE, MAE, and win metrics for each event.
    
    Modifies events_df in place, adding columns:
      fwd_mfe_5, fwd_mae_5, fwd_mfe_10, fwd_mae_10, fwd_mfe_20, fwd_mae_20, fwd_mfe_50, fwd_mae_50
      fwd_win_5, fwd_win_10, fwd_win_20, fwd_win_50
    """
    if horizons is None:
        horizons = [5, 10, 20, 50]

    candles = candles_df.set_index("bar_index")

    for h in horizons:
        events_df[f"fwd_mfe_{h}"] = np.nan
        events_df[f"fwd_mae_{h}"] = np.nan
        events_df[f"fwd_win_{h}"] = np.nan
    # Fix dtype for boolean columns
    for h in horizons:
        events_df[f"fwd_win_{h}"] = events_df[f"fwd_win_{h}"].astype(object)

    for idx, row in events_df.iterrows():
        bar_idx = row["bar_index"]
        direction = get_event_direction(row)
        if direction == "NEUTRAL":
            continue

        entry_price = row["close"]

        for h in horizons:
            end_idx = min(bar_idx + h, candles.index.max())
            if end_idx <= bar_idx:
                continue

            window = candles.loc[bar_idx + 1:end_idx]
            if isinstance(window, pd.Series):
                window = pd.DataFrame([window])
            if window.empty:
                continue

            if direction == "UP":
                best_price = window["high"].max()
                worst_price = window["low"].min()
                mfe = (best_price - entry_price) / entry_price * 100
                mae = (entry_price - worst_price) / entry_price * 100
            else:  # DOWN
                best_price = window["low"].min()
                worst_price = window["high"].max()
                mfe = (entry_price - best_price) / entry_price * 100
                mae = (worst_price - entry_price) / entry_price * 100

            events_df.at[idx, f"fwd_mfe_{h}"] = mfe
            events_df.at[idx, f"fwd_mae_{h}"] = mae

            safe_mae = max(mae, 0.1) if not np.isnan(mae) else 0.1
            win = mfe > 2 * safe_mae if not np.isnan(mfe) else False
            events_df.at[idx, f"fwd_win_{h}"] = win

    return events_df
