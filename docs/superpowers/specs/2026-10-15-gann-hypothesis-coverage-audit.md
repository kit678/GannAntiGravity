# Hypothesis Coverage Audit

Date: 2026-10-15
Prompted by: discovering that the doubling progression — hypothesis #1 in the
Phase 3a corpus design — was never implemented or tested, despite the Phase 3b
spec asserting it was covered.

Sources audited:
- `2026-09-02-gann-phase3-corpus-design.md` — the five hypotheses
- `2026-08-31-gann-ladder-event-logger-design.md` — seven open questions
- What Phase 3b actually built: 7 statistics × 6 groupings

## How the gap happened

The Phase 3b spec claims:

> "So structural claims — the doubling progression, arm sequence, halfway
> significance — are all testable through the shadow, provided results are
> reported per label group rather than pooled."

**That claim is wrong for doubling.** Grouping by `level_sub_index` answers
"does sub-level 4 win more often than sub-level 2" — a comparison of *rates
between groups*. The doubling claim is about the *distance price travels*
growing 1 → 2 → 4 → 8. No rate statistic measures a distance progression, so no
amount of grouping would ever surface it.

Doubling is also absent from the 3b spec's own out-of-scope list (which does
name ML, cross-to-cross sequences, alternative divisions, more instruments). So
it was never consciously deferred. It fell between a spec that said "covered"
and a plan that implemented five rates.

**Process failure:** the Phase 3b plan was written from the Phase 3b spec. The
Phase 3a hypothesis list was never ticked off against it.

## What Phase 3b actually built

**Statistics (7):** hold_rate, rejection_rate, mean_retest_depth, touch_density,
reach_rate (per stop depth × window), timeout_share, already_hit_share.

**Groupings (6):** level_source, level_degree, level_sub_index,
level_is_halfway, level_ring_bin, level_kind. **Each used alone — no
cross-products.**

**Fixed in the corpus, never varied:** `breach_mode="close"`,
`confirmation_closes=2`, `touch_tolerance_sublevels=0.1`,
`resolution_window_bars=50`, `retest_window_bars=50`, eighths division, one
instrument (RELIANCE), one period, scale ×1.

## The five hypotheses

| # | Hypothesis | Status |
|---|---|---|
| 1a | After a breach, price reaches the next level in sequence | **TESTED.** `reach_next_rate`. Confirmed 8/13 on holdout. Caveat: ~65% is confirmation lag. |
| 1b | Within a segment the step doubles (1st → 2nd → 4th → 8th) | **NOT TESTED.** No measurement of step size. |
| 1c | Across major marks likewise (45° → 90° → 180° → 360°) | **NOT TESTED.** Worse — the target is always the adjacent 1/8th line (~₹2.25), never the next major (~₹18). Major-to-major progression has never been measured at all. |
| 2a | Levels act as support/resistance on later visits | **PARTIALLY TESTED.** `hold_rate` and `mean_retest_depth` measure this at a retested level. |
| 2b | ...including levels price skipped over | **NOT TESTED.** A skipped level emits no event, so the events alone cannot show it. Derivable from `ladder_keys` + `bars`, but no code exists. |
| 3 | Retest permutations, and under what conditions | **MOSTLY TESTED.** The `outcome` field is the permutation space. The 2026-09-03 pullback sweep added the retest-then-continue path. "Under what conditions" is answered only at the label-group level — no market conditions (volatility, trend, time of day) are recorded or grouped. |
| 4 | Arm sequence — does one cross's arm order predict another's | **NOT TESTED.** Consciously deferred: explicitly in the 3b out-of-scope list as "sequence rather than rate". Data is sufficient (every event has source + degree + bar_index). |
| 5 | Arm identity — is arm 90 of Sun related to arm 90 of centre | **PARTIALLY TESTED.** We group by degree (pooled across sources) and by source (pooled across degrees). The two are never crossed, so the interaction was never isolated. Cheap to add. |

## The seven Phase 2 open questions

| Question | Status |
|---|---|
| Which breach definition predicts — wick or close, how many closes? | **NOT TESTED.** One setting baked in. Needs a corpus rebuild to vary. **Now the highest-priority question**: `confirmation_closes=2` is the direct cause of the ~65% confirmation-lag artefact. |
| Do levels from one cross outperform another? | **TESTED.** Centre and Moon held on holdout; Sun did not. "Does it vary by regime" — not tested, no regime labels. |
| Does the doubling progression appear? | **NOT TESTED.** |
| Do skipped intermediate levels act as S/R later? | **NOT TESTED.** |
| Does arm angle matter — cardinals (0/90/180/270) vs diagonals? | **PARTIALLY.** Per-arm numbers exist, but cardinals vs diagonals was never grouped as a binary. No clear split visible by eye: explore flagged 135/225/0/90, holdout flagged 90/180. Cheap to add. |
| Does ring size condition anything (segment width grows as 8k)? | **NOT MEANINGFULLY TESTED.** Grouped by ring bin, but 92% of events sit in bin 10-19 (20,510 touches vs 1,881 in 20-29). No spread to learn from at this price. |
| Does confluence between two or three crosses matter? | **NOT TESTED.** Derivable (rebuild all three ladders, find near-coincident prices) but no code. |

## Summary

**Tested and confirmed:** 1 of 12 items (hypothesis 1a), with a known caveat.

**Partially tested:** 4 (2a, 3, 5, arm angle).

**Never tested, testable on the existing corpus** (needs new code, no rebuild):
doubling (1b), major-to-major (1c), skipped levels (2b), arm sequence (4),
source × degree cross (5), cardinal vs diagonal, confluence.

**Never tested, needs a corpus rebuild:** breach definition variants, alternative
divisions, regime conditioning, more instruments, ring spread.

**Hard constraint on all of it:** this corpus's holdout was spent on 2026-09-03.
Everything above can now be *explored* on this corpus but not *confirmed* on it.
Any confirmation needs a fresh instrument or date range.

## Priority

1. **Breach definition sweep.** Directly attacks the confirmation-lag artefact,
   which is currently the biggest problem with the one confirmed result. Needs
   a rebuild, so pair it with a second instrument and get a fresh holdout.
2. **Major-to-major progression (1c).** Cheap, reuses existing machinery, and
   addresses the "levels are only ₹2.25 apart" concern directly.
3. **Doubling (1b).** The headline untested hypothesis. New machinery — it
   measures distances, not rates.
4. Cheap grouping additions: source × degree, cardinal vs diagonal. Hours, not
   days.
5. Skipped levels (2b), confluence, arm sequence (4). Each needs real new code.

## Process fix

Any future plan derived from a spec must carry a coverage table mapping each
stated hypothesis to the task that tests it, or to an explicit "not in this
phase" with a reason. A spec asserting coverage is not evidence of coverage.
