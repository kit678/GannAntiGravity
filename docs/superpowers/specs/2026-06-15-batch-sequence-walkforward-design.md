# Batch Simulation, Sequence Mining & Walk-Forward — Design

**Date:** 2026-06-15
**Status:** Pending Review
**Owner:** kit678

## 1. Goal

Scale pattern mining from single-ticker/single-timeframe to multi-ticker discovery with validation. Three components:

1. **Batch Simulation Runner** — generate trace logs for 6 tickers × 1h from Binance
2. **2-Event Sequence Auto-Miner** — mine consecutive event pairs on the same fan
3. **Walk-Forward Validator** — 70/30 train/test split to detect overfitting

## 2. Context

**What we have:**
- Single-event pattern miner (Tier 1 + Tier 2 + A/B/C grading + trailing stop) working on BTCUSDT 1h
- `build_sequences()` in `trace_miner.py` — groups events by `(fan_id, line_fraction)`, produces 373 per-fan-line chains
- `ticker_config.json` updated with 6 tickers: BTCUSDT, ETHUSDT, BNBUSDT, BCHUSDT, SOLUSDT, LTCUSDT
- `run_simulation.py` accepts `--symbol`, `--resolution`, `--source binance`

**What's missing:**
- No data for tickers other than BTCUSDT
- No mechanism to mine multi-event sequences
- No out-of-sample validation — all stats are in-sample

**What's pending (user side):** Manual testing of price-to-bar ratios on the frontend. The batch runner must support `--scale-ratio` override so ratios can be passed in without editing `ticker_config.json` each time.

## 3. Architecture

```
run_batch_simulation.py  ──shells out──>  run_simulation.py  ──>  simulation_trace_{T}_{TF}.log
                                                      │
                                                      │ (new --scale-ratio flag)
                                                      ▼
                                          get_dynamic_scale_ratio() override
```

```
trace_miner.py (existing)
  ├── parse_trace()         → events_df, candles_df, fan_line_catalog
  ├── build_sequences()     → {(fan, line): [events]}          ← existing, untouched
  └── build_fan_sequences() → {fan_id: [sequence]}             ← NEW

pattern_miner.py (modify)
  ├── [existing single-event miner: Tier 1, Tier 2, grading, trailing stop]
  ├── extract_sequence_pairs()      ← NEW: consume build_fan_sequences()
  ├── run_sequence_tier1()          ← NEW: Tier 1 for pairs
  ├── run_sequence_tier2()          ← NEW: Tier 2 for pairs
  ├── grade_sequences()             ← NEW: A/B/C for pairs (reuse grade_patterns logic)
  └── walk_forward_validate()       ← NEW: train/test split + persistence check
```

## 4. Component Details

### 4.1 Batch Simulation Runner

**File:** New — `gann-visualizer/backend/run_batch_simulation.py`

**Purpose:** Run the trace log generation step for multiple tickers/timeframes sequentially.

**Interface:**
```bash
# All 6 tickers, 1h timeframe
python run_batch_simulation.py --tickers BTCUSDT,ETHUSDT,BNBUSDT,BCHUSDT,SOLUSDT,LTCUSDT --timeframes 60

# Single ticker, multiple timeframes
python run_batch_simulation.py --tickers BTCUSDT --timeframes 60,240

# With scale-ratio override (passes through to run_simulation.py)
python run_batch_simulation.py --tickers SOLUSDT --timeframes 60 --scale-ratio 54.905
```

**Behavior:**
- Accepts `--tickers` (comma-separated), `--timeframes` (comma-separated resolution codes), `--scale-ratio` (optional float)
- For each `(ticker, timeframe)` pair, runs: `python run_simulation.py --symbol {T} --resolution {R} --source binance [--scale-ratio {S}]`
- Logs each run: ticker, resolution, event count, bar count, elapsed time
- Skips if trace log already exists (`--force` to override)
- Output: `logs/backend/simulation_trace_{TICKER}_{RESOLUTION}.log` (e.g., `simulation_trace_ETHUSDT_60.log`)

**Error handling:** If a run fails (non-zero exit or no events), skip remaining runs for that ticker/timeframe but continue with others. Log the failure.

### 4.2 `--scale-ratio` Flag on run_simulation.py

**File:** Modify — `gann-visualizer/backend/run_simulation.py`

Add `--scale-ratio` (float, optional). When provided, bypass `get_dynamic_scale_ratio()` and use the given value directly in the AngularPriceCoverageStudy initialization.

This is the mechanism for the user to test different ratios without editing `ticker_config.json`.

### 4.3 2-Event Sequence Auto-Miner

**Files:**
- Modify `gann-visualizer/backend/analysis/trace_miner.py` — add `build_fan_sequences()`
- Modify `gann-visualizer/backend/analysis/pattern_miner.py` — add sequence mining functions

#### 4.3.1 `build_fan_sequences()` in trace_miner.py

Groups events by `fan_id` only (not fan+line), sorts by `bar_index`, returns ordered sequences with full event data.

```python
build_fan_sequences(events_df: pd.DataFrame) -> dict
# Returns: {fan_id: [list of event dicts with bar_index, event_type, line_fraction, ...]}
```

Events from different line fractions on the same fan appear in the same sequence, sorted by bar_index. Only non-RETRO events.

#### 4.3.2 Sequence Mining Pipeline in pattern_miner.py

**`extract_sequence_pairs(fan_sequences)`**
- From each fan's event sequence, extract all consecutive 2-event pairs with bar gap 1-10 (difference in bar_index between consecutive events).
- Returns DataFrame with columns: `fan_id, event_type_1, event_type_2, line_frac_1, line_frac_2, bar_index_1, bar_index_2, bar_gap`
- Pairs from the same fan, any line fraction (Option B).

**`run_sequence_tier1(events_df, pair_df)`**
- For each unique `(event_type_1, event_type_2)` combo, find all pairs in `pair_df`.
- Use the 2nd event's bar_index to look up forward returns (fwd_mfe_10, fwd_mae_10, fwd_win_10) from `events_df`.
- Reuse `compute_pattern_stats()` on the 2nd event subset.
- Returns DataFrame with columns: `pattern` ("EVT1→EVT2"), `sample_count`, `mean_mfe_10`, `mean_mae_10`, `win_rate`, `composite`, `p25/p50/p75_mfe_10`.
- Filter: sample_count >= 5, win_rate > 50%.

**`run_sequence_tier2(events_df, tier1_df, fan_line_catalog)`**
- Same line-reach validation as single events, using the 2nd event as the entry point.
- For each pair pattern, find all 2nd events, compute line_reach_rate_10 and line_reach_rate_20.
- Returns tier1_df with line_reach columns appended, sorted by composite, top 20.

**`grade_sequences(tier1_df, tier2_df)`**
- Same grading rules as single events: A/B/C based on win_rate and line_reach_rate_10.
- Reuse logic from `grade_patterns()` — either call directly or duplicate with sequence-specific pattern column.

#### 4.3.3 Output

```
pattern              sample_count  win_rate  mean_mfe_10  line_reach_10  grade
SUPPORT_TEST→CROSS_UP      23      0.72      1.234          0.58          A
RESISTANCE_TEST→CROSS_DOWN 18      0.67      0.987          0.45          B
...
```

### 4.4 Walk-Forward Validator

**File:** Modify `gann-visualizer/backend/analysis/pattern_miner.py`

**`walk_forward_validate(events_df, candles_df, fan_line_catalog, train_pct=0.7)`**

1. **Split:** Sort `events_df` by `bar_index` ascending. Earliest 70% of bars → train, latest 30% → test. Use bar_index as proxy for chronological order (bars are sequential in the trace log).

2. **Train:** Run full single-event mining pipeline on train set only:
   - `run_tier1(train_events)` → train Tier 1 candidates
   - `run_tier2(train_events, tier1_train, catalog)` → train Tier 2
   - `grade_patterns(tier1_train, tier2_train)` → graded train patterns

3. **Test evaluation:** For each train pattern, apply the same mask (event_type + line_fraction + candle_pattern, non-RETRO) to test events. Compute test stats using `compute_pattern_stats()`.

4. **Persistence check:** Flag a pattern as "persistent" if all of:
   - test_win_rate >= train_win_rate * 0.8
   - test_composite >= train_composite * 0.8
   - test_sample_count >= 5

5. **Returns:** DataFrame with columns: `pattern, grade, train_composite, test_composite, train_win_rate, test_win_rate, train_samples, test_samples, persistent` (bool). Sorted by train_composite descending.

## 5. File Summary

| Action | File | What |
|--------|------|------|
| Create | `gann-visualizer/backend/run_batch_simulation.py` | Batch runner script (~100 lines) |
| Modify | `gann-visualizer/backend/run_simulation.py` | Add `--scale-ratio` CLI argument |
| Modify | `gann-visualizer/backend/analysis/trace_miner.py` | Add `build_fan_sequences()` |
| Modify | `gann-visualizer/backend/analysis/pattern_miner.py` | Add `extract_sequence_pairs()`, `run_sequence_tier1()`, `run_sequence_tier2()`, `grade_sequences()`, `walk_forward_validate()` |

No new files in `analysis/`. No changes to existing functions.

## 6. Dependencies Between Components

```
Component 1 (batch runner)
  └── Depends on run_simulation.py --scale-ratio flag (Component 2 dependency)
  └── Independent of sequence miner and walk-forward

Component 2 (sequence miner)  
  └── Depends on build_fan_sequences() in trace_miner.py
  └── Depends on compute_pattern_stats(), compute_line_reach(), grade_patterns() in pattern_miner.py
  └── Independent of batch runner and walk-forward

Component 3 (walk-forward)
  └── Depends on full single-event pipeline (Tier 1, Tier 2, grading)
  └── Independent of batch runner and sequence miner
```

Components 2 and 3 are independent and can be built/tested in parallel. Component 1 should be built first so trace logs are ready.

## 7. Testing Strategy

- **Batch runner:** Run on 2 tickers, verify trace logs created, verify skip behavior on re-run
- **Sequence miner:** Run on existing BTCUSDT trace, verify pair extraction produces non-empty DataFrame, verify Tier 1 returns patterns with sample_count >= 5
- **Walk-forward:** Run on BTCUSDT trace, verify train/composite differ, verify persistence flags are boolean, verify test set has >= 3 patterns with test_composite > 0

Verification scripts inline (no formal test framework — same pattern as existing plan).
