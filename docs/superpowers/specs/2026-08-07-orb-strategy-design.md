# Opening Range Breakout (ORB) — Go/No-Go Test Design

**Date:** 2026-08-07
**Status:** Design — approved, not yet implemented
**Deferred work:** see [2026-08-07-strategy-research-backlog.md](../backlog/2026-08-07-strategy-research-backlog.md)

## Goal

Answer one question with a number, not an opinion:

> Does Opening Range Breakout on NIFTY / BANKNIFTY make money after costs, on data it was not designed against?

This is a **go/no-go test**, not a strategy build. If the answer is no, we delete the code and move to the next candidate in the backlog. No tuning to rescue a failing result.

## Scope

**Stage 1 (this spec):** measure P&L in index points on the underlying. Runs on free yfinance data for development; the verdict requires Dhan history.

**Stage 2 (only if Stage 1 passes):** re-measure using real 0DTE option premiums via `option_contract_service.py`. Not designed here.

Rationale for staging: if the signal has no edge on the underlying, buying options on it cannot help — option spread and theta only subtract. Measuring the underlying first also isolates *signal quality* from *option execution cost*, so a Stage 2 failure is interpretable.

## Non-goals

Explicitly out of scope for v1. Every item below is recorded with reasoning in the backlog doc:

- Parameter **optimisation** of any kind — no selecting a winning setting after seeing results. (Distinct from the fixed robustness grid defined under "Verdict rule", which is declared in advance and makes the test *harder* to pass, never easier.)
- Breakout-plus-retest variant
- Trailing stops, breakeven moves, partial exits
- Entry filters (volume, gap, trend, day-of-week, expiry-day)
- Multiple trades per day or re-entry after a stop-out
- Position sizing, leverage modelling, equity curves

## Approach

Two **pre-registered** variants. Both definitions are frozen in this document before any code runs. Each is run once. Reporting a third variant discovered mid-run would invalidate the test.

### Variant A — Classic opening range

| Element | Rule |
|---|---|
| Opening range | 09:15–09:30 IST (first three 5-minute bars) |
| ORH / ORL | Max high / min low of that window |
| Long trigger | First bar after 09:30 that **closes** above ORH |
| Short trigger | First bar after 09:30 that **closes** below ORL |
| Entry price | Close of the trigger bar |
| Stop | ORL for longs, ORH for shorts |
| Target | Entry ± (R × risk), headline R = 2.0 |
| Forced exit | Flat at 15:15 IST |
| Trades per day | One — first trigger only |

Three knobs: `or_minutes`, `entry_rule`, `r_target`. Deliberately minimal, so a positive result is hard to manufacture. `or_minutes` and `r_target` also carry declared neighbour values — see "Robustness grid".

### Variant B — Noise-band breakout

Anchored to today's open rather than a fixed box, so it adapts to volatility and handles gap days.

| Element | Rule |
|---|---|
| Anchor | `O` = open of the 09:15 bar |
| Volatility | `ATR14` computed on **daily** bars, through yesterday's close |
| Band | `O ± (k × ATR14)`, headline `k = 0.25` (neighbours declared in "Robustness grid") |
| Long trigger | First bar after 09:30 that closes above the upper band |
| Short trigger | First bar after 09:30 that closes below the lower band |
| Entry price | Close of the trigger bar |
| Stop | The opposite band |
| Target, forced exit, trades/day | Same as Variant A |

**Honesty note:** this is a simplified stand-in for the published volatility-normalised intraday momentum idea, not a reproduction of any specific paper. It should be described that way in results.

## Architecture

Signal generation is separated from trade execution. The strategy code decides *when and where to enter and where the stop goes*; it never computes P&L. This matches the existing `BaseStrategy` contract and lets both variants share one tested executor.

```
data client ──► session splitter ──► variant signal generator ──► trade simulator ──► verdict report
(yfinance/Dhan)   (session.py)        (variant_a.py / variant_b.py)  (existing)        (runner.py)
```

### New modules

All under `gann-visualizer/backend/`:

| File | Responsibility | Depends on |
|---|---|---|
| `strategy/orb/session.py` | Split a bar series into IST trading sessions; locate the opening-range window; count bars remaining until the flat-by time. Pure functions, no I/O. | pandas, pytz |
| `strategy/orb/variant_a_range.py` | One session in, at most one `CandleSignal` out, plus a diagnostics record. | `session.py` |
| `strategy/orb/variant_b_noise_band.py` | Same interface, band-based rule. Also consumes daily bars for ATR. | `session.py` |
| `strategy/orb/runner.py` | Orchestrate fetch → per-session signals → simulate → split → report. | the above + `signal_trade_simulator` |
| `scripts/run_orb_test.py` | CLI entry point. | `runner.py` |

Each variant module exposes exactly one public function:

```python
def generate_signal(session_bars: pd.DataFrame, params: dict, context: dict) -> Optional[OrbSignal]
```

`OrbSignal` is a small result object holding `signal: Optional[CandleSignal]`, a `reason` string when no signal was produced, and per-session diagnostics (range width, trigger bar, sessions bars seen). The bars-until-forced-flat count lives on `CandleSignal.max_hold_bars` — see the shared-code change below — not on `OrbSignal`, so the simulator receives everything it needs in one object. A consumer needs to know nothing about the internals of either variant.

### Reused unchanged

- `analysis/signal_trade_simulator.py` — the executor. It checks stop before target on the same bar (conservative), supports an R grid, and **already subtracts `fee_rate` and `slippage_per_side`**.
- `yfinance_client.py`, `dhan_client.py` — data, with `cache_manager` caching.
- `option_contract_service.py` — Stage 2 only.

### Deliberately not used

`backtest_engine.py` accepts `commission` and `slippage` constructor arguments and then never applies them (see `_close_position`, which computes raw `exit_price - entry_price`). Any ORB result produced through it would be optimistic by exactly the cost we are trying to measure. Logged in the backlog as an infra defect; not fixed here because ORB does not touch it.

### One required change to shared code

`simulate_trade_grid` takes a single global `max_hold_bars`, and `_future_bar_window` selects bars by index across the whole DataFrame — so a trade opened near the close would run into the **next trading day**. ORB must be flat at 15:15.

Fix: add an optional `max_hold_bars` field to `CandleSignal`, defaulting to `None`. When set, it overrides the global for that signal. Backward compatible — existing callers pass nothing and behaviour is unchanged. Covered by a new test asserting a per-signal cap truncates the window and the global still applies when the field is absent.

## Data plan

| Phase | Source | Symbols | History | Use |
|---|---|---|---|---|
| Development | yfinance | `^NSEI`, `^NSEBANK` | 5m capped at ~60 days (~40 sessions) | Build and unit-test the pipeline |
| Verdict | Dhan | NIFTY, BANKNIFTY | 5m, target 3+ years | The actual answer |

`yfinance_client.INTERVAL_LIMITS` caps 5m at 59 days and 1m at 7. Forty sessions is far too few to conclude anything. **Any report generated from a yfinance run is stamped `PRELIMINARY — INSUFFICIENT DATA` in its header and its verdict field is forced to `INCONCLUSIVE`.** This is enforced in code, not left to the reader.

`dhan_client.fetch_data` already chunks intraday requests at ~90 days, so multi-year pulls work once the API key is refreshed. The Dhan key is the only blocker on the real verdict.

Expiry weekdays for Indian index options have changed more than once. Stage 2 must read the live expiry list via `OptionSelector.get_expiry_list()` rather than hardcoding a weekday.

## Verdict rule

Frozen before the first run.

**Split:** all available sessions, chronologically, into a first half and a second half. Nothing is fitted on the first half — both halves use identical frozen parameters. The split exists only to check the result is stable over time, not to select settings.

**Headline number:** average net P&L per trade at **R = 2.0**, second half, after base costs.

`R = 1.5` and `R = 3.0` are declared robustness neighbours and are held to the weaker "must stay positive" bar (see "Robustness grid"). `R = 1.0` is reported for information only and is labelled *not the verdict*. In no case is the best-performing R selected after the fact — that would be the exact self-deception this design exists to prevent.

ORB **passes** only if all of these hold on the second half:

1. `n_trades >= 30`
2. `avg_net_pnl > 0` at base costs
3. `avg_net_pnl > 0` at **2× base costs** (survives a bad-fills world)
4. First-half `avg_net_pnl` is also `> 0` at base costs — both halves positive, so the result is not one good half carrying a coin flip
5. Beats placebo — see below

**Placebo check.** A *matched* placebo: run only on sessions where a real signal fired, keeping that session's stop distance and `max_hold_bars` unchanged, and randomising only two things — the entry bar (uniform over post-09:30 bars in that session) and the direction. Holding stop distance fixed is what makes the comparison fair; it isolates *"was the ORB trigger informative?"* from *"does this exit rule make money on any entry?"*. Run 200 seeds. ORB's average net P&L must exceed the 95th percentile of the placebo distribution. Without this, a positive result could be nothing more than intraday drift plus a favourable exit rule — the pattern `scripts/placebo_test_rsi.py` already established in this repo.

## Cost model — a stress axis, not an assumption

### Why slippage cannot be dropped

Data quality and slippage are unrelated problems. A perfect tick feed eliminates *bad prints*; it does nothing about the gap between the price you decided at and the price you are filled at. That gap has four sources, none of which a better data vendor touches:

1. **Bid-ask spread.** Bars record last-traded price. You buy at the ask and sell at the bid, on every trade, forever.
2. **Decision-to-order latency.** The rule is "the bar closed beyond the level", which is only knowable at the instant the bar closes. The order arrives after that.
3. **Stop orders become market orders.** A stop fills at whatever is available during a fast move against the position — precisely when spreads are widest.
4. **Gaps through the stop.** Price jumps past the level and fills materially worse.

Breakout systems are the worst case for all four, because they enter and exit during fast directional moves by design.

### Slippage is not tuned

Optimising slippage is meaningless — the best value is always zero. Instead it is swept as a **stress axis**, and the headline output is:

> **Breakeven slippage** — the slippage level, in index points per side, at which average net P&L crosses zero.

Sweep `slippage_per_side` over `[0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0]` and report the crossing point. This replaces an argument about the correct assumption with a fact about the strategy's margin: if ORB survives only below 0.3 points while real NIFTY futures execution costs roughly 0.5–1.0, it is dead, and no assumption debate is needed.

The verdict criteria still reference two fixed points on that sweep — base `1.0` and stressed `2.0` — so there is a crisp pass/fail, but breakeven slippage is the number that actually informs the decision.

### Fees

`fee_rate`: **0.0003** base, **0.0006** stressed. The simulator applies it as `(entry_price + exit_price) × fee_rate`, so 0.0003 is roughly 0.03% per side / 0.06% round trip of notional — a conservative stand-in for NSE index-futures brokerage plus STT, exchange charges, stamp duty and GST. This is an estimate and the report must label it as one; refine it against a real Dhan contract note before Stage 2.

## Robustness grid

Every parameter in this design was, at some point, a guess. Rather than defend the guesses, each carries a small set of neighbouring values, **declared here before any code runs**:

| Parameter | Headline | Declared neighbours |
|---|---|---|
| `or_minutes` (Variant A) | 15 | 30 |
| `k` (Variant B) | 0.25 | 0.15, 0.40 |
| `r_target` (both) | 2.0 | 1.5, 3.0 |

This is not a sweep and no winner is selected from it. The rule runs in one direction only:

- The **headline cell** must pass all five verdict criteria.
- Every **other cell** in the grid must additionally show positive `avg_net_pnl` at base costs on the second half.
- Headline passes but neighbours do not → verdict is **`FRAGILE`**, not `PASS`.

A genuine edge is positive across neighbouring settings; it degrades gracefully. A curve fit works at one setting and collapses on either side. Requiring the whole grid to hold makes this test strictly harder to pass than a single pre-registered cell, which is the point.

## Error handling

Failures must be loud and countable. The failure mode to avoid is a clean-looking report built from silently dropped days.

| Situation | Behaviour |
|---|---|
| Holiday / half day / short session | Skip, record `reason`, count it |
| Opening-range window has fewer bars than expected | Skip, record `reason` |
| Range degenerate (`ORH == ORL`) | Skip, record `reason` |
| Data client returns empty | Raise with symbol and window. Never return an empty result that reads as "no trades" |
| yfinance rate limit / network error | Propagate; do not swallow |

Every report prints `sessions_available`, `sessions_traded`, `sessions_skipped`, and a breakdown by reason. A traded/available ratio far from expectation is treated as a bug signal, not a finding.

Known optimism, stated in the report rather than fixed: when a bar gaps straight through the stop, the simulator fills at the exact stop price. Real fills would be worse. This makes results slightly flattering, which is acceptable for a go/no-go — a strategy that fails under a flattering assumption definitely fails.

## Testing

TDD. Tests are written before each module and run on hand-built synthetic bars with no network access.

**`test_orb_session.py`**
- Splits a multi-day series into the correct sessions in Asia/Kolkata
- Locates the 09:15–09:30 window correctly
- Counts bars-to-flat correctly, including a short session

**`test_orb_variant_a.py`**
- Upward break → LONG at the expected bar, entry price, and stop
- Downward break → SHORT, mirrored
- Inside day (never leaves the range) → no signal
- Day that breaks both ways → only the first trigger is taken
- Degenerate range → skipped with the right `reason`

**`test_orb_variant_b.py`**
- Band computed correctly from a known ATR14
- No breach → no signal
- Gap-open day anchors to today's open, not yesterday's close

**`test_orb_runner.py`**
- Two fabricated sessions run end to end and produce the expected trade count
- Train/test split lands on the expected session boundary
- A yfinance-sourced run forces `verdict = INCONCLUSIVE`
- Fewer than 30 second-half trades forces `verdict = INCONCLUSIVE`, never `PASS`
- Placebo runner keeps stop distance and `max_hold_bars` fixed and varies only entry bar and direction
- Headline cell passing while a neighbour cell is negative yields `FRAGILE`, never `PASS`
- Breakeven slippage is found by interpolation across the sweep, and a strategy negative at zero slippage reports breakeven slippage of `0.0`, not a negative number
- **Sign regression:** a synthetic set constructed to lose money is reported as losing. Guards against a sign error making everything look profitable.

**`test_signal_trade_simulator.py` (addition)**
- Per-signal `max_hold_bars` truncates the window
- Omitting it preserves existing global behaviour

## What a finished run looks like

A single report file per variant per symbol containing:

- The frozen parameters and the fee assumption, labelled as an estimate
- Session accounting (available / traded / skipped, with reason breakdown)
- The R grid table, labelled *not the verdict*
- The headline cell's second-half average net P&L at base and 2× costs
- **Breakeven slippage** — the headline number for judging margin
- The robustness grid, one row per cell, showing which cells stayed positive
- The placebo percentile
- A one-word verdict: `PASS`, `FRAGILE`, `FAIL`, or `INCONCLUSIVE`

If both variants fail, ORB is closed out and we take the next item from the backlog. That outcome is a successful use of this design, not a wasted one.
