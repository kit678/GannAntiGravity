# Pullback-Tolerant Reach Sweep — Results

Date: 2026-09-03
Corpus: `logs/corpus/reliance_5m_x1` (RELIANCE, 5-min, x1, 50 shadows)
Report: `docs/superpowers/reports/gann-mining-report-2026-09-03-1705.md`
Slice: **explore only.** This corpus's holdout was spent on 2026-09-03
(`2026-09-03-gann-phase3b-holdout-confirmation.md`) and must not be reopened.
Nothing here is confirmed or confirmable on this corpus.

## What was tested

The confirmed result used a strict race: after a confirmed breach of level L,
does price reach the next level before *ever closing back through L*? The user
observed that price often breaks L, dips back, retests L, holds, and only then
carries on to the next level — a path the strict test scores as a failure.

So the stop was generalised from "L itself" to "d ladder steps behind L", and
swept at d = 0 (the strict test), 0.5, 1 and 2 steps, at race windows of 50 and
100 bars. One step is the adjacent 1/8th sub-level, ~₹2.25 on this instrument.

Agreed rule: the win is a bar's high/low touching the next level; the loss is a
bar **closing strictly beyond** the stop price. Touching the stop, or wicking
through and closing back, keeps the race alive.

## Headline: the hypothesis was tested and it does not hold

**Loosening the stop does not strengthen the effect. It weakens it.**

Raw rates rise steeply as the stop widens — from ~0.78 to ~0.91 — but they rise
for the shadow ladders too, because a looser stop mechanically keeps every race
alive longer regardless of where the levels sit. The question is whether the
**gap between real and shadow** widens. It mostly narrows.

Margin = real minus the highest of the 50 shadows. Positive means real beat
every shadow.

| Group | d=0 (strict) | d=0.5 | d=1 | d=2 |
|---|---|---|---|---|
| level_source=center | **+0.0148** | +0.0075 | +0.0064 | +0.0059 |
| level_kind=sub | **+0.0083** | +0.0070 | +0.0057 | +0.0032 |
| level_source=sun | +0.0041 | **+0.0044** | +0.0010 | −0.0005 (inside range) |
| level_source=moon | +0.0041 | **+0.0069** | +0.0054 | +0.0013 |
| level_kind=major | +0.0078 | **+0.0130** | +0.0027 | +0.0029 |

Centre and sub-levels — two of the groups that survived holdout confirmation —
are strongest at the **strict** stop and decay monotonically as it loosens.
Moon, Sun and major peak at a half step and then fall away. Sun drops inside the
shadow range entirely by two steps, meaning it stops being distinguishable from
an arbitrary grid at all.

No group's edge is meaningfully better under the pullback-tolerant rule than
under the strict one. The user's observation about the price path is real — the
rates confirm those pullback-and-recover paths are common — but they are just as
common on shadow ladders, so they carry no information about whether the levels
are Gann levels.

## The window made no difference

`d0_w50` and `d0_w100` are identical to four decimal places in every group, and
the same holds at other depths. Doubling the race window changes nothing because
timeouts were already near zero — the race almost always resolves well inside 50
bars. That closes an open question from the original design: the 50-bar window,
inherited from breach resolution, is not a binding constraint on this test.

## The bigger problem this sweep uncovered

`already_hit_share` — the share of confirmed breaches whose target had already
been touched **before the race even started** — runs **0.57 to 0.72 across every
group**, clustering around 0.65.

| Group | real | shadow min–max |
|---|---|---|
| level_source=center | 0.6617 | 0.6299–0.6582 |
| level_source=moon | 0.6328 | 0.6125–0.6303 |
| level_source=sun | 0.6868 | 0.6742–0.6907 |
| level_kind=major | 0.6946 | 0.6369–0.6840 |
| level_kind=sub | 0.6519 | 0.6357–0.6492 |

A breach confirms only after two closes beyond the level. Two 5-minute closes
routinely carry price more than one 1/8th step (~₹2.25), so by the time the race
begins, the target is usually already reached. **About two-thirds of the
headline ~80% "reach next level" rate is confirmation lag, not price travelling
to the next level.**

Two things follow, and they pull in opposite directions:

- **It does not invalidate the shadow comparison.** Shadow ladders show almost
  the same already-hit share (0.63–0.69), so both arms are inflated by roughly
  the same amount and the real-vs-shadow difference survives it.
- **It does shrink what the effect is about.** Only ~35% of raced breaches
  involve price actually travelling to the target after confirmation. The
  confirmed 8/13 holdout result rests on a much smaller effective base than the
  n column suggests, and the statistic is measuring something closer to "how far
  do two confirmation closes carry price" than "do levels chain".

Real already-hit share also sits at the 100th percentile of the shadow spread in
many groups. Real levels are *more* likely than shadows to have already been
reached at confirmation — which is consistent with the unresolved touch-density
confound rather than independent of it.

## Fairness check

Unchanged from the earlier explore run: touch density real 0.8271, shadow
0.8015–0.8295, **98th percentile**. Real levels still get more price exposure
than a typical shadow ladder. Every margin in this document carries that caveat.

## What this does and does not say

**Does say:** the pullback-tolerant variant was implemented, swept across four
stop depths and two windows, and does not improve on the strict test. The strict
stop is the better-performing definition for the groups that survived
confirmation. The race window is not a limiting factor. Roughly two-thirds of
the headline reach rate is an artefact of confirmation lag.

**Does not say:** that the confirmed 8/13 holdout result is wrong. That result
stands as recorded — the depth-0 column here reproduces it bit for bit, verified
by differential test. What this adds is that the effect is smaller in substance
than its headline number, and does not grow when the test is loosened in the way
the hypothesis predicted.

**Cannot say:** anything confirmed. This is explore-slice only. Confirming any
of it needs a corpus built on a different instrument or date range.

## Suggested next step

The confirmation-lag artefact is now the largest single problem with this
statistic, larger than the pullback question that prompted this sweep. A cleaner
version of the test would start the race from the level itself rather than from
the confirmation bar, or require the target to be reached *after* confirmation
rather than at any point. That is a redefinition, not a parameter sweep, and it
would need fresh data to confirm — this corpus's holdout is spent.
