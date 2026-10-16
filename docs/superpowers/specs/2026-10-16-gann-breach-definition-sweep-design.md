# Gann Breach Definition Sweep — Design

Date: 2026-10-16
Prompted by: the hypothesis coverage audit (2026-10-15, on branch
`feat/alpaca-us-market-data`, `docs/superpowers/specs/2026-10-15-gann-hypothesis-coverage-audit.md`),
priority 1: "Breach definition sweep ... pair it with a second instrument and
get a fresh holdout."

## The problem

The one confirmed result, `reach_next_rate` (8 of 13 groups on the RELIANCE
holdout), carries a known artefact: about 65% of raced breaches had already
touched their target by the time the breach was confirmed. A breach confirms
after **two** closes beyond the level, so price often reaches the next level
during the wait. Those rows score as easy wins that a trader acting at
confirmation could never have had.

The breach rule is baked into the corpus build
(`scripts/build_gann_corpus.py:36-47`: `breach_mode="close"`,
`confirmation_closes=2`), so it has never been varied.

## The question

Under which breach rule do Gann levels predict "price reaches the next level"
**after removing every win the trader could not have taken**, and does that
hold on an instrument the ladder has never seen?

## Method in one paragraph

Rebuild the RELIANCE corpus under four breach rules. For each, compute a
*lag-free* reach rate (defined below) for the real ladder and the 50 shadow
ladders. Pick the rule by a rule written down here, before any AAPL data is
built. Then build one AAPL corpus under that single rule and read it exactly
once. AAPL is the fresh holdout; RELIANCE is now explore-only (its holdout was
spent 2026-09-03).

## Breach rules swept (RELIANCE)

| Name | `breach_mode` | `confirmation_closes` |
|---|---|---|
| `wick1` | wick | 1 |
| `close1` | close | 1 |
| `close2` | close | 2 (the existing rule, rebuilt for like-for-like comparison) |
| `close3` | close | 3 |

Everything else stays fixed at the existing corpus values: touch tolerance 0.1
sub-levels, resolution window 50 bars, eighths division, 50 shadows, seed 7,
scale x1, RELIANCE 5-minute 2024-09-02 to 2026-09-01 (cached bars, no refetch).

The analyzer already reads these settings from its config
(`study_tool/gann_ladder_analyzer.py:20-29`); only the build script hard-codes
them. Confirmation bars are consecutive: a bar that fails to close beyond
rejects the breach (`gann_ladder_analyzer.py:237-252`). So the cross bar of a
confirmed breach is always `confirmation bar - (confirmation_closes - 1)`.

## The lag-free reach rate

For a confirmed breach, let `c` be its cross bar and `k` its confirmation bar
(`c = k - (confirmation_closes - 1)`), and `T` its target (the next level, as
already computed by `add_reach_outcomes`).

- `target_hit_before_entry` = True if any bar in `c..k` inclusive touched `T`
  (high >= T going up, low <= T going down). This widens the existing
  `target_already_hit`, which only checks bar `k`.
- **lag-free reach rate** = `reach_outcome` REACHED / (REACHED + STOPPED),
  over confirmed breaches with `target_hit_before_entry == False`.

The race itself is unchanged: it starts on the bar after `k`, with the stop on
the breached level (depth 0) and the corpus window. A trader acting at the
close of `k` sees exactly this: target not yet touched, stop on the level.
Nothing after bar `k` is used to decide whether a row is included, so the
filter adds no lookahead.

The same filter applies to shadow rows, so real and shadow stay comparable.
The old `reach_next_rate` and `target_already_hit` keep their meaning.

## Selection rule (pre-registered, RELIANCE)

For each breach rule, on the whole RELIANCE corpus (all of it is explore now):

1. Pooled lag-free reach rate, real vs the 50 shadows.
   `margin = real - max(shadow)`.
2. The rule with the largest pooled margin is chosen. A tie within 0.001 goes
   to the rule with fewer closes (less lag).
3. **Stop rule:** if no breach rule has a positive pooled margin, the sweep
   reports a null and AAPL is **not built**. The fresh holdout is kept for a
   better question.

Also reported per rule (for reading, not for choosing): the 13-group count
(below), the share of breaches dropped by the filter, the plain
`reach_next_rate`, and touch density real vs shadow (the fairness check).

## Fresh holdout: AAPL

- **Bars:** `data_local/aapl_rth_1m.json` (Alpaca, regular trading hours),
  resampled to 5-minute bars inside each session (09:30-16:00 New York),
  2024-09-02 to 2026-09-01, the same window as RELIANCE. About 39,000 bars,
  close to RELIANCE's 37,110. Bars are cached as parquet with `sun_degree` and
  `moon_degree` added by the existing bar cache path.
- **Scale x6.** A level's price is `square / scale`. Gann sub-level spacing as
  a share of price goes as `1 / sqrt(price x scale)`. RELIANCE's median close
  is 1375 at x1; AAPL's is 247, and 247 x 6 = 1482. So x6 gives AAPL levels the
  same relative spacing as RELIANCE (within about 4%). Integer, so no
  float-square edge cases.
- **One corpus, one rule:** the chosen breach rule only. 50 shadows, seed 7.
- **One look:** the whole AAPL corpus is the holdout slice. Mining reads it
  once, through a new `--slice all` option (no 25% split; nothing on AAPL was
  ever explored).

### AAPL pass rule (pre-registered)

Using the same 13 groups as the 2026-09-03 confirmation
(`level_source` center / moon / sun; `level_ring_bin=10-19`;
`level_kind` sub / major; `level_is_halfway` False / True;
`level_degree` 0 / 90 / 135 / 225; `level_sub_index=5`):

- A group **confirms** when its real lag-free reach rate is above all 50
  shadows.
- **AAPL passes** when the pooled real rate is above all 50 shadows **and** at
  least 7 of the 13 groups confirm.
- If a group has no rows on AAPL (for example a ring bin AAPL never reaches at
  x6), it counts as not confirmed. It is not dropped from the 13.

Touch density on AAPL is reported first. If real is busier than every shadow
(100th percentile), the write-up says so beside the verdict.

## What gets built

1. **Build script settings.** `build_gann_corpus.py` takes `--breach-mode` and
   `--confirmation-closes` (defaults: close, 2, so old commands are
   unchanged). Both are written into `meta.json`.
2. **Corpus meta.** `CorpusMeta` reads both, defaulting to close / 2 for the
   existing corpus whose meta lacks them.
3. **Lag-free column.** `add_reach_outcomes` adds `target_hit_before_entry`,
   using `meta.confirmation_closes` to find the cross bar.
4. **Statistic.** `lag_free_reach_rate` in `mining/statistics.py`.
5. **AAPL bars.** A loader that turns the 1-minute RTH JSON into cached 5-minute
   bars with Sun and Moon longitudes, through the existing `bar_cache` path.
6. **`--slice all`** in `mine_gann_corpus.py`.
7. **Sweep runner.** A script that builds the four RELIANCE corpora, scores
   each, applies the selection rule, and writes the choice to a results doc
   **before** any AAPL step can run. The AAPL step refuses to run if that
   choice file is missing or says "null".

Each piece gets a unit test in `backend/tests/study_tool/`. In particular:
- the cross-bar arithmetic for k = 1, 2, 3 (target touched on the cross bar,
  on a middle bar, on the confirmation bar, never);
- the filter uses no bar after `k`;
- the 5-minute resample keeps session boundaries (no bar spans an overnight
  gap) and sums volume;
- old corpus meta without the new keys loads as close / 2.

## Coverage table

| Item from the audit | Where it is handled |
|---|---|
| Breach definition: wick vs close | `wick1` vs `close1` |
| Breach definition: how many closes | `close1` / `close2` / `close3` |
| Confirmation-lag artefact (~65%) | lag-free reach rate |
| Fresh holdout needed | AAPL, one look |
| Second instrument | AAPL |
| Alternative divisions, regime labels, ring spread | Not in this phase: each multiplies the corpus count; do them after the break rule is settled. |

## Risks

- **Touch density skew** (real ladder busier than shadows) is unresolved and
  could lift any reach statistic. Reported, not fixed, in this phase.
- **Wick mode at k=1** confirms on the very bar that touched the level, so its
  cross bar and confirmation bar are the same bar. The filter then drops rows
  whose own bar also touched the target. That is correct, not a bug.
- **Close-mode first bar must open on the near side of the level**
  (`_crossed`, `gann_ladder_analyzer.py:153-158`): gaps through a level are not
  crosses. Kept as is so every rule shares the same cross test.
- **Disk:** each RELIANCE corpus is ~115 MB of events. Four corpora plus AAPL
  is ~600 MB under `logs/corpus/`, which is gitignored.
