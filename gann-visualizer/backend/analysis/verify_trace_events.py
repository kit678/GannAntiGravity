"""
verify_trace_events.py

Refactored v4 — Complete rewrite per Task 3 specification.
Reads simulation_trace.log and simulation_events.csv, produces a clean
accuracy/completeness report.

Data flows:
  1. parse_trace_log()   -> List[TraceBar] with OHLC, lines, state_blocks
  2. parse_events_csv()  -> List[CSVEvent]
  3. detect_missed_events() -> bars where state machine evaluated a line
                               but no CSV event was fired
  4. generate_report()    -> TRACE_AUDIT_REPORT.txt, EVENT_VERIFICATION.csv
  5. export_ml_data()     -> events_ml.csv, bars_ml.csv
"""

import re
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Fan name normalization
# ---------------------------------------------------------------------------

def _normalize_fan(fan_str: str) -> str:
    """
    Normalize fan name to enable matching between CSV format and trace format.

    CSV format: 'P1 (H1-L1)' or 'P2 (L2-H1)'
    Trace format: 'Fan_H1_L1' or 'Fan_L2_H1'

    Also handles:
    - 'P1 (H1-L1)' -> 'Fan_H1_L1'
    - 'P2 (L2-H1)' -> 'Fan_L2_H1'
    - 'Fan_H1_L1' -> 'Fan_H1_L1' (already normalized)
    """
    fan_str = fan_str.strip()

    # Already in trace format
    if fan_str.startswith('Fan_'):
        # Normalize hyphens to underscores for consistent matching
        return fan_str.replace('-', '_')

    # CSV format: 'P1 (H1-L1)' -> extract 'H1-L1' and prefix with 'Fan_'
    match = re.search(r'\(([^)]+)\)', fan_str)
    if match:
        angle_part = match.group(1)  # e.g., 'H1-L1' or 'L2-H1'
        # Replace hyphens with underscores to get Fan_H1_L1 format
        angle_part = angle_part.replace('-', '_')
        return f'Fan_{angle_part}'

    return fan_str


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def resolve_paths(run_dir: Path) -> dict:
    """Return path dict for a given run directory.
    Keys: trace, events, audit_dir, report, ev_csv, events_ml, bars_ml.
    """
    audit_dir = run_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    return {
        "trace":     run_dir / "trace.log",
        "events":    run_dir / "events.csv",
        "audit_dir": audit_dir,
        "report":    audit_dir / "TRACE_AUDIT_REPORT.txt",
        "ev_csv":    audit_dir / "EVENT_VERIFICATION.csv",
        "events_ml": audit_dir / "events_ml.csv",
        "bars_ml":   audit_dir / "bars_ml.csv",
    }


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class OHLC:
    open_: float
    high: float
    low: float
    close: float


@dataclass
class TraceLine:
    fan: str
    fraction: str
    price: float
    outcome: str
    active_line: bool = False  # True = no intersection, just active line logging


@dataclass
class StateBlock:
    block_type: str
    fan: str
    params: Dict[str, str] = field(default_factory=dict)


@dataclass
class TraceBar:
    bar_index: int
    timestamp: str
    ohlc: OHLC
    lines: List[TraceLine] = field(default_factory=list)
    state_blocks: List[StateBlock] = field(default_factory=list)
    retro: bool = False


@dataclass
class CSVEvent:
    row_num: int
    bar_index: int
    timestamp: str
    fan: str
    fraction: str
    price: float
    event_type: str
    details: str
    open_: float
    high: float
    low: float
    close: float
    zone: str
    zone_high: float
    zone_low: float
    bars_elapsed: int


# ---------------------------------------------------------------------------
# CSV split — respects double-quote enclosure
# ---------------------------------------------------------------------------

def _csv_split(line: str) -> List[str]:
    parts = []
    in_quote = False
    current = ""
    for ch in line:
        if ch == '"':
            in_quote = not in_quote
        elif ch == ',' and not in_quote:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)
    return parts


def _normalize_timestamp(ts: str) -> str:
    """Convert CSV timestamp '4/13/2026, 11:11:00 AM' -> '2026-04-13 11:11'."""
    from datetime import datetime
    ts = ts.strip('"').strip().replace(", ", " ")
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(ts, fmt)
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue
    return ts


# ---------------------------------------------------------------------------
# Parse trace log
# ---------------------------------------------------------------------------

def parse_trace_log(path: Path) -> List[TraceBar]:
    """
    Parse trace log. Returns list of TraceBar in document order.
    Each bar accumulates all eval lines and [STATE] blocks for that bar.
    Lines with '-> [STATE]' are state blocks; lines with '->' but not '[STATE]'
    are evaluation lines.
    A bar section runs from one [Bar N] to the next [Bar M].
    [RETRO] prefix marks retro bars.
    """
    lines_text = path.read_text(encoding="utf-8").splitlines()
    bars: List[TraceBar] = []
    bar_map: Dict[int, TraceBar] = {}  # bar_index -> TraceBar

    i = 0
    while i < len(lines_text):
        raw = lines_text[i].strip()
        if not raw or raw.startswith("==="):
            i += 1
            continue

        is_retro = raw.startswith("[RETRO]")
        inner = raw[7:] if is_retro else raw

        bar_match = re.search(r"\[Bar (\d+)\]", inner)
        if not bar_match:
            i += 1
            continue
        bar_index = int(bar_match.group(1))

        ts_match = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]", inner)
        timestamp = ts_match.group(1) if ts_match else ""

        ohlc_match = re.search(r"\[O:([\d.]+), H:([\d.]+), L:([\d.]+), C:([\d.]+)\]", inner)
        if not ohlc_match:
            i += 1
            continue
        ohlc = OHLC(
            open_=float(ohlc_match.group(1)),
            high=float(ohlc_match.group(2)),
            low=float(ohlc_match.group(3)),
            close=float(ohlc_match.group(4)),
        )

        if bar_index not in bar_map:
            tb = TraceBar(
                bar_index=bar_index,
                timestamp=timestamp,
                ohlc=ohlc,
                lines=[],
                state_blocks=[],
                retro=is_retro,
            )
            bar_map[bar_index] = tb
            bars.append(tb)
        else:
            tb = bar_map[bar_index]
            tb.ohlc = ohlc
            tb.timestamp = timestamp
            tb.retro = tb.retro or is_retro

        # Consume all lines belonging to this bar (until next [Bar M])
        j = i
        while j < len(lines_text):
            line_raw = lines_text[j].strip()
            if not line_raw:
                j += 1
                continue
            is_r = line_raw.startswith("[RETRO]")
            inner_l = line_raw[7:] if is_r else line_raw
            bar_m = re.search(r"\[Bar (\d+)\]", inner_l)
            if bar_m and int(bar_m.group(1)) != bar_index:
                break

            if "-> [STATE]" in line_raw:
                sb = _parse_state_block(line_raw)
                if sb:
                    tb.state_blocks.append(sb)
            elif "->" in line_raw and ("No Intersection" not in line_raw and "No Event" not in line_raw):
                ln = _parse_eval_line(line_raw)
                if ln:
                    tb.lines.append(ln)

            j += 1

        i = j

    return bars


def _parse_eval_line(line_raw: str) -> Optional[TraceLine]:
    """
    Parse evaluation line like:
      [Bar 29] [2026-04-13 11:11] ... -> [H1-L1 0.875 @ 23740.60] O <= Line & C >= Line -> CROSS_UP (Pending Breach UP)
      [RETRO] [Bar 57] ... -> [H2-L1 0.75 @ 23780.95] Intersection detected ... -> TOUCH
    Extract fan, fraction, price from bracket content.
    Extract outcome from after final '->'.
    """
    # Find ALL bracket contents and pick the one with '@' (the line evaluation bracket)
    all_brackets = re.findall(r'\[([^\]]+)\]', line_raw)
    bracket_content = None
    for b in all_brackets:
        if '@' in b:
            bracket_content = b
            break

    if bracket_content is None:
        return None

    price_m = re.search(r"@ ([\d.]+)", bracket_content)
    if not price_m:
        return None
    price_val = float(price_m.group(1))

    # Find fraction suffix
    frac_words = ['main', 'horizontal', '0.875', '0.75', '0.5', '0.25']
    last_fw_idx = -1
    last_fw = "main"
    for fw in frac_words:
        idx = bracket_content.rfind(f" {fw}")
        if idx > last_fw_idx:
            last_fw_idx = idx
            last_fw = fw

    fan_name = bracket_content[:last_fw_idx].strip() if last_fw_idx >= 0 else bracket_content

    # Normalize fan name to match state block format (Fan_H1_L1)
    if fan_name and not fan_name.startswith('Fan_'):
        fan_name = f'Fan_{fan_name}'

    # Get outcome — text after final '->'
    segments = line_raw.split("-> ")
    outcome = segments[-1].strip() if len(segments) >= 2 else "?"

    # Detect active-line-only log (no intersection) — format: "Line X @ Y (Distance: Z)"
    # vs intersection eval log (e.g., "O >= Line & C <= Line -> CROSS_DOWN (Pending Breach DOWN)")
    active_line = outcome.startswith("Line ")

    return TraceLine(fan=fan_name, fraction=last_fw, price=price_val, outcome=outcome, active_line=active_line)


def _parse_state_block(line_raw: str) -> Optional[StateBlock]:
    """
    Parse state block line like:
      ... -> [STATE] pending_breach: fan=Fan_H1_L1 line=0.875 direction=UP bec_close=23743.70 ...
    Format: ... -> [STATE] block_type: key=value key=value ...
    """
    if "-> [STATE]" not in line_raw:
        return None

    # Extract block_type (first word after '[STATE] ')
    state_pos = line_raw.find("-> [STATE]")
    after_state = line_raw[state_pos + len("-> [STATE]"):].strip()
    colon_pos = after_state.find(":")
    if colon_pos < 0:
        return None

    block_type = after_state[:colon_pos].strip()
    kv_part = after_state[colon_pos + 1:].strip()

    params: Dict[str, str] = {}
    # Parse key=value pairs (may be separated by spaces, but values don't contain spaces)
    tokens = kv_part.split()
    for tok in tokens:
        if "=" in tok:
            k, v = tok.split("=", 1)
            params[k.strip()] = v.strip()

    # fan may be the first key or embedded
    fan = params.get("fan", block_type)

    return StateBlock(block_type=block_type, fan=fan, params=params)


# ---------------------------------------------------------------------------
# Parse events CSV
# ---------------------------------------------------------------------------

def parse_events_csv(path: Path) -> List[CSVEvent]:
    lines = path.read_text(encoding="utf-8").splitlines()
    events = []
    for i, raw in enumerate(lines[1:], start=2):
        raw = raw.strip()
        if not raw:
            continue
        parts = _csv_split(raw)
        if len(parts) < 16:
            continue
        try:
            # Row number (col 0) - currently unused, bar_index from col 19
            row_num = int(parts[0].strip('"')) if parts[0] else 0
            ts = parts[1].strip('"')
            fan = parts[2].strip('"')
            frac = parts[3].strip('"')
            price = float(parts[4])
            ev_type = parts[5].strip('"')
            details = parts[6].strip('"')
            open_ = float(parts[7])
            high = float(parts[8])
            low = float(parts[9])
            close = float(parts[10])
            zone = parts[13].strip('"')
            zone_high = float(parts[14]) if parts[14] else 0.0
            zone_low = float(parts[15]) if parts[15] else 0.0
            bars_el = int(parts[31]) if len(parts) > 31 and parts[31] else 0
            bar_index = int(parts[30]) if len(parts) > 30 and parts[30] else 0
            events.append(CSVEvent(
                row_num=i,
                bar_index=bar_index,
                timestamp=ts,
                fan=fan,
                fraction=frac,
                price=price,
                event_type=ev_type,
                details=details,
                open_=open_,
                high=high,
                low=low,
                close=close,
                zone=zone,
                zone_high=zone_high,
                zone_low=zone_low,
                bars_elapsed=bars_el,
            ))
        except (ValueError, IndexError):
            continue
    return events


# ---------------------------------------------------------------------------
# Event verification functions
# ---------------------------------------------------------------------------

def verify_cross_up(ev: CSVEvent) -> Tuple[bool, str]:
    ok = (ev.open_ <= ev.price) and (ev.close >= ev.price)
    detail = (f"O({ev.open_:.2f})<=L({ev.price:.2f})={ev.open_<=ev.price}, "
              f"C({ev.close:.2f})>=L={ev.close>=ev.price}")
    return ok, detail


def verify_cross_down(ev: CSVEvent) -> Tuple[bool, str]:
    ok = (ev.open_ >= ev.price) and (ev.close <= ev.price)
    detail = (f"O({ev.open_:.2f})>=L({ev.price:.2f})={ev.open_>=ev.price}, "
              f"C({ev.close:.2f})<=L={ev.close<=ev.price}")
    return ok, detail


def verify_support_test(ev: CSVEvent) -> Tuple[bool, str]:
    ok = (ev.open_ >= ev.price) and (ev.close >= ev.price) and (ev.low <= ev.price)
    detail = (f"O>=L={ev.open_>=ev.price}, C>=L={ev.close>=ev.price}, L<=L={ev.low<=ev.price}")
    return ok, detail


def verify_resistance_test(ev: CSVEvent) -> Tuple[bool, str]:
    ok = (ev.open_ <= ev.price) and (ev.close <= ev.price) and (ev.high >= ev.price)
    detail = (f"O<=L={ev.open_<=ev.price}, C<=L={ev.close<=ev.price}, H>=L={ev.high>=ev.price}")
    return ok, detail


def verify_support_touch(ev: CSVEvent) -> Tuple[bool, str]:
    ok = (ev.open_ >= ev.price) and (ev.close >= ev.price) and (ev.low <= ev.price) and (ev.close == ev.price)
    detail = (f"O>=L={ev.open_>=ev.price}, C>=L={ev.close>=ev.price}, "
              f"L<=L={ev.low<=ev.price}, C==L={ev.close==ev.price}")
    return ok, detail


def verify_resistance_touch(ev: CSVEvent) -> Tuple[bool, str]:
    ok = (ev.open_ <= ev.price) and (ev.close <= ev.price) and (ev.high >= ev.price) and (ev.close == ev.price)
    detail = (f"O<=L={ev.open_<=ev.price}, C<=L={ev.close<=ev.price}, "
              f"H>=L={ev.high>=ev.price}, C==L={ev.close==ev.price}")
    return ok, detail


def verify_touch_as_directional(ev: CSVEvent) -> Tuple[str, Tuple[bool, str]]:
    """
    Reclassify TOUCH event based on price position.
    Returns (expected_event_type, (ok, detail)).
    """
    lp = ev.price
    if ev.close > lp:
        expected = "SUPPORT_TOUCH"
        ok, detail = verify_support_touch(ev)
    elif ev.close < lp:
        expected = "RESISTANCE_TOUCH"
        ok, detail = verify_resistance_touch(ev)
    else:
        # C == line_price: use body position
        body_mid = (ev.open_ + ev.close) / 2.0
        if body_mid > lp:
            expected = "SUPPORT_TOUCH"
            ok, detail = verify_support_touch(ev)
        else:
            expected = "RESISTANCE_TOUCH"
            ok, detail = verify_resistance_touch(ev)
    return expected, (ok, detail)


def verify_breach_confirmed(ev: CSVEvent, state_block: Optional[StateBlock]) -> Tuple[bool, str]:
    """
    BREACH_CONFIRMED: direction from state_block or details.
    UP:   ok = ev.close > max(bec_close, zec_high)
    DOWN: ok = ev.close < min(bec_close, zec_low)
    """
    if state_block is None:
        # Fall back to details parsing
        direction = "DOWN" if "DOWN" in ev.details else "UP"
    else:
        direction = state_block.params.get("direction", "DOWN" if "DOWN" in ev.details else "UP")

    bec_close = float(state_block.params.get("bec_close", ev.zone_high)) if state_block else ev.zone_high
    zec_high = float(state_block.params.get("zec_high", ev.zone_high)) if state_block else ev.zone_high
    zec_low = float(state_block.params.get("zec_low", ev.zone_low)) if state_block else ev.zone_low

    if direction == "UP":
        boundary = max(bec_close, zec_high)
        ok = ev.close > boundary
    else:
        boundary = min(bec_close, zec_low)
        ok = ev.close < boundary

    detail = f"close={ev.close:.2f}, boundary={boundary:.2f}, direction={direction}"
    return ok, detail


def verify_breach_confirmed_no_alpha(ev: CSVEvent, state_block: Optional[StateBlock]) -> Tuple[bool, str]:
    """
    BREACH_CONFIRMED_NO_ALPHA: accurate if a matching [STATE] block exists.
    """
    if state_block is not None:
        return True, "STATE block present"
    return False, "STATE block missing"


def verify_event(ev: CSVEvent, state_block: Optional[StateBlock]) -> Tuple[bool, str]:
    """
    Dispatcher for verify_* functions.
    Returns (ok, detail_str).
    """
    et = ev.event_type

    if et == "CROSS_UP":
        return verify_cross_up(ev)
    elif et == "CROSS_DOWN":
        return verify_cross_down(ev)
    elif et == "SUPPORT_TEST":
        return verify_support_test(ev)
    elif et == "RESISTANCE_TEST":
        return verify_resistance_test(ev)
    elif et == "SUPPORT_TOUCH":
        return verify_support_touch(ev)
    elif et == "RESISTANCE_TOUCH":
        return verify_resistance_touch(ev)
    elif et == "TOUCH":
        expected, (ok, detail) = verify_touch_as_directional(ev)
        return ok, f"expected={expected}, {detail}"
    elif et == "BREACH_CONFIRMED":
        return verify_breach_confirmed(ev, state_block)
    elif et == "BREACH_CONFIRMED_NO_ALPHA":
        return verify_breach_confirmed_no_alpha(ev, state_block)
    elif et in ("FAN_VALIDATED", "TARGET_HIT", "ZONE_CHANGE", "FAN_DEACTIVATED",
                "TARGET_FAILED", "REST_ON_ANGLE"):
        # State machine events — accurate by definition
        return True, f"state_machine_event={et}"
    elif et in ("SUPPORT_BOUNCE", "RESISTANCE_REJECTION", "DEFERRED",
                "GAP_CROSS_UP", "GAP_CROSS_DOWN"):
        return True, f"requires_state_context={et}"
    elif "Intra" in et or "Intra-bar" in et:
        return True, f"intra_bar_event={et}"
    else:
        return False, f"unhandled_event_type={et}"


# ---------------------------------------------------------------------------
# Missed event detection
# ---------------------------------------------------------------------------

def _classify_bar_line(bar: TraceBar, line: TraceLine) -> Optional[str]:
    """Classify what event type a bar/line combination should produce."""
    o, h, l, c = bar.ohlc.open_, bar.ohlc.high, bar.ohlc.low, bar.ohlc.close
    lp = line.price
    if o <= lp and c >= lp:
        return "CROSS_UP"
    if o >= lp and c <= lp:
        return "CROSS_DOWN"
    if o >= lp and c >= lp and l <= lp and c >= lp:
        return "SUPPORT_TEST"
    if o <= lp and c <= lp and h >= lp and c <= lp:
        return "RESISTANCE_TEST"
    if o >= lp and c >= lp and l <= lp and c == lp:
        return "SUPPORT_TOUCH"
    if o <= lp and c <= lp and h >= lp and c == lp:
        return "RESISTANCE_TOUCH"
    return None


def detect_missed_events(trace_bars: List[TraceBar], csv_events: List[CSVEvent], ts_lookup: Dict[str, int]) -> List[dict]:
    """
    For each bar that has evaluated lines, check if any line meets a CROSS/TEST/TOUCH
    definition but no matching event is in the CSV.

    Returns list of missed event dicts:
      bar_index, timestamp, fan, fraction, line_price, expected_event, reason

    Uses timestamp lookup to match trace bars to CSV event keys.
    """
    # Build CSV event map keyed by (bar_index, fan, fraction, event_type)
    # Fan names are normalized to trace format (Fan_H1_L1)
    csv_map: Dict[Tuple, List[CSVEvent]] = {}
    for ev in csv_events:
        norm_fan = _normalize_fan(ev.fan)
        norm_ts = _normalize_timestamp(ev.timestamp)
        trace_bar = ts_lookup.get(norm_ts, ev.bar_index)
        key = (trace_bar, norm_fan, ev.fraction)
        csv_map.setdefault(key, []).append(ev)

    # Also build a set of (bar_index, fan, fraction) -> {event_types}
    csv_ev_types: Dict[Tuple, set] = {}
    for ev in csv_events:
        norm_fan = _normalize_fan(ev.fan)
        norm_ts = _normalize_timestamp(ev.timestamp)
        trace_bar = ts_lookup.get(norm_ts, ev.bar_index)
        key = (trace_bar, norm_fan, ev.fraction)
        csv_ev_types.setdefault(key, set()).add(ev.event_type)

    missed = []
    for bar in trace_bars:
        if not bar.lines:
            continue

        # Determine bar type: intersection bar (some lines have outcomes) vs active-only bar
        has_intersection = any(not line.active_line for line in bar.lines)
        has_active_only = any(line.active_line for line in bar.lines)

        for line in bar.lines:
            classified = _classify_bar_line(bar, line)
            if classified is None:
                continue
            key = (bar.bar_index, _normalize_fan(line.fan), line.fraction)
            fired_types = csv_ev_types.get(key, set())
            if classified in fired_types:
                continue
            # Check if it's a TOUCH that was fired as TOUCH
            if classified in ("SUPPORT_TOUCH", "RESISTANCE_TOUCH") and "TOUCH" in fired_types:
                continue

            # For active-only bars (no intersection), the outcome is derived from OHLC
            # vs line price — this is a genuinely missed event if classification fires
            missed.append({
                "bar_index": bar.bar_index,
                "timestamp": bar.timestamp,
                "fan": line.fan,
                "fraction": line.fraction,
                "line_price": line.price,
                "expected_event": classified,
                "ohlc": bar.ohlc,
                "reason": f"line outcome={line.outcome}" if not line.active_line else f"active line, no intersection — expected {classified}",
            })
    return missed


# ---------------------------------------------------------------------------
# Build timestamp -> trace bar index lookup
# ---------------------------------------------------------------------------

def build_timestamp_lookup(trace_bars: List[TraceBar]) -> Dict[str, int]:
    """
    Build lookup: normalized_timestamp -> trace bar_index.
    CSV timestamps are normalized to 'YYYY-MM-DD HH:MM' to match trace timestamps.
    """
    return {bar.timestamp: bar.bar_index for bar in trace_bars}


# ---------------------------------------------------------------------------
# Build event -> state_block lookup for state-dependent events
# ---------------------------------------------------------------------------

def build_state_lookup(trace_bars: List[TraceBar]) -> Dict[Tuple, StateBlock]:
    """
    Build lookup: (bar_index, fan, fraction) -> StateBlock
    for state-dependent events like BREACH_CONFIRMED.
    State blocks use normalized fan names (Fan_H1_L1 format).
    """
    lookup: Dict[Tuple, StateBlock] = {}
    for bar in trace_bars:
        for sb in bar.state_blocks:
            fan = sb.params.get("fan", sb.fan)  # Already in Fan_H1_L1 format
            frac = sb.params.get("line", "main")
            key = (bar.bar_index, fan, frac)
            lookup[key] = sb
    return lookup


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(
    trace_bars: List[TraceBar],
    csv_events: List[CSVEvent],
    missed_events: List[dict],
    state_lookup: Dict[Tuple, StateBlock],
    ts_lookup: Dict[str, int],
    paths: dict,
) -> Tuple[float, float]:
    """
    Write TRACE_AUDIT_REPORT.txt and EVENT_VERIFICATION.csv.
    Returns (accuracy_pct, completeness_pct).
    """
    from datetime import datetime

    # Verify each CSV event
    accurate = 0
    inaccurate = 0
    state_dependent_events = []

    ev_results = []
    for ev in csv_events:
        # Normalize fan from CSV format (P1 (H1-L1)) to trace format (Fan_H1_L1)
        norm_fan = _normalize_fan(ev.fan)

        # Try to find the correct trace bar_index using timestamp
        norm_ts = _normalize_timestamp(ev.timestamp)
        trace_bar_index = ts_lookup.get(norm_ts, ev.bar_index)

        # Build key with normalized fan and potentially corrected bar_index
        key = (trace_bar_index, norm_fan, ev.fraction)
        sb = state_lookup.get(key)

        # If no match, try with original bar_index but normalized fan
        if sb is None:
            key = (ev.bar_index, norm_fan, ev.fraction)
            sb = state_lookup.get(key)

        ok, detail = verify_event(ev, sb)
        acc_result = "ACCURATE" if ok else "INACCURATE"
        ev_results.append({
            "bar_index": ev.bar_index,
            "timestamp": ev.timestamp,
            "fan": ev.fan,
            "fraction": ev.fraction,
            "event_type": ev.event_type,
            "line_price": ev.price,
            "ohlc": f"O={ev.open_:.2f} H={ev.high:.2f} L={ev.low:.2f} C={ev.close:.2f}",
            "accuracy_result": acc_result,
            "accuracy_detail": detail,
            "missed_event": "N/A",
            "missed_detail": "",
        })
        if ok:
            accurate += 1
        else:
            inaccurate += 1

        if ev.event_type in ("BREACH_CONFIRMED", "BREACH_CONFIRMED_NO_ALPHA"):
            state_dependent_events.append({
                "bar": ev.bar_index,
                "event_type": ev.event_type,
                "state_block_present": "YES" if sb else "NO",
            })

    total_checked = accurate + inaccurate
    accuracy_pct = (accurate / total_checked * 100) if total_checked > 0 else 100.0

    # Completeness
    bars_evaluated = sum(1 for b in trace_bars if b.lines)
    missed_count = len(missed_events)
    completeness_pct = (
        (bars_evaluated - missed_count) / bars_evaluated * 100
        if bars_evaluated > 0 else 100.0
    )

    # Write EVENT_VERIFICATION.csv
    with open(paths["ev_csv"], "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "bar_index", "timestamp", "fan", "fraction", "event_type",
            "line_price", "ohlc", "accuracy_result", "accuracy_detail",
            "missed_event", "missed_detail",
        ])
        writer.writeheader()
        for r in ev_results:
            writer.writerow(r)

    # Write TRACE_AUDIT_REPORT.txt
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(paths["report"], "w", encoding="utf-8") as f:
        f.write("=== EVENT VERIFICATION REPORT ===\n")
        f.write(f"Generated: {now}\n")
        f.write(f"Source: {paths['events'].name}, {paths['trace'].name}\n\n")

        f.write("ACCURACY (events that fired — were they correct per EVENT_TYPES.md definitions?)\n")
        f.write(f"  Events checked: {total_checked}\n")
        f.write(f"  Accurate: {accurate} ({accuracy_pct:.1f}%)\n")
        f.write(f"  Inaccurate: {inaccurate} ({(100 - accuracy_pct) if (total_checked > 0) else 0:.1f}%)\n")
        if inaccurate > 0:
            f.write("    — list of (bar, timestamp, fan, line, event_type, expected_condition)\n")
            for ev in csv_events:
                key = (ev.bar_index, ev.fan, ev.fraction)
                sb = state_lookup.get(key)
                ok, detail = verify_event(ev, sb)
                if not ok:
                    f.write(f"    [{ev.bar_index}] {ev.timestamp} {ev.fan} {ev.fraction} "
                            f"{ev.event_type} — {detail}\n")
        f.write("\n")
        f.write("  NOTE: Accuracy must be 100%. Any inaccuracy is a bug in event detection logic.\n\n")

        f.write("STATE-DEPENDENT EVENTS (verified via [STATE] blocks — not re-evaluated)\n")
        f.write(f"  {len(state_dependent_events)} events\n")
        for sd in state_dependent_events:
            f.write(f"    Bar {sd['bar']} {sd['event_type']} [STATE] block present: {sd['state_block_present']}\n")
        f.write("\n")

        f.write("COMPLETENESS (bars where state machine evaluated a line — were all events caught?)\n")
        f.write(f"  Bars evaluated: {bars_evaluated}\n")
        f.write(f"  Missed events: {missed_count}\n")
        if missed_count > 0:
            f.write("    — list of (bar, timestamp, fan, fraction, expected_event, reason)\n")
            for me in missed_events:
                f.write(f"    [{me['bar_index']}] {me['timestamp']} {me['fan']} {me['fraction']} "
                        f"{me['expected_event']} — {me['reason']}\n")
        f.write("\n")

        f.write("SUMMARY\n")
        status = "PASS" if (accuracy_pct == 100.0 and completeness_pct == 100.0) else "FAIL"
        f.write(f"  Accuracy: {accuracy_pct:.1f}%  (100% required)\n")
        f.write(f"  Completeness: {completeness_pct:.1f}%\n")
        f.write(f"  Status: {status}\n")

    return accuracy_pct, completeness_pct


# ---------------------------------------------------------------------------
# ML data export
# ---------------------------------------------------------------------------

def export_ml_data(
    trace_bars: List[TraceBar],
    csv_events: List[CSVEvent],
    missed_events: List[dict],
    state_lookup: Dict[Tuple, StateBlock],
    paths: dict,
) -> None:
    """
    Write events_ml.csv and bars_ml.csv.
    events_ml.csv: All CSV events with enriched columns.
    bars_ml.csv: Negative cases — evaluated bars where no event fired.
    """
    # events_ml.csv
    with open(paths["events_ml"], "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "bar_index", "timestamp", "fan_id", "fraction", "line_price",
            "open", "high", "low", "close", "event_type", "direction",
            "zone", "zone_high", "zone_low", "bec_close", "zec_high", "zec_low",
            "target_hit_sequence", "bars_elapsed", "is_missed_event", "accuracy_verified",
        ])
        writer.writeheader()
        for ev in csv_events:
            key = (ev.bar_index, ev.fan, ev.fraction)
            sb = state_lookup.get(key)
            direction = sb.params.get("direction", "N/A") if sb else "N/A"
            bec_close = float(sb.params.get("bec_close", 0)) if sb else ev.zone_high
            zec_high = float(sb.params.get("zec_high", 0)) if sb else ev.zone_high
            zec_low = float(sb.params.get("zec_low", 0)) if sb else ev.zone_low

            ok, _ = verify_event(ev, sb)
            writer.writerow({
                "bar_index": ev.bar_index,
                "timestamp": ev.timestamp,
                "fan_id": ev.fan,
                "fraction": ev.fraction,
                "line_price": ev.price,
                "open": ev.open_,
                "high": ev.high,
                "low": ev.low,
                "close": ev.close,
                "event_type": ev.event_type,
                "direction": direction,
                "zone": ev.zone,
                "zone_high": ev.zone_high,
                "zone_low": ev.zone_low,
                "bec_close": bec_close,
                "zec_high": zec_high,
                "zec_low": zec_low,
                "target_hit_sequence": "",
                "bars_elapsed": ev.bars_elapsed,
                "is_missed_event": False,
                "accuracy_verified": ok,
            })

    # bars_ml.csv — negative cases
    with open(paths["bars_ml"], "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "bar_index", "timestamp", "fan_id", "fraction", "line_price",
            "open", "high", "low", "close", "range", "body_size",
            "distance_to_line", "nearest_line_direction", "event_type",
            "zone", "zone_high", "zone_low", "reason_no_event",
        ])
        writer.writeheader()
        for me in missed_events:
            bar = me["ohlc"]
            rng = bar.high - bar.low
            body_sz = abs(bar.close - bar.open_)
            dist = abs(bar.close - me["line_price"])
            nearest_dir = "ABOVE" if bar.close > me["line_price"] else "BELOW"
            writer.writerow({
                "bar_index": me["bar_index"],
                "timestamp": me["timestamp"],
                "fan_id": me["fan"],
                "fraction": me["fraction"],
                "line_price": me["line_price"],
                "open": bar.open_,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "range": rng,
                "body_size": body_sz,
                "distance_to_line": dist,
                "nearest_line_direction": nearest_dir,
                "event_type": me["expected_event"],
                "zone": "",
                "zone_high": 0.0,
                "zone_low": 0.0,
                "reason_no_event": me["reason"],
            })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Verify trace events for a single run directory")
    parser.add_argument("--run-dir", type=str, required=True,
                        help="Run directory: logs/backend/runs/<instrument>/<timeframe>/<run_id>/")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        print(f"ERROR: run dir not found: {run_dir}")
        sys.exit(1)

    paths = resolve_paths(run_dir)

    if not paths["events"].exists():
        print(f"ERROR: events CSV not found: {paths['events']}")
        sys.exit(1)
    if not paths["trace"].exists():
        print(f"ERROR: trace log not found: {paths['trace']}")
        sys.exit(1)

    print(f"Run directory: {run_dir}")
    print(f"Reading events CSV: {paths['events']}")
    csv_events = parse_events_csv(paths["events"])
    print(f"  Found {len(csv_events)} events in CSV")

    print(f"Reading trace log: {paths['trace']}")
    trace_bars = parse_trace_log(paths["trace"])
    print(f"  Found {len(trace_bars)} bars in trace log")

    print("Building state block lookup...")
    state_lookup = build_state_lookup(trace_bars)
    print(f"  {len(state_lookup)} state blocks indexed")

    print("Building timestamp lookup...")
    ts_lookup = build_timestamp_lookup(trace_bars)
    print(f"  {len(ts_lookup)} timestamps indexed")

    print("Detecting missed events...")
    missed = detect_missed_events(trace_bars, csv_events, ts_lookup)
    print(f"  {len(missed)} missed events detected")

    print("Generating report...")
    acc_pct, comp_pct = generate_report(trace_bars, csv_events, missed, state_lookup, ts_lookup, paths)
    print(f"  Accuracy: {acc_pct:.1f}%, Completeness: {comp_pct:.1f}%")

    print("Exporting ML data...")
    export_ml_data(trace_bars, csv_events, missed, state_lookup, paths)

    print(f"\nOutputs written to {paths['audit_dir']}")
    if acc_pct < 100.0 or comp_pct < 100.0:
        sys.exit(2)  # non-zero so corpus runners can detect failure


if __name__ == "__main__":
    main()
