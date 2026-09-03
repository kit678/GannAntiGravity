# Gann Phase 3b — Mining the Corpus — Design

Date: 2026-09-02
Status: approved premise, not yet implemented
Scope: Phase 3b of three. Phase 3a (the corpus) is complete and on `main`.
Repo: `C:\Dev\GannTesting`

## Purpose

Find out whether Gann Square-of-9 levels predict anything, by measuring the
corpus built in Phase 3a against its shadow control.

This phase explores and reports. It confirms nothing. Every number it produces
is exploratory until it survives the holdout, which this phase does not touch.

## What is actually being tested

A level is a line on a price chart. At RELIANCE's price, lines sit about ₹2.25
apart. Price crosses lines constantly no matter where they are drawn, so
"price interacted with a level 340 times" is not evidence of anything on its
own.

The shadow control answers the only question that matters: **is it these
prices, or would any grid of this shape behave the same?**

A shadow is the real ladder slid sideways by a constant. Same number of levels,
same spacing, same ordering, same labels. Only the prices change. 50 of them,
so the real value is placed against a spread rather than a single fake.

### What the shadow tests, and what it does not

Because a shadow keeps every label while moving every price, a level still
labelled "halfway" now sits at an ordinary price. Comparing real halfway levels
against shadow "halfway" levels therefore tests whether the halfway *position*
matters. The same holds for each arm, each ring, each sub-level index, and each
cross.

So structural claims — the doubling progression, arm sequence, halfway
significance — are all testable through the shadow, provided results are
reported per label group rather than pooled.

The shadow cannot test whether dividing a segment into **eight** is right rather
than six or ten. Every ladder, real and shadow, uses eighths. That is a separate
experiment requiring a corpus rebuilt at other divisions, and is out of scope.

### A rejected alternative, recorded so it is not re-proposed

An earlier draft proposed a second control that scrambled the gaps between
levels. **Withdrawn — it does not produce a readable number.**

Random gaps mean the next level is sometimes a few paise away (reached
trivially, always) and sometimes many rupees away (never reached), so
"did price reach the next level" would measure the random gap width rather than
anything about the theory. Scrambling also clumps the levels, so the control
gets touched at a different rate than the real ladder and stops being a fair
twin. The shifted shadow, read per label group, already covers the structural
questions the scramble was meant to reach.

## Pooling hides signal

Reporting one number across all levels can wash out a real effect:

```
all levels pooled:   real 25%   shadows 24%      -> looks dead
  halfway levels:    real 41%   shadows 24%      -> the actual signal
  1st sub-level:     real 22%   shadows 24%      -> nothing
  7th sub-level:     real 23%   shadows 25%      -> nothing
```

Every statistic is therefore computed per group, not pooled. Pooled figures are
reported too, but as context, never as the headline.

Groups, all already recorded on every event:

| Group | Values |
|---|---|
| `level_source` | center, sun, moon |
| `level_degree` | 0, 45, 90, 135, 180, 225, 270, 315 |
| `level_sub_index` | 1..7, null for majors |
| `level_is_halfway` | true, false |
| `level_ring` | integer, binned |
| `level_kind` | major, sub |

## The measuring device

One function, reused for every question:

```python
compare(events, statistic_fn) -> Comparison
```

`statistic_fn` maps a slice of events to a single float. `compare` runs it once
on the real events and once per shadow, then reports where the real value sits
in the shadow spread.

`Comparison` carries: the real value, the 50 shadow values, the real value's
percentile within them, the shadow min/median/max, and the sample size behind
the real value. Sample size travels with every result — a 100% rate from four
events is noise, and must not read like a finding.

A statistic returns `None` when undefined (zero denominator). `compare`
propagates that rather than substituting zero.

Building this once means every future question inherits the control
automatically, instead of depending on someone remembering to apply it.

## The five questions

Each is a pure function from an events frame to one number.

1. **Hold rate** — `RETEST_HELD / (RETEST_HELD + RETEST_FAILED)`. Of breaches
   that came back to the level, how many held.
2. **Rejection rate** — `NEVER_CONFIRMED / all resolved breaches`. How often
   price crossed but could not hold past the level.
3. **Reach-next-level rate** — hypothesis 1. See below.
4. **Mean retest depth** — mean `depth_in_sublevels` on `LADDER_RETEST` events.
   How far back into the level price came.
5. **Touch density** — touches per bar. **A fairness check, not a finding.**
   Real and shadow should be close. A large gap means the two ladders get
   different exposure and every other comparison is suspect. Report it first
   and read it before anything else.

## Reach-next-level: the headline test

The claim: after a confirmed breach of level L in direction D, price reaches the
next level beyond L before falling back through L.

That is a race between a target and a stop, both set by the geometry, which is
what makes it tradeable rather than merely descriptive.

Measured per confirmed breach:

- **Target** — the next level beyond L in direction D, within the same cross.
  Same cross because the ladder is per-cross and the hypothesis is about
  progression along one cross.
- **Stop** — price closing back through L.
- **Window** — 50 bars, matching `resolution_window_bars` so this outcome and
  the existing breach outcome cover the same span.
- **Outcome** — `REACHED`, `STOPPED`, or `TIMEOUT`.

Statistic: `REACHED / (REACHED + STOPPED)`. Timeouts are excluded from the
ratio and reported separately, since a timeout is neither a win nor a loss.

### Ladder reconstruction

The corpus stores ladders as the three integers they are a pure function of, not
as snapshots. Finding "the next level" therefore requires rebuilding the ladder
at the breach bar.

Measured: 37,110 bars reduce to **14,641 distinct ladder keys**, at 6.3 ms per
build ≈ **92 seconds** for the whole corpus, cached thereafter. Cheap enough to
rebuild rather than store.

For a shadow, the rebuilt ladder must then be shifted by that shadow's offset,
or the target price is wrong.

## Corpus gap: shadow offsets are not recorded

**Found while validating this design.** The corpus records no build metadata —
not the symbol, dates, scale, seed, nor the 50 shadow offsets.

Recovering an offset from the events was tested and **does not work**: joining
real to shadow events on `(bar_index, source, degree, sub_index)` yields 178–182
conflicting delta values per shadow, because that key is not unique within a
bar. Deriving the offsets by re-running the build's internal gap computation
would couple the mining code to build internals and break silently if either
changed.

Fix: write `meta.json` into the corpus recording symbol, date range, interval,
price scale, shadow count, seed, the computed median sub-gap, and the resolved
offset list.

Two pieces of work:

- `corpus_writer.write_corpus` gains a `meta` argument and emits `meta.json`;
  `build_gann_corpus.py` supplies it.
- A backfill script writes `meta.json` for the existing corpus by recomputing
  the gap from `ladder_keys` (~92 s), so the current 113 MB corpus does not need
  the ~40-minute rebuild.

Mining requires `meta.json` and fails loudly if it is absent, rather than
guessing.

## Output

One report, printed and written to a timestamped Markdown file so results are
diffable across runs.

Layout, in this order:

1. **Fairness check** — touch density, real vs shadow. Read this first.
2. **Headline** — the five statistics pooled, with shadow spreads.
3. **Per group** — each statistic broken down by each grouping, with sample
   sizes.
4. **Shortlist** — every group where the real value falls outside the full
   shadow range, sorted by margin, each annotated with its sample size.

The shortlist is a list of **candidates to test later**, not results. The report
says so in its own header, because a table of percentages invites being read as
findings.

## Discipline

- Runs on the `explore` slice only, via `load_events(corpus_dir)`, which
  defaults to explore. The holdout is not read in this phase, by any script.

### The boundary leak, and the buffer that closes it

**Found during spec review.** An event's outcome is forward-looking. A breach
opening in the last 50 bars of the explore slice has its resolution, its
`mfe`/`mae` and its reach-next-level race determined by bars that fall in the
holdout. So a naive explore-only filter still lets a sliver of holdout price
action into the mining.

It is small — the affected window is 50 bars out of 37,110, about 0.1% — but it
is exactly the kind of quiet contamination the split exists to prevent, and
"small" is not a reason to leave a known leak in the one mechanism protecting
every later conclusion.

Fix: mining drops events whose `bar_index` falls within `resolution_window_bars`
(50) of the explore/holdout boundary. The buffer is computed from the boundary
rather than hard-coded, and the number of dropped events is reported so the cost
is visible rather than silent.
- No multiple-comparison correction is applied and none is needed: nothing here
  concludes. Correction applies at holdout confirmation, against the shortlist
  declared before that data is opened.
- Every reported number carries its sample size.

## Modules

```
study_tool/mining/__init__.py
study_tool/mining/shadow_compare.py   # compare() and Comparison
study_tool/mining/statistics.py       # the five statistic functions
study_tool/mining/ladder_rebuild.py   # cached ladder reconstruction + next-level lookup
study_tool/mining/groups.py           # the grouping definitions
scripts/mine_gann_corpus.py           # entry point, writes the report
scripts/backfill_corpus_meta.py       # one-off meta.json for the existing corpus
```

Modified: `study_tool/corpus_writer.py` (emit `meta.json`),
`scripts/build_gann_corpus.py` (supply it).

## Out of scope

- Machine learning. Phase 3c, scoped only once this report exists.
- Touching the holdout.
- Cross-to-cross sequence mining (does Sun arm 90 lead Moon arm 45). Wanted, and
  a natural Phase 3c input, but it is a different shape of question — sequence
  rather than rate — and folding it in here would double the surface before the
  rate machinery has produced anything.
- Alternative segment divisions (sixths, tenths).
- More instruments. RELIANCE first; widening is a corpus rebuild, not a mining
  change.

## Open questions

- Is 50 shadows enough resolution? A percentile lands on a 2% grid with 50,
  which is coarse for a value near the edge. Cheap to raise to 200 — the shadow
  walk is the cheap half of the build.
- Do majors and sub-levels need separating everywhere, or only where the report
  shows they differ?
- Does the 50-bar window suit the reach-next-level test, given it was chosen for
  breach resolution? A shorter window may suit a target/stop race better.
