# RSI Trendline Geometry Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the all-pairs + RANSAC RSI geometry layer with a causal sweep that maintains exactly one active trendline per direction, so the line drawn on the chart is the same object that triggers the trade.

**Architecture:** Split `rsi_geometry.py` into three focused pure modules — pivots, anchor policy, causal sweep. A single bar-by-bar state machine owns all mutable state (running pivot list, active line per direction, break detection, segment emission); the only swappable surface is a small `anchor()` policy that physically cannot see future pivots. The hypothesis then applies the `SMA(200)` filter, a swing-based stop, and the existing unchanged trade simulator.

**Tech Stack:** Python 3.13, pandas, pytest, FastAPI, React, plain Node `.test.mjs` scripts

**Spec:** [2026-07-26-rsi-trendline-geometry-redesign-design.md](../specs/2026-07-26-rsi-trendline-geometry-redesign-design.md)

---

## Conventions used throughout

- All `pytest` commands run **from the repo root** `c:\Dev\GannTesting`.
- Backend test files start with this exact preamble (matching every existing test in `gann-visualizer/backend/tests/`):
  ```python
  import os
  import sys

  sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))
  ```
- Frontend tests are plain Node scripts run with `node <path>`, ending in `console.log('<filename>: ok');`.
- There is **no** `conftest.py` or `pytest.ini` in this repo. Do not add one.

### Pre-existing failures (not caused by this work)

`gann-visualizer/backend/tests/test_rsi_geometry.py` has **2 of 4 tests already failing on main** — its fixtures use pivot spans shorter than the `min_length=8` default. Those tests cover `DeterministicPivotLineBuilder`, which Task 5 deletes, so they are replaced rather than repaired. Do not treat them as regressions you introduced.

---

## File Structure

### Backend — new modules

- Create: `gann-visualizer/backend/analysis/rsi_pivots.py`
  - `GeometryParams`, `RSIPivot`, `compute_rsi_series`, `detect_fractal_candidates`, `apply_dominance`
  - Pure. No line or trade concepts.
- Create: `gann-visualizer/backend/analysis/rsi_line_policy.py`
  - `RSILine`, `WalkBackAnchorPolicy`, `NearestPairAnchorPolicy`
  - Pure. Given same-kind pivots, pick an anchor. No bar loop, no state.
- Create: `gann-visualizer/backend/analysis/rsi_sweep.py`
  - `LineSegment`, `BreakSignal`, `SweepResult`, `run_causal_sweep`
  - Owns *all* mutable state and the only bar loop in the system.

**Dependency direction is strictly one-way:** `rsi_pivots` ← `rsi_line_policy` ← `rsi_sweep`.
`GeometryParams` lives in `rsi_pivots` — the base module — because both the policy
layer and the sweep need it. Putting it in `rsi_sweep` would make the policy layer
depend on the sweep it is called by, and each task's tests would not run standalone.

### Backend — modified

- Modify: `gann-visualizer/backend/analysis/rsi_geometry.py` — reduced to a re-export shim; ~400 lines of dead/wrong builders deleted
- Modify: `gann-visualizer/backend/analysis/rsi_trendline_hypothesis.py` — consume the sweep, swing-based stop, emit `line_timeline`
- Modify: `gann-visualizer/backend/main.py:2331` — pass `line_timeline` through instead of `all_rsi_lines`

### Backend — tests

- Create: `gann-visualizer/backend/tests/test_rsi_pivots.py`
- Create: `gann-visualizer/backend/tests/test_rsi_line_policy.py`
- Create: `gann-visualizer/backend/tests/test_rsi_sweep.py`
- Create: `gann-visualizer/backend/tests/test_rsi_causality.py` — the repaint regression test
- Modify: `gann-visualizer/backend/tests/test_rsi_geometry.py` — replaced with shim re-export tests
- Modify: `gann-visualizer/backend/tests/test_rsi_trendline_hypothesis.py`

### Frontend

- Modify: `gann-visualizer/frontend/src/hypothesisRsiVerification.js` — expose `segment_id`, `line_timeline`
- Modify: `gann-visualizer/frontend/src/hypothesisRsiVerification.test.mjs`
- Modify: `gann-visualizer/frontend/src/TVChartContainer.jsx` — render only segments live at the selected bar
- Modify: `gann-visualizer/frontend/src/App.jsx` — wire the `lineTimeline` prop

### Scripts

- Create: `gann-visualizer/backend/scripts/compare_rsi_policies.py` — the A/B harness required by spec §9.3

---

## Task 1: Pivot Layer — RSI, Fractal Candidates, Dominance

**Files:**
- Create: `gann-visualizer/backend/analysis/rsi_pivots.py`
- Create: `gann-visualizer/backend/tests/test_rsi_pivots.py`

- [ ] **Step 1: Write the failing tests**

Create `gann-visualizer/backend/tests/test_rsi_pivots.py`:

```python
import os
import sys

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

import pandas as pd

from analysis.rsi_pivots import (
    GeometryParams,
    RSIPivot,
    apply_dominance,
    compute_rsi_series,
    detect_fractal_candidates,
)


def test_geometry_params_expose_defaults_for_every_knob():
    params = GeometryParams()

    assert params.left_bars == 3
    assert params.right_bars == 3
    assert params.min_swing == 8.0
    assert params.tolerance == 1.5
    assert params.min_length == 8
    assert params.max_span_bars == 150


def test_rsi_series_stays_in_range_and_rises_on_uptrend():
    close = pd.Series([float(100 + i) for i in range(40)])
    rsi = compute_rsi_series(close, period=14)

    assert len(rsi) == 40
    assert rsi.iloc[-1] > 90.0
    assert ((rsi >= 0.0) & (rsi <= 100.0)).all()


def test_fractal_candidate_confirms_right_bars_after_its_own_bar():
    rsi = pd.Series([40.0, 42.0, 55.0, 43.0, 41.0, 39.0, 38.0])

    candidates = detect_fractal_candidates(rsi, left_bars=2, right_bars=2)
    highs = [c for c in candidates if c.kind == "high"]

    assert highs[0].bar_index == 2
    assert highs[0].rsi_value == 55.0
    assert highs[0].confirmation_bar_index == 4


def test_dominance_replaces_a_weaker_same_kind_pivot():
    weak = RSIPivot(bar_index=10, rsi_value=60.0, kind="high", confirmation_bar_index=12)
    strong = RSIPivot(bar_index=14, rsi_value=68.0, kind="high", confirmation_bar_index=16)

    pivots, changed = apply_dominance([weak], strong, min_swing=8.0)

    assert pivots == [strong]
    assert changed == "high"


def test_dominance_keeps_the_stronger_incumbent_and_reports_no_change():
    strong = RSIPivot(bar_index=10, rsi_value=68.0, kind="high", confirmation_bar_index=12)
    weak = RSIPivot(bar_index=14, rsi_value=61.0, kind="high", confirmation_bar_index=16)

    pivots, changed = apply_dominance([strong], weak, min_swing=8.0)

    assert pivots == [strong]
    assert changed is None


def test_dominance_rejects_an_opposite_pivot_below_min_swing():
    high = RSIPivot(bar_index=10, rsi_value=68.0, kind="high", confirmation_bar_index=12)
    shallow_low = RSIPivot(bar_index=14, rsi_value=63.0, kind="low", confirmation_bar_index=16)

    pivots, changed = apply_dominance([high], shallow_low, min_swing=8.0)

    assert pivots == [high]
    assert changed is None


def test_dominance_appends_an_opposite_pivot_meeting_min_swing():
    high = RSIPivot(bar_index=10, rsi_value=68.0, kind="high", confirmation_bar_index=12)
    deep_low = RSIPivot(bar_index=14, rsi_value=52.0, kind="low", confirmation_bar_index=16)

    pivots, changed = apply_dominance([high], deep_low, min_swing=8.0)

    assert pivots == [high, deep_low]
    assert changed == "low"


def test_dominance_produces_strict_alternation_over_a_stream():
    stream = [
        RSIPivot(bar_index=2, rsi_value=70.0, kind="high", confirmation_bar_index=4),
        RSIPivot(bar_index=6, rsi_value=72.0, kind="high", confirmation_bar_index=8),
        RSIPivot(bar_index=10, rsi_value=50.0, kind="low", confirmation_bar_index=12),
        RSIPivot(bar_index=14, rsi_value=48.0, kind="low", confirmation_bar_index=16),
        RSIPivot(bar_index=18, rsi_value=66.0, kind="high", confirmation_bar_index=20),
    ]

    pivots = []
    for candidate in stream:
        pivots, _ = apply_dominance(pivots, candidate, min_swing=8.0)

    kinds = [p.kind for p in pivots]
    assert kinds == ["high", "low", "high"]
    assert [p.bar_index for p in pivots] == [6, 14, 18]
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python -m pytest gann-visualizer/backend/tests/test_rsi_pivots.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'analysis.rsi_pivots'`

- [ ] **Step 3: Implement the pivot module**

Create `gann-visualizer/backend/analysis/rsi_pivots.py`:

```python
"""Pure RSI pivot detection.

Two stages, deliberately separated:

1. ``detect_fractal_candidates`` finds local extremes with a FIXED confirmation
   lag of ``right_bars``.  A fixed lag is why fractals are used rather than a
   zigzag, whose confirmation lag varies with price and would anchor lines too
   late to catch their own breaks.
2. ``apply_dominance`` reduces those candidates to a strictly alternating
   high-low-high-low sequence.  It is a *step* function taking one candidate at
   a time, so the sweep can drive it incrementally.  Running it as a batch pass
   over the whole series would let a pivot superseded at bar 150 rewrite what
   was anchored at bar 100 -- a repaint.  See test_rsi_causality.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class GeometryParams:
    """Every geometry knob, in one place.

    Lives here rather than in rsi_sweep so the dependency direction stays
    one-way: rsi_pivots <- rsi_line_policy <- rsi_sweep.  The policy layer needs
    these values but must never import the sweep that calls it.
    """

    left_bars: int = 3
    right_bars: int = 3
    min_swing: float = 8.0
    tolerance: float = 1.5
    min_length: int = 8
    max_span_bars: int = 150


@dataclass(frozen=True)
class RSIPivot:
    bar_index: int
    rsi_value: float
    kind: str  # "high" | "low"
    confirmation_bar_index: int


def compute_rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI. Bars before ``period`` are seeded at a neutral 50."""
    close = close.astype(float)
    rsi = pd.Series(50.0, index=close.index, dtype=float)
    if len(close) <= period:
        return rsi

    delta = close.diff().fillna(0.0)
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = float(gain.iloc[1 : period + 1].mean())
    avg_loss = float(loss.iloc[1 : period + 1].mean())

    def to_rsi(current_gain: float, current_loss: float) -> float:
        if current_loss == 0.0:
            return 100.0
        rs = current_gain / current_loss
        return 100.0 - (100.0 / (1.0 + rs))

    rsi.iloc[period] = to_rsi(avg_gain, avg_loss)

    for idx in range(period + 1, len(close)):
        avg_gain = ((avg_gain * (period - 1)) + float(gain.iloc[idx])) / period
        avg_loss = ((avg_loss * (period - 1)) + float(loss.iloc[idx])) / period
        rsi.iloc[idx] = to_rsi(avg_gain, avg_loss)

    return rsi


def detect_fractal_candidates(
    rsi: pd.Series, left_bars: int, right_bars: int
) -> list[RSIPivot]:
    """Local extremes, each confirmed exactly ``right_bars`` after its own bar."""
    values = rsi.astype(float).reset_index(drop=True)
    candidates: list[RSIPivot] = []

    for idx in range(left_bars, len(values) - right_bars):
        center = values.iloc[idx]
        if pd.isna(center):
            continue

        left = values.iloc[idx - left_bars : idx]
        right = values.iloc[idx + 1 : idx + 1 + right_bars]
        neighbours = pd.concat([left, right])
        if neighbours.isna().any():
            continue

        if (center > neighbours).all():
            kind = "high"
        elif (center < neighbours).all():
            kind = "low"
        else:
            continue

        candidates.append(
            RSIPivot(
                bar_index=idx,
                rsi_value=float(center),
                kind=kind,
                confirmation_bar_index=idx + right_bars,
            )
        )

    return candidates


def apply_dominance(
    pivots: list[RSIPivot], candidate: RSIPivot, min_swing: float
) -> tuple[list[RSIPivot], str | None]:
    """Fold one candidate into the running pivot list.

    Returns ``(new_pivots, changed_kind)``.  ``changed_kind`` is the pivot kind
    whose sequence changed, or ``None`` when the candidate was discarded.  The
    input list is never mutated.
    """
    if not pivots:
        return [candidate], candidate.kind

    last = pivots[-1]

    if last.kind == candidate.kind:
        if candidate.kind == "high":
            more_extreme = candidate.rsi_value > last.rsi_value
        else:
            more_extreme = candidate.rsi_value < last.rsi_value
        if more_extreme:
            return pivots[:-1] + [candidate], candidate.kind
        return pivots, None

    if abs(candidate.rsi_value - last.rsi_value) >= min_swing:
        return pivots + [candidate], candidate.kind

    return pivots, None
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python -m pytest gann-visualizer/backend/tests/test_rsi_pivots.py -v`

Expected: PASS, `8 passed`

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/analysis/rsi_pivots.py gann-visualizer/backend/tests/test_rsi_pivots.py
git commit -m "feat: add pure RSI pivot layer with incremental dominance"
```

---

## Task 2: Anchor Policies

**Files:**
- Create: `gann-visualizer/backend/analysis/rsi_line_policy.py`
- Create: `gann-visualizer/backend/tests/test_rsi_line_policy.py`

- [ ] **Step 1: Write the failing tests**

Create `gann-visualizer/backend/tests/test_rsi_line_policy.py`:

```python
import os
import sys

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from analysis.rsi_line_policy import (
    NearestPairAnchorPolicy,
    RSILine,
    WalkBackAnchorPolicy,
    count_touches,
)
from analysis.rsi_pivots import GeometryParams, RSIPivot


def high(bar, value):
    return RSIPivot(bar_index=bar, rsi_value=value, kind="high", confirmation_bar_index=bar + 3)


def low(bar, value):
    return RSIPivot(bar_index=bar, rsi_value=value, kind="low", confirmation_bar_index=bar + 3)


PARAMS = GeometryParams(min_length=8, max_span_bars=150, tolerance=1.5)


def test_line_value_interpolates_and_extrapolates():
    line = RSILine(start_bar_index=10, end_bar_index=20, start_rsi=70.0, end_rsi=60.0, direction="down")

    assert line.value_at(10) == 70.0
    assert line.value_at(15) == 65.0
    assert line.value_at(20) == 60.0
    assert line.value_at(30) == 50.0  # extends forward past its anchors
    assert line.slope == -1.0


def test_walk_back_picks_the_furthest_valid_anchor():
    # 70 / 64 / 62 / 58 all sit on one descending slope.
    pivots = [high(10, 70.0), high(20, 64.0), high(30, 62.0), high(40, 58.0)]

    anchor = WalkBackAnchorPolicy().anchor(pivots, pivots[-1], PARAMS)

    assert anchor is not None
    assert anchor.bar_index == 10


def test_walk_back_refuses_an_anchor_whose_line_a_middle_pivot_pokes_through():
    # 68 at bar 30 sits far above the 70 -> 58 line, so bar 10 is not usable.
    pivots = [high(10, 70.0), high(20, 64.0), high(30, 68.0), high(40, 58.0)]

    anchor = WalkBackAnchorPolicy().anchor(pivots, pivots[-1], PARAMS)

    assert anchor is not None
    assert anchor.bar_index == 30


def test_walk_back_rejects_an_anchor_beyond_the_span_cap():
    pivots = [high(10, 70.0), high(200, 58.0)]
    capped = GeometryParams(min_length=8, max_span_bars=150, tolerance=1.5)

    assert WalkBackAnchorPolicy().anchor(pivots, pivots[-1], capped) is None


def test_walk_back_rejects_an_anchor_closer_than_min_length():
    pivots = [high(10, 70.0), high(15, 58.0)]

    assert WalkBackAnchorPolicy().anchor(pivots, pivots[-1], PARAMS) is None


def test_walk_back_requires_a_lower_high_for_a_down_line():
    pivots = [high(10, 58.0), high(20, 70.0)]

    assert WalkBackAnchorPolicy().anchor(pivots, pivots[-1], PARAMS) is None


def test_walk_back_requires_a_higher_low_for_an_up_line():
    rising = [low(10, 30.0), low(20, 42.0), low(30, 48.0)]

    anchor = WalkBackAnchorPolicy().anchor(rising, rising[-1], PARAMS)

    assert anchor is not None
    assert anchor.bar_index == 10

    falling = [low(10, 48.0), low(20, 30.0)]
    assert WalkBackAnchorPolicy().anchor(falling, falling[-1], PARAMS) is None


def test_nearest_pair_policy_takes_the_closest_anchor_instead():
    pivots = [high(10, 70.0), high(20, 64.0), high(30, 62.0), high(40, 58.0)]

    anchor = NearestPairAnchorPolicy().anchor(pivots, pivots[-1], PARAMS)

    assert anchor is not None
    assert anchor.bar_index == 30


def test_count_touches_counts_anchors_and_excludes_pivots_outside_tolerance():
    # The 70 -> 58 line over 30 bars has slope -0.4, so it predicts:
    #   bar 10 -> 70.0  (anchor, exact)
    #   bar 20 -> 66.0  vs pivot 64.0 -> 2.0 away, OUTSIDE the 1.5 tolerance
    #   bar 30 -> 62.0  (exact touch)
    #   bar 40 -> 58.0  (anchor, exact)
    pivots = [high(10, 70.0), high(20, 64.0), high(30, 62.0), high(40, 58.0)]
    line = RSILine(start_bar_index=10, end_bar_index=40, start_rsi=70.0, end_rsi=58.0, direction="down")

    assert count_touches(line, pivots, tolerance=1.5) == 3
    assert count_touches(line, pivots, tolerance=2.5) == 4  # widening admits bar 20


def test_count_touches_ignores_pivots_outside_the_line_span():
    pivots = [high(5, 80.0), high(10, 70.0), high(40, 58.0), high(50, 40.0)]
    line = RSILine(start_bar_index=10, end_bar_index=40, start_rsi=70.0, end_rsi=58.0, direction="down")

    assert count_touches(line, pivots, tolerance=1.5) == 2  # only the two anchors
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python -m pytest gann-visualizer/backend/tests/test_rsi_line_policy.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'analysis.rsi_line_policy'`

- [ ] **Step 3: Implement the policy module**

Create `gann-visualizer/backend/analysis/rsi_line_policy.py`:

```python
"""Anchor policies -- the only swappable part of the geometry engine.

A policy answers one question: given the confirmed same-kind pivots visible at
this bar and the newest of them, which EARLIER pivot should anchor the line?

Policies are pure and stateless.  They never see the bar loop and never see
pivots that have not yet confirmed -- the sweep filters that before calling, so
causality is structural rather than a rule each policy must remember.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from analysis.rsi_pivots import GeometryParams, RSIPivot


@dataclass(frozen=True)
class RSILine:
    start_bar_index: int
    end_bar_index: int
    start_rsi: float
    end_rsi: float
    direction: str  # "up" | "down"

    @property
    def slope(self) -> float:
        span = self.end_bar_index - self.start_bar_index
        if span == 0:
            return 0.0
        return (self.end_rsi - self.start_rsi) / span

    def value_at(self, bar_index: int) -> float:
        """Total on the whole number line -- a trendline extends forward."""
        return self.start_rsi + self.slope * (bar_index - self.start_bar_index)


def line_between(anchor: RSIPivot, newest: RSIPivot) -> RSILine:
    return RSILine(
        start_bar_index=anchor.bar_index,
        end_bar_index=newest.bar_index,
        start_rsi=anchor.rsi_value,
        end_rsi=newest.rsi_value,
        direction="down" if newest.kind == "high" else "up",
    )


def count_touches(line: RSILine, same_kind: list[RSIPivot], tolerance: float) -> int:
    """Same-kind pivots sitting within ``tolerance`` of the line, anchors included.

    Diagnostic only -- never used for selection.  The walk-back rule already
    maximises it by taking the furthest valid anchor.
    """
    return sum(
        1
        for pivot in same_kind
        if line.start_bar_index <= pivot.bar_index <= line.end_bar_index
        and abs(pivot.rsi_value - line.value_at(pivot.bar_index)) <= tolerance
    )


def _pokes_through(
    anchor: RSIPivot, newest: RSIPivot, same_kind: list[RSIPivot], tolerance: float
) -> bool:
    """True when a pivot between the anchors sits on the wrong side of the line."""
    line = line_between(anchor, newest)
    for pivot in same_kind:
        if not (anchor.bar_index < pivot.bar_index < newest.bar_index):
            continue
        value = line.value_at(pivot.bar_index)
        if newest.kind == "high" and pivot.rsi_value > value + tolerance:
            return True
        if newest.kind == "low" and pivot.rsi_value < value - tolerance:
            return True
    return False


def _slope_sense_ok(anchor: RSIPivot, newest: RSIPivot) -> bool:
    if newest.kind == "high":
        return newest.rsi_value < anchor.rsi_value  # lower high -> falling line
    return newest.rsi_value > anchor.rsi_value      # higher low -> rising line


class AnchorPolicy(Protocol):
    name: str

    def anchor(
        self, same_kind: list[RSIPivot], newest: RSIPivot, params: GeometryParams
    ) -> RSIPivot | None: ...


class WalkBackAnchorPolicy:
    """Take the FURTHEST-back anchor that no intermediate pivot pokes through."""

    name = "walk_back"

    def anchor(
        self, same_kind: list[RSIPivot], newest: RSIPivot, params: GeometryParams
    ) -> RSIPivot | None:
        for candidate in same_kind:  # oldest first
            if candidate.bar_index >= newest.bar_index:
                continue
            span = newest.bar_index - candidate.bar_index
            if span < params.min_length or span > params.max_span_bars:
                continue
            if not _slope_sense_ok(candidate, newest):
                continue
            if _pokes_through(candidate, newest, same_kind, params.tolerance):
                continue
            return candidate
        return None


class NearestPairAnchorPolicy:
    """A/B rival standing in for today's all-pairs builder.

    Takes the NEAREST valid anchor and does not check poke-through, which is
    what produces the 89% pivot-skipping rate measured in spec section 1.1.
    """

    name = "nearest_pair"

    def anchor(
        self, same_kind: list[RSIPivot], newest: RSIPivot, params: GeometryParams
    ) -> RSIPivot | None:
        for candidate in reversed(same_kind):  # newest first
            if candidate.bar_index >= newest.bar_index:
                continue
            span = newest.bar_index - candidate.bar_index
            if span < params.min_length or span > params.max_span_bars:
                continue
            if not _slope_sense_ok(candidate, newest):
                continue
            return candidate
        return None
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python -m pytest gann-visualizer/backend/tests/test_rsi_line_policy.py -v`

Expected: PASS, `10 passed`

> This task depends only on `analysis.rsi_pivots` (Task 1), so its tests run standalone.

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/analysis/rsi_line_policy.py gann-visualizer/backend/tests/test_rsi_line_policy.py
git commit -m "feat: add walk-back and nearest-pair anchor policies"
```

---

## Task 3: The Causal Sweep

**Files:**
- Create: `gann-visualizer/backend/analysis/rsi_sweep.py`
- Create: `gann-visualizer/backend/tests/test_rsi_sweep.py`

- [ ] **Step 1: Write the failing tests**

Create `gann-visualizer/backend/tests/test_rsi_sweep.py`:

```python
import os
import sys

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

import pandas as pd

from analysis.rsi_line_policy import WalkBackAnchorPolicy
from analysis.rsi_pivots import GeometryParams
from analysis.rsi_sweep import run_causal_sweep


def falling_then_breaking_rsi():
    """Three descending RSI peaks, then a decisive break upward."""
    return pd.Series(
        [
            50.0, 52.0, 70.0, 55.0, 50.0,      # peak at bar 2
            48.0, 52.0, 64.0, 52.0, 48.0,      # peak at bar 7
            46.0, 50.0, 60.0, 50.0, 45.0,      # peak at bar 12
            44.0, 48.0, 56.0, 50.0, 46.0,      # peak at bar 17
            48.0, 62.0, 75.0, 80.0, 82.0,      # decisive break up
        ]
    )


PARAMS = GeometryParams(
    left_bars=2, right_bars=2, min_swing=6.0,
    tolerance=1.5, min_length=5, max_span_bars=150,
)


def rsi_with_repeated_reanchors():
    """Many descending peaks in a row, so the down-line re-anchors repeatedly.

    A short series that never re-anchors would let the handoff-overlap bug pass
    unnoticed, so this fixture exists specifically to force handoffs.
    """
    values = []
    for cycle in range(9):
        peak = 74.0 - cycle * 2.0
        trough = 36.0 + cycle * 0.4
        values.extend([trough, trough + 5, peak - 3, peak, peak - 4, trough + 3])
    values.extend([60.0, 72.0, 84.0, 88.0, 90.0])  # decisive break up
    return pd.Series(values)


def test_sweep_never_holds_more_than_one_active_line_per_direction():
    for rsi in (falling_then_breaking_rsi(), rsi_with_repeated_reanchors()):
        result = run_causal_sweep(rsi, WalkBackAnchorPolicy(), PARAMS)

        for bar in range(len(rsi)):
            live = [
                s for s in result.segments
                if s.valid_from_bar <= bar <= s.valid_to_bar
            ]
            for direction in ("up", "down"):
                count = len([s for s in live if s.line.direction == direction])
                assert count <= 1, (
                    f"bar {bar}: {count} live {direction} lines "
                    f"(segments {[s.segment_id for s in live if s.line.direction == direction]})"
                )


def test_the_fixture_actually_exercises_re_anchoring():
    """Guards the test above: an invariant only proven on data that never
    re-anchors proves nothing about the handoff boundary."""
    result = run_causal_sweep(rsi_with_repeated_reanchors(), WalkBackAnchorPolicy(), PARAMS)

    assert any(s.end_reason == "re_anchored" for s in result.segments)


def test_segments_never_have_an_inverted_validity_window():
    for rsi in (falling_then_breaking_rsi(), rsi_with_repeated_reanchors()):
        result = run_causal_sweep(rsi, WalkBackAnchorPolicy(), PARAMS)
        for segment in result.segments:
            assert segment.valid_to_bar >= segment.valid_from_bar


def test_sweep_emits_a_long_signal_when_rsi_breaks_a_down_line():
    rsi = falling_then_breaking_rsi()
    result = run_causal_sweep(rsi, WalkBackAnchorPolicy(), PARAMS)

    longs = [s for s in result.signals if s.side == "LONG"]
    assert longs, "expected at least one LONG break"

    signal = longs[0]
    assert signal.rsi_value > signal.line_value_at_break
    assert any(s.segment_id == signal.segment_id for s in result.segments)


def test_a_broken_segment_is_closed_with_the_broken_reason():
    rsi = falling_then_breaking_rsi()
    result = run_causal_sweep(rsi, WalkBackAnchorPolicy(), PARAMS)

    signal = [s for s in result.signals if s.side == "LONG"][0]
    segment = [s for s in result.segments if s.segment_id == signal.segment_id][0]

    assert segment.end_reason == "broken"
    assert segment.valid_to_bar == signal.bar_index


def test_a_broken_line_never_fires_twice():
    rsi = falling_then_breaking_rsi()
    result = run_causal_sweep(rsi, WalkBackAnchorPolicy(), PARAMS)

    fired = [s.segment_id for s in result.signals]
    assert len(fired) == len(set(fired))


def test_no_segment_becomes_valid_before_its_newest_anchor_confirms():
    rsi = falling_then_breaking_rsi()
    result = run_causal_sweep(rsi, WalkBackAnchorPolicy(), PARAMS)

    assert result.segments
    for segment in result.segments:
        assert segment.valid_from_bar >= segment.anchor_b.confirmation_bar_index
        assert segment.anchor_a.bar_index < segment.anchor_b.bar_index


def test_no_pivot_ever_pokes_through_its_own_segment():
    rsi = falling_then_breaking_rsi()
    result = run_causal_sweep(rsi, WalkBackAnchorPolicy(), PARAMS)

    assert result.segments
    for segment in result.segments:
        same_kind = [p for p in result.pivots if p.kind == segment.anchor_b.kind]
        for pivot in same_kind:
            if not (segment.line.start_bar_index < pivot.bar_index < segment.line.end_bar_index):
                continue
            value = segment.line.value_at(pivot.bar_index)
            if segment.line.direction == "down":
                assert pivot.rsi_value <= value + PARAMS.tolerance
            else:
                assert pivot.rsi_value >= value - PARAMS.tolerance


def test_flat_rsi_produces_no_segments_and_no_signals():
    rsi = pd.Series([50.0] * 40)

    result = run_causal_sweep(rsi, WalkBackAnchorPolicy(), PARAMS)

    assert result.segments == []
    assert result.signals == []


def test_segment_ids_are_unique_and_ascending():
    rsi = falling_then_breaking_rsi()
    result = run_causal_sweep(rsi, WalkBackAnchorPolicy(), PARAMS)

    ids = [s.segment_id for s in result.segments]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python -m pytest gann-visualizer/backend/tests/test_rsi_sweep.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'analysis.rsi_sweep'`

- [ ] **Step 3: Implement the sweep**

Create `gann-visualizer/backend/analysis/rsi_sweep.py`:

```python
"""The causal RSI trendline sweep.

This module owns ALL mutable geometry state and contains the only bar loop in
the system.  It answers exactly one question: what line was a trader looking
at, at bar N?

Invariants, asserted by test_rsi_sweep.py:
  * at most one active line per direction at any bar
  * a segment is never valid before its newest anchor confirms
  * no same-kind pivot pokes through its own segment
  * a broken line never fires twice
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace

import pandas as pd

from analysis.rsi_line_policy import (
    AnchorPolicy,
    RSILine,
    count_touches,
    line_between,
)
from analysis.rsi_pivots import (
    GeometryParams,
    RSIPivot,
    apply_dominance,
    detect_fractal_candidates,
)


@dataclass(frozen=True)
class LineSegment:
    segment_id: int
    line: RSILine
    anchor_a: RSIPivot
    anchor_b: RSIPivot
    valid_from_bar: int
    valid_to_bar: int | None
    end_reason: str | None  # "broken" | "re_anchored" | "end_of_data"
    touch_count: int


@dataclass(frozen=True)
class BreakSignal:
    bar_index: int
    side: str  # "LONG" | "SHORT"
    segment_id: int
    line_value_at_break: float
    rsi_value: float


@dataclass(frozen=True)
class SweepResult:
    pivots: list[RSIPivot]
    segments: list[LineSegment]
    signals: list[BreakSignal]


_SIDE_FOR_DIRECTION = {"down": "LONG", "up": "SHORT"}


def run_causal_sweep(
    rsi: pd.Series, policy: AnchorPolicy, params: GeometryParams
) -> SweepResult:
    values = rsi.astype(float).reset_index(drop=True)
    bar_count = len(values)

    candidates_at: dict[int, list[RSIPivot]] = defaultdict(list)
    for candidate in detect_fractal_candidates(values, params.left_bars, params.right_bars):
        candidates_at[candidate.confirmation_bar_index].append(candidate)

    pivots: list[RSIPivot] = []
    active: dict[str, LineSegment | None] = {"down": None, "up": None}
    segments: list[LineSegment] = []
    signals: list[BreakSignal] = []
    next_segment_id = 1

    for bar in range(bar_count):
        # 1. fold in every pivot that CONFIRMS on this bar
        changed_kinds: list[str] = []
        for candidate in candidates_at.get(bar, []):
            pivots, changed_kind = apply_dominance(pivots, candidate, params.min_swing)
            if changed_kind is not None and changed_kind not in changed_kinds:
                changed_kinds.append(changed_kind)

        # 2. re-anchor the affected directions
        for kind in changed_kinds:
            direction = "down" if kind == "high" else "up"
            same_kind = [p for p in pivots if p.kind == kind]
            newest = same_kind[-1]

            anchor = policy.anchor(same_kind, newest, params)
            if anchor is None:
                continue

            open_segment = active[direction]
            if open_segment is not None:
                # Half-open handoff: the successor owns `bar`, so the outgoing
                # segment ends at bar - 1.  Closing it at `bar` would leave TWO
                # live lines in one direction at every handoff -- precisely the
                # duplicate-line defect this redesign exists to remove.
                # A `broken` segment, by contrast, DOES include its break bar:
                # the line was genuinely live at the moment it broke.
                retired = replace(
                    open_segment, valid_to_bar=bar - 1, end_reason="re_anchored"
                )
                if retired.valid_to_bar >= retired.valid_from_bar:
                    segments.append(retired)

            line = line_between(anchor, newest)
            active[direction] = LineSegment(
                segment_id=next_segment_id,
                line=line,
                anchor_a=anchor,
                anchor_b=newest,
                valid_from_bar=bar,
                valid_to_bar=None,
                end_reason=None,
                touch_count=count_touches(line, same_kind, params.tolerance),
            )
            next_segment_id += 1

        # 3. test the active lines for a break
        for direction in ("down", "up"):
            segment = active[direction]
            if segment is None or bar <= segment.valid_from_bar:
                continue

            line = segment.line
            previous_line = line.value_at(bar - 1)
            current_line = line.value_at(bar)
            previous_rsi = float(values.iloc[bar - 1])
            current_rsi = float(values.iloc[bar])

            if direction == "down":
                crossed = previous_rsi <= previous_line and current_rsi > current_line
            else:
                crossed = previous_rsi >= previous_line and current_rsi < current_line

            if not crossed:
                continue

            segments.append(replace(segment, valid_to_bar=bar, end_reason="broken"))
            signals.append(
                BreakSignal(
                    bar_index=bar,
                    side=_SIDE_FOR_DIRECTION[direction],
                    segment_id=segment.segment_id,
                    line_value_at_break=float(current_line),
                    rsi_value=current_rsi,
                )
            )
            active[direction] = None

    # 4. close whatever is still open when the data runs out
    last_bar = bar_count - 1
    for segment in active.values():
        if segment is not None:
            segments.append(
                replace(segment, valid_to_bar=last_bar, end_reason="end_of_data")
            )

    segments.sort(key=lambda segment: segment.segment_id)
    return SweepResult(pivots=pivots, segments=segments, signals=signals)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python -m pytest gann-visualizer/backend/tests/test_rsi_sweep.py gann-visualizer/backend/tests/test_rsi_line_policy.py -v`

Expected: PASS, `20 passed`

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/analysis/rsi_sweep.py gann-visualizer/backend/tests/test_rsi_sweep.py
git commit -m "feat: add causal RSI trendline sweep"
```

---

## Task 4: Causality Regression Test

This is the guard for the repaint defect described in spec §5.2. It must fail against any implementation that batches the dominance pass.

**Files:**
- Create: `gann-visualizer/backend/tests/test_rsi_causality.py`

- [ ] **Step 1: Write the test**

Create `gann-visualizer/backend/tests/test_rsi_causality.py`:

```python
"""Prefix-stability: what the sweep emitted for bars <= k must never change
as more bars arrive.  This is the regression test for the repaint defect where
a pivot superseded at bar 150 rewrites what was anchored at bar 100.
"""

import os
import sys

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

import pandas as pd
import pytest

from analysis.rsi_line_policy import NearestPairAnchorPolicy, WalkBackAnchorPolicy
from analysis.rsi_pivots import compute_rsi_series
from analysis.rsi_pivots import GeometryParams
from analysis.rsi_sweep import run_causal_sweep

CANDLES = 'C:/Dev/GannTesting/logs/backend/runs/BTCUSDT/15/2026-07-10_barctx_v2/candles.csv'

PARAMS = GeometryParams(
    left_bars=3, right_bars=3, min_swing=8.0,
    tolerance=1.5, min_length=8, max_span_bars=150,
)


def synthetic_rsi():
    """A saw-tooth with progressively lower highs -- forces dominance replacements."""
    values = []
    for cycle in range(12):
        peak = 72.0 - cycle * 1.5
        trough = 34.0 + cycle * 0.5
        values.extend([trough, trough + 6, peak - 4, peak, peak - 5, trough + 4])
    return pd.Series(values)


def signal_fingerprint(result, upto_bar):
    return [
        (s.bar_index, s.side, round(s.line_value_at_break, 6))
        for s in result.signals
        if s.bar_index <= upto_bar
    ]


def segment_fingerprint(result, upto_bar):
    return [
        (
            s.line.start_bar_index, s.line.end_bar_index,
            round(s.line.start_rsi, 6), round(s.line.end_rsi, 6),
            s.valid_from_bar,
        )
        for s in result.segments
        if s.valid_from_bar <= upto_bar
    ]


@pytest.mark.parametrize("policy", [WalkBackAnchorPolicy(), NearestPairAnchorPolicy()])
def test_synthetic_prefix_is_stable_as_more_bars_arrive(policy):
    rsi = synthetic_rsi()
    full = run_causal_sweep(rsi, policy, PARAMS)

    for cut in range(30, len(rsi), 7):
        prefix = run_causal_sweep(rsi.iloc[:cut].reset_index(drop=True), policy, PARAMS)
        horizon = cut - PARAMS.right_bars - 1

        assert signal_fingerprint(prefix, horizon) == signal_fingerprint(full, horizon), (
            f"signals for bars <= {horizon} changed when data grew to {cut} bars"
        )
        assert segment_fingerprint(prefix, horizon) == segment_fingerprint(full, horizon), (
            f"segments valid by bar {horizon} changed when data grew to {cut} bars"
        )


@pytest.mark.skipif(not os.path.exists(CANDLES), reason="run fixture not present")
def test_real_candles_prefix_is_stable():
    candles = pd.read_csv(CANDLES).reset_index(drop=True)
    rsi = compute_rsi_series(candles['close'], period=14)
    policy = WalkBackAnchorPolicy()
    full = run_causal_sweep(rsi, policy, PARAMS)

    for cut in (400, 600, 800):
        prefix = run_causal_sweep(rsi.iloc[:cut].reset_index(drop=True), policy, PARAMS)
        horizon = cut - PARAMS.right_bars - 1

        assert signal_fingerprint(prefix, horizon) == signal_fingerprint(full, horizon)
        assert segment_fingerprint(prefix, horizon) == segment_fingerprint(full, horizon)
```

- [ ] **Step 2: Run the test and confirm it passes**

Run: `python -m pytest gann-visualizer/backend/tests/test_rsi_causality.py -v`

Expected: PASS, `3 passed` (2 parametrized synthetic + 1 real-candle)

If the real-candle test is skipped, the run directory is absent — that is acceptable, but note it. If either test **fails**, the sweep has a lookahead defect; do not proceed to Task 5.

- [ ] **Step 3: Verify the test actually catches a repaint**

Temporarily break causality to prove the test has teeth. In `gann-visualizer/backend/analysis/rsi_sweep.py`, replace the loop body at step 1 with a batch pre-pass:

```python
    # TEMPORARY - deliberately non-causal, to prove the test fails
    all_pivots = []
    for candidate in detect_fractal_candidates(values, params.left_bars, params.right_bars):
        all_pivots, _ = apply_dominance(all_pivots, candidate, params.min_swing)
```

and inside the bar loop use `same_kind = [p for p in all_pivots if p.kind == kind and p.confirmation_bar_index <= bar]`.

Run: `python -m pytest gann-visualizer/backend/tests/test_rsi_causality.py -v`

Expected: **FAIL** — at least one prefix fingerprint mismatch.

Then `git checkout gann-visualizer/backend/analysis/rsi_sweep.py` to restore, and re-run to confirm PASS again.

- [ ] **Step 4: Commit**

```bash
git add gann-visualizer/backend/tests/test_rsi_causality.py
git commit -m "test: add prefix-stability regression test for RSI repaint"
```

---

## Task 5: Reduce rsi_geometry.py to a Shim and Delete the Dead Builders

**Files:**
- Modify: `gann-visualizer/backend/analysis/rsi_geometry.py`
- Modify: `gann-visualizer/backend/tests/test_rsi_geometry.py`

- [ ] **Step 1: Replace the geometry test file**

Overwrite `gann-visualizer/backend/tests/test_rsi_geometry.py` entirely:

```python
"""rsi_geometry is now a compatibility shim over the three focused modules.

The previous contents tested DeterministicPivotLineBuilder, which this change
deletes.  Two of those four tests were already failing on main because their
fixtures used pivot spans below the min_length=8 default.
"""

import os
import sys

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

import pandas as pd
import pytest

import analysis.rsi_geometry as rsi_geometry


def test_shim_reexports_the_public_surface():
    for name in (
        "RSIPivot", "RSILine", "GeometryParams", "LineSegment", "BreakSignal",
        "SweepResult", "compute_rsi_series", "detect_fractal_candidates",
        "apply_dominance", "run_causal_sweep",
        "WalkBackAnchorPolicy", "NearestPairAnchorPolicy",
    ):
        assert hasattr(rsi_geometry, name), f"shim is missing {name}"


def test_shim_rsi_matches_the_pivot_module():
    from analysis.rsi_pivots import compute_rsi_series as canonical

    close = pd.Series([float(100 + (i % 7)) for i in range(60)])
    pd.testing.assert_series_equal(rsi_geometry.compute_rsi_series(close), canonical(close))


@pytest.mark.parametrize(
    "removed",
    [
        "DeterministicPivotLineBuilder",
        "detect_rsi_pivots",
        "detect_rsi_line_breaks",
        "RSIBreakSignal",
    ],
)
def test_superseded_symbols_are_gone(removed):
    assert not hasattr(rsi_geometry, removed), (
        f"{removed} was superseded by the causal sweep and must not be re-exported"
    )
```

- [ ] **Step 2: Run and confirm it fails**

Run: `python -m pytest gann-visualizer/backend/tests/test_rsi_geometry.py -v`

Expected: FAIL — the shim symbols do not exist yet and the superseded ones still do.

- [ ] **Step 3: Replace rsi_geometry.py with the shim**

Overwrite `gann-visualizer/backend/analysis/rsi_geometry.py` entirely:

```python
"""Compatibility shim.

The geometry engine now lives in three focused modules:

    analysis.rsi_pivots       RSI series, fractal candidates, dominance
    analysis.rsi_line_policy  anchor policies and the line primitive
    analysis.rsi_sweep        the causal state machine

Prefer importing from those directly.  This module exists so existing imports
keep resolving.

Deleted here, deliberately:
    DeterministicPivotLineBuilder.build_lines        -> NearestPairAnchorPolicy
    DeterministicPivotLineBuilder.build_best_fit_lines (RANSAC)
    DeterministicPivotLineBuilder.cluster_best_fit_lines   (0 callers)
    DeterministicPivotLineBuilder._ols_best_fit            (0 callers)
    DeterministicPivotLineBuilder._total_least_squares     (0 callers)
    detect_rsi_pivots / detect_rsi_line_breaks       -> run_causal_sweep

RANSAC and the other best-fit builders are gone on purpose: a regression line
has RSI on both sides of it by construction, so "the break" is not a distinct
event.  This strategy needs a line that is touched, then broken.
"""

from __future__ import annotations

from analysis.rsi_line_policy import (
    AnchorPolicy,
    NearestPairAnchorPolicy,
    RSILine,
    WalkBackAnchorPolicy,
    count_touches,
    line_between,
)
from analysis.rsi_pivots import (
    GeometryParams,
    RSIPivot,
    apply_dominance,
    compute_rsi_series,
    detect_fractal_candidates,
)
from analysis.rsi_sweep import (
    BreakSignal,
    LineSegment,
    SweepResult,
    run_causal_sweep,
)

__all__ = [
    "AnchorPolicy",
    "BreakSignal",
    "GeometryParams",
    "LineSegment",
    "NearestPairAnchorPolicy",
    "RSILine",
    "RSIPivot",
    "SweepResult",
    "WalkBackAnchorPolicy",
    "apply_dominance",
    "compute_rsi_series",
    "count_touches",
    "detect_fractal_candidates",
    "line_between",
    "run_causal_sweep",
]
```

- [ ] **Step 4: Run and confirm it passes**

Run: `python -m pytest gann-visualizer/backend/tests/test_rsi_geometry.py -v`

Expected: PASS, `6 passed`

- [ ] **Step 5: Confirm nothing else imported the deleted symbols**

Run:

```bash
grep -rn "DeterministicPivotLineBuilder\|detect_rsi_pivots\|detect_rsi_line_breaks\|build_best_fit_lines\|cluster_best_fit_lines" \
  --include=*.py gann-visualizer/backend | grep -v __pycache__
```

Expected: only `gann-visualizer/backend/analysis/rsi_trendline_hypothesis.py` (fixed in Task 6) and the shim's own docstring.

- [ ] **Step 6: Commit**

```bash
git add gann-visualizer/backend/analysis/rsi_geometry.py gann-visualizer/backend/tests/test_rsi_geometry.py
git commit -m "refactor: reduce rsi_geometry to a shim, delete dead builders"
```

---

## Task 6: Rewrite the Hypothesis — Sweep, Swing Stop, Line Timeline

Implements spec §6.1 (swing stop), §6.2 (max hold), §7.1 (line timeline), §7.2 (detailed log), §8 (skip accounting).

**Files:**
- Modify: `gann-visualizer/backend/analysis/rsi_trendline_hypothesis.py`
- Modify: `gann-visualizer/backend/tests/test_rsi_trendline_hypothesis.py`

- [ ] **Step 1: Write the failing tests**

Overwrite `gann-visualizer/backend/tests/test_rsi_trendline_hypothesis.py`:

```python
import os
import sys

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

import pandas as pd

from analysis.rsi_trendline_hypothesis import RSITrendlineBreakHypothesis, swing_stop_price


def test_swing_stop_uses_the_lowest_low_in_the_lookback_for_a_long():
    candles = pd.DataFrame({
        "bar_index": list(range(6)),
        "high": [105.0, 106.0, 107.0, 108.0, 109.0, 110.0],
        "low": [100.0, 96.0, 99.0, 101.0, 103.0, 104.0],
    })

    stop = swing_stop_price(candles, bar_index=5, side="LONG", lookback=5, buffer=0.0)

    assert stop == 96.0


def test_swing_stop_uses_the_highest_high_in_the_lookback_for_a_short():
    candles = pd.DataFrame({
        "bar_index": list(range(6)),
        "high": [105.0, 112.0, 107.0, 108.0, 109.0, 110.0],
        "low": [100.0, 96.0, 99.0, 101.0, 103.0, 104.0],
    })

    stop = swing_stop_price(candles, bar_index=5, side="SHORT", lookback=5, buffer=0.0)

    assert stop == 112.0


def test_swing_stop_applies_the_buffer_outward():
    candles = pd.DataFrame({
        "bar_index": [0, 1],
        "high": [110.0, 110.0],
        "low": [100.0, 100.0],
    })

    long_stop = swing_stop_price(candles, bar_index=1, side="LONG", lookback=2, buffer=0.01)
    short_stop = swing_stop_price(candles, bar_index=1, side="SHORT", lookback=2, buffer=0.01)

    assert long_stop == 99.0
    assert short_stop == 111.1


def build_trending_candles(bars=420):
    """Rising price with regular pullbacks -- produces RSI peaks and breaks."""
    rows = []
    price = 100.0
    for i in range(bars):
        price += 0.9 if (i % 11) < 8 else -1.6
        rows.append({
            "bar_index": i,
            "time": pd.Timestamp("2026-01-01") + pd.Timedelta(minutes=15 * i),
            "open": price,
            "high": price + 0.8,
            "low": price - 0.8,
            "close": price,
            "volume": 1.0,
        })
    return pd.DataFrame(rows)


def test_hypothesis_returns_a_trade_scored_result_with_a_line_timeline():
    result = RSITrendlineBreakHypothesis().evaluate(pd.DataFrame(), candles_df=build_trending_candles())

    assert result["trade_scored"] is True
    assert "exit_optimization" in result
    assert isinstance(result["detailed_log"], list)
    assert isinstance(result["line_timeline"], list)
    assert isinstance(result["rsi_series"], list)
    assert isinstance(result["skipped"], dict)


def test_every_signal_links_to_a_segment_in_the_timeline():
    result = RSITrendlineBreakHypothesis().evaluate(pd.DataFrame(), candles_df=build_trending_candles())

    timeline_ids = {segment["segment_id"] for segment in result["line_timeline"]}
    assert result["detailed_log"], "expected at least one trade-scored signal"

    for entry in result["detailed_log"]:
        assert entry["segment_id"] in timeline_ids
        assert entry["stop_rule"] == "swing_extreme"
        assert entry["swing_lookback"] == 20
        for field in ("rsi_value", "stop_price", "best_r", "entry_price", "outcome", "net_pnl"):
            assert field in entry


def test_timeline_segments_carry_a_validity_window_and_anchors():
    result = RSITrendlineBreakHypothesis().evaluate(pd.DataFrame(), candles_df=build_trending_candles())

    assert result["line_timeline"]
    for segment in result["line_timeline"]:
        assert segment["valid_from_bar"] <= segment["valid_to_bar"]
        assert segment["direction"] in ("up", "down")
        assert segment["end_reason"] in ("broken", "re_anchored", "end_of_data")
        assert segment["anchor_a"]["bar_index"] < segment["anchor_b"]["bar_index"]


def test_empty_candles_return_an_empty_result_without_raising():
    result = RSITrendlineBreakHypothesis().evaluate(pd.DataFrame(), candles_df=pd.DataFrame())

    assert result["sample_size"] == 0
    assert result["detailed_log"] == []
    assert result["line_timeline"] == []
```

- [ ] **Step 2: Run and confirm it fails**

Run: `python -m pytest gann-visualizer/backend/tests/test_rsi_trendline_hypothesis.py -v`

Expected: FAIL — `ImportError: cannot import name 'swing_stop_price'`

- [ ] **Step 3: Rewrite the hypothesis**

Overwrite `gann-visualizer/backend/analysis/rsi_trendline_hypothesis.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import pandas as pd

from analysis.rsi_line_policy import NearestPairAnchorPolicy, WalkBackAnchorPolicy
from analysis.rsi_pivots import compute_rsi_series
from analysis.rsi_pivots import GeometryParams
from analysis.rsi_sweep import run_causal_sweep
from analysis.signal_trade_simulator import CandleSignal, simulate_trade_grid
from analysis.strategy_analyzer import Hypothesis

POLICIES = {
    "walk_back": WalkBackAnchorPolicy,
    "nearest_pair": NearestPairAnchorPolicy,
}


def swing_stop_price(
    candles: pd.DataFrame, bar_index: int, side: str, lookback: int, buffer: float
) -> float:
    """Stop at the nearest price swing extreme, per the strategy guide.

    Deliberately NOT the breakout candle's own low/high: entering at a candle's
    close with a stop at that same candle's extreme gives a stop ~0.2% of price
    away, which noise removes before the thesis resolves.
    """
    start = max(0, bar_index - lookback)
    window = candles.iloc[start : bar_index + 1]
    if side == "LONG":
        return float(window["low"].min()) * (1.0 - buffer)
    return float(window["high"].max()) * (1.0 + buffer)


class RSITrendlineBreakHypothesis(Hypothesis):
    def __init__(self):
        super().__init__(
            name="RSI Trendline Break Strategy",
            description="Causal RSI trendline breaks filtered by price vs SMA(200).",
        )
        self.set_parameters(
            rsi_period=14,
            sma_period=200,
            anchor_policy="walk_back",
            pivot_left_bars=3,
            pivot_right_bars=3,
            min_swing=8.0,
            tolerance=1.5,
            min_line_length=8,
            max_span_bars=150,
            swing_lookback=20,
            stop_buffer=0.0005,
            r_values=[1.0, 1.5, 2.0, 2.5, 3.0],
            max_hold_bars=40,
        )

    # ------------------------------------------------------------------ #

    def evaluate(self, df: pd.DataFrame, candles_df: pd.DataFrame = None) -> Dict[str, Any]:
        if candles_df is None or candles_df.empty:
            return self._empty_result()

        candles = candles_df.copy().reset_index(drop=True)
        if "bar_index" not in candles.columns:
            candles["bar_index"] = candles.index

        period = int(self.parameters["rsi_period"])
        sma_period = int(self.parameters["sma_period"])
        candles["rsi"] = compute_rsi_series(candles["close"], period=period)
        candles["sma"] = candles["close"].rolling(sma_period, min_periods=sma_period).mean()

        params = GeometryParams(
            left_bars=int(self.parameters["pivot_left_bars"]),
            right_bars=int(self.parameters["pivot_right_bars"]),
            min_swing=float(self.parameters["min_swing"]),
            tolerance=float(self.parameters["tolerance"]),
            min_length=int(self.parameters["min_line_length"]),
            max_span_bars=int(self.parameters["max_span_bars"]),
        )
        policy = POLICIES[str(self.parameters["anchor_policy"])]()
        sweep = run_causal_sweep(candles["rsi"], policy, params)

        segments_by_id = {segment.segment_id: segment for segment in sweep.segments}
        last_bar = int(candles["bar_index"].max())

        skipped = {
            "trend_filter": 0,
            "warmup": 0,
            "invalid_risk": 0,
            "last_bar": 0,
            "missing_candle": 0,
        }
        candidates: List[Dict[str, Any]] = []

        for signal in sweep.signals:
            match = candles.loc[candles["bar_index"] == signal.bar_index]
            if match.empty:
                skipped["missing_candle"] += 1
                continue

            row = match.iloc[0]
            if signal.bar_index >= last_bar:
                skipped["last_bar"] += 1
                continue

            sma_value = row["sma"]
            if pd.isna(sma_value):
                skipped["warmup"] += 1
                continue

            close_price = float(row["close"])
            if signal.side == "LONG" and not close_price > float(sma_value):
                skipped["trend_filter"] += 1
                continue
            if signal.side == "SHORT" and not close_price < float(sma_value):
                skipped["trend_filter"] += 1
                continue

            stop_price = swing_stop_price(
                candles,
                bar_index=int(signal.bar_index),
                side=signal.side,
                lookback=int(self.parameters["swing_lookback"]),
                buffer=float(self.parameters["stop_buffer"]),
            )
            if signal.side == "LONG" and stop_price >= close_price:
                skipped["invalid_risk"] += 1
                continue
            if signal.side == "SHORT" and stop_price <= close_price:
                skipped["invalid_risk"] += 1
                continue

            candidates.append(
                {
                    "signal": CandleSignal(
                        bar_index=int(signal.bar_index),
                        side=signal.side,
                        entry_price=close_price,
                        stop_price=stop_price,
                        signal_time=self._time_string(row.get("time")),
                    ),
                    "detail": self._detail_record(
                        row=row,
                        signal=signal,
                        segment=segments_by_id[signal.segment_id],
                        stop_price=stop_price,
                        candles=candles,
                    ),
                }
            )

        rsi_series = self._rsi_series_payload(candles)
        line_timeline = self._timeline_payload(sweep.segments, candles)

        if not candidates:
            return self._empty_result(
                rsi_series=rsi_series, line_timeline=line_timeline, skipped=skipped
            )

        exit_optimization = simulate_trade_grid(
            candles=candles,
            signals=[c["signal"] for c in candidates],
            r_values=self.parameters["r_values"],
            max_hold_bars=int(self.parameters["max_hold_bars"]),
        )
        best = exit_optimization.get("best") or {}
        best_r = best.get("r_value")
        per_signal = exit_optimization.get("per_signal", {})

        detailed_log: List[Dict[str, Any]] = []
        for index, candidate in enumerate(candidates):
            trade = per_signal.get(f"{candidate['signal'].bar_index}:{index}")
            if trade is None:
                continue
            entry = dict(candidate["detail"])
            entry.update(
                {
                    "best_r": best_r,
                    "target_price": float(trade["target_price"]),
                    "risk_per_unit": float(trade["risk_per_unit"]),
                    "exit_bar_index": int(trade["exit_bar_index"]),
                    "exit_time": trade.get("exit_time"),
                    "exit_price": float(trade["exit_price"]),
                    "exit_reason": trade["exit_reason"],
                    "gross_pnl": float(trade["gross_pnl"]),
                    "net_pnl": float(trade["net_pnl"]),
                    "fees": float(trade["fees"]),
                    "bars_held": int(trade["exit_bar_index"] - trade["bar_index"]),
                    "outcome": trade["outcome"],
                }
            )
            detailed_log.append(entry)

        return self._summarize(
            detailed_log=detailed_log,
            exit_optimization=exit_optimization,
            rsi_series=rsi_series,
            line_timeline=line_timeline,
            skipped=skipped,
        )

    # ------------------------------------------------------------------ #

    @staticmethod
    def _time_string(value: Any) -> str | None:
        if value is None or (not isinstance(value, pd.Timestamp) and pd.isna(value)):
            return None
        if isinstance(value, pd.Timestamp):
            return value.strftime("%Y-%m-%dT%H:%M:%S")
        return str(value)

    def _bar_time(self, candles: pd.DataFrame, bar_index: int) -> str | None:
        if "time" not in candles.columns:
            return None
        match = candles.loc[candles["bar_index"] == bar_index, "time"]
        if match.empty:
            return None
        return self._time_string(match.iloc[0])

    @staticmethod
    def _event_time_fields(time_value: Any, fallback_bar_index: int) -> Dict[str, Any]:
        timestamp = fallback_bar_index
        if time_value is not None and not (
            not isinstance(time_value, pd.Timestamp) and pd.isna(time_value)
        ):
            if isinstance(time_value, pd.Timestamp):
                timestamp = int(time_value.timestamp())
            elif isinstance(time_value, str):
                timestamp = int(pd.Timestamp(time_value).timestamp())
            else:
                timestamp = int(time_value)
        return {
            "time": datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
            "timestamp": timestamp,
        }

    def _anchor_payload(self, pivot, candles: pd.DataFrame) -> Dict[str, Any]:
        return {
            "bar_index": int(pivot.bar_index),
            "rsi": float(pivot.rsi_value),
            "kind": pivot.kind,
            "time": self._bar_time(candles, int(pivot.bar_index)),
        }

    def _detail_record(self, row, signal, segment, stop_price, candles) -> Dict[str, Any]:
        event_time = self._event_time_fields(
            row["time"] if "time" in row.index else None, int(signal.bar_index)
        )
        return {
            "time": event_time["time"],
            "timestamp": event_time["timestamp"],
            "type": f"RSI_TRENDLINE_BREAK_{signal.side}",
            "bar_index": int(signal.bar_index),
            "direction": signal.side,
            "entry_side": signal.side,
            "entry_price": float(row["close"]),
            "price": float(row["close"]),
            "stop_price": float(stop_price),
            "stop_rule": "swing_extreme",
            "swing_lookback": int(self.parameters["swing_lookback"]),
            "is_retro": False,
            "trend_filter_passed": True,
            "sma_period": int(self.parameters["sma_period"]),
            "sma_value": float(row["sma"]),
            "rsi_period": int(self.parameters["rsi_period"]),
            "rsi_value": float(signal.rsi_value),
            "segment_id": int(segment.segment_id),
            "line_direction": segment.line.direction,
            "line_start_bar_index": int(segment.line.start_bar_index),
            "line_end_bar_index": int(segment.line.end_bar_index),
            "line_start_rsi": float(segment.line.start_rsi),
            "line_end_rsi": float(segment.line.end_rsi),
            "line_slope": float(segment.line.slope),
            "line_value_at_break": float(signal.line_value_at_break),
            "touch_count": int(segment.touch_count),
            "pivot_a_bar_index": int(segment.anchor_a.bar_index),
            "pivot_a_rsi": float(segment.anchor_a.rsi_value),
            "pivot_a_kind": segment.anchor_a.kind,
            "pivot_a_time": self._bar_time(candles, int(segment.anchor_a.bar_index)),
            "pivot_b_bar_index": int(segment.anchor_b.bar_index),
            "pivot_b_rsi": float(segment.anchor_b.rsi_value),
            "pivot_b_kind": segment.anchor_b.kind,
            "pivot_b_time": self._bar_time(candles, int(segment.anchor_b.bar_index)),
        }

    def _rsi_series_payload(self, candles: pd.DataFrame) -> List[Dict[str, Any]]:
        if "time" not in candles.columns:
            return []
        payload = []
        for _, row in candles.iterrows():
            value = row.get("rsi")
            if pd.isna(value):
                continue
            payload.append(
                {
                    "bar_index": int(row["bar_index"]),
                    "time": self._time_string(row["time"]),
                    "rsi": float(value),
                }
            )
        return payload

    def _timeline_payload(self, segments, candles: pd.DataFrame) -> List[Dict[str, Any]]:
        payload = []
        for segment in segments:
            payload.append(
                {
                    "segment_id": int(segment.segment_id),
                    "direction": segment.line.direction,
                    "valid_from_bar": int(segment.valid_from_bar),
                    "valid_to_bar": int(segment.valid_to_bar),
                    "valid_from_time": self._bar_time(candles, int(segment.valid_from_bar)),
                    "valid_to_time": self._bar_time(candles, int(segment.valid_to_bar)),
                    "end_reason": segment.end_reason,
                    "slope": float(segment.line.slope),
                    "touch_count": int(segment.touch_count),
                    "anchor_a": self._anchor_payload(segment.anchor_a, candles),
                    "anchor_b": self._anchor_payload(segment.anchor_b, candles),
                }
            )
        return payload

    @staticmethod
    def _summarize(
        detailed_log, exit_optimization, rsi_series, line_timeline, skipped
    ) -> Dict[str, Any]:
        n = len(detailed_log)
        wins = sum(1 for entry in detailed_log if entry.get("outcome") == "WIN")
        total = round(sum(float(e.get("net_pnl", 0.0)) for e in detailed_log), 6)
        average = round(total / n, 6) if n else 0.0

        return {
            "sample_size": n,
            "win_rate": round(wins / n, 4) if n else 0.0,
            "live_sample_size": n,
            "live_win_rate": round(wins / n, 4) if n else 0.0,
            "retro_sample_size": 0,
            "retro_win_rate": 0.0,
            "avg_mfe_10": 0.0,
            "avg_mae_10": 0.0,
            "avg_net_pnl": average,
            "net_pnl_total": total,
            "composite": average * (n ** 0.5) if n else 0.0,
            "groups": {},
            "detailed_log": detailed_log,
            "exit_optimization": exit_optimization,
            "trade_scored": True,
            "rsi_series": rsi_series,
            "line_timeline": line_timeline,
            "skipped": skipped,
        }

    def _empty_result(self, rsi_series=None, line_timeline=None, skipped=None) -> Dict[str, Any]:
        return self._summarize(
            detailed_log=[],
            exit_optimization={"best": None, "all_r_results": [], "per_signal": {}},
            rsi_series=rsi_series or [],
            line_timeline=line_timeline or [],
            skipped=skipped
            or {
                "trend_filter": 0, "warmup": 0, "invalid_risk": 0,
                "last_bar": 0, "missing_candle": 0,
            },
        )
```

- [ ] **Step 4: Run and confirm it passes**

Run: `python -m pytest gann-visualizer/backend/tests/test_rsi_trendline_hypothesis.py -v`

Expected: PASS, `7 passed`

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/analysis/rsi_trendline_hypothesis.py gann-visualizer/backend/tests/test_rsi_trendline_hypothesis.py
git commit -m "feat: causal sweep, swing stop and line timeline in RSI hypothesis"
```

---

## Task 7: Pass line_timeline Through the API

Spec §7.2 — without this the new payload is silently dropped before reaching the frontend.

**Files:**
- Modify: `gann-visualizer/backend/main.py:2331`
- Create: `gann-visualizer/backend/tests/test_rsi_payload_passthrough.py`

- [ ] **Step 1: Write the failing test**

Create `gann-visualizer/backend/tests/test_rsi_payload_passthrough.py`:

```python
import os
import sys

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from main import _transform_per_hypothesis_payload


def test_transform_preserves_rsi_series_and_line_timeline():
    payload = {
        "hypothesis_name": "RSI Trendline Break Strategy",
        "in_sample": {"sample_size": 2},
        "rsi_series": [{"bar_index": 10, "time": "2026-07-10T10:00:00", "rsi": 51.2}],
        "line_timeline": [
            {
                "segment_id": 3,
                "direction": "down",
                "valid_from_bar": 100,
                "valid_to_bar": 140,
                "end_reason": "broken",
                "anchor_a": {"bar_index": 80, "rsi": 68.0, "kind": "high"},
                "anchor_b": {"bar_index": 96, "rsi": 61.0, "kind": "high"},
            }
        ],
    }

    transformed = _transform_per_hypothesis_payload(payload)

    assert transformed["rsi_series"][0]["rsi"] == 51.2
    assert transformed["line_timeline"][0]["segment_id"] == 3
    assert transformed["line_timeline"][0]["end_reason"] == "broken"
```

- [ ] **Step 2: Run and confirm it fails**

Run: `python -m pytest gann-visualizer/backend/tests/test_rsi_payload_passthrough.py -v`

Expected: FAIL — `KeyError: 'line_timeline'`, because the passthrough tuple lists `all_rsi_lines`.

- [ ] **Step 3: Update the passthrough tuple**

In `gann-visualizer/backend/main.py`, in `_transform_per_hypothesis_payload`, change:

```python
    for key in ("hypothesis_name", "description", "in_sample", "walk_forward", "groups",
                "rsi_series", "all_rsi_lines"):
        if key in payload:
            transformed[key] = payload[key]
```

to:

```python
    for key in ("hypothesis_name", "description", "in_sample", "walk_forward", "groups",
                "rsi_series", "line_timeline", "skipped"):
        if key in payload:
            transformed[key] = payload[key]
```

Only the key tuple changes; the loop body is unchanged and shown for context.

- [ ] **Step 4: Run and confirm it passes**

Run: `python -m pytest gann-visualizer/backend/tests/test_rsi_payload_passthrough.py -v`

Expected: PASS, `1 passed`

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/main.py gann-visualizer/backend/tests/test_rsi_payload_passthrough.py
git commit -m "feat: pass line_timeline through the hypothesis API"
```

---

## Task 8: Frontend — Render Only the Lines Live at the Selected Bar

**Files:**
- Modify: `gann-visualizer/frontend/src/hypothesisRsiVerification.js`
- Modify: `gann-visualizer/frontend/src/hypothesisRsiVerification.test.mjs`
- Modify: `gann-visualizer/frontend/src/TVChartContainer.jsx`
- Modify: `gann-visualizer/frontend/src/App.jsx`

- [ ] **Step 1: Write the failing test**

Append to `gann-visualizer/frontend/src/hypothesisRsiVerification.test.mjs`, immediately **before** the final `console.log(...)` line:

```javascript
import { selectLiveSegments } from './hypothesisRsiVerification.js';

// Mirrors the backend's half-open handoff: a re_anchored segment ends at
// (successor.valid_from_bar - 1), so no bar ever has two live down-lines.
const TIMELINE = [
  { segment_id: 1, direction: 'down', valid_from_bar: 10, valid_to_bar: 39, end_reason: 're_anchored' },
  { segment_id: 2, direction: 'down', valid_from_bar: 40, valid_to_bar: 90, end_reason: 'broken' },
  { segment_id: 3, direction: 'up',   valid_from_bar: 20, valid_to_bar: 95, end_reason: 'broken' },
  { segment_id: 4, direction: 'down', valid_from_bar: 95, valid_to_bar: 130, end_reason: 'end_of_data' },
];

{
  const live = selectLiveSegments(TIMELINE, 50);
  assert.deepEqual(live.map((s) => s.segment_id).sort(), [2, 3]);
}

{
  // at most one line per direction, always
  for (const bar of [0, 10, 25, 40, 60, 90, 95, 120, 200]) {
    const live = selectLiveSegments(TIMELINE, bar);
    for (const direction of ['up', 'down']) {
      const count = live.filter((s) => s.direction === direction).length;
      assert.ok(count <= 1, `bar ${bar} had ${count} ${direction} lines`);
    }
  }
}

{
  assert.deepEqual(selectLiveSegments(null, 50), []);
  assert.deepEqual(selectLiveSegments(TIMELINE, null), []);
}

console.log('hypothesisRsiVerification.test.mjs: selectLiveSegments ok');
```

- [ ] **Step 2: Run and confirm it fails**

Run: `node gann-visualizer/frontend/src/hypothesisRsiVerification.test.mjs`

Expected: FAIL — `SyntaxError: The requested module './hypothesisRsiVerification.js' does not provide an export named 'selectLiveSegments'`

- [ ] **Step 3: Add the selector**

Append to `gann-visualizer/frontend/src/hypothesisRsiVerification.js`:

```javascript
/**
 * Segments whose validity window contains `barIndex`.
 *
 * The backend guarantees at most one active line per direction at any bar, so
 * this returns at most two segments. Filtering by a recorded validity window is
 * what stops the display and the trade signal from diverging - the frontend no
 * longer infers which line was live.
 */
export function selectLiveSegments(timeline, barIndex) {
  if (!Array.isArray(timeline) || !Number.isFinite(Number(barIndex))) return [];
  const bar = Number(barIndex);
  return timeline.filter((segment) => {
    const from = Number(segment?.valid_from_bar);
    const to = Number(segment?.valid_to_bar);
    if (!Number.isFinite(from) || !Number.isFinite(to)) return false;
    return from <= bar && bar <= to;
  });
}
```

- [ ] **Step 4: Run and confirm it passes**

Run: `node gann-visualizer/frontend/src/hypothesisRsiVerification.test.mjs`

Expected: PASS, printing both `ok` lines.

- [ ] **Step 5: Replace the line-drawing block in TVChartContainer.jsx**

In `gann-visualizer/frontend/src/TVChartContainer.jsx`, add to the imports at the top of the file:

```javascript
import { selectLiveSegments } from './hypothesisRsiVerification.js';
```

Then replace the entire block from `// --- Draw RSI trendlines (multiple, color-coded by direction) ---` (currently line 752) down to and including the closing `}` of `if (allLines && Array.isArray(allLines) && allLines.length > 0) { ... }` (currently line 874, immediately before `} else if (overlayModel && overlayModel.trendlinePoints.length >= 2) {`) with:

```javascript
                        // --- Draw the RSI trendlines that were LIVE at this bar ---
                        // At most one down-line and one up-line. No display cap,
                        // no score boost, no event-line matching heuristic - all
                        // three existed to manage a line cloud that no longer exists.
                        const timeline = props.lineTimeline;
                        const eventBar = Number(event.bar_index ?? event.break_bar_index);
                        const liveSegments = selectLiveSegments(timeline, eventBar);

                        if (liveSegments.length > 0) {
                            const barTimeMap = new Map();
                            for (const pt of curveSource) {
                                if (Number.isFinite(pt.barIndex) && Number.isFinite(pt.time)) {
                                    barTimeMap.set(pt.barIndex, pt.time);
                                }
                            }

                            const brokenSegmentId = Number(event.segment_id);

                            for (const segment of liveSegments) {
                                const pa = segment.pivot_a || segment.anchor_a;
                                const pb = segment.pivot_b || segment.anchor_b;
                                if (!pa || !pb) continue;

                                const ta = toTimeSec(pa.time) ?? barTimeMap.get(Number(pa.bar_index));
                                const tb = toTimeSec(pb.time) ?? barTimeMap.get(Number(pb.bar_index));
                                const ra = Number(pa.rsi);
                                const rb = Number(pb.rsi);
                                if (!Number.isFinite(ta) || !Number.isFinite(tb)
                                    || !Number.isFinite(ra) || !Number.isFinite(rb)) continue;

                                const isBroken = Number(segment.segment_id) === brokenSegmentId;
                                const baseColor = segment.direction === 'up' ? '#42A5F5' : '#FFB300';

                                const segId = ovChart.createMultipointShape(
                                    [{ time: ta, price: rsiToPrice(ra) },
                                     { time: tb, price: rsiToPrice(rb) }],
                                    {
                                        shape: 'trend_line',
                                        lock: true,
                                        disableUndo: true,
                                        overrides: {
                                            linecolor: isBroken ? '#FFD700' : baseColor,
                                            linewidth: isBroken ? 3 : 2,
                                            linestyle: 0,
                                        },
                                        zOrder: 'top',
                                    }
                                );
                                if (segId) { shapes.push(segId); hypothesisMarkerRef.current.push(segId); }

                                // Extend the broken line from its last anchor to the break bar
                                if (isBroken) {
                                    const breakTime = barTimeMap.get(eventBar);
                                    const lineAtBreak = Number(event.line_value_at_break);
                                    if (Number.isFinite(breakTime) && Number.isFinite(lineAtBreak)) {
                                        const extId = ovChart.createMultipointShape(
                                            [{ time: tb, price: rsiToPrice(rb) },
                                             { time: breakTime, price: rsiToPrice(lineAtBreak) }],
                                            {
                                                shape: 'trend_line',
                                                lock: true,
                                                disableUndo: true,
                                                overrides: { linecolor: '#FFD700', linewidth: 2, linestyle: 2 },
                                                zOrder: 'top',
                                            }
                                        );
                                        if (extId) { shapes.push(extId); hypothesisMarkerRef.current.push(extId); }
                                    }
                                }
                            }
                        }
```

- [ ] **Step 6: Wire the prop in App.jsx**

In `gann-visualizer/frontend/src/App.jsx`:

Replace line 108:
```javascript
    const [allRsiLinesData, setAllRsiLinesData] = useState(null);
```
with:
```javascript
    const [lineTimelineData, setLineTimelineData] = useState(null);
```

Replace line 689:
```javascript
                        allRsiLines={allRsiLinesData}
```
with:
```javascript
                        lineTimeline={lineTimelineData}
```

Replace line 1062:
```javascript
                                                    setAllRsiLinesData(data.all_rsi_lines || null);
```
with:
```javascript
                                                    setLineTimelineData(data.line_timeline || null);
```

- [ ] **Step 7: Confirm no stale references remain**

Run:

```bash
grep -rn "allRsiLines\|all_rsi_lines\|MAX_VISIBLE_LINES\|isEventLine" \
  --include=*.js --include=*.jsx gann-visualizer/frontend/src
```

Expected: no output.

- [ ] **Step 8: Run the frontend tests and build**

Run:

```bash
node gann-visualizer/frontend/src/hypothesisRsiVerification.test.mjs
node gann-visualizer/frontend/src/hypothesisEventFormatting.test.mjs
cd gann-visualizer/frontend && npm run build
```

Expected: both scripts print `ok`; the build completes without errors.

- [ ] **Step 9: Commit**

```bash
git add gann-visualizer/frontend/src/hypothesisRsiVerification.js \
        gann-visualizer/frontend/src/hypothesisRsiVerification.test.mjs \
        gann-visualizer/frontend/src/TVChartContainer.jsx \
        gann-visualizer/frontend/src/App.jsx
git commit -m "feat: render only the RSI lines live at the selected bar"
```

---

## Task 9: A/B Comparison Harness

Spec §9.3 — proves the geometry change earned its keep on identical runs.

**Files:**
- Create: `gann-visualizer/backend/scripts/compare_rsi_policies.py`

- [ ] **Step 1: Write the script**

Create `gann-visualizer/backend/scripts/compare_rsi_policies.py`:

```python
"""A/B the walk-back anchor policy against the nearest-pair rival.

Identical candles, identical trade rules -- only the anchor policy differs.
Reports geometry quality alongside trade outcome, because a policy that trades
better while drawing nonsense is not the goal.

Usage:
    python gann-visualizer/backend/scripts/compare_rsi_policies.py <candles.csv>
"""

from __future__ import annotations

import os
import statistics
import sys

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

import pandas as pd

from analysis.rsi_line_policy import NearestPairAnchorPolicy, WalkBackAnchorPolicy
from analysis.rsi_pivots import compute_rsi_series
from analysis.rsi_pivots import GeometryParams
from analysis.rsi_sweep import run_causal_sweep
from analysis.rsi_trendline_hypothesis import RSITrendlineBreakHypothesis

PARAMS = GeometryParams(
    left_bars=3, right_bars=3, min_swing=8.0,
    tolerance=1.5, min_length=8, max_span_bars=150,
)


def geometry_report(rsi: pd.Series, policy) -> dict:
    result = run_causal_sweep(rsi, policy, PARAMS)
    poked = 0
    for segment in result.segments:
        same_kind = [p for p in result.pivots if p.kind == segment.anchor_b.kind]
        for pivot in same_kind:
            if not (segment.line.start_bar_index < pivot.bar_index < segment.line.end_bar_index):
                continue
            value = segment.line.value_at(pivot.bar_index)
            if segment.line.direction == "down" and pivot.rsi_value > value + PARAMS.tolerance:
                poked += 1
                break
            if segment.line.direction == "up" and pivot.rsi_value < value - PARAMS.tolerance:
                poked += 1
                break
    spans = [s.line.end_bar_index - s.line.start_bar_index for s in result.segments] or [0]
    return {
        "pivots": len(result.pivots),
        "segments": len(result.segments),
        "poked": poked,
        "poked_pct": round(100.0 * poked / len(result.segments), 1) if result.segments else 0.0,
        "median_span": statistics.median(spans),
        "max_span": max(spans),
        "raw_breaks": len(result.signals),
    }


def trade_report(candles: pd.DataFrame, policy_name: str) -> dict:
    hypothesis = RSITrendlineBreakHypothesis()
    hypothesis.set_parameters(**{**hypothesis.parameters, "anchor_policy": policy_name})
    result = hypothesis.evaluate(pd.DataFrame(), candles_df=candles)
    best = (result.get("exit_optimization") or {}).get("best") or {}
    return {
        "n": result["sample_size"],
        "win_rate": result["win_rate"],
        "best_r": best.get("r_value"),
        "net_pnl": result["net_pnl_total"],
        "skipped": result["skipped"],
    }


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)

    path = sys.argv[1]
    candles = pd.read_csv(path).reset_index(drop=True)
    candles["bar_index"] = candles.index
    rsi = compute_rsi_series(candles["close"], period=14)

    print(f"candles: {path}  ({len(candles)} bars)\n")
    header = f"{'policy':<14}{'pivots':>7}{'segs':>6}{'poked':>7}{'poked%':>8}{'medSpan':>9}{'maxSpan':>9}"
    print("GEOMETRY"); print(header)
    for name, policy in (("walk_back", WalkBackAnchorPolicy()), ("nearest_pair", NearestPairAnchorPolicy())):
        g = geometry_report(rsi, policy)
        print(f"{name:<14}{g['pivots']:>7}{g['segments']:>6}{g['poked']:>7}"
              f"{g['poked_pct']:>8}{g['median_span']:>9}{g['max_span']:>9}")

    print("\nTRADES")
    print(f"{'policy':<14}{'n':>5}{'win':>8}{'bestR':>7}{'netPnL':>12}")
    for name in ("walk_back", "nearest_pair"):
        t = trade_report(candles, name)
        print(f"{name:<14}{t['n']:>5}{t['win_rate']:>8.3f}"
              f"{str(t['best_r']):>7}{t['net_pnl']:>12.1f}")
        print(f"{'':<14}skipped: {t['skipped']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the comparison**

Run:

```bash
python gann-visualizer/backend/scripts/compare_rsi_policies.py \
  logs/backend/runs/BTCUSDT/15/2026-07-10_barctx_v2/candles.csv
```

Expected: a GEOMETRY table where `walk_back` shows `poked = 0` and `nearest_pair` shows a materially higher count, followed by a TRADES table for both.

**Record the actual output in the commit message.** Spec §6.3 predicts roughly n≈44 and a positive net PnL for `walk_back`; if the numbers differ substantially, that is a finding to report, not a test to adjust.

- [ ] **Step 3: Commit**

```bash
git add gann-visualizer/backend/scripts/compare_rsi_policies.py
git commit -m "feat: add walk-back vs nearest-pair A/B harness"
```

---

## Task 10: Full Verification Pass

**Files:**
- Modify: none, unless a failure reveals a fix

- [ ] **Step 1: Run every test touched by this work**

Run:

```bash
python -m pytest \
  gann-visualizer/backend/tests/test_rsi_pivots.py \
  gann-visualizer/backend/tests/test_rsi_line_policy.py \
  gann-visualizer/backend/tests/test_rsi_sweep.py \
  gann-visualizer/backend/tests/test_rsi_causality.py \
  gann-visualizer/backend/tests/test_rsi_geometry.py \
  gann-visualizer/backend/tests/test_rsi_trendline_hypothesis.py \
  gann-visualizer/backend/tests/test_rsi_payload_passthrough.py \
  gann-visualizer/backend/tests/test_signal_trade_simulator.py -v
```

Expected: all PASS. `test_signal_trade_simulator.py` is included because the hypothesis still depends on it and it must not have regressed.

- [ ] **Step 2: Check for collateral damage in the wider backend suite**

Run:

```bash
python -m pytest gann-visualizer/backend/tests -q 2>&1 | tail -25
```

Compare against the pre-existing failures recorded before this work began. Any *new* failure must be fixed; pre-existing unrelated failures are out of scope — list them explicitly in the final report rather than silently accepting them.

- [ ] **Step 3: Run the frontend tests and build**

Run:

```bash
node gann-visualizer/frontend/src/hypothesisRsiVerification.test.mjs
node gann-visualizer/frontend/src/hypothesisEventFormatting.test.mjs
node gann-visualizer/frontend/src/hypothesisChartNavigation.test.mjs
cd gann-visualizer/frontend && npm run build
```

Expected: all print `ok`; the build succeeds.

- [ ] **Step 4: Regenerate a real report and inspect the payload**

Run:

```bash
python gann-visualizer/backend/generate_hypothesis_reports.py 2026-07-10 --15m -H "RSI Trendline Break Strategy"
```

Then:

```bash
python - <<'PY'
import json, sys, io
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

paths = sorted(Path("logs/backend/runs/BTCUSDT/15").glob("*/analysis/hypotheses/rsi_trendline_break.json"))
assert paths, "no RSI report generated"
payload = json.loads(paths[-1].read_text(encoding="utf-8"))

print("keys:", sorted(payload.keys()))
print("timeline segments:", len(payload.get("line_timeline", [])))
print("skipped:", payload.get("skipped"))

timeline = payload.get("line_timeline", [])
log = payload.get("detailed_log", [])
ids = {s["segment_id"] for s in timeline}
assert all(e["segment_id"] in ids for e in log), "a signal references a missing segment"

# the core invariant: never two live lines in one direction at one bar
for bar in range(0, 1000, 25):
    live = [s for s in timeline if s["valid_from_bar"] <= bar <= s["valid_to_bar"]]
    for d in ("up", "down"):
        assert len([s for s in live if s["direction"] == d]) <= 1, f"bar {bar}: >1 {d} line"
print("invariant holds: <=1 live line per direction at every sampled bar")

if log:
    e = log[0]
    print("sample signal:", {k: e[k] for k in
          ("bar_index","direction","segment_id","stop_rule","stop_price","best_r","outcome")})
PY
```

Expected: `line_timeline` non-empty, every signal resolves to a segment, the invariant assertion passes, and `stop_rule` reads `swing_extreme`.

- [ ] **Step 5: Manual Hypothesis Navigator smoke test**

Start the backend and frontend as usual, load the regenerated RSI report, and click through several signals. Confirm:

- at most one gold (broken) line and one coloured (other-direction) line per event — never a cloud
- both lines' endpoints sit visibly **on** RSI pivots, not through the curve
- no line stretches across the whole chart
- the gold line extends dashed to the break bar
- entry, stop, exit and exit reason render on the price pane

- [ ] **Step 6: Report results honestly**

Write a short summary covering: the A/B table from Task 9, the win rate and net PnL from Step 4, any new test failures, and any pre-existing failures left in place.

Per spec §9.4, **do not describe the strategy as profitable on the strength of this run.** The §6.3 numbers are single-window in-sample exploration at n≈44. Walk-forward validation across more than one symbol and timeframe is required before any such claim.

- [ ] **Step 7: Commit only if a code change was required**

```bash
git add -A
git commit -m "fix: address RSI geometry verification findings"
```

Skip if verification required no changes.

---

## Plan Self-Review

### Spec coverage

| Spec section | Task |
|---|---|
| §4.1 module split | 1, 2, 3, 5 |
| §4.2 sweep/policy split | 2, 3 |
| §4.4 deletions | 5 |
| §5.1 fractal candidates | 1 |
| §5.2 incremental dominance | 1 (impl), 4 (repaint guard) |
| §5.3 walk-back + span cap | 2 |
| §5.4 lifecycle | 3 |
| §5.5 break detection | 3 |
| §6.1 swing stop | 6 |
| §6.2 max hold = 40 | 6 |
| §7.1 line timeline | 6 |
| §7.2 detailed log + passthrough | 6, 7 |
| §7.3 frontend | 8 |
| §8 error handling / skip accounting | 6 |
| §9.1 geometry invariants | 3 |
| §9.2 causality test | 4 |
| §9.3 A/B comparison | 9 |
| §9.4 walk-forward gate | 10 Step 6 |
| §9.5 navigator smoke test | 10 Step 5 |

### Placeholder scan

No `TBD`, `TODO`, or "similar to above". Every code step carries complete code; every verification step carries an exact command and expected output. Task 10 Step 2 intentionally does not enumerate pre-existing failures — they are captured at execution time, and the step says how to distinguish them from regressions.

### Type consistency

- `RSIPivot` — Task 1, used unchanged in 2, 3, 6.
- `RSILine` with `.slope` property and total `.value_at()` — Task 2, used in 3, 6, 9.
- `GeometryParams` field names (`left_bars`, `right_bars`, `min_swing`, `tolerance`, `min_length`, `max_span_bars`) — identical in Tasks 2, 3, 4, 6, 9.
- `LineSegment.anchor_a` / `.anchor_b` — Task 3, serialised under the same names in Task 6, read by Task 8 with a `pivot_a || anchor_a` fallback.
- `apply_dominance` returns `(list, changed_kind | None)` in Tasks 1 and 3 alike.
- `policy.anchor(same_kind, newest, params)` — the full same-kind list is passed (not sliced), since poke-through checking needs the intermediates; both policies skip candidates at or after `newest` themselves.
- `count_touches(line, same_kind, tolerance)` — Task 2, called in Task 3.

### Ordering

No circular dependency. `GeometryParams` lives in `rsi_pivots` (Task 1), so
`rsi_line_policy` (Task 2) depends only on Task 1 and its tests run standalone.
The chain is strictly `rsi_pivots <- rsi_line_policy <- rsi_sweep <- hypothesis`.
An earlier draft of this plan put `GeometryParams` in `rsi_sweep`, which made
Task 2 untestable until Task 3 landed; that was corrected rather than documented
as a caveat.
