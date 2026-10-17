# Gann AAPL Fresh Holdout - Results

Spec: `docs/superpowers/specs/2026-10-16-gann-breach-definition-sweep-design.md`. Read once.
Rule `close2` (breach_mode close, confirmation_closes 2) from `C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json`. Scale x6, 50 shadows, every row (`--slice all`, 6916182 rows).

## Touch density - read first

| statistic | real | n | shadow min | shadow max | missing | above all | z |
|---|---|---|---|---|---|---|---|
| touch_density | 0.9947 | 37302 | 0.9830 | 1.0025 | 0 | no | 0.12 |

Real touch density is not above every shadow that has one.

## Verdict (pre-registered)

**pass, selection differs**

- pooled lag-free reach rate: real 0.5534 (n=4469), shadow max 0.5523, missing shadows 0, z 2.04
- groups above all shadows: 3 of 13 (strong pass needs 7)
- dropped share: real 0.7647 against shadows 0.7652 to 0.7732; outside the shadow range, so the filtered real and shadow sets are not like-for-like
- entry-only dropped share (real): 0.0000

## Pooled

| statistic | real | n | shadow min | shadow max | missing | above all | z |
|---|---|---|---|---|---|---|---|
| lag_free_reach_rate | 0.5534 | 4469 | 0.5322 | 0.5523 | 0 | yes | 2.04 |
| dropped_share | 0.7647 | 18995 | 0.7652 | 0.7732 | 0 | no | -2.59 |
| entry_dropped_share | 0.0000 | 18995 | 0.0000 | 0.0000 | 0 | no | - |

## The 13 pre-declared groups, lag-free reach rate

Declared for the 2026-09-03 RELIANCE confirmation. At x6, ring_bin=10-19 covers AAPL only below about $253.5, so the pooled test is the primary one. A group with no rows or any missing shadow is not above all shadows.

| group | real | n | shadow min | shadow max | missing | above all | z |
|---|---|---|---|---|---|---|---|
| level_source=center | 0.5668 | 1138 | 0.5408 | 0.5836 | 0 | no | 0.74 |
| level_source=moon | 0.5365 | 2110 | 0.5215 | 0.5499 | 0 | no | 0.29 |
| level_source=sun | 0.5700 | 1221 | 0.5223 | 0.5680 | 0 | yes | 2.48 |
| level_ring_bin=10-19 | 0.5449 | 2628 | 0.5237 | 0.5524 | 0 | no | 0.77 |
| level_kind=sub | 0.5577 | 3945 | 0.5305 | 0.5575 | 0 | yes | 2.18 |
| level_kind=major | 0.5210 | 524 | 0.5127 | 0.5617 | 0 | no | -1.53 |
| level_is_halfway=False | 0.5529 | 3896 | 0.5378 | 0.5554 | 0 | no | 1.25 |
| level_is_halfway=True | 0.5567 | 573 | 0.4921 | 0.5506 | 0 | yes | 3.15 |
| level_degree=0 | 0.5640 | 695 | 0.5462 | 0.6008 | 0 | no | -0.46 |
| level_degree=90 | 0.5321 | 498 | 0.4575 | 0.5468 | 0 | no | 1.05 |
| level_degree=135 | 0.5323 | 402 | 0.5120 | 0.6036 | 0 | no | -0.56 |
| level_degree=225 | 0.5654 | 596 | 0.5253 | 0.5798 | 0 | no | 0.79 |
| level_sub_index=5 | 0.5670 | 545 | 0.5165 | 0.5796 | 0 | no | 1.27 |

Nothing else was computed on AAPL: only the touch density, the pooled lag-free reach rate, the 13 groups, the dropped and entry-only dropped shares and the verdict above. The scoring was run in registered-only mode, which does not evaluate any other statistic, so the holdout is spent on exactly these tests.
Corpus: `C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/aapl_5m_x6`
Generated: 2026-10-16 21:36

## Data check

Loader output (2026-10-16):

- 38898 bars over 501 sessions 2024-09-02..2026-09-01 (78 x 496 full days, 42 x 5 early closes)
- dropped 529 minutes after 13:00 on early-close days
- 2024-08-30 close in the data: 228.86; published AAPL close that day: 229.00. A cents gap (last 15:59 trade vs closing auction), so prices are unadjusted as assumed.
- last close before the window 228.86 x 6 = 1373, matching RELIANCE's median 1375 at x1.

What was seen of AAPL before this look: building the loader meant reading AAPL minute counts, session times and early-close volumes inside the window. No ladder statistic was computed on AAPL before this run.

## Reading

- The pre-registered pass rule is met by 0.0011 (real 0.5534 vs shadow max 0.5523, z 2.04). With 50 shadows, a real ladder with no information beats all of them about 1 time in 51.
- Strong pass is not met: 3 of 13 groups.
- Touch density shows no skew on AAPL (z 0.12), unlike RELIANCE.
- The dropped share is outside the shadow range on the low side (real drops slightly fewer rows), the opposite side from RELIANCE.
- The shadow ladders themselves reach the next level about 54% of the time after a lag-free break. The Gann-specific lift over random ladders is about one percentage point.
