# Anchored Volume Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an anchored volume profile — POC, value area, and volume nodes computed from a user-chosen starting bar — usable both as Python numbers and as a TradingView chart overlay.

**Architecture:** A pure Python package `backend/indicators/volume_profile/` does all the maths and never touches the network. Two functions are vendored from `bfolkens/py-market-profile` (BSD-3) with three upstream bugs fixed and regression-tested. `main.py` owns data fetching and exposes `POST /api/volume_profile`. The frontend splits into a pure shape-builder (unit tested under node) and a thin TradingView renderer.

**Tech Stack:** Python 3, pandas 2.3, numpy 2.2, scipy 1.16, FastAPI + pydantic, pytest. Frontend: React 19, Vite, TradingView Charting Library (self-hosted), plain `node:assert` tests in `.test.mjs` files.

**Spec:** `docs/superpowers/specs/2026-08-26-anchored-volume-profile-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `gann-visualizer/backend/indicators/__init__.py` | Namespace package marker. Empty. |
| `gann-visualizer/backend/indicators/volume_profile/__init__.py` | Public surface: re-exports `compute_anchored_profile`, `VolumeProfileResult`, `resolve_anchor`. |
| `.../volume_profile/vendor/LICENSE-py-market-profile` | BSD-3 text + Brad Folkens copyright. Legal requirement. |
| `.../volume_profile/vendor/market_profile_core.py` | `midmax_idx` + `calculate_value_area`, ported to plain lists, three bugs fixed. |
| `.../volume_profile/binning.py` | `normalize_time_seconds`, `build_bin_edges`, `distribute_fine`, `distribute_estimated`. No POC logic. |
| `.../volume_profile/profile.py` | `VolumeProfileResult` dataclass + `compute_anchored_profile`. The one entry point. |
| `.../volume_profile/anchors.py` | `resolve_anchor` and the three resolvers. Pure, no shared state. |
| `gann-visualizer/backend/main.py` | Adds `VolumeProfileRequest` model + `POST /api/volume_profile` route. Owns all fetching. |
| `gann-visualizer/backend/tests/test_volume_profile_vendor.py` | Regression tests proving the three upstream bugs are fixed. |
| `gann-visualizer/backend/tests/test_volume_profile_binning.py` | Bin edges, both distribution strategies, volume conservation, time normalisation. |
| `gann-visualizer/backend/tests/test_volume_profile.py` | End-to-end indicator behaviour, degenerate input, fallback, determinism. |
| `gann-visualizer/backend/tests/test_volume_profile_anchors.py` | The three anchor resolvers, including timezone cases. |
| `gann-visualizer/frontend/src/study_tool/VolumeProfileOverlay.js` | `buildVolumeProfileShapes` (pure) + `renderVolumeProfile` / `clearVolumeProfile` (chart-touching). |
| `gann-visualizer/frontend/src/study_tool/VolumeProfileOverlay.test.mjs` | Tests the pure builder only. |

**Working directory for all backend commands:** `C:/Dev/GannTesting/gann-visualizer/backend`
**Working directory for all frontend commands:** `C:/Dev/GannTesting/gann-visualizer/frontend`

There is no pytest config file in this repo. All commands below assume `pytest` is invoked with cwd `gann-visualizer/backend` — `python -m pytest` from that directory already puts it on `sys.path`, so test files import backend modules directly (`from indicators.volume_profile... import ...`), matching the existing pattern in `tests/test_target_progression.py`. Do **not** add a `sys.path.append` hack to any new test file — a worktree-relative absolute path breaks the moment the branch merges or a different machine runs it.

---

## Task 1: Vendor the BSD value-area code and fix its bugs

The upstream package (`bfolkens/py-market-profile` 0.1.1, June 2018) pins 2018-era pandas, so it is copied in rather than installed. Two functions are taken: `midmax_idx` from `src/market_profile/utils.py` and `calculate_value_area` from `src/market_profile/__init__.py`. They are ported from pandas Series to plain Python lists because our binning is array-based.

Three upstream bugs are fixed here. Each gets a test that fails against the original.

**Files:**
- Create: `gann-visualizer/backend/indicators/__init__.py`
- Create: `gann-visualizer/backend/indicators/volume_profile/__init__.py`
- Create: `gann-visualizer/backend/indicators/volume_profile/vendor/__init__.py`
- Create: `gann-visualizer/backend/indicators/volume_profile/vendor/LICENSE-py-market-profile`
- Create: `gann-visualizer/backend/indicators/volume_profile/vendor/market_profile_core.py`
- Test: `gann-visualizer/backend/tests/test_volume_profile_vendor.py`

- [ ] **Step 1: Create the package directories and the licence file**

Create three empty files: `indicators/__init__.py`, `indicators/volume_profile/__init__.py`, `indicators/volume_profile/vendor/__init__.py`.

Then create `indicators/volume_profile/vendor/LICENSE-py-market-profile`:

```
The following files in this directory are derived from py-market-profile:

    market_profile_core.py

Source: https://github.com/bfolkens/py-market-profile
Retrieved: 2026-08-26 (version 0.1.1)

Local modifications:
  - Ported from pandas Series to plain Python lists.
  - Fixed falsy-zero neighbour comparison (0.0 volume was treated as absent).
  - Fixed TypeError crash when the value-area walk reaches both profile edges.
  - Changed the loop guard from `<=` to `<` so the walk stops on target
    rather than one bucket past it.

--------------------------------------------------------------------------

BSD License

Copyright (c) 2017, Brad Folkens
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from this
   software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.
```

- [ ] **Step 2: Write the failing tests**

Create `gann-visualizer/backend/tests/test_volume_profile_vendor.py`:

```python
"""
Regression tests for the vendored py-market-profile code.

Each test in TestUpstreamBugs fails against the unmodified upstream
implementation. They are the reason this code is vendored rather than
installed from PyPI.
"""
import pytest

from indicators.volume_profile.vendor.market_profile_core import (
    calculate_value_area,
    midmax_idx,
)


class TestMidmaxIdx:

    def test_single_maximum(self):
        assert midmax_idx([1.0, 9.0, 3.0]) == 1

    def test_tie_resolves_to_middle_bucket(self):
        # Three-way tie at indices 1, 2, 3. The middle one must win.
        assert midmax_idx([3.0, 5.0, 5.0, 5.0, 2.0]) == 2

    def test_empty_returns_none(self):
        assert midmax_idx([]) is None

    def test_all_zero_returns_none(self):
        assert midmax_idx([0.0, 0.0, 0.0]) is None


class TestUpstreamBugs:

    def test_zero_volume_bucket_is_not_treated_as_absent(self):
        """Upstream bug 1: `if not high_volume` makes a 0.0 bucket falsy.

        Profile: [5, 0, 10, 0, 5], POC at index 2, total 20, target 14.
        Correct walk: both neighbours are 0.0, tie goes high -> index 3
        (trial 10), then compares 0.0 low against 5.0 high -> index 4
        (trial 15 >= 14). Result (2, 4).

        Upstream treats both 0.0 neighbours as None, walks left instead,
        and returns (0, 2).
        """
        volumes = [5.0, 0.0, 10.0, 0.0, 5.0]
        assert calculate_value_area(volumes, poc_idx=2, value_area_pct=0.70) == (2, 4)

    def test_full_coverage_does_not_crash_at_edges(self):
        """Upstream bug 3: both neighbours None -> `trial_vol += None`.

        At value_area_pct=1.0 the walk consumes the whole profile and then
        tries to step past both ends. Must return the full range, not raise.
        """
        volumes = [1.0, 1.0, 1.0]
        assert calculate_value_area(volumes, poc_idx=1, value_area_pct=1.0) == (0, 2)

    def test_walk_stops_on_target_not_past_it(self):
        """Upstream bug 2: `while trial_vol <= target_vol` over-expands.

        Profile: [1, 8, 1], total 10, pct 0.80 -> target 8.0.
        The POC bucket alone already holds 8.0, so the value area is just
        the POC. Upstream's `<=` expands one bucket further.
        """
        volumes = [1.0, 8.0, 1.0]
        assert calculate_value_area(volumes, poc_idx=1, value_area_pct=0.80) == (1, 1)


class TestValueAreaBasics:

    def test_symmetric_profile(self):
        volumes = [1.0, 2.0, 10.0, 2.0, 1.0]
        # total 16, target 11.2. POC 10 -> tie 2 vs 2 goes high (index 3,
        # trial 12 >= 11.2).
        assert calculate_value_area(volumes, poc_idx=2, value_area_pct=0.70) == (2, 3)

    def test_heavier_neighbour_wins(self):
        volumes = [1.0, 7.0, 10.0, 2.0, 1.0]
        # total 21, target 14.7. POC 10, left 7 beats right 2 -> index 1,
        # trial 17 >= 14.7.
        assert calculate_value_area(volumes, poc_idx=2, value_area_pct=0.70) == (1, 2)

    def test_zero_total_volume_returns_poc_only(self):
        assert calculate_value_area([0.0, 0.0], poc_idx=0, value_area_pct=0.70) == (0, 0)
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python -m pytest tests/test_volume_profile_vendor.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'indicators.volume_profile.vendor.market_profile_core'`.

- [ ] **Step 4: Write the implementation**

Create `gann-visualizer/backend/indicators/volume_profile/vendor/market_profile_core.py`:

```python
"""
Vendored from bfolkens/py-market-profile (BSD-3-Clause, (c) 2017 Brad Folkens).
See LICENSE-py-market-profile in this directory for the full licence text and
the list of local modifications.

Ported from pandas Series to plain Python lists, and three upstream bugs
fixed. Do not "simplify" the guards back to truthiness checks -- a bucket
holding exactly 0.0 volume is a real bucket, not an absent one.
"""
from typing import List, Optional, Tuple

import numpy as np


def midmax_idx(array: List[float]) -> Optional[int]:
    """Index of the maximum value, breaking ties toward the middle.

    Returns None for an empty profile or one that is entirely zero.
    """
    if len(array) == 0:
        return None

    values = np.asarray(array, dtype=float)
    if not np.any(values > 0):
        return None

    maxima_idxs = np.argwhere(values == np.amax(values))[:, 0]
    if len(maxima_idxs) == 1:
        return int(maxima_idxs[0])

    midpoint = len(values) / 2
    distances = np.abs(maxima_idxs - midpoint)
    return int(maxima_idxs[int(np.argmin(distances))])


def calculate_value_area(
    volumes: List[float],
    poc_idx: int,
    value_area_pct: float = 0.70,
) -> Tuple[int, int]:
    """Expand outward from the POC, always taking the heavier neighbour,
    until the cumulative volume reaches `value_area_pct` of the total.

    Returns (low_index, high_index), both inclusive.
    """
    n = len(volumes)
    if n == 0:
        raise ValueError("cannot compute a value area over an empty profile")

    total_volume = float(sum(volumes))
    target_vol = total_volume * value_area_pct
    trial_vol = float(volumes[poc_idx])

    min_idx = poc_idx
    max_idx = poc_idx

    # Strictly less-than: stop as soon as the target is met, not one bucket
    # past it (upstream used <=).
    while trial_vol < target_vol:
        next_min_idx = min_idx - 1 if min_idx > 0 else None
        next_max_idx = max_idx + 1 if max_idx < n - 1 else None

        # `is None` on purpose. A 0.0 volume bucket is present, not absent.
        low_volume = volumes[next_min_idx] if next_min_idx is not None else None
        high_volume = volumes[next_max_idx] if next_max_idx is not None else None

        if low_volume is None and high_volume is None:
            # Both edges reached and the target is still unmet (float drift,
            # or value_area_pct == 1.0). Upstream crashed here.
            break

        if high_volume is None or (low_volume is not None and low_volume > high_volume):
            trial_vol += low_volume
            min_idx = next_min_idx
        else:
            trial_vol += high_volume
            max_idx = next_max_idx

    return min_idx, max_idx
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python -m pytest tests/test_volume_profile_vendor.py -v
```

Expected: PASS, 10 passed.

- [ ] **Step 6: Commit**

```bash
git add gann-visualizer/backend/indicators gann-visualizer/backend/tests/test_volume_profile_vendor.py && git commit -m "feat: vendor py-market-profile value-area walk with upstream bugs fixed"
```

---

## Task 2: Binning — price buckets and volume distribution

This is written fresh. Upstream's `build_profile` buckets on closing price only and rounds with `math.ceil`, both unusable here.

**Files:**
- Create: `gann-visualizer/backend/indicators/volume_profile/binning.py`
- Test: `gann-visualizer/backend/tests/test_volume_profile_binning.py`

- [ ] **Step 1: Write the failing tests**

Create `gann-visualizer/backend/tests/test_volume_profile_binning.py`:

```python
"""Tests for volume profile bucketing and volume distribution."""
import numpy as np
import pandas as pd
import pytest

from indicators.volume_profile.binning import (
    build_bin_edges,
    distribute_estimated,
    distribute_fine,
    normalize_time_seconds,
)


def make_bars(rows):
    """rows: list of (time, open, high, low, close, volume)."""
    return pd.DataFrame(rows, columns=['time', 'open', 'high', 'low', 'close', 'volume'])


class TestNormalizeTimeSeconds:

    def test_milliseconds_are_converted(self):
        df = make_bars([(1756166400000, 1, 2, 0, 1, 10)])
        assert normalize_time_seconds(df)['time'].iloc[0] == 1756166400

    def test_seconds_are_left_alone(self):
        df = make_bars([(1756166400, 1, 2, 0, 1, 10)])
        assert normalize_time_seconds(df)['time'].iloc[0] == 1756166400

    def test_does_not_mutate_the_caller_frame(self):
        df = make_bars([(1756166400000, 1, 2, 0, 1, 10)])
        normalize_time_seconds(df)
        assert df['time'].iloc[0] == 1756166400000

    def test_empty_frame_is_safe(self):
        df = make_bars([])
        assert len(normalize_time_seconds(df)) == 0


class TestBuildBinEdges:

    def test_edges_span_low_to_high(self):
        bars = make_bars([
            (1, 0, 110.0, 90.0, 100.0, 5.0),
            (2, 0, 120.0, 95.0, 100.0, 5.0),
        ])
        edges = build_bin_edges(bars, bins=4)
        assert len(edges) == 5
        assert edges[0] == pytest.approx(90.0)
        assert edges[-1] == pytest.approx(120.0)
        assert np.all(np.diff(edges) > 0)

    def test_flat_range_still_produces_usable_edges(self):
        bars = make_bars([(1, 100.0, 100.0, 100.0, 100.0, 5.0)])
        edges = build_bin_edges(bars, bins=4)
        assert len(edges) == 5
        assert np.all(np.diff(edges) > 0)


class TestDistributeFine:

    def test_volume_lands_in_the_typical_price_bucket(self):
        edges = np.array([0.0, 10.0, 20.0, 30.0])
        # typical price (H+L+C)/3 = (16+14+15)/3 = 15 -> middle bucket
        fine = make_bars([(1, 15.0, 16.0, 14.0, 15.0, 7.0)])
        volumes = distribute_fine(fine, edges)
        assert volumes.tolist() == [0.0, 7.0, 0.0]

    def test_price_exactly_on_the_top_edge_is_included(self):
        edges = np.array([0.0, 10.0, 20.0])
        fine = make_bars([(1, 20.0, 20.0, 20.0, 20.0, 3.0)])
        volumes = distribute_fine(fine, edges)
        assert volumes.tolist() == [0.0, 3.0]

    def test_total_volume_is_conserved(self):
        edges = np.array([0.0, 10.0, 20.0, 30.0])
        fine = make_bars([
            (1, 5.0, 6.0, 4.0, 5.0, 2.0),
            (2, 15.0, 16.0, 14.0, 15.0, 3.0),
            (3, 25.0, 26.0, 24.0, 25.0, 4.0),
        ])
        assert distribute_fine(fine, edges).sum() == pytest.approx(9.0)


class TestDistributeEstimated:

    def test_candle_spanning_two_buckets_splits_pro_rata(self):
        edges = np.array([0.0, 10.0, 20.0])
        # low 5 -> high 15: half in each bucket.
        bars = make_bars([(1, 5.0, 15.0, 5.0, 15.0, 8.0)])
        volumes = distribute_estimated(bars, edges)
        assert volumes.tolist() == pytest.approx([4.0, 4.0])

    def test_uneven_overlap_splits_by_length(self):
        edges = np.array([0.0, 10.0, 20.0])
        # low 8 -> high 18: 2 units below 10, 8 units above.
        bars = make_bars([(1, 8.0, 18.0, 8.0, 18.0, 10.0)])
        volumes = distribute_estimated(bars, edges)
        assert volumes.tolist() == pytest.approx([2.0, 8.0])

    def test_flat_candle_goes_entirely_into_one_bucket(self):
        edges = np.array([0.0, 10.0, 20.0])
        bars = make_bars([(1, 5.0, 5.0, 5.0, 5.0, 6.0)])
        volumes = distribute_estimated(bars, edges)
        assert volumes.tolist() == pytest.approx([6.0, 0.0])

    def test_total_volume_is_conserved(self):
        edges = np.array([90.0, 100.0, 110.0, 120.0])
        bars = make_bars([
            (1, 95.0, 118.0, 91.0, 100.0, 11.0),
            (2, 100.0, 105.0, 99.0, 104.0, 13.0),
        ])
        assert distribute_estimated(bars, edges).sum() == pytest.approx(24.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python -m pytest tests/test_volume_profile_binning.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'indicators.volume_profile.binning'`.

- [ ] **Step 3: Write the implementation**

Create `gann-visualizer/backend/indicators/volume_profile/binning.py`:

```python
"""Price bucketing and volume distribution for the anchored volume profile.

Two distribution strategies:

  distribute_fine      -- bucket each 1-minute candle at its typical price.
                          Close to a real profile. Preferred.
  distribute_estimated -- spread each candle's volume across every bucket its
                          high-low range touches, pro-rata by overlap. Used
                          when 1m data is unavailable.

Both conserve total volume exactly.
"""
import numpy as np
import pandas as pd

# Epoch seconds will not reach 1e11 until the year 5138. Anything above it
# is milliseconds.
_MILLISECOND_THRESHOLD = 1e11


def normalize_time_seconds(bars: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of `bars` with the `time` column in epoch seconds.

    binance_client._parse_klines emits milliseconds and the frontend candle
    objects carry milliseconds, while this package works in seconds. Detecting
    the unit here means a caller passing raw Binance bars gets a correct
    profile instead of a silently empty one.
    """
    out = bars.copy()
    if len(out) == 0:
        return out
    if float(out['time'].abs().max()) >= _MILLISECOND_THRESHOLD:
        out['time'] = (out['time'] // 1000).astype('int64')
    else:
        out['time'] = out['time'].astype('int64')
    return out


def build_bin_edges(bars: pd.DataFrame, bins: int) -> np.ndarray:
    """`bins + 1` ascending price edges spanning the bar range.

    Explicit edges, no rounding to a tick grid -- upstream's math.ceil
    rounding pushed every price up by as much as a full row.
    """
    low = float(bars['low'].min())
    high = float(bars['high'].max())

    if not np.isfinite(low) or not np.isfinite(high):
        raise ValueError("bars contain non-finite prices")

    if high <= low:
        # Perfectly flat range. Open it up by a hair so the edges stay
        # strictly ascending and bucket lookup still works.
        pad = max(abs(low) * 1e-6, 1e-6)
        low, high = low - pad, high + pad

    return np.linspace(low, high, bins + 1)


def _bucket_index(prices: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Bucket index for each price, clamped into range.

    The clamp is what puts a price sitting exactly on the top edge into the
    last bucket rather than off the end.
    """
    idx = np.searchsorted(edges, prices, side='right') - 1
    return np.clip(idx, 0, len(edges) - 2)


def distribute_fine(fine_bars: pd.DataFrame, edges: np.ndarray) -> np.ndarray:
    """Bucket each fine bar's volume at its typical price (H+L+C)/3."""
    volumes = np.zeros(len(edges) - 1, dtype=float)
    if len(fine_bars) == 0:
        return volumes

    typical = (
        fine_bars['high'].to_numpy(dtype=float)
        + fine_bars['low'].to_numpy(dtype=float)
        + fine_bars['close'].to_numpy(dtype=float)
    ) / 3.0

    np.add.at(volumes, _bucket_index(typical, edges), fine_bars['volume'].to_numpy(dtype=float))
    return volumes


def distribute_estimated(bars: pd.DataFrame, edges: np.ndarray) -> np.ndarray:
    """Spread each bar's volume across the buckets its range overlaps."""
    volumes = np.zeros(len(edges) - 1, dtype=float)
    if len(bars) == 0:
        return volumes

    bucket_low = edges[:-1]
    bucket_high = edges[1:]

    highs = bars['high'].to_numpy(dtype=float)
    lows = bars['low'].to_numpy(dtype=float)
    vols = bars['volume'].to_numpy(dtype=float)

    for high, low, vol in zip(highs, lows, vols):
        span = high - low
        if span <= 0:
            # Flat candle: no range to spread over, dump it in one bucket.
            volumes[_bucket_index(np.array([low]), edges)[0]] += vol
            continue

        overlap = np.clip(
            np.minimum(high, bucket_high) - np.maximum(low, bucket_low),
            0.0,
            None,
        )
        total_overlap = overlap.sum()
        if total_overlap <= 0:
            volumes[_bucket_index(np.array([low]), edges)[0]] += vol
            continue

        volumes += vol * (overlap / total_overlap)

    return volumes
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python -m pytest tests/test_volume_profile_binning.py -v
```

Expected: PASS, 13 passed.

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/indicators/volume_profile/binning.py gann-visualizer/backend/tests/test_volume_profile_binning.py && git commit -m "feat: volume profile price bucketing and volume distribution"
```

---

## Task 3: The indicator entry point

**Files:**
- Create: `gann-visualizer/backend/indicators/volume_profile/profile.py`
- Modify: `gann-visualizer/backend/indicators/volume_profile/__init__.py`
- Test: `gann-visualizer/backend/tests/test_volume_profile.py`

- [ ] **Step 1: Write the failing tests**

Create `gann-visualizer/backend/tests/test_volume_profile.py`:

```python
"""End-to-end tests for compute_anchored_profile."""
import pandas as pd
import pytest

from indicators.volume_profile.profile import (
    VolumeProfileResult,
    compute_anchored_profile,
)


def make_bars(rows):
    """rows: list of (time, open, high, low, close, volume)."""
    return pd.DataFrame(rows, columns=['time', 'open', 'high', 'low', 'close', 'volume'])


# Ten bars, one hour apart, starting 2025-08-26 00:00:00 UTC.
BASE_TS = 1756166400

FLAT_BARS = make_bars([
    (BASE_TS + i * 3600, 100.0, 100.0 + i, 100.0 - i, 100.0, 10.0)
    for i in range(10)
])


class TestAnchorFiltering:

    def test_bars_before_the_anchor_are_excluded(self):
        bars = make_bars([
            (BASE_TS,        0, 200.0, 190.0, 195.0, 1000.0),  # before anchor
            (BASE_TS + 3600, 0, 110.0, 100.0, 105.0, 10.0),
            (BASE_TS + 7200, 0, 110.0, 100.0, 105.0, 10.0),
        ])
        result = compute_anchored_profile(bars, anchor_ts=BASE_TS + 3600, bins=4)

        assert result.bar_count == 2
        assert result.total_volume == pytest.approx(20.0)
        # The 190-200 bar is gone, so the profile cannot reach up there.
        assert result.bin_edges[-1] == pytest.approx(110.0)

    def test_bar_exactly_on_the_anchor_is_included(self):
        result = compute_anchored_profile(FLAT_BARS, anchor_ts=BASE_TS, bins=4)
        assert result.bar_count == 10

    def test_millisecond_bars_are_handled(self):
        ms_bars = FLAT_BARS.copy()
        ms_bars['time'] = ms_bars['time'] * 1000
        result = compute_anchored_profile(ms_bars, anchor_ts=BASE_TS, bins=4)
        assert result.bar_count == 10
        assert result.anchor_ts == BASE_TS


class TestKnownProfile:

    def test_poc_lands_where_the_volume_is(self):
        # Three price shelves. The middle one carries far more volume.
        bars = make_bars([
            (BASE_TS + 0, 0, 100.0, 90.0, 95.0, 1.0),
            (BASE_TS + 1, 0, 110.0, 100.0, 105.0, 50.0),
            (BASE_TS + 2, 0, 120.0, 110.0, 115.0, 1.0),
        ])
        result = compute_anchored_profile(bars, anchor_ts=BASE_TS, bins=3)

        # Edges 90/100/110/120 -> POC is the middle bucket, midpoint 105.
        assert result.poc_price == pytest.approx(105.0)
        assert result.val == pytest.approx(105.0)
        assert result.vah == pytest.approx(105.0)
        assert result.total_volume == pytest.approx(52.0)

    def test_value_area_widens_when_volume_is_spread_out(self):
        bars = make_bars([
            (BASE_TS + 0, 0, 100.0, 90.0, 95.0, 10.0),
            (BASE_TS + 1, 0, 110.0, 100.0, 105.0, 12.0),
            (BASE_TS + 2, 0, 120.0, 110.0, 115.0, 10.0),
        ])
        result = compute_anchored_profile(bars, anchor_ts=BASE_TS, bins=3)
        assert result.val < result.poc_price < result.vah


class TestVolumeConservation:

    def test_bin_volumes_sum_to_total_input_volume(self):
        result = compute_anchored_profile(FLAT_BARS, anchor_ts=BASE_TS, bins=24)
        assert sum(result.bin_volumes) == pytest.approx(100.0)
        assert result.total_volume == pytest.approx(100.0)

    def test_edge_count_is_bins_plus_one(self):
        result = compute_anchored_profile(FLAT_BARS, anchor_ts=BASE_TS, bins=24)
        assert len(result.bin_edges) == 25
        assert len(result.bin_volumes) == 24


class TestFineBarFallback:

    def test_fine_bars_set_source_to_1m(self):
        fine = make_bars([
            (BASE_TS + i * 60, 0, 105.0, 104.0, 104.5, 1.0) for i in range(60)
        ])
        bars = make_bars([(BASE_TS, 0, 110.0, 100.0, 105.0, 60.0)])
        result = compute_anchored_profile(bars, anchor_ts=BASE_TS, fine_bars=fine, bins=4)

        assert result.source == '1m'
        # All fine volume sits at typical price ~104.5, in the 105-107.5 bucket.
        assert result.poc_price == pytest.approx(103.75)

    def test_missing_fine_bars_fall_back_to_estimated(self):
        bars = make_bars([(BASE_TS, 0, 110.0, 100.0, 105.0, 60.0)])
        result = compute_anchored_profile(bars, anchor_ts=BASE_TS, fine_bars=None, bins=4)
        assert result.source == 'estimated'

    def test_empty_fine_bars_fall_back_to_estimated(self):
        bars = make_bars([(BASE_TS, 0, 110.0, 100.0, 105.0, 60.0)])
        empty = make_bars([])
        result = compute_anchored_profile(bars, anchor_ts=BASE_TS, fine_bars=empty, bins=4)
        assert result.source == 'estimated'

    def test_fine_bars_entirely_before_the_anchor_fall_back(self):
        fine = make_bars([(BASE_TS - 600, 0, 105.0, 104.0, 104.5, 1.0)])
        bars = make_bars([(BASE_TS, 0, 110.0, 100.0, 105.0, 60.0)])
        result = compute_anchored_profile(bars, anchor_ts=BASE_TS, fine_bars=fine, bins=4)
        assert result.source == 'estimated'


class TestDegenerateInput:

    def test_no_bars_after_the_anchor(self):
        result = compute_anchored_profile(FLAT_BARS, anchor_ts=BASE_TS + 10 * 3600, bins=4)
        assert result.bar_count == 0
        assert result.poc_price is None
        assert result.vah is None
        assert result.val is None
        assert result.bin_volumes == []
        assert result.hvn == []
        assert result.lvn == []

    def test_empty_frame(self):
        result = compute_anchored_profile(make_bars([]), anchor_ts=BASE_TS, bins=4)
        assert result.bar_count == 0
        assert result.poc_price is None

    def test_all_zero_volume(self):
        bars = make_bars([
            (BASE_TS + 0, 0, 110.0, 100.0, 105.0, 0.0),
            (BASE_TS + 1, 0, 110.0, 100.0, 105.0, 0.0),
        ])
        result = compute_anchored_profile(bars, anchor_ts=BASE_TS, bins=4)
        assert result.total_volume == pytest.approx(0.0)
        assert result.poc_price is None
        assert result.vah is None


class TestDeterminism:

    def test_same_input_gives_identical_output(self):
        a = compute_anchored_profile(FLAT_BARS, anchor_ts=BASE_TS, bins=24)
        b = compute_anchored_profile(FLAT_BARS, anchor_ts=BASE_TS, bins=24)
        assert a.to_dict() == b.to_dict()


class TestSerialization:

    def test_to_dict_has_every_documented_key(self):
        result = compute_anchored_profile(FLAT_BARS, anchor_ts=BASE_TS, bins=8)
        d = result.to_dict()
        assert set(d) == {
            'anchor_ts', 'bin_edges', 'bin_volumes', 'poc_price', 'vah', 'val',
            'total_volume', 'hvn', 'lvn', 'source', 'bar_count',
        }

    def test_to_dict_values_are_json_native(self):
        import json
        result = compute_anchored_profile(FLAT_BARS, anchor_ts=BASE_TS, bins=8)
        json.dumps(result.to_dict())  # must not raise on numpy types
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python -m pytest tests/test_volume_profile.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'indicators.volume_profile.profile'`.

- [ ] **Step 3: Write the implementation**

Create `gann-visualizer/backend/indicators/volume_profile/profile.py`:

```python
"""Anchored volume profile.

The one public entry point. It is pure: it never fetches data, never touches
the network, and never mutates its inputs. The caller decides which bars to
hand it and whether the fine-bar fetch succeeded.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema

from .binning import (
    build_bin_edges,
    distribute_estimated,
    distribute_fine,
    normalize_time_seconds,
)
from .vendor.market_profile_core import calculate_value_area, midmax_idx

logger = logging.getLogger(__name__)

SOURCE_FINE = '1m'
SOURCE_ESTIMATED = 'estimated'


@dataclass
class VolumeProfileResult:
    anchor_ts: int
    bin_edges: List[float] = field(default_factory=list)
    bin_volumes: List[float] = field(default_factory=list)
    poc_price: Optional[float] = None
    vah: Optional[float] = None
    val: Optional[float] = None
    total_volume: float = 0.0
    hvn: List[float] = field(default_factory=list)
    lvn: List[float] = field(default_factory=list)
    source: str = SOURCE_ESTIMATED
    bar_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'anchor_ts': int(self.anchor_ts),
            'bin_edges': [float(x) for x in self.bin_edges],
            'bin_volumes': [float(x) for x in self.bin_volumes],
            'poc_price': None if self.poc_price is None else float(self.poc_price),
            'vah': None if self.vah is None else float(self.vah),
            'val': None if self.val is None else float(self.val),
            'total_volume': float(self.total_volume),
            'hvn': [float(x) for x in self.hvn],
            'lvn': [float(x) for x in self.lvn],
            'source': self.source,
            'bar_count': int(self.bar_count),
        }


def _empty_result(anchor_ts: int, source: str = SOURCE_ESTIMATED) -> VolumeProfileResult:
    return VolumeProfileResult(anchor_ts=int(anchor_ts), source=source)


def compute_anchored_profile(
    bars: pd.DataFrame,
    anchor_ts: int,
    fine_bars: Optional[pd.DataFrame] = None,
    bins: int = 24,
    value_area_pct: float = 0.70,
    hvn_lvn_order: int = 2,
) -> VolumeProfileResult:
    """Build a volume profile over the bars at or after `anchor_ts`.

    `bars` always defines the bucket edges and the bar count. `fine_bars`
    (1-minute candles covering the same window) is used only to distribute
    volume; when it is missing or empty the estimated path runs instead.

    `anchor_ts` is epoch seconds UTC. The `time` column of either frame may be
    seconds or milliseconds -- it is normalised on the way in.
    """
    if bins < 1:
        raise ValueError("bins must be at least 1")
    if not 0.0 < value_area_pct <= 1.0:
        raise ValueError("value_area_pct must be in (0.0, 1.0]")

    anchor_ts = int(anchor_ts)

    if bars is None or len(bars) == 0:
        return _empty_result(anchor_ts)

    bars = normalize_time_seconds(bars)
    window = bars[bars['time'] >= anchor_ts]
    if len(window) == 0:
        return _empty_result(anchor_ts)

    edges = build_bin_edges(window, bins)

    # Prefer the fine path, but only if fine bars actually cover the window.
    volumes = None
    source = SOURCE_ESTIMATED
    if fine_bars is not None and len(fine_bars) > 0:
        fine = normalize_time_seconds(fine_bars)
        fine = fine[(fine['time'] >= anchor_ts) & (fine['time'] <= int(window['time'].max()))]
        if len(fine) > 0:
            volumes = distribute_fine(fine, edges)
            source = SOURCE_FINE
        else:
            logger.warning(
                "volume_profile: fine bars supplied but none fall inside the "
                "anchored window (anchor_ts=%s); falling back to estimated",
                anchor_ts,
            )

    if volumes is None:
        volumes = distribute_estimated(window, edges)

    total_volume = float(volumes.sum())
    midpoints = (edges[:-1] + edges[1:]) / 2.0

    result = VolumeProfileResult(
        anchor_ts=anchor_ts,
        bin_edges=edges.tolist(),
        bin_volumes=volumes.tolist(),
        total_volume=total_volume,
        source=source,
        bar_count=int(len(window)),
    )

    poc_idx = midmax_idx(volumes.tolist())
    if poc_idx is None:
        # Zero volume everywhere. Edges and counts are still meaningful.
        return result

    val_idx, vah_idx = calculate_value_area(volumes.tolist(), poc_idx, value_area_pct)

    result.poc_price = float(midpoints[poc_idx])
    result.val = float(midpoints[val_idx])
    result.vah = float(midpoints[vah_idx])

    if len(volumes) >= 3:
        (peaks,) = argrelextrema(volumes, np.greater, order=hvn_lvn_order)
        (troughs,) = argrelextrema(volumes, np.less, order=hvn_lvn_order)
        result.hvn = [float(midpoints[i]) for i in peaks]
        result.lvn = [float(midpoints[i]) for i in troughs]

    return result
```

Then replace `gann-visualizer/backend/indicators/volume_profile/__init__.py` with:

```python
from .profile import VolumeProfileResult, compute_anchored_profile

__all__ = ['VolumeProfileResult', 'compute_anchored_profile']
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python -m pytest tests/test_volume_profile.py -v
```

Expected: PASS, 17 passed.

- [ ] **Step 5: Run the whole volume profile suite together**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python -m pytest tests/test_volume_profile.py tests/test_volume_profile_binning.py tests/test_volume_profile_vendor.py -v
```

Expected: PASS, 40 passed.

- [ ] **Step 6: Commit**

```bash
git add gann-visualizer/backend/indicators/volume_profile gann-visualizer/backend/tests/test_volume_profile.py && git commit -m "feat: anchored volume profile indicator entry point"
```

---

## Task 4: Anchor resolvers

Three ways to pick the anchor timestamp. Each is pure and returns epoch seconds UTC. `session_start` is the only place a non-UTC timezone appears, and it converts back before returning.

`pivot` deliberately does **not** use `study_tool/pivot_detector.py`. That class keeps state in a module-level registry shared with the fan study, so calling it here would corrupt that state as a side effect of drawing an indicator.

**Files:**
- Create: `gann-visualizer/backend/indicators/volume_profile/anchors.py`
- Modify: `gann-visualizer/backend/indicators/volume_profile/__init__.py`
- Test: `gann-visualizer/backend/tests/test_volume_profile_anchors.py`

- [ ] **Step 1: Write the failing tests**

Create `gann-visualizer/backend/tests/test_volume_profile_anchors.py`:

```python
"""Tests for volume profile anchor resolution."""
import pandas as pd
import pytest

from indicators.volume_profile.anchors import (
    resolve_anchor,
    resolve_manual,
    resolve_pivot,
    resolve_session_start,
)


def make_bars(rows):
    return pd.DataFrame(rows, columns=['time', 'open', 'high', 'low', 'close', 'volume'])


BASE_TS = 1756166400  # 2025-08-26 00:00:00 UTC


class TestManual:

    def test_returns_the_timestamp_unchanged(self):
        assert resolve_manual(BASE_TS) == BASE_TS

    def test_milliseconds_are_converted(self):
        assert resolve_manual(BASE_TS * 1000) == BASE_TS


class TestSessionStart:

    def test_finds_the_utc_midnight_of_the_last_session(self):
        # 48 hourly bars starting at midnight UTC on 2025-08-26.
        bars = make_bars([
            (BASE_TS + i * 3600, 0, 1.0, 1.0, 1.0, 1.0) for i in range(48)
        ])
        ts = resolve_session_start(bars, session_time='00:00', tz='UTC')
        # Last session starts at midnight UTC on 2025-08-27.
        assert ts == BASE_TS + 24 * 3600

    def test_ist_session_start_is_returned_in_utc(self):
        bars = make_bars([
            (BASE_TS + i * 3600, 0, 1.0, 1.0, 1.0, 1.0) for i in range(48)
        ])
        # 09:15 IST == 03:45 UTC. Hourly bars, so the first bar at or after
        # 03:45 UTC on 2025-08-27 is the 04:00 UTC bar.
        ts = resolve_session_start(bars, session_time='09:15', tz='Asia/Kolkata')
        assert ts == BASE_TS + 28 * 3600

    def test_falls_back_to_the_first_bar_when_no_session_open_is_covered(self):
        bars = make_bars([
            (BASE_TS + i * 3600, 0, 1.0, 1.0, 1.0, 1.0) for i in range(3)
        ])
        ts = resolve_session_start(bars, session_time='12:00', tz='UTC')
        assert ts == BASE_TS

    def test_empty_bars_raises(self):
        with pytest.raises(ValueError):
            resolve_session_start(make_bars([]), session_time='00:00', tz='UTC')


class TestPivot:

    def test_finds_the_most_recent_confirmed_swing_high(self):
        # Highs: 1 2 3 9 3 2 1 2 3  -- peak at index 3, confirmed by 2 bars
        # on each side.
        highs = [1, 2, 3, 9, 3, 2, 1, 2, 3]
        bars = make_bars([
            (BASE_TS + i * 3600, 0, float(h), float(h) - 1, float(h), 1.0)
            for i, h in enumerate(highs)
        ])
        ts = resolve_pivot(bars, direction='high', left_bars=2, right_bars=2)
        assert ts == BASE_TS + 3 * 3600

    def test_finds_the_most_recent_confirmed_swing_low(self):
        lows = [9, 8, 7, 1, 7, 8, 9, 8, 7]
        bars = make_bars([
            (BASE_TS + i * 3600, 0, float(l) + 1, float(l), float(l), 1.0)
            for i, l in enumerate(lows)
        ])
        ts = resolve_pivot(bars, direction='low', left_bars=2, right_bars=2)
        assert ts == BASE_TS + 3 * 3600

    def test_takes_the_latest_pivot_when_there_are_several(self):
        highs = [1, 9, 1, 1, 1, 9, 1, 1]
        bars = make_bars([
            (BASE_TS + i * 3600, 0, float(h), float(h) - 1, float(h), 1.0)
            for i, h in enumerate(highs)
        ])
        ts = resolve_pivot(bars, direction='high', left_bars=1, right_bars=1)
        assert ts == BASE_TS + 5 * 3600

    def test_falls_back_to_the_first_bar_when_no_pivot_exists(self):
        bars = make_bars([
            (BASE_TS + i * 3600, 0, float(i), float(i) - 1, float(i), 1.0)
            for i in range(6)
        ])
        ts = resolve_pivot(bars, direction='high', left_bars=2, right_bars=2)
        assert ts == BASE_TS

    def test_does_not_touch_the_shared_pivot_registry(self):
        """The fan study's registry must be untouched by drawing an indicator."""
        from study_tool import pivot_detector

        before = dict(getattr(pivot_detector, '_PIVOT_REGISTRY', {}))
        highs = [1, 2, 3, 9, 3, 2, 1]
        bars = make_bars([
            (BASE_TS + i * 3600, 0, float(h), float(h) - 1, float(h), 1.0)
            for i, h in enumerate(highs)
        ])
        resolve_pivot(bars, direction='high', left_bars=2, right_bars=2)

        assert dict(getattr(pivot_detector, '_PIVOT_REGISTRY', {})) == before


class TestResolveAnchor:

    def test_dispatches_to_manual(self):
        bars = make_bars([(BASE_TS, 0, 1.0, 1.0, 1.0, 1.0)])
        assert resolve_anchor(bars, {'mode': 'manual', 'ts': BASE_TS}) == BASE_TS

    def test_unknown_mode_raises(self):
        bars = make_bars([(BASE_TS, 0, 1.0, 1.0, 1.0, 1.0)])
        with pytest.raises(ValueError):
            resolve_anchor(bars, {'mode': 'astrology'})
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python -m pytest tests/test_volume_profile_anchors.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'indicators.volume_profile.anchors'`.

- [ ] **Step 3: Write the implementation**

Create `gann-visualizer/backend/indicators/volume_profile/anchors.py`:

```python
"""Anchor resolution for the volume profile.

Every resolver returns a single epoch-seconds-UTC timestamp and nothing else.
compute_anchored_profile never learns which resolver produced it, which is what
keeps the anchor configurable without touching the maths.

Adding a fourth mode is one function here plus one value in ANCHOR_MODES.
"""
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict

import numpy as np
import pandas as pd
import pytz

from .binning import normalize_time_seconds

ANCHOR_MODES = ('manual', 'session_start', 'pivot')

_MILLISECOND_THRESHOLD = 1e11


def resolve_manual(ts: int) -> int:
    """Identity, apart from normalising milliseconds to seconds."""
    ts = int(ts)
    if abs(ts) >= _MILLISECOND_THRESHOLD:
        ts //= 1000
    return ts


def resolve_session_start(bars: pd.DataFrame, session_time: str = '00:00', tz: str = 'UTC') -> int:
    """Timestamp of the first bar at or after the most recent session open.

    `session_time` is HH:MM in the `tz` timezone. The result is always UTC.
    Timezone conversion happens here and nowhere else in this package.
    """
    if bars is None or len(bars) == 0:
        raise ValueError("cannot resolve a session anchor from an empty bar set")

    bars = normalize_time_seconds(bars)
    times = np.sort(bars['time'].to_numpy(dtype='int64'))

    hour, minute = (int(part) for part in session_time.split(':'))
    zone = pytz.timezone(tz)

    last_dt_local = datetime.fromtimestamp(int(times[-1]), tz=timezone.utc).astimezone(zone)

    # Walk back day by day until a session open lands inside the bar range.
    # Two steps is enough for any session, but cap it so a bad tz cannot spin.
    for days_back in range(0, 3):
        day = (last_dt_local - timedelta(days=days_back)).date()
        # localize (not replace) so DST offsets are applied correctly.
        open_local = zone.localize(datetime.combine(day, time(hour, minute)))
        open_ts = int(open_local.astimezone(timezone.utc).timestamp())

        if open_ts <= int(times[-1]):
            idx = int(np.searchsorted(times, open_ts, side='left'))
            if idx < len(times):
                return int(times[idx])

    # No session open is covered by these bars. The first bar is the honest
    # answer -- it is the earliest anchor the data can support.
    return int(times[0])


def resolve_pivot(
    bars: pd.DataFrame,
    direction: str = 'high',
    left_bars: int = 5,
    right_bars: int = 5,
) -> int:
    """Timestamp of the most recent confirmed swing high or low.

    A pure left/right-bars scan. It uses the same left_bars/right_bars
    convention as study_tool/pivot_detector.py so the results agree, but it
    deliberately does not call that class -- PivotDetector writes to a
    module-level registry shared with the fan study, and drawing an indicator
    must not mutate that.
    """
    if bars is None or len(bars) == 0:
        raise ValueError("cannot resolve a pivot anchor from an empty bar set")
    if direction not in ('high', 'low'):
        raise ValueError("direction must be 'high' or 'low'")

    bars = normalize_time_seconds(bars).sort_values('time')
    times = bars['time'].to_numpy(dtype='int64')
    series = bars['high' if direction == 'high' else 'low'].to_numpy(dtype=float)

    n = len(series)
    for i in range(n - 1 - right_bars, left_bars - 1, -1):
        left = series[i - left_bars:i]
        right = series[i + 1:i + 1 + right_bars]
        if len(left) < left_bars or len(right) < right_bars:
            continue

        if direction == 'high':
            if series[i] > left.max() and series[i] > right.max():
                return int(times[i])
        else:
            if series[i] < left.min() and series[i] < right.min():
                return int(times[i])

    # No confirmed pivot in range. Anchor at the start of the data.
    return int(times[0])


def resolve_anchor(bars: pd.DataFrame, anchor: Dict[str, Any]) -> int:
    """Dispatch to the resolver named by `anchor['mode']`."""
    mode = anchor.get('mode')

    if mode == 'manual':
        return resolve_manual(anchor['ts'])
    if mode == 'session_start':
        return resolve_session_start(
            bars,
            session_time=anchor.get('session_time', '00:00'),
            tz=anchor.get('tz', 'UTC'),
        )
    if mode == 'pivot':
        return resolve_pivot(
            bars,
            direction=anchor.get('direction', 'high'),
            left_bars=int(anchor.get('left_bars', 5)),
            right_bars=int(anchor.get('right_bars', 5)),
        )

    raise ValueError(f"unknown anchor mode: {mode!r}; expected one of {ANCHOR_MODES}")
```

Then replace `gann-visualizer/backend/indicators/volume_profile/__init__.py` with:

```python
from .anchors import ANCHOR_MODES, resolve_anchor
from .profile import VolumeProfileResult, compute_anchored_profile

__all__ = [
    'ANCHOR_MODES',
    'VolumeProfileResult',
    'compute_anchored_profile',
    'resolve_anchor',
]
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python -m pytest tests/test_volume_profile_anchors.py -v
```

Expected: PASS, 13 passed.

If `test_does_not_touch_the_shared_pivot_registry` fails on the registry
attribute name, open `study_tool/pivot_detector.py` and read the module-level
dict that `clear_pivot_registry` (line 9) resets, then use that name. Do not
delete the test.

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/indicators/volume_profile/anchors.py gann-visualizer/backend/indicators/volume_profile/__init__.py gann-visualizer/backend/tests/test_volume_profile_anchors.py && git commit -m "feat: volume profile anchor resolvers"
```

---

## Task 5: The API endpoint

`main.py` owns all data fetching. The indicator stays pure.

Read `gann-visualizer/backend/main.py:957` (`fetch_candles`) first for the house style, and `main.py:234` (`get_data_client`) for the client factory. Note that `binance_client._parse_klines` returns `time` in **milliseconds**.

**Files:**
- Modify: `gann-visualizer/backend/main.py` (add a request model near `FetchCandlesRequest` at line 224, and a route)

- [ ] **Step 1: Add the request model**

Insert immediately after the `FetchCandlesRequest` class, which ends at `main.py:232`:

```python
class VolumeProfileAnchor(BaseModel):
    mode: str = "manual"                      # manual | session_start | pivot
    ts: Optional[int] = None                  # manual: epoch SECONDS, UTC
    session_time: Optional[str] = "00:00"     # session_start: HH:MM in `tz`
    tz: Optional[str] = "UTC"                 # session_start
    direction: Optional[str] = "high"         # pivot: high | low
    left_bars: Optional[int] = 5              # pivot
    right_bars: Optional[int] = 5             # pivot


class VolumeProfileRequest(BaseModel):
    symbol: str
    resolution: str = "5"
    data_source: str = "binance"
    from_ts: int                              # epoch SECONDS, UTC
    to_ts: int                                # epoch SECONDS, UTC
    anchor: VolumeProfileAnchor = VolumeProfileAnchor()
    bins: int = 24
    value_area_pct: float = 0.70
    use_fine_bars: bool = True
```

- [ ] **Step 2: Add the route**

Append this to the end of `gann-visualizer/backend/main.py`:

```python
@app.post("/api/volume_profile")
async def volume_profile(req: VolumeProfileRequest):
    """Anchored volume profile.

    Every timestamp crossing this endpoint, in either direction, is epoch
    seconds in UTC. Data sources that speak other units (Binance klines are
    milliseconds, Dhan is IST) are converted inside this function and nowhere
    else. See docs/superpowers/specs/2026-08-26-anchored-volume-profile-design.md.
    """
    from fastapi import HTTPException

    from indicators.volume_profile import compute_anchored_profile, resolve_anchor

    if not 4 <= req.bins <= 50:
        raise HTTPException(status_code=422, detail="bins must be between 4 and 50")
    if not 0.0 < req.value_area_pct < 1.0:
        raise HTTPException(status_code=422, detail="value_area_pct must be between 0 and 1")
    if req.to_ts <= req.from_ts:
        raise HTTPException(status_code=422, detail="to_ts must be after from_ts")
    if req.anchor.mode == "manual":
        if req.anchor.ts is None:
            raise HTTPException(status_code=422, detail="manual anchor requires 'ts'")
        if not req.from_ts <= req.anchor.ts <= req.to_ts:
            raise HTTPException(status_code=422, detail="anchor.ts must lie within [from_ts, to_ts]")

    client = get_data_client(req.data_source)
    from_dt = datetime.fromtimestamp(req.from_ts, tz=timezone.utc)
    to_dt = datetime.fromtimestamp(req.to_ts, tz=timezone.utc)

    try:
        bars_df = client.fetch_data(
            req.symbol,
            from_dt.strftime('%Y-%m-%d'),
            to_dt.strftime('%Y-%m-%d'),
            interval=client.tv_resolution_to_interval(req.resolution),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"failed to fetch candles: {exc}")

    if bars_df is None or len(bars_df) == 0:
        raise HTTPException(status_code=404, detail="no candles for the requested window")

    # fetch_data returns a `timestamp` column (already epoch SECONDS -- see
    # binance_client.py:352). The indicator expects `time`.
    bars_df = bars_df.rename(columns={'timestamp': 'time'})
    if 'time' not in bars_df.columns:
        raise HTTPException(status_code=500, detail=f"unexpected candle columns: {list(bars_df.columns)}")

    # Fine bars are best-effort. A failure here degrades the profile, it does
    # not fail the request -- the `source` field tells the caller what happened.
    fine_df = None
    if req.use_fine_bars and req.data_source == "binance":
        try:
            raw = client.fetch_klines_range(
                req.symbol,
                "1m",
                start_time_ms=req.from_ts * 1000,
                end_time_ms=req.to_ts * 1000,
            )
            if raw:
                fine_df = pd.DataFrame(raw)  # time is in MILLISECONDS here
        except Exception as exc:
            print(f"[VolumeProfile] 1m fetch failed, falling back to estimated: {exc}")

    anchor_ts = resolve_anchor(bars_df, req.anchor.model_dump())

    result = compute_anchored_profile(
        bars_df,
        anchor_ts=anchor_ts,
        fine_bars=fine_df,
        bins=req.bins,
        value_area_pct=req.value_area_pct,
    )
    return result.to_dict()
```

- [ ] **Step 3: Verify the server still imports**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python -c "import main; print('import ok')"
```

Expected: `import ok`. If it fails on `pd` or `Optional` not being defined, check the existing imports at the top of `main.py` and add what is missing.

- [ ] **Step 4: Smoke test the endpoint against live Binance data**

Start the server, then in a second shell:

```bash
curl -s -X POST http://localhost:8000/api/volume_profile -H "Content-Type: application/json" -d '{"symbol":"BTCUSDT","resolution":"5","data_source":"binance","from_ts":1756080000,"to_ts":1756166400,"anchor":{"mode":"session_start","session_time":"00:00","tz":"UTC"},"bins":24}'
```

Expected: JSON with `"source": "1m"`, a non-null `poc_price`, 25 `bin_edges`, 24 `bin_volumes`, and `val <= poc_price <= vah`.

- [ ] **Step 5: Verify the validation rejects bad input**

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/volume_profile -H "Content-Type: application/json" -d '{"symbol":"BTCUSDT","from_ts":1756080000,"to_ts":1756166400,"bins":500}'
```

Expected: `422`.

- [ ] **Step 6: Commit**

```bash
git add gann-visualizer/backend/main.py && git commit -m "feat: POST /api/volume_profile endpoint"
```

---

## Task 6: Frontend shape builder

Split into a pure function that turns the API response into shape descriptors, and thin wrappers that hand those to TradingView. Only the pure half is unit tested — that is the half where the bugs live.

Read `gann-visualizer/frontend/src/study_tool/StudyDrawingUtils.js:110-200` first for the `createMultipointShape` / `createShape` option conventions this must match (`lock: true`, `disableUndo: true`, `zOrder: 'top'`).

**Files:**
- Create: `gann-visualizer/frontend/src/study_tool/VolumeProfileOverlay.js`
- Test: `gann-visualizer/frontend/src/study_tool/VolumeProfileOverlay.test.mjs`

- [ ] **Step 1: Write the failing test**

Create `gann-visualizer/frontend/src/study_tool/VolumeProfileOverlay.test.mjs`:

```javascript
import assert from 'node:assert/strict';

import { MAX_BINS, buildVolumeProfileShapes, clampBins } from './VolumeProfileOverlay.js';

const result = {
  anchor_ts: 1756166400,
  bin_edges: [100, 110, 120, 130],
  bin_volumes: [2, 8, 4],
  poc_price: 115,
  vah: 125,
  val: 115,
  total_volume: 14,
  hvn: [115],
  lvn: [105],
  source: '1m',
  bar_count: 12,
};

const opts = { barSeconds: 300, maxWidthBars: 20 };

// --- bucket rectangles -----------------------------------------------------

const shapes = buildVolumeProfileShapes(result, opts);
const rects = shapes.filter((s) => s.kind === 'rect');

assert.equal(rects.length, 3, 'one rectangle per bucket');

// Widest bucket is the 8-volume one; it gets the full maxWidthBars.
assert.equal(rects[1].points[0].time, 1756166400);
assert.equal(rects[1].points[1].time, 1756166400 + 20 * 300);

// The 2-volume bucket is a quarter as wide: round(20 * 2/8) = 5 bars.
assert.equal(rects[0].points[1].time, 1756166400 + 5 * 300);

// Rectangles span their own price bucket.
assert.equal(rects[0].points[0].price, 100);
assert.equal(rects[0].points[1].price, 110);

// The POC bucket is coloured differently from the rest.
assert.notEqual(rects[1].color, rects[0].color);

// --- level lines -----------------------------------------------------------

const lines = shapes.filter((s) => s.kind === 'line');
assert.deepEqual(lines.map((l) => l.label).sort(), ['POC', 'VAH', 'VAL']);
assert.equal(lines.find((l) => l.label === 'POC').price, 115);

// --- zero volume must not divide by zero -----------------------------------

const empty = buildVolumeProfileShapes(
  { ...result, bin_volumes: [0, 0, 0], poc_price: null, vah: null, val: null },
  opts,
);
assert.ok(empty.every((s) => Number.isFinite(s.points ? s.points[1].time : s.price)));
assert.equal(empty.filter((s) => s.kind === 'line').length, 0, 'no lines without levels');

// --- degenerate result -----------------------------------------------------

assert.deepEqual(buildVolumeProfileShapes(null, opts), []);
assert.deepEqual(
  buildVolumeProfileShapes({ ...result, bin_edges: [], bin_volumes: [] }, opts),
  [],
);

// --- bin clamping ----------------------------------------------------------

assert.equal(clampBins(500), MAX_BINS);
assert.equal(clampBins(1), 4);
assert.equal(clampBins(24), 24);
assert.equal(clampBins('nonsense'), 24);

console.log('VolumeProfileOverlay tests passed');
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /c/Dev/GannTesting/gann-visualizer/frontend && node src/study_tool/VolumeProfileOverlay.test.mjs
```

Expected: `ERR_MODULE_NOT_FOUND` for `./VolumeProfileOverlay.js`.

- [ ] **Step 3: Write the implementation**

Create `gann-visualizer/frontend/src/study_tool/VolumeProfileOverlay.js`:

```javascript
/**
 * Anchored volume profile overlay for the TradingView Charting Library.
 *
 * Split in two on purpose:
 *   buildVolumeProfileShapes  -- pure, unit tested, holds all the arithmetic
 *   renderVolumeProfile       -- thin, touches the chart, not unit tested
 *
 * Every bucket is a real chart drawing object, not a canvas primitive, so the
 * bin count is capped hard. See the design spec for why.
 */

export const MIN_BINS = 4;
export const MAX_BINS = 50;
export const DEFAULT_BINS = 24;

const COLOR_BUCKET = '#4A90D9';
const COLOR_POC_BUCKET = '#FF9500';
const COLOR_POC_LINE = '#FF9500';
const COLOR_VALUE_AREA_LINE = '#8E8E93';

/** Clamp a bin count into the supported range, falling back to the default. */
export function clampBins(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return DEFAULT_BINS;
  return Math.min(MAX_BINS, Math.max(MIN_BINS, Math.round(n)));
}

/**
 * Turn an /api/volume_profile response into renderer-agnostic descriptors.
 *
 * @param {Object|null} result   response body from POST /api/volume_profile
 * @param {Object} opts
 * @param {number} opts.barSeconds     seconds per bar at the current resolution
 * @param {number} opts.maxWidthBars   width of the heaviest bucket, in bars
 * @returns {Array<Object>} shape descriptors, `kind` of 'rect' or 'line'
 */
export function buildVolumeProfileShapes(result, opts = {}) {
  if (!result || !Array.isArray(result.bin_edges) || !Array.isArray(result.bin_volumes)) {
    return [];
  }
  if (result.bin_volumes.length === 0 || result.bin_edges.length < 2) {
    return [];
  }

  const barSeconds = Number(opts.barSeconds) || 60;
  const maxWidthBars = Number(opts.maxWidthBars) || 20;
  const anchorTs = Number(result.anchor_ts);

  const maxVolume = Math.max(...result.bin_volumes);
  const pocPrice = result.poc_price;

  const shapes = [];

  result.bin_volumes.forEach((volume, i) => {
    // Guard the divide: an all-zero profile is legal input.
    const share = maxVolume > 0 ? volume / maxVolume : 0;
    const widthBars = Math.max(1, Math.round(maxWidthBars * share));

    const low = result.bin_edges[i];
    const high = result.bin_edges[i + 1];
    const isPocBucket =
      pocPrice !== null && pocPrice !== undefined && pocPrice >= low && pocPrice <= high;

    shapes.push({
      kind: 'rect',
      points: [
        { time: anchorTs, price: low },
        { time: anchorTs + widthBars * barSeconds, price: high },
      ],
      color: isPocBucket ? COLOR_POC_BUCKET : COLOR_BUCKET,
      volume,
    });
  });

  const levels = [
    { label: 'POC', price: result.poc_price, color: COLOR_POC_LINE },
    { label: 'VAH', price: result.vah, color: COLOR_VALUE_AREA_LINE },
    { label: 'VAL', price: result.val, color: COLOR_VALUE_AREA_LINE },
  ];

  levels.forEach((level) => {
    if (level.price === null || level.price === undefined || !Number.isFinite(level.price)) {
      return;
    }
    shapes.push({
      kind: 'line',
      label: level.label,
      price: level.price,
      time: anchorTs,
      color: level.color,
    });
  });

  return shapes;
}

/**
 * Draw the shapes and return their ids. Ids must be retained by the caller and
 * passed to clearVolumeProfile before the next draw, or drawings leak.
 */
export function renderVolumeProfile(chart, result, opts = {}) {
  if (!chart) return [];

  const shapes = buildVolumeProfileShapes(result, opts);
  const ids = [];

  shapes.forEach((shape) => {
    try {
      if (shape.kind === 'rect') {
        const id = chart.createMultipointShape(shape.points, {
          shape: 'rectangle',
          lock: true,
          disableUndo: true,
          overrides: {
            color: shape.color,
            backgroundColor: shape.color,
            fillBackground: true,
            transparency: 40,
            linewidth: 0,
          },
          zOrder: 'bottom',
        });
        if (id) ids.push(id);
      } else {
        const id = chart.createMultipointShape(
          [
            { time: shape.time, price: shape.price },
            { time: shape.time + (Number(opts.barSeconds) || 60), price: shape.price },
          ],
          {
            shape: 'horizontal_line',
            lock: true,
            disableUndo: true,
            text: `${shape.label} ${shape.price.toFixed(2)}`,
            overrides: {
              linecolor: shape.color,
              linewidth: 2,
              showLabel: true,
              textcolor: shape.color,
            },
            zOrder: 'top',
          },
        );
        if (id) ids.push(id);
      }
    } catch (e) {
      console.error('[VolumeProfile] Failed to draw shape:', shape.kind, e);
    }
  });

  return ids;
}

/** Remove previously drawn shapes. Safe to call with a stale or empty list. */
export function clearVolumeProfile(chart, ids) {
  if (!chart || !Array.isArray(ids)) return;
  ids.forEach((id) => {
    try {
      chart.removeEntity(id);
    } catch (e) {
      // A shape the user already deleted by hand. Not an error.
    }
  });
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /c/Dev/GannTesting/gann-visualizer/frontend && node src/study_tool/VolumeProfileOverlay.test.mjs
```

Expected: `VolumeProfileOverlay tests passed`.

- [ ] **Step 5: Check lint is clean**

```bash
cd /c/Dev/GannTesting/gann-visualizer/frontend && npx eslint src/study_tool/VolumeProfileOverlay.js
```

Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add gann-visualizer/frontend/src/study_tool/VolumeProfileOverlay.js gann-visualizer/frontend/src/study_tool/VolumeProfileOverlay.test.mjs && git commit -m "feat: volume profile chart overlay shape builder"
```

---

## Task 7: Wire the overlay into the chart

**Files:**
- Modify: `gann-visualizer/frontend/src/TVChartContainer.jsx`

Read the existing shape lifecycle in `TVChartContainer.jsx` around lines 490-520 and 630-700 first. Follow the same pattern: keep shape ids in a ref, clear before redrawing.

- [ ] **Step 1: Add state and the fetch-and-draw callback**

Add near the other refs at the top of the component:

```javascript
const volumeProfileIdsRef = useRef([]);
const [vpEnabled, setVpEnabled] = useState(false);
const [vpAnchorMode, setVpAnchorMode] = useState('session_start');
const [vpBins, setVpBins] = useState(DEFAULT_BINS);
const [vpSource, setVpSource] = useState(null);
```

Add the import at the top of the file:

```javascript
import {
  DEFAULT_BINS,
  clampBins,
  clearVolumeProfile,
  renderVolumeProfile,
} from './study_tool/VolumeProfileOverlay';
```

Add the callback:

```javascript
const RESOLUTION_SECONDS = { '1': 60, '4': 240, '5': 300, '15': 900, '60': 3600, '240': 14400, 'D': 86400 };

const drawVolumeProfile = useCallback(async (anchorTsOverride = null) => {
  const chart = tvWidgetRef.current?.activeChart?.();
  if (!chart) return;

  clearVolumeProfile(chart, volumeProfileIdsRef.current);
  volumeProfileIdsRef.current = [];
  if (!vpEnabled) {
    setVpSource(null);
    return;
  }

  const range = chart.getVisibleRange();   // { from, to } in epoch SECONDS
  const anchor = anchorTsOverride !== null
    ? { mode: 'manual', ts: anchorTsOverride }
    : { mode: vpAnchorMode, session_time: '00:00', tz: 'UTC', direction: 'high', left_bars: 5, right_bars: 5 };

  try {
    const resp = await fetch('/api/volume_profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbol,
        resolution,
        data_source: dataSource,
        from_ts: Math.floor(range.from),
        to_ts: Math.floor(range.to),
        anchor,
        bins: clampBins(vpBins),
        value_area_pct: 0.70,
      }),
    });
    if (!resp.ok) {
      console.error('[VolumeProfile] request failed:', resp.status, await resp.text());
      return;
    }
    const result = await resp.json();
    setVpSource(result.source);
    volumeProfileIdsRef.current = renderVolumeProfile(chart, result, {
      barSeconds: RESOLUTION_SECONDS[resolution] || 300,
      maxWidthBars: 20,
    });
  } catch (e) {
    console.error('[VolumeProfile] draw failed:', e);
  }
}, [vpEnabled, vpAnchorMode, vpBins, symbol, resolution, dataSource]);
```

- [ ] **Step 2: Add the debounced redraw effect**

```javascript
useEffect(() => {
  const timer = setTimeout(() => { drawVolumeProfile(); }, 250);
  return () => clearTimeout(timer);
}, [drawVolumeProfile]);
```

- [ ] **Step 3: Add the control panel**

Add to the JSX, beside the existing chart controls:

```jsx
<div className="vp-controls">
  <label>
    <input
      type="checkbox"
      checked={vpEnabled}
      onChange={(e) => setVpEnabled(e.target.checked)}
    />
    Volume Profile
  </label>
  <select value={vpAnchorMode} onChange={(e) => setVpAnchorMode(e.target.value)} disabled={!vpEnabled}>
    <option value="session_start">Session start</option>
    <option value="pivot">Last pivot</option>
    <option value="manual">Click a bar</option>
  </select>
  <input
    type="number"
    min={4}
    max={50}
    value={vpBins}
    onChange={(e) => setVpBins(clampBins(e.target.value))}
    disabled={!vpEnabled}
    title="Number of price buckets (4-50)"
  />
  {vpSource === 'estimated' && (
    <span className="vp-warning" title="1-minute data was unavailable; volume was estimated from candle ranges">
      estimated
    </span>
  )}
</div>
```

- [ ] **Step 4: Wire the manual click handler**

```javascript
useEffect(() => {
  if (!vpEnabled || vpAnchorMode !== 'manual') return;
  const widget = tvWidgetRef.current;
  if (!widget) return;

  const onClick = (clickTime) => { drawVolumeProfile(Math.floor(clickTime)); };
  widget.subscribe('mouse_down', onClick);
  return () => { widget.unsubscribe('mouse_down', onClick); };
}, [vpEnabled, vpAnchorMode, drawVolumeProfile]);
```

- [ ] **Step 5: Verify in the browser**

Start the backend and `npm run dev`, then load the chart on BTCUSDT 5m.

Check, in order:
1. Tick "Volume Profile". A horizontal histogram appears anchored at the session open, with orange POC/VAH/VAL lines.
2. The browser console has no errors.
3. Switch the anchor to "Last pivot". The histogram moves and the old drawings are gone, not stacked on top.
4. Switch to "Click a bar" and click a bar. The profile re-anchors there.
5. Set bins to 50, then try to type 500 — it clamps to 50.
6. Untick the checkbox. Every drawing disappears.

- [ ] **Step 6: Commit**

```bash
git add gann-visualizer/frontend/src/TVChartContainer.jsx && git commit -m "feat: wire volume profile overlay into the chart"
```

---

## Task 8: Full suite and documentation

- [ ] **Step 1: Run every volume profile test**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python -m pytest tests/test_volume_profile.py tests/test_volume_profile_anchors.py tests/test_volume_profile_binning.py tests/test_volume_profile_vendor.py -v
```

Expected: PASS, 53 passed.

- [ ] **Step 2: Confirm no existing test regressed**

```bash
cd /c/Dev/GannTesting/gann-visualizer/backend && python -m pytest tests/ -q
```

Expected: the same pass/fail counts as before this branch. Record any pre-existing failures — do not fix unrelated ones here.

- [ ] **Step 3: Run the frontend test**

```bash
cd /c/Dev/GannTesting/gann-visualizer/frontend && node src/study_tool/VolumeProfileOverlay.test.mjs
```

Expected: `VolumeProfileOverlay tests passed`.

- [ ] **Step 4: Mark the spec implemented**

In `docs/superpowers/specs/2026-08-26-anchored-volume-profile-design.md`, change the `**Status:**` line to:

```markdown
**Status:** Implemented 2026-08-26
```

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-08-26-anchored-volume-profile-design.md && git commit -m "docs: mark anchored volume profile spec implemented"
```

---

## Notes for the implementer

**Do not "clean up" the `is None` checks** in `market_profile_core.py` into truthiness checks. That is the exact upstream bug being fixed, and `test_zero_volume_bucket_is_not_treated_as_absent` will catch you.

**Do not call `PivotDetector` from `anchors.py`.** It mutates a module-level registry shared with the fan study.

**Time units are the main hazard here.** Binance klines are milliseconds, TradingView shape points are seconds, and the API contract is seconds. `normalize_time_seconds` exists so a mistake produces a correct profile rather than a silently empty one. Do not remove it.

**If a test's expected number looks wrong, work the value-area walk by hand before changing the test.** The expected values in Tasks 1 and 3 were computed by hand and the reasoning is in each docstring.
