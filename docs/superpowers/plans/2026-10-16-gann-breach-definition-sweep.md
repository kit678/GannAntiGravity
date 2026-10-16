# Gann Breach Definition Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the RELIANCE Gann corpus under four breach rules, pick one by a pre-registered rule on a lag-free reach rate, then read a fresh AAPL corpus under that rule exactly once.

**Architecture:** The analyzer's wick mode is fixed in place; the corpus build script takes the breach rule as arguments and records it in `meta.json`; mining gains two lag-free columns, three statistics, a `z` / `above_all_shadows` on `Comparison`, and a `--slice all`. All pre-registered decisions (rule selection, AAPL verdict, regression gate) live in pure, unit-tested modules under `study_tool/mining/`; two thin scripts (`run_breach_sweep.py`, `run_aapl_holdout.py`) wire them to disk. Long runs are separate RUN tasks at the end.

**Tech Stack:** Python 3.13 (miniconda), pandas 2.3, pyarrow 25, numpy 2.2, pytest; Swiss Ephemeris via `study_tool.ephemeris`.

Spec (source of truth): `docs/superpowers/specs/2026-10-16-gann-breach-definition-sweep-design.md`.

---

## Conventions for every task

- Work in the worktree `C:/Dev/GannTesting/.worktrees/breach-sweep` (branch `feat/breach-definition-sweep`).
- Every command below runs from `C:/Dev/GannTesting/.worktrees/breach-sweep/gann-visualizer/backend`. Git paths are relative to that directory.
- Python is `C:/Users/kitsh/AppData/Local/miniconda3/python.exe`. Checked 2026-10-16: from the worktree backend dir, `python -m pytest` imports the worktree's `study_tool` (cwd is first on `sys.path`) and the suite is green at **470 passed**. No other environment is needed.
- Tests never touch the network, the 113 MB reference corpus, or the 105 MB AAPL JSON. They use small synthetic frames and `tmp_path`.
- Never commit anything under `gann-visualizer/backend/logs/corpus/` (gitignored).
- **After every pytest run, before committing:** importing `main.py` (`main.py:40-48`) deletes the tracked `logs/backend/backend_session_20260507_163028.log` and writes a new untracked session log. Restore and clean up with:

  ```bash
  git -C C:/Dev/GannTesting/.worktrees/breach-sweep checkout -- logs/backend/backend_session_20260507_163028.log
  git -C C:/Dev/GannTesting/.worktrees/breach-sweep ls-files --others --exclude-standard -- 'logs/backend/backend_session_*.log' | sed 's|^|C:/Dev/GannTesting/.worktrees/breach-sweep/|' | xargs -r rm --
  ```

  Every commit step uses explicit `git add <files>`, never `git add -A`, so a stray log cannot ride along.
- Commit messages follow AGENTS.md (Conventional Commits, lower case, imperative, no trailing period) and end with a blank line and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (the second `-m` supplies the blank line).

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `study_tool/gann_ladder_analyzer.py` | modify | `BREACH_MODES`; wick mode crosses against the previous bar's close; pending confirmation is close-beyond in both modes |
| `tests/study_tool/test_gann_ladder_analyzer.py` | modify | wick cases; the two old wick tests rewritten |
| `study_tool/bar_cache.py` | modify | public `cache_path`; `no_fetch` fetcher that raises on a cache miss |
| `tests/study_tool/test_bar_cache.py` | modify | `no_fetch`, `cache_path` |
| `scripts/build_gann_corpus.py` | modify | breach rule into analyzer settings and `meta.json`; `build_to_disk`; `ensure_corpus`; CLI `--breach-mode`, `--confirmation-closes`, `--no-fetch`; `main(argv)` |
| `tests/study_tool/test_build_gann_corpus.py` | modify | breach rule plumbing, cross-bar arithmetic against the real analyzer, CLI, `ensure_corpus` |
| `study_tool/mining/corpus_meta.py` | modify | optional `breach_mode` / `confirmation_closes`, default close / 2, version stays 1 |
| `tests/study_tool/mining/test_corpus_meta.py` | modify | old meta loads as close / 2 |
| `study_tool/mining/ladder_rebuild.py` | modify | `target_hit_before_entry`, `entry_beyond_level` in `add_reach_outcomes` |
| `tests/study_tool/mining/test_lag_free_columns.py` | create | cross-bar arithmetic for closes 1/2/3, no bar after `k`, shadows |
| `study_tool/mining/statistics.py` | modify | `lag_free_reach_rate_for`, `lag_free_reach_rate`, `dropped_share`, `entry_dropped_share` |
| `tests/study_tool/mining/test_statistics.py` | modify | the three statistics on hand-made rows |
| `study_tool/mining/shadow_compare.py` | modify | `Comparison.z`, `Comparison.above_all_shadows` |
| `tests/study_tool/mining/test_shadow_compare.py` | modify | z, missing shadows, above all shadows |
| `study_tool/corpus_writer.py` | modify | `ALL_SLICES = "all"` in `load_events` |
| `tests/study_tool/test_corpus_writer.py` | modify | `slice_name="all"` |
| `scripts/mine_gann_corpus.py` | modify | `ScoredCorpus`, `load_scored_events`, `mining_statistics`, `render_mining_report`; `--slice all`; lag-free statistics in the report; `main(argv)` |
| `tests/study_tool/test_mine_gann_corpus.py` | create | `--slice all` end to end |
| `study_tool/aapl_bars.py` | create | AAPL 1m RTH JSON -> 5m bars -> bar cache parquet |
| `tests/study_tool/test_aapl_bars.py` | create | sessions, DST, half-day, volume sum, window, cache hit |
| `study_tool/mining/regression_gate.py` | create | `GateResult`, `compare_event_tables`, `check_regression` |
| `tests/study_tool/mining/test_regression_gate.py` | create | exact-match definition on small tables |
| `study_tool/mining/report.py` | modify | module-level `display_label` (used by the group matcher) |
| `study_tool/mining/breach_sweep.py` | create | rules, 13 groups, `score_rule`, `select_rule`, `aapl_verdict`, choice file |
| `tests/study_tool/mining/test_breach_sweep.py` | create | selection rule, verdict, choice file, groups, scoring |
| `study_tool/mining/sweep_report.py` | create | RELIANCE results markdown and AAPL verdict markdown |
| `tests/study_tool/mining/test_sweep_report.py` | create | section order, null text, caveats |
| `scripts/run_breach_sweep.py` | create | builds four RELIANCE corpora (no fetch), close2 gate, prints peak memory per build, scores, selects, writes choice + results |
| `tests/study_tool/test_run_breach_sweep.py` | create | pinned null (zero shadows); forced chosen rule end to end; gate failure; build-only; reuse; peak memory probe |
| `scripts/load_aapl_bars.py` | create | CLI for the loader (Task 16); refuses without a non-null `--choice`; prints bar count, early-close drops, 2024-08-30 close, last pre-window close |
| `tests/study_tool/test_load_aapl_bars.py` | create | loader CLI refuses a missing / null choice; writes the cache and prints the checks |
| `scripts/run_aapl_holdout.py` | create | refuses without a non-null choice, if the AAPL corpus already exists, if a `.started` marker or the results exist; builds AAPL x6 under the chosen rule; scores `--slice all`; writes only the spec's statistics and the verdict - never the full mining report |
| `tests/study_tool/test_run_aapl_holdout.py` | create | every refusal, the marker written before scoring, end to end |

Outputs written by the RUN tasks (paths fixed here so later tasks can name them):

- Choice file (committed): `C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json`
- RELIANCE results (committed): `C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-results.md`
- AAPL results (committed): `C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-aapl-holdout-results.md`
- Corpora (not committed): `C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/breach_sweep/reliance_5m_x1_<rule>/` and `C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/aapl_5m_x6/`

---

### Task 1: Fix wick mode in the ladder analyzer

**Files:**
- Modify: `study_tool/gann_ladder_analyzer.py` (lines 12-29, 116-159, 180-181, 211)
- Test: `tests/study_tool/test_gann_ladder_analyzer.py` (imports; tests at lines 180 and 270 rewritten; new tests appended)

Level 105.0, segment 100-110: sub-level gap 1.25, touch tolerance 0.125. A bar is "reached" when `low - 0.125 <= 105 <= high + 0.125`.

- [ ] **Step 1: Write the failing tests**

In `tests/study_tool/test_gann_ladder_analyzer.py`, change the import block (lines 4-10) from

```python
import sys
import os

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.gann_ladder_analyzer import GannLadderAnalyzer
from study_tool.event_logger import EventType
```

to

```python
import sys
import os

import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.gann_ladder_analyzer import GannLadderAnalyzer
from study_tool.event_logger import EventType
```

Replace the test at line 180

```python
def test_wick_mode_confirms_on_range_rather_than_close():
    an = analyzer(breach_mode="wick", confirmation_closes=1)
    events = run(an, [bar(104.0, 106.0, 103.5, 104.2)])
    assert EventType.LADDER_BREACH_CONFIRMED in types_of(events)
```

with

```python
def test_wick_mode_confirms_on_range_rather_than_close():
    # Rewritten 2026-10-16: the old version fed a single bar, which now has
    # no previous close and so cannot cross. A lead-in bar closing below the
    # level gives the wick bar a side to come from.
    an = analyzer(breach_mode="wick", confirmation_closes=1)
    events = run(an, [
        bar(104.0, 104.5, 103.5, 104.2),   # closes below 105, not reached
        bar(104.2, 106.0, 103.5, 104.2),   # wicks up through 105, closes back
    ])
    confirmed = [e for e in events if e.event_type == EventType.LADDER_BREACH_CONFIRMED]
    assert len(confirmed) == 1
    assert confirmed[0].direction == "up"


def test_wick_mode_first_bar_has_no_previous_close_and_cannot_cross():
    an = analyzer(breach_mode="wick", confirmation_closes=1)
    events = run(an, [bar(104.0, 106.0, 103.5, 104.2)])
    assert types_of(events) == [EventType.LADDER_TOUCH]
```

Replace the test at line 270

```python
def test_wick_mode_accumulates_closes_across_bars():
    an = analyzer(breach_mode="wick", confirmation_closes=2)
    events = run(an, [
        bar(104.0, 106.0, 103.5, 104.2),   # wicks through 105 once
        bar(104.2, 106.0, 103.5, 104.3),   # wicks through again, same direction
    ])
    confirmed = [e for e in events if e.event_type == EventType.LADDER_BREACH_CONFIRMED]
    assert len(confirmed) == 1
```

with

```python
def test_wick_mode_pending_cross_needs_a_close_beyond_to_confirm():
    # Rewritten 2026-10-16: a pending wick cross is confirmed by a close
    # beyond the level, the same as close mode. A second wick alone no
    # longer counts.
    an = analyzer(breach_mode="wick", confirmation_closes=2)
    events = run(an, [
        bar(104.0, 104.5, 103.5, 104.2),   # lead-in, closes below
        bar(104.2, 106.0, 103.5, 104.2),   # wicks up through 105: cross, pending
        bar(104.2, 106.0, 104.1, 105.5),   # closes above 105: confirmed
    ])
    confirmed = [e for e in events if e.event_type == EventType.LADDER_BREACH_CONFIRMED]
    assert len(confirmed) == 1
    assert confirmed[0].direction == "up"
    assert confirmed[0].bar_index == 2


def test_wick_mode_a_second_wick_that_closes_back_rejects_the_pending_cross():
    an = analyzer(breach_mode="wick", confirmation_closes=2)
    events = run(an, [
        bar(104.0, 104.5, 103.5, 104.2),
        bar(104.2, 106.0, 103.5, 104.2),   # cross, pending
        bar(104.2, 106.0, 103.5, 104.3),   # wicks again but closes below
    ])
    kinds = types_of(events)
    assert EventType.LADDER_BREACH_CONFIRMED not in kinds
    assert EventType.LADDER_BREACH_REJECTED in kinds
```

Append at the end of the file:

```python
# -- Wick mode as a breach rule (2026-10-16 breach sweep) ---------------------
#
# Wick up: previous close below the level, this bar's high above it.
# Wick down: previous close above the level, this bar's low below it.
# The "reached" gate still runs first.


def test_wick_mode_a_wick_down_from_above_that_closes_back_above_is_a_down_cross():
    an = analyzer(breach_mode="wick", confirmation_closes=1)
    events = run(an, [
        bar(106.5, 107.0, 106.0, 106.5),   # above 105, not reached
        bar(106.5, 106.6, 104.5, 105.8),   # wicks down through 105, closes above
    ])
    crosses = [e for e in events if e.event_type == EventType.LADDER_CROSS]
    assert [e.direction for e in crosses] == ["down"]


def test_wick_mode_a_bar_within_tolerance_that_never_goes_through_is_a_touch():
    an = analyzer(breach_mode="wick", confirmation_closes=1)
    events = run(an, [
        bar(104.0, 104.5, 103.5, 104.2),   # below, not reached
        bar(104.2, 104.9, 104.0, 104.5),   # high within 0.125 of 105, not through
    ])
    assert types_of(events) == [EventType.LADDER_TOUCH]


def test_wick_mode_a_bar_wholly_above_with_its_low_inside_tolerance_is_a_touch():
    an = analyzer(breach_mode="wick", confirmation_closes=1)
    events = run(an, [
        bar(105.6, 106.0, 105.4, 105.5),   # above, not reached
        bar(105.5, 106.0, 105.1, 105.5),   # low 105.1 within tolerance, never below
    ])
    assert types_of(events) == [EventType.LADDER_TOUCH]


def test_wick_mode_a_clean_wick_up_from_below_is_an_up_cross():
    an = analyzer(breach_mode="wick", confirmation_closes=1)
    events = run(an, [
        bar(104.0, 104.5, 103.5, 104.2),
        bar(104.2, 105.6, 104.0, 105.4),
    ])
    crosses = [e for e in events if e.event_type == EventType.LADDER_CROSS]
    confirmed = [e for e in events if e.event_type == EventType.LADDER_BREACH_CONFIRMED]
    assert [e.direction for e in crosses] == ["up"]
    assert len(confirmed) == 1


def test_wick_mode_a_gap_wholly_past_the_tolerance_is_not_tested():
    an = analyzer(breach_mode="wick", confirmation_closes=1)
    events = run(an, [
        bar(104.0, 104.5, 103.5, 104.2),
        bar(106.0, 107.0, 105.9, 106.5),   # gaps over 105 by more than 0.125
    ])
    assert events == []


def test_wick_mode_previous_close_survives_a_state_round_trip():
    bars = [bar(104.0, 104.5, 103.5, 104.2), bar(104.2, 105.6, 104.0, 105.4)]
    straight = run(analyzer(breach_mode="wick", confirmation_closes=1), bars)

    split = analyzer(breach_mode="wick", confirmation_closes=1)
    out = list(split.process_bar(bars[0], 0, LEVELS))
    resumed = analyzer(breach_mode="wick", confirmation_closes=1)
    resumed.restore_state(split.get_state())
    out.extend(resumed.process_bar(bars[1], 1, LEVELS))

    assert types_of(out) == types_of(straight)
    assert EventType.LADDER_CROSS in types_of(out)


def test_an_unknown_breach_mode_is_refused():
    with pytest.raises(ValueError, match="breach_mode"):
        analyzer(breach_mode="body")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/test_gann_ladder_analyzer.py -v`

Expected: FAIL on `test_wick_mode_first_bar_has_no_previous_close_and_cannot_cross`, `test_wick_mode_a_second_wick_that_closes_back_rejects_the_pending_cross`, `test_wick_mode_a_wick_down_from_above_that_closes_back_above_is_a_down_cross` (`assert ['up'] == ['down']`), `test_wick_mode_a_bar_within_tolerance_that_never_goes_through_is_a_touch`, `test_wick_mode_a_bar_wholly_above_with_its_low_inside_tolerance_is_a_touch`, and `test_an_unknown_breach_mode_is_refused` (`DID NOT RAISE`). The others pass.

- [ ] **Step 3: Implement**

In `study_tool/gann_ladder_analyzer.py`, after the import block (line 14, `from study_tool.event_logger import Event, EventType`), add:

```python

# The breach rules the analyzer knows. The build script and corpus meta
# validate against this one tuple.
BREACH_MODES = ("close", "wick")
```

In `__init__`, replace

```python
        self.breach_mode = config.get("breach_mode", "close")
```

with

```python
        self.breach_mode = config.get("breach_mode", "close")
        if self.breach_mode not in BREACH_MODES:
            raise ValueError(
                f"breach_mode {self.breach_mode!r} is not one of {BREACH_MODES}")
```

Replace the whole `_crossed` method (lines 116-159, from `def _crossed(self, price: float, open_price: Optional[float],` through the final `return False, None`) with:

```python
    def _crossed(self, price: float, open_price: Optional[float],
                 high: float, low: float, close: float,
                 direction_hint: Optional[str] = None,
                 prev_close: Optional[float] = None) -> Tuple[bool, Optional[str]]:
        """
        Whether this bar counts as crossing the level, and in which direction.

        A pending cross (direction_hint given) stays alive only on a close
        beyond the level in that direction, in both modes. A bar that wicks
        the right way but closes back rejects the breach.

        First cross, 'close' mode: the bar travelled through the level -
        opened on it or on one side, closed on the other.

        First cross, 'wick' mode: the previous bar closed strictly on one
        side and this bar's range reaches strictly past the level on the
        other. It may close back. The first bar of the data has no previous
        close and cannot cross. Before 2026-10-16 wick mode booked any bar
        with high > level as an up cross from either side; no caller relied
        on that.
        """
        if direction_hint == "up":
            return close > price, "up"
        if direction_hint == "down":
            return close < price, "down"

        if self.breach_mode == "wick":
            if prev_close is None:
                return False, None
            if prev_close < price and high > price:
                return True, "up"
            if prev_close > price and low < price:
                return True, "down"
            return False, None

        beyond_up = close > price
        beyond_down = close < price
        straddled_up = open_price is not None and open_price <= price and beyond_up
        straddled_down = open_price is not None and open_price >= price and beyond_down
        if straddled_up:
            return True, "up"
        if straddled_down:
            return True, "down"
        return False, None
```

Close mode is unchanged: the hint branch returned `beyond_up` / `beyond_down` before and returns the same comparison now.

In `process_bar`, replace

```python
        self._last_bar_index = bar_index
        self._last_bar = bar
```

with

```python
        self._last_bar_index = bar_index
        # Read before overwriting: wick mode crosses against the previous
        # bar's close. One global previous bar - every level shares the path.
        # get_state / restore_state already carry _last_bar across chunks.
        prev_close = self._last_bar.get("close") if self._last_bar else None
        self._last_bar = bar
```

and replace

```python
                crossed_now, direction = self._crossed(price, open_price, high, low, close)
```

with

```python
                crossed_now, direction = self._crossed(
                    price, open_price, high, low, close, prev_close=prev_close)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/test_gann_ladder_analyzer.py tests/study_tool/test_gann_ladder_analyzer_scale.py tests/study_tool/test_run_ladder_study.py tests/study_tool/test_run_ladder_study_resume.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add study_tool/gann_ladder_analyzer.py tests/study_tool/test_gann_ladder_analyzer.py
git commit -m "fix: wick mode crosses against the previous close" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Bar cache can refuse to fetch

**Files:**
- Modify: `study_tool/bar_cache.py` (lines 27-30, 54)
- Test: `tests/study_tool/test_bar_cache.py`

- [ ] **Step 1: Write the failing tests**

In `tests/study_tool/test_bar_cache.py` change

```python
from study_tool.bar_cache import load_bars
```

to

```python
from study_tool.bar_cache import cache_path, load_bars, no_fetch
```

and append:

```python
def test_no_fetch_turns_a_cache_miss_into_an_error(tmp_path):
    """A sweep rebuild must read the cached bars, never refetch from Dhan."""
    with pytest.raises(FileNotFoundError, match="fetching is disabled"):
        load_bars("RELIANCE", "2026-08-25", "2026-08-26", "5",
                  cache_dir=tmp_path, fetcher=no_fetch)
    assert list(tmp_path.glob("*.parquet")) == []


def test_no_fetch_still_reads_a_cache_hit(tmp_path):
    load_bars("RELIANCE", "2026-08-25", "2026-08-26", "5",
              cache_dir=tmp_path, fetcher=CountingFetcher())

    bars = load_bars("RELIANCE", "2026-08-25", "2026-08-26", "5",
                     cache_dir=tmp_path, fetcher=no_fetch)

    assert len(bars) == 5


def test_cache_path_names_the_file_load_bars_writes(tmp_path):
    load_bars("RELIANCE", "2026-08-25", "2026-08-26", "5",
              cache_dir=tmp_path, fetcher=CountingFetcher())

    assert cache_path(tmp_path, "RELIANCE", "2026-08-25", "2026-08-26", "5").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/test_bar_cache.py -v`

Expected: collection ERROR, `ImportError: cannot import name 'cache_path' from 'study_tool.bar_cache'`.

- [ ] **Step 3: Implement**

In `study_tool/bar_cache.py` replace

```python
def _cache_path(cache_dir: Path, symbol: str, from_date: str,
                to_date: str, interval: str) -> Path:
    name = f"{symbol}_{interval}_{from_date}_{to_date}.parquet"
    return Path(cache_dir) / name
```

with

```python
def cache_path(cache_dir: Union[str, Path], symbol: str, from_date: str,
               to_date: str, interval: str) -> Path:
    """Where load_bars keeps one symbol and window."""
    name = f"{symbol}_{interval}_{from_date}_{to_date}.parquet"
    return Path(cache_dir) / name


def no_fetch(symbol: str, from_date: str, to_date: str,
             interval: str) -> pd.DataFrame:
    """
    A fetcher that refuses. Pass it to load_bars when a cache miss must stop
    the run instead of calling Dhan: a rebuild that silently refetched would
    no longer be a rebuild of the same bars.
    """
    raise FileNotFoundError(
        f"no cached bars for {symbol} {interval} {from_date}..{to_date} "
        "and fetching is disabled"
    )
```

and in `load_bars` replace

```python
    path = _cache_path(cache_dir, symbol, from_date, to_date, interval)
```

with

```python
    path = cache_path(cache_dir, symbol, from_date, to_date, interval)
```

(`_cache_path` has no other callers; checked with a repo-wide grep.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/test_bar_cache.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add study_tool/bar_cache.py tests/study_tool/test_bar_cache.py
git commit -m "feat: bar cache can refuse to fetch on a miss" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 3: Build script takes the breach rule; no-fetch; reusable builds

**Files:**
- Modify: `scripts/build_gann_corpus.py` (docstring lines 4-7; imports lines 16-31; `_analyzer_settings` lines 36-47; `build_corpus` lines 112-120 and 168-180; `main` lines 183-224)
- Test: `tests/study_tool/test_build_gann_corpus.py`

- [ ] **Step 1: Write the failing tests**

In `tests/study_tool/test_build_gann_corpus.py` change the import block (lines 7-15) from

```python
import sys
import os

import pandas as pd

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend/scripts'))

from build_gann_corpus import build_corpus
```

to

```python
import sys
import os
import json

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend/scripts'))

from build_gann_corpus import build_corpus
from study_tool.bar_cache import cache_path
```

Append:

```python
# -- Breach rule plumbing (2026-10-16 breach sweep) ----------------------------

FROM, TO = "2026-08-01", "2026-08-31"


def test_default_breach_rule_is_close_two():
    meta = build_corpus(bars=synthetic_bars(), instrument="RELIANCE",
                        timeframe="5", price_scale=1, shadow_count=1,
                        seed=7)["meta"]
    assert (meta["breach_mode"], meta["confirmation_closes"]) == ("close", 2)


def test_breach_rule_reaches_the_meta():
    meta = build_corpus(bars=synthetic_bars(), instrument="RELIANCE",
                        timeframe="5", price_scale=1, shadow_count=1, seed=7,
                        breach_mode="wick", confirmation_closes=1)["meta"]
    assert (meta["breach_mode"], meta["confirmation_closes"]) == ("wick", 1)


@pytest.mark.parametrize("breach_mode, closes", [
    ("close", 1), ("close", 2), ("close", 3), ("wick", 1),
])
def test_a_confirmed_breach_crossed_exactly_closes_minus_one_bars_earlier(
        breach_mode, closes):
    """
    The lag-free filter finds the cross bar as k - (closes - 1). Pin that
    against the real analyzer: every confirmed real breach has a cross on the
    same level exactly that many bars before it.
    """
    events = build_corpus(bars=synthetic_bars(), instrument="RELIANCE",
                          timeframe="5", price_scale=1, shadow_count=1, seed=7,
                          breach_mode=breach_mode,
                          confirmation_closes=closes)["events"]
    real = events[events["shadow_id"].isna()]
    crosses = {
        (row.level_source, row.level_square, int(row.bar_index))
        for row in real[real["event_type"] == "LADDER_CROSS"].itertuples()
    }
    confirmed = real[real["event_type"] == "LADDER_BREACH_CONFIRMED"]

    assert len(confirmed) > 0, "no confirmed breaches to check"
    for row in confirmed.itertuples():
        cross_bar = int(row.bar_index) - (closes - 1)
        assert (row.level_source, row.level_square, cross_bar) in crosses


def test_an_unknown_breach_mode_is_refused():
    with pytest.raises(ValueError, match="breach_mode"):
        build_corpus(bars=synthetic_bars(), instrument="RELIANCE",
                     timeframe="5", price_scale=1, shadow_count=1, seed=7,
                     breach_mode="body")


def test_zero_confirmation_closes_is_refused():
    with pytest.raises(ValueError, match="confirmation_closes"):
        build_corpus(bars=synthetic_bars(), instrument="RELIANCE",
                     timeframe="5", price_scale=1, shadow_count=1, seed=7,
                     confirmation_closes=0)


def write_cached_bars(cache_dir):
    cache_dir.mkdir(parents=True, exist_ok=True)
    synthetic_bars().to_parquet(
        cache_path(cache_dir, "RELIANCE", FROM, TO, "5"), index=False)


def test_the_command_line_writes_the_breach_rule_into_meta_json(tmp_path):
    import build_gann_corpus as runner
    cache, out = tmp_path / "bars", tmp_path / "corpus"
    write_cached_bars(cache)

    runner.main(["--from", FROM, "--to", TO, "--cache", str(cache),
                 "--out", str(out), "--shadows", "2",
                 "--breach-mode", "wick", "--confirmation-closes", "1",
                 "--no-fetch"])

    meta = json.loads((out / "meta.json").read_text())
    assert (meta["breach_mode"], meta["confirmation_closes"]) == ("wick", 1)


def test_the_command_line_defaults_keep_the_old_rule(tmp_path):
    import build_gann_corpus as runner
    cache, out = tmp_path / "bars", tmp_path / "corpus"
    write_cached_bars(cache)

    runner.main(["--from", FROM, "--to", TO, "--cache", str(cache),
                 "--out", str(out), "--shadows", "2", "--no-fetch"])

    meta = json.loads((out / "meta.json").read_text())
    assert (meta["breach_mode"], meta["confirmation_closes"]) == ("close", 2)


def test_no_fetch_refuses_a_cache_miss(tmp_path):
    import build_gann_corpus as runner
    out = tmp_path / "corpus"

    with pytest.raises(FileNotFoundError, match="fetching is disabled"):
        runner.main(["--from", FROM, "--to", TO,
                     "--cache", str(tmp_path / "empty"),
                     "--out", str(out), "--no-fetch"])

    assert not (out / "meta.json").exists()


def ensure_kwargs(tmp_path, **overrides):
    kwargs = dict(symbol="RELIANCE", from_date=FROM, to_date=TO, interval="5",
                  price_scale=1, shadow_count=2, seed=7,
                  cache_dir=tmp_path / "bars", out_dir=tmp_path / "corpus",
                  breach_mode="close", confirmation_closes=2)
    kwargs.update(overrides)
    return kwargs


def test_ensure_corpus_builds_then_reuses(tmp_path, monkeypatch):
    import build_gann_corpus as runner
    write_cached_bars(tmp_path / "bars")

    assert runner.ensure_corpus(**ensure_kwargs(tmp_path)) == "built"

    def boom(*args, **kwargs):
        raise AssertionError("a matching corpus was rebuilt")

    monkeypatch.setattr(runner, "build_corpus", boom)
    assert runner.ensure_corpus(**ensure_kwargs(tmp_path)) == "reused"


def test_ensure_corpus_refuses_a_corpus_built_with_another_rule(tmp_path):
    import build_gann_corpus as runner
    write_cached_bars(tmp_path / "bars")
    runner.ensure_corpus(**ensure_kwargs(tmp_path))

    with pytest.raises(ValueError, match="confirmation_closes"):
        runner.ensure_corpus(**ensure_kwargs(tmp_path, confirmation_closes=3))


def test_ensure_corpus_never_fetches(tmp_path):
    import build_gann_corpus as runner

    with pytest.raises(FileNotFoundError, match="fetching is disabled"):
        runner.ensure_corpus(**ensure_kwargs(tmp_path))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/test_build_gann_corpus.py -v`

Expected: the new tests FAIL with `KeyError: 'breach_mode'`, `TypeError: build_corpus() got an unexpected keyword argument 'breach_mode'`, `TypeError: main() takes 0 positional arguments but 1 was given`, and `AttributeError: module 'build_gann_corpus' has no attribute 'ensure_corpus'`. The pre-existing tests PASS.

- [ ] **Step 3: Implement**

In `scripts/build_gann_corpus.py`:

Replace the usage lines in the module docstring

```python
Usage:
    python scripts/build_gann_corpus.py --symbol RELIANCE \
        --from 2024-09-02 --to 2026-09-01 --interval 5 --scale 1 \
        --shadows 50 --out logs/corpus/reliance_5m_x1
```

with

```python
Usage:
    python scripts/build_gann_corpus.py --symbol RELIANCE \
        --from 2024-09-02 --to 2026-09-01 --interval 5 --scale 1 \
        --shadows 50 --out logs/corpus/reliance_5m_x1

    --breach-mode close|wick and --confirmation-closes N set the breach rule
    (defaults close / 2, the rule every corpus before 2026-10-16 used).
    --no-fetch makes a bar-cache miss raise instead of calling Dhan.
```

Replace the import block

```python
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from study_tool.bar_cache import load_bars
from study_tool.corpus_writer import assign_slices, write_corpus
from study_tool.event_logger import EventLogger
from study_tool.gann_ladder_analyzer import GannLadderAnalyzer
```

with

```python
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Union

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from study_tool.bar_cache import load_bars, no_fetch
from study_tool.corpus_writer import (
    META_FILENAME, assign_slices, load_meta, write_corpus,
)
from study_tool.event_logger import EventLogger
from study_tool.gann_ladder_analyzer import BREACH_MODES, GannLadderAnalyzer
```

Replace the head of `_analyzer_settings`

```python
def _analyzer_settings(instrument: str, timeframe: str,
                       price_scale: int) -> Dict:
    return {
        "breach_mode": "close",
        "confirmation_closes": 2,
```

with

```python
def _analyzer_settings(instrument: str, timeframe: str, price_scale: int,
                       breach_mode: str = "close",
                       confirmation_closes: int = 2) -> Dict:
    if breach_mode not in BREACH_MODES:
        raise ValueError(
            f"breach_mode {breach_mode!r} is not one of {BREACH_MODES}")
    if int(confirmation_closes) < 1:
        raise ValueError(
            f"confirmation_closes must be at least 1, got {confirmation_closes}")
    return {
        "breach_mode": breach_mode,
        "confirmation_closes": int(confirmation_closes),
```

(the remaining keys of the returned dict are unchanged).

Replace the head of `build_corpus`

```python
def build_corpus(bars: pd.DataFrame, instrument: str, timeframe: str,
                 price_scale: int, shadow_count: int, seed: int) -> Dict:
    """
    Walk `bars` against the real ladder and `shadow_count` shifted ones.

    Returns a dict with `events`, `bars`, `ladder_keys` and `meta`. The meta
    carries the shadow offsets, which nothing downstream can recompute.
    """
    settings = _analyzer_settings(instrument, timeframe, price_scale)
```

with

```python
def build_corpus(bars: pd.DataFrame, instrument: str, timeframe: str,
                 price_scale: int, shadow_count: int, seed: int,
                 breach_mode: str = "close",
                 confirmation_closes: int = 2) -> Dict:
    """
    Walk `bars` against the real ladder and `shadow_count` shifted ones.

    Returns a dict with `events`, `bars`, `ladder_keys` and `meta`. The meta
    carries the shadow offsets, which nothing downstream can recompute, and
    the breach rule, which mining needs to find each breach's cross bar.
    Shadows walk with the same settings, so they get the same breach rule.
    """
    settings = _analyzer_settings(instrument, timeframe, price_scale,
                                  breach_mode, confirmation_closes)
```

In the returned meta, replace

```python
            "resolution_window_bars": settings["resolution_window_bars"],
            "bar_count": int(len(bars)),
        },
    }
```

with

```python
            "resolution_window_bars": settings["resolution_window_bars"],
            "bar_count": int(len(bars)),
            "breach_mode": settings["breach_mode"],
            "confirmation_closes": settings["confirmation_closes"],
        },
    }
```

Replace the whole `main` function (from `def main() -> None:` through the final `print("  none")`) with:

```python
def build_to_disk(symbol: str, from_date: str, to_date: str, interval: str,
                  price_scale: int, shadow_count: int, seed: int,
                  cache_dir: Union[str, Path], out_dir: Union[str, Path],
                  breach_mode: str = "close", confirmation_closes: int = 2,
                  overwrite: bool = False,
                  allow_fetch: bool = True) -> pd.DataFrame:
    """
    Load bars, build the corpus, write it. Returns the slice-stamped events.

    allow_fetch=False passes bar_cache.no_fetch, so a cache miss raises
    instead of calling Dhan. Every sweep and holdout build uses that.
    """
    bars = load_bars(symbol, from_date, to_date, interval,
                     cache_dir=cache_dir,
                     fetcher=None if allow_fetch else no_fetch)
    print(f"{len(bars)} bars {from_date}..{to_date}")

    result = build_corpus(
        bars=bars, instrument=symbol, timeframe=interval,
        price_scale=price_scale, shadow_count=shadow_count, seed=seed,
        breach_mode=breach_mode, confirmation_closes=confirmation_closes)

    events = assign_slices(result["events"], order_column="bar_index")
    meta = dict(result["meta"])
    meta["from_date"] = from_date
    meta["to_date"] = to_date
    write_corpus(Path(out_dir), events=events, bars=result["bars"],
                 ladder_keys=result["ladder_keys"], meta=meta,
                 overwrite=overwrite)
    return events


def ensure_corpus(symbol: str, from_date: str, to_date: str, interval: str,
                  price_scale: int, shadow_count: int, seed: int,
                  cache_dir: Union[str, Path], out_dir: Union[str, Path],
                  breach_mode: str, confirmation_closes: int) -> str:
    """
    Build the corpus at `out_dir` unless the same build is already there.

    Returns "built" or "reused". Never fetches.

    write_corpus writes meta.json last, so a meta.json on disk means a
    finished corpus. A build killed mid-write leaves tables without meta;
    write_corpus then refuses to overwrite them, and the directory has to be
    removed by hand.

    A corpus already there with any different setting is an error, never
    reused and never overwritten: a sweep that silently scored the wrong
    breach rule would still print a choice.
    """
    wanted = {
        "symbol": symbol, "from_date": from_date, "to_date": to_date,
        "interval": str(interval), "price_scale": int(price_scale),
        "shadow_count": int(shadow_count), "seed": int(seed),
        "breach_mode": breach_mode,
        "confirmation_closes": int(confirmation_closes),
    }
    if (Path(out_dir) / META_FILENAME).exists():
        found = dict(load_meta(out_dir))
        found.setdefault("breach_mode", "close")
        found.setdefault("confirmation_closes", 2)
        mismatched = {key: (found.get(key), value)
                      for key, value in wanted.items()
                      if found.get(key) != value}
        if mismatched:
            raise ValueError(
                f"{out_dir} already holds a corpus built with different "
                f"settings (found, wanted): {mismatched}"
            )
        return "reused"

    build_to_disk(symbol=symbol, from_date=from_date, to_date=to_date,
                  interval=str(interval), price_scale=price_scale,
                  shadow_count=shadow_count, seed=seed, cache_dir=cache_dir,
                  out_dir=out_dir, breach_mode=breach_mode,
                  confirmation_closes=confirmation_closes,
                  allow_fetch=False)
    return "built"


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="RELIANCE")
    parser.add_argument("--from", dest="from_date", required=True)
    parser.add_argument("--to", dest="to_date", required=True)
    parser.add_argument("--interval", default="5")
    parser.add_argument("--scale", type=int, default=1)
    parser.add_argument("--shadows", type=int, default=50)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--cache", default="logs/corpus/bars")
    parser.add_argument("--out", required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--breach-mode", choices=list(BREACH_MODES),
                        default="close",
                        help="close: travel through the level; wick: the "
                             "previous close on one side, the range past it")
    parser.add_argument("--confirmation-closes", type=int, default=2,
                        help="consecutive bars needed to confirm a breach")
    parser.add_argument("--no-fetch", action="store_true",
                        help="raise on a bar-cache miss instead of fetching")
    args = parser.parse_args(argv)

    events = build_to_disk(
        symbol=args.symbol, from_date=args.from_date, to_date=args.to_date,
        interval=args.interval, price_scale=args.scale,
        shadow_count=args.shadows, seed=args.seed, cache_dir=args.cache,
        out_dir=args.out, breach_mode=args.breach_mode,
        confirmation_closes=args.confirmation_closes,
        overwrite=args.overwrite, allow_fetch=not args.no_fetch)

    real = events[events["shadow_id"].isna()]
    print(f"\nwrote {args.out}")
    print(f"  real events   : {len(real)}")
    print(f"  shadow events : {len(events) - len(real)}")
    print(f"\nreal events by type:")
    print(real["event_type"].value_counts().to_string())
    print(f"\nreal breach outcomes:")
    resolved = real[real["event_type"] == "LADDER_BREACH_RESOLVED"]
    if len(resolved):
        print(resolved["outcome"].value_counts(dropna=False).to_string())
    else:
        print("  none")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/test_build_gann_corpus.py tests/study_tool/test_backfill_corpus_meta.py tests/study_tool/mining/test_report.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_gann_corpus.py tests/study_tool/test_build_gann_corpus.py
git commit -m "feat: corpus build takes the breach rule and can refuse to fetch" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Corpus meta reads the breach rule

**Files:**
- Modify: `study_tool/mining/corpus_meta.py` (the `load_meta` import; the last two dataclass fields; the `return CorpusMeta(` block of `load_corpus_meta`)
- Test: `tests/study_tool/mining/test_corpus_meta.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/study_tool/mining/test_corpus_meta.py`:

```python
def test_old_meta_without_the_breach_rule_loads_as_close_two(tmp_path):
    """Every corpus built before 2026-10-16 used close / 2 and says nothing."""
    write_meta(tmp_path, good_meta())

    meta = load_corpus_meta(tmp_path)

    assert meta.breach_mode == "close"
    assert meta.confirmation_closes == 2


def test_the_breach_rule_is_read_when_present_and_the_version_stays_one(tmp_path):
    raw = good_meta()
    raw["breach_mode"] = "wick"
    raw["confirmation_closes"] = 1
    write_meta(tmp_path, raw)

    meta = load_corpus_meta(tmp_path)

    assert raw["corpus_meta_version"] == 1
    assert (meta.breach_mode, meta.confirmation_closes) == ("wick", 1)


def test_an_unknown_breach_mode_in_meta_raises(tmp_path):
    raw = good_meta()
    raw["breach_mode"] = "body"
    write_meta(tmp_path, raw)

    with pytest.raises(ValueError, match="breach_mode"):
        load_corpus_meta(tmp_path)


def test_zero_confirmation_closes_in_meta_raises(tmp_path):
    raw = good_meta()
    raw["confirmation_closes"] = 0
    write_meta(tmp_path, raw)

    with pytest.raises(ValueError, match="confirmation_closes"):
        load_corpus_meta(tmp_path)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/mining/test_corpus_meta.py -v`

Expected: FAIL with `AttributeError: 'CorpusMeta' object has no attribute 'breach_mode'` and `DID NOT RAISE`.

- [ ] **Step 3: Implement**

In `study_tool/mining/corpus_meta.py` replace

```python
from study_tool.corpus_writer import load_meta
```

with

```python
from study_tool.corpus_writer import load_meta
from study_tool.gann_ladder_analyzer import BREACH_MODES
```

Replace the last two fields of the dataclass

```python
    resolution_window_bars: int
    bar_count: int
```

with

```python
    resolution_window_bars: int
    bar_count: int
    # The breach rule the corpus was built with. Optional keys in meta.json:
    # corpora built before 2026-10-16 do not record it, and they were all
    # close / 2. The meta version stays 1: an old reader ignores the new
    # keys and this reader defaults them.
    breach_mode: str = "close"
    confirmation_closes: int = 2
```

In `load_corpus_meta` replace

```python
    return CorpusMeta(
        symbol=raw["symbol"],
```

with

```python
    breach_mode = str(raw.get("breach_mode", "close"))
    if breach_mode not in BREACH_MODES:
        raise ValueError(
            f"breach_mode {breach_mode!r} in meta.json is not one of "
            f"{BREACH_MODES}"
        )
    confirmation_closes = int(raw.get("confirmation_closes", 2))
    if confirmation_closes < 1:
        raise ValueError(
            f"confirmation_closes {confirmation_closes} in meta.json must be "
            "at least 1"
        )

    return CorpusMeta(
        symbol=raw["symbol"],
```

and replace

```python
        resolution_window_bars=int(raw["resolution_window_bars"]),
        bar_count=int(raw["bar_count"]),
    )
```

with

```python
        resolution_window_bars=int(raw["resolution_window_bars"]),
        bar_count=int(raw["bar_count"]),
        breach_mode=breach_mode,
        confirmation_closes=confirmation_closes,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/mining -v`

Expected: all PASS (existing tests construct `CorpusMeta` without the new fields; the defaults cover them).

- [ ] **Step 5: Commit**

```bash
git add study_tool/mining/corpus_meta.py tests/study_tool/mining/test_corpus_meta.py
git commit -m "feat: corpus meta reads the breach rule, defaulting to close two" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Lag-free columns on raced breaches

**Files:**
- Modify: `study_tool/mining/ladder_rebuild.py` (`add_reach_outcomes`, lines 268-365)
- Create: `tests/study_tool/mining/test_lag_free_columns.py`

For price square 1307 the `center` ladder holds ... 1303.75, 1306.0, 1308.25 ... (checked 2026-10-16), so a breach of 1306.0 targets 1308.25 going up and 1303.75 going down.

- [ ] **Step 1: Write the failing tests**

Create `tests/study_tool/mining/test_lag_free_columns.py`:

```python
"""
The lag-free columns: was the target touched between the cross bar and the
confirmation bar, and did the confirmation bar close beyond the level?

A breach confirms on bar k after `confirmation_closes` consecutive closes, so
its cross bar is c = k - (confirmation_closes - 1). Only bars c..k decide the
filter. The race starts on the bar after k, so the filter must read no bar
after k - that is pinned here.
"""
import sys
import os

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.corpus_meta import CorpusMeta
from study_tool.mining.ladder_rebuild import LadderCache, add_reach_outcomes
from study_tool.run_ladder_study import degree_to_square

SUN = degree_to_square(155.0)
MOON = degree_to_square(331.0)
LEVEL = 1306.0          # a real `center` level for price square 1307
UP_TARGET = 1308.25     # next level up
DOWN_TARGET = 1303.75   # next level down
BAR_COUNT = 8
CONFIRM_BAR = 4         # k in every test


def keys_frame():
    return pd.DataFrame({
        "bar_index": list(range(BAR_COUNT)),
        "price_square": [1307] * BAR_COUNT,
        "sun_square": [SUN] * BAR_COUNT,
        "moon_square": [MOON] * BAR_COUNT,
    })


def meta(confirmation_closes, shadow_offsets=(0.4,)):
    return CorpusMeta(
        symbol="RELIANCE", from_date="a", to_date="b", interval="5",
        price_scale=1, shadow_count=len(shadow_offsets), seed=7,
        median_sub_gap=2.25, shadow_offsets=list(shadow_offsets),
        resolution_window_bars=50, bar_count=BAR_COUNT,
        breach_mode="close", confirmation_closes=confirmation_closes,
    )


def quiet_bars(direction):
    """Bars beyond the level that touch neither target."""
    if direction == "up":
        return pd.DataFrame({"high": [1307.0] * BAR_COUNT,
                             "low": [1306.5] * BAR_COUNT,
                             "close": [1306.8] * BAR_COUNT})
    return pd.DataFrame({"high": [1305.5] * BAR_COUNT,
                         "low": [1305.0] * BAR_COUNT,
                         "close": [1305.2] * BAR_COUNT})


def confirmed(bar_index=CONFIRM_BAR, direction="up", level=LEVEL,
              shadow_id=None):
    return pd.DataFrame({
        "event_type": ["LADDER_BREACH_CONFIRMED"],
        "bar_index": [bar_index],
        "shadow_id": [shadow_id],
        "level_source": ["center"],
        "level_price": [level],
        "direction": [direction],
    })


def outcomes(events, bars, closes):
    return add_reach_outcomes(events, bars, LadderCache(keys_frame(), 1),
                              meta(closes))


@pytest.mark.parametrize("closes, touched_bar, expected", [
    (1, 4, True),     # c = k = 4: the confirmation bar is the cross bar
    (1, 3, False),    # the bar before the cross does not count
    (2, 3, True),     # cross bar c = 3
    (2, 4, True),     # confirmation bar k = 4
    (2, 2, False),    # before the cross
    (3, 2, True),     # cross bar c = 2
    (3, 3, True),     # a middle bar
    (3, 4, True),     # confirmation bar
    (3, 1, False),    # before the cross
    (1, None, False),
    (2, None, False),
    (3, None, False),
])
def test_target_hit_before_entry_reads_bars_from_cross_to_confirmation(
        closes, touched_bar, expected):
    bars = quiet_bars("up")
    if touched_bar is not None:
        bars.loc[touched_bar, "high"] = UP_TARGET + 0.25

    result = outcomes(confirmed(), bars, closes)

    assert bool(result.loc[0, "target_hit_before_entry"]) is expected


def test_the_filter_reads_no_bar_after_confirmation():
    bars = quiet_bars("up")
    before = outcomes(confirmed(), bars, 2)

    later = bars.copy()
    later.loc[CONFIRM_BAR + 1:, "high"] = 1400.0
    later.loc[CONFIRM_BAR + 1:, "low"] = 1200.0
    later.loc[CONFIRM_BAR + 1:, "close"] = 1200.0
    after = outcomes(confirmed(), later, 2)

    for column in ("target_hit_before_entry", "entry_beyond_level"):
        assert bool(before.loc[0, column]) == bool(after.loc[0, column])
    assert bool(after.loc[0, "target_hit_before_entry"]) is False
    assert bool(after.loc[0, "entry_beyond_level"]) is True
    # The race itself does read those bars.
    assert after.loc[0, "reach_outcome"] == "REACHED"


def test_target_hit_before_entry_runs_downward():
    bars = quiet_bars("down")
    bars.loc[3, "low"] = DOWN_TARGET - 0.25

    result = outcomes(confirmed(direction="down"), bars, 2)

    assert bool(result.loc[0, "target_hit_before_entry"]) is True
    assert bool(result.loc[0, "entry_beyond_level"]) is True


def test_target_hit_before_entry_widens_target_already_hit():
    """target_already_hit reads bar k only; the cross bar can be the one."""
    bars = quiet_bars("up")
    bars.loc[3, "high"] = UP_TARGET + 0.25

    result = outcomes(confirmed(), bars, 2)

    assert bool(result.loc[0, "target_hit_before_entry"]) is True
    assert bool(result.loc[0, "target_already_hit"]) is False


def test_entry_beyond_level_is_false_when_the_confirmation_bar_closed_back():
    bars = quiet_bars("up")
    bars.loc[CONFIRM_BAR, "close"] = LEVEL - 0.1

    result = outcomes(confirmed(), bars, 1)

    assert bool(result.loc[0, "entry_beyond_level"]) is False


def test_entry_beyond_level_down_needs_a_close_below():
    bars = quiet_bars("down")
    bars.loc[CONFIRM_BAR, "close"] = LEVEL + 0.1

    result = outcomes(confirmed(direction="down"), bars, 1)

    assert bool(result.loc[0, "entry_beyond_level"]) is False


def test_a_shadow_row_tests_its_own_shifted_target():
    bars = quiet_bars("up")
    bars.loc[CONFIRM_BAR, "high"] = 1308.5   # past 1308.25, short of 1308.65
    events = pd.concat([confirmed(),
                        confirmed(level=LEVEL + 0.4, shadow_id=0.0)],
                       ignore_index=True)

    result = outcomes(events, bars, 2)

    assert bool(result.loc[0, "target_hit_before_entry"]) is True
    assert bool(result.loc[1, "target_hit_before_entry"]) is False


def test_non_breach_rows_stay_none():
    touch = pd.DataFrame({
        "event_type": ["LADDER_TOUCH"], "bar_index": [CONFIRM_BAR],
        "shadow_id": [None], "level_source": ["center"],
        "level_price": [LEVEL], "direction": [None],
    })
    events = pd.concat([confirmed(), touch], ignore_index=True)

    result = outcomes(events, quiet_bars("up"), 2)

    assert result.loc[1, "target_hit_before_entry"] is None
    assert result.loc[1, "entry_beyond_level"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/mining/test_lag_free_columns.py -v`

Expected: FAIL with `KeyError: 'target_hit_before_entry'` (and `'entry_beyond_level'`).

- [ ] **Step 3: Implement**

In `study_tool/mining/ladder_rebuild.py`, `add_reach_outcomes`:

Replace the docstring paragraph

```python
      target_already_hit  - True when the breach's own confirmation bar had
                            already reached the target. Those wins cost no
                            travel; their share must be visible.
```

with

```python
      target_already_hit  - True when the breach's own confirmation bar had
                            already reached the target. Those wins cost no
                            travel; their share must be visible.
      target_hit_before_entry
                          - True when any bar from the cross bar c to the
                            confirmation bar k inclusive touched the target,
                            c = k - (meta.confirmation_closes - 1). Widens
                            target_already_hit. Reads no bar after k.
      entry_beyond_level  - True when bar k closed beyond the breached level.
                            Always True for close rules; a wick rule can
                            confirm on a bar that closed back, and a trader
                            at that close would be past their own stop.
```

Replace

```python
    already_hit: List[Optional[bool]] = [None] * len(frame)
```

with

```python
    already_hit: List[Optional[bool]] = [None] * len(frame)
    hit_before_entry: List[Optional[bool]] = [None] * len(frame)
    beyond_level: List[Optional[bool]] = [None] * len(frame)
    # Confirmation closes are consecutive - a bar that fails to close beyond
    # rejects the breach (gann_ladder_analyzer.process_bar) - so the cross
    # bar sits exactly confirmation_closes - 1 bars before confirmation.
    lead_bars = meta.confirmation_closes - 1
```

Replace

```python
        offset = meta.offset_for(shadow_ids[position])
```

with

```python
        offset = meta.offset_for(shadow_ids[position])

        beyond_level[position] = bool(
            closes[bar] > level_price if direction == "up"
            else closes[bar] < level_price)
```

Replace

```python
        already_hit[position] = bool(
            highs[bar] >= target if direction == "up" else lows[bar] <= target)
```

with

```python
        already_hit[position] = bool(
            highs[bar] >= target if direction == "up" else lows[bar] <= target)

        # Bars c..k inclusive and never later: what a trader acting at the
        # close of k had seen.
        cross_bar = max(0, bar - lead_bars)
        if direction == "up":
            hit_before_entry[position] = bool(
                highs[cross_bar:bar + 1].max() >= target)
        else:
            hit_before_entry[position] = bool(
                lows[cross_bar:bar + 1].min() <= target)
```

Replace

```python
    frame["target_already_hit"] = already_hit
```

with

```python
    frame["target_already_hit"] = already_hit
    frame["target_hit_before_entry"] = hit_before_entry
    frame["entry_beyond_level"] = beyond_level
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/mining -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add study_tool/mining/ladder_rebuild.py tests/study_tool/mining/test_lag_free_columns.py
git commit -m "feat: lag-free columns on raced breaches" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Lag-free reach rate and dropped share statistics

**Files:**
- Modify: `study_tool/mining/statistics.py` (imports lines 20-25; new functions after `already_hit_share`; bound names at the end)
- Test: `tests/study_tool/mining/test_statistics.py`

- [ ] **Step 1: Write the failing tests**

In `tests/study_tool/mining/test_statistics.py` replace the import

```python
from study_tool.mining.statistics import (
    already_hit_share, hold_rate, mean_retest_depth, reach_next_rate,
    reach_rate_for, rejection_rate, timeout_share, timeout_share_for,
    touch_density_fn,
)
```

with

```python
from study_tool.mining.statistics import (
    already_hit_share, dropped_share, entry_dropped_share, hold_rate,
    lag_free_reach_rate, lag_free_reach_rate_for, mean_retest_depth,
    reach_next_rate, reach_rate_for, rejection_rate, timeout_share,
    timeout_share_for, touch_density_fn,
)
```

Append:

```python
def lag_free_frame():
    """
    Row 0 kept REACHED, row 1 kept STOPPED, row 2 dropped (target hit),
    row 3 dropped (closed back), row 4 kept TIMEOUT, row 5 not targeted,
    row 6 dropped by both filters.
    """
    return pd.DataFrame({
        "reach_outcome": ["REACHED", "STOPPED", "REACHED", "REACHED",
                          "TIMEOUT", None, "STOPPED"],
        "target_hit_before_entry": [False, False, True, False, False, None,
                                    True],
        "entry_beyond_level": [True, True, True, False, True, None, False],
    })


def test_lag_free_reach_rate_keeps_only_tradeable_breaches():
    stat = lag_free_reach_rate(lag_free_frame())

    assert stat.value == 0.5
    assert stat.n == 2, "timeouts and dropped rows are not decided rows"


def test_lag_free_reach_rate_binds_to_a_named_column():
    frame = lag_free_frame().rename(columns={"reach_outcome": "reach_d0_w100"})

    assert lag_free_reach_rate_for("reach_d0_w100")(frame).value == 0.5
    assert lag_free_reach_rate(frame).value is None


def test_lag_free_reach_rate_is_none_without_the_flag_columns():
    frame = pd.DataFrame({"reach_outcome": ["REACHED"]})

    assert lag_free_reach_rate(frame) == (None, 0)


def test_lag_free_flags_work_as_a_plain_bool_column():
    frame = pd.DataFrame({"reach_outcome": ["REACHED", "STOPPED"],
                          "target_hit_before_entry": [False, True],
                          "entry_beyond_level": [True, True]})
    assert frame["target_hit_before_entry"].dtype == bool

    stat = lag_free_reach_rate(frame)

    assert stat.value == 1.0
    assert stat.n == 1


def test_dropped_share_is_rows_removed_by_either_filter_over_targeted_rows():
    stat = dropped_share(lag_free_frame())

    assert stat.value == 0.5     # rows 2, 3, 6 of 6 targeted
    assert stat.n == 6, "targeted rows include timeouts, exclude untargeted"


def test_entry_dropped_share_counts_only_the_entry_filter():
    stat = entry_dropped_share(lag_free_frame())

    assert stat.value == pytest.approx(2 / 6)   # rows 3 and 6
    assert stat.n == 6


def test_dropped_shares_are_none_with_no_targeted_rows():
    frame = pd.DataFrame({"reach_outcome": [None],
                          "target_hit_before_entry": [None],
                          "entry_beyond_level": [None]})

    assert dropped_share(frame) == (None, 0)
    assert entry_dropped_share(frame) == (None, 0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/mining/test_statistics.py -v`

Expected: collection ERROR, `ImportError: cannot import name 'dropped_share'`.

- [ ] **Step 3: Implement**

In `study_tool/mining/statistics.py` replace

```python
import json
from typing import Callable, Optional

import pandas as pd
```

with

```python
import json
from typing import Callable, Optional

import numpy as np
import pandas as pd
```

After the `already_hit_share` function (before the `# The original names, bound to the strict column` comment) insert:

```python
LAG_FREE_COLUMNS = ("target_hit_before_entry", "entry_beyond_level")


def _is(flags: pd.Series, value: bool) -> pd.Series:
    """
    Rows whose flag is exactly `value`.

    None and NaN match neither True nor False: a row with no target has no
    lag-free answer, and must be neither kept nor counted as dropped.
    """
    return flags.map(
        lambda v: isinstance(v, (bool, np.bool_)) and bool(v) is value)


def _has_lag_free_columns(events: pd.DataFrame) -> bool:
    return all(column in events.columns for column in LAG_FREE_COLUMNS)


def lag_free_reach_rate_for(column: str) -> StatisticFn:
    """
    REACHED / (REACHED + STOPPED) over the breaches a trader could take.

    Kept: the target was not touched on any bar from the cross to the
    confirmation (target_hit_before_entry False) and the confirmation bar
    closed beyond the level (entry_beyond_level True). Only bars up to the
    confirmation decide inclusion, so the filter adds no lookahead.
    """
    rate = reach_rate_for(column)

    def lag_free_reach_rate(events: pd.DataFrame) -> Stat:
        if not _has_lag_free_columns(events):
            return Stat(None, 0)
        kept = (_is(events["target_hit_before_entry"], False)
                & _is(events["entry_beyond_level"], True))
        return rate(events[kept])

    return lag_free_reach_rate


def dropped_share(events: pd.DataFrame) -> Stat:
    """
    Rows removed by either lag-free filter / targeted rows.

    Targeted rows are confirmed breaches that had a target
    (target_hit_before_entry not null), whatever their race outcome,
    timeouts included. Compared real against shadow: if the filter removes
    a different share of real rows than of shadow rows, the filtered sets
    are not like-for-like.
    """
    if not _has_lag_free_columns(events):
        return Stat(None, 0)
    hit = events["target_hit_before_entry"]
    targeted = _is(hit, True) | _is(hit, False)
    n = int(targeted.sum())
    if n == 0:
        return Stat(None, 0)
    dropped = targeted & (_is(hit, True)
                          | _is(events["entry_beyond_level"], False))
    return Stat(int(dropped.sum()) / n, n)


def entry_dropped_share(events: pd.DataFrame) -> Stat:
    """
    Targeted rows whose confirmation bar closed back (entry_beyond_level
    False) / targeted rows, whether or not the target filter also drops
    them. Zero for every close rule; only a wick rule can be non-zero.
    """
    if not _has_lag_free_columns(events):
        return Stat(None, 0)
    hit = events["target_hit_before_entry"]
    targeted = _is(hit, True) | _is(hit, False)
    n = int(targeted.sum())
    if n == 0:
        return Stat(None, 0)
    dropped = targeted & _is(events["entry_beyond_level"], False)
    return Stat(int(dropped.sum()) / n, n)
```

At the end of the file, after

```python
reach_next_rate = reach_rate_for("reach_outcome")
timeout_share = timeout_share_for("reach_outcome")
```

add

```python
# The lag-free statistic of the 2026-10-16 breach sweep, on the strict column.
lag_free_reach_rate = lag_free_reach_rate_for("reach_outcome")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/mining/test_statistics.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add study_tool/mining/statistics.py tests/study_tool/mining/test_statistics.py
git commit -m "feat: lag-free reach rate and dropped share statistics" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Comparison exposes z and "above all shadows"

**Files:**
- Modify: `study_tool/mining/shadow_compare.py` (after the `margin` property, line 80)
- Test: `tests/study_tool/mining/test_shadow_compare.py`

"Missing shadows" is the existing `Comparison.shadows_missing`: shadows with no rows in the group **and** shadows whose statistic was undefined there (`compare()` counts both). Either way the shadow has no value `s_i`, so a real value cannot be shown to beat it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/study_tool/mining/test_shadow_compare.py`:

```python
# -- z and above_all_shadows (2026-10-16 breach sweep) ------------------------


def test_z_is_distance_from_the_shadow_mean_in_sample_sds():
    result = Comparison(real=5.0, n=10, shadows=[1.0, 2.0, 3.0])

    assert result.z == pytest.approx(3.0)


def test_z_is_none_with_fewer_than_two_shadows():
    assert Comparison(real=5.0, n=1, shadows=[1.0]).z is None


def test_z_is_none_when_the_shadows_have_no_spread():
    assert Comparison(real=5.0, n=1, shadows=[2.0, 2.0, 2.0]).z is None


def test_z_is_none_when_real_is_undefined():
    assert Comparison(real=None, n=0, shadows=[1.0, 2.0]).z is None


def test_z_uses_only_shadows_that_have_a_value():
    result = compare(frame(9.0, [1.0, 2.0, 3.0]), mean_v, shadow_count=4)

    assert result.shadows_missing == 1
    assert result.z == pytest.approx(7.0)


def test_above_all_shadows_needs_real_strictly_above_the_max():
    assert Comparison(real=5.0, n=1, shadows=[1.0, 2.0, 3.0]).above_all_shadows
    assert not Comparison(real=3.0, n=1, shadows=[1.0, 2.0, 3.0]).above_all_shadows


def test_above_all_shadows_is_false_when_any_shadow_is_missing():
    result = compare(frame(9.0, [1.0, 2.0]), mean_v, shadow_count=3)

    assert result.shadows_missing == 1
    assert result.above_all_shadows is False
    assert result.outside_range is True, "the old flag ignores missing shadows"


def test_above_all_shadows_is_false_when_real_is_undefined():
    assert Comparison(real=None, n=0, shadows=[1.0]).above_all_shadows is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/mining/test_shadow_compare.py -v`

Expected: FAIL with `AttributeError: 'Comparison' object has no attribute 'z'` / `'above_all_shadows'`.

- [ ] **Step 3: Implement**

In `study_tool/mining/shadow_compare.py`, directly after the `margin` property (its last line is `        return self.real - self.shadow_min`), insert:

```python

    @property
    def z(self) -> Optional[float]:
        """
        (real - mean of the shadows) / sample sd of the shadows.

        None when real is None, fewer than two shadows have a value, or the
        shadows have no spread. Rule selection uses z rather than margin
        because the shadow spread narrows as row count grows, and breach
        rules have very different row counts.
        """
        if self.real is None or len(self.shadows) < 2:
            return None
        spread = _stats.stdev(self.shadows)
        if spread == 0:
            return None
        return (self.real - _stats.mean(self.shadows)) / spread

    @property
    def above_all_shadows(self) -> bool:
        """
        Real beats every shadow, and no shadow is missing.

        shadows_missing counts shadows with no rows in the group and shadows
        whose statistic was undefined there. Either way that shadow has no
        value to beat, so real has not been shown to beat it.
        """
        if self.real is None or not self.shadows or self.shadows_missing:
            return False
        return self.real > max(self.shadows)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/mining/test_shadow_compare.py tests/study_tool/mining/test_report.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add study_tool/mining/shadow_compare.py tests/study_tool/mining/test_shadow_compare.py
git commit -m "feat: comparison exposes z and above all shadows" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: `load_events` reads every slice by name

**Files:**
- Modify: `study_tool/corpus_writer.py` (line 27 `SLICES`; `load_events` lines 126-148)
- Test: `tests/study_tool/test_corpus_writer.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/study_tool/test_corpus_writer.py`:

```python
def test_load_events_reads_every_row_when_asked_for_all(tmp_path):
    """
    RELIANCE's holdout is spent and AAPL is read whole, once; both read every
    row. It is still a named argument, never the default.
    """
    write_corpus(tmp_path, events=assign_slices(events_frame()),
                 bars=bars_frame(), ladder_keys=keys_frame(), meta=meta_dict())

    loaded = load_events(tmp_path, slice_name="all")

    assert len(loaded) == 10
    assert set(loaded["slice"]) == {"explore", "holdout"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/test_corpus_writer.py -v`

Expected: FAIL with `ValueError: unknown slice 'all'; expected one of ('explore', 'holdout')`.

- [ ] **Step 3: Implement**

In `study_tool/corpus_writer.py` replace

```python
SLICES = ("explore", "holdout")
```

with

```python
SLICES = ("explore", "holdout")
# Not a slice label: the name load_events takes for every row at once.
ALL_SLICES = "all"
```

In `load_events` replace

```python
    if slice_name not in SLICES:
        raise ValueError(
            f"unknown slice {slice_name!r}; expected one of {SLICES}"
        )
```

with

```python
    if slice_name == ALL_SLICES:
        # Every row, for a corpus whose split means nothing: RELIANCE after
        # its holdout was spent (2026-09-03), or a fresh holdout read whole,
        # once. Still a named argument, so it shows up in review.
        frame = pd.read_parquet(Path(corpus_dir) / "events.parquet")
        return frame.reset_index(drop=True)
    if slice_name not in SLICES:
        raise ValueError(
            f"unknown slice {slice_name!r}; expected one of "
            f"{SLICES + (ALL_SLICES,)}"
        )
```

and add to the docstring of `load_events`, after its first paragraph (`Events for one slice. Defaults to `explore`.`):

```python

    `all` returns every row of both slices.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/test_corpus_writer.py -v`

Expected: all PASS (the existing `unknown slice` test still matches).

- [ ] **Step 5: Commit**

```bash
git add study_tool/corpus_writer.py tests/study_tool/test_corpus_writer.py
git commit -m "feat: load every slice of a corpus by name" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Mine a whole corpus with `--slice all`; reusable scoring

**Files:**
- Modify: `scripts/mine_gann_corpus.py` (whole file; full replacement below)
- Create: `tests/study_tool/test_mine_gann_corpus.py`

The run is split so the sweep and the AAPL command can reuse the expensive part (load + race) and compute only their own statistics: `load_scored_events` -> `ScoredCorpus`; `render_mining_report(scored)` renders the existing full report and is used by `run()` only - never on AAPL (Task 16). `run()` keeps its signature and output, so the existing tests in `tests/study_tool/mining/test_report.py` cover the refactor.

- [ ] **Step 1: Write the failing tests**

Create `tests/study_tool/test_mine_gann_corpus.py`:

```python
"""
Mining a whole corpus (--slice all), and the lag-free statistics in the
report. Synthetic corpus, no network, no 113 MB of Parquet.
"""
import sys
import os

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend/scripts'))

from build_gann_corpus import build_corpus
from mine_gann_corpus import load_scored_events, run
from study_tool.corpus_writer import assign_slices, write_corpus


def tiny_corpus(corpus_dir):
    epoch = 1787629500
    rows = []
    for i in range(400):
        open_ = 1300.0 + (i % 40) * 0.6
        close = open_ + 0.5
        rows.append({"open": open_, "high": close + 0.4, "low": open_ - 0.4,
                     "close": close, "volume": 1000.0,
                     "timestamp": float(epoch + i * 300),
                     "sun_degree": 155.0 + i * 0.0007,
                     "moon_degree": (331.0 + i * 0.009) % 360})
    result = build_corpus(bars=pd.DataFrame(rows), instrument="RELIANCE",
                          timeframe="5", price_scale=1, shadow_count=3, seed=7)
    meta = dict(result["meta"])
    meta["from_date"], meta["to_date"] = "2026-08-01", "2026-08-31"
    write_corpus(corpus_dir, events=assign_slices(result["events"]),
                 bars=result["bars"], ladder_keys=result["ladder_keys"],
                 meta=meta)
    return len(pd.read_parquet(corpus_dir / "events.parquet"))


def test_load_scored_events_all_returns_every_row_with_lag_free_columns(tmp_path):
    total = tiny_corpus(tmp_path)

    scored = load_scored_events(tmp_path, slice_name="all")

    assert len(scored.events) == total
    assert scored.slice_name == "all"
    assert scored.dropped_to_buffer == 0
    for column in ("reach_outcome", "target_hit_before_entry",
                   "entry_beyond_level", "level_ring_bin"):
        assert column in scored.events.columns


def test_slice_all_mines_every_row_without_the_buffer_drop(tmp_path):
    total = tiny_corpus(tmp_path)

    text = run(tmp_path, slice_name="all")

    run_section = text.split("## Run")[1].split("## Fairness")[0]
    assert "slice: all" in run_section
    assert f"all events used: {total}" in run_section
    assert "dropped to the boundary buffer: 0" in run_section


def test_the_report_carries_the_lag_free_statistics(tmp_path):
    tiny_corpus(tmp_path)

    text = run(tmp_path, slice_name="all")

    for name in ("lag_free_reach_rate", "dropped_share", "entry_dropped_share"):
        assert f"### {name}" in text, f"missing {name}"


def test_an_unknown_slice_is_refused(tmp_path):
    tiny_corpus(tmp_path)

    with pytest.raises(ValueError, match="unknown slice"):
        run(tmp_path, slice_name="test")


def test_the_command_line_accepts_slice_all(tmp_path):
    import mine_gann_corpus as miner
    corpus, out = tmp_path / "corpus", tmp_path / "reports"
    corpus.mkdir()
    tiny_corpus(corpus)

    miner.main(["--corpus", str(corpus), "--out", str(out), "--slice", "all"])

    reports = list(out.glob("gann-mining-report-*.md"))
    assert len(reports) == 1
    assert "slice: all" in reports[0].read_text(encoding="utf-8")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/test_mine_gann_corpus.py -v`

Expected: collection ERROR, `ImportError: cannot import name 'load_scored_events' from 'mine_gann_corpus'`.

- [ ] **Step 3: Implement**

Replace the entire contents of `scripts/mine_gann_corpus.py` with:

```python
"""
Mine the Gann corpus against its shadow control and write the report.

Usage:
    python scripts/mine_gann_corpus.py --corpus logs/corpus/reliance_5m_x1 \
        --out docs/superpowers/reports

Defaults to the explore slice. Pass --slice holdout for the one-time
confirmation pass over the holdout slice, once a shortlist has been declared
against explore. Pass --slice all to read every row: for a corpus whose split
means nothing (RELIANCE after its holdout was spent on 2026-09-03) or a fresh
holdout read whole, once (AAPL, 2026-10-16 breach sweep).

The boundary buffer-drop exists only to protect explore events from having
their outcome decided by holdout price action, which sits chronologically
after explore. It runs for explore only: holdout is the last slice, and
`all` has no split to protect.
"""

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from study_tool.corpus_writer import ALL_SLICES, load_events
from study_tool.mining.boundary import boundary_bar_index, drop_boundary_events
from study_tool.mining.corpus_meta import CorpusMeta, load_corpus_meta
from study_tool.mining.groups import GROUPINGS, add_ring_bin, iter_groups
from study_tool.mining.ladder_rebuild import (
    LadderCache, add_reach_outcomes, outcome_column,
)
from study_tool.mining.report import GroupResult, render_report
from study_tool.mining.shadow_compare import compare
from study_tool.mining.statistics import (
    StatisticFn, already_hit_share, dropped_share, entry_dropped_share,
    hold_rate, lag_free_reach_rate, mean_retest_depth, reach_rate_for,
    rejection_rate, timeout_share_for, touch_density_fn,
)

SLICE_CHOICES = ("explore", "holdout", ALL_SLICES)


def _check_ladder_tables(bars: pd.DataFrame, keys: pd.DataFrame) -> None:
    """
    A duplicate bar_index in ladder_keys would silently overwrite in
    LadderCache's internal dict, mis-racing every event built from that bar.
    Bars must also cover every bar_index the keys reference, or
    race_to_next_level would silently read past valid data. Both failures are
    the kind that produce a plausible-looking wrong report rather than a
    crash, so they are checked here and raised loudly instead.
    """
    if not keys["bar_index"].is_unique:
        dupes = keys.loc[keys["bar_index"].duplicated(), "bar_index"].unique()
        raise ValueError(
            f"ladder_keys has duplicate bar_index values {list(dupes)[:5]}; "
            "LadderCache would silently overwrite one with the other"
        )

    max_key_bar = int(keys["bar_index"].max())
    if len(bars) < max_key_bar + 1:
        raise ValueError(
            f"bars has {len(bars)} rows but ladder_keys references bar_index "
            f"up to {max_key_bar}; race_to_next_level would read past the "
            "end of bars"
        )


@dataclass
class ScoredCorpus:
    """One slice of a corpus with the reach race run, and how it was cut."""
    corpus_dir: Path
    events: pd.DataFrame
    meta: CorpusMeta
    slice_name: str
    boundary: int
    dropped_to_buffer: int
    sweep_columns: List[str]


def _load_slice(corpus_dir: Path, slice_name: str, boundary: int,
                buffer_bars: int) -> Tuple[pd.DataFrame, int]:
    """Events for the slice, and how many the boundary buffer dropped."""
    if slice_name == "explore":
        events = load_events(corpus_dir, slice_name="explore")
        buffered = drop_boundary_events(
            events, boundary=boundary, buffer_bars=buffer_bars)
        print(f"dropped {buffered.dropped} events inside the "
              f"{buffer_bars}-bar buffer")
        return buffered.events, buffered.dropped
    if slice_name == "holdout":
        # Holdout is the last slice - no data after it can leak into it.
        return load_events(corpus_dir, slice_name="holdout"), 0
    if slice_name == ALL_SLICES:
        # Every row: there is no split to protect.
        return load_events(corpus_dir, slice_name=ALL_SLICES), 0
    raise ValueError(
        f"unknown slice {slice_name!r}; expected one of {SLICE_CHOICES}")


def load_scored_events(corpus_dir: Union[str, Path],
                       slice_name: str = "explore",
                       stop_depths: Sequence[float] = (0.0,),
                       windows: Optional[Sequence[int]] = None) -> ScoredCorpus:
    """
    Load one slice, add level_ring_bin, and run the reach race.

    `stop_depths` and `windows` sweep the race: every pair gets its own
    outcome column. The defaults - depth 0 at the corpus's own resolution
    window - reproduce the strict test the confirmed result was measured
    with, and give `reach_outcome`, which the lag-free statistic reads.
    """
    corpus_dir = Path(corpus_dir)
    meta = load_corpus_meta(corpus_dir)

    # Only bar_index and slice are read from the full events table, to find
    # the boundary. That is structural bookkeeping, not price action, so it
    # does not spend the holdout.
    all_slices = pd.read_parquet(corpus_dir / "events.parquet",
                                 columns=["bar_index", "slice"])
    boundary = boundary_bar_index(all_slices)
    del all_slices
    print(f"explore/holdout boundary at bar {boundary}")

    events, dropped_to_buffer = _load_slice(
        corpus_dir, slice_name, boundary, meta.resolution_window_bars)
    events = add_ring_bin(events)

    bars = pd.read_parquet(corpus_dir / "bars.parquet")
    keys = pd.read_parquet(corpus_dir / "ladder_keys.parquet")
    _check_ladder_tables(bars, keys)

    started = time.time()
    cache = LadderCache(keys, meta.price_scale)
    events = add_reach_outcomes(events, bars, cache, meta,
                                stop_depths=stop_depths, windows=windows)

    resolved_windows = tuple(windows or (meta.resolution_window_bars,))
    sweep_columns = [outcome_column(d, w)
                     for d in stop_depths for w in resolved_windows]

    # Per sweep column, not `reach_outcome`. That alias only exists when the
    # sweep actually contains depth 0 at the corpus window.
    elapsed = time.time() - started
    raced = ", ".join(f"{c}={int(events[c].notna().sum())}"
                      for c in sweep_columns if c in events.columns)
    print(f"raced breaches in {elapsed:.0f}s: {raced or 'none'}")

    return ScoredCorpus(corpus_dir=corpus_dir, events=events, meta=meta,
                        slice_name=slice_name, boundary=boundary,
                        dropped_to_buffer=dropped_to_buffer,
                        sweep_columns=sweep_columns)


def mining_statistics(scored: ScoredCorpus) -> Dict[str, StatisticFn]:
    """Every statistic the report runs, by name."""
    bar_count = int(scored.events["bar_index"].nunique())
    statistics: Dict[str, StatisticFn] = {
        "hold_rate": hold_rate,
        "rejection_rate": rejection_rate,
        "mean_retest_depth": mean_retest_depth,
        "touch_density": touch_density_fn(bar_count),
        "already_hit_share": already_hit_share,
        "lag_free_reach_rate": lag_free_reach_rate,
        "dropped_share": dropped_share,
        "entry_dropped_share": entry_dropped_share,
    }
    for column in scored.sweep_columns:
        statistics[f"reach_rate[{column}]"] = reach_rate_for(column)
        statistics[f"timeout_share[{column}]"] = timeout_share_for(column)
    return statistics


def render_mining_report(scored: ScoredCorpus) -> str:
    """The standard mining report Markdown for an already-raced slice."""
    statistics = mining_statistics(scored)
    events, meta = scored.events, scored.meta

    results: List[GroupResult] = []
    for grouping in GROUPINGS:
        for label, rows in iter_groups(events, grouping):
            for name, fn in statistics.items():
                results.append(GroupResult(
                    grouping, label, name,
                    compare(rows, fn, shadow_count=meta.shadow_count)))

    context: Dict = {
        "slice": scored.slice_name,
        "corpus_dir": str(scored.corpus_dir),
        "symbol": meta.symbol,
        "interval": meta.interval,
        "price_scale": meta.price_scale,
        "shadow_count": meta.shadow_count,
        "explore_events": len(events),
        "dropped_to_buffer": scored.dropped_to_buffer,
        "boundary_bar_index": scored.boundary,
        "buffer_bars": meta.resolution_window_bars,
        "touch_density": compare(events, statistics["touch_density"],
                                 shadow_count=meta.shadow_count),
    }
    return render_report(results, context)


def run(corpus_dir: Union[str, Path], slice_name: str = "explore",
        stop_depths: Sequence[float] = (0.0,),
        windows: Optional[Sequence[int]] = None) -> str:
    """Mine one corpus and return the report Markdown."""
    scored = load_scored_events(corpus_dir, slice_name=slice_name,
                                stop_depths=stop_depths, windows=windows)
    return render_mining_report(scored)


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--out", default="docs/superpowers/reports")
    parser.add_argument("--slice", choices=list(SLICE_CHOICES),
                        default="explore")
    parser.add_argument(
        "--stop-depths", default="0",
        help="comma-separated ladder steps behind the breached level to place "
             "the stop; 0 is the strict test (stop on the level itself)")
    parser.add_argument(
        "--windows", default="",
        help="comma-separated bar windows for the race; empty uses the "
             "corpus's own resolution_window_bars")
    args = parser.parse_args(argv)

    depths = tuple(float(d) for d in args.stop_depths.split(",") if d.strip())
    race_windows = tuple(int(w) for w in args.windows.split(",") if w.strip())
    text = run(Path(args.corpus), slice_name=args.slice,
               stop_depths=depths or (0.0,),
               windows=race_windows or None)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d-%H%M")
    path = out_dir / f"gann-mining-report-{stamp}.md"
    path.write_text(text, encoding="utf-8")

    print(text)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/test_mine_gann_corpus.py tests/study_tool/mining/test_report.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/mine_gann_corpus.py tests/study_tool/test_mine_gann_corpus.py
git commit -m "feat: mine a whole corpus with --slice all" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: AAPL 1-minute RTH JSON -> 5-minute bar cache

**Files:**
- Create: `study_tool/aapl_bars.py`
- Create: `tests/study_tool/test_aapl_bars.py`

The command-line wrapper `scripts/load_aapl_bars.py` is built in Task 16, after `read_choice` exists (Task 13): it refuses to build AAPL bars until the RELIANCE choice file exists and names a rule.

Facts about the real source, checked 2026-10-16 (tests do **not** read it): `C:/Dev/GannTesting/data_local/aapl_rth_1m.json` is `{"symbol", "source", "candles": [{"time", "open", "high", "low", "close", "volume"}, ...]}`, 1,050,923 minutes, `time` = UTC epoch of the minute start. In 2024-09-02..2026-09-01 it holds 195,019 minutes over 501 New York sessions, all between 09:30 and 15:59. On the five NYSE early-close days in the window (2024-11-29, 2024-12-24, 2025-07-03, 2025-11-28, 2025-12-24) it **also keeps 13:00-15:59 minutes** (529 in total) whose median volume is about 1,000 against about 50,000 before 13:00: extended-hours prints, not the session. The loader drops them and prints the count. 2026-07-02 traded a full day (median volume after 13:00 about 91,000) and is not an early close. The last minute before the window is 2024-08-30 15:59, close 228.86.

- [ ] **Step 1: Write the failing tests**

Create `tests/study_tool/test_aapl_bars.py`:

```python
"""
AAPL 1-minute regular-hours bars resampled to the 5-minute corpus cache.

Small synthetic minutes only - never the 105 MB source file.
"""
import sys
import os
import json

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend/scripts'))

from study_tool.aapl_bars import (
    NYSE_EARLY_CLOSES, last_close_before, read_minute_json, resample_to_5m,
    session_close, write_bar_cache,
)
from study_tool.bar_cache import load_bars, no_fetch

FROM, TO = "2024-09-02", "2026-09-01"


def epoch(date, hm):
    """UTC epoch seconds of a New York wall-clock minute."""
    return int(pd.Timestamp(f"{date} {hm}", tz="America/New_York").timestamp())


def minutes(date, start_hm, count, base=100.0):
    start = epoch(date, start_hm)
    return [{"time": start + 60 * i, "open": base + i,
             "high": base + i + 0.5, "low": base + i - 0.5,
             "close": base + i + 0.25, "volume": 10.0 + i}
            for i in range(count)]


def frame(*chunks):
    return pd.DataFrame([row for chunk in chunks for row in chunk])


def test_buckets_start_at_0930_and_aggregate_ohlcv():
    result = resample_to_5m(frame(minutes("2025-03-07", "09:30", 10)), FROM, TO)
    bars = result.bars

    assert list(bars["timestamp"]) == [float(epoch("2025-03-07", "09:30")),
                                       float(epoch("2025-03-07", "09:35"))]
    assert list(bars["open"]) == [100.0, 105.0]
    assert list(bars["high"]) == [104.5, 109.5]
    assert list(bars["low"]) == [99.5, 104.5]
    assert list(bars["close"]) == [104.25, 109.25]
    assert list(bars["volume"]) == [60.0, 85.0]          # 10..14, 15..19
    assert list(bars.columns) == ["open", "high", "low", "close", "volume",
                                  "timestamp"]


def test_dst_moves_the_utc_timestamp_not_the_new_york_alignment():
    """2025-03-07 is EST (UTC-5), 2025-03-10 is EDT (UTC-4)."""
    result = resample_to_5m(frame(minutes("2025-03-07", "09:30", 5),
                                  minutes("2025-03-10", "09:30", 5)), FROM, TO)

    assert list(result.bars["timestamp"]) == [1741357800.0, 1741613400.0]


def test_a_bucket_never_spans_two_sessions():
    result = resample_to_5m(frame(minutes("2025-03-07", "15:57", 3),
                                  minutes("2025-03-10", "09:30", 2, base=200.0)),
                            FROM, TO)
    bars = result.bars

    assert list(bars["timestamp"]) == [float(epoch("2025-03-07", "15:55")),
                                       float(epoch("2025-03-10", "09:30"))]
    assert list(bars["volume"]) == [33.0, 21.0]
    assert list(bars["open"]) == [100.0, 200.0]
    assert result.sessions == 2


def test_an_early_close_day_drops_the_minutes_after_1300():
    assert "2024-12-24" in NYSE_EARLY_CLOSES

    result = resample_to_5m(frame(minutes("2024-12-24", "12:55", 15),
                                  minutes("2025-03-07", "13:00", 5)), FROM, TO)

    assert list(result.bars["timestamp"]) == [
        float(epoch("2024-12-24", "12:55")), float(epoch("2025-03-07", "13:00"))]
    assert result.early_close_minutes_dropped == 10


def test_the_window_is_inclusive_of_both_dates():
    result = resample_to_5m(frame(minutes("2024-08-30", "09:30", 1),
                                  minutes("2024-09-03", "09:30", 1),
                                  minutes("2026-09-01", "09:30", 1),
                                  minutes("2026-09-02", "09:30", 1)), FROM, TO)

    assert list(result.bars["timestamp"]) == [
        float(epoch("2024-09-03", "09:30")), float(epoch("2026-09-01", "09:30"))]
    assert result.sessions == 2


@pytest.mark.parametrize("hm", ["09:29", "16:00"])
def test_a_minute_outside_regular_hours_is_refused(hm):
    with pytest.raises(ValueError, match="outside 09:30-16:00"):
        resample_to_5m(frame(minutes("2025-03-07", hm, 1)), FROM, TO)


def test_the_closes_before_the_window_come_from_the_last_session():
    minutes_frame = frame(minutes("2024-08-30", "15:58", 2, base=228.0),
                          minutes("2024-09-03", "09:30", 1, base=230.0))

    assert last_close_before(minutes_frame, FROM) == ("2024-08-30", 229.25)
    assert session_close(minutes_frame, "2024-08-30") == 229.25


def test_read_minute_json_reads_the_candles_list(tmp_path):
    path = tmp_path / "aapl.json"
    path.write_text(json.dumps({"symbol": "AAPL", "source": "test",
                                "candles": minutes("2025-03-07", "09:30", 3)}))

    loaded = read_minute_json(path)

    assert list(loaded.columns) == ["time", "open", "high", "low", "close",
                                    "volume"]
    assert len(loaded) == 3


def test_read_minute_json_refuses_a_file_without_candles(tmp_path):
    path = tmp_path / "aapl.json"
    path.write_text(json.dumps({"symbol": "AAPL"}))

    with pytest.raises(ValueError, match="candles"):
        read_minute_json(path)


def test_the_cache_file_is_a_hit_for_load_bars(tmp_path):
    bars = resample_to_5m(frame(minutes("2025-03-07", "09:30", 10)),
                          FROM, TO).bars
    write_bar_cache(bars, "AAPL", FROM, TO, "5", tmp_path)

    cached = load_bars("AAPL", FROM, TO, "5", cache_dir=tmp_path,
                       fetcher=no_fetch)

    assert len(cached) == 2
    assert list(cached["timestamp"]) == list(bars["timestamp"])
    for column in ("sun_degree", "moon_degree"):
        assert cached[column].notna().all()


def test_write_bar_cache_refuses_to_replace_without_overwrite(tmp_path):
    bars = resample_to_5m(frame(minutes("2025-03-07", "09:30", 5)),
                          FROM, TO).bars
    write_bar_cache(bars, "AAPL", FROM, TO, "5", tmp_path)

    with pytest.raises(FileExistsError, match="overwrite"):
        write_bar_cache(bars, "AAPL", FROM, TO, "5", tmp_path)

    write_bar_cache(bars, "AAPL", FROM, TO, "5", tmp_path, overwrite=True)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/test_aapl_bars.py -v`

Expected: collection ERROR, `ModuleNotFoundError: No module named 'study_tool.aapl_bars'`.

- [ ] **Step 3: Implement the loader module**

Create `study_tool/aapl_bars.py`:

```python
"""
AAPL 1-minute regular-hours bars, resampled into the 5-minute bar cache.

AAPL is the fresh holdout for the Square-of-9 ladder (spec:
docs/superpowers/specs/2026-10-16-gann-breach-definition-sweep-design.md).
The source is Alpaca 1-minute bars filtered to 09:30-16:00 New York
(`data_local/aapl_rth_1m.json` in the main checkout; key `time` = UTC epoch
seconds of the minute's start).

Sessions are New York calendar dates, so DST needs no special case: each
bucket start is computed from the minute's own epoch, never from a fixed UTC
offset. Buckets are 5 minutes from 09:30 and never span two sessions, because
a session never crosses midnight.

Early closes: the source keeps 13:00-16:00 minutes on NYSE half-days. Those
are extended-hours prints (median 1-minute volume about 1,000 against about
50,000 before 13:00 on the same days, checked 2026-10-16), so they are
dropped and counted.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet, Tuple, Union

import pandas as pd

from study_tool.bar_cache import cache_path, load_bars

NEW_YORK = "America/New_York"
SESSION_OPEN_MINUTE = 9 * 60 + 30     # 09:30
SESSION_MINUTES = 390                 # 09:30-16:00
EARLY_CLOSE_MINUTES = 210             # 09:30-13:00
BUCKET_MINUTES = 5
MINUTE_COLUMNS = ["time", "open", "high", "low", "close", "volume"]
BAR_COLUMNS = ["open", "high", "low", "close", "volume", "timestamp"]

# NYSE 1 p.m. closes inside 2024-09-02..2026-09-01. 2026-07-02 traded a full
# day in the source and is not one.
NYSE_EARLY_CLOSES: FrozenSet[str] = frozenset({
    "2024-11-29", "2024-12-24", "2025-07-03", "2025-11-28", "2025-12-24",
})


@dataclass(frozen=True)
class Resampled:
    bars: pd.DataFrame
    sessions: int
    early_close_minutes_dropped: int


def read_minute_json(path: Union[str, Path]) -> pd.DataFrame:
    """The `candles` list of the Alpaca JSON as a frame."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    candles = data.get("candles") if isinstance(data, dict) else None
    if not candles:
        raise ValueError(f"{path} has no 'candles' list")
    frame = pd.DataFrame(candles)
    missing = [c for c in MINUTE_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"{path} candles are missing {missing}")
    return frame.loc[:, MINUTE_COLUMNS]


def _new_york(minutes: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    """(New York date as YYYY-MM-DD, minutes since 09:30) for every row."""
    local = (pd.to_datetime(minutes["time"], unit="s", utc=True)
             .dt.tz_convert(NEW_YORK))
    dates = local.dt.strftime("%Y-%m-%d")
    offsets = local.dt.hour * 60 + local.dt.minute - SESSION_OPEN_MINUTE
    return dates, offsets


def resample_to_5m(minutes: pd.DataFrame, from_date: str, to_date: str,
                   early_closes: FrozenSet[str] = NYSE_EARLY_CLOSES) -> Resampled:
    """
    5-minute bars for New York dates from_date..to_date inclusive.

    Bar timestamp = bucket start as UTC epoch seconds, float (the corpus
    convention, as in the RELIANCE cache). open first, high max, low min,
    close last, volume sum.

    Raises:
        ValueError: on a minute not on a whole minute, or outside 09:30-16:00
            New York. The source is meant to be regular hours only; a stray
            premarket print would open a bucket before 09:30.
    """
    frame = minutes.sort_values("time").reset_index(drop=True)
    dates, offsets = _new_york(frame)

    in_window = (dates >= from_date) & (dates <= to_date)
    frame, dates, offsets = frame[in_window], dates[in_window], offsets[in_window]
    if frame.empty:
        raise ValueError(f"no minutes between {from_date} and {to_date}")
    if (frame["time"] % 60 != 0).any():
        raise ValueError("a minute timestamp is not on a whole minute")

    outside = (offsets < 0) | (offsets >= SESSION_MINUTES)
    if outside.any():
        first = int(frame.loc[outside, "time"].iloc[0])
        raise ValueError(
            f"minute at epoch {first} is outside 09:30-16:00 New York")

    late = dates.isin(early_closes) & (offsets >= EARLY_CLOSE_MINUTES)
    dropped = int(late.sum())
    frame, dates, offsets = frame[~late], dates[~late], offsets[~late]

    bucket_start = frame["time"] - (offsets % BUCKET_MINUTES) * 60
    grouped = frame.assign(bucket=bucket_start).groupby("bucket", sort=True)
    bars = pd.DataFrame({
        "open": grouped["open"].first(),
        "high": grouped["high"].max(),
        "low": grouped["low"].min(),
        "close": grouped["close"].last(),
        "volume": grouped["volume"].sum(),
    }).reset_index().rename(columns={"bucket": "timestamp"})
    bars["timestamp"] = bars["timestamp"].astype(float)

    return Resampled(bars=bars.loc[:, BAR_COLUMNS].reset_index(drop=True),
                     sessions=int(dates.nunique()),
                     early_close_minutes_dropped=dropped)


def session_close(minutes: pd.DataFrame, date: str) -> float:
    """The last 1-minute close on one New York date."""
    dates, _ = _new_york(minutes)
    day = minutes[dates == date]
    if day.empty:
        raise ValueError(f"no minutes on {date}")
    return float(day.sort_values("time")["close"].iloc[-1])


def last_close_before(minutes: pd.DataFrame,
                      from_date: str) -> Tuple[str, float]:
    """
    (New York date, close) of the last minute before `from_date`.

    The x6 scale is fixed from this, data before the window, never from the
    window itself.
    """
    dates, _ = _new_york(minutes)
    before = minutes[dates < from_date]
    if before.empty:
        raise ValueError(f"no minutes before {from_date}")
    last = before["time"].idxmax()
    return str(dates[last]), float(before.loc[last, "close"])


def write_bar_cache(bars: pd.DataFrame, symbol: str, from_date: str,
                    to_date: str, interval: str,
                    cache_dir: Union[str, Path],
                    overwrite: bool = False) -> pd.DataFrame:
    """
    Put the bars where build_gann_corpus looks for them.

    Goes through bar_cache.load_bars with a fetcher that returns these bars,
    so the existing code adds sun_degree / moon_degree and writes the file
    atomically, and a later build is a plain cache hit that never calls Dhan.
    """
    path = cache_path(cache_dir, symbol, from_date, to_date, interval)
    if path.exists():
        if not overwrite:
            raise FileExistsError(
                f"{path} already exists; pass overwrite=True to replace it")
        path.unlink()
    return load_bars(symbol, from_date, to_date, interval,
                     cache_dir=cache_dir, fetcher=lambda *_: bars)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/test_aapl_bars.py tests/study_tool/test_bar_cache.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add study_tool/aapl_bars.py tests/study_tool/test_aapl_bars.py
git commit -m "feat: resample aapl 1m rth bars into the bar cache" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: The close2 regression gate

**Files:**
- Create: `study_tool/mining/regression_gate.py`
- Create: `tests/study_tool/mining/test_regression_gate.py`

**Definition of "match exactly"** (spec: "same rows, same values"), fixed here:
1. Same column names in the same order.
2. Same Arrow type per column.
3. Same row count.
4. After sorting each table by every column whose Arrow type is not `null`, every column is equal value for value, nulls matching nulls.

Row order is not compared (it is a writer artefact). Parquet schema metadata (the pandas JSON blob) is ignored. Float NaN is read as null on both sides before sorting. **No column is excluded:** the reference `meta.json` differs (it was backfilled and lacks the new keys) but meta is not compared; every events column is a pure function of bars + settings, including `datetime` and `slice`. Two columns can fail for a reason other than the breach rule, and the reason string lists **every** differing column so the diagnosis is immediate: `datetime` is rendered with the machine's local timezone by `event_logger` (the gate must run on this same machine); `slice` comes from `assign_slices`, which sorts with pandas' default quicksort (not stable), so rows sharing a `bar_index` at the 75% cutoff can be labelled differently if the rows arrived in a different order. If `slice` is the only differing column, the events are the same and only their order going into `assign_slices` changed - investigate that, do not wave it through. Measured 2026-10-16 on the reference: 5,326,759 rows x 72 columns, 2.4 GB in Arrow, read 0.6 s, full sort 8 s; the gate holds both tables plus one column at a time, about 6 GB peak (machine has 63 GB).

- [ ] **Step 1: Write the failing tests**

Create `tests/study_tool/mining/test_regression_gate.py`:

```python
"""
The close2 regression gate: does the rebuilt corpus reproduce the old one?
"""
import sys
import os

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.regression_gate import (
    GateResult, check_regression, compare_event_tables,
)


def events():
    return pd.DataFrame({
        "bar_index": [0, 1, 1, 2],
        "event_type": ["LADDER_TOUCH", "LADDER_CROSS", "LADDER_TOUCH",
                       "LADDER_BREACH_CONFIRMED"],
        "level_price": [1306.0, 1306.0, 1308.25, 1306.0],
        "shadow_id": [None, None, 0.0, None],
        "angle_name": [None, None, None, None],     # an Arrow null column
        "outcome": [None, None, None, "x"],
    })


def write(frame, path):
    frame.to_parquet(path, index=False)
    return path


def test_identical_tables_pass(tmp_path):
    result = check_regression(write(events(), tmp_path / "a.parquet"),
                              write(events(), tmp_path / "b.parquet"))

    assert isinstance(result, GateResult)
    assert result.passed is True
    assert "4 rows" in result.reason


def test_row_order_does_not_matter(tmp_path):
    shuffled = events().iloc[[3, 1, 0, 2]].reset_index(drop=True)

    result = check_regression(write(events(), tmp_path / "a.parquet"),
                              write(shuffled, tmp_path / "b.parquet"))

    assert result.passed is True


def test_one_changed_value_fails_and_names_the_column(tmp_path):
    changed = events()
    changed.loc[2, "level_price"] = 1308.5

    result = check_regression(write(events(), tmp_path / "a.parquet"),
                              write(changed, tmp_path / "b.parquet"))

    assert result.passed is False
    assert "'level_price'" in result.reason


def test_every_differing_column_is_named(tmp_path):
    changed = events()
    changed.loc[2, "level_price"] = 1308.5
    changed.loc[3, "outcome"] = "y"

    result = check_regression(write(events(), tmp_path / "a.parquet"),
                              write(changed, tmp_path / "b.parquet"))

    assert result.passed is False
    assert "['level_price', 'outcome']" in result.reason


def test_a_slice_only_difference_still_fails_and_names_slice(tmp_path):
    reference = events().assign(slice=["explore", "explore", "holdout",
                                       "holdout"])
    relabelled = reference.copy()
    relabelled.loc[1, "slice"] = "holdout"

    result = check_regression(write(reference, tmp_path / "a.parquet"),
                              write(relabelled, tmp_path / "b.parquet"))

    assert result.passed is False
    assert "['slice']" in result.reason


def test_an_extra_column_fails(tmp_path):
    extra = events()
    extra["extra"] = 1

    result = check_regression(write(events(), tmp_path / "a.parquet"),
                              write(extra, tmp_path / "b.parquet"))

    assert result.passed is False
    assert "only in rebuilt ['extra']" in result.reason


def test_a_missing_row_fails(tmp_path):
    result = check_regression(write(events(), tmp_path / "a.parquet"),
                              write(events().iloc[:3], tmp_path / "b.parquet"))

    assert result.passed is False
    assert "row count" in result.reason


def test_a_changed_type_fails(tmp_path):
    floats = events()
    floats["bar_index"] = floats["bar_index"].astype(float)

    result = check_regression(write(events(), tmp_path / "a.parquet"),
                              write(floats, tmp_path / "b.parquet"))

    assert result.passed is False
    assert "'bar_index'" in result.reason


def test_schema_metadata_is_ignored(tmp_path):
    bare = pa.Table.from_pandas(events(), preserve_index=False) \
        .replace_schema_metadata(None)
    pq.write_table(bare, tmp_path / "b.parquet")

    result = check_regression(write(events(), tmp_path / "a.parquet"),
                              tmp_path / "b.parquet")

    assert result.passed is True


def test_nan_and_null_compare_equal():
    with_nan = pa.table({"x": pa.array([1.0, float("nan")])})
    with_null = pa.table({"x": pa.array([1.0, None], pa.float64())})

    assert compare_event_tables(with_nan, with_null).passed is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/mining/test_regression_gate.py -v`

Expected: collection ERROR, `ModuleNotFoundError: No module named 'study_tool.mining.regression_gate'`.

- [ ] **Step 3: Implement**

Create `study_tool/mining/regression_gate.py`:

```python
"""
The close2 regression gate.

The breach sweep rebuilds the RELIANCE corpus under the old rule (close, two
closes) before trusting the three new ones. If the rebuild does not
reproduce the existing corpus's events exactly, something other than the
breach rule changed, and no comparison between rules can be read. Nothing is
scored until this passes.

"Exactly" means: the same column names in the same order, the same Arrow
type per column, the same row count, and - after both tables are sorted by
every column - every column equal value for value, nulls matching nulls.
Row order is not compared; it is an artefact of the writer. Schema metadata
is ignored. Float NaN is read as null on both sides.

No column is excluded, and the failure reason lists every differing column.
Two can differ for reasons other than the breach rule: `datetime` is
rendered in the build machine's local timezone, and `slice` comes from
assign_slices, whose unstable quicksort can label rows sharing a bar_index
at the cutoff differently if they arrived in another order. Either one
alone is the diagnosis, not a pass.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Union

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


@dataclass(frozen=True)
class GateResult:
    passed: bool
    reason: str
    rows: int


def _nan_as_null(column: pa.ChunkedArray) -> pa.ChunkedArray:
    if not pa.types.is_floating(column.type):
        return column
    return pc.if_else(pc.is_nan(column), pa.scalar(None, column.type), column)


def _normalised(table: pa.Table) -> pa.Table:
    """Schema metadata dropped, float NaN turned into null."""
    columns = [_nan_as_null(table.column(i)) for i in range(table.num_columns)]
    return pa.Table.from_arrays(columns, schema=table.schema.remove_metadata())


def _sort_keys(schema: pa.Schema) -> List[Tuple[str, str]]:
    # A column of Arrow type null holds no values and cannot be a sort key.
    return [(field.name, "ascending") for field in schema
            if not pa.types.is_null(field.type)]


def compare_event_tables(reference: pa.Table, rebuilt: pa.Table) -> GateResult:
    """Apply the exact-match definition above to two in-memory tables."""
    rows = reference.num_rows
    if reference.column_names != rebuilt.column_names:
        only_ref = sorted(set(reference.column_names) - set(rebuilt.column_names))
        only_new = sorted(set(rebuilt.column_names) - set(reference.column_names))
        detail = ("" if only_ref or only_new
                  else " (same names, different order)")
        return GateResult(
            False, f"columns differ: only in reference {only_ref}, "
                   f"only in rebuilt {only_new}{detail}", rows)

    for ref_field, new_field in zip(reference.schema, rebuilt.schema):
        if ref_field.type != new_field.type:
            return GateResult(
                False, f"column {ref_field.name!r} is {ref_field.type} in the "
                       f"reference but {new_field.type} rebuilt", rows)

    if reference.num_rows != rebuilt.num_rows:
        return GateResult(
            False, f"row count {reference.num_rows} in the reference, "
                   f"{rebuilt.num_rows} rebuilt", rows)

    reference, rebuilt = _normalised(reference), _normalised(rebuilt)
    keys = _sort_keys(reference.schema)
    ref_order = pc.sort_indices(reference, sort_keys=keys)
    new_order = pc.sort_indices(rebuilt, sort_keys=keys)

    differing = [
        name for name in reference.column_names
        if not reference.column(name).take(ref_order).equals(
            rebuilt.column(name).take(new_order))
    ]
    if differing:
        return GateResult(
            False, f"columns {differing} differ after sorting both tables "
                   "by every column", rows)

    return GateResult(
        True, f"{rows} rows match on all {len(reference.column_names)} columns",
        rows)


def check_regression(reference_events: Union[str, Path],
                     rebuilt_events: Union[str, Path]) -> GateResult:
    """Read two events.parquet files and compare them exactly."""
    return compare_event_tables(pq.read_table(reference_events),
                                pq.read_table(rebuilt_events))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/mining/test_regression_gate.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add study_tool/mining/regression_gate.py tests/study_tool/mining/test_regression_gate.py
git commit -m "feat: close2 regression gate on event tables" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Breach rules, the 13 groups, scoring and the selection rule

**Files:**
- Modify: `study_tool/mining/report.py` (`GroupResult.display_label`, lines 43-53)
- Create: `study_tool/mining/breach_sweep.py`
- Create: `tests/study_tool/mining/test_breach_sweep.py`
- Test: `tests/study_tool/mining/test_report.py`

The 13 groups are matched the way the report prints labels (`level_sub_index=5` is the float 5.0, `level_degree=90` the int 90), so the label normaliser moves to a module-level `display_label` that both use.

An eligible rule whose z is undefined (shadow sd 0) cannot be ranked by the pre-registered rule; `select_rule` raises instead of guessing. With 50 shadows of continuous rates this should never happen; if it does, the sweep stops and the user decides.

- [ ] **Step 1: Write the failing tests**

Append to `tests/study_tool/mining/test_report.py`:

```python
def test_display_label_is_available_as_a_function():
    from study_tool.mining.report import display_label

    assert display_label("5.0") == "5"
    assert display_label("10-19") == "10-19"
    assert display_label("center") == "center"
```

Create `tests/study_tool/mining/test_breach_sweep.py`:

```python
"""
The pre-registered pieces of the breach sweep, on hand-made inputs: which
rule wins, which rows each of the 13 groups holds, and what gets scored.
"""
import sys
import os

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.breach_sweep import (
    CONFIRMATION_GROUPS, RULE_ORDER, RULES, RULES_BY_NAME, BreachRule,
    confirmation_groups, group_name, score_rule, select_rule,
)
from study_tool.mining.shadow_compare import Comparison


def test_the_four_rules_in_tie_order():
    assert RULE_ORDER == ("close1", "wick1", "close2", "close3")
    assert RULES_BY_NAME["wick1"] == BreachRule("wick1", "wick", 1)
    assert RULES_BY_NAME["close3"] == BreachRule("close3", "close", 3)
    assert len(RULES) == 4


def test_there_are_thirteen_distinct_confirmation_groups():
    assert len(CONFIRMATION_GROUPS) == 13
    assert len(set(CONFIRMATION_GROUPS)) == 13


def label_frame():
    return pd.DataFrame({
        "shadow_id": [None, None, None],
        "level_source": ["center", "moon", "sun"],
        "level_ring_bin": ["10-19", "20-29", "10-19"],
        "level_kind": ["sub", "major", "sub"],
        "level_is_halfway": [False, False, True],
        "level_degree": [90, 0, 225],
        "level_sub_index": [5.0, None, 4.0],
    })


def test_groups_match_labels_the_way_the_report_prints_them():
    groups = dict(confirmation_groups(label_frame()))

    assert len(groups) == 13
    assert len(groups["level_sub_index=5"]) == 1
    assert len(groups["level_degree=90"]) == 1
    assert len(groups["level_is_halfway=True"]) == 1
    assert len(groups["level_ring_bin=10-19"]) == 2
    assert len(groups["level_degree=135"]) == 0


def test_a_missing_column_gives_an_empty_group_not_an_error():
    groups = dict(confirmation_groups(label_frame().drop(columns="level_ring_bin")))

    assert len(groups["level_ring_bin=10-19"]) == 0


def breach_row(shadow_id, outcome, hit=False, beyond=True):
    return {"event_type": "LADDER_BREACH_CONFIRMED", "bar_index": 0,
            "shadow_id": shadow_id, "reach_outcome": outcome,
            "target_hit_before_entry": hit, "entry_beyond_level": beyond,
            "target_already_hit": hit, "level_source": "center",
            "level_degree": 90, "level_sub_index": 5.0, "level_kind": "sub",
            "level_is_halfway": False, "level_ring_bin": "10-19"}


def scored_events():
    rows = [breach_row(None, "REACHED") for _ in range(3)]
    rows += [breach_row(None, "STOPPED"), breach_row(None, "REACHED", hit=True)]
    for shadow in (0.0, 1.0):
        rows += [breach_row(shadow, "REACHED"), breach_row(shadow, "STOPPED")]
    return pd.DataFrame(rows)


def test_score_rule_reads_pooled_and_group_statistics():
    score = score_rule("close2", scored_events(), shadow_count=2)

    assert score.rule == "close2"
    assert score.lag_free.real == 0.75
    assert score.lag_free.shadows == [0.5, 0.5]
    assert score.lag_free.above_all_shadows is True
    assert score.reach_next.real == 0.8
    assert score.dropped.real == 0.2
    assert score.dropped.outside_range is True
    assert score.entry_dropped.real == 0.0
    assert len(score.groups) == 13
    assert score.groups["level_source=center"].real == 0.75
    assert score.groups["level_source=moon"].real is None
    assert score.groups["level_source=moon"].shadows_missing == 2


def z_comparison(z, missing=0):
    """Shadows -1, 0, 1 have mean 0 and sample sd 1, so real == z."""
    return Comparison(real=z, n=100, shadows=[-1.0, 0.0, 1.0],
                      shadows_missing=missing)


def inside():
    return Comparison(real=0.5, n=100, shadows=[-1.0, 0.0, 1.0])


def test_the_eligible_rule_with_the_largest_z_wins():
    selection = select_rule({"close1": z_comparison(2.0),
                             "wick1": z_comparison(3.0),
                             "close2": z_comparison(2.5),
                             "close3": z_comparison(2.2)})

    assert selection.chosen == "wick1"
    assert selection.candidates == ["wick1"]
    assert selection.eligible == ["close1", "wick1", "close2", "close3"]


def test_a_rule_with_a_missing_shadow_is_not_eligible():
    selection = select_rule({"close1": z_comparison(5.0, missing=1),
                             "close2": z_comparison(2.0)})

    assert selection.chosen == "close2"
    assert selection.eligible == ["close2"]


def test_a_rule_inside_the_shadow_range_is_not_eligible():
    selection = select_rule({"close1": inside(), "close3": z_comparison(2.0)})

    assert selection.eligible == ["close3"]


def test_ties_within_the_window_go_to_the_earliest_rule():
    selection = select_rule({"close1": z_comparison(2.95),
                             "close3": z_comparison(3.0)})

    assert selection.chosen == "close1"
    assert selection.candidates == ["close1", "close3"]


def test_a_z_outside_the_window_is_not_a_candidate():
    selection = select_rule({"close1": z_comparison(2.85),
                             "close3": z_comparison(3.0)})

    assert selection.chosen == "close3"
    assert selection.candidates == ["close3"]


def test_close_comes_before_wick_and_wick_before_close2_in_a_tie():
    assert select_rule({"close1": z_comparison(3.0),
                        "wick1": z_comparison(3.0)}).chosen == "close1"
    assert select_rule({"wick1": z_comparison(2.0),
                        "close2": z_comparison(2.0)}).chosen == "wick1"


def test_no_eligible_rule_is_a_null():
    selection = select_rule({name: inside() for name in RULE_ORDER})

    assert selection.chosen is None
    assert selection.eligible == []
    assert "null" in selection.reason


def test_z_is_reported_for_every_rule():
    selection = select_rule({"close1": inside(), "close2": z_comparison(2.0)})

    assert selection.z == {"close1": pytest.approx(0.5),
                           "close2": pytest.approx(2.0)}


def test_an_unknown_rule_name_is_refused():
    with pytest.raises(ValueError, match="close4"):
        select_rule({"close4": z_comparison(2.0)})


def test_an_eligible_rule_with_undefined_z_is_refused():
    no_spread = Comparison(real=2.0, n=5, shadows=[1.0, 1.0])
    assert no_spread.above_all_shadows and no_spread.z is None

    with pytest.raises(ValueError, match="z is undefined"):
        select_rule({"close1": no_spread})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/mining/test_breach_sweep.py tests/study_tool/mining/test_report.py -v`

Expected: collection ERROR for `test_breach_sweep.py` (`ModuleNotFoundError: No module named 'study_tool.mining.breach_sweep'`) and FAIL for `test_display_label_is_available_as_a_function` (`ImportError: cannot import name 'display_label'`).

- [ ] **Step 3: Move `display_label` to module level in report.py**

In `study_tool/mining/report.py`, insert after `_RANGE = re.compile(r'^(-?\d+)-(-?\d+)$')`:

```python


def display_label(label: str) -> str:
    """
    A group label as a human should read it.

    level_sub_index mixes ints and nulls, which pandas upcasts to float64,
    so iter_groups yields "1.0" rather than "1". This strips that suffix.
    The breach sweep matches its pre-declared groups through this too.
    """
    match = _DOTZERO.match(label)
    return match.group(1) if match else label
```

and replace the body of the `GroupResult.display_label` property

```python
        match = _DOTZERO.match(self.label)
        return match.group(1) if match else self.label
```

with

```python
        return display_label(self.label)
```

- [ ] **Step 4: Implement breach_sweep.py**

Create `study_tool/mining/breach_sweep.py`:

```python
"""
The breach definition sweep, as pure functions.

Spec: docs/superpowers/specs/2026-10-16-gann-breach-definition-sweep-design.md

Everything that decides an outcome - which breach rule is chosen, whether
AAPL passes - is here and takes only events frames or comparisons, so the
pre-registered rules are tested on hand-made inputs before any real corpus
is read.
"""

from dataclasses import dataclass
from typing import Dict, List, Mapping, NamedTuple, Optional, Tuple

import pandas as pd

from study_tool.mining.groups import NULL_LABEL
from study_tool.mining.report import display_label
from study_tool.mining.shadow_compare import Comparison, compare
from study_tool.mining.statistics import (
    already_hit_share, dropped_share, entry_dropped_share,
    lag_free_reach_rate, reach_next_rate, touch_density_fn,
)

SPEC_PATH = ("docs/superpowers/specs/"
             "2026-10-16-gann-breach-definition-sweep-design.md")


class BreachRule(NamedTuple):
    name: str
    breach_mode: str
    confirmation_closes: int


# In tie order: fewer closes first; close before wick because close is the
# house rule.
RULES: Tuple[BreachRule, ...] = (
    BreachRule("close1", "close", 1),
    BreachRule("wick1", "wick", 1),
    BreachRule("close2", "close", 2),
    BreachRule("close3", "close", 3),
)
RULE_ORDER: Tuple[str, ...] = tuple(rule.name for rule in RULES)
RULES_BY_NAME: Dict[str, BreachRule] = {rule.name: rule for rule in RULES}
TIE_WINDOW = 0.1
STRONG_PASS_GROUPS = 7

# Pre-declared for the 2026-09-03 RELIANCE confirmation; kept because they
# were declared in advance, not because they suit the lag-free statistic.
CONFIRMATION_GROUPS: Tuple[Tuple[str, str], ...] = (
    ("level_source", "center"),
    ("level_source", "moon"),
    ("level_source", "sun"),
    ("level_ring_bin", "10-19"),
    ("level_kind", "sub"),
    ("level_kind", "major"),
    ("level_is_halfway", "False"),
    ("level_is_halfway", "True"),
    ("level_degree", "0"),
    ("level_degree", "90"),
    ("level_degree", "135"),
    ("level_degree", "225"),
    ("level_sub_index", "5"),
)


def group_name(column: str, label: str) -> str:
    return f"{column}={label}"


def confirmation_groups(events: pd.DataFrame) -> List[Tuple[str, pd.DataFrame]]:
    """
    (name, rows) for each of the 13 groups, real and shadow rows together.

    Labels are matched the way the report prints them. A group with no rows
    comes back empty rather than missing: compare() then counts every shadow
    missing, and the group cannot be above all shadows.
    """
    labels: Dict[str, pd.Series] = {}
    out: List[Tuple[str, pd.DataFrame]] = []
    for column, label in CONFIRMATION_GROUPS:
        name = group_name(column, label)
        if column not in events.columns:
            out.append((name, events.iloc[0:0]))
            continue
        if column not in labels:
            labels[column] = events[column].map(
                lambda v: NULL_LABEL if pd.isna(v) else display_label(str(v)))
        out.append((name, events[labels[column] == label]))
    return out


@dataclass(frozen=True)
class RuleScore:
    rule: str
    lag_free: Comparison
    dropped: Comparison
    entry_dropped: Comparison
    reach_next: Comparison
    already_hit: Comparison
    touch_density: Comparison
    groups: Dict[str, Comparison]


def score_rule(rule: str, events: pd.DataFrame, shadow_count: int) -> RuleScore:
    """
    Every number the sweep reads for one breach rule, pooled and per group.

    `events` must already carry the reach race and level_ring_bin -
    mine_gann_corpus.load_scored_events supplies both.
    """
    bar_count = int(events["bar_index"].nunique())

    def pooled(statistic) -> Comparison:
        return compare(events, statistic, shadow_count=shadow_count)

    return RuleScore(
        rule=rule,
        lag_free=pooled(lag_free_reach_rate),
        dropped=pooled(dropped_share),
        entry_dropped=pooled(entry_dropped_share),
        reach_next=pooled(reach_next_rate),
        already_hit=pooled(already_hit_share),
        touch_density=pooled(touch_density_fn(bar_count)),
        groups={name: compare(rows, lag_free_reach_rate,
                              shadow_count=shadow_count)
                for name, rows in confirmation_groups(events)},
    )


@dataclass(frozen=True)
class Selection:
    chosen: Optional[str]
    eligible: List[str]
    candidates: List[str]
    z: Dict[str, Optional[float]]
    reason: str


def select_rule(pooled: Mapping[str, Comparison],
                tie_window: float = TIE_WINDOW) -> Selection:
    """
    The pre-registered selection rule, on the pooled lag-free reach rate.

    1. Gate: a rule is eligible only if it is above all shadows.
    2. Choose the eligible rule with the largest z.
    3. Ties: candidates are eligible rules with z >= max z - tie_window;
       take the earliest in RULE_ORDER.
    4. No eligible rule: a null. AAPL is not built.
    """
    unknown = sorted(set(pooled) - set(RULE_ORDER))
    if unknown:
        raise ValueError(f"unknown breach rules {unknown}; expected {RULE_ORDER}")

    present = [name for name in RULE_ORDER if name in pooled]
    z = {name: pooled[name].z for name in present}
    eligible = [name for name in present if pooled[name].above_all_shadows]

    if not eligible:
        return Selection(
            chosen=None, eligible=[], candidates=[], z=z,
            reason="no breach rule is above all shadows on the pooled "
                   "lag-free reach rate; the sweep is null and AAPL is not "
                   "built")

    undefined = [name for name in eligible if z[name] is None]
    if undefined:
        raise ValueError(
            f"z is undefined for eligible rules {undefined} (shadow sd is 0); "
            "the pre-registered rule cannot rank them - stop and report")

    best = max(z[name] for name in eligible)
    candidates = [name for name in eligible if z[name] >= best - tie_window]
    chosen = candidates[0]
    return Selection(
        chosen=chosen, eligible=eligible, candidates=candidates, z=z,
        reason=(f"{chosen} chosen: best z {best:.3f}; candidates within "
                f"{tie_window} of it: {', '.join(candidates)}; the earliest "
                f"in the order {', '.join(RULE_ORDER)} wins"))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/mining -v`

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add study_tool/mining/report.py study_tool/mining/breach_sweep.py tests/study_tool/mining/test_breach_sweep.py tests/study_tool/mining/test_report.py
git commit -m "feat: breach rules, confirmation groups and the selection rule" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: The AAPL verdict and the choice file

**Files:**
- Modify: `study_tool/mining/breach_sweep.py` (append)
- Test: `tests/study_tool/mining/test_breach_sweep.py` (append)

Pre-registered labels: `fail`; `pass` (pooled lag-free rate above all shadows); `strong pass` (pass and at least 7 of the 13 groups above all shadows). If the real dropped share is outside the shadow range, a pass or strong pass gets `, selection differs` appended. A fail stays `fail`.

- [ ] **Step 1: Write the failing tests**

In `tests/study_tool/mining/test_breach_sweep.py` replace the import

```python
from study_tool.mining.breach_sweep import (
    CONFIRMATION_GROUPS, RULE_ORDER, RULES, RULES_BY_NAME, BreachRule,
    confirmation_groups, group_name, score_rule, select_rule,
)
```

with

```python
import json

from study_tool.mining.breach_sweep import (
    CONFIRMATION_GROUPS, RULE_ORDER, RULES, RULES_BY_NAME, BreachRule,
    RuleScore, aapl_verdict, choice_record, confirmation_groups, group_name,
    read_choice, score_rule, select_rule, write_choice,
)
from study_tool.mining.regression_gate import GateResult
```

Append:

```python
def above():
    return Comparison(real=0.9, n=100, shadows=[0.5, 0.6])


def within():
    return Comparison(real=0.55, n=100, shadows=[0.5, 0.6])


def rule_score(lag_free, groups_above=0, dropped=None, touch=None,
               rule="close1"):
    names = [group_name(column, label) for column, label in CONFIRMATION_GROUPS]
    groups = {name: (above() if i < groups_above else within())
              for i, name in enumerate(names)}
    return RuleScore(rule=rule, lag_free=lag_free,
                     dropped=dropped or within(), entry_dropped=within(),
                     reach_next=within(), already_hit=within(),
                     touch_density=touch or within(), groups=groups)


def test_verdict_fail_when_pooled_is_not_above_all_shadows():
    verdict = aapl_verdict(rule_score(within(), groups_above=13))

    assert verdict.label == "fail"
    assert verdict.passed is False
    assert verdict.groups_above == 13


def test_verdict_pass_with_six_groups():
    verdict = aapl_verdict(rule_score(above(), groups_above=6))

    assert verdict.label == "pass"
    assert verdict.strong is False


def test_verdict_strong_pass_with_seven_groups():
    verdict = aapl_verdict(rule_score(above(), groups_above=7))

    assert verdict.label == "strong pass"
    assert verdict.strong is True


def test_a_dropped_share_outside_the_shadows_labels_the_pass():
    assert aapl_verdict(rule_score(above(), dropped=above())).label == \
        "pass, selection differs"
    assert aapl_verdict(rule_score(above(), groups_above=7,
                                   dropped=above())).label == \
        "strong pass, selection differs"


def test_a_fail_stays_a_fail_whatever_the_dropped_share():
    verdict = aapl_verdict(rule_score(within(), dropped=above()))

    assert verdict.label == "fail"
    assert verdict.selection_differs is True


def test_verdict_flags_touch_density_above_every_shadow():
    assert aapl_verdict(rule_score(above(), touch=above())) \
        .touch_busier_than_all_shadows is True
    assert aapl_verdict(rule_score(above())) \
        .touch_busier_than_all_shadows is False


def gate():
    return GateResult(True, "4 rows match on all 6 columns", 4)


def test_the_choice_file_round_trips_the_chosen_rule(tmp_path):
    scores = {name: rule_score(above(), rule=name) for name in RULE_ORDER}
    selection = select_rule({name: s.lag_free for name, s in scores.items()})
    path = tmp_path / "specs" / "choice.json"

    write_choice(path, choice_record(selection, scores, gate()))

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["chosen"] == selection.chosen
    assert record["regression_gate"]["passed"] is True
    assert set(record["rules"]) == set(RULE_ORDER)
    assert read_choice(path) == RULES_BY_NAME[selection.chosen]


def test_a_missing_choice_file_is_refused(tmp_path):
    with pytest.raises(FileNotFoundError, match="AAPL is not built"):
        read_choice(tmp_path / "missing.json")


def test_a_null_choice_is_refused(tmp_path):
    scores = {name: rule_score(within(), rule=name) for name in RULE_ORDER}
    selection = select_rule({name: s.lag_free for name, s in scores.items()})
    path = tmp_path / "choice.json"
    write_choice(path, choice_record(selection, scores, gate()))

    assert json.loads(path.read_text(encoding="utf-8"))["chosen"] is None
    with pytest.raises(ValueError, match="null"):
        read_choice(path)


def test_an_unknown_rule_in_the_choice_file_is_refused(tmp_path):
    path = tmp_path / "choice.json"
    path.write_text(json.dumps({"chosen": "close9"}), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown"):
        read_choice(path)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/mining/test_breach_sweep.py -v`

Expected: collection ERROR, `ImportError: cannot import name 'aapl_verdict'`.

- [ ] **Step 3: Implement**

In `study_tool/mining/breach_sweep.py` replace the import block

```python
from dataclasses import dataclass
from typing import Dict, List, Mapping, NamedTuple, Optional, Tuple

import pandas as pd

from study_tool.mining.groups import NULL_LABEL
```

with

```python
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, NamedTuple, Optional, Tuple, Union

import pandas as pd

from study_tool.mining.groups import NULL_LABEL
from study_tool.mining.regression_gate import GateResult
```

Append at the end of the file:

```python
@dataclass(frozen=True)
class Verdict:
    label: str
    passed: bool
    strong: bool
    groups_above: int
    selection_differs: bool
    touch_busier_than_all_shadows: bool


def aapl_verdict(score: RuleScore) -> Verdict:
    """
    The pre-registered AAPL reading.

    pass: pooled lag-free reach rate above all shadows. strong pass: pass
    and at least STRONG_PASS_GROUPS of the 13 groups above all shadows. If
    the real dropped share is outside the shadow range the filtered sets are
    not like-for-like, and a pass says so in its label.
    """
    passed = score.lag_free.above_all_shadows
    groups_above = sum(1 for c in score.groups.values() if c.above_all_shadows)
    strong = passed and groups_above >= STRONG_PASS_GROUPS
    selection_differs = score.dropped.outside_range

    label = "fail"
    if passed:
        label = "strong pass" if strong else "pass"
        if selection_differs:
            label += ", selection differs"

    return Verdict(label=label, passed=passed, strong=strong,
                   groups_above=groups_above,
                   selection_differs=selection_differs,
                   touch_busier_than_all_shadows=(
                       score.touch_density.above_all_shadows))


def choice_record(selection: Selection, scores: Mapping[str, RuleScore],
                  gate: GateResult) -> Dict:
    """The choice file's contents: the decision and what it rested on."""
    chosen = RULES_BY_NAME[selection.chosen] if selection.chosen else None
    return {
        "spec": SPEC_PATH,
        "chosen": selection.chosen,
        "breach_mode": chosen.breach_mode if chosen else None,
        "confirmation_closes": chosen.confirmation_closes if chosen else None,
        "reason": selection.reason,
        "eligible": list(selection.eligible),
        "candidates": list(selection.candidates),
        "regression_gate": {"passed": gate.passed, "reason": gate.reason},
        "rules": {
            name: {
                "lag_free_real": score.lag_free.real,
                "lag_free_n": score.lag_free.n,
                "shadow_max": score.lag_free.shadow_max,
                "shadows_missing": score.lag_free.shadows_missing,
                "above_all_shadows": score.lag_free.above_all_shadows,
                "z": score.lag_free.z,
            }
            for name, score in scores.items()
        },
    }


def write_choice(path: Union[str, Path], record: Dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def read_choice(path: Union[str, Path]) -> BreachRule:
    """
    The breach rule the RELIANCE sweep chose.

    Raises:
        FileNotFoundError: no choice file - the sweep has not run.
        ValueError: the choice is null (the stop rule keeps AAPL unbuilt) or
            names a rule this code does not know.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found: the RELIANCE sweep has not chosen a breach "
            "rule, so AAPL is not built")
    record = json.loads(path.read_text(encoding="utf-8"))
    chosen = record.get("chosen")
    if chosen is None:
        raise ValueError(
            f"{path} records a null sweep: no breach rule beat every shadow, "
            "and the pre-registered stop rule keeps AAPL unbuilt")
    if chosen not in RULES_BY_NAME:
        raise ValueError(f"{path} names unknown breach rule {chosen!r}")
    return RULES_BY_NAME[chosen]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/mining/test_breach_sweep.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add study_tool/mining/breach_sweep.py tests/study_tool/mining/test_breach_sweep.py
git commit -m "feat: aapl verdict and the breach sweep choice file" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: The two write-ups

**Files:**
- Create: `study_tool/mining/sweep_report.py`
- Create: `tests/study_tool/mining/test_sweep_report.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/study_tool/mining/test_sweep_report.py`:

```python
"""
The RELIANCE results document and the AAPL verdict document, rendered from
numbers only, so what each says for a given outcome is pinned before the run.
"""
import sys
import os

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.breach_sweep import (
    CONFIRMATION_GROUPS, RULE_ORDER, RuleScore, Selection, Verdict, group_name,
)
from study_tool.mining.regression_gate import GateResult
from study_tool.mining.shadow_compare import Comparison
from study_tool.mining.sweep_report import (
    render_aapl_results, render_sweep_results,
)


def comparison(real=0.6):
    return Comparison(real=real, n=100, shadows=[0.5, 0.55])


def rule_score(rule):
    groups = {group_name(c, l): comparison() for c, l in CONFIRMATION_GROUPS}
    return RuleScore(rule=rule, lag_free=comparison(), dropped=comparison(0.3),
                     entry_dropped=comparison(0.0), reach_next=comparison(),
                     already_hit=comparison(), touch_density=comparison(),
                     groups=groups)


def scores():
    return {name: rule_score(name) for name in RULE_ORDER}


def chosen():
    return Selection(chosen="close1", eligible=["close1"],
                     candidates=["close1"], z={n: 2.0 for n in RULE_ORDER},
                     reason="close1 chosen: best z 2.000")


def null():
    return Selection(chosen=None, eligible=[], candidates=[],
                     z={n: 0.1 for n in RULE_ORDER},
                     reason="no breach rule is above all shadows; null")


def sweep_context():
    return {"generated": "2026-10-16 12:00", "cache_dir": "bars",
            "reference": "ref/events.parquet",
            "corpora": {n: f"out/reliance_5m_x1_{n}" for n in RULE_ORDER}}


def gate():
    return GateResult(True, "4 rows match on all 6 columns", 4)


def test_sweep_results_put_the_gate_before_the_selection():
    text = render_sweep_results(scores(), chosen(), gate(), sweep_context())

    assert text.index("## Regression gate") < text.index("## Selection")
    assert "**PASSED**" in text
    assert "Chosen rule: `close1`" in text


def test_a_null_sweep_says_aapl_is_not_built():
    text = render_sweep_results(scores(), null(), gate(), sweep_context())

    assert "AAPL is not built" in text
    assert "Chosen rule" not in text


def test_sweep_results_report_every_rule_and_every_group():
    text = render_sweep_results(scores(), chosen(), gate(), sweep_context())

    for name in RULE_ORDER:
        assert f"### {name}" in text
        assert f"| {name} |" in text
    for column, label in CONFIRMATION_GROUPS:
        assert f"| {group_name(column, label)} |" in text
    for heading in ("## Dropped share", "## Plain reach_next_rate",
                    "## Touch density"):
        assert heading in text


def test_sweep_results_render_the_same_twice():
    first = render_sweep_results(scores(), chosen(), gate(), sweep_context())
    assert first == render_sweep_results(scores(), chosen(), gate(),
                                         sweep_context())


def aapl_context():
    return {"rule": "close1", "breach_mode": "close", "confirmation_closes": 1,
            "choice": "choice.json", "corpus": "out/aapl_5m_x6",
            "price_scale": 6, "shadow_count": 50,
            "rows": 1234, "generated": "2026-10-17 09:00"}


def verdict(label="pass", differs=False, busier=False):
    return Verdict(label=label, passed=label != "fail",
                   strong=label.startswith("strong"), groups_above=3,
                   selection_differs=differs,
                   touch_busier_than_all_shadows=busier)


def test_aapl_results_read_touch_density_first():
    text = render_aapl_results(rule_score("close1"), verdict(), aapl_context())

    assert text.index("## Touch density") < text.index("## Verdict")
    assert "**pass**" in text
    assert "3 of 13" in text
    assert "Full mining report" not in text


def test_aapl_results_flag_a_busier_real_ladder():
    text = render_aapl_results(rule_score("close1"), verdict(busier=True),
                               aapl_context())

    assert "touched more than every shadow" in text


def test_aapl_results_carry_the_dropped_share_caveat():
    text = render_aapl_results(rule_score("close1"),
                               verdict("pass, selection differs", differs=True),
                               aapl_context())

    assert "**pass, selection differs**" in text
    assert "not like-for-like" in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/mining/test_sweep_report.py -v`

Expected: collection ERROR, `ModuleNotFoundError: No module named 'study_tool.mining.sweep_report'`.

- [ ] **Step 3: Implement**

Create `study_tool/mining/sweep_report.py`:

```python
"""
The two write-ups of the breach sweep: the RELIANCE results with the
pre-registered choice, and the one-look AAPL verdict.

Both are rendered from numbers only, so a test pins what each says for a
given outcome - the null, the caveats, the order - before the real run.
"""

from typing import Dict, List, Mapping, Optional, Tuple

from study_tool.mining.breach_sweep import (
    CONFIRMATION_GROUPS, RULE_ORDER, RULES_BY_NAME, SPEC_PATH,
    STRONG_PASS_GROUPS, TIE_WINDOW, RuleScore, Selection, Verdict, group_name,
)
from study_tool.mining.regression_gate import GateResult
from study_tool.mining.shadow_compare import Comparison

COMPARISON_HEAD = ("| {first} | real | n | shadow min | shadow max | missing "
                   "| above all | z |\n|---|---|---|---|---|---|---|---|")


def _num(value: Optional[float], places: int = 4) -> str:
    """None renders as a dash; 0.0000 would read as a measured zero."""
    return "-" if value is None else f"{value:.{places}f}"


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"


def _comparison_table(first: str,
                      rows: List[Tuple[str, Comparison]]) -> List[str]:
    lines = [COMPARISON_HEAD.format(first=first)]
    for label, c in rows:
        lines.append(
            f"| {label} | {_num(c.real)} | {c.n} | {_num(c.shadow_min)} | "
            f"{_num(c.shadow_max)} | {c.shadows_missing} | "
            f"{_yes(c.above_all_shadows)} | {_num(c.z, 2)} |")
    return lines


def _dropped_table(scores: List[RuleScore]) -> List[str]:
    lines = ["| rule | real dropped | targeted n (raced, timeouts included) "
             "| shadow min | shadow max | outside shadow range "
             "| entry-only dropped (real) |",
             "|---|---|---|---|---|---|---|"]
    for s in scores:
        d = s.dropped
        lines.append(
            f"| {s.rule} | {_num(d.real)} | {d.n} | {_num(d.shadow_min)} | "
            f"{_num(d.shadow_max)} | {_yes(d.outside_range)} | "
            f"{_num(s.entry_dropped.real)} |")
    return lines


def _groups_table(score: RuleScore) -> List[str]:
    names = [group_name(c, l) for c, l in CONFIRMATION_GROUPS]
    return _comparison_table(
        "group", [(name, score.groups[name]) for name in names
                  if name in score.groups])


def render_sweep_results(scores: Mapping[str, RuleScore],
                         selection: Selection, gate: GateResult,
                         context: Dict) -> str:
    ordered = [scores[name] for name in RULE_ORDER if name in scores]
    lines = [
        "# Gann Breach Definition Sweep - Results",
        "",
        f"Spec: `{SPEC_PATH}`.",
        "RELIANCE is explore-only (its holdout was spent 2026-09-03), so "
        "every row of each corpus is read (`--slice all`). Nothing here is "
        "confirmed; AAPL is the confirmation.",
        "",
        "## Run",
        "",
        f"- generated: {context['generated']}",
        f"- bars: `{context['cache_dir']}` (no fetching)",
        f"- gate reference: `{context['reference']}`",
    ]
    for name in RULE_ORDER:
        if name in context["corpora"]:
            lines.append(f"- {name}: `{context['corpora'][name]}`")

    lines += [
        "",
        "## Regression gate - close2 rebuild against the existing corpus",
        "",
        f"**{'PASSED' if gate.passed else 'FAILED'}** - {gate.reason}",
        "",
        "## Selection (pre-registered)",
        "",
    ]
    if selection.chosen is None:
        lines.append("**Null: no breach rule is above all shadows on the "
                     "pooled lag-free reach rate. AAPL is not built.**")
    else:
        rule = RULES_BY_NAME[selection.chosen]
        lines.append(f"**Chosen rule: `{rule.name}`** (breach_mode "
                     f"{rule.breach_mode}, confirmation_closes "
                     f"{rule.confirmation_closes})")
    lines += [
        "",
        selection.reason,
        "",
        f"- eligible (above all shadows): "
        f"{', '.join(selection.eligible) or 'none'}",
        f"- tie candidates (z within {TIE_WINDOW} of the best): "
        f"{', '.join(selection.candidates) or 'none'}",
        "",
        "Pooled lag-free reach rate, real against the shadows:",
        "",
    ]
    lines += _comparison_table("rule", [(s.rule, s.lag_free) for s in ordered])

    lines += [
        "",
        "## Dropped share - real against shadow",
        "",
        "Rows removed by either lag-free filter over targeted rows. If the "
        "real share is outside the shadow range, the filtered real and "
        "shadow sets are not like-for-like, and a pass on them reads as "
        "\"pass, selection differs\".",
        "",
    ]
    lines += _dropped_table(ordered)

    lines += ["", "## Plain reach_next_rate (the old, lag-laden statistic, "
              "for reading)", ""]
    lines += _comparison_table("rule", [(s.rule, s.reach_next) for s in ordered])

    lines += ["", "## Touch density - the fairness check", ""]
    lines += _comparison_table("rule",
                               [(s.rule, s.touch_density) for s in ordered])

    lines += ["", "## The 13 pre-declared groups, lag-free reach rate", ""]
    for s in ordered:
        lines += [f"### {s.rule}", ""]
        lines += _groups_table(s)
        lines.append("")
    return "\n".join(lines)


def render_aapl_results(score: RuleScore, verdict: Verdict,
                        context: Dict) -> str:
    lag, dropped = score.lag_free, score.dropped
    lines = [
        "# Gann AAPL Fresh Holdout - Results",
        "",
        f"Spec: `{SPEC_PATH}`. Read once.",
        f"Rule `{context['rule']}` (breach_mode {context['breach_mode']}, "
        f"confirmation_closes {context['confirmation_closes']}) from "
        f"`{context['choice']}`. Scale x{context['price_scale']}, "
        f"{context['shadow_count']} shadows, every row (`--slice all`, "
        f"{context['rows']} rows).",
        "",
        "## Touch density - read first",
        "",
    ]
    lines += _comparison_table("statistic",
                               [("touch_density", score.touch_density)])
    lines.append("")
    if verdict.touch_busier_than_all_shadows:
        lines.append("**The real ladder is touched more than every shadow.** "
                     "A reach statistic can be lifted by that exposure rather "
                     "than by the levels; read the verdict beside it.")
    else:
        lines.append("Real touch density is not above every shadow.")

    caveat = ("; outside the shadow range, so the filtered real and shadow "
              "sets are not like-for-like" if verdict.selection_differs
              else "; inside the shadow range")
    lines += [
        "",
        "## Verdict (pre-registered)",
        "",
        f"**{verdict.label}**",
        "",
        f"- pooled lag-free reach rate: real {_num(lag.real)} (n={lag.n}), "
        f"shadow max {_num(lag.shadow_max)}, missing shadows "
        f"{lag.shadows_missing}, z {_num(lag.z, 2)}",
        f"- groups above all shadows: {verdict.groups_above} of "
        f"{len(CONFIRMATION_GROUPS)} (strong pass needs {STRONG_PASS_GROUPS})",
        f"- dropped share: real {_num(dropped.real)} against shadows "
        f"{_num(dropped.shadow_min)} to {_num(dropped.shadow_max)}{caveat}",
        f"- entry-only dropped share (real): {_num(score.entry_dropped.real)}",
        "",
        "## Pooled",
        "",
    ]
    lines += _comparison_table("statistic", [
        ("lag_free_reach_rate", score.lag_free),
        ("reach_next_rate", score.reach_next),
        ("already_hit_share", score.already_hit),
        ("dropped_share", score.dropped),
        ("entry_dropped_share", score.entry_dropped),
    ])
    lines += [
        "",
        "## The 13 pre-declared groups, lag-free reach rate",
        "",
        "Declared for the 2026-09-03 RELIANCE confirmation. At x6, "
        "ring_bin=10-19 covers AAPL only below about $253.5, so the pooled "
        "test is the primary one. A group with no rows or any missing shadow "
        "is not above all shadows.",
        "",
    ]
    lines += _groups_table(score)
    lines += [
        "",
        "Nothing else was computed on AAPL: no other statistic or grouping "
        "was read, so the holdout is spent on exactly the tests above.",
        f"Corpus: `{context['corpus']}`",
        f"Generated: {context['generated']}",
        "",
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/mining/test_sweep_report.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add study_tool/mining/sweep_report.py tests/study_tool/mining/test_sweep_report.py
git commit -m "feat: breach sweep and aapl holdout write-ups" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: The RELIANCE sweep runner

**Files:**
- Create: `scripts/run_breach_sweep.py`
- Create: `tests/study_tool/test_run_breach_sweep.py`

close2 is always built first and gated immediately, so a failing gate stops the run before three more hour-long builds. `--rules X --build-only` builds a subset and stops, so the slow builds can run as parallel processes; a later full run reuses them (`ensure_corpus`) and re-runs the gate before scoring.

- [ ] **Step 1: Write the failing tests**

Create `tests/study_tool/test_run_breach_sweep.py`:

```python
"""
The sweep runner, end to end on a tiny cached bar set. No network: every
build passes no_fetch, and the cache is written by the test.
"""
import sys
import os
import json

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend/scripts'))

import build_gann_corpus
import run_breach_sweep as sweep
from build_gann_corpus import build_to_disk
from study_tool.bar_cache import cache_path
from study_tool.mining.breach_sweep import (
    RULE_ORDER, RULES_BY_NAME, Selection, read_choice,
)

FROM, TO = "2026-08-01", "2026-08-31"
SHADOWS = 5


def write_cache(tmp_path):
    epoch = 1787629500
    rows = []
    for i in range(400):
        open_ = 1300.0 + (i % 40) * 0.6
        close = open_ + 0.5
        rows.append({"open": open_, "high": close + 0.4, "low": open_ - 0.4,
                     "close": close, "volume": 1000.0,
                     "timestamp": float(epoch + i * 300),
                     "sun_degree": 155.0 + i * 0.0007,
                     "moon_degree": (331.0 + i * 0.009) % 360})
    cache = tmp_path / "bars"
    cache.mkdir()
    pd.DataFrame(rows).to_parquet(
        cache_path(cache, "RELIANCE", FROM, TO, "5"), index=False)
    return cache


def write_reference(tmp_path, cache, seed=7, shadows=SHADOWS):
    out = tmp_path / f"reference_seed{seed}_shadows{shadows}"
    build_to_disk(symbol="RELIANCE", from_date=FROM, to_date=TO, interval="5",
                  price_scale=1, shadow_count=shadows, seed=seed,
                  cache_dir=cache, out_dir=out, allow_fetch=False)
    return out / "events.parquet"


def paths(tmp_path):
    return {"out_root": tmp_path / "sweep",
            "choice_path": tmp_path / "docs" / "choice.json",
            "results_path": tmp_path / "docs" / "results.md"}


def run(tmp_path, cache, reference, **overrides):
    kwargs = dict(cache_dir=cache, reference=reference, from_date=FROM,
                  to_date=TO, shadows=SHADOWS, **paths(tmp_path))
    kwargs.update(overrides)
    return sweep.run_sweep(**kwargs)


def test_a_sweep_with_no_shadows_is_a_pinned_null(tmp_path):
    """
    The whole pipeline, with an outcome known in advance: with zero shadows
    no rule can be above all shadows, so the pre-registered rule must return
    a null and the choice file must say so.
    """
    cache = write_cache(tmp_path)
    reference = write_reference(tmp_path, cache, shadows=0)
    p = paths(tmp_path)

    selection = run(tmp_path, cache, reference, shadows=0)

    assert selection.chosen is None
    assert selection.eligible == []
    record = json.loads(p["choice_path"].read_text(encoding="utf-8"))
    assert record["chosen"] is None
    assert record["breach_mode"] is None
    assert record["regression_gate"]["passed"] is True
    assert set(record["rules"]) == set(RULE_ORDER)
    text = p["results_path"].read_text(encoding="utf-8")
    assert "**PASSED**" in text
    assert "AAPL is not built" in text
    with pytest.raises(ValueError, match="null"):
        read_choice(p["choice_path"])


def test_a_chosen_rule_reaches_the_choice_file_and_the_report(tmp_path,
                                                              monkeypatch):
    """
    Real builds, real gate and real scoring on five shadows; only the
    selection is forced, so the chosen-rule path is checked end to end.
    """
    cache = write_cache(tmp_path)
    reference = write_reference(tmp_path, cache)
    p = paths(tmp_path)
    seen = {}

    def forced(pooled, tie_window=0.1):
        seen["rules"] = sorted(pooled)
        return Selection(chosen="wick1", eligible=["wick1"],
                         candidates=["wick1"],
                         z={name: c.z for name, c in pooled.items()},
                         reason="forced by the test")

    monkeypatch.setattr(sweep, "select_rule", forced)

    selection = run(tmp_path, cache, reference)

    assert selection.chosen == "wick1"
    assert seen["rules"] == sorted(RULE_ORDER)
    record = json.loads(p["choice_path"].read_text(encoding="utf-8"))
    assert (record["chosen"], record["breach_mode"],
            record["confirmation_closes"]) == ("wick1", "wick", 1)
    assert read_choice(p["choice_path"]) == RULES_BY_NAME["wick1"]
    assert "Chosen rule: `wick1`" in         p["results_path"].read_text(encoding="utf-8")
    for name in RULE_ORDER:
        meta = json.loads(
            (sweep.corpus_dir_for(p["out_root"], name) / "meta.json").read_text())
        rule = RULES_BY_NAME[name]
        assert (meta["breach_mode"], meta["confirmation_closes"]) ==             (rule.breach_mode, rule.confirmation_closes)

    # A second run reuses every corpus instead of rebuilding.
    def boom(*args, **kwargs):
        raise AssertionError("a finished corpus was rebuilt")

    monkeypatch.setattr(build_gann_corpus, "build_corpus", boom)
    assert run(tmp_path, cache, reference).chosen == "wick1"


def test_peak_memory_is_reported_on_windows():
    peak = sweep.peak_memory_gb()
    if sys.platform == "win32":
        assert peak is not None and peak > 0
    else:
        assert peak is None


def test_a_failing_gate_stops_before_any_other_build_or_score(tmp_path):
    cache = write_cache(tmp_path)
    reference = write_reference(tmp_path, cache, seed=8)   # other shadows
    p = paths(tmp_path)

    with pytest.raises(sweep.RegressionGateError, match="close2"):
        run(tmp_path, cache, reference)

    assert not p["choice_path"].exists()
    assert not p["results_path"].exists()
    assert not sweep.corpus_dir_for(p["out_root"], "close1").exists()


def test_main_exits_2_on_a_failing_gate(tmp_path):
    cache = write_cache(tmp_path)
    reference = write_reference(tmp_path, cache, seed=8)
    p = paths(tmp_path)

    code = sweep.main(["--cache", str(cache), "--reference", str(reference),
                       "--out-root", str(p["out_root"]),
                       "--choice", str(p["choice_path"]),
                       "--results", str(p["results_path"]),
                       "--from", FROM, "--to", TO,
                       "--shadows", str(SHADOWS)])

    assert code == 2
    assert not p["choice_path"].exists()


def test_build_only_builds_just_the_named_rules(tmp_path):
    cache = write_cache(tmp_path)
    p = paths(tmp_path)

    result = run(tmp_path, cache, tmp_path / "unused.parquet",
                 rules=("close1",), build_only=True)

    assert result is None
    assert (sweep.corpus_dir_for(p["out_root"], "close1") / "meta.json").exists()
    assert not sweep.corpus_dir_for(p["out_root"], "close2").exists()
    assert not p["choice_path"].exists()


def test_scoring_needs_all_four_rules(tmp_path):
    with pytest.raises(ValueError, match="all four"):
        run(tmp_path, tmp_path / "bars", tmp_path / "unused.parquet",
            rules=("close1",))


def test_an_unknown_rule_is_refused(tmp_path):
    with pytest.raises(ValueError, match="close9"):
        run(tmp_path, tmp_path / "bars", tmp_path / "unused.parquet",
            rules=("close9",), build_only=True)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/test_run_breach_sweep.py -v`

Expected: collection ERROR, `ModuleNotFoundError: No module named 'run_breach_sweep'`.

- [ ] **Step 3: Implement**

Create `scripts/run_breach_sweep.py`:

```python
"""
The RELIANCE breach definition sweep.

Builds four corpora (close1, wick1, close2, close3) from the cached bars -
never fetching - checks the close2 rebuild against the existing corpus,
scores every rule on every row, applies the pre-registered selection rule,
and writes the choice file and the results document.

Spec: docs/superpowers/specs/2026-10-16-gann-breach-definition-sweep-design.md

Usage (from gann-visualizer/backend/):
    python scripts/run_breach_sweep.py \
        --cache C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/bars \
        --reference C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/reliance_5m_x1/events.parquet \
        --out-root C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/breach_sweep \
        --choice <repo>/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json \
        --results <repo>/docs/superpowers/specs/2026-10-16-gann-breach-sweep-results.md

`--rules close1 --build-only` builds one corpus and stops, so the slow builds
can run as parallel processes. Corpora already on disk under the same
settings are reused. close2 is always built first and gated at once.
--from, --to and --shadows exist for tests; the sweep uses the defaults.
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from build_gann_corpus import ensure_corpus
from mine_gann_corpus import load_scored_events
from study_tool.corpus_writer import ALL_SLICES
from study_tool.mining.breach_sweep import (
    RULE_ORDER, RULES_BY_NAME, RuleScore, Selection, choice_record,
    score_rule, select_rule, write_choice,
)
from study_tool.mining.regression_gate import GateResult, check_regression
from study_tool.mining.sweep_report import render_sweep_results

SYMBOL = "RELIANCE"
FROM_DATE = "2024-09-02"
TO_DATE = "2026-09-01"
INTERVAL = "5"
SCALE = 1
SHADOWS = 50
SEED = 7
GATE_RULE = "close2"

PathLike = Union[str, Path]


class RegressionGateError(RuntimeError):
    """The close2 rebuild does not reproduce the existing corpus."""


def peak_memory_gb() -> Optional[float]:
    """
    This process's peak working set in GB, or None off Windows.

    Printed after every build so the RUN task can decide whether the other
    three builds fit in memory side by side. ctypes rather than psutil,
    which is not installed.
    """
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32")
    psapi = ctypes.WinDLL("psapi")
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(),
                                      ctypes.byref(counters), counters.cb):
        return None
    return counters.PeakWorkingSetSize / 1e9


def _print_peak_memory() -> None:
    peak = peak_memory_gb()
    if peak is not None:
        print(f"peak memory so far: {peak:.1f} GB")


def corpus_dir_for(out_root: PathLike, rule: str) -> Path:
    return Path(out_root) / f"reliance_5m_x1_{rule}"


def build_rule(rule: str, out_root: PathLike, cache_dir: PathLike,
               from_date: str = FROM_DATE, to_date: str = TO_DATE,
               shadows: int = SHADOWS) -> str:
    """Build (or reuse) one rule's corpus. Never fetches."""
    spec = RULES_BY_NAME[rule]
    return ensure_corpus(
        symbol=SYMBOL, from_date=from_date, to_date=to_date,
        interval=INTERVAL, price_scale=SCALE, shadow_count=shadows,
        seed=SEED, cache_dir=cache_dir,
        out_dir=corpus_dir_for(out_root, rule),
        breach_mode=spec.breach_mode,
        confirmation_closes=spec.confirmation_closes)


def run_gate(out_root: PathLike, reference: PathLike) -> GateResult:
    result = check_regression(
        reference, corpus_dir_for(out_root, GATE_RULE) / "events.parquet")
    print(f"regression gate: {'PASSED' if result.passed else 'FAILED'} - "
          f"{result.reason}")
    if not result.passed:
        raise RegressionGateError(
            f"close2 rebuild does not match {reference}: {result.reason}. "
            "Stop and find out why before scoring anything.")
    return result


def run_sweep(out_root: PathLike, cache_dir: PathLike, reference: PathLike,
              choice_path: PathLike, results_path: PathLike,
              rules: Sequence[str] = RULE_ORDER, build_only: bool = False,
              from_date: str = FROM_DATE, to_date: str = TO_DATE,
              shadows: int = SHADOWS) -> Optional[Selection]:
    """
    Build, gate, score, select. Returns the Selection, or None when
    build_only. Raises RegressionGateError if close2 does not reproduce the
    reference; nothing is scored or written in that case.
    """
    unknown = [rule for rule in rules if rule not in RULES_BY_NAME]
    if unknown:
        raise ValueError(f"unknown breach rules {unknown}; expected {RULE_ORDER}")
    if not build_only and set(rules) != set(RULE_ORDER):
        raise ValueError(
            "scoring needs all four rules; pass build_only to build a subset")

    # close2 first, so a failing gate stops the run before the other builds.
    ordered = sorted(rules, key=lambda r: (r != GATE_RULE, RULE_ORDER.index(r)))
    gate: Optional[GateResult] = None
    for rule in ordered:
        started = time.time()
        status = build_rule(rule, out_root, cache_dir, from_date, to_date,
                            shadows)
        print(f"{rule}: {status} in {time.time() - started:.0f}s")
        _print_peak_memory()
        if rule == GATE_RULE:
            gate = run_gate(out_root, reference)

    if build_only:
        return None

    scores: Dict[str, RuleScore] = {}
    for rule in RULE_ORDER:
        started = time.time()
        scored = load_scored_events(corpus_dir_for(out_root, rule),
                                    slice_name=ALL_SLICES)
        scores[rule] = score_rule(rule, scored.events, scored.meta.shadow_count)
        del scored
        print(f"{rule}: scored in {time.time() - started:.0f}s")

    selection = select_rule({name: s.lag_free for name, s in scores.items()})
    write_choice(choice_path, choice_record(selection, scores, gate))

    context = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "cache_dir": str(cache_dir),
        "reference": str(reference),
        "corpora": {rule: str(corpus_dir_for(out_root, rule))
                    for rule in RULE_ORDER},
    }
    results_path = Path(results_path)
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(
        render_sweep_results(scores, selection, gate, context),
        encoding="utf-8")

    print(f"chosen: {selection.chosen or 'null - AAPL is not built'}")
    print(f"wrote {choice_path}\nwrote {results_path}")
    return selection


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--choice", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--rules", default=",".join(RULE_ORDER))
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--from", dest="from_date", default=FROM_DATE)
    parser.add_argument("--to", dest="to_date", default=TO_DATE)
    parser.add_argument("--shadows", type=int, default=SHADOWS)
    args = parser.parse_args(argv)

    rules = tuple(r.strip() for r in args.rules.split(",") if r.strip())
    try:
        run_sweep(out_root=args.out_root, cache_dir=args.cache,
                  reference=args.reference, choice_path=args.choice,
                  results_path=args.results, rules=rules,
                  build_only=args.build_only, from_date=args.from_date,
                  to_date=args.to_date, shadows=args.shadows)
    except RegressionGateError as exc:
        print(f"STOPPED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/test_run_breach_sweep.py -v`

Expected: all PASS (about 20-40 s; it builds several tiny corpora). The ctypes probe in `peak_memory_gb` was checked on this machine on 2026-10-16 (returned the process's peak working set).

- [ ] **Step 5: Commit**

```bash
git add scripts/run_breach_sweep.py tests/study_tool/test_run_breach_sweep.py
git commit -m "feat: breach sweep runner with the close2 regression gate" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 16: The AAPL commands - bar loader and holdout, with one-look guards

**Files:**
- Create: `scripts/load_aapl_bars.py`
- Create: `tests/study_tool/test_load_aapl_bars.py`
- Create: `scripts/run_aapl_holdout.py`
- Create: `tests/study_tool/test_run_aapl_holdout.py`

Guards, all tested:
- `load_aapl_bars.py` takes a required `--choice` and calls `read_choice` first: no AAPL bars are built until the RELIANCE choice exists and names a rule.
- `run_aapl` refuses: a missing or null choice; an existing results file; an existing `<results>.started` marker; an existing AAPL corpus directory (`ensure_corpus` must return `"built"` - a hand-built corpus is never silently reused).
- `run_aapl` writes `<results>.started` after the build and **before** `load_scored_events`, so a crash during scoring still counts as the look.
- `run_aapl` computes and writes only what the spec names - touch density first, pooled lag-free reach rate, the 13 groups, dropped share (+ entry-only), the verdict. It never renders `render_mining_report` on AAPL: that would run about 66 other statistic x grouping comparisons on the holdout.

Whether the choice file is **committed** is checked by hand in Task 19.

- [ ] **Step 1: Write the failing loader tests**

Create `tests/study_tool/test_load_aapl_bars.py`:

```python
"""
The AAPL bar loader command refuses to run before the RELIANCE sweep has
chosen a breach rule.
"""
import sys
import os
import json

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend/scripts'))

import load_aapl_bars

CACHE_NAME = "AAPL_5_2024-09-02_2026-09-01.parquet"


def minutes(date, start_hm, count, base):
    start = int(pd.Timestamp(f"{date} {start_hm}",
                             tz="America/New_York").timestamp())
    return [{"time": start + 60 * i, "open": base + i,
             "high": base + i + 0.5, "low": base + i - 0.5,
             "close": base + i + 0.25, "volume": 10.0 + i}
            for i in range(count)]


def write_json(tmp_path):
    path = tmp_path / "aapl.json"
    path.write_text(json.dumps({
        "symbol": "AAPL", "source": "test",
        "candles": (minutes("2024-08-30", "15:58", 2, 228.0)
                    + minutes("2024-09-03", "09:30", 10, 230.0))}))
    return path


def write_choice(tmp_path, chosen):
    path = tmp_path / "choice.json"
    path.write_text(json.dumps({"chosen": chosen}), encoding="utf-8")
    return path


def test_refuses_without_a_choice_file(tmp_path):
    cache = tmp_path / "bars"

    with pytest.raises(FileNotFoundError, match="AAPL is not built"):
        load_aapl_bars.main(["--choice", str(tmp_path / "missing.json"),
                             "--json", str(write_json(tmp_path)),
                             "--cache", str(cache)])

    assert not (cache / CACHE_NAME).exists()


def test_refuses_a_null_choice(tmp_path):
    cache = tmp_path / "bars"

    with pytest.raises(ValueError, match="null"):
        load_aapl_bars.main(["--choice", str(write_choice(tmp_path, None)),
                             "--json", str(write_json(tmp_path)),
                             "--cache", str(cache)])

    assert not (cache / CACHE_NAME).exists()


def test_writes_the_cache_and_prints_the_checks(tmp_path, capsys):
    cache = tmp_path / "bars"

    load_aapl_bars.main(["--choice", str(write_choice(tmp_path, "close1")),
                         "--json", str(write_json(tmp_path)),
                         "--cache", str(cache)])

    out = capsys.readouterr().out
    assert "breach rule close1 is chosen" in out
    assert "2 bars over 1 sessions 2024-09-02..2026-09-01" in out
    assert "2024-08-30 close: 229.25" in out
    assert "last close before 2024-09-02: 229.25 on 2024-08-30" in out
    assert (cache / CACHE_NAME).exists()
```

- [ ] **Step 2: Write the failing holdout tests**

Create `tests/study_tool/test_run_aapl_holdout.py`:

```python
"""
The AAPL command: refuses without a non-null choice, refuses anything that
looks like a second look, builds one corpus under the chosen rule, reads it
whole once, and writes only the spec's statistics and the verdict.
"""
import sys
import os
import json

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend/scripts'))

import mine_gann_corpus
import run_aapl_holdout as holdout
from study_tool.bar_cache import cache_path

FROM, TO = "2026-08-01", "2026-08-31"
SHADOWS = 5
VALID_LABELS = {"fail", "pass", "strong pass", "pass, selection differs",
                "strong pass, selection differs"}


def write_cache(tmp_path):
    epoch = 1787629500
    rows = []
    for i in range(400):
        open_ = 228.0 + (i % 40) * 0.1
        close = open_ + 0.08
        rows.append({"open": open_, "high": close + 0.06, "low": open_ - 0.06,
                     "close": close, "volume": 1000.0,
                     "timestamp": float(epoch + i * 300),
                     "sun_degree": 155.0 + i * 0.0007,
                     "moon_degree": (331.0 + i * 0.009) % 360})
    cache = tmp_path / "bars"
    cache.mkdir()
    pd.DataFrame(rows).to_parquet(
        cache_path(cache, "AAPL", FROM, TO, "5"), index=False)
    return cache


def write_choice_file(tmp_path, chosen):
    path = tmp_path / "choice.json"
    path.write_text(json.dumps({"chosen": chosen}), encoding="utf-8")
    return path


def kwargs(tmp_path, choice, cache):
    return dict(choice_path=choice, cache_dir=cache,
                out_dir=tmp_path / "aapl_5m_x6",
                results_path=tmp_path / "docs" / "aapl.md",
                from_date=FROM, to_date=TO, shadows=SHADOWS)


def marker(args):
    return holdout.started_marker(args["results_path"])


def test_refuses_without_a_choice_file(tmp_path):
    args = kwargs(tmp_path, tmp_path / "missing.json", write_cache(tmp_path))

    with pytest.raises(FileNotFoundError, match="AAPL is not built"):
        holdout.run_aapl(**args)

    assert not args["out_dir"].exists()
    assert not marker(args).exists()


def test_refuses_a_null_choice(tmp_path):
    args = kwargs(tmp_path, write_choice_file(tmp_path, None),
                  write_cache(tmp_path))

    with pytest.raises(ValueError, match="null"):
        holdout.run_aapl(**args)

    assert not args["out_dir"].exists()


def test_main_returns_1_and_builds_nothing_without_a_choice(tmp_path):
    cache = write_cache(tmp_path)

    code = holdout.main(["--choice", str(tmp_path / "missing.json"),
                         "--cache", str(cache),
                         "--out", str(tmp_path / "aapl_5m_x6"),
                         "--results", str(tmp_path / "aapl.md")])

    assert code == 1
    assert not (tmp_path / "aapl_5m_x6").exists()


def test_refuses_an_existing_aapl_corpus_directory(tmp_path):
    args = kwargs(tmp_path, write_choice_file(tmp_path, "close1"),
                  write_cache(tmp_path))
    args["out_dir"].mkdir()

    with pytest.raises(FileExistsError, match="already exists"):
        holdout.run_aapl(**args)

    assert not marker(args).exists()


def test_refuses_when_ensure_corpus_did_not_build(tmp_path, monkeypatch):
    args = kwargs(tmp_path, write_choice_file(tmp_path, "close1"),
                  write_cache(tmp_path))
    monkeypatch.setattr(holdout, "ensure_corpus", lambda **_: "reused")

    with pytest.raises(RuntimeError, match="reused"):
        holdout.run_aapl(**args)

    assert not marker(args).exists()


def test_the_marker_is_written_before_scoring_and_blocks_a_retry(tmp_path,
                                                                  monkeypatch):
    args = kwargs(tmp_path, write_choice_file(tmp_path, "close1"),
                  write_cache(tmp_path))

    def crash(*_, **__):
        assert marker(args).exists(), "scoring started before the marker"
        raise RuntimeError("scoring crashed")

    monkeypatch.setattr(holdout, "load_scored_events", crash)
    with pytest.raises(RuntimeError, match="scoring crashed"):
        holdout.run_aapl(**args)

    monkeypatch.undo()
    with pytest.raises(FileExistsError, match="started"):
        holdout.run_aapl(**args)


def test_builds_under_the_chosen_rule_and_writes_only_the_spec_statistics(
        tmp_path, monkeypatch):
    def no_report(*_, **__):
        raise AssertionError("the full mining report was rendered on AAPL")

    monkeypatch.setattr(mine_gann_corpus, "render_mining_report", no_report)
    args = kwargs(tmp_path, write_choice_file(tmp_path, "close1"),
                  write_cache(tmp_path))

    verdict = holdout.run_aapl(**args)

    assert verdict.label in VALID_LABELS
    assert not hasattr(holdout, "render_mining_report")
    meta = json.loads((args["out_dir"] / "meta.json").read_text())
    assert meta["symbol"] == "AAPL"
    assert meta["price_scale"] == 6
    assert meta["shadow_count"] == SHADOWS
    assert meta["seed"] == 7
    assert (meta["breach_mode"], meta["confirmation_closes"]) == ("close", 1)
    assert marker(args).exists()
    text = args["results_path"].read_text(encoding="utf-8")
    assert text.index("## Touch density") < text.index("## Verdict")
    assert f"**{verdict.label}**" in text
    assert "hold_rate" not in text
    assert list(tmp_path.rglob("gann-mining-report-*.md")) == []


def test_a_second_look_is_refused(tmp_path):
    args = kwargs(tmp_path, write_choice_file(tmp_path, "close2"),
                  write_cache(tmp_path))
    holdout.run_aapl(**args)

    with pytest.raises(FileExistsError, match="one look"):
        holdout.run_aapl(**args)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/test_load_aapl_bars.py tests/study_tool/test_run_aapl_holdout.py -v`

Expected: collection ERRORs, `ModuleNotFoundError: No module named 'load_aapl_bars'` and `No module named 'run_aapl_holdout'`.

- [ ] **Step 4: Implement the loader command**

Create `scripts/load_aapl_bars.py`:

```python
"""
Resample the AAPL 1-minute RTH JSON into the 5-minute bar cache.

Refuses to run until the RELIANCE breach sweep has written a choice file
that names a rule: AAPL bars are not built before the rule is fixed.

Usage (from gann-visualizer/backend/):
    python scripts/load_aapl_bars.py \
        --choice <repo>/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json \
        --json C:/Dev/GannTesting/data_local/aapl_rth_1m.json \
        --cache C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/bars

Prints the bar and session count, the extended-hours minutes dropped on
early-close days, the 2024-08-30 close (to check against the published
close in the write-up) and the last close before the window (which fixes
the x6 scale).
"""

import argparse
import os
import sys
from typing import List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from study_tool.aapl_bars import (
    last_close_before, read_minute_json, resample_to_5m, session_close,
    write_bar_cache,
)
from study_tool.bar_cache import cache_path
from study_tool.mining.breach_sweep import read_choice

AAPL_SCALE = 6


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--choice", required=True)
    parser.add_argument("--json", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--from", dest="from_date", default="2024-09-02")
    parser.add_argument("--to", dest="to_date", default="2026-09-01")
    parser.add_argument("--interval", default="5")
    parser.add_argument("--check-date", default="2024-08-30")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    rule = read_choice(args.choice)   # raises before any AAPL data is read
    print(f"breach rule {rule.name} is chosen; loading AAPL bars")

    minutes = read_minute_json(args.json)
    resampled = resample_to_5m(minutes, args.from_date, args.to_date)
    bars = write_bar_cache(resampled.bars, args.symbol, args.from_date,
                           args.to_date, args.interval, args.cache,
                           overwrite=args.overwrite)
    check_close = session_close(minutes, args.check_date)
    before_date, before_close = last_close_before(minutes, args.from_date)

    print(f"{len(bars)} bars over {resampled.sessions} sessions "
          f"{args.from_date}..{args.to_date}")
    print(f"dropped {resampled.early_close_minutes_dropped} minutes after "
          "13:00 on early-close days")
    print(f"{args.check_date} close: {check_close} "
          "(check against the published close)")
    print(f"last close before {args.from_date}: {before_close} on "
          f"{before_date}; x{AAPL_SCALE} = {before_close * AAPL_SCALE:.0f}")
    print(f"wrote {cache_path(args.cache, args.symbol, args.from_date, args.to_date, args.interval)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Implement the holdout command**

Create `scripts/run_aapl_holdout.py`:

```python
"""
The AAPL fresh holdout: one corpus under the breach rule the RELIANCE sweep
chose, read whole, once.

Refuses to run if the choice file is missing or null, if the results file or
its `.started` marker exists, or if the AAPL corpus directory already
exists. Writes the marker before any AAPL statistic is computed. Computes
only what the spec names: touch density, the pooled lag-free reach rate,
the 13 groups, the dropped shares and the verdict. The choice file must
also be committed before this runs (checked by hand; see the plan).

Spec: docs/superpowers/specs/2026-10-16-gann-breach-definition-sweep-design.md

Usage (from gann-visualizer/backend/), after scripts/load_aapl_bars.py:
    python scripts/run_aapl_holdout.py \
        --choice <repo>/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json \
        --cache C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/bars \
        --out C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/aapl_5m_x6 \
        --results <repo>/docs/superpowers/specs/2026-10-16-gann-aapl-holdout-results.md

--from, --to and --shadows exist for tests; the holdout uses the defaults.
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import List, Optional, Union

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from build_gann_corpus import ensure_corpus
from mine_gann_corpus import load_scored_events
from study_tool.corpus_writer import ALL_SLICES
from study_tool.mining.breach_sweep import (
    Verdict, aapl_verdict, read_choice, score_rule,
)
from study_tool.mining.sweep_report import render_aapl_results

SYMBOL = "AAPL"
FROM_DATE = "2024-09-02"
TO_DATE = "2026-09-01"
INTERVAL = "5"
# 228.86 (last close before the window, 2024-08-30) x 6 = 1373, matching
# RELIANCE's median 1375 at x1: the same relative sub-level spacing.
SCALE = 6
SHADOWS = 50
SEED = 7

PathLike = Union[str, Path]


def started_marker(results_path: PathLike) -> Path:
    """`<results>.started`: written once the look begins, never removed."""
    return Path(f"{results_path}.started")


def run_aapl(choice_path: PathLike, cache_dir: PathLike, out_dir: PathLike,
             results_path: PathLike, from_date: str = FROM_DATE,
             to_date: str = TO_DATE, shadows: int = SHADOWS) -> Verdict:
    """Build, read once, write the verdict. Returns the Verdict."""
    rule = read_choice(choice_path)            # before anything touches AAPL
    results_path = Path(results_path)
    marker = started_marker(results_path)
    if results_path.exists():
        raise FileExistsError(
            f"{results_path} exists: AAPL has been read already, and the "
            "holdout gets one look")
    if marker.exists():
        raise FileExistsError(
            f"{marker} exists: a look at AAPL was started already, and the "
            "holdout gets one look even if that run crashed")
    if Path(out_dir).exists():
        raise FileExistsError(
            f"{out_dir} already exists: the AAPL corpus is built by this "
            "command only, never reused")

    status = ensure_corpus(
        symbol=SYMBOL, from_date=from_date, to_date=to_date,
        interval=INTERVAL, price_scale=SCALE, shadow_count=shadows,
        seed=SEED, cache_dir=cache_dir, out_dir=out_dir,
        breach_mode=rule.breach_mode,
        confirmation_closes=rule.confirmation_closes)
    if status != "built":
        raise RuntimeError(
            f"ensure_corpus returned {status!r} for {out_dir}; the AAPL "
            "corpus must be built fresh by this command")
    print(f"AAPL corpus built under {rule.name}")

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        f"AAPL look started {time.strftime('%Y-%m-%d %H:%M')} under "
        f"{rule.name}\n", encoding="utf-8")

    scored = load_scored_events(out_dir, slice_name=ALL_SLICES)
    score = score_rule(rule.name, scored.events, scored.meta.shadow_count)
    verdict = aapl_verdict(score)

    context = {
        "rule": rule.name, "breach_mode": rule.breach_mode,
        "confirmation_closes": rule.confirmation_closes,
        "choice": str(choice_path), "corpus": str(out_dir),
        "price_scale": SCALE,
        "shadow_count": scored.meta.shadow_count,
        "rows": len(scored.events),
        "generated": time.strftime("%Y-%m-%d %H:%M"),
    }
    results_path.write_text(render_aapl_results(score, verdict, context),
                            encoding="utf-8")

    print(f"verdict: {verdict.label}")
    print(f"wrote {results_path}")
    return verdict


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--choice", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--from", dest="from_date", default=FROM_DATE)
    parser.add_argument("--to", dest="to_date", default=TO_DATE)
    parser.add_argument("--shadows", type=int, default=SHADOWS)
    args = parser.parse_args(argv)

    try:
        read_choice(args.choice)
    except (FileNotFoundError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    run_aapl(choice_path=args.choice, cache_dir=args.cache, out_dir=args.out,
             results_path=args.results, from_date=args.from_date,
             to_date=args.to_date, shadows=args.shadows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest tests/study_tool/test_load_aapl_bars.py tests/study_tool/test_run_aapl_holdout.py -v`

Expected: all PASS.

- [ ] **Step 7: Commit**

Restore the session log first (see Conventions), then:

```bash
git add scripts/load_aapl_bars.py scripts/run_aapl_holdout.py tests/study_tool/test_load_aapl_bars.py tests/study_tool/test_run_aapl_holdout.py
git commit -m "feat: aapl loader and holdout commands with one-look guards" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: Full test suite

**Files:** none.

- [ ] **Step 1: Run the whole backend suite**

Run: `C:/Users/kitsh/AppData/Local/miniconda3/python.exe -m pytest`

Expected: 0 failed, 0 errors (baseline before this plan: 470 passed; this plan adds roughly 120). If anything fails, use superpowers:systematic-debugging, fix it in the task that owns the file, and commit the fix as `fix: ...` before moving on.

- [ ] **Step 2: Restore the tracked session log and remove new ones**

The run imported `main.py`, which deletes `logs/backend/backend_session_20260507_163028.log` (tracked) and writes a new untracked session log (`main.py:40-48`). Run:

```bash
git -C C:/Dev/GannTesting/.worktrees/breach-sweep checkout -- logs/backend/backend_session_20260507_163028.log
git -C C:/Dev/GannTesting/.worktrees/breach-sweep ls-files --others --exclude-standard -- 'logs/backend/backend_session_*.log' | sed 's|^|C:/Dev/GannTesting/.worktrees/breach-sweep/|' | xargs -r rm --
```

The same applies after every pytest run in every task, before its commit; every commit uses explicit `git add <files>`.

- [ ] **Step 3: Confirm the tree is clean**

Run: `git -C C:/Dev/GannTesting/.worktrees/breach-sweep status --short`

Expected: empty output.

---

### Task 18 (RUN): The RELIANCE sweep

**Files:**
- Writes (gitignored): `C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/breach_sweep/reliance_5m_x1_{close1,wick1,close2,close3}/`
- Writes and commits: `C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json`, `C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-results.md`

Expected cost, from the 2026-09-02 build of `reliance_5m_x1` (bars cached 19:11, events written 19:59) and the 2026-09-02 mining run (559,110 breaches raced in 131 s): about 50 minutes per corpus build at x1, longer for `close1` and `wick1` (more crosses); gate about 1-2 minutes and about 6 GB RAM; scoring about 5-10 minutes per corpus. Wall clock about 3 hours with the three non-gate builds in parallel, about 4.5 hours serial. Disk: about 115-200 MB per corpus (23 GB free on C: on 2026-10-16). Agent token cost is small (the runs are background processes).

- [ ] **Step 1: Warn the user and wait for a yes**

Tell the user: four RELIANCE corpus builds plus scoring, about 3 hours wall clock in the background, about 1 GB of disk under the main checkout's gitignored `logs/corpus/breach_sweep/`, no fetching, no AAPL data touched. Wait for an explicit yes.

- [ ] **Step 2: Preflight**

Run:

```bash
ls -la C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/bars/RELIANCE_5_2024-09-02_2026-09-01.parquet C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/reliance_5m_x1/events.parquet
git status --short
git log --oneline -1
```

Expected: both files exist (1,549,987 and 113,357,023 bytes); clean tree; HEAD is the Task 16 commit or later.

- [ ] **Step 3: Build close2 and run the gate (background)**

Run (in the background):

```bash
C:/Users/kitsh/AppData/Local/miniconda3/python.exe scripts/run_breach_sweep.py --cache C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/bars --reference C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/reliance_5m_x1/events.parquet --out-root C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/breach_sweep --choice C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json --results C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-results.md --rules close2 --build-only
```

Expected (about 50 minutes): `37110 bars 2024-09-02..2026-09-01`, `close2: built in ...s`, `peak memory so far: <P> GB`, then `regression gate: PASSED - 5326759 rows match on all 72 columns`, exit code 0. **Write down P** (the build's peak working set); Step 4 depends on it.

If it prints `STOPPED:` and exits 2: **stop the whole plan.** Do not build or score anything else. Use superpowers:systematic-debugging on the named column, report to the user, and do not proceed until the gate passes.

- [ ] **Step 4: Build the other three rules - parallel only if they fit**

Decide from P (Step 3): if `3 x P < 50` GB, start the three commands below as parallel background processes. Otherwise run them one at a time, each after the previous exits. `close1` and `wick1` produce more crosses than `close2`, so their peaks can exceed P; 50 GB leaves about 13 GB of the machine's 63 GB as margin. The commands are the same as Step 3, changing only `--rules`:

```bash
C:/Users/kitsh/AppData/Local/miniconda3/python.exe scripts/run_breach_sweep.py --cache C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/bars --reference C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/reliance_5m_x1/events.parquet --out-root C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/breach_sweep --choice C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json --results C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-results.md --rules close1 --build-only
```

```bash
C:/Users/kitsh/AppData/Local/miniconda3/python.exe scripts/run_breach_sweep.py --cache C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/bars --reference C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/reliance_5m_x1/events.parquet --out-root C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/breach_sweep --choice C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json --results C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-results.md --rules wick1 --build-only
```

```bash
C:/Users/kitsh/AppData/Local/miniconda3/python.exe scripts/run_breach_sweep.py --cache C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/bars --reference C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/reliance_5m_x1/events.parquet --out-root C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/breach_sweep --choice C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json --results C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-results.md --rules close3 --build-only
```

Expected: each prints `<rule>: built in ...s` and `peak memory so far: ... GB`, and exits 0 (about 50-90 minutes each). While they run in parallel, check total use now and then with `powershell -NoProfile -Command "(Get-Process python | Measure-Object WorkingSet64 -Sum).Sum / 1GB"`; if it passes 55 GB, stop starting new builds and let the running ones finish.

- [ ] **Step 5: Score and select**

Run:

```bash
C:/Users/kitsh/AppData/Local/miniconda3/python.exe scripts/run_breach_sweep.py --cache C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/bars --reference C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/reliance_5m_x1/events.parquet --out-root C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/breach_sweep --choice C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json --results C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-results.md
```

Expected (about 30-45 minutes): four `<rule>: reused`, `regression gate: PASSED ...`, four `<rule>: scored in ...s`, then `chosen: <rule>` or `chosen: null - AAPL is not built`, and the two `wrote` lines.

- [ ] **Step 6: Sanity-check the results before committing**

Read the results document. Check, and stop and debug if any fails:
- `entry-only dropped (real)` is `0.0000` for `close1`, `close2` and `close3` (a non-zero value is a bug in `entry_beyond_level`).
- The `close2` plain `reach_next_rate` real value is close to the confirmed figures (all rows now, not explore only, so not identical).
- Every rule's lag-free `n` is smaller than its plain `reach_next_rate` `n`.
- Per AGENTS.md, a result that looks profitable is where a bug hides: the filter reads only bars `c..k` (pinned by `test_the_filter_reads_no_bar_after_confirmation`); the race starts after `k`.

Do not change any selection input after reading the result. The choice is whatever the file says.

- [ ] **Step 7: Commit the choice and the results**

```bash
git add C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-results.md
git commit -m "docs: breach sweep results and the pre-registered choice" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 8: If the choice is null, stop here**

If `"chosen": null`, the sweep is a null and AAPL is **not** built (spec stop rule). Report to the user and skip Task 19. The fresh holdout is kept for a better question.

---

### Task 19 (RUN): The AAPL look — only after Task 18 is committed with a non-null choice

**Files:**
- Writes (gitignored): `C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/bars/AAPL_5_2024-09-02_2026-09-01.parquet`, `C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/aapl_5m_x6/`
- Writes and commits: `C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-aapl-holdout-results.md` and its marker `C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-aapl-holdout-results.md.started`

**The RELIANCE choice must be committed before any step here runs.** Both AAPL commands also refuse in code without a non-null choice file. Expected cost: loader about 1-2 minutes; AAPL build at x6 roughly 1-1.5 hours (grid builds dominate; more distinct keys than RELIANCE x1); scoring about 5 minutes (only the spec's statistics are computed).

- [ ] **Step 1: Confirm the choice is committed and non-null**

Run:

```bash
git log -1 --format=%h -- C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json
git status --porcelain -- C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json
grep '"chosen"' C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json
```

Expected: a commit hash; empty porcelain output; `"chosen": "<rule>"` (not `null`). If any check fails, stop.

- [ ] **Step 2: Confirm nothing from an earlier look exists**

Run:

```bash
ls C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/aapl_5m_x6 C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-aapl-holdout-results.md C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-aapl-holdout-results.md.started
```

Expected: `No such file or directory` for all three. If any exists, stop and report: the holdout may already be spent.

- [ ] **Step 3: Warn the user and wait for a yes**

Tell the user: this is the one look at the fresh AAPL holdout under `<rule>`, about 1.5 hours in the background, and it cannot be repeated. Wait for an explicit yes.

- [ ] **Step 4: Load the AAPL bars into the cache**

Run:

```bash
C:/Users/kitsh/AppData/Local/miniconda3/python.exe scripts/load_aapl_bars.py --choice C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json --json C:/Dev/GannTesting/data_local/aapl_rth_1m.json --cache C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/bars
```

Expected: `breach rule <rule> is chosen; loading AAPL bars`, about `38898 bars over 501 sessions 2024-09-02..2026-09-01` (496 full sessions x 78 + 5 early closes x 42, fewer only if whole 5-minute buckets are missing), `dropped 529 minutes after 13:00 on early-close days`, `2024-08-30 close: 228.86 (check against the published close)`, `last close before 2024-09-02: 228.86 on 2024-08-30; x6 = 1373`. Save these lines for Step 7.

The 2024-08-30 value is the 15:59 bar's last trade, not the closing auction, so a gap of cents from the published close is expected; a gap of dollars means the source is adjusted differently than assumed - stop and report.

- [ ] **Step 5: Run the holdout (background)**

Run (in the background):

```bash
C:/Users/kitsh/AppData/Local/miniconda3/python.exe scripts/run_aapl_holdout.py --choice C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json --cache C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/bars --out C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/aapl_5m_x6 --results C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-aapl-holdout-results.md
```

Expected: `AAPL corpus built under <rule>`, then `verdict: <fail | pass | strong pass>[, selection differs]`, then `wrote ...results.md`; exit code 0. If it crashes after the marker is written, the look is spent: do not delete the marker to retry. Report to the user.

- [ ] **Step 6: Read the result in the pre-registered order**

Touch density first, then the verdict, then the dropped-share line. Do not re-run, re-scale, re-slice, or run `mine_gann_corpus.py` on the AAPL corpus: the holdout is spent on exactly the statistics in the results file, and any further statistic on it is an unplanned look.

- [ ] **Step 7: Add the data check to the results document**

Append to `C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-aapl-holdout-results.md`:

````markdown
## Data check

Loader output (scripts/load_aapl_bars.py):

```
<the lines saved in Step 4, verbatim>
```

Published AAPL close on 2024-08-30: <value and source>.

What was seen of AAPL before this look: while writing the loader
(2026-10-16), the minute counts per session, the session times (09:30-15:59)
and the 1-minute volumes on early-close days inside the window were read, to
find the extended-hours minutes after 13:00. No Gann ladder, level or reach
statistic was computed on AAPL before this run.
````

- [ ] **Step 8: Commit**

```bash
git add C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-aapl-holdout-results.md C:/Dev/GannTesting/.worktrees/breach-sweep/docs/superpowers/specs/2026-10-16-gann-aapl-holdout-results.md.started
git commit -m "docs: aapl fresh holdout results" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Coverage table

| Spec item | Task |
|---|---|
| What gets built 1: wick mode fix, with tests | 1 |
| What gets built 2: `--breach-mode` / `--confirmation-closes`, defaults close / 2, both in `meta.json` | 3 |
| What gets built 3: `CorpusMeta` optional keys, default close / 2, version stays 1 | 4 |
| What gets built 4: `target_hit_before_entry` (via `meta.confirmation_closes`) and `entry_beyond_level` | 5 |
| What gets built 5: `lag_free_reach_rate`, `dropped_share` (+ entry-only share); z and missing-shadow count from the comparison | 6, 7 |
| What gets built 6: `--slice all` in `load_events` and `mine_gann_corpus.py` | 8, 9 |
| What gets built 7: AAPL bars loader (NY-date sessions, 09:30 buckets, UTC bucket start, volume sum, inclusive window, 2024-08-30 close printed, cache hit with sun/moon) | 10 (module), 16 (command, gated on the choice) |
| What gets built 8: sweep runner (four corpora, close2 gate, scoring, selection, choice file) | 11, 12, 13, 14, 15, 18 |
| What gets built 8: AAPL command refusing without a non-null choice | 13, 16, 19 |
| Regression gate: close2 matches `reliance_5m_x1` exactly, stop if not | 11, 15, 18 |
| No step may fetch (bar cache path risk) | 2, 3, 15, 16 |
| Selection rule: gate, z, tie window 0.1, order, stop rule | 12 |
| Also reported per rule: 13 groups, dropped share real vs shadow, plain `reach_next_rate`, raced counts, touch density | 12, 14 |
| Choice committed before any AAPL step | 18 (Step 7), 19 (Step 1); in code, both AAPL commands refuse without a non-null choice (16) |
| AAPL: scale x6, one rule, 50 shadows, seed 7, one look, `--slice all` | 16, 19 |
| AAPL one look enforced: no reuse of an existing corpus, `.started` marker before scoring, results file, no full mining report | 16 |
| AAPL pass / strong pass, dropped-share reading, touch density first | 13, 14, 16 |
| Test: cross-bar arithmetic for closes 1, 2, 3 (cross bar, middle bar, confirmation bar, never) | 5 (`test_target_hit_before_entry_reads_bars_from_cross_to_confirmation`), 3 (`test_a_confirmed_breach_crossed_exactly_closes_minus_one_bars_earlier`) |
| Test: the filter uses no bar after `k` | 5 (`test_the_filter_reads_no_bar_after_confirmation`) |
| Test: wick cases (down from above closing back, within tolerance no cross, clean wick up; two old tests rewritten) | 1 |
| Test: 5-minute resample - session boundaries, DST, a half-day, volume sum | 10 |
| Test: old meta without the new keys loads as close / 2 | 4 |
| Test: z, missing shadows, above all shadows on hand-made inputs | 7, 12 |
| Test: AAPL command refuses without a choice file, and with a null one | 13, 16 |

## Spec ambiguities resolved in this plan

1. **Half-days.** The source keeps 13:00-15:59 extended-hours minutes on the five early-close days in the window (529 minutes). The loader drops them using an explicit `NYSE_EARLY_CLOSES` list and prints the count.
2. **Missing shadows** means `Comparison.shadows_missing`: no rows in the group **or** an undefined statistic there. Either way that shadow has no value to beat.
3. **Eligible rule with undefined z** (shadow sd 0): `select_rule` raises rather than guess. Not expected with 50 shadows.
4. **Entry-only dropped share** = targeted rows with `entry_beyond_level` False / targeted rows, whether or not the target filter also drops them.
5. **"Match exactly"** for the gate is defined in Task 11 (names, order, types, row count, sorted values; NaN = null; schema metadata ignored; no column excluded; every differing column named).
6. **`entry_beyond_level`** is set for every confirmed breach; only targeted rows count toward the dropped shares.
7. **Wick first cross** uses strict inequalities against the previous close; a previous close exactly on the level is no cross.
8. **One look** is enforced in code by the choice check, refusing an existing AAPL corpus, the `.started` marker and the results file; "committed" is a manual check in Task 19.
9. **What AAPL output is** - only the spec's statistics (touch density, pooled lag-free reach rate, 13 groups, dropped shares, verdict). The general mining report is never run on AAPL.
10. **Before the look,** loader development read AAPL minute counts, session times and early-close volumes inside the window (not ladder statistics). This is recorded in the AAPL write-up (Task 19, Step 7).
