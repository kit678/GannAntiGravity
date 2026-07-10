# Trade Discovery Mining Implementation Plan

> **For agentic workers:** Execute this plan phase-by-phase. Keep the first version narrowly focused on trade-based discovery from existing run artifacts. Do not expand scope into live trading, portfolio sizing, or black-box strategy automation.

**Goal:** Build a trade-discovery pipeline that mines existing Gann simulation artifacts for readable, tradeable patterns using **actual realized trade outcomes only**.

**Architecture:** Four core modules plus one run-level output directory. The pipeline loads existing run artifacts, builds a trade-candidate feature table, labels rows with realized trade results, mines readable rules, validates them chronologically, and exports promoted candidate strategies for follow-up testing in the hypothesis framework.

**Tech Stack:** Python 3.x, pandas, numpy, existing backend analysis stack. Optional ML phase may use scikit-learn only if already available in the project environment; otherwise defer ML until after rule mining is stable.

**Spec:** `docs/superpowers/specs/2026-07-09-trade-discovery-mining-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| **Create** | `gann-visualizer/backend/analysis/trade_feature_builder.py` | Load run artifacts, define candidate universe, build feature table |
| **Create** | `gann-visualizer/backend/analysis/trade_rule_miner.py` | Rule mining, ranking, rule summaries |
| **Create** | `gann-visualizer/backend/analysis/trade_discovery_runner.py` | End-to-end CLI runner and output orchestration |
| **Create** | `gann-visualizer/backend/analysis/trade_ml_ranker.py` | Optional second-pass ML ranking and feature importance |
| **Modify (if needed)** | `gann-visualizer/backend/analysis/exit_optimizer.py` | Reuse helpers for realized trade labels; only touch if reuse requires extraction/refactor |
| **Modify (if needed)** | `gann-visualizer/backend/analysis/hypothesis_framework.py` | Reuse output helpers only if necessary; avoid mixing discovery logic into the hypothesis runner |

Output directory per run:

- `logs/backend/runs/<symbol>/<tf>/<run_id>/analysis/trade_discovery/`

Primary output files:

- `trade_candidates.csv`
- `mined_rules.csv`
- `walk_forward_rules.csv`
- `top_candidates.json`
- `summary.txt`

---

## Phase 1: Build the Run Loader and Candidate Extractor

**Goal:** Produce a clean row-per-setup table from existing run artifacts, without adding new simulation-time logging yet.

**Files:**
- Create: `gann-visualizer/backend/analysis/trade_feature_builder.py`

- [ ] **Step 1: Implement run artifact loading**

Load:
- `events.csv`
- `candles.csv`
- trade-enriched hypothesis JSONs when available, especially bounce-follow-through variants that already contain entry/exit fields

Define a small loader API:

```python
load_run_artifacts(run_dir) -> {
    "events_df": ...,
    "candles_df": ...,
    "hypothesis_reports": {...},
}
```

- [ ] **Step 2: Define the first candidate universe**

First version should include only entry-style setups with clear trade semantics:
- `SUPPORT_BOUNCE`
- `RESISTANCE_REJECTION`
- trade-enriched bounce-follow-through report rows

Do not include every event type in v1.

- [ ] **Step 3: Build normalized candidate rows**

Each candidate row should include:
- symbol
- timeframe
- run id
- raw event timestamp
- test timestamp
- confirmation timestamp
- event type
- fan id / display
- anchor type
- fraction
- live vs retro

Use stable column naming from the start to avoid downstream rewrites.

- [ ] **Step 4: Verify**

Run the builder against a known BTCUSDT 15m run and confirm:
- non-empty output
- one row per candidate setup
- expected identity fields present

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/analysis/trade_feature_builder.py
git commit -m "feat: add trade candidate loader and extractor"
```

---

## Phase 2: Attach Realized Trade Labels

**Goal:** Ensure every candidate row is labeled from realized trade outcomes, not MFE-based proxy outcomes.

**Files:**
- Modify: `gann-visualizer/backend/analysis/trade_feature_builder.py`
- Modify only if required: `gann-visualizer/backend/analysis/exit_optimizer.py`

- [ ] **Step 1: Add trade label attachment**

Attach, per candidate:
- `entry_price`
- `entry_time`
- `entry_side`
- `exit_price`
- `exit_time`
- `exit_reason`
- `bars_held`
- `net_pnl`
- `pnl_pct`
- `trade_win`

Priority order for labels:
1. existing trade-enriched hypothesis outputs
2. reusable optimizer / trade simulation helpers
3. only if needed, a narrowly scoped replay of trade logic

- [ ] **Step 2: Enforce trade-based truth**

Every downstream ranking field must derive from:
- `trade_win`
- `net_pnl`
- aggregated expectancy
- aggregated profit factor

MFE/MAE may be stored only as diagnostics and must not define the label.

- [ ] **Step 3: Verify**

Validate a sample of rows against an existing hypothesis JSON and confirm:
- timestamps match
- entry/exit prices match
- exit reason matches
- win/loss matches `net_pnl`

- [ ] **Step 4: Commit**

```bash
git add gann-visualizer/backend/analysis/trade_feature_builder.py gann-visualizer/backend/analysis/exit_optimizer.py
git commit -m "feat: attach realized trade labels to discovery candidates"
```

---

## Phase 3: Add Context and Bar-Structure Features

**Goal:** Enrich the candidate table with the minimum set of predictive features needed for rule discovery.

**Files:**
- Modify: `gann-visualizer/backend/analysis/trade_feature_builder.py`

- [ ] **Step 1: Add setup-context features**

Include:
- trend-aligned vs counter-trend
- fan direction / slope
- bars since anchor
- bars since prior event on same fan
- bars since prior event on same line
- zone / cluster / breach / rest state where recoverable
- line congestion summary
- distance to nearby supporting/opposing lines

- [ ] **Step 2: Add bar-structure features**

Include:
- test candle polarity
- confirmation candle polarity
- test/confirmation body size
- upper/lower wick ratios
- prior 1 to 5 bar returns
- prior 1 to 5 bar range expansion/contraction
- local volatility proxy

- [ ] **Step 3: Add sequence features**

Include:
- previous event type on same fan
- previous event type on same line
- recent event counts on same fan
- whether current touch is first / repeat / clustered

Keep sequence logic simple in v1. Use engineered columns, not a separate sequence miner.

- [ ] **Step 4: Verify**

Check that:
- feature columns are populated for most rows
- no post-exit information leaked into the feature set
- missing values are handled consistently

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/analysis/trade_feature_builder.py
git commit -m "feat: enrich discovery candidates with context and bar features"
```

---

## Phase 4: Build the Rule Miner

**Goal:** Discover readable rule combinations ranked by trade-based performance.

**Files:**
- Create: `gann-visualizer/backend/analysis/trade_rule_miner.py`

- [ ] **Step 1: Implement aggregate scoring helpers**

Add helpers to compute, per rule:
- sample size
- wins / losses
- win rate
- expectancy
- profit factor
- avg pnl
- avg pnl pct

Use conservative handling for divide-by-zero and tiny samples.

- [ ] **Step 2: Implement rule search**

First version should search:
- single-feature rules
- pairwise rules
- selected three-way combinations

Examples:
- event type + fraction
- anchor type + event type
- trend alignment + event type + fraction
- sequence state + fraction

Do not brute-force every possible combination in v1.

- [ ] **Step 3: Add ranking and gates**

Default ranking priority:
1. win rate
2. expectancy
3. profit factor
4. sample size

Default minimum gates:
- minimum total sample size
- minimum wins
- positive expectancy
- profit factor > 1.0

- [ ] **Step 4: Export plain-English rule summaries**

Each surviving rule should be convertible to a readable sentence such as:

`Support bounce on high-anchored fan at 0.875 with repeat-touch context`

- [ ] **Step 5: Verify**

Run the miner on a known BTCUSDT 15m feature table and confirm:
- non-empty mined rule table
- rules are readable
- top-ranked rules are trade-based

- [ ] **Step 6: Commit**

```bash
git add gann-visualizer/backend/analysis/trade_rule_miner.py
git commit -m "feat: add trade-based rule miner for discovery pipeline"
```

---

## Phase 5: Add Walk-Forward Validation

**Goal:** Reject rules that look good in-sample but fail chronologically out of sample.

**Files:**
- Modify: `gann-visualizer/backend/analysis/trade_rule_miner.py`

- [ ] **Step 1: Implement chronological train/test split**

Use time-ordered splitting only:
- earliest 70% -> train
- latest 30% -> test

Split by event/candidate timestamp, not shuffled rows.

- [ ] **Step 2: Re-score rules on train and test**

For each surviving train rule, compute on test:
- sample size
- win rate
- expectancy
- profit factor

- [ ] **Step 3: Add persistence flag**

A rule is persistent only if:
- test sample size is adequate
- test expectancy remains positive
- test PF remains above threshold
- test win rate does not collapse materially vs train

- [ ] **Step 4: Verify**

Run on one known run and confirm:
- clear train/test columns
- persistent and rejected rules separated cleanly

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/analysis/trade_rule_miner.py
git commit -m "feat: add walk-forward validation to trade discovery rules"
```

---

## Phase 6: Build the End-to-End Runner and Outputs

**Goal:** Make the pipeline runnable on a single run directory with clean outputs.

**Files:**
- Create: `gann-visualizer/backend/analysis/trade_discovery_runner.py`

- [ ] **Step 1: Create CLI entry point**

Recommended interface:

```bash
python -m analysis.trade_discovery_runner --run-dir <run_dir>
```

Optional flags:
- `--min-sample`
- `--top-n`
- `--include-retro`
- `--skip-ml`

- [ ] **Step 2: Wire phases together**

Pipeline order:
1. load artifacts
2. build candidates
3. attach labels
4. enrich features
5. mine rules
6. validate rules
7. write outputs

- [ ] **Step 3: Write output files**

Write to:
- `analysis/trade_discovery/trade_candidates.csv`
- `analysis/trade_discovery/mined_rules.csv`
- `analysis/trade_discovery/walk_forward_rules.csv`
- `analysis/trade_discovery/top_candidates.json`
- `analysis/trade_discovery/summary.txt`

- [ ] **Step 4: Verify**

Run the full pipeline on a known BTCUSDT 15m run and confirm all outputs are created and internally consistent.

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/analysis/trade_discovery_runner.py
git commit -m "feat: add end-to-end trade discovery runner"
```

---

## Phase 7: Optional ML Ranking Layer

**Goal:** Add a second-pass discovery aid without turning the strategy into a black box.

**Files:**
- Create: `gann-visualizer/backend/analysis/trade_ml_ranker.py`

- [ ] **Step 1: Add a simple baseline model**

Recommended order:
- logistic regression baseline
- random forest
- gradient-boosted trees if environment supports them cleanly

- [ ] **Step 2: Use ML only for support**

Outputs should be:
- feature importance
- high-confidence segments
- candidate interactions worth converting into explicit rules

Do not allow the raw model prediction itself to become the final trading strategy in v1.

- [ ] **Step 3: Verify**

Check that ML output aligns with discovered rule families rather than contradicting them arbitrarily.

- [ ] **Step 4: Commit**

```bash
git add gann-visualizer/backend/analysis/trade_ml_ranker.py
git commit -m "feat: add optional ML ranker for trade discovery"
```

---

## Phase 8: Promotion Back Into Formal Hypotheses

**Goal:** Convert the best surviving mined rules into explicit, re-testable hypotheses.

**Files:**
- Modify later as needed: `gann-visualizer/backend/analysis/hypothesis_framework.py`

- [ ] **Step 1: Select top surviving rules**

Choose only candidates that:
- pass walk-forward
- have enough sample size
- remain readable
- are visually explainable

- [ ] **Step 2: Translate into explicit hypothesis definitions**

Each promoted rule should become a clear hypothesis with:
- event filter
- context filter
- trade logic
- trade-based scoring

- [ ] **Step 3: Re-run through existing hypothesis framework**

Use the current framework for:
- JSON outputs
- front-end review
- side-by-side comparison with existing hypotheses

This phase is intentionally last. Do not promote weak or unstable rules.

---

## Verification Checklist

- [ ] Candidate dataset uses actual trade labels, not MFE-based labels
- [ ] Rule ranking is trade-based
- [ ] Walk-forward is chronological
- [ ] Output files are created in the run directory
- [ ] Top rules are readable in plain English
- [ ] No feature leakage from post-exit fields
- [ ] Pipeline runs on at least one known BTCUSDT 15m run end to end

---

## Recommended Execution Order

1. Phase 1: loader + candidate extractor
2. Phase 2: realized trade labels
3. Phase 3: feature enrichment
4. Phase 4: rule miner
5. Phase 5: walk-forward validation
6. Phase 6: end-to-end runner
7. Phase 7: optional ML ranking
8. Phase 8: promote survivors into formal hypotheses

## Recommended First Milestone

The best first milestone is:

> Produce `trade_candidates.csv` for one known BTCUSDT 15m run, with correct actual trade labels attached.

That milestone gives us the foundation for everything else and will quickly tell us whether the pipeline is grounded correctly.
