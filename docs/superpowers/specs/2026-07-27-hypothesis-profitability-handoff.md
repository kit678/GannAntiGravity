# Handoff: Making the Gann/RSI Hypotheses Actually Profitable

**Date:** 2026-07-27
**Repo:** `c:\Dev\GannTesting` — branch `main`, HEAD `dcf5d53`
**Audience:** a fresh agent session with no prior context

---

## 1. The goal

Maximise **expectancy** — average net PnL per trade — while keeping the win rate
as high as that allows.

Stated plainly: the user wants *both* a high proportion of winning trades *and* a
good average profit per trade. Those are one metric, not two:

```
expectancy = (win_rate x avg_win) - (loss_rate x avg_loss)
```

**Optimise expectancy. Report win rate, profit factor and sample size alongside
it. Never optimise win rate on its own** — section 5 shows exactly how that
backfires here.

---

## 2. What this project is

A backtesting system for trading strategies on crypto/index futures.

| Thing | Where |
|---|---|
| Backend | `gann-visualizer/backend` — Python 3.13, pandas, pytest |
| Frontend | `gann-visualizer/frontend` — React + TradingView widget ("Hypothesis Navigator") |
| Run data | `logs/backend/runs/<SYMBOL>/<TF>/<run_id>/` with `candles.csv`, `events.csv` |
| Hypothesis output | `<run_dir>/analysis/hypotheses/*.json` + `run_summary.json` |
| Main working run | `logs/backend/runs/BTCUSDT/15/2026-07-10_barctx_v2` (961 bars, BTCUSDT 15m) |

There are 24 run directories across BTCUSDT and `_NSEI` at 4m/15m/60m, but only
**22 are distinct** — a few are duplicates of the same window.

### Regenerating hypothesis reports

```python
import sys, os
sys.path.insert(0, os.path.abspath('gann-visualizer/backend'))
from analysis.hypothesis_framework import HypothesisRunner
HypothesisRunner(r'C:/Dev/GannTesting/logs/backend/runs/BTCUSDT/15/2026-07-10_barctx_v2').run_all()
```

> **Do not use `generate_hypothesis_reports.py` for BTCUSDT.** Line 379 hardcodes
> `base_runs_path = ...\runs\_NSEI`, so it can only ever target `_NSEI`.

### Test conventions

- Run pytest from the repo root: `python -m pytest gann-visualizer/backend/tests/<file> -v`
- There is deliberately **no** `conftest.py` or `pytest.ini`. Do not add one.
- `.gitignore:24` contains `**/tests/`, so **test files need `git add -f`**.
- Test preamble (worktree-safe; do not copy the older hardcoded-path style):
  ```python
  import os, sys
  sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
  ```
- Frontend tests are plain Node scripts: `node gann-visualizer/frontend/src/<name>.test.mjs`

---

## 3. Where things stand

19 hypotheses are registered in `HypothesisRunner.HYPOTHESIS_CONFIG`
(`gann-visualizer/backend/analysis/hypothesis_framework.py`). Latest realized-trade
results on the BTCUSDT 15m run:

| hypothesis | n | win rate | net PnL | WF test | persistent |
|---|---:|---:|---:|---:|:--:|
| Target Progression Probability | 78 | 0.410 | **+2299** | 0.250 | no |
| The 1/4 Reversal Anomaly | 36 | 0.472 | **+1179** | 0.636 | **YES** |
| RSI Trendline Break Strategy | 45 | 0.511 | **+111** | 0.429 | no |
| Reversal by Angle Line | 748 | 0.447 | −14553 | 0.360 | no |
| Confluence Bounce Rule | 613 | 0.429 | −17058 | 0.342 | no |
| S/R Risk/Reward Edge | 632 | 0.427 | −18791 | 0.358 | no |
| Bounce Follow-Through | 243 | 0.239 | −28745 | 0.178 | no |
| Bounce Follow-Through V5/V7/V8 | 204 | 0.176 | −29937 | 0.129 | no |

**Portfolio total: −221,559.** Only 3 of 19 are net-positive; only 1 is persistent.

---

## 4. What has already been done (do not redo)

### 4.1 All hypotheses now score on realized futures trades

Previously **15 of 19** scored on `MFE > MAE x ratio` ("did price move favourably
at some point in the horizon") and 3 on event labels. Only the RSI strategy used
real trades. MFE labels never have to survive a stop, so they wildly overstated
performance — Bounce Follow-Through V5 reported **0.721** by MFE while its real
trades won **0.176** and lost 29,937.

Fixed by `rescore_from_realized_trades()` in `hypothesis_framework.py`. The real
trades were *already* being simulated by `ExitOptimizer` and written into
`detailed_log`; only the headline `in_sample` / `walk_forward` numbers still came
from MFE. The MFE figures survive as `label_win_rate` / `label_sample_size`.

Tests: `gann-visualizer/backend/tests/test_realized_trade_scoring.py` (7 tests).

### 4.2 RSI trendline geometry rebuilt

The RSI strategy's trendlines were rebuilt as a causal, non-repainting engine:

- `analysis/rsi_pivots.py` — RSI series, fractal candidates, incremental dominance
- `analysis/rsi_line_policy.py` — swappable anchor policies
- `analysis/rsi_sweep.py` — the causal state machine (one active line per direction)
- `analysis/rsi_geometry.py` — thin re-export shim (was 898 lines, now 65)

Default policy is `CollinearExtendAnchorPolicy`: start at the adjacent pivot and
extend back only while every intermediate pivot stays *on* the line. Result on real
data: **0% of segments skip a pivot** (was 71.7%), median 3 touches, 57% touching 3+.

Tests: `test_rsi_pivots.py`, `test_rsi_line_policy.py`, `test_rsi_sweep.py`,
`test_rsi_causality.py` (prefix-stability / anti-repaint), `test_rsi_geometry.py`.

### 4.3 Tooling built (all committed, all reusable)

| Script | Purpose |
|---|---|
| `backend/scripts/sweep_exit_rules.py` | Sweep stop rule x max hold x R grid across every hypothesis, on real trades with fees |
| `backend/scripts/placebo_test_rsi.py` | Does the entry *timing* carry any edge vs a time-shifted control? |
| `backend/scripts/compare_rsi_policies.py` | A/B two RSI anchor policies on one run |
| `backend/scripts/compare_rsi_policies_multi.py` | Same, pooled over all 24 runs |

---

## 5. Hard-won findings — read before changing anything

### 5.1 Win rate and profitability move in opposite directions here

A 20-bar window stop with a 40-bar hold *raises* win rates substantially and
*destroys* PnL:

| hypothesis | base WR | base net | w20/40 WR | w20/40 net |
|---|---:|---:|---:|---:|
| S/R Risk/Reward Edge | 0.427 | −18,791 | **0.467** | **−59,002** |
| Confluence Bounce Rule | 0.429 | −17,058 | **0.470** | **−51,002** |
| Bounce Follow-Through V5 | 0.176 | −29,937 | **0.397** | −22,673 |
| **TOTAL** | | **−221,559** | | **−261,722** |

Wider stops win more often and lose far more per loss. **This is why the objective
must be expectancy.**

### 5.2 The RSI entry trigger failed a placebo test

Holding the trend filter, stop, R grid and max hold constant and moving *only* the
entry bar:

```
REAL rsi-break     n=538  win=0.4517  net= 58157
placebo +13 bars   n=524  win=0.4981  net= 64250   <- beats real
placebo +23 bars   n=536  win=0.4925  net= 60853   <- beats real
trend-filter only  n=772  win=0.4080  net= 28745
```

The real signal sits *inside* the placebo spread. **Gate every entry-rule change on
this test.** Run `placebo_test_rsi.py` and adapt it per hypothesis.

### 5.3 Several "variants" are not variants

12 Bounce Follow-Through variants collapse to **7 distinct** hypotheses. V2/V5/V7/V8
trade byte-identical entry sets, as do V3/V4/V10 — they differ only in `mfe_ratio`,
which only ever affected the (now discarded) MFE label. Four of the 7 have n<10.

### 5.4 Fee handling is inconsistent — FIX THIS FIRST

- `analysis/exit_optimizer.py` uses `TAKER_FEE = 0.0004` (0.04%/side) ✅
- `analysis/signal_trade_simulator.py` defaults `fee_rate=0.0`, and
  `rsi_trendline_hypothesis.py` does not pass one ❌

So **the RSI strategy's numbers are gross of fees while every other hypothesis's are
net.** The comparison in section 3 is not apples-to-apples until this is fixed. RSI's
+111 will likely go negative once fees are applied.

### 5.5 The shared trade model's defaults are arbitrary

In `exit_optimizer.py::_simulate_one`:
- Entry = close of the confirmation candle
- Stop = test-candle extreme for BFT events; **hardcoded `GENERIC_RISK_PCT = 0.005`**
  (0.5%) for every other hypothesis
- TP = `entry ± risk x R`, `R_VALUES = [1.0, 1.5, 2.0, 2.5, 3.0]`
- `MAX_HOLD_BARS = 10`

The 0.5% stop has no relationship to market structure. Note also that R is chosen
**globally in hindsight** — the grid is run over all trades and the single best R is
applied to every one. Live you would have to pick R in advance.

### 5.6 Entry is not executable as written

Entry is taken at the **close of the signal bar**, but the signal is only knowable
once that bar has closed. Live you would be filled at the next bar's open. Every
backtest figure assumes a fill you cannot get — a systematic ~1-bar advantage on
every trade. `sweep_exit_rules.py` already supports an `entry_offset` of 1 for
testing this.

---

## 6. The plan

### Phase 0 — Make the numbers trustworthy (do this first)

1. Fix the fee inconsistency (5.4): pass `fee_rate=0.0004` from
   `rsi_trendline_hypothesis.py`, or change the `simulate_trade_grid` default.
   Re-run and expect RSI's +111 to move.
2. Add **expectancy**, **profit factor** and **avg win / avg loss** to
   `rescore_from_realized_trades()` and to `run_summary`. These are the objective.
3. Add a `next_bar_open` entry mode and make it the default (5.6). Re-baseline
   everything against it. Expect all numbers to worsen; that is the honest starting
   point.
4. Re-run all hypotheses and record the new baseline table.

**Do not proceed until the baseline is fee-inclusive, next-bar-entry, and
expectancy-reported.**

### Phase 1 — Establish a null baseline for every hypothesis

Generalise `placebo_test_rsi.py` to all hypotheses. For each, compare its real
entries against entries shifted +7/+13/+23/+37 bars with identical stop/exit rules.

**Any hypothesis that does not beat its own placebo on expectancy should be
retired, not tuned.** Based on section 5.2 expect several to fail. This is the
single highest-value step: it tells you which hypotheses have any signal at all
before you spend effort on their exits.

### Phase 2 — Collapse the duplicates

Merge V2/V5/V7/V8 into one hypothesis and V3/V4/V10 into another (5.3). Delete
variants with n<10 (V6 n=4, V9 n=3). This removes ~5 redundant entries from every
future sweep and stops duplicate rows misleading the ranking.

### Phase 3 — Optimise exits on expectancy, survivors only

For hypotheses that passed Phase 1, use `sweep_exit_rules.py` (change its objective
from win rate to expectancy) over:

- stop: fixed 0.5/1.0/1.5%, N-bar window (10/20/40), prior swing pivot, ATR multiple
- max hold: 10 / 20 / 40 / 80
- R grid, plus **per-trade R chosen in advance** rather than globally in hindsight
- trailing stop / break-even-at-1R as additional exit modes

Report expectancy, profit factor, win rate, n. Pick on expectancy.

### Phase 4 — Validate out of sample

Everything above is in-sample on one 961-bar window. Before believing any of it:

- walk-forward within each run (already wired: `walk_forward` in each report)
- pooled across all 22 distinct runs and both symbols (`compare_rsi_policies_multi.py`
  shows the pattern to follow)
- report in-sample and out-of-sample side by side; treat any hypothesis whose test
  expectancy is negative as failed regardless of its in-sample figure

### Phase 5 — Only then, position sizing

Once expectancy is positive out of sample, risk-per-trade normalisation (fixed
fractional sizing on the stop distance) converts expectancy into a portfolio curve.
This is where "higher PnL per trade" is genuinely controlled — not by tightening
stops.

---

## 7. Honest assessment

11 of 12 measurable hypotheses lose money on realized trades under **every**
configuration tested, and their apparent edge came entirely from MFE labelling. The
exit sweep is evidence that stop/exit tuning does **not** recover it.

The one hypothesis that looks real is **The 1/4 Reversal Anomaly**: n=36, 47.2%
in-sample, **63.6% out-of-sample**, +1179, and the only one flagged persistent. It is
a small sample on one window.

If forced to choose where the effort goes: **Phase 0 + Phase 1 across everything,
then concentrate on 1/4 Reversal Anomaly and gather more data for it.** Do not spend
weeks tuning exits on hypotheses that cannot beat a time-shifted control.

---

## 8. Traps that have already cost time

1. **Do not optimise win rate.** Demonstrated in 5.1 to cost 40,000.
2. **Do not trust any `label_win_rate` or MFE figure.** They exist only as diagnostics.
3. **Do not measure a geometric property against a filtered subset.** A claim that
   "RSI pivots are rarely collinear" was wrong — it came from measuring against a
   dominance-filtered pivot list (57 of 130 highs) at too tight a tolerance. Measure
   against the raw structure.
4. **Beware in-sample sweeps.** Every table in this document is in-sample on one
   window unless stated otherwise. Sweeping many configs on one window finds noise.
5. **`git add -f` for test files** (`.gitignore:24` has `**/tests/`).
6. **Verify a test can fail.** The anti-repaint test originally passed against
   deliberately broken code because its synthetic fixture was too benign. Break the
   implementation on purpose and confirm the test catches it.

---

## 9. Suggested opening move

```bash
cd c:/Dev/GannTesting
python -m pytest gann-visualizer/backend/tests/test_realized_trade_scoring.py -v
python gann-visualizer/backend/scripts/sweep_exit_rules.py
```

Then implement Phase 0 items 1–2, re-run the hypotheses, and post the new
expectancy-based baseline table before touching anything else.
