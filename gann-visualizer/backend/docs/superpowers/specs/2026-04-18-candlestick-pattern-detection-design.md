# Candlestick Pattern Detection — Design

## Context
The trace logs (`replay_trace.log`, `simulation_trace.log`) log every bar's OHLC data but don't identify the candlestick pattern type (doji, hammer, etc.). Adding pattern detection enhances the analytical value of trace logs and feeds into the broader event analysis.

## Decision
**Option C: Wrapper Class** — Create a `CandlestickPatternDetector` interface that wraps CandleKit. This isolates the dependency and allows swapping to TA-Lib or custom logic later without pipeline changes.

---

## Architecture

### New Files
| File | Role |
|------|------|
| `gann-visualizer/backend/study_tool/candlestick_detector.py` | Main wrapper class + pattern enum |
| `gann-visualizer/backend/logs/candle_patterns.log` | Dedicated pattern log (new) |

### Modified Files
| File | Change |
|------|--------|
| `gann-visualizer/backend/study_tool/unified_state_machine.py` | Call `CandlestickPatternDetector.detect()` per bar, append pattern to trace |
| `gann-visualizer/backend/study_tool/event_logger.py` | Call `log_candle_pattern()` stub (already exists, wire it up) |
| `requirements.txt` / `pyproject.toml` | Add `candlekit` dependency |

---

## Components

### `CandlestickPatternDetector` class
```
- __init__(pattern_log_path: str)
- detect(ohlc: Dict[str, float]) -> Optional[PatternType]
- detect_single(ohlc: Dict) -> Optional[str]   # CandleKit integration
- _classify(ohlc: Dict) -> PatternType          # Maps library output to PatternType enum
```

### `PatternType` enum
Single-candle patterns: `DOJI`, `HAMMER`, `HANGING_MAN`, `SHOOTING_STAR`, `INVERTED_HAMMER`, `SPINNING_TOP`, `MARUBOZU`, `NO_PATTERN`

### Integration Point
In `UnifiedStateMachine._log_trace()`:
```python
pattern = detector.detect({'open': c_open, 'high': c_high, 'low': c_low, 'close': c_close})
pattern_str = f"[Pattern: {pattern.name}]" if pattern != PatternType.NO_PATTERN else ""
# append pattern_str to trace line
```

### Dual Output
- **Trace log**: Pattern tag appended to existing bar line
- **Dedicated log**: Full pattern entry per bar (including no-pattern, for completeness)

---

## Data Flow (updated per-bar pipeline)
```
process_bar()
  -> UnifiedStateMachine.process_bar()
     -> CandlestickPatternDetector.detect(OHLC)  # NEW
     -> IntersectionDetector.detect()
     -> _log_trace()  # now includes pattern tag
     -> EventLogger.log_event()
        -> EventLogger.log_candle_pattern()  # wire up stub
```

---

## Pattern Detection Logic (CandleKit)
CandleKit takes OHLC as pandas DataFrame or dict:
- `candlekit.detect_pattern(df)` returns pattern name(s)
- Map returned string to `PatternType` enum

---

## Verification
1. Run existing simulation/replay — verify `candle_patterns.log` created with pattern entries
2. Check trace log for `[Pattern: X]` tags on bars
3. Confirm `log_candle_pattern()` is now being called in `EventLogger`
4. Run against same data twice — output should be deterministic
