# Gann Phase 3a Corpus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Gann level-interaction corpus for RELIANCE, plus a matched shadow (control) corpus, split into explore and holdout slices, ready for mining.

**Architecture:** Bars are fetched from Dhan once and cached on disk. Sun and Moon ecliptic longitudes are computed per bar with Swiss Ephemeris. Each bar is walked through `GannLadderAnalyzer` against the real ladder, then against N shadow ladders derived from that same real ladder by adding a constant offset — never rebuilt, because grid construction is the dominant cost. Events, bars and ladder keys are written as Parquet.

**Tech Stack:** Python 3.13, pandas, pyarrow, pyswisseph, pytest. Existing modules `study_tool/gann_ladder.py`, `study_tool/gann_ladder_analyzer.py`, `study_tool/run_ladder_study.py`, `study_tool/event_logger.py`, `dhan_client.py`.

**Spec:** `docs/superpowers/specs/2026-09-02-gann-phase3-corpus-design.md`

**Scope note:** the spec's corpus v1 covers two resolutions, ×1/5-minute and ×10/1-minute. This plan builds ×1/5-minute end to end. The ×10 corpus is the same pipeline with two flags changed (`--interval 1 --scale 10`) and is deliberately the second run, not the first — there is no point paying for a 175,000-bar build before the 42,000-bar one has produced sensible counts.

---

## Facts established before planning (do not re-derive)

- Dhan `fetch_data(symbol, from_date, to_date, interval)` returns a DataFrame with a `RangeIndex` and columns `['open','high','low','close','volume','timestamp']`. `timestamp` is float epoch **seconds in true UTC** — epoch 1787629500 is 03:45 UTC, which is the 09:15 IST open. **No timezone correction is needed.**
- Dhan serves 5-minute bars at least 3 years back (verified at 6mo, 1y, 2y, 3y). ~86 bars per trading day.
- `build_all_ladders(price, scale, sun_square, moon_square)` returns level dicts with keys: `degree, direction, is_halfway, kind, price, ring, segment_end, segment_start, source, square, sub_index`.
- `GannLadderAnalyzer` never reads `level['direction']`; direction is computed from the bar.
- The forward-outcome method is named `enrich_with_forward_outcomes(candles)`, **not** `enrich()`. It matches `event.timestamp` against `int(c['time'])`, so candle dicts must use the key `time`.
- One `build_all_ladders` call costs 6.3 ms at ×1 and 27.2 ms at ×10. `process_bar` costs 0.65 ms/bar over 363 levels.
- `pyarrow` is **not installed**. Task 1 adds it.
- **Repo quirk:** `.gitignore` blanket-excludes `**/tests/`. Every new test file must be added with `git add -f` or it will silently not be tracked.

---

## File structure

| File | Responsibility |
|---|---|
| `gann-visualizer/backend/study_tool/ephemeris.py` | Sun/Moon ecliptic longitude for a UTC epoch. Nothing else. |
| `gann-visualizer/backend/study_tool/bar_cache.py` | Fetch bars from Dhan, cache to Parquet, never refetch. |
| `gann-visualizer/backend/study_tool/shadow_ladder.py` | Derive shifted ladders from a real one. Pure arithmetic. |
| `gann-visualizer/backend/study_tool/corpus_writer.py` | Write and read the three corpus tables, enforce the slice default. |
| `gann-visualizer/backend/scripts/build_gann_corpus.py` | Entry point wiring the above together. |
| `gann-visualizer/backend/study_tool/event_logger.py` | *Modified* — add raw excursion fields. |
| `gann-visualizer/backend/requirements.txt` | *Modified* — add pyswisseph, pyarrow. |

---

### Task 1: Dependencies and the ephemeris module

**Files:**
- Modify: `gann-visualizer/backend/requirements.txt`
- Create: `gann-visualizer/backend/study_tool/ephemeris.py`
- Test: `gann-visualizer/backend/tests/study_tool/test_ephemeris.py`

- [ ] **Step 1: Add the dependencies**

Append to `gann-visualizer/backend/requirements.txt`:

```
pyswisseph>=2.10.0
pyarrow>=14.0.0
```

- [ ] **Step 2: Install them**

Run: `pip install "pyswisseph>=2.10.0" "pyarrow>=14.0.0"`
Expected: both install, or report already satisfied for pyswisseph (2.10.03 is present).

- [ ] **Step 3: Write the failing test**

Create `gann-visualizer/backend/tests/study_tool/test_ephemeris.py`:

```python
"""
Sun and Moon ecliptic longitude from a bar's UTC epoch.

Dhan bar timestamps are true UTC epoch seconds - epoch 1787629500 is 03:45
UTC, the 09:15 IST open - so they are passed straight through with no offset.
Getting this wrong would shift the Moon by ~3 degrees over 5.5 hours, which is
3 grid squares, so the convention is pinned by a test rather than a comment.
"""
import sys
import os

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.ephemeris import sun_moon_longitudes

# 2026-08-25 03:45:00 UTC — the NSE open that day.
NSE_OPEN_EPOCH = 1787629500


def test_returns_both_longitudes_in_range():
    sun, moon = sun_moon_longitudes(NSE_OPEN_EPOCH)
    assert 0.0 <= sun < 360.0
    assert 0.0 <= moon < 360.0


def test_moon_moves_far_faster_than_the_sun():
    """~1 deg/day for the Sun, ~13 deg/day for the Moon. Catches a swapped pair."""
    sun_a, moon_a = sun_moon_longitudes(NSE_OPEN_EPOCH)
    sun_b, moon_b = sun_moon_longitudes(NSE_OPEN_EPOCH + 86400)

    sun_step = (sun_b - sun_a) % 360
    moon_step = (moon_b - moon_a) % 360

    assert 0.7 < sun_step < 1.3, f"sun moved {sun_step} deg/day"
    assert 11.0 < moon_step < 15.5, f"moon moved {moon_step} deg/day"


def test_epoch_is_read_as_utc_not_local():
    """
    5.5 hours of Moon motion is ~3 degrees. If the epoch were shifted by the
    IST offset, this difference would collapse or double.
    """
    _, moon_utc = sun_moon_longitudes(NSE_OPEN_EPOCH)
    _, moon_plus_ist = sun_moon_longitudes(NSE_OPEN_EPOCH + int(5.5 * 3600))

    step = (moon_plus_ist - moon_utc) % 360
    assert 2.0 < step < 4.0, f"5.5h of moon motion came out as {step} deg"


def test_repeated_calls_are_identical():
    """Determinism matters: the corpus must be reproducible."""
    assert sun_moon_longitudes(NSE_OPEN_EPOCH) == sun_moon_longitudes(NSE_OPEN_EPOCH)
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/test_ephemeris.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'study_tool.ephemeris'`

- [ ] **Step 5: Write the implementation**

Create `gann-visualizer/backend/study_tool/ephemeris.py`:

```python
"""
Sun and Moon ecliptic longitude for a bar timestamp.

Ported from the GannSq9 repo's backend/app/utils/ephemeris.py, reduced to the
one question this corpus asks: where were the Sun and Moon at this instant?

Dhan returns bar timestamps as epoch seconds in true UTC (verified: epoch
1787629500 is 03:45 UTC, the 09:15 IST open), and swisseph's calc_ut expects
Universal Time, so the epoch is used directly. Applying an IST offset here
would shift the Moon by about 3 degrees - 3 grid squares - on every bar.
"""

import datetime
from typing import Tuple

import swisseph as swe

_FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED


def _julian_day(epoch_seconds: float) -> float:
    when = datetime.datetime.fromtimestamp(
        epoch_seconds, tz=datetime.timezone.utc
    )
    return swe.julday(
        when.year,
        when.month,
        when.day,
        when.hour + when.minute / 60.0 + when.second / 3600.0,
    )


def sun_moon_longitudes(epoch_seconds: float) -> Tuple[float, float]:
    """
    Return (sun_longitude, moon_longitude) in degrees, each in [0, 360).

    Args:
        epoch_seconds: UTC epoch seconds, as Dhan supplies on every bar.
    """
    jd = _julian_day(epoch_seconds)
    sun, _ = swe.calc_ut(jd, swe.SUN, _FLAGS)
    moon, _ = swe.calc_ut(jd, swe.MOON, _FLAGS)
    return sun[0] % 360.0, moon[0] % 360.0
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/test_ephemeris.py -q`
Expected: `4 passed`

- [ ] **Step 7: Commit**

```bash
git add gann-visualizer/backend/requirements.txt gann-visualizer/backend/study_tool/ephemeris.py
git add -f gann-visualizer/backend/tests/study_tool/test_ephemeris.py
git commit -m "feat: sun and moon longitude for a bar timestamp

Ported from GannSq9's ephemeris helper, reduced to the single question the
corpus asks. Dhan epochs are true UTC so they pass straight to calc_ut; a
test pins that, because an IST offset would move the Moon three squares on
every bar."
```

---

### Task 2: Bar cache

**Files:**
- Create: `gann-visualizer/backend/study_tool/bar_cache.py`
- Test: `gann-visualizer/backend/tests/study_tool/test_bar_cache.py`

- [ ] **Step 1: Write the failing test**

Create `gann-visualizer/backend/tests/study_tool/test_bar_cache.py`:

```python
"""
Bar fetching and caching.

The network is never touched in these tests. A fake fetcher is injected so the
cache's behaviour - fetch once, reuse forever, append the ephemeris - is
tested without a live Dhan token.
"""
import sys
import os

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.bar_cache import load_bars

NSE_OPEN_EPOCH = 1787629500


def fake_frame(n=5):
    return pd.DataFrame({
        "open": [1300.0 + i for i in range(n)],
        "high": [1301.0 + i for i in range(n)],
        "low": [1299.0 + i for i in range(n)],
        "close": [1300.5 + i for i in range(n)],
        "volume": [1000.0] * n,
        "timestamp": [float(NSE_OPEN_EPOCH + i * 300) for i in range(n)],
    })


class CountingFetcher:
    def __init__(self):
        self.calls = 0

    def __call__(self, symbol, from_date, to_date, interval):
        self.calls += 1
        return fake_frame()


def test_returns_bars_with_sun_and_moon_columns(tmp_path):
    bars = load_bars(
        "RELIANCE", "2026-08-25", "2026-08-26", "5",
        cache_dir=tmp_path, fetcher=CountingFetcher(),
    )
    for column in ("open", "high", "low", "close", "timestamp",
                   "sun_degree", "moon_degree"):
        assert column in bars.columns, f"missing {column}"
    assert len(bars) == 5


def test_second_call_does_not_refetch(tmp_path):
    fetcher = CountingFetcher()
    args = ("RELIANCE", "2026-08-25", "2026-08-26", "5")

    first = load_bars(*args, cache_dir=tmp_path, fetcher=fetcher)
    second = load_bars(*args, cache_dir=tmp_path, fetcher=fetcher)

    assert fetcher.calls == 1, "the cache refetched instead of reading disk"
    pd.testing.assert_frame_equal(first, second)


def test_bars_come_back_sorted_and_deduplicated(tmp_path):
    """Chunked fetches can overlap at the seams; the analyzer needs strict order."""
    def messy(symbol, from_date, to_date, interval):
        frame = fake_frame()
        return pd.concat([frame.iloc[2:], frame]).reset_index(drop=True)

    bars = load_bars(
        "RELIANCE", "2026-08-25", "2026-08-26", "5",
        cache_dir=tmp_path, fetcher=messy,
    )
    assert bars["timestamp"].is_monotonic_increasing
    assert not bars["timestamp"].duplicated().any()


def test_empty_fetch_raises_rather_than_caching_nothing(tmp_path):
    """
    An expired token returns an empty frame. Caching that would poison every
    later run with a silent zero-bar corpus.
    """
    with pytest.raises(ValueError, match="no bars"):
        load_bars(
            "RELIANCE", "2026-08-25", "2026-08-26", "5",
            cache_dir=tmp_path, fetcher=lambda *a, **k: pd.DataFrame(),
        )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/test_bar_cache.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'study_tool.bar_cache'`

- [ ] **Step 3: Write the implementation**

Create `gann-visualizer/backend/study_tool/bar_cache.py`:

```python
"""
Fetch bars once, keep them on disk, and stamp each with the Sun and Moon.

Dhan access tokens expire every 24 hours and the data API is capped, so a
corpus build must never depend on refetching. The ephemeris is computed here
rather than at run time so a rebuilt corpus is reproducible from the cache
alone, with no ephemeris dependency and no clock involved.
"""

from pathlib import Path
from typing import Callable, Optional, Union

import pandas as pd

from study_tool.ephemeris import sun_moon_longitudes

BAR_COLUMNS = ["open", "high", "low", "close", "volume", "timestamp"]


def _default_fetcher(symbol: str, from_date: str, to_date: str,
                     interval: str) -> pd.DataFrame:
    from dhan_client import DhanClient
    return DhanClient().fetch_data(symbol, from_date, to_date, interval=interval)


def _cache_path(cache_dir: Path, symbol: str, from_date: str,
                to_date: str, interval: str) -> Path:
    name = f"{symbol}_{interval}_{from_date}_{to_date}.parquet"
    return Path(cache_dir) / name


def load_bars(
    symbol: str,
    from_date: str,
    to_date: str,
    interval: str,
    cache_dir: Union[str, Path],
    fetcher: Optional[Callable[..., pd.DataFrame]] = None,
) -> pd.DataFrame:
    """
    Bars for one symbol and window, with `sun_degree` and `moon_degree` added.

    Reads the on-disk cache if present. Otherwise fetches, enriches, sorts,
    deduplicates and writes the cache.

    Raises:
        ValueError: if the fetch returned nothing. An expired token looks
            exactly like a quiet market, and caching an empty frame would
            silently produce a zero-event corpus later.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, symbol, from_date, to_date, interval)

    if path.exists():
        return pd.read_parquet(path)

    fetch = fetcher or _default_fetcher
    frame = fetch(symbol, from_date, to_date, interval)

    if frame is None or len(frame) == 0:
        raise ValueError(
            f"no bars returned for {symbol} {interval} {from_date}..{to_date} "
            "- check the Dhan access token has not expired"
        )

    frame = frame.loc[:, [c for c in BAR_COLUMNS if c in frame.columns]].copy()
    frame = (frame
             .drop_duplicates(subset="timestamp")
             .sort_values("timestamp")
             .reset_index(drop=True))

    longitudes = [sun_moon_longitudes(t) for t in frame["timestamp"]]
    frame["sun_degree"] = [s for s, _ in longitudes]
    frame["moon_degree"] = [m for _, m in longitudes]

    frame.to_parquet(path, index=False)
    return frame
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/test_bar_cache.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/study_tool/bar_cache.py
git add -f gann-visualizer/backend/tests/study_tool/test_bar_cache.py
git commit -m "feat: fetch bars once, cache them, stamp sun and moon

Tokens expire daily and the API is capped, so a corpus build must not depend
on refetching. Ephemeris is computed at cache time so a rebuild is
reproducible from disk alone.

An empty fetch raises rather than caching: an expired token is
indistinguishable from a quiet market, and a cached empty frame would
silently yield a zero-event corpus."
```

---

### Task 3: Shadow ladder derivation

**Files:**
- Create: `gann-visualizer/backend/study_tool/shadow_ladder.py`
- Test: `gann-visualizer/backend/tests/study_tool/test_shadow_ladder.py`

- [ ] **Step 1: Write the failing test**

Create `gann-visualizer/backend/tests/study_tool/test_shadow_ladder.py`:

```python
"""
Shadow ladders: the real ladder slid sideways.

A shadow keeps the number of levels, their spacing (including the uneven
spacing of off-centre crosses) and their ordering, and destroys only whether
they sit at Gann prices. It must never trigger a grid rebuild - that is the
difference between a 3-hour corpus build and a 67-hour one.
"""
import sys
import os

import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.run_ladder_study import build_all_ladders, degree_to_square
from study_tool.shadow_ladder import shadow_offsets, shift_ladder

SUN = degree_to_square(155.0)
MOON = degree_to_square(331.0)


def real_ladder(scale=1):
    return build_all_ladders(1307.35, scale, SUN, MOON)


def test_shadow_has_the_same_number_of_levels():
    levels = real_ladder()
    assert len(shift_ladder(levels, 0.4, scale=1)) == len(levels)


def test_spacing_between_levels_is_preserved_exactly():
    """The control tests the prices, not the shape. The shape must survive."""
    levels = sorted(real_ladder(), key=lambda l: l["price"])
    shifted = sorted(shift_ladder(levels, 0.4, scale=1), key=lambda l: l["price"])

    real_gaps = [b["price"] - a["price"] for a, b in zip(levels, levels[1:])]
    shadow_gaps = [b["price"] - a["price"] for a, b in zip(shifted, shifted[1:])]

    for real, shadow in zip(real_gaps, shadow_gaps):
        assert real == pytest.approx(shadow, abs=1e-9)


def test_labels_are_untouched():
    """Arm, ring, source and kind identify the level and must not move."""
    levels = real_ladder()
    shifted = shift_ladder(levels, 0.4, scale=1)
    for before, after in zip(levels, shifted):
        for field in ("source", "kind", "degree", "ring", "sub_index",
                      "is_halfway"):
            assert before[field] == after[field]


def test_square_stays_consistent_with_price():
    """price == square / scale is an invariant the rest of the code relies on."""
    levels = real_ladder(scale=10)
    shifted = shift_ladder(levels, 0.4, scale=10)
    for level in shifted:
        assert level["price"] == pytest.approx(level["square"] / 10, abs=1e-9)


def test_sub_level_gap_is_unchanged_by_a_shift():
    """
    The analyzer derives touch tolerance from segment_start/segment_end. A
    constant shift must not change that width, or the shadow would be measured
    with a different yardstick than the real ladder.
    """
    from study_tool.gann_ladder_analyzer import GannLadderAnalyzer

    levels = [l for l in real_ladder(scale=10) if l["kind"] == "sub"]
    shifted = shift_ladder(levels, 0.4, scale=10)
    analyzer = GannLadderAnalyzer({"price_scale": 10})

    for before, after in zip(levels, shifted):
        assert analyzer._sub_gap(before) == pytest.approx(
            analyzer._sub_gap(after), abs=1e-9)


def test_the_original_ladder_is_not_mutated():
    levels = real_ladder()
    prices_before = [l["price"] for l in levels]
    shift_ladder(levels, 0.4, scale=1)
    assert [l["price"] for l in levels] == prices_before


def test_offsets_avoid_landing_back_on_the_real_levels():
    """
    An offset near zero or near a whole gap puts the shadow on top of the real
    ladder and dilutes the contrast the control exists to create.
    """
    gap = 2.25
    offsets = shadow_offsets(count=50, gap=gap, seed=7)

    assert len(offsets) == 50
    for delta in offsets:
        assert 0.1 * gap <= delta <= 0.9 * gap


def test_offsets_are_reproducible_from_the_seed():
    assert shadow_offsets(50, 2.25, seed=7) == shadow_offsets(50, 2.25, seed=7)
    assert shadow_offsets(50, 2.25, seed=7) != shadow_offsets(50, 2.25, seed=8)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/test_shadow_ladder.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'study_tool.shadow_ladder'`

- [ ] **Step 3: Write the implementation**

Create `gann-visualizer/backend/study_tool/shadow_ladder.py`:

```python
"""
Shadow ladders - the control the whole corpus is measured against.

Take the real ladder and add a constant to every price. The number of levels,
the spacing between them (including the uneven spacing of off-centre crosses),
their ordering and the relationship between the three crosses all survive. The
only thing destroyed is whether the levels sit at Gann prices, which is exactly
the question: is it these prices, or would any grid of this shape look the same?

A shadow is arithmetic on an already-built ladder. It must never call
build_all_ladders. Grid construction costs 27 ms at scale 10 and dominates the
corpus build; rebuilding per shadow turns a 3-hour job into a 67-hour one.
"""

import random
from typing import Dict, List

# Squares and segment bounds live in grid units; price is square / scale. A
# shift has to move all of them together or price == square / scale breaks.
_SQUARE_FIELDS = ("square", "segment_start", "segment_end")


def shift_ladder(levels: List[Dict], delta: float, scale: float) -> List[Dict]:
    """
    Return a copy of `levels` with every price moved by `delta`.

    Args:
        levels: output of build_all_ladders
        delta: price offset to add
        scale: the price scale those levels were built at (1 or 10)

    The input list is not mutated - the real ladder is reused for every shadow
    and for the real run itself.
    """
    square_delta = delta * scale
    shifted = []
    for level in levels:
        copy = dict(level)
        copy["price"] = level["price"] + delta
        for field in _SQUARE_FIELDS:
            if copy.get(field) is not None:
                copy[field] = level[field] + square_delta
        shifted.append(copy)
    return shifted


def shadow_offsets(count: int, gap: float, seed: int) -> List[float]:
    """
    `count` offsets, each between 0.1 and 0.9 of one sub-level gap.

    The bounds matter. An offset near 0, or near a whole gap, lands the shadow
    back on top of the real levels and weakens the contrast the control exists
    to provide.

    Seeded so a corpus build is reproducible.
    """
    rng = random.Random(seed)
    return [rng.uniform(0.1 * gap, 0.9 * gap) for _ in range(count)]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/test_shadow_ladder.py -q`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/study_tool/shadow_ladder.py
git add -f gann-visualizer/backend/tests/study_tool/test_shadow_ladder.py
git commit -m "feat: derive shadow ladders by shifting, never by rebuilding

A shadow keeps level count, spacing and ordering and destroys only whether
the prices are Gann prices. Squares and segment bounds shift with price so
the price == square / scale invariant holds and the analyzer measures both
ladders with the same yardstick.

Deriving rather than rebuilding is a requirement, not an optimisation: grid
construction is 27 ms at scale 10 and dominates the build."
```

---

### Task 4: Raw excursions, so directionless events carry an honest outcome

**Files:**
- Modify: `gann-visualizer/backend/study_tool/event_logger.py`
- Test: `gann-visualizer/backend/tests/study_tool/test_event_logger_raw_excursions.py`

Context: `enrich_with_forward_outcomes` assigns `mfe = max(exc_up, exc_down)` when an event has no `direction`. That labels whichever way price actually moved as "favourable" after the fact — not a quantity anything could predict, and poison as a training label. `LADDER_TOUCH` events have no direction. The existing directional behaviour cannot change, because the angular-coverage strategy depends on it, so raw excursions are recorded alongside.

**Most of this already exists.** `exc_up_10` and `exc_down_10` are declared fields (`event_logger.py:152-153`), already in `to_dict` (232-233), `from_dict` (309-310), the CSV export (860-861) and the hypothesis JSON (1030-1031). `calc_excursions` already returns `exc_up, exc_down`. Only the 10-bar horizon keeps them — line 734 captures them, while 733, 735 and 736 discard them with `_, _`.

So this task extends an existing pattern to the other three horizons. Follow the `exc_up_N` / `exc_down_N` naming already in use. Do not invent a parallel name.

- [ ] **Step 1: Write the failing test**

Create `gann-visualizer/backend/tests/study_tool/test_event_logger_raw_excursions.py`:

```python
"""
Raw forward excursions, recorded alongside the directional MFE/MAE.

For an event with no direction, enrich_with_forward_outcomes labels the larger
of the two moves as 'favourable'. That is decided after the fact, so nothing
could have predicted it, and using it as a training label would leak. Raw
up/down excursions are recorded so mining can pick the honest one.

The existing directional behaviour must not change - the angular-coverage
strategy already depends on it.
"""
import sys
import os

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.event_logger import Event, EventLogger, EventType


def candle(t, high, low, close=None):
    return {"time": t, "open": low, "high": high, "low": low,
            "close": close if close is not None else low}


def make_logger(event):
    logger = EventLogger()
    logger.events = [event]
    return logger


def base_event(direction=None):
    return Event(
        timestamp=1000,
        event_type=EventType.LADDER_TOUCH,
        price=100.0,
        direction=direction,
        bar_index=0,
    )


def rising_then_falling():
    """From price 100: up to 106 (exc_up 6), down to 97 (exc_down 3)."""
    return [
        candle(1000, 100.0, 100.0),
        candle(1001, 106.0, 99.0),
        candle(1002, 101.0, 97.0),
    ]


def test_raw_excursions_recorded_at_every_horizon_not_just_10():
    """
    exc_up_10 / exc_down_10 already worked. The other three horizons discarded
    theirs with `_, _`.
    """
    event = base_event(direction=None)
    make_logger(event).enrich_with_forward_outcomes(rising_then_falling())

    for horizon in (5, 10, 20, 50):
        assert getattr(event, f"exc_up_{horizon}") is not None, \
            f"exc_up_{horizon} not populated"
        assert getattr(event, f"exc_down_{horizon}") is not None, \
            f"exc_down_{horizon} not populated"


def test_raw_excursions_do_not_depend_on_which_move_was_larger():
    """The whole point: they are not sorted by outcome."""
    event = base_event(direction=None)
    make_logger(event).enrich_with_forward_outcomes(rising_then_falling())

    assert event.exc_up_5 == 6.0, "up must stay up, not become 'mfe'"
    assert event.exc_down_5 == 3.0


def test_directional_mfe_mae_behaviour_is_unchanged():
    """Regression guard for the angular-coverage strategy."""
    event = base_event(direction="up")
    make_logger(event).enrich_with_forward_outcomes(rising_then_falling())

    assert event.mfe_5 == 6.0
    assert event.mae_5 == 3.0


def test_raw_excursions_survive_the_serialisation_round_trip():
    event = base_event(direction=None)
    make_logger(event).enrich_with_forward_outcomes(rising_then_falling())

    restored = Event.from_dict(event.to_dict())
    for horizon in (5, 10, 20, 50):
        assert getattr(restored, f"exc_up_{horizon}") == \
            getattr(event, f"exc_up_{horizon}")
        assert getattr(restored, f"exc_down_{horizon}") == \
            getattr(event, f"exc_down_{horizon}")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/test_event_logger_raw_excursions.py -q`
Expected: FAIL — `AttributeError: 'Event' object has no attribute 'exc_up_5'`

- [ ] **Step 3: Add the six missing fields to the Event dataclass**

In `gann-visualizer/backend/study_tool/event_logger.py`, the pair for horizon 10
already exists at lines 152-153:

```python
    exc_up_10: Optional[float] = None
    exc_down_10: Optional[float] = None
```

Add the other three horizons beside them, and a comment explaining why they
exist:

```python
    # Raw forward excursions, not sorted into favourable/adverse.
    #
    # For an event with no direction - every LADDER_TOUCH - mfe/mae fall back
    # to labelling whichever move was larger as favourable. That is decided
    # after the fact and cannot be predicted, so it leaks as a training label.
    # These keep the two directions separate.
    exc_up_5: Optional[float] = None
    exc_down_5: Optional[float] = None
    exc_up_10: Optional[float] = None
    exc_down_10: Optional[float] = None
    exc_up_20: Optional[float] = None
    exc_down_20: Optional[float] = None
    exc_up_50: Optional[float] = None
    exc_down_50: Optional[float] = None
```

- [ ] **Step 4: Add the six to `to_dict`**

Beside the existing `"exc_up_10"` / `"exc_down_10"` entries at lines 232-233,
so the block reads:

```python
            "exc_up_5": self.exc_up_5,
            "exc_down_5": self.exc_down_5,
            "exc_up_10": self.exc_up_10,
            "exc_down_10": self.exc_down_10,
            "exc_up_20": self.exc_up_20,
            "exc_down_20": self.exc_down_20,
            "exc_up_50": self.exc_up_50,
            "exc_down_50": self.exc_down_50,
```

- [ ] **Step 5: Add the six to `from_dict`**

Beside the existing lines 309-310, so the block reads:

```python
        event.exc_up_5 = data.get("exc_up_5")
        event.exc_down_5 = data.get("exc_down_5")
        event.exc_up_10 = data.get("exc_up_10")
        event.exc_down_10 = data.get("exc_down_10")
        event.exc_up_20 = data.get("exc_up_20")
        event.exc_down_20 = data.get("exc_down_20")
        event.exc_up_50 = data.get("exc_up_50")
        event.exc_down_50 = data.get("exc_down_50")
```

- [ ] **Step 6: Stop discarding them in `enrich_with_forward_outcomes`**

`calc_excursions` already returns `mfe, mae, exc_up, exc_down`. Three of the
four call sites throw the last two away. At lines 733-736, replace:

```python
            event.mfe_5, event.mae_5, _, _ = calc_excursions(5)
            event.mfe_10, event.mae_10, event.exc_up_10, event.exc_down_10 = calc_excursions(10)
            event.mfe_20, event.mae_20, _, _ = calc_excursions(20)
            event.mfe_50, event.mae_50, _, _ = calc_excursions(50)
```

with:

```python
            event.mfe_5, event.mae_5, event.exc_up_5, event.exc_down_5 = calc_excursions(5)
            event.mfe_10, event.mae_10, event.exc_up_10, event.exc_down_10 = calc_excursions(10)
            event.mfe_20, event.mae_20, event.exc_up_20, event.exc_down_20 = calc_excursions(20)
            event.mfe_50, event.mae_50, event.exc_up_50, event.exc_down_50 = calc_excursions(50)
```

Nothing else in `calc_excursions` changes.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/test_event_logger_raw_excursions.py -q`
Expected: `4 passed`

- [ ] **Step 8: Run the whole ladder and event-logger suite for regressions**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/ tests/test_event_logger_ladder_schema.py tests/test_event_logger_mfe_mae_horizons.py -q`
Expected: all pass, no failures introduced.

- [ ] **Step 9: Commit**

```bash
git add gann-visualizer/backend/study_tool/event_logger.py
git add -f gann-visualizer/backend/tests/study_tool/test_event_logger_raw_excursions.py
git commit -m "feat: record raw forward excursions alongside MFE/MAE

For a directionless event - every LADDER_TOUCH - enrich falls back to
calling the larger move favourable. That is decided after the fact, so it
would leak as a training label.

Raw up/down excursions are added rather than changing the fallback, because
the angular-coverage strategy depends on the existing behaviour."
```

---

### Task 5: Corpus writer

**Files:**
- Create: `gann-visualizer/backend/study_tool/corpus_writer.py`
- Test: `gann-visualizer/backend/tests/study_tool/test_corpus_writer.py`

- [ ] **Step 1: Write the failing test**

Create `gann-visualizer/backend/tests/study_tool/test_corpus_writer.py`:

```python
"""
The corpus on disk: three tables, and a holdout that is hard to touch by accident.

Mining runs on the explore slice. The holdout is spent once, in batches, so
reaching it must be a deliberate act rather than a forgotten default.
"""
import sys
import os

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.corpus_writer import (
    assign_slices, load_events, write_corpus,
)


def events_frame():
    return pd.DataFrame({
        "bar_index": list(range(10)),
        "timestamp": [1000 + i for i in range(10)],
        "event_type": ["LADDER_TOUCH"] * 10,
        "level_source": ["center"] * 10,
        "shadow_id": [None] * 10,
    })


def bars_frame():
    return pd.DataFrame({
        "timestamp": [1000 + i for i in range(10)],
        "close": [100.0 + i for i in range(10)],
    })


def keys_frame():
    return pd.DataFrame({
        "bar_index": list(range(10)),
        "price_square": [100 + i for i in range(10)],
        "sun_square": [156] * 10,
        "moon_square": [332] * 10,
    })


def test_assign_slices_splits_by_time_not_at_random():
    """A random split would leak the future into the explore set."""
    frame = assign_slices(events_frame(), holdout_fraction=0.25,
                          order_column="bar_index")

    explore = frame[frame["slice"] == "explore"]["bar_index"]
    holdout = frame[frame["slice"] == "holdout"]["bar_index"]

    assert explore.max() < holdout.min(), "slices overlap in time"
    assert len(holdout) == 3  # ceil of 25% of 10, taken from the end
    assert len(explore) == 7


def test_write_then_read_round_trips(tmp_path):
    write_corpus(tmp_path, events=assign_slices(events_frame()),
                 bars=bars_frame(), ladder_keys=keys_frame())

    for name in ("events", "bars", "ladder_keys"):
        assert (tmp_path / f"{name}.parquet").exists(), f"{name} not written"


def test_load_events_returns_only_explore_by_default(tmp_path):
    write_corpus(tmp_path, events=assign_slices(events_frame()),
                 bars=bars_frame(), ladder_keys=keys_frame())

    loaded = load_events(tmp_path)

    assert set(loaded["slice"]) == {"explore"}, (
        "the default load reached the holdout"
    )


def test_load_events_needs_an_explicit_argument_for_the_holdout(tmp_path):
    write_corpus(tmp_path, events=assign_slices(events_frame()),
                 bars=bars_frame(), ladder_keys=keys_frame())

    loaded = load_events(tmp_path, slice_name="holdout")

    assert set(loaded["slice"]) == {"holdout"}


def test_an_unknown_slice_name_raises(tmp_path):
    write_corpus(tmp_path, events=assign_slices(events_frame()),
                 bars=bars_frame(), ladder_keys=keys_frame())

    with pytest.raises(ValueError, match="unknown slice"):
        load_events(tmp_path, slice_name="test")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/test_corpus_writer.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'study_tool.corpus_writer'`

- [ ] **Step 3: Write the implementation**

Create `gann-visualizer/backend/study_tool/corpus_writer.py`:

```python
"""
The corpus on disk.

Three tables:
  events       - one row per level interaction, real and shadow
  bars         - the OHLC used, with the Sun and Moon degree per bar
  ladder_keys  - (bar_index, price_square, sun_square, moon_square)

ladder_keys stores the ladder as its inputs rather than as a snapshot.
build_all_ladders is a pure function of exactly those three integers, so any
ladder is reconstructible on demand. A snapshot per rebuild would be roughly 63
million rows on the x10 corpus, because the price square changes on nearly
every bar.

The explore/holdout split is stamped into the data rather than left as a
convention, and the loader defaults to explore, so reaching the holdout takes a
deliberate argument and shows up in code review.
"""

import math
from pathlib import Path
from typing import Union

import pandas as pd

SLICES = ("explore", "holdout")
TABLES = ("events", "bars", "ladder_keys")


def assign_slices(events: pd.DataFrame, holdout_fraction: float = 0.25,
                  order_column: str = "bar_index") -> pd.DataFrame:
    """
    Stamp each row `explore` or `holdout`, split by time.

    The split is by time, never at random: a random split puts future bars in
    the explore set, and the holdout then measures nothing.
    """
    frame = events.sort_values(order_column).reset_index(drop=True).copy()
    holdout_rows = math.ceil(len(frame) * holdout_fraction)
    cutoff = len(frame) - holdout_rows

    frame["slice"] = ["explore"] * cutoff + ["holdout"] * holdout_rows
    return frame


def write_corpus(corpus_dir: Union[str, Path], events: pd.DataFrame,
                 bars: pd.DataFrame, ladder_keys: pd.DataFrame) -> None:
    """Write all three tables as Parquet."""
    corpus_dir = Path(corpus_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)

    for name, frame in zip(TABLES, (events, bars, ladder_keys)):
        frame.to_parquet(corpus_dir / f"{name}.parquet", index=False)


def load_events(corpus_dir: Union[str, Path],
                slice_name: str = "explore") -> pd.DataFrame:
    """
    Events for one slice. Defaults to `explore`.

    Getting the holdout requires naming it. The holdout is consumable - each
    look followed by a change turns it into training data - so it should not
    arrive by default.
    """
    if slice_name not in SLICES:
        raise ValueError(
            f"unknown slice {slice_name!r}; expected one of {SLICES}"
        )
    frame = pd.read_parquet(Path(corpus_dir) / "events.parquet")
    return frame[frame["slice"] == slice_name].reset_index(drop=True)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/test_corpus_writer.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/study_tool/corpus_writer.py
git add -f gann-visualizer/backend/tests/study_tool/test_corpus_writer.py
git commit -m "feat: corpus tables on disk, with the holdout behind a named argument

Three tables. ladder_keys stores the ladder as the three integers it is a
pure function of rather than as a snapshot, which would be ~63M rows on the
x10 corpus.

The split is by time, never random, and the loader defaults to explore so
reaching the holdout is deliberate and visible in review."
```

---

### Task 6: Corpus runner

**Files:**
- Create: `gann-visualizer/backend/scripts/build_gann_corpus.py`
- Test: `gann-visualizer/backend/tests/study_tool/test_build_gann_corpus.py`

- [ ] **Step 1: Write the failing test**

Create `gann-visualizer/backend/tests/study_tool/test_build_gann_corpus.py`:

```python
"""
The runner that wires bars, ephemeris, ladders and shadows into a corpus.

Runs on a small synthetic bar set so the whole pipeline is exercised in under a
second, with no network and no live token.
"""
import sys
import os

import pandas as pd

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend/scripts'))

from build_gann_corpus import build_corpus

NSE_OPEN_EPOCH = 1787629500


def synthetic_bars(n=60):
    """A climbing series, so levels are actually crossed."""
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


def test_produces_real_and_shadow_events():
    result = build_corpus(
        bars=synthetic_bars(), instrument="RELIANCE", timeframe="5",
        price_scale=1, shadow_count=3, seed=7,
    )
    events = result["events"]

    assert len(events) > 0, "no events produced at all"
    assert events["shadow_id"].isna().any(), "no real events"
    assert set(events["shadow_id"].dropna().unique()) == {0, 1, 2}


def test_ladder_keys_has_one_row_per_bar():
    bars = synthetic_bars()
    result = build_corpus(
        bars=bars, instrument="RELIANCE", timeframe="5",
        price_scale=1, shadow_count=2, seed=7,
    )
    keys = result["ladder_keys"]

    assert len(keys) == len(bars)
    for column in ("bar_index", "price_square", "sun_square", "moon_square"):
        assert column in keys.columns


def test_shadow_runs_do_not_rebuild_the_grid(monkeypatch):
    """
    The performance requirement, enforced rather than documented. One build per
    distinct ladder key, no matter how many shadows are run.
    """
    import build_gann_corpus as runner

    calls = {"n": 0}
    real_build = runner.build_all_ladders

    def counting_build(*args, **kwargs):
        calls["n"] += 1
        return real_build(*args, **kwargs)

    monkeypatch.setattr(runner, "build_all_ladders", counting_build)

    bars = synthetic_bars(n=30)
    build_corpus(bars=bars, instrument="RELIANCE", timeframe="5",
                 price_scale=1, shadow_count=20, seed=7)

    assert calls["n"] <= len(bars), (
        f"{calls['n']} grid builds for {len(bars)} bars with 20 shadows - "
        "shadows are rebuilding instead of being derived"
    )


def test_forward_excursions_are_populated():
    """Blank outcome columns would make the corpus useless for mining."""
    result = build_corpus(
        bars=synthetic_bars(), instrument="RELIANCE", timeframe="5",
        price_scale=1, shadow_count=1, seed=7,
    )
    events = result["events"]
    assert events["exc_up_5"].notna().any()
    assert events["exc_down_5"].notna().any()


def test_run_is_reproducible():
    kwargs = dict(bars=synthetic_bars(), instrument="RELIANCE", timeframe="5",
                  price_scale=1, shadow_count=3, seed=7)
    first = build_corpus(**kwargs)["events"]
    second = build_corpus(**kwargs)["events"]
    pd.testing.assert_frame_equal(first, second)


def test_events_frame_is_parquet_safe(tmp_path):
    """
    to_dict emits `details` and `active_angle_prices` as dicts, which Parquet
    cannot store. They must be JSON strings by the time the frame is returned.
    """
    events = build_corpus(
        bars=synthetic_bars(), instrument="RELIANCE", timeframe="5",
        price_scale=1, shadow_count=1, seed=7,
    )["events"]

    for column in ("details", "active_angle_prices"):
        if column in events.columns:
            assert not events[column].apply(
                lambda v: isinstance(v, (dict, list))).any(), \
                f"{column} still holds dicts"

    events.to_parquet(tmp_path / "events.parquet", index=False)
    assert (tmp_path / "events.parquet").exists()


def test_breach_outcome_is_lifted_into_its_own_column():
    """The most-queried field in the corpus should not need JSON parsing."""
    events = build_corpus(
        bars=synthetic_bars(), instrument="RELIANCE", timeframe="5",
        price_scale=1, shadow_count=1, seed=7,
    )["events"]

    assert "outcome" in events.columns
    resolved = events[events["event_type"] == "LADDER_BREACH_RESOLVED"]
    assert len(resolved) > 0, "no resolved breaches to check"
    assert resolved["outcome"].notna().any()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/test_build_gann_corpus.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'build_gann_corpus'`

- [ ] **Step 3: Write the implementation**

Create `gann-visualizer/backend/scripts/build_gann_corpus.py`:

```python
"""
Build the Gann level-interaction corpus and its shadow control.

Usage:
    python scripts/build_gann_corpus.py --symbol RELIANCE \
        --from 2024-09-02 --to 2026-09-01 --interval 5 --scale 1 \
        --shadows 50 --out logs/corpus/reliance_5m_x1

The ladder is built once per distinct (price square, sun square, moon square)
and every shadow is derived from that build by adding a constant. Grid
construction is 27 ms at scale 10 and dominates the run; rebuilding per shadow
turns roughly 3 hours into roughly 67.
"""

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
from study_tool.run_ladder_study import build_all_ladders, degree_to_square
from study_tool.shadow_ladder import shadow_offsets, shift_ladder

HORIZON_CANDLE_KEY = "time"


def _analyzer_settings(instrument: str, timeframe: str,
                       price_scale: int) -> Dict:
    return {
        "breach_mode": "close",
        "confirmation_closes": 2,
        "touch_tolerance_sublevels": 0.1,
        "resolution_window_bars": 50,
        "retest_window_bars": 50,
        "instrument": instrument,
        "timeframe": timeframe,
        "price_scale": price_scale,
    }


def _median_sub_gap(levels: List[Dict], price_scale: int) -> float:
    """Typical sub-level width in price, used to bound the shadow offsets."""
    gaps = [
        abs(l["segment_end"] - l["segment_start"]) / 8.0 / price_scale
        for l in levels
        if l.get("segment_start") is not None
        and l.get("segment_end") is not None
        and l["segment_end"] != l["segment_start"]
    ]
    if not gaps:
        return 1.0
    gaps.sort()
    return gaps[len(gaps) // 2]


def _candles_for_enrichment(bars: pd.DataFrame) -> List[Dict]:
    return [
        {HORIZON_CANDLE_KEY: int(row.timestamp), "open": row.open,
         "high": row.high, "low": row.low, "close": row.close}
        for row in bars.itertuples()
    ]


def _walk(bars: pd.DataFrame, ladders_by_bar: List[List[Dict]],
          settings: Dict) -> List:
    analyzer = GannLadderAnalyzer(settings)
    events = []
    for index, row in enumerate(bars.itertuples()):
        bar = {"open": row.open, "high": row.high, "low": row.low,
               "close": row.close, "timestamp": int(row.timestamp)}
        events.extend(analyzer.process_bar(bar, index, ladders_by_bar[index]))
    events.extend(analyzer.finalize())
    return events


def _events_to_frame(events: List, bars: pd.DataFrame,
                     shadow_id: Optional[int]) -> pd.DataFrame:
    logger = EventLogger()
    logger.events = events
    logger.enrich_with_forward_outcomes(_candles_for_enrichment(bars))

    frame = pd.DataFrame([event.to_dict() for event in events])
    frame["shadow_id"] = shadow_id

    # to_dict emits two dict-valued columns, which Parquet cannot store as-is.
    # The breach outcome lives inside `details` and is the single most-queried
    # field in the corpus, so it is lifted into a real column; the rest of
    # details is kept verbatim as JSON so nothing is lost.
    if "details" in frame.columns:
        frame["outcome"] = frame["details"].apply(
            lambda d: d.get("outcome") if isinstance(d, dict) else None)
    for column in ("details", "active_angle_prices"):
        if column in frame.columns:
            frame[column] = frame[column].apply(
                lambda v: json.dumps(v) if isinstance(v, (dict, list)) else v)

    return frame


def build_corpus(bars: pd.DataFrame, instrument: str, timeframe: str,
                 price_scale: int, shadow_count: int, seed: int) -> Dict:
    """
    Walk `bars` against the real ladder and `shadow_count` shifted ones.

    Returns a dict with `events`, `bars` and `ladder_keys` frames.
    """
    settings = _analyzer_settings(instrument, timeframe, price_scale)

    # One grid build per distinct key. Everything else reuses the result.
    cache: Dict = {}
    keys: List[Dict] = []
    real_by_bar: List[List[Dict]] = []

    for index, row in enumerate(bars.itertuples()):
        price_square = int(round(row.close * price_scale))
        sun_square = degree_to_square(row.sun_degree)
        moon_square = degree_to_square(row.moon_degree)
        key = (price_square, sun_square, moon_square)

        if key not in cache:
            cache[key] = build_all_ladders(
                row.close, price_scale, sun_square, moon_square)

        real_by_bar.append(cache[key])
        keys.append({"bar_index": index, "price_square": price_square,
                     "sun_square": sun_square, "moon_square": moon_square})

    all_levels = [lv for ladder in cache.values() for lv in ladder]
    gap = _median_sub_gap(all_levels, price_scale)
    offsets = shadow_offsets(shadow_count, gap, seed)

    frames = [_events_to_frame(_walk(bars, real_by_bar, settings), bars, None)]

    for shadow_id, delta in enumerate(offsets):
        shifted_cache = {
            key: shift_ladder(ladder, delta, price_scale)
            for key, ladder in cache.items()
        }
        shadow_by_bar = [
            shifted_cache[(k["price_square"], k["sun_square"], k["moon_square"])]
            for k in keys
        ]
        frames.append(_events_to_frame(
            _walk(bars, shadow_by_bar, settings), bars, shadow_id))

    return {
        "events": pd.concat(frames, ignore_index=True),
        "bars": bars.reset_index(drop=True),
        "ladder_keys": pd.DataFrame(keys),
    }


def main() -> None:
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
    args = parser.parse_args()

    bars = load_bars(args.symbol, args.from_date, args.to_date,
                     args.interval, cache_dir=args.cache)
    print(f"{len(bars)} bars {args.from_date}..{args.to_date}")

    result = build_corpus(
        bars=bars, instrument=args.symbol, timeframe=args.interval,
        price_scale=args.scale, shadow_count=args.shadows, seed=args.seed)

    events = assign_slices(result["events"], order_column="bar_index")
    write_corpus(Path(args.out), events=events, bars=result["bars"],
                 ladder_keys=result["ladder_keys"])

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


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/test_build_gann_corpus.py -q`
Expected: `7 passed`

- [ ] **Step 5: Run the full suite for regressions**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/ tests/test_event_logger_ladder_schema.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add gann-visualizer/backend/scripts/build_gann_corpus.py
git add -f gann-visualizer/backend/tests/study_tool/test_build_gann_corpus.py
git commit -m "feat: corpus runner for the real and shadow ladders

One grid build per distinct (price square, sun square, moon square); every
shadow is derived from that build by adding a constant. A test counts the
builds and fails if shadows start rebuilding, because that is the difference
between a 3-hour run and a 67-hour one.

Calls enrich_with_forward_outcomes so events carry outcomes rather than
blank columns."
```

---

### Task 7: Pilot run and event census

The spec's first open question is how many events two years actually produces. Nothing downstream can be designed until that number exists.

- [ ] **Step 1: Check the Dhan token has not expired**

Run:

```bash
cd gann-visualizer/backend && python -c "
import os, base64, json, time
from dotenv import load_dotenv
load_dotenv('.env', override=True)
t = os.environ.get('DHAN_ACCESS_TOKEN','').split('.')
c = json.loads(base64.urlsafe_b64decode(t[1] + '='*(-len(t[1])%4)))
print('hours left:', round((c.get('exp',0)-time.time())/3600, 1))"
```

Expected: a positive number. If negative, paste a fresh token into
`gann-visualizer/backend/.env` before continuing — an expired token returns
empty frames, and `load_bars` raises rather than caching them.

- [ ] **Step 2: Run one month as a pilot, with few shadows**

Run:

```bash
cd gann-visualizer/backend && python scripts/build_gann_corpus.py \
  --symbol RELIANCE --from 2026-08-01 --to 2026-08-31 \
  --interval 5 --scale 1 --shadows 5 \
  --out logs/corpus/pilot_reliance_5m_x1
```

Expected: roughly 1,700 bars (~86/day × 20 trading days), a printed event
count by type, and a breach-outcome census. Note the wall-clock time.

- [ ] **Step 3: Sanity-check the pilot output**

Run:

```bash
cd gann-visualizer/backend && python -c "
import pandas as pd
e = pd.read_parquet('logs/corpus/pilot_reliance_5m_x1/events.parquet')
real = e[e['shadow_id'].isna()]
print('real events:', len(real), '| shadow events:', len(e) - len(real))
print('slices:', e['slice'].value_counts().to_dict())
print('null level_degree:', real['level_degree'].isna().sum())
print('null exc_up_5:', real['exc_up_5'].isna().sum())
print('sources:', real['level_source'].value_counts().to_dict())"
```

Expected: real events > 0; all three of `center`, `sun`, `moon` present;
`level_degree` mostly populated; `exc_up_5` mostly populated (the final
50 bars have no forward window, so some nulls at the tail are correct).

**Stop and report the numbers before continuing.** If confirmed-breach-with-retest
events are in the single digits for a month, two years will not support the
hypotheses that depend on them, and the window or instrument count has to grow
before the full build is worth running.

- [ ] **Step 4: Run the full two years**

Only after Step 3's numbers have been reviewed.

```bash
cd gann-visualizer/backend && python scripts/build_gann_corpus.py \
  --symbol RELIANCE --from 2024-09-02 --to 2026-09-01 \
  --interval 5 --scale 1 --shadows 50 \
  --out logs/corpus/reliance_5m_x1
```

Expected: roughly 42,000 bars. Based on the pilot's timing, budget accordingly.

- [ ] **Step 5: Commit the census, not the corpus**

Parquet corpora do not belong in git. Record the numbers instead.

Create `docs/superpowers/specs/2026-09-02-gann-corpus-census.md` containing the
counts printed in Steps 2–4: bars, real events by type, breach outcomes by
category, events per slice, and the wall-clock build time.

```bash
git add docs/superpowers/specs/2026-09-02-gann-corpus-census.md
git commit -m "docs: event census for the first RELIANCE corpus

Answers the spec's first open question - how many events two years actually
produces - so Phase 3b can be designed against real counts rather than
guesses."
```

- [ ] **Step 6: Confirm the corpus is not tracked**

Run: `cd /c/Dev/GannTesting && git status --short | grep corpus || echo "clean - corpus is ignored"`
Expected: `clean - corpus is ignored`. If Parquet files appear, add
`logs/corpus/` to `.gitignore` and commit that.

---

## Notes for whoever executes this

- **Do not build the ×10 corpus from any commit before `fcb8e5a`.** The
  sub-level gap was measured in grid squares rather than price, making the
  touch tolerance ten times too wide at scale 10. Every touch and retest would
  be wrong, and it would look fine.
- The ×10 / 1-minute corpus is the second build, not the first. Get ×1 /
  5-minute working end to end before adding a resolution.
- `.gitignore` excludes `**/tests/`. Every new test file needs `git add -f`.
  Check `git status` after adding one.
