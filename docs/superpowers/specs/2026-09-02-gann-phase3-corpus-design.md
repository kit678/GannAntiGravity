# Gann Phase 3 — Mining Corpus and Shadow Control — Design

Date: 2026-09-02
Status: approved premise, not yet implemented
Scope: Phase 3a of three. Phases 1 and 2 are complete and merged.
Repo: `C:\Dev\GannTesting`. Phase 1 (level engine) lives in `C:\Dev\GannSq9`.

## Premise

Everything in the Phase 1 spec under "observed movement proclivities" is a
**hypothesis**, not a claim and not a result. This phase exists to give those
hypotheses enough data to be tested, and enough of a control to stop us
believing things that are not there.

Nothing in this phase predicts, scores, or ranks. It assembles evidence.

## What we are actually trying to find

Three crosses produce levels: `center` (fixed at square 1), `sun` and `moon`
(centred on the body's degree square, moving ~1°/day and ~13°/day).

All three use **identical arm labels** — 0, 45, 90, 135, 180, 225, 270, 315.
That was a deliberate choice in Phase 1, and it is the thing that makes
cross-to-cross questions askable at all.

The hypotheses, restated so they are testable:

1. **Progression.** After a confirmed breach of a level, price reaches the next
   level in sequence. Within a segment the step tends to double
   (1st → 2nd → 4th → 8th); across major marks likewise (45° → 90° → 180° → 360°).
2. **Support and resistance.** Levels — including intermediate sub-levels, and
   including ones price skipped over — act as support and resistance on later
   visits.
3. **Retest permutations.** A breach may retest the breached level before
   continuing to the next one, or not, or fail entirely. Which permutation
   occurs, and under what conditions, is to be measured rather than assumed.
4. **Arm sequence.** The order in which price interacts with the arms of one
   cross may correlate with its movement between the arms of another cross.
5. **Arm identity.** The arm label itself may carry meaning across crosses —
   whether arm 90 of the Sun cross relates to arm 90 of the centre cross by
   virtue of both being 90. Recorded either way; the data decides.

(1) and (2) are not alternatives. They are two things the same level does, and
(3) is the space of ways they combine.

## The core discipline

The RSI trendline strategy in this repo looked profitable until
`scripts/placebo_test_rsi.py` compared it against a control. It then landed
inside the control spread and two shifted variants beat it outright.

Phase 3 will generate far more hypotheses than that did. So the control is not
a gate we pass once and forget. **It is a ruler held up to every finding.**

Therefore the shadow corpus is built in the same pass as the real corpus, not
bolted on afterwards. Any statistic computed on the real corpus must be
computable on the shadow corpus by the same code path.

### What the shadow is

Take the real ladder. Add a constant offset δ to every level `price`. Leave
every label — square, arm degree, ring, sub-index, source — untouched.

This preserves exactly:

- the number of levels
- the spacing between them, including the uneven spacing of off-centre crosses
- their ordering, and which are majors versus sub-levels
- the relationship between the three crosses

and destroys exactly one thing: whether the levels sit at Gann prices.

That is the question, stated as an experiment: *is it these prices, or would
any grid with this shape look the same?*

δ is drawn per shadow run as a fraction of that ladder's median sub-level gap,
uniformly from [0.1, 0.9]. The bounds matter: a δ near 0 or near a whole gap
would land the shadow back on top of the real levels and dilute the contrast.

Default 50 shadow runs, configurable. That gives a distribution to place the
real value against, not a single fake to beat.

### Multiple comparisons

Every hypothesis tested against the shadow spread is one more chance to find
noise. Where a family of related tests is run (e.g. one per cross, one per arm),
the threshold is corrected for the size of that family, and the family is
declared before looking. Exploratory numbers are reported as exploratory and
never promoted to findings without a fresh pre-registered test.

## Instrument, scale and timeframe

The useful resolution is the one where an average bar's range is roughly one
sub-level. Phase 2 established this is measurable, not a matter of taste, via
`scripts/level_spacing_fit.py` in the GannSq9 repo.

Measured for RELIANCE on 2026-09-01 (spot ₹1,307, sub-level gap ₹2.25 at ×1):

| Timeframe | Avg bar range | ×1 ratio | ×10 ratio |
|---|---|---|---|
| 5 min | ₹1.81 | **0.80 fits** | 2.53 too coarse |
| 15 min | ₹3.02 | **1.34 fits** | 4.24 too coarse |
| 1 hour | ₹5.91 | 2.63 too coarse | 8.29 too coarse |
| 1 day | ₹34.35 | 15.27 too coarse | 48.21 too coarse |

Reliance traded ₹1,152–1,585 over the last two years, giving sub-level gaps of
₹2.125–2.50 across the window. The 5-minute fit therefore holds for the whole
corpus period, not just at today's price. Daily bars are unusable, confirming
the earlier finding across other tickers.

The two scales are two resolutions of one structure, not competitors:
**×10 pairs with 1-minute bars, ×1 pairs with 5–25 minute bars.** Both are
collected and tagged, so the resolution question is itself minable.

**Corpus v1: RELIANCE, 2 years, at (×1, 5-minute) and (×10, 1-minute).**

Built on one instrument for iteration speed. The corpus format, the scale
choice and the fetch layer are all written per-instrument from the start, so
widening is configuration rather than rework. More instruments is the single
highest-value expansion, for the reason in the next section.

## Samples, not columns

More derived features over the same two years of one stock does not strengthen
anything. It makes overfitting easier. The binding constraint on any later
model is the number of **independent market events**, which grows with
instruments and years, not with feature count.

This is recorded here because the natural instinct during feature engineering
is the opposite one.

## What gets stored

Three tables, written as Parquet (columnar, typed, fast to filter; CSV export
retained via the existing `export_csv` for eyeballing).

### 1. `bars`

The raw OHLC used, cached on disk so a re-run never refetches. Keyed by
`(instrument, timeframe, timestamp)`. Also carries the Sun and Moon ecliptic
longitude computed for that bar, so a re-run is reproducible without the
ephemeris.

### 2. `events`

The existing `Event` schema, already carrying everything the hypotheses need:
`level_source`, `level_degree` (the arm), `level_ring`, `level_sub_index`,
`level_is_halfway`, `level_segment_start/end`, `price_scale`, `body_degree`,
`body_square`, `breach_id`, `parent_breach_id`, plus bar index and timestamp.

Plus one new column: `shadow_id` — null for the real corpus, `0..N-1` for
shadow runs. This is what lets one code path compute a statistic on both.

### 3. `ladders` — new

**Gap identified during review.** The events record the level that was
interacted with. They do not record what the *rest of the ladder* looked like
at that moment. Hypothesis (1) asks "did price reach the next level", and
hypothesis (2) asks about levels price skipped. Neither is answerable from the
events alone.

The ladder is rebuilt only when `(price square, sun square, moon square)`
changes, so snapshotting on rebuild is far cheaper than per-bar. One row per
level per rebuild, keyed by `(rebuild_bar_index, source)`, joinable to events.

## Known defects to fix in this phase

Both found by reading the code during design review.

### Forward returns are never populated for ladder events

`Event` carries `mfe_5/10/20/50` and `mae_5/10/20/50` — how far price ran in
favour and against over the next N bars. `EventLogger.enrich()` computes them
from candles. **`gann_ladder_analyzer.py` never calls it**, so every ladder
event has these blank. They are the primary continuous outcome any later model
would regress on. The corpus runner must call `enrich()`.

### `enrich()`'s no-direction fallback leaks

When an event has no `direction`, `enrich()` falls back to
`mfe = max(exc_up, exc_down)`, `mae = min(...)` — it labels the larger move as
"favourable" after the fact. That is not a quantity anything could have
predicted, and as a training label it would leak.

`LADDER_TOUCH` events have no direction, so this fallback would apply to them.

Fix: store raw `excursion_up` and `excursion_down` per horizon alongside the
directional fields, and have mining use the raw pair for directionless events.
Do not change `enrich()`'s existing behaviour for the angular-coverage strategy
that already depends on it.

## Modules

```
scripts/build_gann_corpus.py     # entry point: fetch -> ephemeris -> run -> write
study_tool/ephemeris.py          # ported from GannSq9 backend/app/utils/ephemeris.py
study_tool/shadow_ladder.py      # δ-shifted ladder generation
study_tool/corpus_writer.py      # the three Parquet tables
```

`pyswisseph>=2.10.0` is added to `gann-visualizer/backend/requirements.txt`.
It is installed in the working environment (2.10.03) but undeclared here.

Ephemeris timing uses the bar's own timestamp converted to UTC. Dhan returns
IST epoch seconds; IST is UTC+05:30 with no DST.

## Phases 3b and 3c — named, not designed here

**3b. Feature engineering and descriptive mining.** Arm interaction sequences
per cross; cross-to-cross lead/lag; progression path frequencies; the retest
permutation space; conditioning on ring, arm, sub-index and halfway. Every
statistic computed against the shadow spread by the same code path.

**3c. Models.** Only on structure that survived 3b. Scope set once 3b has run,
because what is worth modelling is not knowable yet.

Each gets its own spec.

## Out of scope here

- Prediction, scoring, ranking, position sizing.
- Bodies beyond Sun and Moon (`level_source` is a free string; adding one needs
  no schema change).
- Additional astrological features. Explicitly wanted later, deliberately not
  now — they multiply the hypothesis count, and the shadow machinery must be
  proven before that.
- US market data. Dhan exposes no historical bars for it.
- Live trading of anything found.

## Open questions

- How many events does 2 years actually produce? The corpus runner reports
  counts before any metric is locked. If confirmed-breach-with-retest is rare,
  the hypotheses that depend on it need a longer window or more instruments.
- Is 50 shadow runs enough resolution at the corrected thresholds, given the
  ×10/1-minute corpus is ~175,000 bars and 51 passes over it is the dominant
  compute cost?
- Do the two resolutions (×1/5-min and ×10/1-min) agree? Disagreement is itself
  a finding about whether the structure is scale-invariant.
