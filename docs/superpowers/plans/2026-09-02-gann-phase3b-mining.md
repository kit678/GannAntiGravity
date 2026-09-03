# Gann Phase 3b Mining Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure the Gann corpus against its 50-shadow control, per label group, and emit a Markdown report whose output is a shortlist of candidates to test later against the holdout.

**Architecture:** One reusable `compare(events, statistic_fn)` runs a statistic on the real events and on each shadow, then reports where real sits in the shadow spread. Statistics are pure functions from an events frame to `(value, sample_size)`. The reach-next-level race needs the ladder at the breach bar, which is rebuilt from `ladder_keys` and cached as a compact per-source price array rather than as full level dicts. Shadow targets are the real target plus that shadow's offset, which is why the corpus must first learn to record its offsets.

**Tech Stack:** Python 3.13, pandas, numpy, pyarrow, pytest. Existing modules `study_tool/corpus_writer.py`, `study_tool/run_ladder_study.py`, `study_tool/shadow_ladder.py`, `scripts/build_gann_corpus.py`.

**Spec:** `docs/superpowers/specs/2026-09-02-gann-phase3b-mining-design.md`

---

## Facts established before planning (do not re-derive)

- `build_all_ladders(price, price_scale, sun_square, moon_square)` uses `price`
  **only** via `target = int(round(price * price_scale))` (`run_ladder_study.py:43`).
  `ladder_keys.parquet` stores exactly that integer as `price_square`, so
  `build_all_ladders(price_square / price_scale, price_scale, sun_square, moon_square)`
  reproduces the build's ladder **exactly**. No approximation.
- Level dicts carry `price, square, source, kind, degree, ring, sub_index,
  is_halfway, segment_start, segment_end, direction`.
- Events carry `level_source, level_price, level_square, level_kind,
  level_degree, level_ring, level_sub_index, level_is_halfway,
  level_segment_start, level_segment_end, direction, bar_index, breach_id,
  parent_breach_id, outcome, shadow_id, slice` as real columns.
- **`depth_in_sublevels` is NOT a column.** It lives inside the `details` JSON
  string on `LADDER_RETEST` events (`gann_ladder_analyzer.py:343`). Mining must
  parse `details` to reach it.
- `direction` is the string `"up"` or `"down"` on breach events.
- `outcome` is a real column, lifted out of `details` by
  `build_gann_corpus._events_to_frame`. Values seen: `RETEST_FAILED`,
  `NEVER_CONFIRMED`, `RETEST_HELD`, `NEVER_RETESTED`, `None` (truncated).
- `assign_slices` sorts **all** rows (real + shadow) by `bar_index` and takes the
  last 25% as holdout. The explore/holdout boundary is therefore a `bar_index`,
  recoverable as the minimum `bar_index` among holdout rows.
- `resolution_window_bars` is 50, set in
  `build_gann_corpus._analyzer_settings`.
- Corpus scale: 37,110 bars, 14,641 distinct ladder keys, 105,807 real events,
  5,220,952 shadow events, 14,803 real `LADDER_BREACH_CONFIRMED`.
- **Repo quirk:** `.gitignore` blanket-excludes `**/tests/`. Every new test file
  needs `git add -f` or it silently goes untracked.

## Two deliberate deviations from the spec

1. The spec writes `statistic_fn` as returning "a single float". It returns
   `Stat(value, n)` instead. The spec also requires that sample size travels
   with every result; threading it separately would mean a parallel function per
   statistic just to count rows, and the two would drift apart.
2. The spec lists four mining modules. This plan uses seven, splitting out
   `corpus_meta.py`, `boundary.py` and `report.py`. Each is one responsibility
   and each is separately testable; folding them into the entry point would put
   the two leak-closing mechanisms inside an untested script.

---

## File structure

| File | Responsibility |
|---|---|
| `gann-visualizer/backend/study_tool/corpus_writer.py` | *Modified* — require and emit `meta.json`. |
| `gann-visualizer/backend/scripts/build_gann_corpus.py` | *Modified* — assemble and supply the meta. |
| `gann-visualizer/backend/scripts/backfill_corpus_meta.py` | One-off: write `meta.json` for the existing 113 MB corpus. |
| `gann-visualizer/backend/study_tool/mining/__init__.py` | Package marker. Nothing else. |
| `gann-visualizer/backend/study_tool/mining/corpus_meta.py` | Load and validate `meta.json`. Fail loudly if absent. |
| `gann-visualizer/backend/study_tool/mining/boundary.py` | Drop the explore events whose forward window reaches the holdout. |
| `gann-visualizer/backend/study_tool/mining/shadow_compare.py` | `Stat`, `Comparison`, `compare()`. |
| `gann-visualizer/backend/study_tool/mining/statistics.py` | The five statistic functions. |
| `gann-visualizer/backend/study_tool/mining/groups.py` | The grouping definitions and ring binning. |
| `gann-visualizer/backend/study_tool/mining/ladder_rebuild.py` | Cached ladder rebuild, next-level lookup, the target/stop race. |
| `gann-visualizer/backend/study_tool/mining/report.py` | Turn comparisons into Markdown. |
| `gann-visualizer/backend/scripts/mine_gann_corpus.py` | Entry point. Wires it all, writes the report. |

---

### Task 1: The corpus records its own build metadata

The shadow offsets are not recoverable from the events — tested, and the natural
join key yields 178–182 conflicting deltas per shadow. Without them a shadow's
next-level target is wrong. `meta` is a **required** argument, not an optional
one, because a corpus without it cannot be mined and an optional argument invites
the same gap a second time.

**Files:**
- Modify: `gann-visualizer/backend/study_tool/corpus_writer.py`
- Modify: `gann-visualizer/backend/scripts/build_gann_corpus.py`
- Modify (tests): `gann-visualizer/backend/tests/study_tool/test_corpus_writer.py`
- Modify (tests): `gann-visualizer/backend/tests/study_tool/test_build_gann_corpus.py`

- [ ] **Step 1: Write the failing tests**

Add to the top of `gann-visualizer/backend/tests/study_tool/test_corpus_writer.py`,
replacing the import block at lines 15-17:

```python
import json

from study_tool.corpus_writer import (
    assign_slices, load_events, load_meta, write_corpus,
)
```

Add this helper below `keys_frame()`:

```python
def meta_dict():
    return {
        "corpus_meta_version": 1,
        "symbol": "RELIANCE",
        "from_date": "2026-08-01",
        "to_date": "2026-08-31",
        "interval": "5",
        "price_scale": 1,
        "shadow_count": 2,
        "seed": 7,
        "median_sub_gap": 2.25,
        "shadow_offsets": [0.4, 1.1],
        "resolution_window_bars": 50,
        "bar_count": 10,
    }
```

Every existing `write_corpus(...)` call in that file gains `meta=meta_dict()`.
There are seven of them, at lines 60, 68, 72, 77, 80, 88, 99 and 108. For
example line 60-61 becomes:

```python
    write_corpus(tmp_path, events=assign_slices(events_frame()),
                 bars=bars_frame(), ladder_keys=keys_frame(), meta=meta_dict())
```

Then append these four new tests:

```python
def test_meta_json_is_written_beside_the_tables(tmp_path):
    write_corpus(tmp_path, events=assign_slices(events_frame()),
                 bars=bars_frame(), ladder_keys=keys_frame(), meta=meta_dict())

    assert (tmp_path / "meta.json").exists()


def test_meta_round_trips_including_the_shadow_offsets(tmp_path):
    """
    The offsets are the point. They are not recoverable from the events - a
    join on (bar_index, source, degree, sub_index) yields 178-182 conflicting
    deltas per shadow - so if they are not written here they are gone.
    """
    write_corpus(tmp_path, events=assign_slices(events_frame()),
                 bars=bars_frame(), ladder_keys=keys_frame(), meta=meta_dict())

    loaded = load_meta(tmp_path)

    assert loaded["shadow_offsets"] == [0.4, 1.1]
    assert loaded["seed"] == 7
    assert loaded["price_scale"] == 1


def test_write_corpus_refuses_a_meta_whose_offsets_do_not_match_the_count(tmp_path):
    """A short offset list would silently mis-target most shadows."""
    broken = meta_dict()
    broken["shadow_count"] = 50

    with pytest.raises(ValueError, match="shadow_offsets"):
        write_corpus(tmp_path, events=assign_slices(events_frame()),
                     bars=bars_frame(), ladder_keys=keys_frame(), meta=broken)


def test_an_existing_meta_json_also_blocks_an_accidental_overwrite(tmp_path):
    """A corpus takes 40 minutes to build; half-replacing one is worse than not."""
    (tmp_path).mkdir(exist_ok=True)
    (tmp_path / "meta.json").write_text(json.dumps(meta_dict()))

    with pytest.raises(FileExistsError, match="overwrite"):
        write_corpus(tmp_path, events=assign_slices(events_frame()),
                     bars=bars_frame(), ladder_keys=keys_frame(), meta=meta_dict())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/test_corpus_writer.py -q`
Expected: FAIL — `ImportError: cannot import name 'load_meta' from 'study_tool.corpus_writer'`

- [ ] **Step 3: Implement in `corpus_writer.py`**

Replace the imports and constants block (lines 20-27) with:

```python
import json
import math
from pathlib import Path
from typing import Dict, Union

import pandas as pd

SLICES = ("explore", "holdout")
TABLES = ("events", "bars", "ladder_keys")
META_FILENAME = "meta.json"

# Everything the mining phase needs and cannot recover from the events.
REQUIRED_META_FIELDS = (
    "corpus_meta_version", "symbol", "from_date", "to_date", "interval",
    "price_scale", "shadow_count", "seed", "median_sub_gap",
    "shadow_offsets", "resolution_window_bars", "bar_count",
)
```

Replace `write_corpus` (lines 46-68) with:

```python
def _validate_meta(meta: Dict) -> None:
    missing = [f for f in REQUIRED_META_FIELDS if f not in meta]
    if missing:
        raise ValueError(f"meta is missing {missing}")

    if len(meta["shadow_offsets"]) != meta["shadow_count"]:
        raise ValueError(
            f"shadow_offsets has {len(meta['shadow_offsets'])} entries but "
            f"shadow_count is {meta['shadow_count']}; a short list would "
            "silently mis-target most shadows"
        )


def write_corpus(corpus_dir: Union[str, Path], events: pd.DataFrame,
                 bars: pd.DataFrame, ladder_keys: pd.DataFrame,
                 meta: Dict, overwrite: bool = False) -> None:
    """
    Write the three tables as Parquet, plus meta.json.

    `meta` is required, not optional. The shadow offsets it carries are not
    recoverable from the events - joining real to shadow on
    (bar_index, source, degree, sub_index) yields 178-182 conflicting deltas
    per shadow - so a corpus written without them cannot be mined at all. An
    optional argument would let that gap reappear silently.

    Refuses to touch a directory that already holds any corpus file unless
    overwrite=True. A corpus can take hours to build, and to_parquet would
    otherwise replace it with no warning.
    """
    _validate_meta(meta)

    corpus_dir = Path(corpus_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)

    if not overwrite:
        existing = [name for name in TABLES
                    if (corpus_dir / f"{name}.parquet").exists()]
        if (corpus_dir / META_FILENAME).exists():
            existing.append(META_FILENAME)
        if existing:
            raise FileExistsError(
                f"{corpus_dir} already has {existing}; pass overwrite=True to replace"
            )

    for name, frame in zip(TABLES, (events, bars, ladder_keys)):
        frame.to_parquet(corpus_dir / f"{name}.parquet", index=False)

    (corpus_dir / META_FILENAME).write_text(
        json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")


def load_meta(corpus_dir: Union[str, Path]) -> Dict:
    """
    The corpus build metadata.

    Raises:
        FileNotFoundError: if meta.json is absent. Guessing the offsets is
            worse than stopping - a wrong offset puts every shadow's
            next-level target on the wrong price and the report still prints.
    """
    path = Path(corpus_dir) / META_FILENAME
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found; run scripts/backfill_corpus_meta.py for a "
            "corpus built before meta.json existed"
        )
    meta = json.loads(path.read_text(encoding="utf-8"))
    _validate_meta(meta)
    return meta
```

- [ ] **Step 4: Run the corpus-writer tests**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/test_corpus_writer.py -q`
Expected: `11 passed`

- [ ] **Step 5: Make the build script supply the meta**

In `gann-visualizer/backend/scripts/build_gann_corpus.py`, change the
`build_corpus` signature and return (lines 109-164). Replace lines 109-116 with:

```python
CORPUS_META_VERSION = 1


def build_corpus(bars: pd.DataFrame, instrument: str, timeframe: str,
                 price_scale: int, shadow_count: int, seed: int) -> Dict:
    """
    Walk `bars` against the real ladder and `shadow_count` shifted ones.

    Returns a dict with `events`, `bars`, `ladder_keys` and `meta`. The meta
    carries the shadow offsets, which nothing downstream can recompute.
    """
    settings = _analyzer_settings(instrument, timeframe, price_scale)
```

Replace the return block (lines 160-164) with:

```python
    return {
        "events": pd.concat(frames, ignore_index=True),
        "bars": bars.reset_index(drop=True),
        "ladder_keys": pd.DataFrame(keys),
        "meta": {
            "corpus_meta_version": CORPUS_META_VERSION,
            "symbol": instrument,
            "interval": timeframe,
            "price_scale": price_scale,
            "shadow_count": shadow_count,
            "seed": seed,
            "median_sub_gap": gap,
            "shadow_offsets": list(offsets),
            "resolution_window_bars": settings["resolution_window_bars"],
            "bar_count": int(len(bars)),
        },
    }
```

In `main()`, replace lines 189-191 with:

```python
    events = assign_slices(result["events"], order_column="bar_index")
    meta = dict(result["meta"])
    meta["from_date"] = args.from_date
    meta["to_date"] = args.to_date
    write_corpus(Path(args.out), events=events, bars=result["bars"],
                 ladder_keys=result["ladder_keys"], meta=meta,
                 overwrite=args.overwrite)
```

`from_date` / `to_date` are added in `main` because `build_corpus` takes a bar
frame, not a date range, and inventing dates from the bars would disagree with
the arguments actually used.

- [ ] **Step 6: Add the build-script test**

Append to `gann-visualizer/backend/tests/study_tool/test_build_gann_corpus.py`:

```python
def test_build_returns_one_offset_per_shadow():
    """
    Mining shifts each shadow's target by its own offset. A missing or
    misaligned offset silently prices every shadow target wrongly.
    """
    result = build_corpus(
        bars=synthetic_bars(), instrument="RELIANCE", timeframe="5",
        price_scale=1, shadow_count=3, seed=7,
    )
    meta = result["meta"]

    assert len(meta["shadow_offsets"]) == 3
    assert meta["seed"] == 7
    assert meta["price_scale"] == 1
    assert meta["shadow_count"] == 3
    assert meta["resolution_window_bars"] == 50
    assert meta["bar_count"] == 60


def test_meta_offsets_are_reproducible_from_the_seed():
    kwargs = dict(bars=synthetic_bars(), instrument="RELIANCE", timeframe="5",
                  price_scale=1, shadow_count=3, seed=7)
    assert build_corpus(**kwargs)["meta"]["shadow_offsets"] == \
        build_corpus(**kwargs)["meta"]["shadow_offsets"]
```

- [ ] **Step 7: Run both test files**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/test_corpus_writer.py tests/study_tool/test_build_gann_corpus.py -q`
Expected: `20 passed`

- [ ] **Step 8: Run the full ladder suite for regressions**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/ tests/test_event_logger_ladder_schema.py tests/test_event_logger_mfe_mae_horizons.py -q`
Expected: all pass. Baseline before this task was `122 passed`; expect `128 passed`.

- [ ] **Step 9: Commit**

```bash
git add gann-visualizer/backend/study_tool/corpus_writer.py gann-visualizer/backend/scripts/build_gann_corpus.py
git add -f gann-visualizer/backend/tests/study_tool/test_corpus_writer.py gann-visualizer/backend/tests/study_tool/test_build_gann_corpus.py
git commit -m "feat: corpus records its build metadata, including the shadow offsets

The offsets are not recoverable from the events. Joining real to shadow on
(bar_index, source, degree, sub_index) yields 178-182 conflicting deltas per
shadow, because that key is not unique within a bar. Without the offset a
shadow's next-level target lands on the wrong price and the report still
prints a number.

meta is a required argument rather than an optional one, because a corpus
without it cannot be mined and an optional argument would let the same gap
reappear."
```

---

### Task 2: Backfill `meta.json` for the existing corpus

The 113 MB corpus already on disk took ~40 minutes and needs a live Dhan token
to rebuild. The offsets are a pure function of the ladder keys, the seed and the
scale, all of which the corpus already stores, so they can be recomputed in
~92 seconds instead.

This script deliberately imports the build's own `_median_sub_gap` rather than
copying it. Duplicating it would let the two drift, and a drifted gap yields
offsets that look plausible and are wrong. The coupling is confined to this
one-off script; mining reads `meta.json` and never recomputes anything.

**Files:**
- Create: `gann-visualizer/backend/scripts/backfill_corpus_meta.py`
- Test: `gann-visualizer/backend/tests/study_tool/test_backfill_corpus_meta.py`

- [ ] **Step 1: Write the failing test**

Create `gann-visualizer/backend/tests/study_tool/test_backfill_corpus_meta.py`:

```python
"""
Backfilling meta.json onto a corpus built before meta.json existed.

The test builds a tiny corpus with the real builder, deletes its meta.json,
backfills, and checks the offsets came back byte-identical. Anything weaker
would pass while producing plausible-looking wrong offsets.
"""
import sys
import os

import pandas as pd

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend/scripts'))

from build_gann_corpus import build_corpus
from backfill_corpus_meta import backfill_meta
from study_tool.corpus_writer import assign_slices, load_meta, write_corpus

NSE_OPEN_EPOCH = 1787629500


def synthetic_bars(n=60):
    rows = []
    for i in range(n):
        open_ = 1300.0 + i * 0.4
        close = open_ + 0.4
        rows.append({
            "open": open_, "high": close + 0.3, "low": open_ - 0.3,
            "close": close, "volume": 1000.0,
            "timestamp": float(NSE_OPEN_EPOCH + i * 300),
            "sun_degree": 155.0 + i * 0.0007,
            "moon_degree": (331.0 + i * 0.009) % 360,
        })
    return pd.DataFrame(rows)


def make_corpus(tmp_path):
    result = build_corpus(bars=synthetic_bars(), instrument="RELIANCE",
                          timeframe="5", price_scale=1, shadow_count=3, seed=7)
    meta = dict(result["meta"])
    meta["from_date"] = "2026-08-01"
    meta["to_date"] = "2026-08-31"
    write_corpus(tmp_path, events=assign_slices(result["events"]),
                 bars=result["bars"], ladder_keys=result["ladder_keys"],
                 meta=meta)
    return meta


def test_backfilled_offsets_match_the_original_exactly(tmp_path):
    original = make_corpus(tmp_path)
    (tmp_path / "meta.json").unlink()

    backfill_meta(tmp_path, symbol="RELIANCE", from_date="2026-08-01",
                  to_date="2026-08-31", interval="5", price_scale=1,
                  shadow_count=3, seed=7)

    restored = load_meta(tmp_path)
    assert restored["shadow_offsets"] == original["shadow_offsets"]
    assert restored["median_sub_gap"] == original["median_sub_gap"]


def test_backfill_refuses_to_clobber_an_existing_meta(tmp_path):
    make_corpus(tmp_path)

    import pytest
    with pytest.raises(FileExistsError, match="meta.json"):
        backfill_meta(tmp_path, symbol="RELIANCE", from_date="2026-08-01",
                      to_date="2026-08-31", interval="5", price_scale=1,
                      shadow_count=3, seed=7)


def test_backfill_checks_the_shadow_count_against_the_events(tmp_path):
    """
    Passing the wrong --shadows produces the wrong offset list, which would
    mis-target every shadow while the report still prints happily.
    """
    make_corpus(tmp_path)
    (tmp_path / "meta.json").unlink()

    import pytest
    with pytest.raises(ValueError, match="shadow"):
        backfill_meta(tmp_path, symbol="RELIANCE", from_date="2026-08-01",
                      to_date="2026-08-31", interval="5", price_scale=1,
                      shadow_count=7, seed=7)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/test_backfill_corpus_meta.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backfill_corpus_meta'`

- [ ] **Step 3: Write the implementation**

Create `gann-visualizer/backend/scripts/backfill_corpus_meta.py`:

```python
"""
Write meta.json for a corpus built before meta.json existed.

Usage:
    python scripts/backfill_corpus_meta.py \
        --corpus logs/corpus/reliance_5m_x1 \
        --symbol RELIANCE --from 2024-09-02 --to 2026-09-01 \
        --interval 5 --scale 1 --shadows 50 --seed 7

The shadow offsets are a pure function of the ladder keys, the price scale and
the seed - all of which the corpus already stores or the operator already knows
- so they are recomputed here rather than paying a ~40 minute rebuild that also
needs a live Dhan token.

The build's own _median_sub_gap is imported rather than copied. A second copy
would drift, and a drifted gap yields offsets that look plausible and are
wrong. The coupling stops here: mining reads meta.json and recomputes nothing.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, Union

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from build_gann_corpus import CORPUS_META_VERSION, _analyzer_settings, _median_sub_gap
from study_tool.corpus_writer import META_FILENAME, _validate_meta
from study_tool.run_ladder_study import build_all_ladders
from study_tool.shadow_ladder import shadow_offsets

import json


def _rebuild_all_distinct_ladders(keys: pd.DataFrame, price_scale: int):
    """
    Every distinct ladder in the corpus, built once each.

    build_all_ladders uses `price` only as int(round(price * price_scale)),
    which is exactly the stored price_square, so dividing back out reproduces
    the build's ladder with no approximation.
    """
    distinct = keys[["price_square", "sun_square", "moon_square"]].drop_duplicates()
    levels = []
    for row in distinct.itertuples():
        levels.extend(build_all_ladders(
            row.price_square / price_scale, price_scale,
            int(row.sun_square), int(row.moon_square)))
    return levels


def backfill_meta(corpus_dir: Union[str, Path], symbol: str, from_date: str,
                  to_date: str, interval: str, price_scale: int,
                  shadow_count: int, seed: int) -> Dict:
    """
    Recompute and write meta.json. Returns the meta it wrote.

    Raises:
        FileExistsError: if meta.json is already there. It may hold the real
            offsets from the build; overwriting them with recomputed ones
            would destroy the only authoritative copy.
        ValueError: if `shadow_count` disagrees with the shadow ids actually
            present in the events. A wrong count produces a wrong offset list
            that mis-targets every shadow while the report still prints.
    """
    corpus_dir = Path(corpus_dir)
    meta_path = corpus_dir / META_FILENAME
    if meta_path.exists():
        raise FileExistsError(f"{meta_path} already exists; nothing to backfill")

    events = pd.read_parquet(corpus_dir / "events.parquet",
                             columns=["shadow_id"])
    present = int(events["shadow_id"].dropna().nunique())
    if present != shadow_count:
        raise ValueError(
            f"--shadows {shadow_count} but the events hold {present} distinct "
            "shadow ids; the offset list would not line up"
        )

    keys = pd.read_parquet(corpus_dir / "ladder_keys.parquet")
    levels = _rebuild_all_distinct_ladders(keys, price_scale)
    gap = _median_sub_gap(levels, price_scale)
    offsets = shadow_offsets(shadow_count, gap, seed)

    bars = pd.read_parquet(corpus_dir / "bars.parquet", columns=["timestamp"])

    meta = {
        "corpus_meta_version": CORPUS_META_VERSION,
        "symbol": symbol,
        "from_date": from_date,
        "to_date": to_date,
        "interval": interval,
        "price_scale": price_scale,
        "shadow_count": shadow_count,
        "seed": seed,
        "median_sub_gap": gap,
        "shadow_offsets": list(offsets),
        "resolution_window_bars":
            _analyzer_settings(symbol, interval, price_scale)["resolution_window_bars"],
        "bar_count": int(len(bars)),
        "backfilled": True,
    }
    _validate_meta(meta)
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True),
                         encoding="utf-8")
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--symbol", default="RELIANCE")
    parser.add_argument("--from", dest="from_date", required=True)
    parser.add_argument("--to", dest="to_date", required=True)
    parser.add_argument("--interval", default="5")
    parser.add_argument("--scale", type=int, default=1)
    parser.add_argument("--shadows", type=int, default=50)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    meta = backfill_meta(args.corpus, symbol=args.symbol,
                         from_date=args.from_date, to_date=args.to_date,
                         interval=args.interval, price_scale=args.scale,
                         shadow_count=args.shadows, seed=args.seed)

    print(f"wrote {Path(args.corpus) / META_FILENAME}")
    print(f"  median sub gap : {meta['median_sub_gap']:.6f}")
    print(f"  offsets        : {len(meta['shadow_offsets'])}")
    print(f"  first three    : {[round(o, 6) for o in meta['shadow_offsets'][:3]]}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/test_backfill_corpus_meta.py -q`
Expected: `3 passed`

- [ ] **Step 5: Backfill the real corpus**

Run:

```bash
cd gann-visualizer/backend && python scripts/backfill_corpus_meta.py --corpus logs/corpus/reliance_5m_x1 --symbol RELIANCE --from 2024-09-02 --to 2026-09-01 --interval 5 --scale 1 --shadows 50 --seed 7
```

Expected: takes roughly 90 seconds, then prints `offsets : 50` and a median sub
gap near `2.25`. No Dhan token needed — this reads Parquet only.

If it raises about the shadow count, **stop**: the corpus on disk is not the one
this plan assumes.

- [ ] **Step 6: Commit**

```bash
git add gann-visualizer/backend/scripts/backfill_corpus_meta.py
git add -f gann-visualizer/backend/tests/study_tool/test_backfill_corpus_meta.py
git commit -m "feat: backfill meta.json onto a corpus built without it

The 113 MB corpus took 40 minutes and a live Dhan token. The offsets are a
pure function of the ladder keys, scale and seed, all already on disk, so
they are recomputed in ~90 seconds instead.

The test rebuilds a small corpus, deletes its meta and checks the backfilled
offsets come back identical - a weaker test would pass while producing
plausible wrong offsets."
```

---

### Task 3: Mining package and the metadata gate

**Files:**
- Create: `gann-visualizer/backend/study_tool/mining/__init__.py`
- Create: `gann-visualizer/backend/study_tool/mining/corpus_meta.py`
- Test: `gann-visualizer/backend/tests/study_tool/mining/test_corpus_meta.py`

- [ ] **Step 1: Write the failing test**

Create `gann-visualizer/backend/tests/study_tool/mining/test_corpus_meta.py`:

```python
"""
Mining refuses to start without the corpus metadata.

A missing offset does not crash anything downstream. It silently puts every
shadow's next-level target on the wrong price, and the report still prints a
percentage. So the gate is here, at load time, and it is loud.
"""
import sys
import os
import json

import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.corpus_meta import CorpusMeta, load_corpus_meta


def good_meta():
    return {
        "corpus_meta_version": 1,
        "symbol": "RELIANCE",
        "from_date": "2024-09-02",
        "to_date": "2026-09-01",
        "interval": "5",
        "price_scale": 1,
        "shadow_count": 3,
        "seed": 7,
        "median_sub_gap": 2.25,
        "shadow_offsets": [0.4, 1.1, 1.9],
        "resolution_window_bars": 50,
        "bar_count": 60,
    }


def write_meta(tmp_path, meta):
    (tmp_path / "meta.json").write_text(json.dumps(meta))


def test_loads_into_a_typed_object(tmp_path):
    write_meta(tmp_path, good_meta())

    meta = load_corpus_meta(tmp_path)

    assert isinstance(meta, CorpusMeta)
    assert meta.price_scale == 1
    assert meta.shadow_count == 3
    assert meta.resolution_window_bars == 50
    assert meta.shadow_offsets == [0.4, 1.1, 1.9]


def test_offset_for_returns_the_right_shadows_shift(tmp_path):
    write_meta(tmp_path, good_meta())

    meta = load_corpus_meta(tmp_path)

    assert meta.offset_for(0) == 0.4
    assert meta.offset_for(2) == 1.9


def test_offset_for_a_real_event_is_zero(tmp_path):
    """Real events carry shadow_id None. Their ladder is unshifted."""
    write_meta(tmp_path, good_meta())

    assert load_corpus_meta(tmp_path).offset_for(None) == 0.0


def test_an_unknown_shadow_id_raises_rather_than_defaulting(tmp_path):
    write_meta(tmp_path, good_meta())

    with pytest.raises(KeyError, match="shadow"):
        load_corpus_meta(tmp_path).offset_for(9)


def test_a_missing_meta_file_raises_with_the_fix_in_the_message(tmp_path):
    with pytest.raises(FileNotFoundError, match="backfill_corpus_meta"):
        load_corpus_meta(tmp_path)


def test_a_future_meta_version_raises(tmp_path):
    """Silently reading a newer layout is how a wrong offset gets used."""
    meta = good_meta()
    meta["corpus_meta_version"] = 99
    write_meta(tmp_path, meta)

    with pytest.raises(ValueError, match="corpus_meta_version"):
        load_corpus_meta(tmp_path)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_corpus_meta.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'study_tool.mining'`

- [ ] **Step 3: Create the package marker**

Create `gann-visualizer/backend/study_tool/mining/__init__.py`:

```python
"""
Mining the Gann corpus against its shadow control.

Everything here explores. Nothing here concludes. The holdout is not read by
any module in this package.
"""
```

- [ ] **Step 4: Write the implementation**

Create `gann-visualizer/backend/study_tool/mining/corpus_meta.py`:

```python
"""
The corpus build metadata, as a typed object mining can rely on.

The shadow offsets are the reason this exists. A shadow ladder is the real
ladder plus a constant, so a shadow breach's next-level target is the real
next level plus that same constant. Get the constant wrong and the target sits
on an arbitrary price - but nothing crashes, and the report still prints a
percentage. So the check is here, at load time, and it fails loudly.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from study_tool.corpus_writer import load_meta

SUPPORTED_META_VERSION = 1


@dataclass(frozen=True)
class CorpusMeta:
    symbol: str
    from_date: str
    to_date: str
    interval: str
    price_scale: int
    shadow_count: int
    seed: int
    median_sub_gap: float
    shadow_offsets: List[float]
    resolution_window_bars: int
    bar_count: int

    def offset_for(self, shadow_id: Optional[float]) -> float:
        """
        The price shift applied to this shadow's ladder.

        Real events carry shadow_id None and an unshifted ladder, so they get
        0.0. Anything else must be a known shadow: defaulting an unknown id to
        zero would quietly measure a shadow against the real ladder's targets.
        """
        if shadow_id is None or (isinstance(shadow_id, float) and shadow_id != shadow_id):
            return 0.0
        index = int(shadow_id)
        if not 0 <= index < len(self.shadow_offsets):
            raise KeyError(
                f"shadow id {shadow_id} is outside the "
                f"{len(self.shadow_offsets)} offsets in meta.json"
            )
        return self.shadow_offsets[index]


def load_corpus_meta(corpus_dir: Union[str, Path]) -> CorpusMeta:
    """
    Read and validate meta.json.

    Raises:
        FileNotFoundError: naming the backfill script, because a corpus built
            before meta.json existed is the common case.
        ValueError: on an unsupported layout version.
    """
    try:
        raw = load_meta(corpus_dir)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"{corpus_dir} has no meta.json; mining cannot guess the shadow "
            "offsets. Run scripts/backfill_corpus_meta.py to write one."
        ) from exc

    version = raw["corpus_meta_version"]
    if version != SUPPORTED_META_VERSION:
        raise ValueError(
            f"corpus_meta_version {version} but this code supports "
            f"{SUPPORTED_META_VERSION}"
        )

    return CorpusMeta(
        symbol=raw["symbol"],
        from_date=raw["from_date"],
        to_date=raw["to_date"],
        interval=raw["interval"],
        price_scale=int(raw["price_scale"]),
        shadow_count=int(raw["shadow_count"]),
        seed=int(raw["seed"]),
        median_sub_gap=float(raw["median_sub_gap"]),
        shadow_offsets=[float(o) for o in raw["shadow_offsets"]],
        resolution_window_bars=int(raw["resolution_window_bars"]),
        bar_count=int(raw["bar_count"]),
    )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_corpus_meta.py -q`
Expected: `6 passed`

- [ ] **Step 6: Commit**

```bash
git add gann-visualizer/backend/study_tool/mining/__init__.py gann-visualizer/backend/study_tool/mining/corpus_meta.py
git add -f gann-visualizer/backend/tests/study_tool/mining/test_corpus_meta.py
git commit -m "feat: mining reads the corpus metadata or refuses to start

A wrong shadow offset does not crash. It moves every shadow target to an
arbitrary price and the report still prints a percentage, which is the worst
possible failure mode here. So the gate is at load time and it is loud, and
an unknown shadow id raises rather than defaulting to zero."
```

---

### Task 4: Close the explore/holdout boundary leak

An event's outcome is forward-looking. A breach opening in the last 50 bars of
the explore slice has its resolution decided by holdout bars. That is 0.1% of
events, and it is a leak in the one mechanism protecting every later conclusion.

**Files:**
- Create: `gann-visualizer/backend/study_tool/mining/boundary.py`
- Test: `gann-visualizer/backend/tests/study_tool/mining/test_boundary.py`

- [ ] **Step 1: Write the failing test**

Create `gann-visualizer/backend/tests/study_tool/mining/test_boundary.py`:

```python
"""
The buffer at the explore/holdout boundary.

Outcomes look forward 50 bars. An explore event opening within 50 bars of the
boundary has its outcome decided by holdout price action, so mining drops it.
The count dropped is returned rather than logged quietly - the cost of the
buffer should be visible in the report.
"""
import sys
import os

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.boundary import (
    BufferedEvents, boundary_bar_index, drop_boundary_events,
)


def events_frame(n=100, holdout_from=75):
    return pd.DataFrame({
        "bar_index": list(range(n)),
        "slice": ["explore" if i < holdout_from else "holdout"
                  for i in range(n)],
        "event_type": ["LADDER_TOUCH"] * n,
    })


def test_boundary_is_the_first_holdout_bar():
    assert boundary_bar_index(events_frame()) == 75


def test_boundary_raises_when_there_is_no_holdout():
    """A corpus with no holdout means the split never ran. Do not guess."""
    frame = events_frame(holdout_from=100)
    with pytest.raises(ValueError, match="no holdout"):
        boundary_bar_index(frame)


def test_events_inside_the_buffer_are_dropped():
    explore = events_frame()[lambda f: f["slice"] == "explore"]

    result = drop_boundary_events(explore, boundary=75, buffer_bars=50)

    assert isinstance(result, BufferedEvents)
    assert result.events["bar_index"].max() < 25
    assert result.dropped == 50
    assert result.boundary == 75
    assert result.buffer_bars == 50


def test_a_kept_event_is_far_enough_back_to_resolve_inside_explore():
    """
    The invariant, stated as arithmetic: the last kept bar plus the forward
    window must still land before the first holdout bar.
    """
    explore = events_frame()[lambda f: f["slice"] == "explore"]

    result = drop_boundary_events(explore, boundary=75, buffer_bars=50)

    assert result.events["bar_index"].max() + 50 <= 75


def test_a_zero_buffer_drops_nothing():
    explore = events_frame()[lambda f: f["slice"] == "explore"]

    result = drop_boundary_events(explore, boundary=75, buffer_bars=0)

    assert result.dropped == 0
    assert len(result.events) == 75


def test_dropping_everything_raises_rather_than_returning_an_empty_frame():
    """
    A silent empty frame downstream produces a report full of None. Better to
    stop with the reason.
    """
    explore = events_frame()[lambda f: f["slice"] == "explore"]

    with pytest.raises(ValueError, match="buffer"):
        drop_boundary_events(explore, boundary=75, buffer_bars=200)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_boundary.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'study_tool.mining.boundary'`

- [ ] **Step 3: Write the implementation**

Create `gann-visualizer/backend/study_tool/mining/boundary.py`:

```python
"""
The buffer that stops holdout price action leaking into the explore slice.

Every outcome in this corpus looks forward: a breach is resolved by the next
50 bars, mfe/mae read the next 50 bars, and the reach-next-level race runs over
the next 50 bars. So an explore event opening in the last 50 bars of the
explore slice has its outcome decided by holdout data, even though the row
itself is labelled explore.

It is about 50 bars out of 37,110 - roughly 0.1% of events - which is exactly
why it would never be noticed. It is also a leak in the single mechanism every
later conclusion depends on, so it is closed rather than tolerated, and the
number dropped is returned so the cost is visible in the report.
"""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class BufferedEvents:
    events: pd.DataFrame
    dropped: int
    boundary: int
    buffer_bars: int


def boundary_bar_index(events: pd.DataFrame) -> int:
    """
    The first bar index that belongs to the holdout.

    Reads only `bar_index` and `slice`. That is structural bookkeeping, not
    price action or outcomes, so it does not spend the holdout.

    Raises:
        ValueError: if no row is labelled holdout. A corpus with no holdout
            never had the split applied, and guessing a boundary would place
            the buffer somewhere meaningless.
    """
    holdout = events[events["slice"] == "holdout"]
    if holdout.empty:
        raise ValueError(
            "no holdout rows in this events frame; the explore/holdout split "
            "was never applied, so there is no boundary to buffer"
        )
    return int(holdout["bar_index"].min())


def drop_boundary_events(explore_events: pd.DataFrame, boundary: int,
                         buffer_bars: int) -> BufferedEvents:
    """
    Drop explore events whose forward window reaches past `boundary`.

    An event at bar b reads bars up to b + buffer_bars, so it is safe only
    when b + buffer_bars <= boundary.

    Raises:
        ValueError: if that leaves nothing. An empty frame downstream produces
            a report full of Nones rather than an error.
    """
    cutoff = boundary - buffer_bars
    kept = explore_events[explore_events["bar_index"] <= cutoff]
    dropped = len(explore_events) - len(kept)

    if kept.empty:
        raise ValueError(
            f"a {buffer_bars}-bar buffer before boundary {boundary} drops "
            f"every one of the {len(explore_events)} explore events"
        )

    return BufferedEvents(
        events=kept.reset_index(drop=True),
        dropped=dropped,
        boundary=boundary,
        buffer_bars=buffer_bars,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_boundary.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/study_tool/mining/boundary.py
git add -f gann-visualizer/backend/tests/study_tool/mining/test_boundary.py
git commit -m "fix: drop explore events whose forward window reaches the holdout

Outcomes look forward 50 bars, so an explore event in the last 50 bars of the
slice is resolved by holdout data. About 0.1% of events, which is why it would
never be noticed, and a leak in the one mechanism protecting every later
conclusion.

The boundary is computed from the data rather than hard-coded, and the number
dropped is returned so the cost lands in the report instead of a log line."
```

---

### Task 5: The measuring device

**Files:**
- Create: `gann-visualizer/backend/study_tool/mining/shadow_compare.py`
- Test: `gann-visualizer/backend/tests/study_tool/mining/test_shadow_compare.py`

- [ ] **Step 1: Write the failing test**

Create `gann-visualizer/backend/tests/study_tool/mining/test_shadow_compare.py`:

```python
"""
compare(): run one statistic on the real events and on every shadow.

Built once so every future question inherits the control automatically,
instead of depending on someone remembering to apply it.
"""
import sys
import os

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.shadow_compare import Comparison, Stat, compare


def frame(real_value, shadow_values):
    """One row per shadow id (and None for real), carrying a `v` column."""
    rows = [{"shadow_id": None, "v": real_value}]
    for shadow_id, value in enumerate(shadow_values):
        rows.append({"shadow_id": float(shadow_id), "v": value})
    return pd.DataFrame(rows)


def mean_v(events):
    values = events["v"].dropna()
    if len(values) == 0:
        return Stat(None, 0)
    return Stat(float(values.mean()), len(values))


def test_reports_the_real_value_and_every_shadow_value():
    result = compare(frame(9.0, [1.0, 2.0, 3.0]), mean_v, shadow_count=3)

    assert isinstance(result, Comparison)
    assert result.real == 9.0
    assert result.shadows == [1.0, 2.0, 3.0]
    assert result.n == 1


def test_percentile_is_the_share_of_shadows_below_the_real_value():
    result = compare(frame(2.5, [1.0, 2.0, 3.0, 4.0]), mean_v, shadow_count=4)

    assert result.percentile == 50.0


def test_a_real_value_above_every_shadow_is_flagged_outside_the_range():
    result = compare(frame(9.0, [1.0, 2.0, 3.0]), mean_v, shadow_count=3)

    assert result.outside_range is True
    assert result.margin == pytest.approx(6.0)


def test_a_real_value_below_every_shadow_is_also_outside_the_range():
    """Under-performing the control is a finding too, not an absence of one."""
    result = compare(frame(0.5, [1.0, 2.0, 3.0]), mean_v, shadow_count=3)

    assert result.outside_range is True
    assert result.margin == pytest.approx(-0.5)


def test_a_real_value_inside_the_spread_is_not_flagged():
    result = compare(frame(2.0, [1.0, 2.0, 3.0]), mean_v, shadow_count=3)

    assert result.outside_range is False
    assert result.margin == 0.0


def test_shadow_summary_statistics_are_reported():
    result = compare(frame(2.0, [1.0, 2.0, 6.0]), mean_v, shadow_count=3)

    assert result.shadow_min == 1.0
    assert result.shadow_median == 2.0
    assert result.shadow_max == 6.0


def test_an_undefined_statistic_propagates_as_none_not_zero():
    """
    A zero denominator is 'we cannot say', not 'the rate is zero'. Zero would
    read as a strong finding.
    """
    empty = pd.DataFrame({"shadow_id": pd.Series(dtype="float64"),
                          "v": pd.Series(dtype="float64")})

    result = compare(empty, mean_v, shadow_count=3)

    assert result.real is None
    assert result.percentile is None
    assert result.outside_range is False
    assert result.n == 0


def test_shadows_with_no_rows_are_skipped_not_counted_as_zero():
    events = frame(9.0, [1.0, 2.0])  # shadow 2 has no rows at all

    result = compare(events, mean_v, shadow_count=3)

    assert result.shadows == [1.0, 2.0]
    assert result.shadows_missing == 1


def test_sample_size_travels_with_the_result():
    """A 100% rate from four events is noise and must not read as a finding."""
    events = pd.DataFrame([
        {"shadow_id": None, "v": 1.0},
        {"shadow_id": None, "v": 1.0},
        {"shadow_id": 0.0, "v": 1.0},
    ])

    assert compare(events, mean_v, shadow_count=1).n == 2
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_shadow_compare.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'study_tool.mining.shadow_compare'`

- [ ] **Step 3: Write the implementation**

Create `gann-visualizer/backend/study_tool/mining/shadow_compare.py`:

```python
"""
One comparison, reused for every question.

`compare` takes a slice of events - real rows and shadow rows together - and a
statistic. It runs the statistic on the real rows and once per shadow, then
places the real value in the shadow spread.

Building this once means every future question inherits the control
automatically, instead of depending on someone remembering to apply it. That
is the entire reason this file exists.
"""

import statistics as _stats
from dataclasses import dataclass, field
from typing import Callable, List, NamedTuple, Optional

import pandas as pd


class Stat(NamedTuple):
    """
    A statistic and the number of rows behind it.

    Sample size travels with the value rather than beside it. A 100% hold rate
    from four events is noise, and separating the two invites printing the
    percentage without it.
    """
    value: Optional[float]
    n: int


StatisticFn = Callable[[pd.DataFrame], Stat]


@dataclass(frozen=True)
class Comparison:
    real: Optional[float]
    n: int
    shadows: List[float] = field(default_factory=list)
    shadows_missing: int = 0

    @property
    def shadow_min(self) -> Optional[float]:
        return min(self.shadows) if self.shadows else None

    @property
    def shadow_max(self) -> Optional[float]:
        return max(self.shadows) if self.shadows else None

    @property
    def shadow_median(self) -> Optional[float]:
        return _stats.median(self.shadows) if self.shadows else None

    @property
    def percentile(self) -> Optional[float]:
        """Share of shadows strictly below the real value, as a percentage."""
        if self.real is None or not self.shadows:
            return None
        below = sum(1 for s in self.shadows if s < self.real)
        return 100.0 * below / len(self.shadows)

    @property
    def outside_range(self) -> bool:
        """True when real beats or trails every shadow."""
        if self.real is None or not self.shadows:
            return False
        return self.real > self.shadow_max or self.real < self.shadow_min

    @property
    def margin(self) -> float:
        """
        Distance past the shadow range: positive above, negative below, 0 inside.

        Sorting the shortlist by percentile alone cannot separate two groups
        that both sit above all 50 shadows.
        """
        if not self.outside_range:
            return 0.0
        if self.real > self.shadow_max:
            return self.real - self.shadow_max
        return self.real - self.shadow_min


def compare(events: pd.DataFrame, statistic_fn: StatisticFn,
            shadow_count: int) -> Comparison:
    """
    Run `statistic_fn` on the real rows and on each shadow's rows.

    Args:
        events: rows for one group, real and shadow together. Real rows carry
            a null `shadow_id`.
        statistic_fn: events frame -> Stat. Returns Stat(None, n) when the
            statistic is undefined.
        shadow_count: how many shadows the corpus holds. Taken from meta
            rather than from the data, so a shadow that produced no rows in
            this group is counted as missing instead of vanishing.

    A shadow with no rows contributes nothing and is counted in
    `shadows_missing`. Substituting zero would drag the spread down and make
    the real value look extreme.
    """
    is_real = events["shadow_id"].isna()
    real_stat = statistic_fn(events[is_real])

    shadow_values: List[float] = []
    missing = 0
    grouped = {int(key): frame
               for key, frame in events[~is_real].groupby("shadow_id")}

    for shadow_id in range(shadow_count):
        rows = grouped.get(shadow_id)
        if rows is None or len(rows) == 0:
            missing += 1
            continue
        value = statistic_fn(rows).value
        if value is None:
            missing += 1
            continue
        shadow_values.append(value)

    return Comparison(
        real=real_stat.value,
        n=real_stat.n,
        shadows=shadow_values,
        shadows_missing=missing,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_shadow_compare.py -q`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/study_tool/mining/shadow_compare.py
git add -f gann-visualizer/backend/tests/study_tool/mining/test_shadow_compare.py
git commit -m "feat: one comparison every statistic inherits the control from

compare() runs a statistic on the real events and on each shadow, then places
the real value in the shadow spread. Written once so no future question can
be asked without its control.

Sample size travels inside the Stat rather than beside it, and an undefined
statistic propagates as None rather than zero - a zero denominator means 'we
cannot say', and zero would read as a strong finding."
```

---

### Task 6: The five statistics

**Files:**
- Create: `gann-visualizer/backend/study_tool/mining/statistics.py`
- Test: `gann-visualizer/backend/tests/study_tool/mining/test_statistics.py`

Note on shapes: four of the five are pure `frame -> Stat`. Touch density also
needs a bar count, and reach-next-level needs the race outcome, which costs a
ladder rebuild. Both are handled by binding: `touch_density_fn(bar_count)`
returns a closure, and the race writes a `reach_outcome` column onto the frame
in Task 8 before `compare` ever runs. Everything `compare` sees stays
`frame -> Stat`.

- [ ] **Step 1: Write the failing test**

Create `gann-visualizer/backend/tests/study_tool/mining/test_statistics.py`:

```python
"""
The five statistics. Each is a pure function from an events frame to a value
and its sample size.

`depth_in_sublevels` is not a column - it lives inside the `details` JSON
string on LADDER_RETEST rows - so mean_retest_depth parses it. That is pinned
by a test because it is the kind of thing a refactor silently breaks.
"""
import sys
import os
import json

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.statistics import (
    hold_rate, mean_retest_depth, reach_next_rate, rejection_rate,
    timeout_share, touch_density_fn,
)


def resolved(outcomes):
    return pd.DataFrame({
        "event_type": ["LADDER_BREACH_RESOLVED"] * len(outcomes),
        "outcome": outcomes,
    })


def test_hold_rate_counts_only_breaches_that_came_back():
    frame = resolved(["RETEST_HELD", "RETEST_HELD", "RETEST_FAILED",
                      "NEVER_RETESTED", "NEVER_CONFIRMED"])

    stat = hold_rate(frame)

    assert stat.value == 2 / 3
    assert stat.n == 3, "n must be the retested breaches, not all rows"


def test_hold_rate_is_none_when_nothing_was_retested():
    stat = hold_rate(resolved(["NEVER_RETESTED", "NEVER_CONFIRMED"]))

    assert stat.value is None
    assert stat.n == 0


def test_rejection_rate_is_never_confirmed_over_all_resolved():
    frame = resolved(["NEVER_CONFIRMED", "RETEST_HELD", "RETEST_FAILED",
                      "NEVER_RETESTED"])

    stat = rejection_rate(frame)

    assert stat.value == 0.25
    assert stat.n == 4


def test_rejection_rate_ignores_truncated_breaches():
    """
    A breach still open when the data ended has outcome None. It is neither a
    rejection nor a confirmation, and counting it either way biases the rate.
    """
    frame = resolved(["NEVER_CONFIRMED", "RETEST_HELD", None])

    stat = rejection_rate(frame)

    assert stat.n == 2
    assert stat.value == 0.5


def test_mean_retest_depth_reads_depth_out_of_the_details_json():
    frame = pd.DataFrame({
        "event_type": ["LADDER_RETEST", "LADDER_RETEST", "LADDER_TOUCH"],
        "details": [json.dumps({"depth_in_sublevels": 0.4}),
                    json.dumps({"depth_in_sublevels": 0.8}),
                    json.dumps({"depth_in_sublevels": 99.0})],
    })

    stat = mean_retest_depth(frame)

    assert stat.value == pytest.approx(0.6)
    assert stat.n == 2, "the LADDER_TOUCH row must not be counted"


def test_mean_retest_depth_survives_a_details_string_without_the_key():
    frame = pd.DataFrame({
        "event_type": ["LADDER_RETEST", "LADDER_RETEST"],
        "details": [json.dumps({"depth_in_sublevels": 0.4}),
                    json.dumps({"retest_extreme": 12.0})],
    })

    stat = mean_retest_depth(frame)

    assert stat.value == 0.4
    assert stat.n == 1


def test_touch_density_is_touches_per_bar():
    frame = pd.DataFrame({"event_type": ["LADDER_TOUCH"] * 30 +
                                        ["LADDER_CROSS"] * 5})

    stat = touch_density_fn(bar_count=10)(frame)

    assert stat.value == 3.0
    assert stat.n == 30


def test_touch_density_is_none_for_zero_bars():
    frame = pd.DataFrame({"event_type": ["LADDER_TOUCH"]})

    assert touch_density_fn(bar_count=0)(frame).value is None


def test_reach_next_rate_excludes_timeouts_from_the_ratio():
    """A timeout is neither a win nor a loss, so it must not dilute either."""
    frame = pd.DataFrame({
        "reach_outcome": ["REACHED", "REACHED", "STOPPED", "TIMEOUT",
                          "TIMEOUT", None],
    })

    stat = reach_next_rate(frame)

    assert stat.value == 2 / 3
    assert stat.n == 3


def test_timeout_share_reports_what_reach_next_rate_dropped():
    frame = pd.DataFrame({
        "reach_outcome": ["REACHED", "STOPPED", "TIMEOUT", "TIMEOUT"],
    })

    stat = timeout_share(frame)

    assert stat.value == 0.5
    assert stat.n == 4


def test_every_statistic_returns_none_on_an_empty_frame():
    empty = pd.DataFrame({"event_type": pd.Series(dtype="object"),
                          "outcome": pd.Series(dtype="object"),
                          "details": pd.Series(dtype="object"),
                          "reach_outcome": pd.Series(dtype="object")})

    for fn in (hold_rate, rejection_rate, mean_retest_depth,
               reach_next_rate, timeout_share, touch_density_fn(100)):
        assert fn(empty).value is None, fn
        assert fn(empty).n == 0, fn
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_statistics.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'study_tool.mining.statistics'`

- [ ] **Step 3: Write the implementation**

Create `gann-visualizer/backend/study_tool/mining/statistics.py`:

```python
"""
The five questions asked of the corpus, each a pure function of an events
frame.

Every one returns Stat(value, n), and returns None rather than 0.0 when its
denominator is empty. A zero denominator means 'this group cannot answer', and
printing 0.0 would read as a strong negative finding.

Touch density is a fairness check, not a finding. Real and shadow ladders
should be touched at similar rates; a large gap means the two get different
exposure and every other comparison in the report is suspect. Read it first.
"""

import json
from typing import Callable, Optional

import pandas as pd

from study_tool.mining.shadow_compare import Stat

RETESTED = ("RETEST_HELD", "RETEST_FAILED")
RESOLVED_OUTCOMES = ("RETEST_HELD", "RETEST_FAILED", "NEVER_RETESTED",
                     "NEVER_CONFIRMED")

StatisticFn = Callable[[pd.DataFrame], Stat]


def _resolved(events: pd.DataFrame) -> pd.DataFrame:
    if "outcome" not in events.columns:
        return events.iloc[0:0]
    return events[events["outcome"].isin(RESOLVED_OUTCOMES)]


def hold_rate(events: pd.DataFrame) -> Stat:
    """
    RETEST_HELD / (RETEST_HELD + RETEST_FAILED).

    Of the breaches that came back to the level, how many held. Breaches that
    never came back are excluded: they answer a different question.
    """
    retested = _resolved(events)
    retested = retested[retested["outcome"].isin(RETESTED)]
    if retested.empty:
        return Stat(None, 0)
    held = int((retested["outcome"] == "RETEST_HELD").sum())
    return Stat(held / len(retested), len(retested))


def rejection_rate(events: pd.DataFrame) -> Stat:
    """
    NEVER_CONFIRMED / all resolved breaches.

    How often price crossed a level but could not hold past it. Breaches still
    open when the data ended carry outcome None and are excluded - they are
    neither a rejection nor a confirmation.
    """
    resolved = _resolved(events)
    if resolved.empty:
        return Stat(None, 0)
    rejected = int((resolved["outcome"] == "NEVER_CONFIRMED").sum())
    return Stat(rejected / len(resolved), len(resolved))


def _depth(details: object) -> Optional[float]:
    """
    depth_in_sublevels out of the details JSON string.

    It is not a column. The analyzer writes it into `details`
    (gann_ladder_analyzer.py:343) and build_gann_corpus stores that dict as a
    JSON string, so it has to be parsed back out here.
    """
    if not isinstance(details, str):
        return None
    try:
        parsed = json.loads(details)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    value = parsed.get("depth_in_sublevels")
    return float(value) if isinstance(value, (int, float)) else None


def mean_retest_depth(events: pd.DataFrame) -> Stat:
    """Mean `depth_in_sublevels` over LADDER_RETEST events."""
    if "details" not in events.columns:
        return Stat(None, 0)
    retests = events[events["event_type"] == "LADDER_RETEST"]
    depths = [d for d in (_depth(v) for v in retests["details"]) if d is not None]
    if not depths:
        return Stat(None, 0)
    return Stat(sum(depths) / len(depths), len(depths))


def touch_density_fn(bar_count: int) -> StatisticFn:
    """
    Touches per bar, as a statistic bound to a bar count.

    Bound rather than passed, so compare() only ever sees frame -> Stat.

    This is the fairness check. If the real ladder and the shadows are touched
    at very different rates they are not comparable twins, and every other
    number in the report is suspect. Read it before anything else.
    """
    def touch_density(events: pd.DataFrame) -> Stat:
        touches = int((events["event_type"] == "LADDER_TOUCH").sum())
        if bar_count <= 0 or touches == 0:
            return Stat(None, touches)
        return Stat(touches / bar_count, touches)

    return touch_density


def reach_next_rate(events: pd.DataFrame) -> Stat:
    """
    REACHED / (REACHED + STOPPED). The headline hypothesis.

    Timeouts are excluded: a race that ran out of window is neither a win nor
    a loss, and folding it into either side would move the rate for a reason
    that has nothing to do with the levels. `timeout_share` reports them.

    Reads the `reach_outcome` column written by ladder_rebuild.
    """
    if "reach_outcome" not in events.columns:
        return Stat(None, 0)
    decided = events[events["reach_outcome"].isin(("REACHED", "STOPPED"))]
    if decided.empty:
        return Stat(None, 0)
    reached = int((decided["reach_outcome"] == "REACHED").sum())
    return Stat(reached / len(decided), len(decided))


def timeout_share(events: pd.DataFrame) -> Stat:
    """
    TIMEOUT / all raced breaches.

    Reported beside reach_next_rate so the excluded races are visible. A group
    whose races nearly all time out has a reach rate built on very little.
    """
    if "reach_outcome" not in events.columns:
        return Stat(None, 0)
    raced = events[events["reach_outcome"].isin(
        ("REACHED", "STOPPED", "TIMEOUT"))]
    if raced.empty:
        return Stat(None, 0)
    timeouts = int((raced["reach_outcome"] == "TIMEOUT").sum())
    return Stat(timeouts / len(raced), len(raced))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_statistics.py -q`
Expected: `11 passed`

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/study_tool/mining/statistics.py
git add -f gann-visualizer/backend/tests/study_tool/mining/test_statistics.py
git commit -m "feat: the five corpus statistics, each with its sample size

Touch density is the fairness check rather than a finding: if real and shadow
ladders are touched at different rates they are not comparable twins and
everything else in the report is suspect.

depth_in_sublevels is parsed out of the details JSON because it was never
lifted into a column. Timeouts are excluded from the reach rate and reported
separately - a race that ran out of window is neither a win nor a loss."
```

---

### Task 7: Groupings

**Files:**
- Create: `gann-visualizer/backend/study_tool/mining/groups.py`
- Test: `gann-visualizer/backend/tests/study_tool/mining/test_groups.py`

- [ ] **Step 1: Write the failing test**

Create `gann-visualizer/backend/tests/study_tool/mining/test_groups.py`:

```python
"""
The label groups every statistic is reported across.

Pooling can wash out a real effect: 41% on halfway levels and 22% everywhere
else averages to something that looks dead. So nothing is reported pooled
alone.
"""
import sys
import os

import pandas as pd

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.groups import (
    GROUPINGS, add_ring_bin, iter_groups,
)


def frame():
    return pd.DataFrame({
        "shadow_id": [None, None, 0.0, 0.0],
        "level_source": ["center", "sun", "center", "sun"],
        "level_degree": [0, 90, 0, 90],
        "level_sub_index": [1, None, 1, None],
        "level_is_halfway": [True, False, True, False],
        "level_ring": [3, 47, 3, 47],
        "level_kind": ["sub", "major", "sub", "major"],
    })


def test_the_six_spec_groupings_are_all_present():
    assert set(GROUPINGS) == {
        "level_source", "level_degree", "level_sub_index",
        "level_is_halfway", "level_ring_bin", "level_kind",
    }


def test_ring_bin_buckets_rings_so_groups_are_not_one_row_each():
    binned = add_ring_bin(frame(), width=10)

    assert list(binned["level_ring_bin"]) == ["0-9", "40-49", "0-9", "40-49"]


def test_iter_groups_yields_a_frame_per_distinct_value():
    binned = add_ring_bin(frame())

    found = dict(iter_groups(binned, "level_source"))

    assert set(found) == {"center", "sun"}
    assert len(found["center"]) == 2, "real and shadow rows must stay together"


def test_each_group_frame_keeps_both_real_and_shadow_rows():
    """
    compare() splits real from shadow itself. A grouping that dropped the
    shadows would silently remove the control.
    """
    binned = add_ring_bin(frame())

    _, group = next(iter(iter_groups(binned, "level_source")))

    assert group["shadow_id"].isna().any()
    assert group["shadow_id"].notna().any()


def test_null_group_values_become_their_own_labelled_group():
    """
    level_sub_index is null for majors. Dropping nulls would silently exclude
    every major level from the sub-index breakdown rather than showing them.
    """
    binned = add_ring_bin(frame())

    found = dict(iter_groups(binned, "level_sub_index"))

    assert "none" in found
    assert len(found["none"]) == 2


def test_groups_come_back_in_a_stable_order():
    """The report is diffed across runs, so ordering must not float."""
    binned = add_ring_bin(frame())

    first = [label for label, _ in iter_groups(binned, "level_source")]
    second = [label for label, _ in iter_groups(binned, "level_source")]

    assert first == second == sorted(first)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_groups.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'study_tool.mining.groups'`

- [ ] **Step 3: Write the implementation**

Create `gann-visualizer/backend/study_tool/mining/groups.py`:

```python
"""
The label groups every statistic is reported across.

Pooling hides signal. A 41% hold rate on halfway levels sitting beside 22%
everywhere else averages out to something that looks dead, so no statistic in
this phase is reported pooled on its own.

Every grouping keeps real and shadow rows together in the same frame, because
compare() does the real/shadow split itself. A grouping that dropped shadows
would remove the control without changing any output shape.
"""

from typing import Iterator, List, Tuple

import pandas as pd

GROUPINGS: Tuple[str, ...] = (
    "level_source",       # center / sun / moon
    "level_degree",       # 0, 45, ... 315 - the arm
    "level_sub_index",    # 1..7, null for majors
    "level_is_halfway",   # true / false
    "level_ring_bin",     # ring, bucketed
    "level_kind",         # major / sub
)

RING_BIN_WIDTH = 10
NULL_LABEL = "none"


def add_ring_bin(events: pd.DataFrame, width: int = RING_BIN_WIDTH) -> pd.DataFrame:
    """
    Add `level_ring_bin`, a bucketed copy of `level_ring`.

    Rings run into the dozens on a two-year corpus, so grouping on the raw
    ring would produce many groups of a handful of events each - every one of
    them noise, and every one of them a chance to land outside the shadow
    range by accident.
    """
    frame = events.copy()

    def label(ring) -> str:
        if pd.isna(ring):
            return NULL_LABEL
        low = (int(ring) // width) * width
        return f"{low}-{low + width - 1}"

    frame["level_ring_bin"] = frame["level_ring"].apply(label)
    return frame


def iter_groups(events: pd.DataFrame,
                column: str) -> Iterator[Tuple[str, pd.DataFrame]]:
    """
    Yield (label, rows) for each distinct value of `column`, in sorted order.

    Nulls become the group `"none"` rather than being dropped:
    level_sub_index is null for every major level, and dropping it would
    quietly exclude majors from that breakdown instead of showing them.

    Sorted so the Markdown report diffs cleanly across runs.
    """
    labelled = events[column].apply(
        lambda v: NULL_LABEL if pd.isna(v) else str(v))
    for label in sorted(labelled.unique()):
        yield label, events[labelled == label]


def grouping_columns() -> List[str]:
    """The groupings, as a list, for callers that want to iterate them."""
    return list(GROUPINGS)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_groups.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/study_tool/mining/groups.py
git add -f gann-visualizer/backend/tests/study_tool/mining/test_groups.py
git commit -m "feat: report every statistic per label group, never pooled alone

Pooling washes out an effect that lives in one group. Rings are bucketed
because raw rings would produce dozens of tiny groups, each one noise and
each one a fresh chance to fall outside the shadow range by accident.

Nulls become their own group rather than being dropped: level_sub_index is
null for every major, and dropping it would silently exclude majors."
```

---

### Task 8: Ladder rebuild and the reach-next-level race

The headline test. After a confirmed breach of level L in direction D, does
price reach the next level beyond L before closing back through L?

Two performance facts shape this file:

- **Do not cache whole ladders.** 14,641 keys × ~363 level dicts is 5.3 million
  dicts. Cache one sorted price array per (key, source) instead — about 42 MB.
- **Do not rebuild ladders for shadows.** A shadow ladder is the real ladder
  plus a constant, so a shadow's target is the real target plus that constant.
  Subtract the offset, look up in the real ladder, add it back. This is the
  whole reason `meta.json` was needed.

**Files:**
- Create: `gann-visualizer/backend/study_tool/mining/ladder_rebuild.py`
- Test: `gann-visualizer/backend/tests/study_tool/mining/test_ladder_rebuild.py`

- [ ] **Step 1: Write the failing test**

Create `gann-visualizer/backend/tests/study_tool/mining/test_ladder_rebuild.py`:

```python
"""
Rebuilding the ladder at a breach bar, and racing target against stop.

The corpus stores ladders as the three integers they are a pure function of,
so 'the next level up from here' has to be rebuilt. build_all_ladders reads
`price` only as int(round(price * scale)), which is exactly the stored
price_square, so the rebuild is exact rather than approximate - that is pinned
by a test.
"""
import sys
import os

import numpy as np
import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.corpus_meta import CorpusMeta
from study_tool.mining.ladder_rebuild import (
    LadderCache, add_reach_outcomes, race_to_next_level,
)
from study_tool.run_ladder_study import build_all_ladders, degree_to_square

SUN = degree_to_square(155.0)
MOON = degree_to_square(331.0)


def keys_frame():
    return pd.DataFrame({
        "bar_index": [0, 1],
        "price_square": [1307, 1307],
        "sun_square": [SUN, SUN],
        "moon_square": [MOON, MOON],
    })


def meta(shadow_offsets=(0.4,)):
    return CorpusMeta(
        symbol="RELIANCE", from_date="a", to_date="b", interval="5",
        price_scale=1, shadow_count=len(shadow_offsets), seed=7,
        median_sub_gap=2.25, shadow_offsets=list(shadow_offsets),
        resolution_window_bars=50, bar_count=2,
    )


def test_rebuilt_prices_match_a_direct_build_exactly():
    cache = LadderCache(keys_frame(), price_scale=1)
    direct = sorted(l["price"] for l in build_all_ladders(1307, 1, SUN, MOON)
                    if l["source"] == "center")

    rebuilt = list(cache.prices(bar_index=0, source="center"))

    assert rebuilt == pytest.approx(direct)


def test_the_grid_is_built_once_per_distinct_key(monkeypatch):
    """
    14,641 distinct keys at 6.3 ms each is 92 seconds. Rebuilding per event
    would be 14,803 real breaches plus 740,000 shadow ones.
    """
    from study_tool.mining import ladder_rebuild

    calls = {"n": 0}
    real = ladder_rebuild.build_all_ladders

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(ladder_rebuild, "build_all_ladders", counting)

    cache = LadderCache(keys_frame(), price_scale=1)
    for _ in range(20):
        cache.prices(bar_index=0, source="center")
        cache.prices(bar_index=1, source="sun")

    assert calls["n"] == 1, f"{calls['n']} builds for one distinct key"


def test_next_level_up_is_the_smallest_price_above_the_breached_one():
    cache = LadderCache(keys_frame(), price_scale=1)
    prices = list(cache.prices(bar_index=0, source="center"))
    level = prices[len(prices) // 2]

    target = cache.next_level(bar_index=0, source="center",
                              level_price=level, direction="up", offset=0.0)

    assert target > level
    assert target == pytest.approx(min(p for p in prices if p > level))


def test_next_level_down_is_the_largest_price_below():
    cache = LadderCache(keys_frame(), price_scale=1)
    prices = list(cache.prices(bar_index=0, source="center"))
    level = prices[len(prices) // 2]

    target = cache.next_level(bar_index=0, source="center",
                              level_price=level, direction="down", offset=0.0)

    assert target == pytest.approx(max(p for p in prices if p < level))


def test_a_shadow_target_is_the_real_target_shifted_by_its_offset():
    """
    The reason meta.json exists. A shadow ladder is the real one plus a
    constant, so subtracting the offset, looking up, and adding it back gives
    the shadow's own next level without rebuilding anything.
    """
    cache = LadderCache(keys_frame(), price_scale=1)
    prices = list(cache.prices(bar_index=0, source="center"))
    level = prices[len(prices) // 2]

    real_target = cache.next_level(0, "center", level, "up", offset=0.0)
    shadow_target = cache.next_level(0, "center", level + 0.4, "up", offset=0.4)

    assert shadow_target == pytest.approx(real_target + 0.4)


def test_next_level_returns_none_past_the_end_of_the_ladder():
    """The ladder is finite. Beyond its top there is no next level to reach."""
    cache = LadderCache(keys_frame(), price_scale=1)
    top = max(cache.prices(bar_index=0, source="center"))

    assert cache.next_level(0, "center", top, "up", offset=0.0) is None


def test_race_reaches_the_target():
    highs = np.array([100.0, 101.0, 105.0])
    lows = np.array([99.0, 100.0, 101.0])
    closes = np.array([100.0, 101.0, 104.0])

    assert race_to_next_level(highs, lows, closes, start=0, level_price=99.5,
                              target=104.5, direction="up", window=50) == "REACHED"


def test_race_stops_when_price_closes_back_through_the_level():
    highs = np.array([100.0, 101.0, 101.0])
    lows = np.array([99.0, 98.0, 97.0])
    closes = np.array([100.0, 99.0, 98.0])

    assert race_to_next_level(highs, lows, closes, start=0, level_price=99.5,
                              target=104.5, direction="up", window=50) == "STOPPED"


def test_race_times_out_when_neither_happens_in_the_window():
    highs = np.array([100.0] * 10)
    lows = np.array([99.9] * 10)
    closes = np.array([100.0] * 10)

    assert race_to_next_level(highs, lows, closes, start=0, level_price=99.5,
                              target=104.5, direction="up", window=5) == "TIMEOUT"


def test_a_bar_that_both_reaches_and_closes_back_counts_as_reached():
    """
    The target is a high, which happens during the bar. The stop is a close,
    which happens at its end. So within one bar the target came first. This is
    a real judgement call, so it is pinned rather than left to reading order.
    """
    highs = np.array([100.0, 106.0])
    lows = np.array([99.0, 98.0])
    closes = np.array([100.0, 98.5])

    assert race_to_next_level(highs, lows, closes, start=0, level_price=99.5,
                              target=104.5, direction="up", window=50) == "REACHED"


def test_race_runs_down_as_well_as_up():
    highs = np.array([100.0, 100.0, 100.0])
    lows = np.array([99.0, 98.0, 94.0])
    closes = np.array([100.0, 99.0, 95.0])

    assert race_to_next_level(highs, lows, closes, start=0, level_price=100.5,
                              target=94.5, direction="down", window=50) == "REACHED"


def test_race_truncated_by_the_end_of_data_is_a_timeout_not_a_loss():
    highs = np.array([100.0, 101.0])
    lows = np.array([99.0, 100.0])
    closes = np.array([100.0, 101.0])

    assert race_to_next_level(highs, lows, closes, start=0, level_price=99.5,
                              target=104.5, direction="up", window=50) == "TIMEOUT"


def test_add_reach_outcomes_labels_only_confirmed_breaches():
    events = pd.DataFrame({
        "event_type": ["LADDER_BREACH_CONFIRMED", "LADDER_TOUCH"],
        "bar_index": [0, 0],
        "shadow_id": [None, None],
        "level_source": ["center", "center"],
        "level_price": [1307.0, 1307.0],
        "direction": ["up", None],
    })
    bars = pd.DataFrame({
        "high": [1310.0, 1400.0], "low": [1300.0, 1305.0],
        "close": [1308.0, 1390.0],
    })

    result = add_reach_outcomes(events, bars, LadderCache(keys_frame(), 1),
                                meta())

    assert result.loc[1, "reach_outcome"] is None
    assert result.loc[0, "reach_outcome"] in ("REACHED", "STOPPED", "TIMEOUT")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_ladder_rebuild.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'study_tool.mining.ladder_rebuild'`

- [ ] **Step 3: Write the implementation**

Create `gann-visualizer/backend/study_tool/mining/ladder_rebuild.py`:

```python
"""
Rebuilding the ladder at a bar, and racing the next level against the stop.

The corpus stores each bar's ladder as the three integers it is a pure
function of, not as a snapshot - a snapshot per rebuild would be tens of
millions of rows. So 'the next level beyond L' means rebuilding.

Two things keep that affordable:

  Only prices are cached, not level dicts. 14,641 distinct keys times ~363
  levels is 5.3 million dicts; one sorted float array per (key, source) is
  about 42 MB.

  Shadows never rebuild. A shadow ladder is the real ladder plus a constant,
  so a shadow's next level is the real next level plus that same constant.
  Subtract the offset, look up, add it back. This is exactly why the corpus
  had to start recording its offsets.
"""

import bisect
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from study_tool.mining.corpus_meta import CorpusMeta
from study_tool.run_ladder_study import build_all_ladders

CONFIRMED = "LADDER_BREACH_CONFIRMED"
REACHED, STOPPED, TIMEOUT = "REACHED", "STOPPED", "TIMEOUT"


class LadderCache:
    """
    Level prices per bar, rebuilt once per distinct ladder key.

    build_all_ladders reads `price` only as int(round(price * price_scale)),
    which is exactly the `price_square` stored in ladder_keys. Dividing it back
    out therefore reproduces the build's ladder exactly, not approximately.
    """

    def __init__(self, ladder_keys: pd.DataFrame, price_scale: int):
        self.price_scale = price_scale
        self._key_by_bar: Dict[int, Tuple[int, int, int]] = {
            int(row.bar_index): (int(row.price_square), int(row.sun_square),
                                 int(row.moon_square))
            for row in ladder_keys.itertuples()
        }
        self._cache: Dict[Tuple[int, int, int], Dict[str, List[float]]] = {}

    def _ladder(self, key: Tuple[int, int, int]) -> Dict[str, List[float]]:
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        price_square, sun_square, moon_square = key
        levels = build_all_ladders(price_square / self.price_scale,
                                   self.price_scale, sun_square, moon_square)

        by_source: Dict[str, List[float]] = {}
        for level in levels:
            by_source.setdefault(level["source"], []).append(level["price"])
        for prices in by_source.values():
            prices.sort()

        self._cache[key] = by_source
        return by_source

    def prices(self, bar_index: int, source: str) -> List[float]:
        """Sorted level prices for one cross at one bar. Empty if unknown."""
        key = self._key_by_bar.get(int(bar_index))
        if key is None:
            return []
        return self._ladder(key).get(source, [])

    def next_level(self, bar_index: int, source: str, level_price: float,
                   direction: str, offset: float) -> Optional[float]:
        """
        The next level beyond `level_price` along `direction`, same cross.

        Args:
            offset: this shadow's price shift, 0.0 for real events. The lookup
                happens on the unshifted ladder and the shift is added back,
                so no shadow ladder is ever built.

        Returns None at the end of the ladder: it is finite, and beyond its
        last level there is no next level to reach.

        Same cross because the ladder is per-cross and the hypothesis is about
        progression along one cross.
        """
        prices = self.prices(bar_index, source)
        if not prices:
            return None

        unshifted = level_price - offset
        # A tolerance below one paise: level_price came back through Parquet
        # and an exact float match cannot be relied on.
        epsilon = 1e-6

        if direction == "up":
            index = bisect.bisect_right(prices, unshifted + epsilon)
            if index >= len(prices):
                return None
            return prices[index] + offset

        index = bisect.bisect_left(prices, unshifted - epsilon) - 1
        if index < 0:
            return None
        return prices[index] + offset


def race_to_next_level(highs: np.ndarray, lows: np.ndarray,
                       closes: np.ndarray, start: int, level_price: float,
                       target: float, direction: str, window: int) -> str:
    """
    Does price reach `target` before closing back through `level_price`?

    Returns REACHED, STOPPED or TIMEOUT. A race truncated by the end of the
    data is a TIMEOUT, not a loss.

    Within a single bar the target wins. The target is tested against the
    bar's high or low, which occur during the bar; the stop is tested against
    the close, which is the bar's last price. So if both conditions hold, the
    target came first. This is a judgement call and it is pinned by a test.
    """
    last = min(start + 1 + window, len(closes))
    for i in range(start + 1, last):
        if direction == "up":
            if highs[i] >= target:
                return REACHED
            if closes[i] < level_price:
                return STOPPED
        else:
            if lows[i] <= target:
                return REACHED
            if closes[i] > level_price:
                return STOPPED
    return TIMEOUT


def add_reach_outcomes(events: pd.DataFrame, bars: pd.DataFrame,
                       cache: LadderCache, meta: CorpusMeta) -> pd.DataFrame:
    """
    Add a `reach_outcome` column: REACHED / STOPPED / TIMEOUT, or None.

    None means the row was not raced - it is not a confirmed breach, or its
    cross had no next level beyond the breached one. None is not a loss and
    the statistics treat it as absent.

    Run before compare(), so every statistic stays a pure frame -> Stat.
    """
    highs = bars["high"].to_numpy(dtype=float)
    lows = bars["low"].to_numpy(dtype=float)
    closes = bars["close"].to_numpy(dtype=float)
    window = meta.resolution_window_bars

    frame = events.reset_index(drop=True)
    outcomes: List[Optional[str]] = [None] * len(frame)

    # Positional rather than label-based: the frame arrives from a filtered
    # slice, and iterating positions keeps the outcome list aligned with it.
    is_confirmed = (frame["event_type"] == CONFIRMED).to_numpy()

    for position in range(len(frame)):
        if not is_confirmed[position]:
            continue

        row = frame.iloc[position]
        direction = row["direction"]
        if direction not in ("up", "down"):
            continue

        level_price = float(row["level_price"])
        target = cache.next_level(
            bar_index=int(row["bar_index"]), source=row["level_source"],
            level_price=level_price, direction=direction,
            offset=meta.offset_for(row["shadow_id"]))
        if target is None:
            continue

        outcomes[position] = race_to_next_level(
            highs, lows, closes, start=int(row["bar_index"]),
            level_price=level_price, target=target,
            direction=direction, window=window)

    frame["reach_outcome"] = outcomes
    return frame
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_ladder_rebuild.py -q`
Expected: `13 passed`

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/study_tool/mining/ladder_rebuild.py
git add -f gann-visualizer/backend/tests/study_tool/mining/test_ladder_rebuild.py
git commit -m "feat: rebuild the ladder at a breach and race target against stop

The corpus stores ladders as the three integers they are a pure function of,
so the next level has to be rebuilt. Only sorted prices are cached, not level
dicts: 14,641 keys times 363 levels would be 5.3M dicts.

Shadows never rebuild. A shadow ladder is the real one plus a constant, so
its next level is the real next level plus that constant - which is the whole
reason the corpus now records its offsets.

Within one bar the target wins over the stop: the target is a high, which
happens during the bar, and the stop is a close, which is its last price."
```

---

### Task 9: The report and the entry point

**Files:**
- Create: `gann-visualizer/backend/study_tool/mining/report.py`
- Create: `gann-visualizer/backend/scripts/mine_gann_corpus.py`
- Test: `gann-visualizer/backend/tests/study_tool/mining/test_report.py`

- [ ] **Step 1: Write the failing test**

Create `gann-visualizer/backend/tests/study_tool/mining/test_report.py`:

```python
"""
The report.

Its output is a shortlist of candidates, not findings. A table of percentages
invites being read as results, so the document says what it is in its own
header rather than relying on the reader remembering.
"""
import sys
import os

import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.report import GroupResult, render_report
from study_tool.mining.shadow_compare import Comparison


def comparison(real, shadows, n):
    return Comparison(real=real, n=n, shadows=shadows)


def results():
    return [
        GroupResult("level_is_halfway", "True", "hold_rate",
                    comparison(0.41, [0.22, 0.24, 0.25], 900)),
        GroupResult("level_is_halfway", "False", "hold_rate",
                    comparison(0.23, [0.22, 0.24, 0.25], 4000)),
        GroupResult("level_degree", "90", "hold_rate",
                    comparison(0.99, [0.20, 0.30, 0.40], 4)),
    ]


def context():
    return {
        "corpus_dir": "logs/corpus/reliance_5m_x1",
        "symbol": "RELIANCE",
        "interval": "5",
        "price_scale": 1,
        "shadow_count": 3,
        "explore_events": 100000,
        "dropped_to_buffer": 132,
        "boundary_bar_index": 27833,
        "buffer_bars": 50,
        "touch_density": comparison(0.81, [0.79, 0.80, 0.82], 29963),
    }


def test_header_says_these_are_candidates_not_findings():
    text = render_report(results(), context())

    assert "candidates" in text.lower()
    assert "not findings" in text.lower()


def test_fairness_check_appears_before_any_statistic():
    text = render_report(results(), context())

    assert text.index("Fairness check") < text.index("hold_rate")


def test_the_buffer_cost_is_reported_rather_than_silent():
    text = render_report(results(), context())

    assert "132" in text
    assert "27833" in text


def test_shortlist_holds_only_groups_outside_the_whole_shadow_range():
    text = render_report(results(), context())
    shortlist = text.split("## Shortlist")[1]

    assert "level_is_halfway=True" in shortlist
    assert "level_is_halfway=False" not in shortlist


def test_every_shortlist_row_carries_its_sample_size():
    """A 99% rate from four events must not read like the strongest result."""
    text = render_report(results(), context())
    shortlist = text.split("## Shortlist")[1]

    assert "900" in shortlist
    assert "n=4" in shortlist or "| 4 " in shortlist


def test_a_none_valued_comparison_renders_as_dash_not_zero():
    empty = [GroupResult("level_degree", "45", "hold_rate",
                         comparison(None, [], 0))]

    text = render_report(empty, context())

    assert "0.000" not in text.split("## Per group")[1].split("## Shortlist")[0]


def test_the_report_is_stable_across_two_renders():
    """It is written to a file and diffed across runs."""
    assert render_report(results(), context()) == \
        render_report(results(), context())
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_report.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'study_tool.mining.report'`

- [ ] **Step 3: Write the report module**

Create `gann-visualizer/backend/study_tool/mining/report.py`:

```python
"""
The mining report.

What comes out of this phase is a shortlist of candidates to test later, not a
set of results. A table of percentages invites being read as findings, so the
document says what it is in its own header.

Order matters. The fairness check is first, because if the real ladder and the
shadows are touched at very different rates then every other number below it
is suspect and should not be read at all.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from study_tool.mining.shadow_compare import Comparison

HEADER = """# Gann Corpus Mining Report

**These are candidates, not findings.** Nothing below is confirmed. Every
number here comes from the explore slice, which the search has already seen,
so any group that looks strong is a hypothesis to test against the holdout -
once, in a batch, with the result recorded whichever way it falls.

No multiple-comparison correction is applied and none is needed, because
nothing here concludes. Correction belongs at holdout confirmation, against a
shortlist declared before that data is opened.
"""


@dataclass(frozen=True)
class GroupResult:
    grouping: str
    label: str
    statistic: str
    comparison: Comparison

    @property
    def name(self) -> str:
        return f"{self.grouping}={self.label}"


def _num(value: Optional[float], places: int = 4) -> str:
    """None renders as a dash. 0.0000 would read as a measured zero."""
    return "-" if value is None else f"{value:.{places}f}"


def _comparison_row(name: str, comparison: Comparison) -> str:
    return (
        f"| {name} | {_num(comparison.real)} | {comparison.n} | "
        f"{_num(comparison.shadow_min)} | {_num(comparison.shadow_median)} | "
        f"{_num(comparison.shadow_max)} | {_num(comparison.percentile, 1)} |"
    )


TABLE_HEAD = ("| group | real | n | shadow min | shadow median | "
              "shadow max | pct |\n|---|---|---|---|---|---|---|")


def _fairness_section(context: Dict) -> str:
    touch = context["touch_density"]
    lines = [
        "## Fairness check - read this first",
        "",
        "Touches per bar, real against shadow. These should be close. A large",
        "gap means the two ladders get different exposure to price, and every",
        "comparison below it is measuring that gap rather than the levels.",
        "",
        TABLE_HEAD,
        _comparison_row("touch_density", touch),
        "",
    ]
    return "\n".join(lines)


def _context_section(context: Dict) -> str:
    return "\n".join([
        "## Run",
        "",
        f"- corpus: `{context['corpus_dir']}`",
        f"- symbol: {context['symbol']}, interval {context['interval']}, "
        f"scale x{context['price_scale']}",
        f"- shadows: {context['shadow_count']}",
        f"- explore events used: {context['explore_events']}",
        f"- dropped to the boundary buffer: {context['dropped_to_buffer']} "
        f"(events within {context['buffer_bars']} bars of holdout boundary "
        f"bar {context['boundary_bar_index']}, whose outcomes would have been "
        "decided by holdout price action)",
        "",
    ])


def _per_group_section(results: List[GroupResult]) -> str:
    lines = ["## Per group", ""]
    for statistic in sorted({r.statistic for r in results}):
        lines += [f"### {statistic}", "", TABLE_HEAD]
        rows = [r for r in results if r.statistic == statistic]
        for result in sorted(rows, key=lambda r: (r.grouping, r.label)):
            lines.append(_comparison_row(result.name, result.comparison))
        lines.append("")
    return "\n".join(lines)


def _shortlist_section(results: List[GroupResult]) -> str:
    outside = [r for r in results if r.comparison.outside_range]
    outside.sort(key=lambda r: abs(r.comparison.margin), reverse=True)

    lines = [
        "## Shortlist",
        "",
        "Groups whose real value falls outside the **entire** shadow range,",
        "sorted by how far outside. Sample size is in the table because a",
        "rate built on a handful of events lands outside the range easily and",
        "means nothing.",
        "",
        "| group | statistic | real | n | shadow min | shadow max | margin |",
        "|---|---|---|---|---|---|---|",
    ]
    if not outside:
        lines.append("| _nothing fell outside the shadow range_ | | | | | | |")
    for result in outside:
        c = result.comparison
        lines.append(
            f"| {result.name} | {result.statistic} | {_num(c.real)} | "
            f"n={c.n} | {_num(c.shadow_min)} | {_num(c.shadow_max)} | "
            f"{_num(c.margin)} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_report(results: List[GroupResult], context: Dict) -> str:
    """
    The whole report as Markdown.

    Deterministic: every section sorts its rows, so two runs over the same
    corpus diff to nothing and a real change stands out.
    """
    return "\n".join([
        HEADER,
        _context_section(context),
        _fairness_section(context),
        _per_group_section(results),
        _shortlist_section(results),
    ])
```

- [ ] **Step 4: Run the report test to verify it passes**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_report.py -q`
Expected: `7 passed`

- [ ] **Step 5: Write the entry point**

Create `gann-visualizer/backend/scripts/mine_gann_corpus.py`:

```python
"""
Mine the Gann corpus against its shadow control and write the report.

Usage:
    python scripts/mine_gann_corpus.py --corpus logs/corpus/reliance_5m_x1 \
        --out docs/superpowers/reports

Reads the explore slice only. No script in this phase opens the holdout.
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Dict, List

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from study_tool.corpus_writer import load_events
from study_tool.mining.boundary import boundary_bar_index, drop_boundary_events
from study_tool.mining.corpus_meta import load_corpus_meta
from study_tool.mining.groups import GROUPINGS, add_ring_bin, iter_groups
from study_tool.mining.ladder_rebuild import LadderCache, add_reach_outcomes
from study_tool.mining.report import GroupResult, render_report
from study_tool.mining.shadow_compare import compare
from study_tool.mining.statistics import (
    hold_rate, mean_retest_depth, reach_next_rate, rejection_rate,
    timeout_share, touch_density_fn,
)


def run(corpus_dir: Path) -> str:
    """Mine one corpus and return the report Markdown."""
    meta = load_corpus_meta(corpus_dir)

    # Only bar_index and slice are read from the full events table, to find
    # the boundary. That is structural bookkeeping, not price action, so it
    # does not spend the holdout.
    all_slices = pd.read_parquet(corpus_dir / "events.parquet",
                                 columns=["bar_index", "slice"])
    boundary = boundary_bar_index(all_slices)
    del all_slices

    print(f"explore/holdout boundary at bar {boundary}")

    events = load_events(corpus_dir)
    buffered = drop_boundary_events(
        events, boundary=boundary, buffer_bars=meta.resolution_window_bars)
    print(f"dropped {buffered.dropped} events inside the "
          f"{meta.resolution_window_bars}-bar buffer")

    events = add_ring_bin(buffered.events)

    bars = pd.read_parquet(corpus_dir / "bars.parquet")
    keys = pd.read_parquet(corpus_dir / "ladder_keys.parquet")

    started = time.time()
    cache = LadderCache(keys, meta.price_scale)
    events = add_reach_outcomes(events, bars, cache, meta)
    print(f"raced {int(events['reach_outcome'].notna().sum())} breaches "
          f"in {time.time() - started:.0f}s")

    bar_count = int(events["bar_index"].nunique())
    statistics = {
        "hold_rate": hold_rate,
        "rejection_rate": rejection_rate,
        "reach_next_rate": reach_next_rate,
        "timeout_share": timeout_share,
        "mean_retest_depth": mean_retest_depth,
        "touch_density": touch_density_fn(bar_count),
    }

    results: List[GroupResult] = []
    for grouping in GROUPINGS:
        for label, rows in iter_groups(events, grouping):
            for name, fn in statistics.items():
                results.append(GroupResult(
                    grouping, label, name,
                    compare(rows, fn, shadow_count=meta.shadow_count)))

    context: Dict = {
        "corpus_dir": str(corpus_dir),
        "symbol": meta.symbol,
        "interval": meta.interval,
        "price_scale": meta.price_scale,
        "shadow_count": meta.shadow_count,
        "explore_events": len(events),
        "dropped_to_buffer": buffered.dropped,
        "boundary_bar_index": buffered.boundary,
        "buffer_bars": buffered.buffer_bars,
        "touch_density": compare(events, statistics["touch_density"],
                                 shadow_count=meta.shadow_count),
    }
    return render_report(results, context)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--out", default="docs/superpowers/reports")
    args = parser.parse_args()

    text = run(Path(args.corpus))

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

- [ ] **Step 6: Smoke-test the entry point end to end**

Append to `gann-visualizer/backend/tests/study_tool/mining/test_report.py`:

```python
def test_the_entry_point_mines_a_tiny_corpus_end_to_end(tmp_path):
    """
    Everything wired together on a synthetic corpus: no network, no token,
    no 113 MB of Parquet.
    """
    sys.path.append(os.path.abspath(
        'C:/Dev/GannTesting/gann-visualizer/backend/scripts'))
    import pandas as pd
    from build_gann_corpus import build_corpus
    from mine_gann_corpus import run
    from study_tool.corpus_writer import assign_slices, write_corpus

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
    bars = pd.DataFrame(rows)

    result = build_corpus(bars=bars, instrument="RELIANCE", timeframe="5",
                          price_scale=1, shadow_count=3, seed=7)
    meta = dict(result["meta"])
    meta["from_date"], meta["to_date"] = "2026-08-01", "2026-08-31"
    write_corpus(tmp_path, events=assign_slices(result["events"]),
                 bars=result["bars"], ladder_keys=result["ladder_keys"],
                 meta=meta)

    text = run(tmp_path)

    assert "## Shortlist" in text
    assert "Fairness check" in text


def test_the_entry_point_refuses_a_corpus_with_no_meta(tmp_path):
    """The gate, exercised through the real entry point rather than in unit."""
    sys.path.append(os.path.abspath(
        'C:/Dev/GannTesting/gann-visualizer/backend/scripts'))
    from mine_gann_corpus import run

    with pytest.raises(FileNotFoundError, match="backfill_corpus_meta"):
        run(tmp_path)
```

- [ ] **Step 7: Run the mining suite**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/ -q`
Expected: `60 passed` (6 corpus_meta + 6 boundary + 9 shadow_compare +
11 statistics + 6 groups + 13 ladder_rebuild + 9 report)

- [ ] **Step 8: Run everything for regressions**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/ tests/test_event_logger_ladder_schema.py tests/test_event_logger_mfe_mae_horizons.py -q`
Expected: all pass. No pre-existing test may start failing.

- [ ] **Step 9: Commit**

```bash
git add gann-visualizer/backend/study_tool/mining/report.py gann-visualizer/backend/scripts/mine_gann_corpus.py
git add -f gann-visualizer/backend/tests/study_tool/mining/test_report.py
git commit -m "feat: mining report and entry point

The report leads with the fairness check, because if real and shadow ladders
are touched at different rates then nothing below it is readable. It ends
with a shortlist of groups outside the whole shadow range, each carrying its
sample size, and it states in its own header that those are candidates rather
than findings.

The entry point reads the explore slice only. It touches the full events
table for two columns - bar_index and slice - to locate the boundary, which
is bookkeeping rather than price action."
```

---

### Task 10: Run it, and record what came out

**Files:**
- Create: `docs/superpowers/specs/2026-09-02-gann-phase3b-mining-results.md`

- [ ] **Step 1: Confirm the corpus has its metadata**

Run:

```bash
cd gann-visualizer/backend && python -c "
from study_tool.mining.corpus_meta import load_corpus_meta
m = load_corpus_meta('logs/corpus/reliance_5m_x1')
print(m.symbol, m.interval, 'x', m.price_scale, '|', m.shadow_count, 'shadows')
print('window', m.resolution_window_bars, '| bars', m.bar_count)
print('first offsets', [round(o, 4) for o in m.shadow_offsets[:3]])"
```

Expected: `RELIANCE 5 x 1 | 50 shadows`, `window 50 | bars 37110`. If it raises
about `meta.json`, Task 2 Step 5 was not run.

- [ ] **Step 2: Run the mining**

Run:

```bash
cd gann-visualizer/backend && python scripts/mine_gann_corpus.py --corpus logs/corpus/reliance_5m_x1 --out ../../docs/superpowers/reports
```

Expected: the boundary bar and the dropped-event count print first, then the
race count, then the report. Budget several minutes — the ladder cache builds
14,641 grids at 6.3 ms (~92 s) and the race runs over roughly 755,000 confirmed
breaches.

If it exhausts memory, the cause is `add_reach_outcomes` copying a 4-million-row
frame. Report the failure rather than guessing at a fix.

- [ ] **Step 3: Read the fairness check before anything else**

Look only at the touch-density row. Real and shadow should be close.

**If real touch density falls outside the shadow range, stop and report it.**
It means the two ladders get different exposure to price, and every other
number in the report is measuring that difference rather than the levels. That
is a finding about the control, and the rest of the report should not be read
until it is understood.

- [ ] **Step 4: Write the results document**

Create `docs/superpowers/specs/2026-09-02-gann-phase3b-mining-results.md`
containing, in this order:

1. The run parameters and the report file path.
2. The fairness check numbers, and a sentence on whether the control holds.
3. The number of events dropped to the boundary buffer, and the boundary bar.
4. The pooled figures for all five statistics, marked as context only.
5. The shortlist verbatim, with sample sizes.
6. A short "what this does not say" paragraph: these are explore-slice
   candidates; nothing is confirmed until the holdout is spent against a
   shortlist declared in advance.

- [ ] **Step 5: Confirm no report or corpus file is being committed**

Run: `cd /c/Dev/GannTesting && git status --short`
Expected: only the results Markdown is untracked. If Parquet files or a
`docs/superpowers/reports/` file appear and should not be tracked, add the
appropriate `.gitignore` entry and commit that first.

The generated report **is** worth tracking if it is small — it is diffable
across runs, which is why it is written to a file at all. Decide once and note
the decision in the results document.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-09-02-gann-phase3b-mining-results.md
git commit -m "docs: what the first mining run found

Explore-slice candidates only. The fairness check is recorded first because
it decides whether the rest of the report is readable at all.

Nothing here is confirmed. Confirmation means spending the holdout once,
against a shortlist declared before it is opened, with the result recorded
whichever way it falls."
```

---

## Notes for whoever executes this

- **The holdout is not opened in this phase, by any script.** The one place the
  full events table is touched is `mine_gann_corpus.run`, which reads two
  columns — `bar_index` and `slice` — to locate the boundary. That is
  bookkeeping. If you find yourself wanting an outcome column from a holdout
  row, stop.
- **`.gitignore` blanket-excludes `**/tests/`.** Every new test file in this
  plan needs `git add -f`. There are seven of them. Check `git status` after
  each commit.
- `tests/study_tool/mining/` is a new directory. It needs no `__init__.py` —
  the existing suite runs without one — but the directory itself must exist
  before the first test file is written.
- The corpus is gitignored, 113 MB, local only, and cost 40 minutes plus a live
  Dhan token. Nothing in this plan should ever write into it except
  `backfill_corpus_meta.py` writing `meta.json`.
- The three open questions from the spec — is 50 shadows enough, is a 50-bar
  window right for a target/stop race, do majors and subs need separating
  everywhere — are **not** answered here. Raising shadows to 200 is a corpus
  rebuild. Changing the race window is a one-line change to
  `add_reach_outcomes`, worth doing only once the first report shows how many
  races time out.
