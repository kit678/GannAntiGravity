# Batch Simulation, Sequence Mining & Walk-Forward — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scale pattern mining to 6 tickers on Binance 1h, add 2-event sequence discovery, and validate patterns with walk-forward train/test split.

**Architecture:** Three independent components. Component 1 (batch runner + scale-ratio flag) generates trace logs. Component 2 (sequence miner) adds `build_fan_sequences()` and sequence-aware Tier1/Tier2/grading. Component 3 (walk-forward) splits data chronologically and flags persistent patterns. Components 2 and 3 can be built in parallel.

**Tech Stack:** Python 3.x, pandas, numpy. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-15-batch-sequence-walkforward-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `gann-visualizer/backend/run_batch_simulation.py` | Batch runner script |
| Modify | `gann-visualizer/backend/run_simulation.py` | Add `--scale-ratio` CLI flag and parameter passthrough |
| Modify | `gann-visualizer/backend/analysis/trace_miner.py` | Add `build_fan_sequences()` |
| Modify | `gann-visualizer/backend/analysis/pattern_miner.py` | Add sequence miner functions + walk_forward_validate |

No new files in `analysis/`. No changes to existing functions.

---

### Task 1: Add --scale-ratio flag to run_simulation.py

**Files:**
- Modify: `gann-visualizer/backend/run_simulation.py:184-222` and `gann-visualizer/backend/run_simulation.py:517-530`

- [ ] **Step 1: Add scale_ratio parameter to run_simulation() and use it when provided**

In `run_simulation()`, add `scale_ratio=None` parameter. When provided (not None), skip `get_dynamic_scale_ratio()` and use the given value. Also add the CLI argument.

**Change 1: Add parameter to function signature (line 184):**

```python
def run_simulation(symbol="^NSEI", resolution="4", data_source="yfinance", from_date=None, to_date=None, lookback_bars=5000, left_bars=5, right_bars=5, warmup_days=0, timezone="UTC", scale_ratio=None):
```

**Change 2: Replace lines 203-211 (scale_ratio resolution block) with:**

```python
    # Get dynamic scale ratio just like the frontend (or use override)
    if scale_ratio is not None:
        logging.info(f"Using override scale_ratio: {scale_ratio}")
    else:
        try:
            # The frontend passes "NIFTY 50" to get_dynamic_scale_ratio even if the YFinance symbol is "^NSEI"
            config_symbol = "NIFTY 50" if symbol == "^NSEI" else symbol
            scale_ratio = get_dynamic_scale_ratio(config_symbol, resolution)
            logging.info(f"Dynamically resolved scale_ratio for {config_symbol} at {resolution}m: {scale_ratio}")
        except Exception as e:
            logging.warning(f"Failed to get dynamic scale ratio: {e}. Falling back to 3.6603")
            scale_ratio = 3.6603
```

**Change 3: Add CLI argument (after line 527):**

```python
    parser.add_argument("--scale-ratio", type=float, default=None, help="Override scale_ratio from ticker_config.json. Required for tickers without config entries.")
```

**Change 4: Pass scale_ratio through in the main block (line 532-543):**

```python
    run_simulation(
        symbol=args.symbol,
        resolution=args.resolution,
        data_source=args.source,
        from_date=args.from_date,
        to_date=args.to_date,
        lookback_bars=args.lookback,
        left_bars=args.left_bars,
        right_bars=args.right_bars,
        warmup_days=args.warmup_days,
        timezone=args.timezone,
        scale_ratio=args.scale_ratio,
    )
```

- [ ] **Step 2: Verify the flag works**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python run_simulation.py --help | grep scale-ratio
```

Expected: `--scale-ratio SCALE_RATIO    Override scale_ratio from ticker_config.json.`

- [ ] **Step 3: Commit**

```bash
cd /c/Dev/GannTesting
git add gann-visualizer/backend/run_simulation.py
git commit -m "feat: add --scale-ratio CLI flag to run_simulation.py"
```

---

### Task 2: Create batch simulation runner

**Files:**
- Create: `gann-visualizer/backend/run_batch_simulation.py`

- [ ] **Step 1: Create the batch runner script**

```python
"""
Batch Simulation Runner — Runs run_simulation.py across multiple tickers/timeframes.

Usage:
    python run_batch_simulation.py --tickers BTCUSDT,ETHUSDT --timeframes 60
    python run_batch_simulation.py --tickers SOLUSDT --timeframes 60 --scale-ratio 54.905
    python run_batch_simulation.py --tickers BTCUSDT --timeframes 60,240 --force
"""
import subprocess
import sys
import os
import argparse
import time

TRACE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "logs", "backend")


def run_batch(tickers, timeframes, scale_ratio=None, force=False):
    """Run simulation for each ticker x timeframe combination."""
    total = len(tickers) * len(timeframes)
    completed = 0
    failed = []

    print(f"Batch: {total} runs ({len(tickers)} tickers x {len(timeframes)} timeframes)")
    print("=" * 60)

    for ticker in tickers:
        for tf in timeframes:
            trace_file = os.path.join(TRACE_DIR, f"simulation_trace_{ticker}_{tf}.log")

            if os.path.exists(trace_file) and not force:
                print(f"SKIP: {ticker} {tf} — trace log already exists")
                completed += 1
                continue

            print(f"RUN : {ticker} {tf} ...", end=" ", flush=True)

            cmd = [
                sys.executable, "run_simulation.py",
                "--symbol", ticker,
                "--resolution", tf,
                "--source", "binance",
            ]
            if scale_ratio is not None:
                cmd.extend(["--scale-ratio", str(scale_ratio)])

            t0 = time.time()

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                       cwd=os.path.dirname(os.path.abspath(__file__)))
                elapsed = time.time() - t0

                if result.returncode != 0:
                    print(f"FAIL (exit={result.returncode}, {elapsed:.0f}s)")
                    print(f"  stderr: {result.stderr[-300:] if result.stderr else 'none'}")
                    failed.append((ticker, tf))
                    continue

                # Check trace log was created
                if not os.path.exists(trace_file):
                    print(f"FAIL (no trace log, {elapsed:.0f}s)")
                    failed.append((ticker, tf))
                    continue

                # Quick event count check
                event_count = 0
                with open(trace_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if "| event_type:" in line and "SNAPSHOT" not in line:
                            event_count += 1

                print(f"DONE ({elapsed:.0f}s, {event_count} events)")
                completed += 1

            except subprocess.TimeoutExpired:
                print(f"FAIL (timeout after 600s)")
                failed.append((ticker, tf))
            except Exception as e:
                print(f"FAIL ({e})")
                failed.append((ticker, tf))

    print("=" * 60)
    print(f"Completed: {completed}/{total}")

    if failed:
        print(f"Failed ({len(failed)}):")
        for t, f in failed:
            print(f"  - {t} {f}")

    return len(failed) == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch Gann Angular Price Coverage Simulation")
    parser.add_argument("--tickers", type=str, required=True,
                        help="Comma-separated ticker symbols (e.g., BTCUSDT,ETHUSDT)")
    parser.add_argument("--timeframes", type=str, required=True,
                        help="Comma-separated resolution codes (e.g., 60,240)")
    parser.add_argument("--scale-ratio", type=float, default=None,
                        help="Override scale_ratio for all runs")
    parser.add_argument("--force", action="store_true",
                        help="Re-run even if trace log already exists")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]

    if not tickers or not timeframes:
        print("ERROR: --tickers and --timeframes are required")
        sys.exit(1)

    # Ensure trace directory exists
    os.makedirs(TRACE_DIR, exist_ok=True)

    success = run_batch(tickers, timeframes, args.scale_ratio, args.force)
    sys.exit(0 if success else 1)
```

- [ ] **Step 2: Verify it runs with 1 ticker**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python run_batch_simulation.py --tickers BTCUSDT --timeframes 60
```

Expected: SKIP (trace log for BTCUSDT 60 already exists). If not, it runs and produces the log.

- [ ] **Step 3: Commit**

```bash
cd /c/Dev/GannTesting
git add gann-visualizer/backend/run_batch_simulation.py
git commit -m "feat: add batch simulation runner for multi-ticker trace generation"
```

---

### Task 3: Add build_fan_sequences() to trace_miner.py

**Files:**
- Modify: `gann-visualizer/backend/analysis/trace_miner.py` (append after `build_sequences()`)

- [ ] **Step 1: Append build_fan_sequences() function**

Append after `build_sequences()` (after line 293 in trace_miner.py):

```python
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
```

- [ ] **Step 2: Verify build_fan_sequences() produces valid output**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python -c "
from analysis.trace_miner import parse_trace, build_fan_sequences

events_df, candles_df, catalog = parse_trace('../../logs/backend/simulation_trace.log')
fan_seqs = build_fan_sequences(events_df)
print(f'Fans with sequences: {len(fan_seqs)}')
for fan_id in sorted(fan_seqs.keys())[:3]:
    seq = fan_seqs[fan_id]
    print(f'  {fan_id}: {len(seq)} events, first at bar {seq[0][\"bar_index\"]}')
    # Show first 3 events and their line fractions
    for evt in seq[:3]:
        print(f'    bar={evt[\"bar_index\"]}, type={evt[\"event_type\"]}, frac={evt[\"line_fraction\"]}')
print('PASS')
"
```

Expected: Multiple fans. Each fan shows events possibly at different line fractions (not all same).

- [ ] **Step 3: Commit**

```bash
cd /c/Dev/GannTesting
git add gann-visualizer/backend/analysis/trace_miner.py
git commit -m "feat: add build_fan_sequences() for cross-line 2-event sequence mining"
```

---

### Task 4: Add extract_sequence_pairs() to pattern_miner.py

**Files:**
- Modify: `gann-visualizer/backend/analysis/pattern_miner.py` (append at end)

- [ ] **Step 1: Append extract_sequence_pairs() function**

```python
def extract_sequence_pairs(fan_sequences: dict, max_gap: int = 10) -> pd.DataFrame:
    """
    Extract consecutive 2-event pairs from fan-based sequences.

    For each fan's event sequence, takes every consecutive pair of events,
    filters by bar gap <= max_gap, and returns a DataFrame of unique
    (event_type_1, event_type_2) combos with metadata.

    Args:
        fan_sequences: dict from build_fan_sequences() — {fan_id: [event dicts]}
        max_gap: Max bar_index gap between consecutive events (default 10)

    Returns:
        DataFrame with columns:
          fan_id, event_type_1, event_type_2, line_frac_1, line_frac_2,
          bar_index_1, bar_index_2, bar_gap
    """
    pairs = []
    for fan_id, seq in fan_sequences.items():
        for i in range(len(seq) - 1):
            evt_a = seq[i]
            evt_b = seq[i + 1]
            bar_gap = evt_b["bar_index"] - evt_a["bar_index"]
            if bar_gap < 1 or bar_gap > max_gap:
                continue
            pairs.append({
                "fan_id": fan_id,
                "event_type_1": evt_a["event_type"],
                "event_type_2": evt_b["event_type"],
                "line_frac_1": evt_a["line_fraction"],
                "line_frac_2": evt_b["line_fraction"],
                "bar_index_1": evt_a["bar_index"],
                "bar_index_2": evt_b["bar_index"],
                "bar_gap": bar_gap,
            })

    if not pairs:
        return pd.DataFrame(columns=[
            "fan_id", "event_type_1", "event_type_2", "line_frac_1", "line_frac_2",
            "bar_index_1", "bar_index_2", "bar_gap"
        ])

    return pd.DataFrame(pairs)
```

- [ ] **Step 2: Verify pair extraction produces output**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python -c "
from analysis.trace_miner import parse_trace, build_fan_sequences
from analysis.pattern_miner import extract_sequence_pairs

events_df, _, _ = parse_trace('../../logs/backend/simulation_trace.log')
fan_seqs = build_fan_sequences(events_df)
pairs_df = extract_sequence_pairs(fan_seqs)

print(f'Total pairs: {len(pairs_df)}')
if len(pairs_df) > 0:
    print(f'Columns: {list(pairs_df.columns)}')
    # Show unique combos
    combos = pairs_df.groupby(['event_type_1', 'event_type_2']).size().sort_values(ascending=False)
    print(f'Unique combos: {len(combos)}')
    print(combos.head(10).to_string())
    # Verify cross-line pairs exist
    cross_line = pairs_df[pairs_df['line_frac_1'] != pairs_df['line_frac_2']]
    print(f'Cross-line pairs: {len(cross_line)}/{len(pairs_df)}')
    assert len(pairs_df) > 0
    assert len(cross_line) > 0, 'No cross-line pairs found — Option B needs these'
    print('PASS')
"
```

Expected: Non-zero pairs, at least some cross-line pairs (different line_fraction between events 1 and 2).

- [ ] **Step 3: Commit**

```bash
cd /c/Dev/GannTesting
git add gann-visualizer/backend/analysis/pattern_miner.py
git commit -m "feat: add extract_sequence_pairs() for 2-event sequence pair discovery"
```

---

### Task 5: Add run_sequence_tier1() to pattern_miner.py

**Files:**
- Modify: `gann-visualizer/backend/analysis/pattern_miner.py` (append at end)

- [ ] **Step 1: Append run_sequence_tier1() function**

```python
def run_sequence_tier1(events_df: pd.DataFrame, pair_df: pd.DataFrame,
                       min_sample: int = 5, min_win_rate: float = 0.50) -> pd.DataFrame:
    """
    Tier 1 screening for 2-event sequence patterns.

    For each unique (event_type_1, event_type_2) combo, compute forward-return
    stats using the 2nd event as the entry point. Reuses compute_pattern_stats().

    Args:
        events_df: Enriched events DataFrame
        pair_df: DataFrame from extract_sequence_pairs()
        min_sample: Minimum occurrences for a combo to be considered
        min_win_rate: Minimum forward win rate

    Returns:
        DataFrame sorted by composite score, columns: pattern, event_type_1,
        event_type_2, sample_count, mean_mfe_10, mean_mae_10, win_rate, composite,
        p25_mfe_10, p50_mfe_10, p75_mfe_10
    """
    if pair_df.empty:
        return pd.DataFrame()

    results = []

    combos = pair_df.groupby(["event_type_1", "event_type_2"])

    for (et1, et2), group in combos:
        # Use bar_index of the 2nd event to look up forward returns
        bar_indices = group["bar_index_2"].tolist()
        mask = events_df["bar_index"].isin(bar_indices) & (~events_df["is_retro"])
        stats = compute_pattern_stats(events_df, mask)

        pattern_name = f"{et1}→{et2}"
        if stats["sample_count"] >= min_sample and stats["win_rate"] >= min_win_rate:
            results.append({
                "pattern": pattern_name,
                "event_type_1": et1,
                "event_type_2": et2,
                "sequence_type": "pair",
                **stats,
            })

    if not results:
        return pd.DataFrame()

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values("composite", ascending=False).reset_index(drop=True)
    return results_df
```

- [ ] **Step 2: Verify Tier 1 produces sequence patterns**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python -c "
from analysis.trace_miner import parse_trace, build_fan_sequences, enrich_forward_returns
from analysis.pattern_miner import extract_sequence_pairs, run_sequence_tier1

events_df, candles_df, _ = parse_trace('../../logs/backend/simulation_trace.log')
events_df = enrich_forward_returns(events_df, candles_df)
fan_seqs = build_fan_sequences(events_df)
pairs_df = extract_sequence_pairs(fan_seqs)
seq_tier1 = run_sequence_tier1(events_df, pairs_df)

print(f'Sequence patterns found: {len(seq_tier1)}')
if len(seq_tier1) > 0:
    cols = ['pattern', 'sample_count', 'win_rate', 'mean_mfe_10', 'composite']
    existing = [c for c in cols if c in seq_tier1.columns]
    print(seq_tier1[existing].head(10).to_string())
    print(f'Sequence type column: {\"sequence_type\" in seq_tier1.columns}')
    assert len(seq_tier1) > 0
    print('PASS')
"
```

Expected: Non-zero sequence patterns with win_rate > 50%, sample_count >= 5.

- [ ] **Step 3: Commit**

```bash
cd /c/Dev/GannTesting
git add gann-visualizer/backend/analysis/pattern_miner.py
git commit -m "feat: add run_sequence_tier1() for 2-event pair Tier 1 screening"
```

---

### Task 6: Add run_sequence_tier2() to pattern_miner.py

**Files:**
- Modify: `gann-visualizer/backend/analysis/pattern_miner.py` (append at end)

- [ ] **Step 1: Append run_sequence_tier2() function**

```python
def run_sequence_tier2(events_df: pd.DataFrame, tier1_df: pd.DataFrame,
                       pair_df: pd.DataFrame, fan_line_catalog: dict) -> pd.DataFrame:
    """
    Tier 2 line-reach validation for 2-event sequence patterns.

    Uses the 2nd event of each pair as the entry point for line-reach computation.

    Args:
        events_df: Enriched events DataFrame
        tier1_df: DataFrame from run_sequence_tier1()
        pair_df: DataFrame from extract_sequence_pairs()
        fan_line_catalog: Catalog from parse_trace()

    Returns:
        tier1_df with line_reach_rate columns appended, sorted by composite, top 20.
    """
    if tier1_df.empty or pair_df.empty:
        return pd.DataFrame()

    results = []

    for _, candidate in tier1_df.iterrows():
        et1 = candidate["event_type_1"]
        et2 = candidate["event_type_2"]

        # Find all 2nd-event bar indices for this combo
        combo_pairs = pair_df[(pair_df["event_type_1"] == et1) & (pair_df["event_type_2"] == et2)]
        bar_indices = combo_pairs["bar_index_2"].tolist()

        mask = events_df["bar_index"].isin(bar_indices) & (~events_df["is_retro"])
        reach = compute_line_reach(events_df, mask, fan_line_catalog)

        row = candidate.to_dict()
        row.update(reach)
        results.append(row)

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values("composite", ascending=False).head(20)
    return results_df
```

- [ ] **Step 2: Verify Tier 2 adds line_reach to sequence patterns**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python -c "
from analysis.trace_miner import parse_trace, build_fan_sequences, enrich_forward_returns
from analysis.pattern_miner import extract_sequence_pairs, run_sequence_tier1, run_sequence_tier2

events_df, candles_df, catalog = parse_trace('../../logs/backend/simulation_trace.log')
events_df = enrich_forward_returns(events_df, candles_df)
fan_seqs = build_fan_sequences(events_df)
pairs_df = extract_sequence_pairs(fan_seqs)
seq_tier1 = run_sequence_tier1(events_df, pairs_df)
seq_tier2 = run_sequence_tier2(events_df, seq_tier1, pairs_df, catalog)

print(f'Sequence Tier 2 candidates: {len(seq_tier2)}')
if len(seq_tier2) > 0:
    cols = ['pattern', 'sample_count', 'composite', 'line_reach_rate_10']
    existing = [c for c in cols if c in seq_tier2.columns]
    print(seq_tier2[existing].to_string())
    assert 'line_reach_rate_10' in seq_tier2.columns
    print('PASS')
"
```

Expected: Tier 2 output with line_reach_rate_10 column present.

- [ ] **Step 3: Commit**

```bash
cd /c/Dev/GannTesting
git add gann-visualizer/backend/analysis/pattern_miner.py
git commit -m "feat: add run_sequence_tier2() for 2-event pair line-reach validation"
```

---

### Task 7: Add grade_sequences() to pattern_miner.py

**Files:**
- Modify: `gann-visualizer/backend/analysis/pattern_miner.py` (append at end)

- [ ] **Step 1: Append grade_sequences() function**

```python
def grade_sequences(tier1_df: pd.DataFrame, tier2_df: pd.DataFrame) -> pd.DataFrame:
    """
    Grade 2-event sequence patterns into A/B/C tiers.

    Reuses the same grading logic as grade_patterns() for single events.
    See grade_patterns() docstring for grading rules.

    Returns:
        DataFrame with grade column, sorted by grade (A first) then composite desc.
    """
    return grade_patterns(tier1_df, tier2_df)
```

- [ ] **Step 2: Verify grading works on sequence patterns**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python -c "
from analysis.trace_miner import parse_trace, build_fan_sequences, enrich_forward_returns
from analysis.pattern_miner import extract_sequence_pairs, run_sequence_tier1, run_sequence_tier2, grade_sequences

events_df, candles_df, catalog = parse_trace('../../logs/backend/simulation_trace.log')
events_df = enrich_forward_returns(events_df, candles_df)
fan_seqs = build_fan_sequences(events_df)
pairs_df = extract_sequence_pairs(fan_seqs)
seq_tier1 = run_sequence_tier1(events_df, pairs_df)
seq_tier2 = run_sequence_tier2(events_df, seq_tier1, pairs_df, catalog)
seq_graded = grade_sequences(seq_tier1, seq_tier2)

print(f'Graded sequences: {len(seq_graded)}')
if len(seq_graded) > 0:
    cols = ['pattern', 'grade', 'win_rate', 'composite', 'line_reach_rate_10']
    existing = [c for c in cols if c in seq_graded.columns]
    print(seq_graded[existing].to_string())
    assert 'grade' in seq_graded.columns
    print('PASS')
"
```

Expected: Graded sequences with A/B/C grades.

- [ ] **Step 3: Commit**

```bash
cd /c/Dev/GannTesting
git add gann-visualizer/backend/analysis/pattern_miner.py
git commit -m "feat: add grade_sequences() — delegates to grade_patterns for 2-event pairs"
```

---

### Task 8: Add walk_forward_validate() to pattern_miner.py

**Files:**
- Modify: `gann-visualizer/backend/analysis/pattern_miner.py` (append at end)

- [ ] **Step 1: Append walk_forward_validate() function**

```python
def walk_forward_validate(events_df: pd.DataFrame, candles_df: pd.DataFrame,
                          fan_line_catalog: dict, train_pct: float = 0.7) -> pd.DataFrame:
    """
    Walk-forward validation: mine patterns on train set, evaluate on test set.

    Splits events_df chronologically by bar_index (earliest bars = train).
    Runs full single-event pipeline on train, then evaluates each pattern
    on the test set using the same mask.

    Args:
        events_df: Enriched events DataFrame
        candles_df: OHLC candles DataFrame (for enrichment, not directly used here)
        fan_line_catalog: Catalog from parse_trace()
        train_pct: Fraction of bars for training (default 0.7)

    Returns:
        DataFrame with columns: pattern, grade, train_composite, test_composite,
        train_win_rate, test_win_rate, train_samples, test_samples, persistent (bool).
        Sorted by train_composite descending.
    """
    non_retro = events_df[~events_df["is_retro"]].copy()
    non_retro = non_retro.sort_values("bar_index").reset_index(drop=True)

    # Chronological split: first train_pct of bars → train, rest → test
    n = len(non_retro)
    split_idx = int(n * train_pct)
    if split_idx < 20 or n - split_idx < 20:
        raise ValueError(f"Not enough events for split: train={split_idx}, test={n - split_idx}")

    train_events = non_retro.iloc[:split_idx].copy()
    test_events = non_retro.iloc[split_idx:].copy()

    # Run full pipeline on train
    tier1_train = run_tier1(train_events)
    if tier1_train.empty:
        return pd.DataFrame()

    tier2_train = run_tier2(train_events, tier1_train, fan_line_catalog)
    graded_train = grade_patterns(tier1_train, tier2_train)

    if graded_train.empty:
        return pd.DataFrame()

    # Evaluate each train pattern on test set
    results = []
    for _, pattern_row in graded_train.iterrows():
        et = pattern_row["event_type"]
        frac = pattern_row["line_fraction"]
        cp = pattern_row.get("candle_pattern", "any")

        mask_train = (train_events["event_type"] == et) & (train_events["line_fraction"] == str(frac))
        if cp and cp != "any":
            mask_train = mask_train & (train_events["candle_pattern"] == cp)

        mask_test = (test_events["event_type"] == et) & (test_events["line_fraction"] == str(frac))
        if cp and cp != "any":
            mask_test = mask_test & (test_events["candle_pattern"] == cp)

        train_stats = compute_pattern_stats(train_events, mask_train)
        test_stats = compute_pattern_stats(test_events, mask_test)

        # Persistence: test stats within 80% of train
        persistent = (
            test_stats["sample_count"] >= 5
            and test_stats["win_rate"] >= train_stats["win_rate"] * 0.8
            and test_stats["composite"] >= train_stats["composite"] * 0.8
        )

        results.append({
            "pattern": pattern_row["pattern"],
            "grade": pattern_row.get("grade", "?"),
            "train_composite": train_stats["composite"],
            "test_composite": test_stats["composite"],
            "train_win_rate": train_stats["win_rate"],
            "test_win_rate": test_stats["win_rate"],
            "train_samples": train_stats["sample_count"],
            "test_samples": test_stats["sample_count"],
            "persistent": persistent,
        })

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values("train_composite", ascending=False).reset_index(drop=True)
    return results_df
```

- [ ] **Step 2: Verify walk-forward produces persistence flags**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python -c "
from analysis.trace_miner import parse_trace, enrich_forward_returns
from analysis.pattern_miner import walk_forward_validate

events_df, candles_df, catalog = parse_trace('../../logs/backend/simulation_trace.log')
events_df = enrich_forward_returns(events_df, candles_df)

wf = walk_forward_validate(events_df, candles_df, catalog)
print(f'Walk-forward patterns: {len(wf)}')
if len(wf) > 0:
    cols = ['pattern', 'grade', 'train_composite', 'test_composite', 'persistent']
    existing = [c for c in cols if c in wf.columns]
    print(wf[existing].to_string())

    persistent_count = wf['persistent'].sum()
    print(f'\nPersistent patterns: {persistent_count}/{len(wf)}')

    # Verify: persistent is boolean
    assert wf['persistent'].dtype == bool

    # Verify: train and test values differ (meaningful split)
    assert not (wf['train_composite'] == wf['test_composite']).all(), 'Train/Test composites identical'

    assert len(wf) > 0
    print('PASS')
"
```

Expected: Walk-forward DataFrame with persistent boolean column. At least some patterns should persist. Train/test composite values differ.

- [ ] **Step 3: Commit**

```bash
cd /c/Dev/GannTesting
git add gann-visualizer/backend/analysis/pattern_miner.py
git commit -m "feat: add walk_forward_validate() for out-of-sample pattern persistence"
```

---

### Task 9: End-to-end verification — all 3 components

**Files:**
- None (verification only)

- [ ] **Step 1: Run full end-to-end pipeline**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python -c "
from analysis.trace_miner import parse_trace, build_fan_sequences, enrich_forward_returns
from analysis.pattern_miner import (
    extract_sequence_pairs, run_sequence_tier1, run_sequence_tier2,
    grade_sequences, walk_forward_validate
)

events_df, candles_df, catalog = parse_trace('../../logs/backend/simulation_trace.log')
events_df = enrich_forward_returns(events_df, candles_df)

print('=== Component 1: Batch Runner ===')
# Already verified via run_batch_simulation.py execution
print('SKIP (verified in Task 2)')

print('\n=== Component 2: Sequence Mining ===')
fan_seqs = build_fan_sequences(events_df)
pairs_df = extract_sequence_pairs(fan_seqs)
print(f'Pairs extracted: {len(pairs_df)}')
assert len(pairs_df) > 0

seq_tier1 = run_sequence_tier1(events_df, pairs_df)
print(f'Sequence Tier 1: {len(seq_tier1)} patterns')
assert len(seq_tier1) > 0

seq_tier2 = run_sequence_tier2(events_df, seq_tier1, pairs_df, catalog)
print(f'Sequence Tier 2: {len(seq_tier2)} patterns')

seq_graded = grade_sequences(seq_tier1, seq_tier2)
print(f'Graded sequences: {len(seq_graded)}')
for grade in ['A', 'B', 'C']:
    count = (seq_graded['grade'] == grade).sum() if 'grade' in seq_graded.columns else 0
    print(f'  Grade {grade}: {count}')

print('\n=== Component 3: Walk-Forward ===')
wf = walk_forward_validate(events_df, candles_df, catalog)
print(f'Walk-forward patterns: {len(wf)}')
persistent = wf['persistent'].sum() if len(wf) > 0 else 0
print(f'Persistent: {persistent}/{len(wf)}')

print('\n=== ALL COMPONENTS VERIFIED ===')
"
```

Expected: All 3 components produce valid output. Sequence Tier 1 > 0. Walk-forward produces non-empty results.

- [ ] **Step 2: Commit**

```bash
cd /c/Dev/GannTesting
git add .
git commit -m "test: end-to-end verification of batch runner, sequence miner, walk-forward"
```

---

## Self-Review Checklist

**1. Spec coverage:**

| Spec Section | Task(s) |
|---|---|
| 4.1 Batch Simulation Runner | Task 2 |
| 4.2 --scale-ratio flag | Task 1 |
| 4.3.1 build_fan_sequences() | Task 3 |
| 4.3.2 extract_sequence_pairs() | Task 4 |
| 4.3.2 run_sequence_tier1() | Task 5 |
| 4.3.2 run_sequence_tier2() | Task 6 |
| 4.3.2 grade_sequences() | Task 7 |
| 4.4 walk_forward_validate() | Task 8 |
| End-to-end (section 7) | Task 9 |

All spec sections covered.

**2. Placeholder scan:** No TBD, TODO, or incomplete steps. All code provided inline. All verification commands are complete and executable.

**3. Type consistency:**
- `fan_sequences` consistently `{fan_id: [event dicts]}` across Tasks 3-7
- `pair_df` columns consistent across Tasks 4-6: `event_type_1, event_type_2, bar_index_2`
- `fan_line_catalog` passed through to Tier 2 (Task 6) and walk_forward (Task 8)
- `walk_forward_validate()` signature includes `fan_line_catalog` (fixed from initial spec draft)
- `grade_sequences()` delegates to `grade_patterns()` — same return type guaranteed
