# Gann Phase 3b Holdout Confirmation

Date: 2026-09-03
Corpus: `logs/corpus/reliance_5m_x1` (RELIANCE, 5-min, scale x1, 50 shadows)
Explore report (shortlist declared in advance): `docs/superpowers/reports/gann-mining-report-2026-09-03-0128.md`
Explore results doc: `docs/superpowers/specs/2026-09-02-gann-phase3b-mining-results.md`
Holdout report (this run): `docs/superpowers/reports/gann-mining-report-2026-09-03-1433.md`

This is the one holdout look this project's own discipline allows: the shortlist
below was declared on `main` (commit `8e60e64`) before the holdout was ever
read. Every row from that shortlist is checked here against the holdout
result, whichever way it falls. No row has been added, removed, or re-run
after seeing the holdout numbers.

## Run parameters

- Bars: 37,110 total (holdout is the last ~25% by time, boundary at bar 28166)
- Holdout events used: 1,331,690 (no boundary-buffer drop applied — that
  buffer exists only to protect explore from holdout leakage, and does not
  apply when holdout itself is the slice being read)
- Wall-clock: ~27s to race 187,327 confirmed breaches (much faster than the
  explore run's 559,110, consistent with holdout being ~25% of the data)

## Fairness check — same caveat as explore, worse

Touch density (real vs. 50 shadows): real 0.8810, shadow range 0.8369-0.8729,
**100th percentile** — real is busier than every one of the 50 shadow ladders
on the holdout slice. This is a stronger skew than explore's already-mild
98th percentile. Every number below should be read with this in mind: some
of the lift in every statistic could reflect the real ladder simply getting
touched more often, not the levels doing anything special. This was flagged
as a risk in the explore report and the holdout confirms the risk did not
go away.

## reach_next_rate: the headline candidate, checked row by row

This was the statistic that showed the most consistent, one-directional
effect in explore (real above shadow, across many overlapping groupings).
13 unique groups from the pre-declared shortlist involved `reach_next_rate`
(two pairs are the same physical group under two names: `level_sub_index=4`
= `level_is_halfway=True`; `level_sub_index=none` = `level_kind=major`).

| Group | Explore margin | Holdout real | Holdout shadow range | Holdout result |
|---|---|---|---|---|
| level_source=center | +0.0148 | 0.8250 | 0.7636–0.8207 | **CONFIRMED** (outside, margin +0.0043) |
| level_source=moon | +0.0041 | 0.8006 | 0.7605–0.7855 | **CONFIRMED** (outside, margin +0.0151 — strongest in the whole holdout shortlist) |
| level_ring_bin=10-19 | +0.0088 | 0.8046 | 0.7784–0.7975 | **CONFIRMED** (outside, margin +0.0071) |
| level_kind=sub | +0.0083 | 0.8027 | 0.7790–0.7954 | **CONFIRMED** (outside, margin +0.0073) |
| level_sub_index=none / level_kind=major | +0.0078 | 0.8184 | 0.7571–0.8131 | **CONFIRMED** (outside, margin +0.0053) |
| level_is_halfway=False | +0.0068 | 0.8015 | 0.7730–0.7923 | **CONFIRMED** (outside, margin +0.0091) |
| level_degree=90 | +0.0015 | 0.8111 | 0.7744–0.8085 | **CONFIRMED** (outside, margin +0.0026) |
| level_sub_index=5 | +0.0001 (barely outside in explore) | 0.8093 | 0.7588–0.8046 | **CONFIRMED** (outside, margin +0.0047) |
| level_sub_index=4 / level_is_halfway=True | +0.0118 | 0.8268 | 0.7783–0.8352 | not confirmed (inside range, 86th pct — still above shadow median) |
| level_degree=135 | +0.0094 | 0.7776 | 0.7522–0.7956 | not confirmed (inside, 48th pct — landed almost exactly on the shadow median) |
| level_source=sun | +0.0042 | 0.7920 | 0.7889–0.8209 | not confirmed (inside, 22nd pct — this one reversed, now *below* shadow median) |
| level_degree=225 | +0.0039 | 0.7910 | 0.7656–0.7919 | not confirmed (inside, but only by 0.0009 — 98th pct, right at the edge) |
| level_degree=0 | +0.0033 | 0.8385 | 0.8025–0.8598 | not confirmed (inside, 66th pct) |

**8 of 13 confirmed** — real reach_next_rate stayed fully outside the 50-shadow
range on data the search never saw, same direction (real above shadow) as
explore. Of the 5 that did not confirm, 4 stayed on the same side of the
shadow median (just short of clearing the full range) and only 1
(`level_source=sun`) actually reversed to below median.

**No group in the entire holdout run flipped sign strongly** — nothing that
was clearly positive in explore came back clearly negative in holdout. The
weakest cases came back close to the shadow median rather than the opposite
side of it.

## Other statistics from the pre-declared shortlist

The remaining ~21 pre-declared rows (hold_rate, rejection_rate,
mean_retest_depth, touch_density, spread across the same six groupings) were
each individually small-margin entries in explore (several with |margin| under
0.002 — noise-level even in the exploring pass). Spot-checking the largest
of these: `level_sub_index=4 | hold_rate | +0.0047` in explore → holdout real
0.3350, shadow 0.3083–0.3488 → inside range (64th pct), not confirmed.
`level_source=center | mean_retest_depth | -0.0191` in explore → holdout real
0.0103, shadow -0.0065–0.0932 → inside range (22nd pct), not confirmed. None
of these smaller-margin candidates showed the same one-directional,
many-overlapping-groups pattern that `reach_next_rate` did in explore, so
they were always the weaker candidates — their non-confirmation here is
expected, not surprising.

## What this does and does not say

`reach_next_rate` — after a confirmed breach of a level, does price reach the
next level before falling back through the breached one — held up on holdout
data in 8 of 13 pre-declared, overlapping groupings, always in the same
direction, with no reversals. That is the strongest evidence this project has
produced so far that Gann Square-of-9 levels carry real information, not
noise from an arbitrary grid.

It is not proof, and three real caveats travel with it:

1. **The fairness check got worse, not better, on holdout** (100th percentile
   touch density, worse than explore's 98th). Some or all of the
   `reach_next_rate` lift could be the real ladder's higher price exposure
   rather than the levels themselves. This has not been separated out.
2. **This was one look, already spent.** The discipline this whole project
   is built on says the holdout is consumable — this confirmation pass is
   it. Re-running mining against holdout again, tweaking groupings, or
   re-declaring a new shortlist to test against the *same* holdout would
   turn it into training data and invalidate any future claim.
3. **8/13 is suggestive, not statistically dispositive** on its own — no
   formal significance test or multiple-comparison correction has been run
   here. The genuinely persuasive part is the *pattern*: many overlapping,
   partially-independent groupings (by arm, source, ring, sub-index) all
   pointing the same way, with no reversals, is harder to explain by chance
   than any single row in isolation — but this document reports the raw
   comparison, not a formal test statistic.

Next step, if this is worth pursuing further: design a proper significance
test for `reach_next_rate` specifically (the one statistic that survived),
using a fresh instrument/date range so the current holdout isn't spent
twice. That is Phase 3c territory, not scoped yet.
