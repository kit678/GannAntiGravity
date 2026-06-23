# Unified Hypothesis Framework — Design

**Date:** 2026-06-22
**Status:** Pending Review
**Owner:** kit678

## 1. Goal

Replace the scattered, inconsistent testing mechanisms with a single unified framework where every claim about market behavior is defined as a "Hypothesis," evaluated by the same runner, validated by walk-forward, and output in a consistent format.

**The question we're answering:** "What can we consistently trade in the market?"

## 2. Current State — Problems

| Problem | Details |
|---|---|
| Scattered tests | Reversal outcome in event_logger, 6 hypothesis classes in strategy_analyzer, walk-forward in pattern_miner, angle breakdowns done ad-hoc |
| Inconsistent win definitions | 3 different win semantics: MFE/MAE ratio, event-type WIN/MISS, pre-computed Reversal_Outcome |
| Inconsistent enrichment | Two parallel systems: event_logger (absolute price) vs trace_miner (percentage) |
| Copy-pasted logic | Live/retro split, result-dict assembly, win formula duplicated across 5+ classes |
| Broken contracts | MultiTFReversalHypothesis returns minimal dict; orchestrators use try/except TypeError to paper over signature mismatches |
| No validation | All win rates are in-sample; walk-forward exists in pattern_miner but is never run on hypotheses |
| No unified output | Reports in different directories, different formats, different schemas |

## 3. Architecture — Three Layers

```
Layer 1: METRICS (during simulation)
  event_logger.py → enrich_with_forward_outcomes()
    Computes: MFE_5/10/20/50, MAE_5/10/20/50, reversal_outcome (WIN/LOSS), body_break
    Stored in: hypothesis_events.json (per-event fields)

Layer 2: HYPOTHESES (post-simulation)
  analysis/hypothesis_framework.py → HypothesisRunner
    Runs all 7 hypotheses via unified evaluate() interface
    Each hypothesis: selects events → determines win → computes stats → returns standard dict

Layer 3: VALIDATION (post-hypotheses)
  analysis/hypothesis_framework.py → WalkForwardValidator
    Takes each hypothesis result, splits data 70/30 chronologically
    Reports: train_WR, test_WR, persistent (bool)
    Every hypothesis result includes walk-forward — no in-sample-only results
```

### Data Flow

```
run_simulation.py
  │
  ├── (during sim) event_logger.enrich_with_forward_outcomes()
  │     └── writes MFE/MAE/reversal_outcome/body_break into events
  │
  ├── (after sim) HypothesisRunner.run_all(events_df)
  │     ├── StrongSRHypothesis.evaluate(df)
  │     ├── QuarterReversalAnomalyHypothesis.evaluate(df)
  │     ├── ConfluenceBounceHypothesis.evaluate(df)
  │     ├── TargetProgressionHypothesis.evaluate(df)
  │     ├── PostBreachPullbackHypothesis.evaluate(df)
  │     ├── ReversalByAngleLineHypothesis.evaluate(df)    ← NEW
  │     └── BounceFollowThroughHypothesis.evaluate(df)     ← NEW
  │
  ├── (after hypotheses) WalkForwardValidator.validate_all(hypotheses, events_df)
  │     └── For each hypothesis: 70/30 split → train stats vs test stats → persistent flag
  │
  └── Output → analysis/hypotheses/
        ├── strong_sr_rule.json
        ├── quarter_reversal_anomaly.json
        ├── confluence_bounce.json
        ├── target_progression.json
        ├── post_breach_pullback.json
        ├── reversal_by_angle_line.json
        ├── bounce_follow_through.json
        └── run_summary.json          ← unified summary of all 7 + walk-forward
```

## 4. Layer 1 — Metrics (event_logger.py changes)

### 4.1 Remove TARGET_HIT from reversal_outcome

**Files:** `study_tool/event_logger.py` line 668, `run_simulation.py` `compute_first_break()`

Currently: `SUPPORT_TEST, RESISTANCE_TEST, TARGET_HIT`
Change to: `SUPPORT_TEST, RESISTANCE_TEST`

TARGET_HIT means price reached a target — not that it reversed. Including it muddies reversal data.

**Two code paths need this change:**
1. `event_logger.py` → `enrich_with_forward_outcomes()` — the primary enrichment during simulation
2. `run_simulation.py` → `compute_first_break()` — a secondary reversal check that writes to the CSV's `Reversal_Outcome` column

**Impact on QuarterReversalAnomalyHypothesis:** This hypothesis previously selected TARGET_HIT events (among others) and read their `Reversal_Outcome`. After this change, TARGET_HIT events will no longer have `Reversal_Outcome` set. The hypothesis must drop TARGET_HIT from its `_select_events()` filter — it will select only SUPPORT_TEST and RESISTANCE_TEST at 0.25. This is correct: the hypothesis tests whether 0.25 line tests reverse, not whether target hits reverse.

### 4.2 Add body_break field

**File:** `study_tool/event_logger.py`

For SUPPORT_TEST and RESISTANCE_TEST events, compute `body_break`:

- SUPPORT_TEST: `body_break = True` if next bar's close > test candle's close
- RESISTANCE_TEST: `body_break = True` if next bar's close < test candle's close
- If there is no next bar (last bar in data), `body_break = None`

This is a simpler confirmation signal than the threshold-based bounce. Stored as a per-event field in the event and exported to CSV/JSON.

### 4.3 SUPPORT_BOUNCE / RESISTANCE_REJECTION — no reversal_outcome

These events already confirm reversal. They get MFE/MAE (already computed) but NOT reversal_outcome. Their alpha is measured by the BounceFollowThrough hypothesis (Layer 2).

## 5. Layer 2 — Unified Hypothesis Framework

### 5.1 Refactored Base Class

**File:** `analysis/strategy_analyzer.py`

```python
class Hypothesis:
    """Base class for all trading hypotheses."""

    # Declared capabilities — subclasses override
    needs_candles: bool = False
    needs_fan_catalog: bool = False

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.parameters = {}

    def set_parameters(self, **kwargs):
        self.parameters.update(kwargs)

    def evaluate(self, df: pd.DataFrame, candles_df=None, fan_catalog=None) -> Dict[str, Any]:
        """
        Template method. Subclasses implement _select_events() and _is_win().
        Base class handles: live/retro split, stats computation, result assembly.
        """
        selected = self._select_events(df)
        if len(selected) == 0:
            return self._empty_result()

        # Compute win/loss per event using hypothesis-specific logic
        log = []
        for _, event in selected.iterrows():
            is_win = self._is_win(event, df, candles_df, fan_catalog)
            is_retro = "[Retro]" in str(event.get("Details", ""))
            log.append({
                **event.to_dict(),
                "hypothesis_win": is_win,
                "is_retro": is_retro,
            })

        return self._compute_stats(log)

    def _select_events(self, df: pd.DataFrame) -> pd.DataFrame:
        """Subclass: return filtered subset of events to test."""
        raise NotImplementedError

    def _is_win(self, event, df, candles_df, fan_catalog) -> bool:
        """Subclass: determine if this single event is a win."""
        raise NotImplementedError

    def _compute_stats(self, log: list) -> Dict[str, Any]:
        """Shared: compute sample_size, win_rate, live/retro split, MFE/MAE averages.
        
        Consolidates logic previously copy-pasted across 5 hypothesis classes:
        - Total: sample_size, win_rate (wins/total), avg_mfe_10, avg_mae_10
        - Live subset: events where "[Retro]" NOT in Details
        - Retro subset: events where "[Retro]" IN Details
        - composite = avg_mfe_10 * sqrt(sample_count) for walk-forward use
        - detailed_log: the full per-event list with hypothesis_win flag
        """

    def _empty_result(self) -> Dict[str, Any]:
        """Standard empty result when no events match."""
        return {
            "sample_size": 0, "win_rate": 0.0,
            "avg_mfe_10": 0.0, "avg_mae_10": 0.0,
            "live_sample_size": 0, "live_win_rate": 0.0,
            "retro_sample_size": 0, "retro_win_rate": 0.0,
            "detailed_log": [],
        }
```

**Key improvements:**
- Single `evaluate()` signature with declared capabilities (no more `try/except TypeError`)
- `_select_events()` and `_is_win()` are the only methods subclasses implement
- Live/retro split, stats, result dict — computed once in base class
- Win determination is pluggable per hypothesis

### 5.2 The 7 Hypotheses

| # | Class | _select_events | _is_win | Status |
|---|---|---|---|---|
| 1 | StrongSRHypothesis | SUPPORT_TEST, RESISTANCE_TEST | MFE_10 > max(MAE_10, 0.1) × ratio (default 2.0) | Refactor existing |
| 2 | QuarterReversalAnomalyHypothesis | Fraction==0.25, SUPPORT_TEST/RESISTANCE_TEST (TARGET_HIT dropped — see 4.1), with gating (prior 0.5 breach, no horizontal hit) | Reversal_Outcome == "WIN" | Refactor existing |
| 3 | ConfluenceBounceHypothesis | SUPPORT_TEST/RESISTANCE_TEST/TOUCH near other fan lines (within 0.2%) | MFE_10 > max(MAE_10, 0.1) × 2.0 | Refactor existing |
| 4 | TargetProgressionHypothesis | TARGET_HIT / TARGET_FAILED | TARGET_HIT = WIN, TARGET_FAILED = LOSS | Refactor existing |
| 5 | PostBreachPullbackHypothesis | BREACH_CONFIRMED → later SUPPORT_TEST/RESISTANCE_TEST on same line within 10 bars | MFE_10 > max(MAE_10, 0.1) × ratio on pullback test | Refactor existing |
| 6 | ReversalByAngleLineHypothesis | SUPPORT_TEST, RESISTANCE_TEST — grouped by Fraction (0.25, 0.5, 0.75, 0.875, horizontal) | Reversal_Outcome == "WIN" | **NEW** |
| 7 | BounceFollowThroughHypothesis | SUPPORT_BOUNCE, RESISTANCE_REJECTION | MFE_10 > max(MAE_10, 0.1) × ratio (default 1.5 — lower bar since bounce already confirmed) | **NEW** |

### 5.3 ReversalByAngleLineHypothesis (new)

Returns a grouped result — one stat block per angle line plus an overall aggregate.

**Implementation note:** This hypothesis overrides `_compute_stats()` in the base class. The base class computes overall stats; the override adds a `groups` dict with per-fraction breakdowns. The `evaluate()` template method still calls `_compute_stats(log)`, so the override receives the full log and can group by `Fraction` before computing stats per group.

```json
{
  "sample_size": 252,
  "win_rate": 0.56,
  "groups": {
    "0.25": {"sample_size": 41, "win_rate": 0.71, "avg_mfe_10": 1824, "avg_mae_10": 1233},
    "0.5": {"sample_size": 50, "win_rate": 0.52, "avg_mfe_10": 1500, "avg_mae_10": 1100},
    "0.75": {"sample_size": 82, "win_rate": 0.56, "avg_mfe_10": 1200, "avg_mae_10": 900},
    "0.875": {"sample_size": 33, "win_rate": 0.36, "avg_mfe_10": 800, "avg_mae_10": 1400},
    "horizontal": {"sample_size": 46, "win_rate": 0.61, "avg_mfe_10": 1600, "avg_mae_10": 1000}
  }
}
```

### 5.4 BounceFollowThroughHypothesis (new)

Tests whether confirmed bounces have sustained follow-through. Win = MFE_10 > MAE_10 × 1.5 (lower ratio than Strong SR because the bounce is already confirmed — we're testing momentum continuation, not initial reversal).

Returns separate stats for SUPPORT_BOUNCE and RESISTANCE_REJECTION, plus combined.

## 6. Layer 3 — Walk-Forward Validation

### 6.1 Mechanism

**File:** `analysis/hypothesis_framework.py` (new)

```python
class WalkForwardValidator:
    def validate(self, hypothesis: Hypothesis, df: pd.DataFrame,
                 train_pct: float = 0.7) -> Dict[str, Any]:
        """
        Split events chronologically by bar_index.
        Run hypothesis on train set, then on test set.
        Flag persistent if test stats hold within 80% of train.
        """
```

**Critical: Selection before split.** For cross-event hypotheses like PostBreachPullback (which needs to find BREACH_CONFIRMED → later SUPPORT_TEST pairs), splitting the df first would break pairs that span the boundary. Instead:

1. Call `hypothesis._select_events(df)` on the FULL df — this finds all qualifying event pairs
2. Split the SELECTED events chronologically by `bar_index` into train (70%) and test (30%)
3. Compute stats on train subset and test subset separately

This ensures pair-finding logic works on complete data, and only the final stats are split.

### 6.2 Persistence criteria

A hypothesis is "persistent" if ALL:
- `test_sample_count >= 5`
- `test_win_rate >= train_win_rate * 0.8`
- `test_composite >= train_composite * 0.8`

Where `composite = avg_mfe_10 * sqrt(sample_count)` (sample-size-weighted edge).

**Grouped hypotheses (e.g., ReversalByAngleLine):** Walk-forward validates the overall aggregate, not each subgroup. Subgroup stats in the output are in-sample only. This avoids overfitting individual angle lines to the test set.

### 6.3 Output per hypothesis

Every hypothesis JSON includes both in-sample and walk-forward results:

```json
{
  "hypothesis_name": "Strong SR Rule",
  "in_sample": {
    "sample_size": 199,
    "win_rate": 0.47,
    "avg_mfe_10": 1500,
    "avg_mae_10": 900
  },
  "walk_forward": {
    "train_sample_size": 139,
    "train_win_rate": 0.48,
    "test_sample_size": 60,
    "test_win_rate": 0.45,
    "persistent": true
  }
}
```

## 7. Unified Output

### 7.1 Directory structure

```
<run_dir>/
  hypothesis_events.json          ← per-event data with metrics (existing)
  events.csv                      ← per-event CSV (existing)
  analysis/
    hypotheses/
      strong_sr_rule.json
      quarter_reversal_anomaly.json
      confluence_bounce.json
      target_progression.json
      post_breach_pullback.json
      reversal_by_angle_line.json
      bounce_follow_through.json
      run_summary.json            ← combined summary
      run_summary.txt             ← human-readable
```

### 7.2 run_summary.txt format

*(Numbers below are illustrative examples, not actual results.)*

```
=== RUN SUMMARY: BTCUSDT 60m, 2025-04-01 to 2025-04-14 ===
Events: 1141 | Candles: 313 | Fans: 12

HYPOTHESIS RESULTS (in-sample | walk-forward)
─────────────────────────────────────────────────────────────
Hypothesis                    n    WR    WF:train  WF:test  Persistent
Strong SR Rule              199  47%    48%       45%      YES
1/4 Reversal Anomaly         15  67%    70%       60%      YES
Confluence Bounce           199  47%    48%       45%      YES
Target Progression           24  79%    75%       83%      YES
Post-Breach Pullback         17  35%    40%       25%      NO
Reversal by Angle Line      252  56%    55%       58%      YES
  0.25:                       41  71%
  0.5:                        50  52%
  0.75:                       82  56%
  0.875:                      33  36%
  horizontal:                 46  61%
Bounce Follow-Through        70  65%    68%       60%      YES
─────────────────────────────────────────────────────────────
PERSISTENT: 6/7
```

## 8. File Summary

| Action | File | What |
|--------|------|------|
| Modify | `study_tool/event_logger.py` | Remove TARGET_HIT from reversal check; add body_break field; export body_break to CSV and JSON |
| Modify | `analysis/strategy_analyzer.py` | Refactor Hypothesis base class with template method; refactor 5 existing subclasses; add ReversalByAngleLineHypothesis and BounceFollowThroughHypothesis |
| Create | `analysis/hypothesis_framework.py` | HypothesisRunner (loads events.csv, instantiates hypotheses, runs evaluate, writes output), WalkForwardValidator |
| Modify | `generate_hypothesis_reports.py` | Delegate to HypothesisRunner; output to analysis/hypotheses/ instead of timestamped hypothesis_reports/ subdirs; preserve CLI interface |
| Modify | `run_simulation.py` | Remove TARGET_HIT from `compute_first_break()`; call HypothesisRunner + WalkForwardValidator after simulation exports |

### 8.1 Data Loading

`HypothesisRunner` loads `events.csv` from the run directory into a pandas DataFrame (same as existing `StrategyAnalyzer.load_data`). The CSV already contains `MFE_10`, `MAE_10`, `Reversal_Outcome`, `bar_index`, and will now include `Body_Break`. No separate data loading path — hypotheses consume the same CSV that's already exported.

## 9. What Stays the Same

- `hypothesis_events.json` format — frontend still reads this for the navigator
- Event types and classification logic in `unified_state_machine.py`
- The 5 existing hypotheses' core logic — only refactored to use base class hooks
- `events.csv` columns — only adding `Body_Break` column

## 10. Migration Notes

- `phase1_edge_test.py` and `pattern_miner.py` are NOT changed in this iteration. They still work via the CSV adapter. Future iteration can migrate them to the unified framework.
- The old `hypothesis_reports/` directory (with timestamped subdirs) is replaced by `analysis/hypotheses/`. Old reports remain for backward compatibility.
- EMA Crossover and MultiTF Reversal are dropped from the auto-run suite. They can be re-added later when properly refactored.
- `generate_hypothesis_reports.py` CLI interface (`--all-timeframes`, `--4m`, `-H` flags) is preserved for manual use. It delegates to `HypothesisRunner` internally. The auto-run path in `run_simulation.py` calls `HypothesisRunner` directly.
