# Gann Phase 3b Mining Results (first run)

## 1. Run parameters

- Corpus: `logs/corpus/reliance_5m_x1` (main checkout, `C:\Dev\GannTesting\gann-visualizer\backend\logs\corpus\reliance_5m_x1`)
- Symbol: RELIANCE
- Interval: 5 (minutes)
- Price scale: x1
- Shadow count: 50
- Bars: 37110, resolution window: 50 bars
- Mining code: `feat/gann-phase3b-mining` branch, worktree at `C:\Dev\GannTesting\.worktrees\gann-phase3b-mining\gann-visualizer\backend`
- Report written to: `C:\Dev\GannTesting\docs\superpowers\reports\gann-mining-report-2026-09-03-0128.md`
- Wall-clock run time: ~8m36s (started 01:19:44 MDT, report file written 01:28:20 MDT). Internal race step alone: 559,110 breaches raced in 131s.

## 2. Fairness check

Touch density (touches per bar), real vs. shadow:

| group | real | n | shadow min | shadow median | shadow max | percentile |
|---|---|---|---|---|---|---|
| touch_density | 0.8271 | 22391 | 0.8015 | 0.8147 | 0.8295 | 98.0 |

The real value sits *inside* the full shadow range (0.8015-0.8295), so the control does not fail outright. But it lands at the 98th percentile — only 1 of the 50 shadow ladders was busier than the real ladder, and the real value is close to the shadow max, not near the median (0.8147). This is a mild-to-moderate skew, not a clean pass. **Read every other number in this report with that caveat**: the real ladder gets slightly more price exposure than a typical shadow ladder, so headline differences could be partly (not necessarily wholly) attributable to that extra exposure rather than to level placement itself.

## 3. Boundary buffer

- Explore/holdout boundary: bar index 28166
- Events dropped to the boundary buffer (within 50 bars of the boundary, whose outcome depends on holdout price action): 5,647
- Explore events used after dropping: 3,989,422

## 4. Pooled/headline figures (context only, not findings)

These are explore-slice aggregates across all groupings in the report (`level_degree`, `level_is_halfway`, `level_kind`, `level_ring_bin`, `level_source`, `level_sub_index`). They are provided for orientation only — none of them are statistically confirmed, and none should be read as a trading signal.

- **hold_rate**: ranges roughly 0.21-0.27 across groups (n per group ~780-9250), generally landing at or above the shadow median (many groups at 80-100th percentile).
- **rejection_rate**: ranges roughly 0.26-0.30 across groups (n ~1150-14100), mostly close to shadow median with no extreme outliers.
- **reach_next_rate**: ranges roughly 0.75-0.81 across groups (n ~780-10200), consistently at or above shadow values (many groups at 90-100th percentile) — this is the statistic with the most consistent one-directional skew.
- **timeout_share**: 0.0000 for every group, real and shadow alike — no timeouts occurred in this corpus/window configuration for either arm.
- **mean_retest_depth**: highly variable by group, from about -0.09 to +0.46; `level_kind=major` / `level_sub_index=none` stands out at 0.4618 (shadow median 0.4690, so actually mid-pack despite the large absolute value — major levels simply retest deeper than sub levels for both real and shadow).
- **touch_density**: ranges from about 0.06 (level_degree=270) to 0.76 (level_ring_bin=10-19, the ring holding almost all levels), tracking shadow closely in most groups (percentiles mostly 30-100, no group outside its shadow range in this statistic alone — see shortlist for the two touch_density entries that do sit outside range at the `level_kind`/`level_sub_index=major/none` grouping).

## 5. Shortlist (verbatim from generated report)

Groups whose real value falls outside the **entire** shadow range, sorted by margin. Sample size is included because a rate built on a handful of events lands outside the range easily and means nothing.

| group | statistic | real | n | shadow min | shadow max | margin |
|---|---|---|---|---|---|---|
| level_sub_index=4 | mean_retest_depth | -0.0046 | n=1306 | 0.0255 | 0.0705 | -0.0301 |
| level_is_halfway=True | mean_retest_depth | -0.0046 | n=1306 | 0.0255 | 0.0705 | -0.0301 |
| level_ring_bin=20-29 | mean_retest_depth | -0.0902 | n=779 | -0.0607 | -0.0134 | -0.0295 |
| level_source=center | mean_retest_depth | 0.0115 | n=2633 | 0.0306 | 0.0659 | -0.0191 |
| level_source=center | reach_next_rate | 0.7873 | n=2929 | 0.7627 | 0.7725 | 0.0148 |
| level_sub_index=6 | rejection_rate | 0.2861 | n=1940 | 0.2340 | 0.2727 | 0.0134 |
| level_sub_index=4 | reach_next_rate | 0.7890 | n=1431 | 0.7538 | 0.7771 | 0.0118 |
| level_is_halfway=True | reach_next_rate | 0.7890 | n=1431 | 0.7538 | 0.7771 | 0.0118 |
| level_degree=135 | reach_next_rate | 0.8040 | n=1143 | 0.7578 | 0.7946 | 0.0094 |
| level_ring_bin=10-19 | reach_next_rate | 0.7846 | n=10212 | 0.7682 | 0.7758 | 0.0088 |
| level_kind=sub | reach_next_rate | 0.7783 | n=9753 | 0.7631 | 0.7700 | 0.0083 |
| level_sub_index=none | reach_next_rate | 0.8084 | n=1336 | 0.7708 | 0.8006 | 0.0078 |
| level_kind=major | reach_next_rate | 0.8084 | n=1336 | 0.7708 | 0.8006 | 0.0078 |
| level_is_halfway=False | reach_next_rate | 0.7809 | n=9658 | 0.7666 | 0.7741 | 0.0068 |
| level_degree=90 | mean_retest_depth | -0.0050 | n=1586 | 0.0006 | 0.0752 | -0.0056 |
| level_sub_index=none | touch_density | 0.0934 | n=2529 | 0.0772 | 0.0885 | 0.0049 |
| level_kind=major | touch_density | 0.0934 | n=2529 | 0.0772 | 0.0885 | 0.0049 |
| level_sub_index=4 | hold_rate | 0.2692 | n=1300 | 0.2443 | 0.2645 | 0.0047 |
| level_is_halfway=True | hold_rate | 0.2692 | n=1300 | 0.2443 | 0.2645 | 0.0047 |
| level_sub_index=5 | hold_rate | 0.2533 | n=1287 | 0.2244 | 0.2490 | 0.0043 |
| level_source=sun | reach_next_rate | 0.7972 | n=3413 | 0.7834 | 0.7931 | 0.0042 |
| level_source=moon | reach_next_rate | 0.7676 | n=4747 | 0.7498 | 0.7635 | 0.0041 |
| level_degree=225 | reach_next_rate | 0.7826 | n=966 | 0.7521 | 0.7787 | 0.0039 |
| level_degree=0 | reach_next_rate | 0.7872 | n=1931 | 0.7549 | 0.7839 | 0.0033 |
| level_degree=90 | touch_density | 0.1392 | n=3769 | 0.1280 | 0.1363 | 0.0029 |
| level_source=moon | hold_rate | 0.2438 | n=4361 | 0.2302 | 0.2412 | 0.0026 |
| level_kind=sub | mean_retest_depth | -0.0018 | n=8925 | 0.0006 | 0.0189 | -0.0024 |
| level_degree=90 | reach_next_rate | 0.7538 | n=1718 | 0.7269 | 0.7523 | 0.0015 |
| level_sub_index=2 | rejection_rate | 0.2935 | n=1959 | 0.2567 | 0.2923 | 0.0012 |
| level_degree=315 | hold_rate | 0.2369 | n=1148 | 0.2138 | 0.2357 | 0.0012 |
| level_degree=90 | hold_rate | 0.2300 | n=1574 | 0.2119 | 0.2293 | 0.0006 |
| level_sub_index=1 | touch_density | 0.1031 | n=2790 | 0.1034 | 0.1103 | -0.0003 |
| level_sub_index=5 | reach_next_rate | 0.7900 | n=1414 | 0.7607 | 0.7899 | 0.0001 |
| level_sub_index=7 | touch_density | 0.0991 | n=2683 | 0.0992 | 0.1060 | -0.0001 |

## 6. What this does not say

Every row above is an explore-slice candidate, not a finding. The search has already seen this data — that is exactly what makes a group "look strong" here, and it is why nothing in this document is confirmed or actionable on its own. In particular: `reach_next_rate` shows up repeatedly and in one consistent direction (real above shadow) across many overlapping groupings (by degree, by source, by kind, by ring, by sub-index), which is suggestive of a real, corpus-wide effect worth testing — but it is still a hypothesis, not a result, and the fairness check above means part of that lift could reflect the real ladder's slightly higher touch density rather than the levels doing anything special. Confirmation requires spending the holdout exactly once, against a shortlist of groups declared *before* the holdout is opened, with the result recorded regardless of which way it falls. No multiple-comparison correction has been applied to the numbers above, and none is needed at this stage, because nothing here concludes — correction belongs at the holdout-confirmation step, against a pre-declared shortlist, not here.
