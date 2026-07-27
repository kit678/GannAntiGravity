import json
import os
import re
from datetime import datetime, timezone


def extract_fan_identity(fan_label: str) -> str:
    if not fan_label:
        return ""
    label = str(fan_label).strip()
    match = re.search(r'([HL]\d+-[HL]\d+)', label)
    return match.group(1) if match else label


def parse_detailed_log_time(time_str: str) -> int:
    if not time_str:
        return 0

    raw = str(time_str).strip()
    if not raw:
        return 0

    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        pass

    try:
        clean = raw.replace(',', '')
        dt = datetime.strptime(clean, '%m/%d/%Y %I:%M:%S %p')
        dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (ValueError, OSError):
        return 0


def build_hypothesis_lookup(run_dir: str) -> dict:
    hypo_path = os.path.join(run_dir, "hypothesis_events.json")
    if not os.path.exists(hypo_path):
        return {}

    with open(hypo_path, "r", encoding="utf-8") as f:
        hypo_data = json.load(f)

    lookup = {}
    events = hypo_data.get("events", []) or hypo_data.get("live_events", []) or []
    for evt in events:
        ts = evt.get("timestamp", 0)
        fi = evt.get("fan_identity") or evt.get("fan_display") or ""
        frac = str(evt.get("fraction", ""))
        key = (ts, fi, frac)
        if key not in lookup:
            lookup[key] = evt

    return lookup


def enrich_detailed_log(detailed_log: list, run_dir: str) -> list:
    lookup = build_hypothesis_lookup(run_dir)
    enriched = []

    type_display = {
        "SUPPORT_BOUNCE": "Support Bounce",
        "RESISTANCE_REJECTION": "Resistance Rejection",
        "SUPPORT_TEST": "Support Test",
        "RESISTANCE_TEST": "Resistance Test",
        "BREACH_CONFIRMED": "Breach Confirmed",
        "TARGET_HIT": "Target Hit",
        "TARGET_FAILED": "Target Failed",
        "FAN_VALIDATED": "Fan Validated",
    }

    for i, entry in enumerate(detailed_log):
        ts = parse_detailed_log_time(entry.get("time", ""))
        fan_id = extract_fan_identity(entry.get("fan", ""))
        frac = str(entry.get("fraction", ""))

        match = lookup.get((ts, fan_id, frac))
        if not match:
            for (k_ts, k_fi, k_fr), value in lookup.items():
                if k_fi == fan_id and k_fr == frac:
                    match = value
                    break

        enriched_entry = {
            "event_id": i + 1,
            "event_type": entry.get("type", ""),
            "time": entry.get("time", ""),
            "test_time": entry.get("test_time", ""),
            "fan": entry.get("fan", ""),
            "fraction": entry.get("fraction", ""),
            "type": entry.get("type", ""),
            "price": entry.get("price"),
            "is_retro": entry.get("is_retro", False),
            "outcome": entry.get("outcome"),
            "mfe": entry.get("mfe"),
            "mae": entry.get("mae"),
            "anchor_bar_index": entry.get("anchor_bar_index"),
            "scale_ratio": entry.get("scale_ratio"),
            "anchor_price": entry.get("anchor_price"),
            "details": entry.get("details", ""),
            "confirmation_details": entry.get("confirmation_details") or entry.get("details", ""),
            "entry_price": entry.get("entry_price"),
            "entry_time": entry.get("entry_time", ""),
            "exit_price": entry.get("exit_price"),
            "exit_time": entry.get("exit_time", ""),
            "exit_reason": entry.get("exit_reason"),
            "exit_label": entry.get("exit_label", ""),
            "net_pnl": entry.get("net_pnl"),
            "pnl_pct": entry.get("pnl_pct"),
            "bars_held": entry.get("bars_held"),
            "entry_side": entry.get("entry_side"),
            "event_type_display": type_display.get(entry.get("type", ""), entry.get("type", "")),
        }

        if match:
            enriched_entry["direction"] = match.get("direction")
            enriched_entry["fan_geometry"] = match.get("fan_geometry")
            enriched_entry["fan_identity"] = match.get("fan_identity") or fan_id
            enriched_entry["fan_display"] = match.get("fan_display") or entry.get("fan", "")
            enriched_entry["priority_label"] = match.get("priority_label", "")
            enriched_entry["description"] = match.get("description", "")
            enriched_entry["current_zone"] = match.get("current_zone")
            enriched_entry["bars_in_zone"] = match.get("bars_in_zone")
            enriched_entry["is_gap_cross"] = match.get("is_gap_cross", False)
            enriched_entry["anchor_type"] = match.get("anchor_type")
            enriched_entry["bar_index"] = match.get("bar_index")
            enriched_entry["timestamp"] = match.get("timestamp", ts)
        else:
            enriched_entry["timestamp"] = ts

        base_keys = set(enriched_entry.keys())
        for key, value in entry.items():
            if key not in base_keys and value is not None:
                enriched_entry[key] = value

        enriched.append(enriched_entry)

    return enriched
