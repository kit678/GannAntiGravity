# Gann Breach Definition Sweep — Design

Date: 2026-10-16 (revised the same day after an adversarial review)
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
once. AAPL is the fresh holdout for the **Square-of-9 ladder hypothesis
only**: AAPL bars have been used by other studies in this repo (the 15m
steep-line pullback test split, fan wick/close explorations), but no Gann
ladder corpus has ever been built or read on AAPL. RELIANCE is explore-only
(its holdout was spent 2026-09-03).

## Breach rules swept (RELIANCE)

| Name | `breach_mode` | `confirmation_closes` |
|---|---|---|
| `close1` | close | 1 |
| `wick1` | wick (fixed, see below) | 1 |
| `close2` | close | 2 (the existing rule, rebuilt) |
| `close3` | close | 3 |

Everything else stays fixed at the existing corpus values: touch tolerance 0.1
sub-levels, resolution window 50 bars, eighths division, 50 shadows, seed 7,
scale x1, RELIANCE 5-minute 2024-09-02 to 2026-09-01 (the cached bars in the
main checkout's `gann-visualizer/backend/logs/corpus/bars/`, no refetch).

The analyzer already reads these settings from its config
(`study_tool/gann_ladder_analyzer.py:20-29`); only the build script hard-codes
them. Shadows walk with the same settings (`build_gann_corpus.py:150-162`), so
they get the same breach rule. Confirmation bars are consecutive: a bar that
fails to close beyond rejects the breach (`gann_ladder_analyzer.py:232-252`).
So the cross bar of a confirmed breach is always
`confirmation bar - (confirmation_closes - 1)`.

**Regression gate:** the rebuilt `close2` corpus must match the existing
`reliance_5m_x1` events exactly (same rows, same values). If it does not, stop
and find out why before scoring anything.

### Fixing wick mode

The ladder analyzer's wick mode (`gann_ladder_analyzer.py:134-145`) is not a
breach rule today. Any reached bar with `high > level` is booked as an **up**
cross, whichever side price came from, including bars wholly above the level
whose low is merely within the touch tolerance. Down crosses only come from
bars at or below the level. So it fires on almost every reached bar and
mislabels direction. No caller uses it (the `wick` users in `fan_manager.py`
and `angular_coverage_study.py` are a different code path), so it is fixed in
place:

- **Wick up:** previous bar's close below the level, and this bar's high
  above it.
- **Wick down:** previous bar's close above the level, and this bar's low
  below it.
- The first bar of the data has no previous close and cannot cross.
- The previous close is the one global previous bar (all levels share the
  price path). It must be read **before** `self._last_bar = bar`
  (`gann_ladder_analyzer.py:181`) overwrites it. `get_state`/`restore_state`
  already carry `last_bar` across chunks.
- The existing "reached" gate (`gann_ladder_analyzer.py:204-210`) still runs
  first, for every rule. A bar that gaps wholly past a level by more than the
  touch tolerance is not tested for a cross, in wick or close mode.
- Pending confirmation (closes > 1) changes in wick mode from `high > level`
  (`gann_ladder_analyzer.py:137-140`) to close-beyond, the same as close mode.
  It does not matter for `wick1` (closes = 1).

New tests: approach from above that wicks down through and closes back above
(must be a down cross, not up); a bar within tolerance that never goes through
(no cross, a touch); a clean wick through from below (up cross). Two existing
tests assume the old wick behaviour and are rewritten:
`tests/study_tool/test_gann_ladder_analyzer.py:180` (a single bar, which now
has no previous close) and `:270` (pending check now needs a close beyond).

## The lag-free reach rate

For a confirmed breach, let `c` be its cross bar and `k` its confirmation bar
(`c = k - (confirmation_closes - 1)`), and `T` its target (the next level, as
already computed by `add_reach_outcomes`, from the ladder at bar `k`).

- `target_hit_before_entry` = True if any bar in `c..k` inclusive touched `T`
  (high >= T going up, low <= T going down). This widens the existing
  `target_already_hit`, which only checks bar `k`.
- `entry_beyond_level` = True if bar `k` closed beyond the breached level
  (above it going up, below it going down). Always True for close rules. For
  `wick1` a bar can wick through and close back on the near side; a trader at
  that close would be entering past their own stop, so those rows are not
  tradeable entries.
- **lag-free reach rate** = `reach_outcome` REACHED / (REACHED + STOPPED),
  over confirmed breaches with `target_hit_before_entry == False` and
  `entry_beyond_level == True`.

The race itself is unchanged: it starts on the bar after `k`, with the stop on
the breached level (depth 0) and the corpus window. A trader acting at the
close of `k` sees exactly this: target not yet touched, stop on the level.
Only bars `c..k` decide inclusion, so the filter adds no lookahead.

The same filter applies to shadow rows. That does **not** by itself make the
two sides comparable: the real ladder's already-hit share has sat at the 100th
percentile of the shadows (`2026-09-03-gann-pullback-sweep-results.md`), so the
filter can remove a different share of real rows than shadow rows. Therefore
the **dropped share** is itself
compared real vs shadow, for every rule and on AAPL, and printed beside the
verdict. Pre-registered reading: if the real dropped share is outside the
shadow range, any pass is labelled "pass, selection differs" and the write-up
says the filtered sets are not like-for-like.

**Dropped share** = rows removed by either filter / **targeted rows**, where
targeted rows are confirmed breaches with a non-null
`target_hit_before_entry` (a target existed), whatever their race outcome,
timeouts included. The share removed by `entry_beyond_level` alone is also
printed (zero for close rules).

The old `reach_next_rate` and `target_already_hit` keep their meaning.

## Comparison terms (exact)

For one statistic on one group, with the real value `r` and the 50 shadow
values `s_1..s_50`:

- **missing shadows** = shadows with no rows in the group (`compare()` skips
  them, `shadow_compare.py:361-370`).
- **above all shadows** = `missing shadows == 0` and `r > max(s_i)`.
- **z** = `(r - mean(s_i)) / sd(s_i)` (sample sd). Undefined if fewer than 2
  shadows or sd = 0.

`Comparison.margin` (which is 0 when `r` is inside the range,
`shadow_compare.py:320-332`) is not used for selection.

## Selection rule (pre-registered, RELIANCE)

On the whole RELIANCE corpus (all of it is explore now), pooled over all
levels, lag-free reach rate:

1. **Gate:** a rule is eligible only if it is **above all shadows**.
2. **Choose** the eligible rule with the largest **z**. z rather than a raw
   margin, because the shadow spread narrows as row count grows and the rules
   have very different row counts.
3. **Ties:** the candidates are the eligible rules with
   `z >= max z - 0.1`. Of those, take the earliest in this order: `close1`,
   `wick1`, `close2`, `close3` (fewer closes first; close before wick because
   close is the house rule).
4. **Stop rule:** if no rule is eligible, the sweep reports a null and AAPL is
   **not built**. The fresh holdout is kept for a better question.

Also reported per rule (for reading, not for choosing): the 13-group results,
dropped share real vs shadow, plain `reach_next_rate`, raced row counts, and
touch density real vs shadow (the fairness check).

The choice is written to a results file and committed **before** any AAPL
step runs. The AAPL step refuses to run if that file is missing or says null.

## Fresh holdout: AAPL

- **Bars:** `data_local/aapl_rth_1m.json` in the main checkout (Alpaca,
  regular trading hours; JSON key `time` = epoch seconds), resampled to
  5-minute bars:
  - sessions grouped by New York calendar date (handles DST and half-days);
  - 5-minute buckets aligned to 09:30 New York; a bucket never spans two
    sessions;
  - bar timestamp = bucket start, UTC epoch seconds (the corpus convention);
  - open = first, high = max, low = min, close = last, volume = sum;
  - window 2024-09-02 to 2026-09-01 inclusive, the same as RELIANCE. About
    39,000 bars (500 sessions x 78).
  - Prices as stored. No split falls in the window (the last AAPL split was
    2020). The loader prints the 2024-08-30 close for the write-up to check
    against the published close.
- **Into the pipeline:** the loader writes
  `AAPL_5_2024-09-02_2026-09-01.parquet` into the bar cache with
  `sun_degree` / `moon_degree` added by the existing `bar_cache` code, so
  `build_gann_corpus.py` finds it as a cache hit and never calls Dhan.
- **Scale x6**, fixed from data **before** the window: the last AAPL close
  before 2024-09-02 is about 228.86 (2024-08-30); 228.86 x 6 = 1373, matching
  RELIANCE's median of 1375 at x1. Gann sub-level spacing as a share of price
  goes as `1 / sqrt(price x scale)`, so this gives AAPL the same relative
  spacing as RELIANCE at the start of the window.
- **One corpus, one rule:** the chosen breach rule only. 50 shadows, seed 7.
- **One look:** the whole AAPL corpus is read once through a new
  `--slice all` (no 25% split; nothing on this ladder was ever explored on
  AAPL).

### AAPL pass rule (pre-registered)

- **Pass:** pooled lag-free reach rate, real is **above all shadows**.
- **Strong pass:** pass, and at least 7 of the 13 groups below are above all
  shadows.
- The dropped-share reading above applies to both.

The 13 groups are the ones pre-declared for the 2026-09-03 confirmation:
`level_source` center / moon / sun; `level_ring_bin=10-19`; `level_kind`
sub / major; `level_is_halfway` False / True; `level_degree` 0 / 90 / 135 /
225; `level_sub_index=5`. They are kept because they were declared in
advance, but they were picked for the old, lag-laden statistic, and they do
not mean the same thing on AAPL: ring 20 starts at square 1521
(`gann_ladder.py:68-81`), so at x6 `ring_bin=10-19` covers only AAPL prices
below about $253.5, while AAPL traded up to about $343 in the window. That is
why the pooled test is the primary one. A group with no rows, or with any
missing shadow, counts as not above all shadows.

Touch density on AAPL is reported first. If real is busier than every shadow,
the write-up says so beside the verdict. One known difference: at x1 RELIANCE
major levels fall on whole-rupee prices; at x6 AAPL major levels fall on
1/6-dollar steps. If round-number clustering drives the touch skew, it will
act differently on the two instruments.

## What gets built

1. **Wick mode fix** in `gann_ladder_analyzer.py` (above), with tests.
2. **Build script settings.** `build_gann_corpus.py` takes `--breach-mode`
   and `--confirmation-closes` (defaults close / 2, so old commands are
   unchanged). Both go into `meta.json`.
3. **Corpus meta.** `CorpusMeta` reads both as optional keys, defaulting to
   close / 2 when absent (the existing corpus). The meta version stays 1.
4. **Lag-free columns.** `add_reach_outcomes` adds `target_hit_before_entry`
   (using `meta.confirmation_closes` to find the cross bar) and
   `entry_beyond_level`.
5. **Statistics.** `lag_free_reach_rate` and `dropped_share` in
   `mining/statistics.py`; z and missing-shadow count exposed from the
   comparison.
6. **`--slice all`** in `corpus_writer.load_events` and
   `mine_gann_corpus.py`.
7. **AAPL bars loader** (above).
8. **Sweep runner.** Builds the four RELIANCE corpora, runs the `close2`
   regression gate, scores each rule, applies the selection rule, and writes
   the choice file. A separate AAPL command builds and scores AAPL, refusing
   to run without a non-null choice file.

Each piece gets a unit test in `gann-visualizer/backend/tests/study_tool/`.
In particular:
- the cross-bar arithmetic for closes = 1, 2, 3 (target touched on the cross
  bar, a middle bar, the confirmation bar, never);
- the filter uses no bar after `k`;
- the wick-mode cases above;
- the 5-minute resample: session boundaries, DST, a half-day, volume sum;
- old meta without the new keys loads as close / 2;
- z, missing shadows and "above all shadows" on hand-made inputs;
- the AAPL command refuses without a choice file, and with a null one.

## Coverage table

| Item from the audit | Where it is handled |
|---|---|
| Breach definition: wick vs close | `wick1` (fixed) vs `close1` |
| Breach definition: how many closes | `close1` / `close2` / `close3` |
| Confirmation-lag artefact (~65%) | lag-free reach rate + dropped-share check |
| Fresh holdout needed | AAPL, one look |
| Second instrument | AAPL |
| Touch-density skew | Reported, not fixed, in this phase |
| Alternative divisions, regime labels, ring spread | Not in this phase: each multiplies the corpus count; do them after the break rule is settled. |

## Risks

- **Touch density skew** is unresolved and could lift any reach statistic.
- **Close-mode first bar must open on the near side of the level**
  (`_crossed`, `gann_ladder_analyzer.py:153-158`): gaps through a level are not
  crosses. Kept so all close rules share one cross test. The fixed wick rule
  uses the previous close instead, so it counts a gap through a level only
  when the gap bar is still within touch tolerance of the level.
- **Bar cache path:** `build_gann_corpus.py` defaults to the relative
  `logs/corpus/bars`, which is empty in the worktree, and a cache miss falls
  through to a Dhan fetch (`bar_cache.py:315-319`). The runner passes the main
  checkout's absolute cache path and a fetcher that raises on a miss. The AAPL
  loader writes into the same directory. No step may fetch.
- **Wick at closes = 1** confirms on the cross bar itself, so `c = k`; the
  filter drops rows whose own bar also touched the target. That is correct.
- **Disk:** about 115 MB of events per RELIANCE corpus, more for `wick1` and
  `close1` (more crosses). All under the gitignored `logs/corpus/`.
