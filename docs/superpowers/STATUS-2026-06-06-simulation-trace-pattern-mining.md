# Simulation Trace Pattern Mining — Status Tracker

**Created:** 2026-06-06
**Last Updated:** 2026-06-06
**Owner:** kit678

## Overview

Mining `logs/backend/simulation_trace.log` (71,521 lines, BTCUSDT 1h) for repeatable, profitable price-action patterns around Gann angle division lines.

---

## What Was Planned

| Component | Scope |
|-----------|-------|
| Bug fixes | Fix 8 bugs in existing data pipeline |
| Component B — Trace Miner | Parse trace log, enrich forward returns, build sequences |
| Component B — Pattern Miner | Tier 1 MFE/MAE screening, Tier 2 line-reach validation |
| Component A — Hypothesis Validation | Validate 5 existing hypotheses on BTCUSDT |
| Component C — Notebook | Interactive Jupyter notebook for exploration |

---

## Current Status

### Bug Fixes

| Priority | Bug | Status |
|----------|-----|--------|
| P0 | `fix_applied` NameError in event_logger.py | FIXED |
| P0 | Column index mismatch in verify_trace_events.py | FIXED |
| P1 | Missing enrichment → MFE/MAE=0 ambiguity | FIXED (empty string sentinel) |
| P1 | `[Retro]` flag via fragile string match | FIXED (dedicated is_retro column) |
| P2 | ZONE_CHANGE enriched but dropped from CSV | FIXED (skip enrichment) |
| P2 | Hardcoded `/tmp/` path on Windows | FIXED (removed) |
| P2 | Three versions of event_logger.py | FIXED (deleted .bak, _fixed) |
| P3 | `evaluate()` docstring missing keys | FIXED (updated, added adapter) |

### Component B — Trace Parser (`trace_miner.py`)

**Status: DONE**

- Parses entire 71,521-line trace log
- 3,791 deduplicated events, 758 candles
- RETRO/non-RETRO dedup works (prefer non-RETRO)
- Forward MFE/MAE enrichment at 5/10/20/50 bar horizons
- 5/5 verification checks pass
- `build_sequences()` — 373 per-fan-line event chains
- `verify_parser()` — automated spot-checks and sanity tests

### Component B — Pattern Miner (`pattern_miner.py`)

**Status: DONE (Tier 1), PARTIAL (Tier 2)**

- Tier 1 screening works — tests every event_type × line_fraction × candle_pattern
- 12 candidates found passing thresholds (sample ≥ 20, win rate > 50%)
- Tier 2 line-reach validation implemented but returns 0.0 — known limitation (see below)

### Component A — Hypothesis Validation

**Status: NOT STARTED**

- 5 existing hypotheses await validation on BTCUSDT
- Adapter function (`events_df_to_csv_adapter`) is in place

### Component C — Interactive Notebook

**Status: DONE**

- `pattern_mining.ipynb` with 7 cells: load, verify, rank, explore, context-slice, visualize
- No 2-event sequence patterns or 3-event sequences yet

---

## Tier 1 Results (Top Patterns on BTCUSDT 1h)

| Pattern | Samples | MFE_10 | Win Rate | Composite |
|---------|---------|--------|----------|-----------|
| SUPPORT_TEST on 0.75 line | 127 | +0.92% | 66.1% | 10.40 |
| RESISTANCE_TEST on 0.5 line | 69 | +1.18% | 71.0% | 9.84 |
| RESISTANCE_TEST on 0.75 line | 96 | +0.99% | 56.3% | 9.74 |
| RESISTANCE_TEST on 0.25 line | 86 | +1.01% | 61.6% | 9.37 |
| SUPPORT_TEST on 0.5 line | 118 | +0.86% | 67.0% | 9.36 |
| SUPPORT_TEST on 0.25 line | 111 | +0.86% | 66.7% | 9.02 |
| BREACH_CONFIRMED (any line) [SPINNING_TOP] | 40 | +0.93% | 55.0% | 5.87 |
| SUPPORT_TEST on 0.5 line [SPINNING_TOP] | 25 | +1.09% | 80.0% | 5.44 |
| SUPPORT_TEST on 0.75 line [SPINNING_TOP] | 20 | +1.16% | 85.0% | 5.19 |
| SUPPORT_TEST on 0.5 line [PINBAR] | 24 | +0.98% | 79.2% | 4.78 |

**Key insight:** SUPPORT_TEST + SUPPORT_BOUNCE patterns dominate. 0.25/0.5/0.75 lines all show positive edge. Adding SPINNING_TOP or PINBAR candle filter improves win rate substantially (80-85%) at the cost of sample size.

---

## Limitations / Known Issues

1. **Tier 2 line-reach returns 0.0 for all patterns.** Root cause: `line_prices` dict is built from no_event lines, but events occur at bars where no_event data for that fan isn't available. Fix: build a per-fan line catalog across all bars, not just event-adjacent bars.

2. **Only single-event patterns tested.** 2-event and 3-event sequences not yet run. The sequence builder (`build_sequences()`) is in place but auto-miner doesn't consume it.

3. **No price structure context in auto-miner.** Trend/volatility/volume slicing only available in the notebook manually.

4. **State machine events (PENDING_BREACH, FAN_VALIDATED, DEFERRED) are parsed but not joined to their parent events.** This data could enable richer sequence patterns.

5. **pandas FutureWarning on bool/float dtype mixing** — patched but needs a cleaner fix.

---

## Files Created / Modified

| File | Action | Lines |
|------|--------|-------|
| `gann-visualizer/backend/study_tool/event_logger.py` | Modified (+5 fixes) | ~10 |
| `gann-visualizer/backend/study_tool/event_logger.py.bak` | Deleted | — |
| `gann-visualizer/backend/study_tool/event_logger_fixed.py` | Deleted | — |
| `gann-visualizer/backend/run_simulation.py` | Modified (NaN sentinel, is_retro) | ~20 |
| `gann-visualizer/backend/analysis/verify_trace_events.py` | Modified (column indices) | ~3 |
| `gann-visualizer/backend/analysis/strategy_analyzer.py` | Modified (docstring, adapter) | ~30 |
| `gann-visualizer/backend/analysis/trace_miner.py` | Created | ~370 |
| `gann-visualizer/backend/analysis/pattern_miner.py` | Created | ~197 |
| `gann-visualizer/backend/analysis/notebooks/pattern_mining.ipynb` | Created | ~164 |

---

## Next Steps / Enhancements Needed

### High Priority

1. **Fix Tier 2 line-reach validation** — build per-fan line price catalog from all bars, not just event-adjacent bars. This will unlock actual trade-outcome statistics.

2. **Port top Tier 1 candidates into formal Hypothesis subclasses** — encode "SUPPORT_TEST on 0.75 line" and "RESISTANCE_TEST on 0.5 line" as `GannSupportTestHypothesis` classes for formal backtesting.

### Medium Priority

3. **Add 2-event sequence auto-miner** — consume `build_sequences()`, test all event_type pairs within 1-10 bars, rank by composite score.

4. **Layer price structure context into auto-miner** — add trend direction (EMA20 slope), ATR percentile, and volume context as auto-sliced filters.

5. **Validate 5 existing hypotheses** on BTCUSDT data via the adapter.

### Low Priority

6. **Clean up pandas dtype warnings** — refactor boolean column initialization.
7. **Join state machine events to parent events** for sequence enrichment.

---
## Future Architecture Direction: Live Multi-Ticker Screener

Once pattern mining validates which setups have a real edge, the goal is a **perpetual screener** that:

- Continuously analyzes Gann fans across multiple tickers simultaneously (crypto, stocks, forex)
- Detects real-time setups matching validated patterns
- Routes signals to appropriate brokers (Binance for crypto, Dhan for stocks, others for forex)
- Places trades concurrently across brokers

**Key principle: The screening mechanism and Gann analysis is a common module** — same engine regardless of data source or broker. The current architecture already supports this:

```
Multiple Data Sources (Binance / Dhan / YFinance / Forex)
        │
        ▼
Common Gann Analysis Engine (AngularPriceCoverageStudy)
        │
        ▼
Pattern Miner (stateless pure functions on event DataFrames)
        │
        ▼
Signal Router (match detected pattern → broker)
        │
        ▼
Multiple Broker Adapters (Binance / Dhan / others)
```

**What already exists:**
- `AngularPriceCoverageStudy` — ticker-agnostic Gann fan analysis
- `pattern_miner.py` — stateless functions, works on any events_df regardless of source
- `get_data_client()` factory in `main.py` — already routes by source

**What's needed (separate future project):**
1. Streaming event buffer per ticker (windowed DataFrame from live study)
2. Signal router (pattern match → broker dispatch)
3. Broker abstraction layer (unified interface: place_order, get_positions, get_balance)
4. Concurrency model for multi-ticker screening

**Do NOT fold into current work** — the research phase must answer "which patterns work?" before investing in live infrastructure.

---
## Related Documents

- Design spec: [2026-06-06-simulation-trace-pattern-mining-design.md](file:///c:/Dev/GannTesting/docs/superpowers/specs/2026-06-06-simulation-trace-pattern-mining-design.md)
- Implementation plan: [2026-06-06-simulation-trace-pattern-mining-plan.md](file:///c:/Dev/GannTesting/docs/superpowers/plans/2026-06-06-simulation-trace-pattern-mining-plan.md)
- Batch/Sequence/Walk-Forward spec: [2026-06-15-batch-sequence-walkforward-design.md](file:///c:/Dev/GannTesting/docs/superpowers/specs/2026-06-15-batch-sequence-walkforward-design.md)
