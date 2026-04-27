# Event Verification Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance the trace log to emit structured [STATE] blocks for state-dependent events, then rewrite the verification script to produce a clean accuracy/completeness report plus ML training CSVs.

**Architecture:**
- Part 1: Add `[STATE]` block emission to the shared `_log_trace()` in `UnifiedStateMachine`. State context is accumulated per-bar in `_bar_state_events` and flushed at end of `process_bar()`. Path B BREACH_CONFIRMED_NO_ALPHA in `angular_coverage_study.py` writes a `[STATE]` block directly (no duplicate bar header).
- Part 2: Rewrite `verify_trace_events.py` to parse `[STATE]` blocks, verify OHLC-based events directly, detect missed events on evaluated bars, and emit `EVENT_VERIFICATION.csv`, `TRACE_AUDIT_REPORT.txt`, `events_ml.csv`, and `bars_ml.csv`.

**Tech Stack:** Python 3, standard library (csv, datetime, dataclasses, pathlib, re)

---

## Task 1: Add [STATE] block infrastructure to UnifiedStateMachine

**Files:**
- Modify: `gann-visualizer/backend/study_tool/unified_state_machine.py:1-130`

- [ ] **Step 1: Add `_bar_state_events` dict and emit methods to `__init__`**

Find the `__init__` method around line 22. After `self._pending_trace_evals` (line 76), add:

```python
# Per-bar state event blocks for [STATE] log emission
# Keyed by bar_index, accumulates state context for state-dependent events
self._bar_state_events: Dict[int, List[str]] = {}
```

After `append_trace_eval_for_bar` (around line 97), add these emit methods:

```python
def emit_pending_breach_state(self, bar_index: int, fan_id: str, fraction: str,
                              direction: str, bec_close: float, zec_high: float,
                              zec_low: float, pending_bar: int, outcome: str):
    """Accumulate a pending breach [STATE] block for a bar."""
    if bar_index not in self._bar_state_events:
        self._bar_state_events[bar_index] = []
    state_str = (
        f"[STATE] pending_breach: fan={fan_id} line={fraction} direction={direction} "
        f"bec_close={bec_close:.2f} zec_high={zec_high:.2f} zec_low={zec_low:.2f} "
        f"pending_bar={pending_bar} outcome={outcome}"
    )
    self._bar_state_events[bar_index].append(state_str)

def emit_pending_test_state(self, bar_index: int, fan_id: str, fraction: str,
                             direction: str, trigger_close: float, trigger_bar: int):
    """Accumulate a pending test [STATE] block for a bar."""
    if bar_index not in self._bar_state_events:
        self._bar_state_events[bar_index] = []
    state_str = (
        f"[STATE] pending_test: fan={fan_id} line={fraction} direction={direction} "
        f"trigger_close={trigger_close:.2f} trigger_bar={trigger_bar}"
    )
    self._bar_state_events[bar_index].append(state_str)

def emit_fan_validated_state(self, bar_index: int, fan_id: str, origin_bar: int, breach_close: float):
    """Accumulate a fan validated [STATE] block for a bar."""
    if bar_index not in self._bar_state_events:
        self._bar_state_events[bar_index] = []
    state_str = (
        f"[STATE] fan_validated: fan={fan_id} origin_bar={origin_bar} breach_close={breach_close:.2f}"
    )
    self._bar_state_events[bar_index].append(state_str)

def emit_fan_deactivated_state(self, bar_index: int, fan_id: str, reason: str):
    """Accumulate a fan deactivated [STATE] block for a bar."""
    if bar_index not in self._bar_state_events:
        self._bar_state_events[bar_index] = []
    state_str = f"[STATE] fan_deactivated: fan={fan_id} reason={reason}"
    self._bar_state_events[bar_index].append(state_str)

def emit_target_hit_state(self, bar_index: int, fan_id: str, fraction: str,
                           target_value: str, hit_bar: int):
    """Accumulate a target hit [STATE] block for a bar."""
    if bar_index not in self._bar_state_events:
        self._bar_state_events[bar_index] = []
    state_str = (
        f"[STATE] target_hit: fan={fan_id} line={fraction} target={target_value} hit_bar={hit_bar}"
    )
    self._bar_state_events[bar_index].append(state_str)
```

- [ ] **Step 2: Modify `_log_trace()` to flush `_bar_state_events`**

Find `_log_trace()` around line 99. After the line `all_evals = evaluations + pending` (line 114), add:

```python
# Flush any [STATE] blocks accumulated for this bar
state_blocks = self._bar_state_events.pop(bar_index, [])
```

Then in the `with open(...)` block, after the `for eval_str in all_evals:` loop (after line 121), add:

```python
        for state_block in state_blocks:
            f.write(f"{header} {pattern_str} -> {state_block}\n")
```

The `with open(...)` block should now look like:
```python
        with open(self.trace_log_path, 'a', encoding='utf-8') as f:
            if not all_evals:
                f.write(f"{header} {pattern_str} -> [No Intersection Detected] -> No Event\n")
                for state_block in state_blocks:
                    f.write(f"{header} {pattern_str} -> {state_block}\n")
            else:
                for eval_str in all_evals:
                    f.write(f"{header} {pattern_str} -> {eval_str}\n")
                for state_block in state_blocks:
                    f.write(f"{header} {pattern_str} -> {state_block}\n")
```

- [ ] **Step 3: Verify no existing call is broken**

Run: `python -m py_compile gann-visualizer/backend/study_tool/unified_state_machine.py`
Expected: No syntax errors

- [ ] **Step 4: Commit**

```bash
git add gann-visualizer/backend/study_tool/unified_state_machine.py
git commit -m "feat: add [STATE] block infrastructure to UnifiedStateMachine"
```

---

## Task 2: Wire [STATE] emissions to event creation points

**Files:**
- Modify: `gann-visualizer/backend/study_tool/unified_state_machine.py`
- Modify: `gann-visualizer/backend/study_tool/angular_coverage_study.py`

### 2A: BREACH_CONFIRMED (Path A — intra-bar multi-cross)

**Files:**
- Modify: `gann-visualizer/backend/study_tool/unified_state_machine.py:300-345`

- [ ] **Step 1: Find the Path A BREACH_CONFIRMED_NO_ALPHA code and add `emit_pending_breach_state` call**

In `unified_state_machine.py` around lines 308-318 (Path A, UP direction), find where `EventOutput` is appended for `BREACH_CONFIRMED_NO_ALPHA`. After the `results.append(...)` call, add:

```python
self.emit_pending_breach_state(
    bar_index=bar_index,
    fan_id=event.fan_id,
    fraction=frac_name,
    direction='UP',
    bec_close=c_close,
    zec_high=zec_high,
    zec_low=zec_low,
    pending_bar=bar_index,
    outcome='BREACH_CONFIRMED_NO_ALPHA'
)
```

Similarly for the DOWN path (around lines 327-337), add the same call with `direction='DOWN'`.

- [ ] **Step 2: Verify BREACH_CONFIRMED (non-NO_ALPHA) also emits state**

Find where BREACH_CONFIRMED is emitted (around lines 532-543 in `flush_deferred_breaches`). After the `results.append(...)` for BREACH_CONFIRMED, add:

```python
state = self.pending_breaches.get(state_key)
if state:
    self.emit_pending_breach_state(
        bar_index=bar_index,
        fan_id=state['fan_id'],
        fraction=state['fraction'],
        direction=direction.upper(),
        bec_close=state['bec_close'],
        zec_high=state['zec_high'],
        zec_low=state['zec_low'],
        pending_bar=state['first_breach_bar'],
        outcome='BREACH_CONFIRMED'
    )
```

- [ ] **Step 3: Verify DEFERRED events emit state**

Find where DEFERRED evaluation string is built (around line 399). After `self.deferred_breaches.append(...)`, add:

```python
self.emit_pending_breach_state(
    bar_index=bar_index,
    fan_id=fan_id,
    fraction=frac_name,
    direction='DOWN' if direction == 'down' else 'UP',
    bec_close=bec_close,
    zec_high=bec_close,  # For DEFERRED, use BEC as both
    zec_low=zec_low,
    pending_bar=bar_index,
    outcome='DEFERRED'
)
```

Note: The UP vs DOWN direction for DEFERRED should match the direction variable at that point (check it uses 'up'/'down' lowercase).

- [ ] **Step 4: Verify SUPPORT_BOUNCE and RESISTANCE_REJECTION emit state**

In the pending tests processing section (around lines 459-469 for SUPPORT_BOUNCE, similar for RESISTANCE_REJECTION), after the `results.append(...)` for the bounce/rejection event, add:

```python
self.emit_pending_test_state(
    bar_index=bar_index,
    fan_id=fan_id,
    fraction=fraction,
    direction='UP' if event_type == 'SUPPORT_BOUNCE' else 'DOWN',
    trigger_close=trigger_close,
    trigger_bar=state['test_bar']
)
```

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/study_tool/unified_state_machine.py
git commit -m "feat: wire [STATE] emissions to BREACH_CONFIRMED, DEFERRED, BOUNCE/REJECTION events"
```

### 2B: FAN_VALIDATED, FAN_DEACTIVATED, TARGET_HIT

**Files:**
- Modify: `gann-visualizer/backend/study_tool/angular_coverage_study.py`

- [ ] **Step 1: Find FAN_VALIDATED emission and add state emit**

Search for where `EventType.FAN_VALIDATED` is logged in `angular_coverage_study.py`. Around line 1065-1090, find the code that calls `self.event_logger.log_event(..., EventType.FAN_VALIDATED, ...)`. After that call, add:

```python
self.state_machine.emit_fan_validated_state(
    bar_index=bar_index,
    fan_id=fan_id,
    origin_bar=bar_index,
    breach_close=c_close
)
```

- [ ] **Step 2: Find FAN_DEACTIVATED emission and add state emit**

Search for where `EventType.FAN_DEACTIVATED` is logged. Find where `_sync_fans()` deactivates fans and emits the event. After `self.event_logger.log_event(..., EventType.FAN_DEACTIVATED, ...)`, add:

```python
self.state_machine.emit_fan_deactivated_state(
    bar_index=bar_index,
    fan_id=fan_id,
    reason='INVALIDATED'  # or 'COMPLETED' based on context
)
```

- [ ] **Step 3: Find TARGET_HIT emission and add state emit**

Search for where `EventType.TARGET_HIT` is logged in `angular_coverage_study.py`. After the `self.event_logger.log_event(..., EventType.TARGET_HIT, ...)` call, add:

```python
self.state_machine.emit_target_hit_state(
    bar_index=bar_index,
    fan_id=fan_id,
    fraction=str(fraction) if fraction else 'main',
    target_value=str(fraction) if fraction else 'main',
    hit_bar=bar_index
)
```

- [ ] **Step 4: Handle Path B BREACH_CONFIRMED_NO_ALPHA**

Path B fires **after** `_log_trace(bar_index)` was already called for that bar. Calling `emit_pending_breach_state(bar_index, ...)` would create an orphan entry in `_bar_state_events[bar_index]` that only flushes with the *next* bar's trace, causing ordering issues.

Instead, write the `[STATE]` block directly to the trace file immediately (same pattern as the current direct write, but as a `[STATE]` block only):

Replace the current `with open(...)` block at line 1218 with:

```python
# Get the pending breach state that was stored when the breach was first deferred
prev_state_key = f"{fan_id}_{prev_line}"
state = self.state_machine.pending_breaches.get(prev_state_key, {})
bec = float(state.get('bec_close', c_close))
zec_h = float(state.get('zec_high', c_close))
zec_l = float(state.get('zec_low', c_close))

# Write [STATE] block directly to trace (no duplicate bar header)
# Bar's regular trace was already written by process_bar()
state_str = (
    f"[STATE] pending_breach: fan={fan_id} line={prev_line} direction={dir_str} "
    f"bec_close={bec:.2f} zec_high={zec_h:.2f} zec_low={zec_l:.2f} "
    f"pending_bar={pending_bar} outcome=BREACH_CONFIRMED_NO_ALPHA"
)
dt_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')
with open(self.state_machine.trace_log_path, 'a', encoding='utf-8') as f:
    f.write(f"[Bar {bar_index}] [{dt_str}] [O:{c_open:.2f}, H:{c_high:.2f}, L:{c_low:.2f}, C:{c_close:.2f}]  -> {state_str}\n")
```

Also remove the `trace_eval` variable and its usage since we're no longer writing a custom event string — the `[STATE]` block is sufficient for the verification script.

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/study_tool/angular_coverage_study.py
git commit -m "feat: wire [STATE] emissions for FAN_VALIDATED, FAN_DEACTIVATED, TARGET_HIT, Path B breach"
```

---

## Task 3: Rewrite the verification script

**Files:**
- Modify: `gann-visualizer/backend/analysis/verify_trace_events.py` (complete rewrite)
- Create: `gann-visualizer/backend/analysis/verify_trace_events.py` (the old file is replaced)

### 3A: Data structures and trace log parsing

**Files:**
- Modify/Create: `gann-visualizer/backend/analysis/verify_trace_events.py`

- [ ] **Step 1: Write the dataclasses**

```python
from dataclasses import dataclass, field
from typing import Optional, List, Dict

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

@dataclass
class StateBlock:
    """Parsed [STATE] block from trace log."""
    block_type: str          # 'pending_breach', 'pending_test', 'fan_validated', etc.
    fan: str
    params: Dict[str, str]   # all key=value pairs as strings

@dataclass
class TraceBar:
    bar_index: int
    timestamp: str
    ohlc: OHLC
    lines: List[TraceLine]   # all evaluation lines for this bar
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
```

- [ ] **Step 2: Write `parse_trace_log()`**

The function parses the trace log returning `Dict[int, TraceBar]`. Key parsing rules:
- Lines starting with `===` or empty are skipped
- `[RETRO]` prefix marks retro bars
- `[Bar N]` and `[TIMESTAMP]` and `[O:H:L:C]` are extracted from the header
- Lines containing `->` are evaluation lines: parse `fan fraction @ price` before `->` and outcome after
- Lines containing `[STATE]` are state blocks: parse block_type (first word after `[STATE]`) and all `key=value` pairs

```python
def parse_trace_log(path: Path) -> Dict[int, TraceBar]:
    lines = path.read_text(encoding='utf-8').splitlines()
    bars: Dict[int, TraceBar] = {}
    i = 0
    while i < len(lines):
        raw = lines[i].strip()
        if not raw or raw.startswith('==='):
            i += 1
            continue

        is_retro = raw.startswith('[RETRO]')
        inner = raw[7:] if is_retro else raw

        bar_match = re.search(r'\[Bar (\d+)\]', inner)
        if not bar_match:
            i += 1
            continue
        bar_index = int(bar_match.group(1))

        ts_match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]', inner)
        timestamp = ts_match.group(1) if ts_match else ''

        ohlc_match = re.search(r'\[O:([\d.]+), H:([\d.]+), L:([\d.]+), C:([\d.]+)\]', inner)
        if not ohlc_match:
            i += 1
            continue
        ohlc = OHLC(
            open_=float(ohlc_match.group(1)),
            high=float(ohlc_match.group(2)),
            low=float(ohlc_match.group(3)),
            close=float(ohlc_match.group(4)),
        )

        # Consume all lines for this bar (same bar_index)
        eval_lines: List[TraceLine] = []
        state_blocks: List[StateBlock] = []
        j = i
        while j < len(lines):
            line_raw = lines[j].strip()
            if not line_raw:
                j += 1
                continue
            is_r = line_raw.startswith('[RETRO]')
            inner_l = line_raw[7:] if is_r else line_raw
            bar_m = re.search(r'\[Bar (\d+)\]', inner_l)
            if bar_m and int(bar_m.group(1)) != bar_index:
                break

            if '[STATE]' in line_raw:
                state_blocks.append(_parse_state_block(line_raw))
            elif '->' in line_raw:
                tl = _parse_eval_line(line_raw, is_r)
                if tl:
                    eval_lines.append(tl)
            j += 1

        bars[bar_index] = TraceBar(
            bar_index=bar_index, timestamp=timestamp, ohlc=ohlc,
            lines=eval_lines, state_blocks=state_blocks, retro=is_retro
        )
        i = j
    return bars

def _parse_eval_line(line_raw: str, is_retro: bool) -> Optional[TraceLine]:
    """Parse an evaluation line like: ... -> [Fan fraction @ price] O <= Line -> CROSS_UP"""
    if '->' not in line_raw:
        return None
    after_arrow = line_raw.split('->')[-1].strip()
    outcome = after_arrow

    # Try to find [fan fraction @ price] before the arrow
    bracket_m = re.search(r'\[([^\]]+)\]', line_raw)
    if not bracket_m:
        return TraceLine(fan='?', fraction='?', price=0.0, outcome=outcome)
    bracket_content = bracket_m.group(1)

    price_m = re.search(r'@ ([\d.]+)', bracket_content)
    price_val = float(price_m.group(1)) if price_m else 0.0

    # Extract fan and fraction
    frac_words = ['main', 'horizontal', '0.875', '0.75', '0.5', '0.25']
    last_fw_idx = -1
    last_fw = 'main'
    for fw in frac_words:
        idx = bracket_content.rfind(f' {fw}')
        if idx > last_fw_idx:
            last_fw_idx = idx
            last_fw = fw
    fan_name = bracket_content[:last_fw_idx].strip() if last_fw_idx >= 0 else bracket_content

    return TraceLine(fan=fan_name, fraction=last_fw, price=price_val, outcome=outcome)

def _parse_state_block(line_raw: str) -> StateBlock:
    """Parse a [STATE] block line."""
    # Format: ... -> [STATE] block_type: key=value key=value ...
    after_arrow = line_raw.split('->')[-1].strip()
    after_state = after_arrow.replace('[STATE]', '').strip()
    parts = after_state.split(': ', 1)
    block_type = parts[0].strip()
    params = {}
    if len(parts) > 1:
        for kv in parts[1].split():
            if '=' in kv:
                k, v = kv.split('=', 1)
                params[k.strip()] = v.strip()
    return StateBlock(block_type=block_type, fan=params.get('fan', ''), params=params)
```

- [ ] **Step 3: Write `parse_events_csv()`**

```python
def parse_events_csv(path: Path) -> List[CSVEvent]:
    lines = path.read_text(encoding='utf-8').splitlines()
    events = []
    for i, raw in enumerate(lines[1:], start=2):
        raw = raw.strip()
        if not raw:
            continue
        parts = _csv_split(raw)
        if len(parts) < 16:
            continue
        try:
            events.append(CSVEvent(
                row_num=i,
                bar_index=int(parts[0]) if parts[0] else 0,
                timestamp=parts[1].strip('"'),
                fan=parts[2].strip('"'),
                fraction=parts[3].strip('"'),
                price=float(parts[4]),
                event_type=parts[5].strip('"'),
                details=parts[6].strip('"'),
                open_=float(parts[7]),
                high=float(parts[8]),
                low=float(parts[9]),
                close=float(parts[10]),
                zone=parts[13].strip('"'),
                zone_high=float(parts[14]) if parts[14] else 0.0,
                zone_low=float(parts[15]) if parts[15] else 0.0,
                bars_elapsed=int(parts[18]) if len(parts) > 18 and parts[18] else 0,
            ))
        except (ValueError, IndexError):
            continue
    return events
```

- [ ] **Step 4: Write event verification functions**

```python
def verify_cross_up(ev: CSVEvent) -> tuple:
    """Returns (accurate: bool, detail: str)"""
    ok = (ev.open_ <= ev.price) and (ev.close >= ev.price)
    return ok, f"O({ev.open_:.2f})<=L({ev.price:.2f})={ev.open_<=ev.price}, C({ev.close:.2f})>=L={ev.close>=ev.price}"

def verify_cross_down(ev: CSVEvent) -> tuple:
    ok = (ev.open_ >= ev.price) and (ev.close <= ev.price)
    return ok, f"O({ev.open_:.2f})>=L({ev.price:.2f})={ev.open_>=ev.price}, C({ev.close:.2f})<=L={ev.close<=ev.price}"

def verify_support_test(ev: CSVEvent) -> tuple:
    ok = (ev.open_ >= ev.price) and (ev.close >= ev.price) and (ev.low <= ev.price) and (ev.close > ev.price)
    return ok, f"O>=L={ev.open_>=ev.price}, C>=L={ev.close>=ev.price}, L<=L={ev.low<=ev.price}, C>L={ev.close>ev.price}"

def verify_resistance_test(ev: CSVEvent) -> tuple:
    ok = (ev.open_ <= ev.price) and (ev.close <= ev.price) and (ev.high >= ev.price) and (ev.close < ev.price)
    return ok, f"O<=L={ev.open_<=ev.price}, C<=L={ev.close<=ev.price}, H>=L={ev.high>=ev.price}, C<L={ev.close<ev.price}"

def verify_support_touch(ev: CSVEvent) -> tuple:
    """SUPPORT_TOUCH: body above line, low wick touches, close ON the line (not crossed)."""
    ok = (ev.open_ >= ev.price) and (ev.close >= ev.price) and (ev.low <= ev.price) and (ev.close == ev.price)
    return ok, f"O>=L={ev.open_>=ev.price}, C>=L={ev.close>=ev.price}, L<=L={ev.low<=ev.price}, C==L={ev.close==ev.price}"

def verify_resistance_touch(ev: CSVEvent) -> tuple:
    """RESISTANCE_TOUCH: body below line, high wick touches, close ON the line (not crossed)."""
    ok = (ev.open_ <= ev.price) and (ev.close <= ev.price) and (ev.high >= ev.price) and (ev.close == ev.price)
    return ok, f"O<=L={ev.open_<=ev.price}, C<=L={ev.close<=ev.price}, H>=L={ev.high>=ev.price}, C==L={ev.close==ev.price}"

def verify_breach_confirmed(ev: CSVEvent, state_block: Optional[StateBlock]) -> tuple:
    """Verify BREACH_CONFIRMED using [STATE] block context."""
    if state_block is None:
        return False, "No [STATE] block found for BREACH_CONFIRMED"
    p = state_block.params
    bec = float(p.get('bec_close', 0))
    zec_h = float(p.get('zec_high', 0))
    zec_l = float(p.get('zec_low', 0))
    direction = p.get('direction', '')
    boundary = max(bec, zec_h) if direction == 'UP' else min(bec, zec_l)
    if direction == 'UP':
        ok = ev.close > boundary
    else:
        ok = ev.close < boundary
    return ok, f"C={ev.close:.2f} {'>' if direction=='UP' else '<'} boundary={boundary:.2f} (BEC={bec}, ZEC_H={zec_h}, ZEC_L={zec_l})"

def verify_breach_confirmed_no_alpha(ev: CSVEvent, state_block: Optional[StateBlock]) -> tuple:
    """BREACH_CONFIRMED_NO_ALPHA is verifiable via [STATE] block."""
    if state_block is None:
        return False, "No [STATE] block found"
    return True, f"Path={state_block.params.get('outcome', 'N/A')}"

def verify_touch_as_directional(ev: CSVEvent) -> tuple:
    """
    Classify current CSV 'TOUCH' as SUPPORT_TOUCH or RESISTANCE_TOUCH.
    If C > line_price -> SUPPORT_TOUCH. If C < line_price -> RESISTANCE_TOUCH.
    If C == line_price, use body position: O >= line -> SUPPORT_TOUCH else RESISTANCE_TOUCH.
    """
    if ev.close > ev.price:
        expected = 'SUPPORT_TOUCH'
    elif ev.close < ev.price:
        expected = 'RESISTANCE_TOUCH'
    else:
        expected = 'SUPPORT_TOUCH' if ev.open_ >= ev.price else 'RESISTANCE_TOUCH'
    ok = (ev.event_type == expected)
    return ok, f"C={ev.close:.2f} {'>' if ev.close>ev.price else '<' if ev.close<ev.price else '='} L={ev.price:.2f} -> {expected}"
```

- [ ] **Step 5: Write missed event detection**

```python
def detect_missed_events(trace_bars: Dict[int, TraceBar], csv_events: List[CSVEvent]) -> List[Dict]:
    """
    For each bar in trace_bars that has evaluated lines (not 'No Event'),
    check if any line meets CROSS/TEST/TOUCH criteria but no matching event in CSV.
    """
    # Build CSV events indexed by (bar_index, fan, fraction)
    csv_event_map: Dict[tuple, CSVEvent] = {}
    for ev in csv_events:
        key = (ev.bar_index, ev.fan, ev.fraction)
        csv_event_map[key] = ev

    missed = []
    for bar_index, bar in trace_bars.items():
        for line in bar.lines:
            outcome = line.outcome.strip()
            if outcome in ('No Event', 'No Intersection', ''):
                continue
            if 'pending' in outcome.lower() or 'deferred' in outcome.lower():
                continue  # Not a confirmed event yet

            # Check if this bar meets any event definition
            expected_event = _classify_bar_line(bar, line)
            if expected_event is None:
                continue

            # Check if CSV has a matching event
            csv_key = (bar_index, line.fan, line.fraction)
            csv_ev = csv_event_map.get(csv_key)

            if csv_ev is None:
                missed.append({
                    'bar_index': bar_index,
                    'timestamp': bar.timestamp,
                    'fan': line.fan,
                    'fraction': line.fraction,
                    'line_price': line.price,
                    'expected_event': expected_event,
                    'ohlc': f"O={bar.ohlc.open_:.2f} H={bar.ohlc.high:.2f} L={bar.ohlc.low:.2f} C={bar.ohlc.close:.2f}",
                    'actual_trace': outcome,
                    'reason': 'Event definition met but no matching event in CSV'
                })
            elif csv_ev.event_type != expected_event:
                missed.append({
                    'bar_index': bar_index,
                    'timestamp': bar.timestamp,
                    'fan': line.fan,
                    'fraction': line.fraction,
                    'line_price': line.price,
                    'expected_event': expected_event,
                    'actual_csv_event': csv_ev.event_type,
                    'ohlc': f"O={bar.ohlc.open_:.2f} H={bar.ohlc.high:.2f} L={bar.ohlc.low:.2f} C={bar.ohlc.close:.2f}",
                    'reason': f'Wrong event type: expected {expected_event}, got {csv_ev.event_type}'
                })

    return missed

def _classify_bar_line(bar: TraceBar, line: TraceLine) -> Optional[str]:
    """
    Given a bar's OHLC and a line price, determine which event type
    the bar should be classified as based on EVENT_TYPES.md definitions.
    Returns the event type string or None if no event.
    """
    o, h, l, c = bar.ohlc.open_, bar.ohlc.high, bar.ohlc.low, bar.ohlc.close
    lp = line.price

    # CROSS_UP: O <= line AND C >= line
    if o <= lp and c >= lp:
        return 'CROSS_UP'
    # CROSS_DOWN: O >= line AND C <= line
    if o >= lp and c <= lp:
        return 'CROSS_DOWN'
    # SUPPORT_TEST: O >= line AND C >= line AND L <= line AND C > line
    if o >= lp and c >= lp and l <= lp and c > lp:
        return 'SUPPORT_TEST'
    # RESISTANCE_TEST: O <= line AND C <= line AND H >= line AND C < line
    if o <= lp and c <= lp and h >= lp and c < lp:
        return 'RESISTANCE_TEST'
    # SUPPORT_TOUCH: O >= line AND C >= line AND L <= line AND C == line
    if o >= lp and c >= lp and l <= lp and c == lp:
        return 'SUPPORT_TOUCH'
    # RESISTANCE_TOUCH: O <= line AND C <= line AND H >= line AND C == line
    if o <= lp and c <= lp and h >= lp and c == lp:
        return 'RESISTANCE_TOUCH'
    return None
```

- [ ] **Step 6: Write the main report generation**

```python
def generate_report(trace_bars: Dict[int, TraceBar], csv_events: List[CSVEvent],
                     missed_events: List[Dict], output_dir: Path):
    """Generate TRACE_AUDIT_REPORT.txt and EVENT_VERIFICATION.csv."""

    # Build state block lookup
    state_map: Dict[tuple, StateBlock] = {}
    for bar in trace_bars.values():
        for sb in bar.state_blocks:
            key = (bar.bar_index, sb.fan)
            state_map[key] = sb

    accuracy_results = []
    state_dependent_events = []
    inaccurate_events = []

    for ev in csv_events:
        accurate, detail = verify_event(ev, state_map.get((ev.bar_index, ev.fan)))
        if ev.event_type in ('BREACH_CONFIRMED_NO_ALPHA', 'BREACH_CONFIRMED', 'FAN_VALIDATED',
                              'FAN_DEACTIVATED', 'TARGET_HIT', 'SUPPORT_BOUNCE',
                              'RESISTANCE_REJECTION', 'DEFERRED', 'ZONE_CHANGE'):
            state_dependent_events.append({
                'bar': ev.bar_index, 'timestamp': ev.timestamp,
                'fan': ev.fan, 'fraction': ev.fraction,
                'event_type': ev.event_type,
                'has_state_block': (ev.bar_index, ev.fan) in state_map
            })
        else:
            accuracy_results.append({
                'bar': ev.bar_index, 'timestamp': ev.timestamp,
                'fan': ev.fan, 'fraction': ev.fraction,
                'event_type': ev.event_type, 'line_price': ev.price,
                'accurate': accurate, 'detail': detail
            })
            if not accurate:
                inaccurate_events.append({
                    'bar': ev.bar_index, 'timestamp': ev.timestamp,
                    'fan': ev.fan, 'fraction': ev.fraction,
                    'event_type': ev.event_type,
                    'expected_condition': detail,
                    'csv_event_type': ev.event_type
                })

    total_checkable = len(accuracy_results)
    accurate_count = sum(1 for r in accuracy_results if r['accurate'])
    inaccurate_count = total_checkable - accurate_count
    accuracy_pct = (accurate_count / total_checkable * 100) if total_checkable > 0 else 0

    bars_evaluated = sum(1 for b in trace_bars.values() if b.lines)
    missed_count = len(missed_events)
    completeness_pct = ((bars_evaluated - missed_count) / bars_evaluated * 100) if bars_evaluated > 0 else 0

    # Write text report
    report_path = output_dir / 'TRACE_AUDIT_REPORT.txt'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("=== EVENT VERIFICATION REPORT ===\n")
        f.write(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("ACCURACY (events that fired — were they correct per EVENT_TYPES.md definitions?)\n")
        f.write(f"  Events checked: {total_checkable}\n")
        f.write(f"  Accurate: {accurate_count} ({accuracy_pct:.1f}%)\n")
        f.write(f"  Inaccurate: {inaccurate_count} ({inaccuracy_pct:.1f}%)\n")
        if inaccurate_events:
            f.write("  Inaccurate events:\n")
            for ie in inaccurate_events:
                f.write(f"    Bar {ie['bar']} [{ie['timestamp']}] {ie['fan']} {ie['fraction']}\n")
                f.write(f"      Event type: {ie['csv_event_type']}, Condition: {ie['expected_condition']}\n")
        f.write(f"\n  NOTE: Accuracy must be 100%. Any inaccuracy is a bug in event detection logic.\n\n")

        f.write("STATE-DEPENDENT EVENTS (verified via [STATE] blocks — not re-evaluated)\n")
        f.write(f"  {len(state_dependent_events)} events\n")
        for sd in state_dependent_events:
            status = 'YES' if sd['has_state_block'] else 'MISSING'
            f.write(f"    Bar {sd['bar']} [{sd['timestamp']}] {sd['fan']} {sd['fraction']} {sd['event_type']} [STATE]={status}\n")

        f.write(f"\nCOMPLETENESS (bars where state machine evaluated a line — were all events caught?)\n")
        f.write(f"  Bars evaluated: {bars_evaluated}\n")
        f.write(f"  Missed events: {missed_count}\n")
        if missed_events:
            f.write("  Missed event details:\n")
            for me in missed_events[:20]:  # cap at 20 for readability
                f.write(f"    Bar {me['bar_index']} [{me['timestamp']}] {me['fan']} {me['fraction']} @ {me['line_price']}\n")
                f.write(f"      Expected: {me['expected_event']}, Reason: {me['reason']}\n")
                f.write(f"      OHLC: {me['ohlc']}\n")

        f.write(f"\nSUMMARY\n")
        f.write(f"  Accuracy: {accuracy_pct:.1f}%  (100% required)\n")
        f.write(f"  Completeness: {completeness_pct:.1f}%\n")
        f.write(f"  Status: {'PASS' if accuracy_pct == 100.0 and missed_count == 0 else 'FAIL'}\n")

    # Write verification CSV
    csv_path = output_dir / 'EVENT_VERIFICATION.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'bar_index', 'timestamp', 'fan', 'fraction', 'event_type', 'line_price',
            'ohlc', 'accuracy_result', 'accuracy_detail', 'missed_event', 'missed_detail'
        ])
        writer.writeheader()

        # Write accuracy-checkable events
        for r in accuracy_results:
            writer.writerow({
                'bar_index': r['bar'], 'timestamp': r['timestamp'],
                'fan': r['fan'], 'fraction': r['fraction'],
                'event_type': r['event_type'], 'line_price': r['line_price'],
                'ohlc': '',
                'accuracy_result': 'ACCURATE' if r['accurate'] else 'INACCURATE',
                'accuracy_detail': r['detail'],
                'missed_event': 'YES' if r['bar'] in [m['bar_index'] for m in missed_events] else 'NO',
                'missed_detail': next((m['reason'] for m in missed_events if m['bar_index'] == r['bar']), '')
            })

        # Write state-dependent events
        for sd in state_dependent_events:
            writer.writerow({
                'bar_index': sd['bar'], 'timestamp': sd['timestamp'],
                'fan': sd['fan'], 'fraction': sd['fraction'],
                'event_type': sd['event_type'], 'line_price': '',
                'ohlc': '',
                'accuracy_result': 'STATE_DEPENDENT',
                'accuracy_detail': '[STATE] block present: ' + ('YES' if sd['has_state_block'] else 'MISSING'),
                'missed_event': 'NO',
                'missed_detail': ''
            })

    return accuracy_pct, completeness_pct, len(missed_events)
```

- [ ] **Step 7: Write the ML data export**

```python
def export_ml_data(trace_bars: Dict[int, TraceBar], csv_events: List[CSVEvent],
                    missed_events: List[Dict], accuracy_results: List[Dict],
                    output_dir: Path):
    """Export events_ml.csv and bars_ml.csv for ML training."""

    # Build state block lookup
    state_map: Dict[tuple, StateBlock] = {}
    for bar in trace_bars.values():
        for sb in bar.state_blocks:
            state_map[(bar.bar_index, sb.fan)] = sb

    missed_bar_indices = {m['bar_index'] for m in missed_events}

    # events_ml.csv — all CSV events with full context
    events_ml_path = output_dir / 'events_ml.csv'
    with open(events_ml_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'bar_index', 'timestamp', 'fan_id', 'fraction', 'line_price',
            'open', 'high', 'low', 'close', 'event_type', 'direction',
            'zone', 'zone_high', 'zone_low', 'bec_close', 'zec_high', 'zec_low',
            'target_hit_sequence', 'bars_elapsed', 'is_missed_event', 'accuracy_verified'
        ])
        writer.writeheader()
        for ev in csv_events:
            state = state_map.get((ev.bar_index, ev.fan))
            is_missed = ev.bar_index in missed_bar_indices
            accurate = next((r['accurate'] for r in accuracy_results
                            if r['bar'] == ev.bar_index and r['fan'] == ev.fan and r['fraction'] == ev.fraction), None)

            direction = 'N/A'
            if ev.event_type in ('CROSS_UP', 'SUPPORT_TEST', 'SUPPORT_TOUCH', 'SUPPORT_BOUNCE'):
                direction = 'UP'
            elif ev.event_type in ('CROSS_DOWN', 'RESISTANCE_TEST', 'RESISTANCE_TOUCH', 'RESISTANCE_REJECTION'):
                direction = 'DOWN'
            elif ev.event_type in ('BREACH_CONFIRMED', 'BREACH_CONFIRMED_NO_ALPHA'):
                direction = state.params.get('direction', 'N/A') if state else 'N/A'

            writer.writerow({
                'bar_index': ev.bar_index, 'timestamp': ev.timestamp,
                'fan_id': ev.fan, 'fraction': ev.fraction,
                'line_price': ev.price,
                'open': ev.open_, 'high': ev.high, 'low': ev.low, 'close': ev.close,
                'event_type': ev.event_type, 'direction': direction,
                'zone': ev.zone, 'zone_high': ev.zone_high, 'zone_low': ev.zone_low,
                'bec_close': float(state.params['bec_close']) if state and 'bec_close' in state.params else '',
                'zec_high': float(state.params['zec_high']) if state and 'zec_high' in state.params else '',
                'zec_low': float(state.params['zec_low']) if state and 'zec_low' in state.params else '',
                'target_hit_sequence': '',
                'bars_elapsed': ev.bars_elapsed,
                'is_missed_event': 'TRUE' if is_missed else 'FALSE',
                'accuracy_verified': str(accurate).upper() if accurate is not None else 'N/A'
            })

    # bars_ml.csv — evaluated bars with no event (near-miss negative cases)
    bars_ml_path = output_dir / 'bars_ml.csv'
    with open(bars_ml_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'bar_index', 'timestamp', 'fan_id', 'fraction', 'line_price',
            'open', 'high', 'low', 'close', 'range', 'body_size',
            'distance_to_line', 'nearest_line_direction',
            'event_type', 'zone', 'zone_high', 'zone_low', 'reason_no_event'
        ])
        writer.writeheader()
        for bar in trace_bars.values():
            for line in bar.lines:
                outcome = line.outcome.strip()
                if outcome in ('No Event', 'No Intersection', ''):
                    continue

                classified = _classify_bar_line(bar, line)
                if classified is not None:
                    continue  # Has an event — not a negative case

                rng = bar.ohlc.high - bar.ohlc.low
                body = abs(bar.ohlc.close - bar.ohlc.open_)
                dist = bar.ohlc.close - line.price
                dir_ = 'ABOVE' if dist > 0 else 'BELOW' if dist < 0 else 'ON'

                writer.writerow({
                    'bar_index': bar.bar_index, 'timestamp': bar.timestamp,
                    'fan_id': line.fan, 'fraction': line.fraction,
                    'line_price': line.price,
                    'open': bar.ohlc.open_, 'high': bar.ohlc.high,
                    'low': bar.ohlc.low, 'close': bar.ohlc.close,
                    'range': rng, 'body_size': body,
                    'distance_to_line': abs(dist),
                    'nearest_line_direction': dir_,
                    'event_type': 'NONE',
                    'zone': '', 'zone_high': '', 'zone_low': '',
                    'reason_no_event': f"No CROSS/TEST criteria met (trace: {outcome})"
                })
```

- [ ] **Step 8: Write the `verify_event()` dispatcher**

```python
def verify_event(ev: CSVEvent, state_block: Optional[StateBlock]) -> tuple:
    """Dispatch to the right verification function. Returns (accurate: bool, detail: str)."""
    # First handle TOUCH reclassification
    if ev.event_type == 'TOUCH':
        return verify_touch_as_directional(ev)

    dispatch = {
        'CROSS_UP': verify_cross_up,
        'CROSS_DOWN': verify_cross_down,
        'SUPPORT_TEST': verify_support_test,
        'RESISTANCE_TEST': verify_resistance_test,
        'SUPPORT_TOUCH': verify_support_touch,
        'RESISTANCE_TOUCH': verify_resistance_touch,
        'BREACH_CONFIRMED': verify_breach_confirmed,
        'BREACH_CONFIRMED_NO_ALPHA': verify_breach_confirmed_no_alpha,
        'FAN_VALIDATED': lambda e, sb: (True, 'fan validated via [STATE]'),
        'FAN_DEACTIVATED': lambda e, sb: (True, 'fan deactivated via [STATE]'),
        'TARGET_HIT': lambda e, sb: (True, 'target hit via [STATE]'),
        'SUPPORT_BOUNCE': lambda e, sb: (True, 'support bounce via [STATE]'),
        'RESISTANCE_REJECTION': lambda e, sb: (True, 'resistance rejection via [STATE]'),
        'DEFERRED': lambda e, sb: (True, 'deferred via [STATE]'),
        'ZONE_CHANGE': lambda e, sb: (True, 'zone change — not verified from trace'),
        'REST_ON_ANGLE': lambda e, sb: (True, 'rest on angle — not an event type in EVENT_TYPES.md'),
    }
    fn = dispatch.get(ev.event_type)
    if fn:
        return fn(ev, state_block)
    return (False, f'Unknown event type: {ev.event_type}')
```

- [ ] **Step 9: Write the `main()` function**

```python
def main():
    import datetime

    REPO_ROOT = Path(__file__).parent.parent.parent.parent
    TRACE_PATH = REPO_ROOT / 'logs' / 'backend' / 'simulation_trace.log'
    EVENTS_CSV = REPO_ROOT / 'logs' / 'backend' / 'simulation_events.csv'
    OUT_DIR = REPO_ROOT / 'logs' / 'backend' / 'trace_audit'
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not EVENTS_CSV.exists():
        print(f'ERROR: events CSV not found: {EVENTS_CSV}')
        sys.exit(1)
    if not TRACE_PATH.exists():
        print(f'ERROR: trace log not found: {TRACE_PATH}')
        sys.exit(1)

    print(f'Reading events CSV: {EVENTS_CSV}')
    csv_events = parse_events_csv(EVENTS_CSV)
    print(f'  Found {len(csv_events)} events in CSV')

    print(f'Reading trace log: {TRACE_PATH}')
    trace_bars = parse_trace_log(TRACE_PATH)
    print(f'  Found {len(trace_bars)} bars in trace log')

    print('Detecting missed events...')
    missed_events = detect_missed_events(trace_bars, csv_events)

    print('Generating reports...')
    accuracy_pct, completeness_pct, missed_count = generate_report(
        trace_bars, csv_events, missed_events, OUT_DIR
    )

    print('Exporting ML data...')
    accuracy_results = []  # built during report generation
    export_ml_data(trace_bars, csv_events, missed_events, accuracy_results, OUT_DIR)

    print(f'\n=== SUMMARY ===')
    print(f'Accuracy: {accuracy_pct:.1f}%  (100% required)')
    print(f'Completeness: {completeness_pct:.1f}%')
    print(f'Missed events: {missed_count}')
    print(f'Status: {"PASS" if accuracy_pct == 100.0 and missed_count == 0 else "FAIL"}')
    print(f'\nOutputs:')
    print(f'  {OUT_DIR / "TRACE_AUDIT_REPORT.txt"}')
    print(f'  {OUT_DIR / "EVENT_VERIFICATION.csv"}')
    print(f'  {OUT_DIR / "events_ml.csv"}')
    print(f'  {OUT_DIR / "bars_ml.csv"}')
```

Note: The `accuracy_results` list needs to be populated during report generation and passed to `export_ml_data()`. Restructure `generate_report()` to also return `accuracy_results` list, or build it before calling `export_ml_data()`.

- [ ] **Step 10: Fix `generate_report()` to return accuracy_results**

In `generate_report()`, after building `accuracy_results`, add:
```python
    return accuracy_pct, completeness_pct, len(missed_events), accuracy_results
```

Then in `main()`, change the call to:
```python
    accuracy_pct, completeness_pct, missed_count, accuracy_results = generate_report(...)
```

And pass `accuracy_results` to `export_ml_data()`.

- [ ] **Step 11: Test the script**

Run: `python gann-visualizer/backend/analysis/verify_trace_events.py`
Expected: Script runs without errors, produces 4 output files

- [ ] **Step 12: Commit**

```bash
git add gann-visualizer/backend/analysis/verify_trace_events.py
git commit -m "refactor: rewrite verify_trace_events.py with clean report output and ML export"
```

---

## Task 4: Integration test — run simulation and verify

- [ ] **Step 1: Run a simulation to generate fresh trace log and CSV**

This step depends on having a runnable simulation. If `run_simulation.py` exists:
Run: `python gann-visualizer/backend/run_simulation.py` (or equivalent)
Expected: `logs/backend/simulation_trace.log` and `logs/backend/simulation_events.csv` are updated

- [ ] **Step 2: Run the verification script**

Run: `python gann-visualizer/backend/analysis/verify_trace_events.py`
Expected: No errors, 4 output files in `logs/backend/trace_audit/`

- [ ] **Step 3: Inspect TRACE_AUDIT_REPORT.txt**

Expected format: ACCURACY section, STATE-DEPENDENT section, COMPLETENESS section, SUMMARY with PASS/FAIL

- [ ] **Step 4: Inspect events_ml.csv row count vs events CSV row count**

Expected: `events_ml.csv` has same number of rows as `simulation_events.csv` (all events included)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test: run verification on fresh simulation data"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|---|---|
| [STATE] blocks for BREACH_CONFIRMED | Task 1 + 2A |
| [STATE] blocks for BREACH_CONFIRMED_NO_ALPHA (Path A + Path B) | Task 2A + 2B |
| [STATE] blocks for DEFERRED | Task 2A |
| [STATE] blocks for SUPPORT_BOUNCE / RESISTANCE_REJECTION | Task 2A |
| [STATE] blocks for FAN_VALIDATED | Task 2B |
| [STATE] blocks for FAN_DEACTIVATED | Task 2B |
| [STATE] blocks for TARGET_HIT | Task 2B |
| Clean accuracy report (PASS/FAIL) | Task 3 |
| Missed event detection | Task 3 |
| events_ml.csv | Task 3 |
| bars_ml.csv | Task 3 |
| Replay trace log identical to simulation | Task 1 (additive [STATE] blocks only) |
| TOUCH → SUPPORT_TOUCH / RESISTANCE_TOUCH classification | Task 3 |
| 100% accuracy required | Task 3 |
