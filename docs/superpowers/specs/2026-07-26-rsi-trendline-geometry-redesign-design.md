# RSI Trendline Geometry Redesign

**Date:** 2026-07-26
**Status:** Pending Review
**Owner:** kit678
**Supersedes:** geometry sections (§5.2, §6.2, §6.3, §7.2, §11.3) of [2026-07-11-rsi-trendline-break-strategy-design.md](2026-07-11-rsi-trendline-break-strategy-design.md)

## 1. Problem

RSI trendlines render wrongly on the price pane: lines bisect the RSI curve, 30+
near-parallel lines crowd the chart, slopes range from impossibly steep to nearly
flat, some lines span the entire dataset, and the trade-triggering line skips
intermediate pivots in a way no human would draw.

Successive fixes — display caps, slope filters, span filters, pivot-count scoring,
RANSAC, OLS, TLS — each addressed a symptom. The chart improved but never became
correct, and `rsi_geometry.py` grew to ~900 lines holding six line builders, four
of which have no callers.

### 1.1 Measured baseline

Against `logs/backend/runs/BTCUSDT/15/2026-07-10_barctx_v2` (961 bars, BTCUSDT 15m):

| Metric | Value |
|---|---|
| Pivots detected | 242 (one per 4 bars, median gap 3) |
| Lines built | 215 |
| Lines skipping an intermediate same-kind pivot | 191 / 215 (89%) |
| Median line span | 38 bars (max 578) |
| Signals after trend filter | 94 |
| Win rate | 0.4255 |
| Net PnL | **−1178.2** |

The strategy was never profitable. A 42.6% win rate at `R=1.0` loses by
construction; the headline win-rate figure obscured this.

### 1.2 Root causes

1. **Pivot detection is too sensitive.** 242 pivots on 961 bars. The `min_swing`
   filter barely bites — it only fires when the previous pivot is opposite-kind and
   never *replaces* a weaker pivot, so raising it from 0 to 10 removes only 66
   pivots, and past `left/right=5` it removes nothing at all (103 → 103 → 103).
2. **The builder enumerates every pivot pair, then filters.** "Adjacent" is not a
   concept the generator has, so 89% pivot-skipping is structural. No filter placed
   downstream can repair a generator that never modelled adjacency.
3. **Best-fit is the wrong tool for a break strategy.** A regression line has RSI
   on both sides of it by construction, so "the break" is not a distinct event. The
   strategy needs a line that is *touched* then *broken*.
4. **Lookahead in the signal path.** Break detection runs against RANSAC lines
   selected from the whole series including future pivots
   ([rsi_trendline_hypothesis.py:82](../../../gann-visualizer/backend/analysis/rsi_trendline_hypothesis.py)).
   The break is gated to after the anchor confirms, but *which lines exist at all*
   is future-informed. The 42.6% baseline is measured under lookahead.

### 1.3 The apparent display/signal tension is not real

The premise that trade signals need far-apart pivot pairs while rendering wants
short local lines is an artifact of running two builders concurrently: `build_lines`
(all-pairs) for events and `build_best_fit_lines` (RANSAC) for display, unioned at
[rsi_trendline_hypothesis.py:82](../../../gann-visualizer/backend/analysis/rsi_trendline_hypothesis.py).
One causal builder maintaining one active line per direction makes the displayed
line *be* the event line. The tension dissolves rather than being traded off.

## 2. Goal

Replace the geometry layer with a causal engine that answers *"what line was a
trader looking at, at bar N?"* — a single question with a single answer per
direction — and correct two trade rules that diverge from the source strategy.

Non-goals: no changes to `signal_trade_simulator.py`, the report pipeline, the
walk-forward machinery, or the Gann event stream.

## 3. Strategy source of truth

From [RSI Leading Signal Trading Strategy Guide.pdf](../../strategy/RSI%20Leading%20Signal%20Trading%20Strategy%20Guide.pdf):

- Momentum precedes price; an RSI trendline break is a *leading* signal.
- The line is drawn **during a pullback against the main trend** — for a long
  setup, a falling line across RSI *peaks* while price holds above `SMA(200)`.
- Entry on the breakout candle.
- **Stop "slightly below the nearest price swing low"** (long) / above the nearest
  swing high (short).
- `RSI(14)` for 5m/15m/30m; `RSI(8)` for H4/Daily.

Two divergences from the current implementation are corrected in §6.

## 4. Architecture

### 4.1 Module split

`rsi_geometry.py` becomes a thin re-export shim over three focused modules:

| Module | Owns | Pure |
|---|---|---|
| `rsi_pivots.py` | RSI series, fractal candidates, the dominance *step function* | yes |
| `rsi_line_policy.py` | anchor policies (walk-back, and the A/B rival) | yes |
| `rsi_sweep.py` | causal state machine: lifecycle, breaks, segment emission | yes |

The shim keeps existing imports working. Each module is small enough to hold in
context at once, which the current 900-line file is not.

`rsi_pivots.py` exports dominance as a pure step function
`apply_dominance(pivot_list, candidate, min_swing) -> (new_list, changed_kind)`.
It is *owned* there but *driven* by the sweep, one candidate at a time — never run
as a batch pass over the series (§5.2).

### 4.2 Sweep / policy split

```
run_causal_sweep(rsi, candidates, policy, params) -> SweepResult
  |
  |  for bar in range(N):
  |      1. ingest fractal candidates CONFIRMED at this bar
  |         -> update running pivot list via dominance (§5.2)
  |      2. for each direction whose pivot list changed:
  |             line = policy.anchor(same_kind_so_far, newest, params)
  |             if line: retire current segment, install as active[direction]
  |      3. for each active line:
  |             if RSI crossed it -> emit BreakSignal, retire, active = None
  |
  '- SweepResult:
       pivots   : [RSIPivot]
       segments : [LineSegment(line, valid_from, valid_to, end_reason)]
       signals  : [BreakSignal(bar, side, segment_id, line_value, rsi)]
```

`policy.anchor()` is the only swappable surface. It receives pivots already
filtered to `confirmation_bar <= current_bar`, so a policy **cannot** see the
future — causality is enforced structurally by the sweep, not by each policy
remembering to behave.

`end_reason` is one of `broken`, `re_anchored`, `end_of_data`.

### 4.3 Data flow

```
candles.csv
  -> compute_rsi_series(close, period)                    rsi_pivots.py
  -> detect_fractal_candidates(rsi, left, right)
  -> run_causal_sweep(rsi, candidates, policy, params)    rsi_sweep.py
       -> pivots + segments + signals
  -> SMA(200) trend filter                                rsi_trendline_hypothesis.py
  -> swing-based stop (§6.1)
  -> simulate_trade_grid(R grid)                          signal_trade_simulator.py (unchanged)
  -> detailed_log + line_timeline -> report JSON -> Hypothesis Navigator
```

Everything above the trend filter is pure geometry with no trade awareness,
preserving §5.1 of the superseded spec.

### 4.4 Deletions

Removed from `rsi_geometry.py` (~400 lines):

| Symbol | Reason |
|---|---|
| `cluster_best_fit_lines` | zero callers |
| `_fit_cluster` | zero callers |
| `_ols_best_fit` | zero callers |
| `_total_least_squares` | zero callers |
| `build_best_fit_lines` | RANSAC — conceptually wrong for a break strategy (§1.2.3) |

`build_lines` survives, reshaped as `NearestPairAnchorPolicy`, solely so the A/B
comparison in §9 has a rival.

## 5. Geometry rules

### 5.1 Fractal candidates

A bar is a candidate high when its RSI strictly exceeds all `left_bars` before and
all `right_bars` after; a candidate low when strictly below. Confirmation bar is
`bar + right_bars` — a fixed, known lag, which is why fractal detection is retained
rather than replaced by a pure zigzag (whose confirmation lag varies from 2 to 40+
bars and would anchor lines too late to catch their own breaks).

### 5.2 Dominance pass

Applied **incrementally inside the sweep**, never as a pre-pass. Given the running
pivot list and a newly confirmed candidate:

- **Same kind as the last pivot** → keep whichever is more extreme. If the new one
  wins it *replaces* the last entry and that direction is marked changed.
- **Opposite kind** → append only if `|rsi_new − rsi_last| >= min_swing`.

This yields strict `high-low-high-low` alternation, which is what makes "adjacent
same-kind pivot" well-defined.

> **This must run incrementally.** Running dominance as a pre-pass over the whole
> series lets a pivot superseded at bar 150 silently rewrite what was anchored at
> bar 100 — a repaint. This defect was present in the design prototype and is
> called out here so the implementation does not reintroduce it.

Measured: 194 fractal candidates → 114 dominance pivots, strict alternation
verified, median gap 7 bars.

### 5.3 Anchor policy — walk back while valid

Given confirmed same-kind pivots up to the current bar and the newest one:

1. Walk from the **oldest** candidate forward, and take the **first** (i.e.
   furthest-back) pivot that satisfies all of:
   - `min_length <= newest.bar − candidate.bar <= max_span_bars`
   - correct slope sense: lower high for a down-line, higher low for an up-line
   - **no intermediate same-kind pivot pokes through**: for a down-line every
     intermediate high must sit at or below `line_value + tolerance`; for an
     up-line every intermediate low at or above `line_value − tolerance`
2. If none qualifies, no line is anchored for that direction this bar.

Skipping intermediate pivots is permitted only when the skipped pivots sit on the
correct side of the line — which is exactly what the eye does. Pivot poke-through
is therefore **zero by construction**, verified at 0/102 segments in the prototype
against 191/215 today.

`max_span_bars` exists because walk-back-while-valid legitimately finds anchors 578
bars back — geometrically valid, but reads as a chart-spanning best-fit line. Default
150 bars (~1.5 days on 15m), exposed as a swept parameter rather than a fixed
constant.

### 5.4 Lifecycle

At most **one active down-line and one active up-line** at any bar. A line ends when:

- **RSI breaks it** → emits exactly one signal, `end_reason=broken`
- **A newly confirmed same-kind pivot re-runs the walk-back** → `end_reason=re_anchored`

A broken line is never reused; it is no longer a valid trendline in the strategy's
own terms, and re-firing off a stale line would produce correlated trades that
inflate sample size without adding information.

**Handoff boundary.** The two end reasons close their window differently, and the
distinction is load-bearing:

- `broken` → `valid_to_bar = break_bar` (**inclusive**). The line was genuinely
  live at the moment it broke, and the chart must show it there.
- `re_anchored` → `valid_to_bar = successor.valid_from_bar − 1`. The successor
  owns the handoff bar.

Closing both at the same bar would leave two live lines in one direction at every
handoff — reintroducing the duplicate-line defect this redesign exists to remove.
A segment whose window would invert is dropped rather than emitted. Validity
windows are compared **inclusively** at both ends by every consumer.

### 5.5 Break detection

A break at bar `b` requires the cross to complete between `b-1` and `b`:

- down-line: `rsi[b-1] <= line(b-1)` and `rsi[b] > line(b)` → **LONG**
- up-line: `rsi[b-1] >= line(b-1)` and `rsi[b] < line(b)` → **SHORT**

Breaks are only tested from `valid_from + 1` onward, where `valid_from` is the bar
the line was installed — never before its newest anchor confirmed.

## 6. Trade rule corrections

The geometry fix alone leaves the strategy net-negative. Investigation found two
trade rules that diverge from the source strategy and dominate PnL.

### 6.1 Stop loss — swing extreme, not breakout candle

Superseded spec §7.2 places the stop at the breakout candle's own low/high. The
strategy PDF specifies the **nearest price swing low/high**. Entering at a candle's
close with a stop at that same candle's low yields a stop 0.2% of price away; noise
removes the trade before the thesis resolves.

New rule:

- long: `min(low[b − swing_lookback : b]) * (1 − buffer)`
- short: `max(high[b − swing_lookback : b]) * (1 + buffer)`

Defaults `swing_lookback = 20` bars, `buffer = 0.0005`, both swept. Median resulting
risk is 0.72% of price versus 0.21% today.

### 6.2 Max hold must scale with stop distance

`max_hold_bars = 10` with a 0.7% stop cannot reach even 1R on 15m bars. Stop
distance and hold time are coupled; the superseded spec set them independently.
Default raised to 40 and swept jointly with `swing_lookback`.

### 6.3 Measured effect

| Configuration | n | win | best R | net PnL |
|---|---|---|---|---|
| baseline production (with lookahead) | 94 | 0.426 | 1.0 | −1178.2 |
| causal geometry + §7.2 candle stop, hold=10 | 33 | 0.333 | 1.0 | −1223.7 |
| causal geometry + swing stop, hold=10 | 44 | 0.477 | 1.0 | +129.4 |
| causal geometry + swing stop, hold=20 | 44 | 0.591 | 1.0 | +2681.5 |
| causal geometry + swing stop, hold=40 | 44 | 0.523 | 3.0 | +4920.3 |
| causal geometry + swing stop, hold=60 | 44 | 0.545 | 3.0 | +5730.6 |

> **These are in-sample exploration numbers, not validation.** They come from one
> 961-bar window with n≈44, after sweeping several parameter combinations against
> that same window. They justify building the thing; they do not establish that the
> strategy works. §9 is binding before any profitability claim is made.

## 7. Output contract

### 7.1 Line timeline

The hypothesis emits `line_timeline` alongside `detailed_log`:

```json
{
  "segment_id": 17,
  "direction": "down",
  "valid_from_bar": 214, "valid_to_bar": 261,
  "valid_from_time": "...", "valid_to_time": "...",
  "end_reason": "broken",
  "anchor_a": {"bar_index": 188, "rsi": 68.4, "kind": "high", "time": "..."},
  "anchor_b": {"bar_index": 210, "rsi": 61.2, "kind": "high", "time": "..."},
  "slope": -0.327,
  "touch_count": 4
}
```

`touch_count` is the number of same-kind pivots within `tolerance` of the line over
`[anchor_a.bar, anchor_b.bar]`, inclusive of both anchors — so its minimum is 2. It
is diagnostic only and never influences selection; the walk-back rule already
maximises it by taking the furthest valid anchor.

`valid_from_bar` / `valid_to_bar` are what make the frontend correct: it renders the
segments whose validity window contains the selected event's bar, rather than
inferring which lines were live. This is the specific mechanism that stops
display/signal divergence from recurring.

### 7.2 Detailed log

Retains every field in §10 of the superseded spec, plus `segment_id` linking each
signal to its timeline entry, and `stop_rule` / `swing_lookback` recording how the
stop was derived.

The passthrough key list at
[main.py:2331](../../../gann-visualizer/backend/main.py) currently reads
`("rsi_series", "all_rsi_lines")`. `all_rsi_lines` is replaced by `line_timeline`,
so that tuple must be updated in the same change — otherwise the new payload is
silently dropped before it reaches the frontend, which is the same class of bug
Task 1 of the previous plan was written to prevent.

### 7.3 Frontend

[TVChartContainer.jsx](../../../gann-visualizer/frontend/src/TVChartContainer.jsx)
changes:

- Drop `MAX_VISIBLE_LINES`, the `+1e9` best-fit score boost, and the
  `isEventLine` matching heuristic. All three exist to manage a line cloud that no
  longer exists.
- Render only segments live at the selected event's bar: at most one down-line and
  one up-line, plus the broken segment highlighted.
- Optionally render retired segments faded, behind a toggle, for context.

The RSI curve is currently drawn as ~960 individual `trend_line` shapes. Reducing
this to the visible range only is included, since the redraw cost is already
noticeable and the code is being touched regardless.

## 8. Error handling

| Case | Behaviour |
|---|---|
| Indicator warmup | no signals until both `RSI` and `SMA(200)` are available |
| Fewer than 2 same-kind pivots | no line for that direction; not an error |
| No qualifying anchor | no active line; direction stays empty until the next pivot |
| Zero/negative risk after stop rule | skip the signal, count it in a `skipped` tally |
| Stop on wrong side of entry | skip the signal, count it |
| Signal on the last bar | skip — not simulatable |
| Missing candle for a signal bar | skip, record the issue, do not fail the run |
| Missing optional display field | degrade gracefully; core trade fields are required |

Skipped-signal counts are reported rather than silently dropped, so a run that
produces few trades is distinguishable from one that produced many and discarded them.

## 9. Validation — binding before any profitability claim

1. **Geometry invariants** (property tests, synthetic + real series)
   - zero pivot poke-through across all emitted segments
   - never more than one active line per direction at any bar
   - strict `high-low-high-low` alternation in the pivot stream
   - every segment's `valid_from` ≥ its newest anchor's confirmation bar
2. **Causality test.** Run the sweep on bars `0..k` for increasing `k`; assert that
   segments and signals emitted for bars `≤ k` never change as `k` grows. This is
   the regression test for the repaint defect in §5.2 and must fail against a
   pre-pass dominance implementation.
3. **A/B comparison.** `WalkBackAnchorPolicy` vs `NearestPairAnchorPolicy` on
   identical runs, identical trade rules. Reports both geometry quality
   (poke-through rate, lines on screen) and trade outcome.
4. **Walk-forward.** No profitability claim is made from §6.3. The parameter set
   must be fitted in-sample and evaluated out-of-sample through the existing
   walk-forward path, across more than one symbol and timeframe.
5. **Navigator smoke test.** Select an RSI event; confirm exactly the lines live at
   that bar render, the broken line is highlighted, and the anchors sit on RSI
   pivots.

## 10. Risks

| Risk | Mitigation |
|---|---|
| n≈44 is too small to conclude anything | §9.4 walk-forward across symbols/timeframes before any claim |
| §6.3 gains are curve-fit to one window | parameters swept out-of-sample; report both in- and out-of-sample |
| Honest causal numbers may be worse than the lookahead baseline | expected and correct; the baseline was never real |
| Frontend regression for Gann events | RSI overlay path is separate; Gann rendering untouched |
| Re-anchoring produces more segments than expected (123 vs 95) | each re-anchor is a real causal event; asserted by the §9.2 test |

## 11. Spec self-review

- **Placeholders:** none. Every parameter has a default and a sweep range.
- **Consistency:** §4.2 sweep, §5.2 incremental dominance, and §9.2 causality test
  all describe the same single-pass model. §5.3's `max_span_bars` matches §6.3's
  measured configuration.
- **Scope:** one implementation plan — geometry replacement plus two named trade-rule
  corrections. The trade-rule corrections are in scope because the geometry fix
  cannot be evaluated without them (§6.3 row 2 shows geometry alone is net-negative).
- **Ambiguity:** "adjacent pivot" is defined via §5.2 strict alternation; "valid
  line" via §5.3's three conditions; "break" via §5.5's two-bar cross. Poke-through
  tolerance, span cap, swing lookback and max hold are all named parameters with
  defaults, not prose.
- **Superseded sections** are listed in the header so the older spec is not read as
  still authoritative on geometry.
