# Hypothesis Mining Methodology — Lean MVP

**Date:** 2026-04-28
**Status:** Approved (brainstorming complete; ready for implementation plan)
**Owner:** kit678

## 1. Goal

Get from "4 untested hypotheses + 60-row replay log" to **a paper-traded short-term strategy with measured edge** in approximately 3 weeks of focused work.

The strategy is the Angular Price Coverage strategy. Trading vehicles are short-term futures and weekly options on Indian indices (NIFTY/BANKNIFTY) and equities.

The methodology must be lean enough to actually execute, but disciplined enough that any "winner" it surfaces is a real signal rather than noise.

## 2. Decisions Captured From Brainstorming

| # | Decision | Source |
|---|---|---|
| D1 | Data scale = multi-instrument × multi-timeframe (NIFTY/BANKNIFTY × 5m/15m/1h, ~6 months history). Tens of thousands of events feasible. | Q1 |
| D2 | "Hypothesis works" measured by a **two-stage gate**: Phase 1 = statistical edge on forward returns; Phase 2 = rule-based backtest with realistic execution. | Q2 |
| D3 | Backtest vehicle = **futures for research; options as a separate manual translation step** (no automated options backtester for MVP). | Q3 |
| D4 | ML ambition = **interpretable + unsupervised pattern mining only**. No black-box predictive deployment. *Deferred entirely from MVP.* | Q4 |
| D5 | Validation discipline = held-out month (most recent), per-slice reporting, no pooled-only conclusions. **Dropped from MVP:** Bonferroni/BH correction, pre-registration, held-out instrument. | Q5 |
| D6 | Multi-TF strategies (e.g., HTF interaction → LTF execution) are anticipated as a future strategy class. **Architecture must not preclude them**, but no multi-TF infrastructure built in MVP. | User note after Section 1 |
| D7 | Lean over sophisticated. Defer parquet, regime/sequence column pre-computation, multi-TF context table, ML mining, BH correction, options backtester, corpus YAML manifest. | User feedback before approval |

## 3. Lean MVP Plan

### 3.1 Phase 0 — Data Generation (Week 1)

Minimum changes to existing code to enable trustworthy multi-instrument × multi-timeframe analysis.

**Code changes:**

1. **Add `instrument` and `timeframe` to `Event` dataclass** in [event_logger.py](../../../gann-visualizer/backend/study_tool/event_logger.py). Propagate through `to_dict`, `from_dict`, `export_csv` (column order: insert after `#`/`Time`). Without these, multi-instrument data is unusable.
2. **Partition simulation output** in [run_simulation.py](../../../gann-visualizer/backend/run_simulation.py) — write to `logs/backend/runs/<instrument>/<timeframe>/<run_id>/` (containing `trace.log`, `events.csv`, plus an `audit/` subdirectory). Replaces the current single hardcoded `simulation_events.csv`.
3. **Wrapper script** `scripts/run_corpus.py` — hardcoded Python list of (instrument, timeframe, from_date, to_date) tuples; loops and invokes `run_simulation()` per slice. No YAML, no manifest, no validation framework.
4. **Parameterize `verify_trace_events.py`** to accept `--run-dir <path>` and read trace + events relative to that directory. Output the audit report into `<run_dir>/audit/`.

**Corpus to generate:**

| Instrument | Timeframes | Date Range |
|---|---|---|
| NIFTY (^NSEI) | 5m, 15m, 60m | Last 6 months excluding most recent 1 month |
| BANKNIFTY (^NSEBANK) | 5m, 15m, 60m | Last 6 months excluding most recent 1 month |

The most recent 1 month is the **held-out OOS slice** — never touched until backtest time.

**Audit gate:**

- Run [verify_trace_events.py](../../../gann-visualizer/backend/analysis/verify_trace_events.py) per slice.
- Gate per slice = 100% accuracy AND 100% completeness (matches the project's existing PASS criterion at [verify_trace_events.py:791](../../../gann-visualizer/backend/analysis/verify_trace_events.py#L791)).
- If a slice fails, fix the underlying engine bug *before* including that slice in analysis. Slices that pass continue independently.

**What is NOT done in Phase 0:**

- No parquet, no schema migration. Stay with CSV.
- No `bars.parquet` (per-bar table). Forward returns are computed during analysis (Phase 1) by reading the trace log when needed.
- No multi-TF context table.
- No regime/sequence/confluence pre-computation as columns.
- No collapse of the dual-event-track in `run_simulation.py`. Touch only if the audit gate fails because of it.

### 3.2 Phase 1 — Statistical Edge Test (Week 2)

Test the 4 existing hypotheses in [strategy_analyzer.py](../../../gann-visualizer/backend/analysis/strategy_analyzer.py) on the corpus, slice-by-slice.

**Code changes:**

1. **Extend `enrich_with_forward_outcomes()`** in [event_logger.py:414](../../../gann-visualizer/backend/study_tool/event_logger.py#L414) to compute MFE/MAE at horizons **5, 10, 20, 50 bars**. Currently only 10 and 20.
2. **Add a corpus-loop driver** — a small script (notebook or `.py`) that:
   - Loads each slice's `events.csv` into a DataFrame
   - Runs each `Hypothesis.evaluate()` on it
   - Aggregates into one summary table: `(hypothesis, instrument, timeframe) → {sample_size, win_rate, mean_fwd_return_5/10/20/50, sharpe-of-signal}`
3. **One Jupyter notebook** at `gann-visualizer/backend/analysis/notebooks/phase1_edge_test.ipynb` (or equivalent) that produces:
   - The summary table above
   - A per-hypothesis breakdown showing per-slice consistency
   - A "winners" cell that flags any hypothesis with sample-size ≥ 30, win-rate consistent across slices, and mean fwd-return positive at the 10–20 bar horizon

**Discipline rules (MVP-light):**

- **Held-out month untouched.** Phase 1 only sees the in-sample 6-month corpus.
- **Per-slice reporting is mandatory.** Pooled results may be shown for context but never as the basis for "this works."
- **Sample-size threshold per slice:** ≥ 30 events. Below that, the slice's result is annotated "low-N" and excluded from cross-slice consistency judgement.
- **Cross-slice consistency:** a hypothesis is a "candidate winner" only if it shows positive expected return *in the same direction* on at least 4 of the 6 slices.

**Existing hypotheses tested (no new code beyond what's in [strategy_analyzer.py](../../../gann-visualizer/backend/analysis/strategy_analyzer.py)):**

- `StrongSRHypothesis` — angle lines as S/R
- `TargetProgressionHypothesis` — post-breach target reach probability
- `QuarterReversalAnomalyHypothesis` — 0.25 line reversal
- `ConfluenceBounceHypothesis` — multi-fan-line confluence

These map approximately to the four hypotheses described in the user's brief. Any mismatch is a one-line edit to the existing class, not new architecture.

### 3.3 Phase 2 — Backtest the Survivor (Week 3)

For up to 2 hypotheses surviving Phase 1's cross-slice consistency check:

**Code changes:**

1. **Write a rule-based strategy module** at `gann-visualizer/backend/analysis/strategies/<hypothesis_name>.py` — vectorized over the events table, ~100–200 lines. Inputs: events DataFrame + bars CSV. Outputs: trade list (entry_time, entry_price, exit_time, exit_price, P&L_points).
2. **Strategy spec for each survivor:**
   - Entry signal (which event type + filters)
   - Stop loss rule (in points or % of entry)
   - Target rule (next angle line / fixed R-multiple)
   - Position sizing (fixed lots — no compounding for MVP)
3. **Run on held-out month** — single OOS peek. Output: P&L curve, max drawdown, hit rate, profit factor, expectancy in points.
4. **Manual options translation** for top survivor:
   - Pick weekly ATM or OTM-1-strike based on the strategy's directional confidence
   - Map futures stop to options stop in premium terms (no Greeks model — use rough delta intuition)
   - Theta-aware exit rule: hard exit if held > 2 trading sessions on weekly contracts

**No options backtester is built.** The translation happens manually for paper trading.

### 3.4 Phase 3 — Paper Trade (Week 4+)

The Week 3 survivor strategy is paper-traded for 4–6 weeks on live data. The Phase 1 notebook becomes the ongoing analysis tool — new live observations append to it.

Decision criteria for going live:
- Paper-trade Sharpe ≥ backtest Sharpe × 0.7 (some live degradation expected)
- Paper-trade max drawdown ≤ backtest max drawdown × 1.5
- No mechanical execution issues (slippage, missed signals, broker quirks)

If criteria pass: small live size. If they fail: back to Phase 1 with the failure as a new constraint.

## 4. Trading-Regime Constraints

These apply to all phases:

- **Forward-return horizons:** 5/10/20/50 bars on the trading TF. No daily-bar horizons.
- **Holding period:** intraday or short multi-day. Phase 2 backtest assumes square-off by EOD or by Friday EOD for weekly options.
- **Slippage assumptions:** futures = 1 tick per leg; weekly OTM options = 0.5 to 1.0 rupee premium slip per leg (loose, deliberately conservative).
- **Position sizing for MVP:** fixed lot count — no Kelly, no risk parity, no compounding. Avoids confusing strategy edge with sizing edge.

## 5. Explicit Non-Goals (For MVP)

These are deferred and **not implementation targets**:

- Parquet/columnar storage migration
- Multi-TF context table and HTF→LTF strategies
- ML / unsupervised pattern mining
- Automated options backtester with strikes & Greeks
- Bonferroni / BH multiple-testing correction
- Pre-registration formalism
- Held-out instrument (held-out month covers it)
- Corpus YAML manifest / config-driven runs
- Dual-event-track refactor in `run_simulation.py` (only if audit forces it)
- Regime/sequence/confluence pre-computed columns
- Continuous mining loop / automation

Each of these is captured in the **North Star Architecture** appendix below for when the MVP graduates.

## 6. Risks and Open Questions

| Risk | Mitigation |
|---|---|
| **Audit reveals widespread engine bugs across slices.** Phase 0 stalls. | Prioritize fixing slices in order of TF granularity (5m most likely to reveal bugs). Drop a slice if its bug is too deep to fix in 1–2 days; analyze on remaining slices. |
| **All 4 hypotheses fail Phase 1 cross-slice consistency.** | The methodology has delivered its primary value: a definitive answer that none of the current hypotheses are tradeable as-is. Decide whether to (a) refine hypothesis parameters and re-test, (b) add new hypotheses by hand, or (c) graduate to Phase 3 (ML mining) of the north-star architecture. |
| **Phase 2 backtest shows edge, but options translation kills it on bid-ask.** | Document the gap. Either move to futures-only trading (lower leverage, lower returns, simpler) or invest in a proper options backtester before risking capital. |
| **Held-out month happens to be an unusual regime** (e.g., trending vs. ranging mismatch with in-sample). | A single OOS month is inherently noisy. If results are borderline, extend held-out to 2 months before deploying. |
| **MFE/MAE at fixed bar horizons miss the strategy's natural exit signal.** | Phase 2 backtest replaces fixed-horizon excursion with the strategy's actual stop/target rules — this is the correction. Phase 1's MFE/MAE is a *cheap filter*, not the final judge. |

**Open questions to resolve during implementation (not blocking spec approval):**

- Exact mapping of user's 4 hypotheses ↔ the 4 `Hypothesis` subclasses in [strategy_analyzer.py](../../../gann-visualizer/backend/analysis/strategy_analyzer.py). May require minor edits to existing classes.
- Data source for BANKNIFTY at 5m granularity over 6 months. yfinance has limits; may need Dhan or another source.
- Specific stop/target rules for each backtest strategy in Phase 2 — to be written collaboratively when Phase 2 starts.

## 7. Deliverables

By end of Week 3:

1. Multi-instrument × multi-TF event corpus at `logs/backend/runs/<instrument>/<timeframe>/<run_id>/` (CSV format).
2. Per-slice audit reports passing the 100/100 gate.
3. `phase1_edge_test.ipynb` notebook with the summary table and winner identification.
4. 1–2 backtested strategy modules at `gann-visualizer/backend/analysis/strategies/`.
5. Phase 2 backtest output on held-out month (P&L curve, drawdown, expectancy).
6. Manual options translation document for the top survivor.

By Week 4+:

7. Paper trading log + ongoing analysis updates.

---

## Appendix A — North Star Architecture

For when the MVP graduates and we need scale. **Not built in MVP.**

The full design is a 4-phase pipeline:

```
Phase 0 — Trace Audit + Schema Upgrade (parquet, bars + events + multi_tf_context)
   ↓
Phase 1 — Statistical Edge Testing (BH-corrected, walk-forward, regime-conditional)
   ↓
Phase 2 — Strategy-as-Code Backtest (futures + automated options overlay)
   ↓
Phase 3 — ML Mining of New Hypotheses (interpretable trees + unsupervised sequence mining)
   ↓ (loops back to Phase 1)
```

**Key future extensions:**

- **Parquet schema** with `bars.parquet` (one row per bar), `events.parquet` (one row per event), `multi_tf_context.parquet` (LTF rows joined to HTF state at LTF bar close — the substrate for multi-TF strategies).
- **`bar_close_time` field** on every bar (currently only `time` = bar open) to make multi-TF joins leak-free.
- **Pre-computed feature columns:** regime tags (trend slope, ATR%), sequence fields (`prior_event_type_same_fan`, `bars_since_last_event_same_fan`), confluence count.
- **Corpus runner** with YAML manifest of (instrument × TF × date-range) tuples.
- **Walk-forward validation** in Phase 2 backtests (rolling train/test windows).
- **BH multiple-testing correction** when ranking many hypotheses.
- **Held-out instrument** as final pre-deployment sanity check.
- **Phase 3 ML mining** with interpretable trees (CART, GBM + SHAP) and unsupervised sequence mining. ML produces *candidate rules*, never deployed signals — every ML-discovered rule re-enters Phase 1 for validation.
- **Automated options overlay backtester** with strike selection, theta-aware exits, and bid-ask realism.

The MVP architecture is forward-compatible with all of the above:

- Adding `instrument` and `timeframe` columns now means a future parquet migration is a format change, not a schema change.
- Partitioned output paths now mean future corpus tooling can crawl them without restructuring.
- The `Hypothesis` interface in [strategy_analyzer.py](../../../gann-visualizer/backend/analysis/strategy_analyzer.py) survives unchanged into the north-star design.

When MVP findings justify the investment, this appendix becomes the spec for v2.

---

## Appendix B — File and Path Conventions (MVP)

```
logs/backend/runs/
  <instrument>/                    e.g., NIFTY, BANKNIFTY
    <timeframe>/                   e.g., 5m, 15m, 60m
      <run_id>/                    e.g., 2026-04-28_a1b2c3
        trace.log                  per-bar narrative (existing format)
        events.csv                 EventLogger output (with new instrument/TF columns)
        audit/
          TRACE_AUDIT_REPORT.txt
          EVENT_VERIFICATION.csv
          events_ml.csv
          bars_ml.csv

gann-visualizer/backend/analysis/
  strategy_analyzer.py             existing Hypothesis classes (extended for fwd_return_5/50)
  notebooks/
    phase1_edge_test.ipynb         the corpus-loop notebook
  strategies/
    <hypothesis_name>.py           per-strategy backtest module (Phase 2)

scripts/
  run_corpus.py                    hardcoded instrument×TF loop wrapper
```

`run_id` format: `<YYYY-MM-DD>_<short-git-hash>` so every output traces back to the engine commit that produced it.
