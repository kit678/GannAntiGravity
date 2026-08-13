# VWAP Extremity Sweep — Go/No-Go Test Design

**Date:** 2026-08-12
**Status:** Design — awaiting approval, not yet implemented
**Source:** Instagram reel by `aabandzfx`, "order flow strategy". Transcript at
`C:\Users\kitsh\Downloads\Instagram_Reels\orderflow.json`, extracted rules at
`order_flow_description.md`.
**Backlog context:** [2026-08-07-strategy-research-backlog.md](../backlog/2026-08-07-strategy-research-backlog.md)
— this is Level 2 candidate #4 ("VWAP band mean reversion") crossed with the
liquidity-sweep idea already tested as ORB variant C.

## Goal

Answer one question with a number:

> Does fading a liquidity sweep that lands in the 2–3 sigma VWAP extremity zone
> make money after costs, on data it was not designed against?

A go/no-go test, not a strategy build. If the answer is no, the code is closed
out and the next backlog item is taken. No tuning to rescue a failing result.

## Provenance and what it implies

The source is a 95-second promotional reel. It opens with "90% win rate" and
closes by asking viewers to comment for the full strategy. It is a lead magnet,
and it is **deliberately incomplete**. Three material rules are never stated:

1. Where the Anchored VWAP is anchored. It is dragged onto the chart by hand.
2. What a "candle confirmation" is, mechanically.
3. Which target to use — he names three in ten seconds (the main VWAP line, the
   opposite extremity band, and a discretionary prior high giving "a one to six").

Every gap is closed below either by a declared range of values or by an explicit
decision recorded here. None is closed by picking the setting that performs best.
The "90% win rate" claim is treated as marketing and is not a hypothesis this
test is obliged to reproduce.

## The rule as described

From the transcript, in his order:

1. Anchored VWAP with the 2nd and 3rd standard-deviation bands enabled.
2. The region between the 2 and 3 sigma bands is the "region of extremity".
3. "We have an Asian high being swept **into** our area of extremity."
4. "Then we wait for a candle confirmation."
5. Enter on that confirmation candle. Stop above/below its extreme.
6. "Target the other extremity or VWAP, the main VWAP band."
7. Same day — sweep and confirmation are not carried overnight.

Point 4 is decisive: the sweep bar and the entry bar are separate. Point 3 fixes
that the sweep and the extremity must be simultaneous, not merely both present.

## Market

**BTCUSDT, Binance USD-M futures, 5-minute bars.** Headline symbol. ETHUSDT and
SOLUSDT are run separately as a second opinion, not pooled.

Rationale. The setup depends on an Asian session that is a *prior* session,
swept during a *later* one. That only exists in a market trading around the
clock. NIFTY via Dhan is unusable here — the Indian session *is* Asian hours, so
there is no Asian high to sweep later in the day. US futures via yfinance match
the video but cap intraday history at ~60 days, which the harness already forces
to `INCONCLUSIVE`.

Data is already on disk at `logs/backend/history/BTCUSDT/5m/candles.csv` —
roughly five years (2021-08-11 onward, ~526,000 bars, ~1,800 UTC days), fetched
by `scripts/fetch_binance_history.py` from the `fapi` futures endpoint.

### Session structure

A "session" is one UTC day.

| Window | UTC | Bars (5m) | Role |
|---|---|---|---|
| Asian range | 00:00–08:00 | 96 | Produces `asian_high` / `asian_low` |
| Tradable | 08:00–23:55 | 192 | Sweeps and entries happen here |
| Flat by | 23:55 | — | Forced exit at that bar's close |

00:00 UTC is Tokyo's open by the convention crypto desks use, so the VWAP daily
anchor and the Asian range share a start. That is a coincidence worth stating
rather than a design constraint.

## Anchored VWAP and bands

`typical_price = (high + low + close) / 3` (HLC3, TradingView's default; the
video does not specify, so the default is used and recorded as an assumption).

From the anchor bar to bar *t*, using **closed bars only**, up to and including
*t*:

```
VWAP_t  = Σ(tp_i · v_i) / Σ(v_i)
var_t   = Σ(v_i · (tp_i − VWAP_t)²) / Σ(v_i)
σ_t     = sqrt(var_t)
band_k  = VWAP_t ± k · σ_t
```

**Numerics.** The textbook `var = Σ(tp²·v)/Σv − VWAP²` cancels catastrophically
when σ is small relative to price. At BTC 100,000 with a 50-dollar sigma, that
subtracts two numbers agreeing to nine significant figures, and float64 has
about fifteen — most of the answer is rounding error.

Fixed by shifting the origin to `K`, the first typical price of the anchor
period, before accumulating. `d_i = tp_i − K` is intraday-range sized rather than
price-level sized, so nothing cancels:

```
Sv     = cumsum(v)          Sdv = cumsum(d·v)          Sd2v = cumsum(d²·v)
mean_d = Sdv / Sv
VWAP   = K + mean_d
σ      = sqrt(max(Sd2v / Sv − mean_d², 0))
```

Still one vectorised pass per anchor period, still uses only bars up to and
including *t*. The `max(·, 0)` clamps the residual float error that can make a
near-zero variance come out marginally negative. A test asserts this agrees with
the naive form on well-conditioned synthetic input, where the naive form is
still trustworthy.

**Anchor policies.** Declared as a range because the video does not specify:

| Policy | Anchor | Status |
|---|---|---|
| `daily` | 00:00 UTC each day | Headline |
| `weekly` | Monday 00:00 UTC | Declared neighbour |

**Warmup guard:** a bar is only eligible to produce a signal if at least 96 bars
have closed since its anchor. Under both policies the tradable window starts at
or after 08:00 UTC, so this is satisfied automatically; the guard exists to make
a future anchor policy fail loudly rather than silently trade a two-bar sigma.

**Zero-volume bars** contribute nothing to either sum and are not errors. A day
whose Asian window has zero total volume is skipped with a reason.

## Signal rule

Stated for the **short** side. The long side is the exact mirror (Asian low,
lower bands, `low <` and `close >`).

| Step | Rule |
|---|---|
| Level | `asian_high` = max high over 00:00–08:00 UTC of the same UTC day |
| Sweep bar | A tradable-window bar with `high > asian_high` **and** `high ≥ VWAP + 2σ` |
| Confirmation | Within the next 6 bars, the first bar closing `< asian_high` **and** `< VWAP + 2σ` |
| Entry | The **open of the bar after** the confirmation bar |
| Stop | High of the confirmation bar |
| Target | VWAP at the confirmation bar |
| Per day | One trade — the first setup that survives the active filters |

### Decisions embedded above

**Entry is the next bar's open, not the confirmation close.** The video says
enter at the close of the confirmation candle. That is not executable: a bar is
only known to qualify once it has already closed, so its close is not an
available fill price. `CandleSignal.entry_bar_index` exists for exactly this and
its docstring names it "the only executable reading of a signal that is not
knowable until its bar has closed". This repo has already been bitten by the
optimistic reading once — commit `787c9ee`, "fill at next bar open". Using the
close here would inflate every result by roughly one bar of the reversal move,
which is precisely the move the strategy is claiming to capture.

**The sweep bar may not be its own confirmation.** `bars_waited ≥ 1` is
required. A bar that both sweeps and closes back inside is the CRT / failed-
breakout pattern, already tested as ORB variant C and already `FAIL` on NIFTY.
Including it would blend a known loser into a new test. Such bars are counted
and reported under `sweep_bar_self_confirmed` for information only.

**Bands are read at the confirmation bar, not the entry bar.** The entry bar's
VWAP is not known until it closes, which is after we have already filled. Every
price level the trade depends on — stop, target, band positions — is fixed from
the last fully closed bar.

**Target is a price, not an R multiple.** The video's exit is a reversion to the
VWAP line, which is a different distance every trade. The "1 to 2, 1 to 3"
figures he quotes are a *consequence* of that, not a rule. Testing a fixed R
instead would test a different strategy. The realised ratio is recorded per trade
as `planned_rr`, which measures his claim directly.

**A failed sweep does not end the day.** If a sweep produces no confirmation
within 6 bars, scanning continues for a later sweep in the same session. Only one
trade is taken. `failed_sweeps_before_entry` is recorded. This adds no parameter
and matches what a person watching the chart would do.

### Guards, each producing a counted reason

| Condition | Reason code |
|---|---|
| UTC day has < 240 of 288 bars (exchange downtime) | `incomplete_day` |
| Asian window has < 80 of 96 bars | `incomplete_asian_range` |
| `asian_high == asian_low` | `degenerate_asian_range` |
| No bar sweeps a level into the extremity zone | `no_sweep` |
| Sweep found, no confirmation within 6 bars | `unconfirmed_sweep` |
| Confirmation lands on the last tradable bar | `no_entry_bar_before_flat` |
| Entry gapped past the stop, so risk ≤ 0 | `stop_wrong_side` |
| Target is not on the profitable side of entry | `target_wrong_side` |
| Setup excluded by the active cell's filters | `filtered_out` |

Every session lands in exactly one bucket. A traded/available ratio far from
expectation is treated as a bug signal, not a finding.

## Architecture — scan once, score forever

The dominant constraint is that re-running a five-year 5-minute scan for every
question is unaffordable. The pipeline is therefore split at the point where
cost stops mattering.

```
candles.csv ──► scan ──► trade ledger (JSON) ──┬──► scoring ──► verdict report (md)
              (slow,                            │
               run once)                        └──► navigator report (JSON)
```

### Why costs are free

The exit path of a trade — whether it hits the stop, the target, or the forced
flat, and on which bar — depends only on price levels. Fees and slippage are
subtracted afterwards. `_trade_cost` in `analysis/signal_trade_simulator.py` is
`entry_price·fee_in + exit_price·fee_out + 2·slippage`, evaluated after the path
is known.

So the ledger records each trade's **gross** result plus its entry and exit
prices, and net P&L under *any* cost model is arithmetic on those three numbers.
The zero-fee world (Shoonya-style Indian brokerage), the Binance-futures world,
and every point of the cost sweep all come from one scan. **No cost question ever
requires a re-run.** A test asserts gross figures in the ledger are invariant to
any fee input.

### Which knobs are free and which are not

| Tier | Knobs | Cost |
|---|---|---|
| Post-hoc arithmetic | every cost scenario | free |
| Post-hoc filter on a recorded column | confirmation window (`bars_waited`), extremity rule (`sweep_sigma`), and any future filter such as hour-of-day | free |
| Changes the simulated path | stop rule, target rule | 4 combinations |
| Changes the bands, so changes the scan | VWAP anchor policy | ×2 |

The scan therefore runs at the **loosest** settings — confirmation window 6,
extremity `≥ 2σ` — records every confirmed setup in the session rather than only
the first, and simulates all four stop×target paths for each. Total: 2 anchors ×
4 paths, in one command.

Recording every setup (not just the first) is what makes the filter tier
genuinely free. Under a tighter cell the first setup may be excluded, and the
correct behaviour is then to take the day's *next* qualifying setup — which is
only possible if it was recorded.

### New modules

Under `gann-visualizer/backend/`:

| File | Responsibility | Depends on |
|---|---|---|
| `strategy/vwap_sweep/vwap_bands.py` | Anchored VWAP, sigma, bands, anchor policies. Pure, no I/O. | pandas |
| `strategy/vwap_sweep/extremity_sweep.py` | One session in, every confirmed setup out, plus per-session diagnostics. | `vwap_bands`, `orb.session` |
| `strategy/vwap_sweep/ledger.py` | The ledger record type; build, serialise, load, validate. | `signal_trade_simulator` |
| `strategy/vwap_sweep/scoring.py` | Ledger + cost model + cell filters → `CellResult`s, sweeps, verdict. | `orb.verdict`, `orb.costs`, `orb.placebo` |
| `strategy/vwap_sweep/navigator_report.py` | Ledger + cell → Hypothesis Navigator JSON. | `ledger` |
| `scripts/run_vwap_sweep_scan.py` | CLI. Slow. Writes the ledger and the run directory. | the above |
| `scripts/score_vwap_sweep.py` | CLI. Instant. Reads a ledger, writes reports. | `scoring`, `navigator_report` |

### Reused unchanged

`analysis/signal_trade_simulator.py` (path simulation, R accounting, cost
application), `strategy/orb/verdict.py` (the frozen verdict rule),
`strategy/orb/costs.py::breakeven_slippage` (the interpolation is over an
arbitrary level→P&L map and is reused verbatim for the cost-rate sweep).

### Changes to shared code

| File | Change | Compatibility |
|---|---|---|
| `analysis/signal_trade_simulator.py` | Optional `target_price` on `CandleSignal`, overriding the R-derived target when set. Same pattern as `max_hold_bars`. Raises if the target is on the wrong side of entry. | Backward compatible — absent means current behaviour |
| `strategy/orb/session.py` | `tz` parameter on the session helpers, defaulting to `Asia/Kolkata` | Backward compatible |
| `strategy/orb/placebo.py` | Hold **target distance** fixed as well as stop distance | Needed because variant D's target is a price, not an R multiple |
| `frontend/src/App.jsx` + new `frontend/src/hypothesisColumns.js` | Drive the events table from a `columns` list in the report JSON | Reports without `columns` keep the existing hardcoded rendering |

`strategy/orb/runner.py` is **not** modified. Variant D has a two-phase shape
that does not fit `run_orb`'s single-shot signature, and forcing it in would make
both harder to read. The shared pieces are reused at module level instead.

### Deliberately not used

`backtest_engine.py` accepts `commission` and `slippage` and never applies them
(`_close_position` returns a raw price delta). Logged as an infra defect in the
backlog; not fixed here because this design does not touch it.

## The trade ledger

One JSON file per symbol per scan.

```json
{
  "meta": {
    "symbol": "BTCUSDT",
    "interval": "5m",
    "source": "binance_history",
    "bars": 526000,
    "first_bar": "2021-08-11T18:35:00Z",
    "last_bar": "2026-08-11T23:55:00Z",
    "scan_params": { "max_wait_bars": 6, "min_sweep_sigma": 2.0, "...": "..." },
    "sessions": { "available": 1800, "with_setup": 0, "skip_reasons": {} },
    "train_dates": ["..."],
    "test_dates": ["..."],
    "generated_at": "2026-08-12T00:00:00Z",
    "code_version": "<git sha>"
  },
  "setups": [
    {
      "setup_id": 0,
      "session_date": "2021-08-12",
      "anchor_policy": "daily",
      "direction": "SHORT",
      "…diagnostic columns…": "…",
      "paths": {
        "confirm|vwap":     { "entry_price": 0, "stop_price": 0, "target_price": 0,
                              "risk_per_unit": 0, "exit_bar_index": 0, "exit_price": 0,
                              "exit_reason": "target", "bars_held": 0,
                              "gross_pnl": 0, "gross_r": 0, "mfe_r": 0, "mae_r": 0 },
        "confirm|opp_band": { "…": "…" },
        "sweep|vwap":       { "…": "…" },
        "sweep|opp_band":   { "…": "…" }
      }
    }
  ]
}
```

Nothing in `paths` depends on a fee. `net_pnl` and `net_r` are absent by
construction, so no consumer can accidentally read a cost-free figure as a net
one.

Sweeps that never confirmed are recorded as setups with `paths: null` and a
`reason`, so session accounting reconciles from the ledger alone.

Written to `logs/backend/vwap_sweep/<SYMBOL>/<run_id>/ledger.json`.

## Cost model

### Rates, not points

`slippage_per_side` in the existing harness is in **absolute price units**,
calibrated for NIFTY around 24,000. BTC traded from ~46,000 to over 100,000
across this window, so no fixed figure is meaningful at both ends. It is
therefore held at `0.0`, and all cost is expressed as a **rate on notional**
through `fee_rate` and `maker_fee_rate`, which the simulator already applies as
`entry_price·fee_rate + exit_price·exit_fee_rate`. Slippage in basis points and
fees in basis points have identical algebraic form, so folding them into one rate
loses nothing.

`maker_fee_rate` applies to target exits only — the VWAP target is a resting
limit order. Stops and forced flats are market orders and pay the taker rate. The
simulator already makes this distinction.

### Scenarios, all from one scan

| Scenario | taker (per side) | maker (target exit) | Meaning |
|---|---|---|---|
| `zero` | 0 bps | 0 bps | No brokerage at all (Shoonya-style). Context only — see below |
| `base` | 5 bps | 3 bps | Binance futures taker 4 bps + 1 bp slippage; maker 2 bps + 1 bp |
| `stressed` | 10 bps | 6 bps | 2× base |

**The zero-cost result is reported but is not a pass criterion.** It bounds the
signal's raw quality and separates "no edge" from "edge eaten by fees", which is
diagnostically useful. It cannot be traded on Binance, so a strategy positive
only at zero cost is a `FAIL`, not a `PASS`.

### Sweep

Taker rate over `[0, 1, 2, 4, 6, 8, 10, 15]` bps per side, maker held at
`max(taker − 2, 0)`. Headline output:

> **Breakeven cost rate** — bps per side at which average net R crosses zero.

Compare against Binance futures reality (~4 bps taker, ~2 bps maker) to judge
margin. This replaces an argument about the right assumption with a fact about
the strategy's cushion.

## Headline metric

**Average net R per trade, second half.** Not USD.

BTC ran from ~46,000 to over 100,000 across the window. A dollar P&L per unit
pools a 2021 trade with a 2026 trade of the same quality and reports them as
wildly different, which corrupts both the half-split comparison and the placebo.
`signal_trade_simulator` already computes `net_r` per trade and its own docstring
states R-multiples are "the only figure that survives being pooled across
symbols, timeframes and eras".

`CellResult`'s fields are named `avg_net_pnl_*`. They are populated with net R
here and the report states the metric explicitly in its header. The fields are
not renamed: `decide_verdict` is a validated component shared with ORB and CRT,
and renaming its fields to satisfy a naming preference risks a working harness
for no behavioural gain. A comment in `verdict.py` records that the field carries
whichever metric the caller chose.

## Robustness grid

Declared before any code runs. One knob moved off the headline per cell.

| Cell | Anchor | Wait ≤ | Extremity | Stop | Target |
|---|---|---|---|---|---|
| **headline** | daily | 3 | ≥ 2σ | confirm bar | VWAP |
| `wait=1` | daily | 1 | ≥ 2σ | confirm bar | VWAP |
| `wait=6` | daily | 6 | ≥ 2σ | confirm bar | VWAP |
| `band=2to3` | daily | 3 | 2σ–3σ only | confirm bar | VWAP |
| `anchor=weekly` | weekly | 3 | ≥ 2σ | confirm bar | VWAP |
| `stop=sweep` | daily | 3 | ≥ 2σ | sweep bar | VWAP |
| `target=oppband` | daily | 3 | ≥ 2σ | confirm bar | opposite 2σ band |

Not a sweep, and no winner is selected from it. The rule runs one way only:

- The **headline** cell must pass every verdict criterion.
- Every **other** cell must additionally show positive average net R at base
  costs on the second half.
- Headline passes but a neighbour does not → **`FRAGILE`**, never `PASS`.

A real edge degrades gracefully across neighbouring settings. A curve fit works
at one setting and collapses on either side. Requiring the whole grid makes this
strictly harder to pass, which is the point.

**Reported for information, explicitly not the verdict:** the headline setup
exited at a fixed R = 2.0 target instead of VWAP. This is the direct test of his
"go for a one to two" claim and is labelled as such.

## Verdict rule

Frozen before the first run. Evaluated by `strategy/orb/verdict.py::decide_verdict`,
unchanged.

**Split:** all sessions, chronologically, into first and second half. Nothing is
fitted on the first half — both halves use identical frozen parameters. The split
checks stability over time, not parameter selection.

Passes only if all hold on the second half:

1. `n_trades ≥ 30`
2. Average net R `> 0` at base costs
3. Average net R `> 0` at stressed (2×) costs
4. First-half average net R `> 0` at base costs
5. Beats placebo — below

**Placebo.** Matched, per the pattern in `scripts/placebo_test_rsi.py`. Run only
on sessions where a real setup fired. Hold **stop distance, target distance and
`max_hold_bars` fixed**; randomise only the entry bar (uniform over the tradable
window) and the direction. Holding both distances fixed is what makes the
comparison fair — it isolates "was the sweep informative?" from "does this exit
geometry make money on any entry?". 200 seeds. The real result must exceed the
95th percentile.

Holding target distance fixed is new. The existing placebo fixes stop distance
only, which is sufficient for a fixed-R strategy but not for one whose target is
a price level.

## Hypothesis Navigator integration

Every scored cell emits a Navigator report so results can be inspected trade by
trade against the chart, rather than trusted as a summary number.

### The blocker

The Navigator's columns are not dynamic today. `frontend/src/App.jsx:1121`
selects between **two hardcoded column sets** with
`if (evt.rsi_value != null || evt.best_r != null)`. A VWAP report would fall into
the RSI branch and render columns labelled RSI, SMA and Pivots showing dashes.

**Fix:** the report JSON may carry a `columns` array of
`{ key, label, format, width? }`. When present, the table renders from it.
When absent, the existing branching is used unchanged, so every existing report
keeps working. Extracted into `frontend/src/hypothesisColumns.js` with unit
tests alongside the existing `hypothesisReportOptions.test.mjs`.

### Report shape

Existing envelope — `{ metadata, live_events, retro_events }` — plus `columns`.

- `live_events` — trades this cell actually took.
- `retro_events` — setups detected but excluded by this cell's filters, each
  carrying `excluded_by`. These render orange as `RETRO` and let near-misses be
  inspected on the chart.

### Columns

**Identity and bars.** The envelope's `time` / `timestamp` / `bar_index` refer to
the **entry** bar, matching how `navigateToHypothesisEvent` jumps the chart.
Every other bar in the setup is named explicitly, because a three-bar setup that
only reports one bar index cannot be verified against the chart:
`setup_id`, `session_date`, `sweep_bar_index`, `sweep_time`,
`confirm_bar_index`, `confirm_time`, `entry_bar_index`, `bars_waited`.

**Setup:** `asian_high`, `asian_low`, `asian_range_width`, `asian_range_pct`,
`swept_level` (`asian_high` / `asian_low`), `sweep_penetration`,
`sweep_penetration_pct_range`, `sweep_sigma`, `failed_sweeps_before_entry`.

**Context at entry:** `vwap_at_confirm`, `sigma_at_confirm`,
`sigma_pct_at_confirm`, `band_2`, `band_3`, `entry_sigma`, `planned_rr`,
`target_distance_bps`, `entry_slip_vs_confirm_close`, `hour_utc`, `day_of_week`,
`anchor_policy`, `stop_rule`, `target_rule`, `half` (`train` / `test`),
`cost_scenario`.

**Outcome:** `direction`, `entry_price`, `stop_price`, `target_price`,
`risk_per_unit`, `exit_bar_index`, `exit_time`, `exit_price`, `exit_reason`,
`bars_held`, `gross_pnl`, `fees`, `net_pnl`, `net_r`, `mfe_r`, `mae_r`,
`outcome`.

**Recorded but never filtered on:** `sweep_volume_ratio`, `day_of_week`,
`hour_utc`, `sigma_pct_at_confirm`, `asian_range_pct`. These exist so a failure
can be understood and so a *future* pre-registered test can be designed from
evidence. Selecting a grid cell by any of them after seeing results would break
the pre-registration this design exists to enforce, and is a non-goal.

Derived columns, defined once here so scoring and the Navigator cannot disagree
(all evaluated at the **confirmation** bar unless stated):

| Column | Definition (short side; long mirrors) |
|---|---|
| `sweep_sigma` | `(sweep_bar.high − VWAP) / σ`, at the **sweep** bar |
| `sweep_penetration` | `sweep_bar.high − asian_high` |
| `sweep_penetration_pct_range` | `sweep_penetration / asian_range_width` |
| `entry_sigma` | `(entry_price − VWAP) / σ` |
| `planned_rr` | `abs(target_price − entry_price) / abs(stop_price − entry_price)` |
| `bars_waited` | `confirm_bar_index − sweep_bar_index`, always ≥ 1 |
| `asian_range_pct` | `asian_range_width / asian_high` |
| `sigma_pct_at_confirm` | `σ / VWAP` |
| `target_distance_bps` | `10000 · abs(target_price − entry_price) / entry_price` |
| `entry_slip_vs_confirm_close` | `confirm_bar.close − entry_price` (positive = the honest fill was worse than the video's claimed fill) |
| `sweep_volume_ratio` | `sweep_bar.volume / mean(volume)` over the session's closed bars up to the sweep |

Four of these earn their place specifically:

- **`entry_slip_vs_confirm_close`** measures, per trade, exactly what the
  next-bar-open fill costs against the confirmation-close fill the video claims.
  If the strategy is only profitable at the claimed fill, this column says so in
  one number rather than requiring a second run.
- **`target_distance_bps`** answers whether the target even clears the round
  trip. At 8 bps round trip, a target 15 bps away cannot survive a 50% hit rate.
  Prior work in this repo landed on a fee-drag conclusion; this makes that
  visible per trade instead of only in the aggregate.
- **`sigma_pct_at_confirm`** and **`asian_range_pct`** are price-neutral. Absolute
  sigma in dollars is not comparable between BTC at 46,000 and BTC at 100,000, so
  the absolute columns alone cannot be sliced across the window.

`sweep_sigma` and `bars_waited` are the two filter columns, so the Navigator can
reproduce any cell's selection by eye. `planned_rr` tests the video's headline
claim directly. `mfe_r` / `mae_r` show how close losing trades came, which is the
first thing to look at if the result is marginal.

### Run directory

The Navigator discovers reports by globbing
`logs/backend/runs/**/hypothesis_reports/**/*_report.json` and loads candles from
the run directory. The scan therefore writes:

```
logs/backend/runs/BTCUSDT/5/<run_id>/
    candles.csv                                    (copied from the history corpus)
    hypothesis_reports/<HHMMSS>/
        vwap_extremity_sweep_<cell>_report.json
```

Resolution is `5` — TradingView style, matching existing run directories, not
`5m`.

## Testing

TDD. Tests are written before each module, on hand-built synthetic bars, with no
network access.

**`test_vwap_bands.py`**
- VWAP matches a hand-computed value over three bars
- Sigma matches a hand-computed value
- No lookahead: appending a spiked future bar leaves earlier band values unchanged
- Daily anchor resets at 00:00 UTC; weekly anchor resets Monday 00:00 UTC
- Zero-volume bars contribute nothing and do not raise
- Running-sums and `Σ(tp²v)/Σv − VWAP²` forms agree on well-conditioned input

**`test_extremity_sweep.py`**
- Short setup detected at the expected bars, prices and stop
- Long setup is the exact mirror
- Wick past the level but short of 2σ → no setup
- Into 2σ but no wick past the level → no setup
- Sweep with no confirmation in 6 bars → recorded `unconfirmed_sweep`
- A self-confirming sweep bar is not traded and is flagged
- Multiple setups in one session are all recorded
- Confirmation on the last tradable bar → `no_entry_bar_before_flat`
- Entry price is the next bar's **open**, not the confirmation close
- Bands are read at the confirmation bar, not the entry bar

**`test_ledger.py`**
- Serialise/load round-trips exactly
- Gross figures are invariant to any fee input (the free-costs claim, asserted)
- A ledger missing `paths` for an unconfirmed sweep still reconciles session counts

**`test_scoring.py`**
- Net P&L under a given cost model matches a hand-computed value
- Zero cost reproduces gross exactly
- Per day, the first setup passing the cell's filters is the one taken
- A cell excluding the first setup takes the day's next qualifying setup
- `bars_waited` and `sweep_sigma` filters select the expected subsets
- Breakeven cost rate is interpolated; negative-at-zero reports the lowest tested level
- **Sign regression:** a ledger constructed to lose money is reported as losing

**`test_signal_trade_simulator.py` (additions)**
- `target_price` overrides the R-derived target
- Omitting it preserves existing behaviour exactly
- A target on the wrong side of entry raises

**`test_session_tz.py`**
- UTC splitting produces the expected day boundaries
- The 00:00–08:00 Asian window and the 23:55 flat-by resolve correctly
- The IST default is unchanged for existing callers

**`test_placebo.py` (additions)**
- Target distance is held fixed alongside stop distance
- Entry bar and direction are the only randomised quantities

**`test_navigator_report.py`**
- Emits a `columns` array
- Live/retro split matches the cell's filters
- `excluded_by` is populated on every retro event

**`frontend/src/hypothesisColumns.test.mjs`**
- A report with `columns` renders those columns
- A report without `columns` falls back to the existing behaviour

## Non-goals

Every item below is deliberate. Adding any of them to a failing result is how a
dead strategy gets resurrected as a curve fit.

- **Parameter optimisation of any kind.** No setting is chosen after seeing
  results. The robustness grid is declared in advance and only makes the test
  harder to pass.
- Engulfing or other candle-shape confirmation rules
- Trailing stops, breakeven moves, partial exits
- Re-entry after a stop-out; more than one trade per day
- Entry filters — volume, higher-timeframe trend, day-of-week, London vs NY
- The discretionary "target even this high" exit, which is not mechanisable
- Position sizing, leverage, compounding, equity curves
- Options of any kind. There is no US options data path in this repo, and the
  strategy is being tested on crypto perps regardless
- Pooling BTCUSDT, ETHUSDT and SOLUSDT into one result

## Known optimism, stated rather than fixed

When a bar gaps straight through the stop, `signal_trade_simulator` fills at the
exact stop price. Real fills would be worse. This flatters results, which is
acceptable for a go/no-go — a strategy that fails under a flattering assumption
definitely fails. Recorded in the backlog.

## What a finished run looks like

Per symbol: one ledger, plus one markdown verdict report and one Navigator JSON
per grid cell. The verdict report contains:

- Frozen parameters and the cost assumptions, labelled as estimates
- Session accounting: available / traded / skipped, broken down by reason
- The robustness grid, one row per cell, showing which stayed positive
- Headline second-half average net R at zero, base and stressed costs
- **Breakeven cost rate in bps per side** — the number that judges margin
- The fixed-R = 2.0 comparison, labelled *not the verdict*
- Distribution of `planned_rr`, against his "1 to 2, 1 to 3" claim
- The placebo percentile and seed attrition
- One word: `PASS`, `FRAGILE`, `FAIL`, or `INCONCLUSIVE`

If it fails, the strategy is closed out in the backlog with its numbers and the
next candidate is taken. That is a successful use of this design, not a wasted
one.
