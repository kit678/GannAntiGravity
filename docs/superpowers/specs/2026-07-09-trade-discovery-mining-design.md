# Trade Discovery Mining Design

**Date:** 2026-07-09  
**Status:** Pending Review  
**Owner:** kit678

## 1. Goal

Design a discovery pipeline that mines the existing Gann event stream and candle data for tradeable patterns, scores them using **actual simulated trade outcomes only**, and promotes the best surviving patterns into formal, human-readable strategies.

The optimization priority is:

1. Highest trade-based win rate
2. Best expectancy
3. Best profit factor
4. Adequate sample size
5. Walk-forward persistence

This explicitly excludes MFE-only ranking. MFE/MAE may remain as diagnostic features, but never as the primary definition of strategy success.

## 2. Why This Is Needed

The current system has already tested many manually authored hypotheses through the unified framework in [hypothesis_framework.py](file:///c:/Dev/GannTesting/gann-visualizer/backend/analysis/hypothesis_framework.py). That work has been useful for narrowing the search space, but no single hand-authored hypothesis has shown a strong enough and stable enough edge.

The project now needs a discovery layer that can:

- leverage the current event stream and bar data
- look beyond pre-written hypotheses
- stay anchored to real traded outcomes
- remain interpretable enough to convert discoveries into explicit rules

## 3. Recommendation

Build a new **trade-discovery pipeline** beside the existing hypothesis framework, not inside it.

This pipeline should:

1. Generate a unified feature table from run artifacts
2. Label each candidate setup using actual trade outcomes
3. Mine both rule combinations and sequence/state patterns
4. Use ML only as a secondary ranking and discovery aid
5. Promote the strongest surviving patterns into formal hypotheses for re-testing

This keeps the current hypothesis framework intact while allowing a more open-ended search process.

## 4. Non-Goals

The first version will not:

- place live trades
- auto-optimize on MFE-only labels
- replace the current hypothesis framework
- search every possible model family
- optimize portfolio sizing or capital allocation

The first version is a **strategy discovery and validation layer**, not a live trading engine.

## 5. Architecture Overview

The new pipeline will have five stages:

1. **Run Loader**  
   Reads `events.csv`, `candles.csv`, and any trade-enriched hypothesis outputs from a run directory.

2. **Feature Builder**  
   Produces one row per candidate setup with event, bar, sequence, and geometry context.

3. **Trade Labeler**  
   Attaches the actual trade result for that setup: entry, exit, PnL, exit reason, win/loss, bars held.

4. **Discovery Engine**  
   Runs rule mining first, then optional ML ranking on the same feature table.

5. **Validation + Promotion**  
   Applies chronological walk-forward tests and outputs the top surviving patterns as plain-English candidate strategies.

## 6. Data Model

The core artifact is a **trade-candidate feature table**.

Each row represents one candidate setup and contains four groups of fields.

### 6.1 Setup Identity

- symbol
- timeframe
- run id / run path
- event timestamp
- test timestamp
- confirmation timestamp
- fan id / fan display
- anchor type
- angle fraction
- event type
- live vs retro flag

### 6.2 Context Features

These describe the setup environment at the time of entry.

- trend-aligned vs counter-trend
- fan direction / slope
- bars since anchor
- bars since previous event on same fan
- bars since previous event on same line
- line fraction class
- active zone / cluster state
- breach state
- rest state
- nearby active angle lines
- distance to nearest supporting line
- distance to nearest opposing line
- distance to next target line
- congestion count around current price

### 6.3 Bar-Structure Features

These describe price action around the setup.

- test candle body size and wick ratios
- confirmation candle body size and wick ratios
- test candle polarity
- confirmation candle polarity
- previous 1 to 5 bars return pattern
- previous 1 to 5 bars range expansion / contraction
- local volatility
- momentum proxy from recent closes
- relationship of candle closes to the tested line

### 6.4 Trade Outcome Fields

These are the labels and must be actual-trade based.

- entry price
- entry timestamp
- entry side
- stop loss
- take profit
- exit price
- exit timestamp
- exit reason
- bars held
- net PnL
- pnl_pct
- win/loss

MFE/MAE can be stored as secondary diagnostics, but the primary label is always the realized trade result.

## 7. Candidate Definition

The recommended first version should build rows only for setups that already correspond to a plausible trade entry event, rather than every raw event in the log.

Recommended candidate universe:

- `SUPPORT_BOUNCE`
- `RESISTANCE_REJECTION`
- any existing trade-enriched bounce-follow-through outputs
- optionally, later, additional entry-style events such as post-breach pullback entries

This keeps the first version focused on setups that already have a clear entry concept and actual trade outcome path.

## 8. Discovery Strategy

### 8.1 Primary Engine: Rule Mining

Rule mining should be the main discovery engine.

It should search for readable feature combinations such as:

- event type + fraction + anchor type
- event type + fraction + candle pattern
- anchor type + sequence state + line congestion
- trend alignment + zone state + recent bar structure

Recommended first techniques:

- grouped aggregations over discrete engineered features
- pairwise and three-way rule combinations
- shallow decision trees with constrained depth

Why this is recommended:

- results stay interpretable
- rules can be reviewed visually in the Hypothesis Navigator
- strong candidates can be converted directly into formal hypotheses

### 8.2 Secondary Engine: ML Ranking

ML should be used only after the feature table is stable.

Recommended models:

- gradient-boosted trees
- random forest
- regularized logistic regression as a baseline

ML is not the final strategy definition. Its job is to:

- surface nonlinear feature interactions
- rank feature importance
- suggest combinations worth turning into explicit rules

This avoids relying on a black-box model as the trade strategy.

### 8.3 Sequence/State Mining

Because this system is event-driven, sequence context should be part of the discovery pipeline.

Recommended sequence features:

- previous event type on same fan
- previous event type on same line
- event pair within last N bars
- count of recent tests/rejections/breaches on same fan
- whether the current setup is the first, second, or repeated touch

Recommendation: include sequence information as engineered features in the first version, rather than building a separate sequence-only miner first.

## 9. Scoring and Ranking

All candidate rules must be scored from realized trade outcomes only.

### 9.1 Ranking Priority

1. Win rate
2. Expectancy
3. Profit factor
4. Sample size
5. Walk-forward persistence

### 9.2 Hard Minimum Gates

Recommended initial gates:

- minimum sample size per rule
- minimum out-of-sample sample size
- positive expectancy
- profit factor above 1.0
- no severe walk-forward degradation

These thresholds should be configurable, but the first implementation should ship with conservative defaults.

### 9.3 Anti-Overfitting Rules

Reject or downgrade rules that:

- only work in a tiny sample
- collapse out of sample
- rely on too many conditions
- only work in retro events
- depend on a narrow artifact of one specific run window

## 10. Validation

Validation must be chronological, not random.

### 10.1 Walk-Forward

Use chronological train/test splits by time, not shuffled rows.

Recommended first implementation:

- train on the earliest 70%
- test on the latest 30%
- compare win rate, expectancy, PF, and sample size

A rule is considered persistent only if the out-of-sample result remains reasonably close to the in-sample result and still has enough trades.

### 10.2 Cross-Run Validation

Once the single-run version works, extend the same mining flow across multiple runs.

Recommended order:

1. multiple windows on BTCUSDT 15m
2. multiple windows on BTCUSDT 5m
3. then cross-symbol testing if needed

This gives a more honest view of whether the rule is real or just run-specific.

## 11. Outputs

The pipeline should write:

- a feature dataset file
- a scored rules file
- a walk-forward validation file
- a summary file of top surviving candidate strategies

Recommended output format:

- CSV for raw tables
- JSON for structured summaries and downstream UI use

Each promoted candidate should include:

- plain-English rule description
- sample size
- win rate
- expectancy
- profit factor
- train/test comparison
- top supporting features

## 12. File Layout Recommendation

Recommended new backend modules:

- `gann-visualizer/backend/analysis/trade_feature_builder.py`
- `gann-visualizer/backend/analysis/trade_rule_miner.py`
- `gann-visualizer/backend/analysis/trade_ml_ranker.py`
- `gann-visualizer/backend/analysis/trade_discovery_runner.py`

Recommended output directory inside each run:

- `analysis/trade_discovery/`

This keeps the discovery system parallel to `analysis/hypotheses/` rather than mixing the two concerns.

## 13. Data Collection Changes Recommended

The current system is already close, but the miner will be stronger if we extend collection in a few focused places.

Recommended additions:

- explicit previous-event metadata on same fan and same line
- active-line congestion summary at event time
- line-distance features at event time
- recent bar-sequence summary fields
- stronger identification of trend-aligned vs counter-trend status

Recommendation: add these as derived post-processing features first where possible. Only push them back into simulation-time logging if post-processing cannot recover them reliably.

## 14. Implementation Phases

### Phase 1: Feature Table + Trade Labels

- load run artifacts
- build one row per candidate setup
- attach actual trade outcomes
- export feature table

This is the highest-value first milestone.

### Phase 2: Rule Miner

- grouped rule search
- configurable thresholds
- ranking by trade win rate, expectancy, PF, sample size
- write top candidate rules

### Phase 3: Walk-Forward Validation

- chronological validation
- persistent vs non-persistent tagging
- out-of-sample summary

### Phase 4: ML Ranking

- fit tree-based models
- extract feature importance
- generate rule suggestions

### Phase 5: Promotion Back Into Hypotheses

- convert top surviving mined rules into explicit hypotheses
- re-run in the unified framework for visual and statistical review

## 15. Risks and Mitigations

### Risk: Overfitting

Mitigation:

- minimum sample gates
- chronological walk-forward
- cross-run validation
- limit rule complexity

### Risk: Black-box outputs

Mitigation:

- keep rule mining primary
- use ML as discovery support only
- require plain-English exported rules

### Risk: Feature leakage

Mitigation:

- ensure every feature is known at entry time
- keep post-trade fields out of the feature set
- separate diagnostic fields from predictive fields

### Risk: Too much scope in v1

Mitigation:

- begin only with entry-style bounce/rejection candidates
- start with one timeframe and one symbol family
- defer cross-symbol and advanced modeling until the feature table is stable

## 16. Success Criteria

The first version is successful if it can:

1. produce a clean trade-candidate dataset from an existing run
2. discover readable patterns ranked by actual trade win rate, expectancy, and PF
3. reject unstable patterns with walk-forward testing
4. produce at least a small set of candidate rules worth promoting into the formal hypothesis framework

## 17. Final Recommendation

Proceed with a **trade-based rule-mining pipeline first**, using the current hypothesis and exit-optimization outputs as raw material.

Do **not** start with a black-box ML strategy search.

Recommended build order:

1. feature table
2. rule miner
3. walk-forward validation
4. ML ranking
5. promotion into formal hypotheses

This is the highest-probability path to discovering something genuinely tradeable while keeping the results understandable and visually verifiable.
