# Pullback-Tolerant Reach Test — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Test whether price reaches the next level after a breach *even when it dips back and retests the breached level first* — and find which stop depth and time window the effect actually lives at.

**Architecture:** The existing strict race already does target-vs-stop with the stop pinned at the breached level. Generalising the stop to an arbitrary price turns the strict test into the depth-0 case of a family, so one race function covers every variant. Stop prices are read off the real ladder (respecting its uneven spacing) rather than from a global constant. Every (depth, window) pair becomes its own outcome column, computed in one pass that shares the expensive per-row ladder lookup.

**Tech Stack:** Python 3.13, pandas, numpy, pytest. Existing modules `study_tool/mining/ladder_rebuild.py`, `statistics.py`, `scripts/mine_gann_corpus.py`.

**Origin:** user hypothesis, 2026-09-03. The strict test scores "breach → dip back → retest → then reach next level" as a failure. The user observes this path happens often and ends successfully, so the strict test undercounts.

---

## Facts established before planning (do not re-derive)

- `LadderCache._ladder` groups level prices by `source` **only**, mixing majors and
  sub-levels into one sorted array (`ladder_rebuild.py:60-64`). So "the next level"
  is the adjacent 1/8th sub-level, not the next major. Median adjacent gap on this
  corpus is **2.25** (`meta.json: median_sub_gap`).
- Spacing is **uneven** for off-centre crosses. Stop prices must therefore come from
  the ladder itself, never from `median_sub_gap` arithmetic.
- `race_to_next_level` (`ladder_rebuild.py:113-139`) stops on `closes[i] < level_price`
  (up) — strictly below, so a close exactly at the stop survives. Target uses
  `highs[i] >= target`. Target wins ties within a bar. Keep both conventions.
- `resolution_window_bars` is 50, inherited from breach resolution, not chosen for
  this race. 50 bars × 5 min ≈ 4h10m of trading.
- `add_reach_outcomes` currently does `frame.iloc[position]` per confirmed row —
  already flagged as the hot path. With N outcome columns the per-row ladder lookup
  must be done **once**, then N cheap race loops run off it.
- Confirmed breaches: ~560k on explore, ~187k on holdout (real + 50 shadows).
- Existing `reach_outcome` column and the statistics reading it must keep working
  unchanged — the confirmed 8/13 holdout result depends on that exact definition.
- **Repo quirk:** `.gitignore` blanket-excludes `**/tests/`. New test files need `git add -f`.

---

## Agreed rule (from the user, 2026-09-03)

For an up-breach of level L, with stop depth `d` steps:

| Event | Test | Result |
|---|---|---|
| Win | a bar's **high** reaches the level one step above L | REACHED |
| Loss | a bar **closes strictly below** the price `d` steps below L | STOPPED |
| Alive | dips under L, touches the stop level, or wicks below and closes back | race continues |
| No result | neither inside the window | TIMEOUT (excluded from the rate, reported separately) |

Mirrored for a down-breach. `d = 0` reproduces the strict test exactly.

---

## File structure

| File | Responsibility |
|---|---|
| `study_tool/mining/ladder_rebuild.py` | *Modified* — `level_steps_away`, generalised `race`, multi-column `add_reach_outcomes`. |
| `study_tool/mining/statistics.py` | *Modified* — statistic factories bound to an outcome column. |
| `scripts/mine_gann_corpus.py` | *Modified* — `--stop-depths` / `--windows` CLI, wires one statistic pair per column. |

---

### Task 1: Find a price N steps along the ladder

**Files:**
- Modify: `study_tool/mining/ladder_rebuild.py`
- Test: `tests/study_tool/mining/test_ladder_rebuild.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/study_tool/mining/test_ladder_rebuild.py`:

```python
def test_zero_steps_returns_the_level_itself():
    cache = LadderCache(keys_frame(), price_scale=1)
    prices = list(cache.prices(bar_index=0, source="center"))
    level = prices[len(prices) // 2]

    assert cache.level_steps_away(0, "center", level, "up", 0.0, 0.0) == \
        pytest.approx(level)


def test_one_step_along_direction_matches_next_level():
    """The existing next_level is the +1 case of this, and must agree."""
    cache = LadderCache(keys_frame(), price_scale=1)
    prices = list(cache.prices(bar_index=0, source="center"))
    level = prices[len(prices) // 2]

    for direction in ("up", "down"):
        assert cache.level_steps_away(0, "center", level, direction, 0.0, 1.0) == \
            pytest.approx(cache.next_level(0, "center", level, direction, 0.0))


def test_negative_steps_go_against_the_breach_direction():
    """The stop sits behind the breached level, so it is a negative step."""
    cache = LadderCache(keys_frame(), price_scale=1)
    prices = sorted(cache.prices(bar_index=0, source="center"))
    index = len(prices) // 2
    level = prices[index]

    assert cache.level_steps_away(0, "center", level, "up", 0.0, -1.0) == \
        pytest.approx(prices[index - 1])
    assert cache.level_steps_away(0, "center", level, "down", 0.0, -1.0) == \
        pytest.approx(prices[index + 1])


def test_two_steps_back_skips_a_level():
    cache = LadderCache(keys_frame(), price_scale=1)
    prices = sorted(cache.prices(bar_index=0, source="center"))
    index = len(prices) // 2

    assert cache.level_steps_away(0, "center", prices[index], "up", 0.0, -2.0) == \
        pytest.approx(prices[index - 2])


def test_a_half_step_lands_between_two_levels():
    """
    Uneven spacing on off-centre crosses means a half step is half of the
    real local gap, not half of a global constant.
    """
    cache = LadderCache(keys_frame(), price_scale=1)
    prices = sorted(cache.prices(bar_index=0, source="center"))
    index = len(prices) // 2
    level, below = prices[index], prices[index - 1]

    half = cache.level_steps_away(0, "center", level, "up", 0.0, -0.5)

    assert half == pytest.approx(level - (level - below) / 2.0)
    assert below < half < level


def test_a_shadow_step_is_the_real_step_shifted_by_its_offset():
    cache = LadderCache(keys_frame(), price_scale=1)
    prices = sorted(cache.prices(bar_index=0, source="center"))
    level = prices[len(prices) // 2]

    real = cache.level_steps_away(0, "center", level, "up", 0.0, -1.0)
    shadow = cache.level_steps_away(0, "center", level + 0.4, "up", 0.4, -1.0)

    assert shadow == pytest.approx(real + 0.4)


def test_running_off_the_end_of_the_ladder_returns_none():
    cache = LadderCache(keys_frame(), price_scale=1)
    prices = sorted(cache.prices(bar_index=0, source="center"))

    assert cache.level_steps_away(0, "center", prices[0], "up", 0.0, -1.0) is None
    assert cache.level_steps_away(0, "center", prices[-1], "up", 0.0, 1.0) is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_ladder_rebuild.py -q`
Expected: FAIL — `AttributeError: 'LadderCache' object has no attribute 'level_steps_away'`

- [ ] **Step 3: Implement**

Add to `LadderCache` in `study_tool/mining/ladder_rebuild.py`, after `next_level`:

```python
    def _index_of(self, prices: List[float], unshifted: float) -> Optional[int]:
        """
        Position of `unshifted` in the sorted ladder, or None if it is not a
        ladder price. A tolerance below one paise absorbs the Parquet float
        round-trip, exactly as next_level does.
        """
        epsilon = 1e-6
        index = bisect.bisect_left(prices, unshifted - epsilon)
        if index < len(prices) and abs(prices[index] - unshifted) <= epsilon:
            return index
        return None

    def level_steps_away(self, bar_index: int, source: str, level_price: float,
                         direction: str, offset: float,
                         steps: float) -> Optional[float]:
        """
        The price `steps` ladder positions from `level_price` along `direction`.

        Positive steps go with the breach (the target side), negative steps go
        against it (the stop side). `steps=1` is exactly `next_level`.

        Fractional steps interpolate between the two bracketing levels, so a
        half step is half of the *real local gap*. That matters: spacing is
        uneven on off-centre crosses, so half of `median_sub_gap` would be the
        wrong distance nearly everywhere.

        Returns None when the walk runs off the end of the finite ladder.
        """
        prices = self.prices(bar_index, source)
        if not prices:
            return None

        unshifted = level_price - offset
        base = self._index_of(prices, unshifted)
        if base is None:
            return None

        # Ladder prices ascend, so walking "down" means walking left.
        signed = steps if direction == "up" else -steps
        lower = math.floor(signed)
        upper = math.ceil(signed)

        if not (0 <= base + lower < len(prices)):
            return None
        if not (0 <= base + upper < len(prices)):
            return None

        low_price = prices[base + int(lower)]
        if lower == upper:
            return low_price + offset

        high_price = prices[base + int(upper)]
        fraction = signed - lower
        return low_price + (high_price - low_price) * fraction + offset
```

Add `import math` to the imports at the top of the file.

- [ ] **Step 4: Run to verify they pass**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_ladder_rebuild.py -q`
Expected: `20 passed` (13 existing + 7 new)

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/study_tool/mining/ladder_rebuild.py
git add -f gann-visualizer/backend/tests/study_tool/mining/test_ladder_rebuild.py
git commit -m "feat: find a price N ladder steps from a level, in either direction

The stop for a pullback-tolerant race sits some number of levels behind the
breached one, so the race needs to address the ladder by step count rather
than only by 'the next one'.

Fractional steps interpolate against the real local gap, not against
median_sub_gap - spacing is uneven on off-centre crosses, so a global
constant would put a half step at the wrong price nearly everywhere."
```

---

### Task 2: Race against an arbitrary stop price

**Files:**
- Modify: `study_tool/mining/ladder_rebuild.py`
- Test: `tests/study_tool/mining/test_ladder_rebuild.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/study_tool/mining/test_ladder_rebuild.py`:

```python
def test_race_with_stop_reproduces_the_strict_race_when_stop_is_the_level():
    """Depth 0 must be the test we already ran, bit for bit."""
    highs = np.array([100.0, 101.0, 101.0])
    lows = np.array([99.0, 98.0, 97.0])
    closes = np.array([100.0, 99.0, 98.0])

    assert race_with_stop(highs, lows, closes, start=0, stop_price=99.5,
                          target=104.5, direction="up", window=50) == \
        race_to_next_level(highs, lows, closes, start=0, level_price=99.5,
                           target=104.5, direction="up", window=50)


def test_a_dip_below_the_level_survives_when_the_stop_sits_lower():
    """
    The whole point. Price closes back under the breached level at 99.5, then
    recovers and reaches the target. Strict scores STOPPED, this scores REACHED.
    """
    highs = np.array([100.0, 100.0, 105.0])
    lows = np.array([99.0, 98.6, 100.0])
    closes = np.array([100.0, 98.8, 104.0])

    strict = race_to_next_level(highs, lows, closes, start=0, level_price=99.5,
                                target=104.5, direction="up", window=50)
    lenient = race_with_stop(highs, lows, closes, start=0, stop_price=98.0,
                             target=104.5, direction="up", window=50)

    assert strict == "STOPPED"
    assert lenient == "REACHED"


def test_touching_the_stop_price_is_not_a_failure():
    """Agreed rule: only a close strictly below the stop kills the race."""
    highs = np.array([100.0, 100.0, 105.0])
    lows = np.array([99.0, 97.5, 100.0])
    closes = np.array([100.0, 98.0, 104.0])

    assert race_with_stop(highs, lows, closes, start=0, stop_price=98.0,
                          target=104.5, direction="up", window=50) == "REACHED"


def test_closing_below_the_stop_still_fails():
    highs = np.array([100.0, 100.0, 105.0])
    lows = np.array([99.0, 97.0, 100.0])
    closes = np.array([100.0, 97.9, 104.0])

    assert race_with_stop(highs, lows, closes, start=0, stop_price=98.0,
                          target=104.5, direction="up", window=50) == "STOPPED"


def test_race_with_stop_runs_downward_too():
    highs = np.array([100.0, 101.4, 100.0])
    lows = np.array([99.0, 100.0, 94.0])
    closes = np.array([100.0, 101.2, 95.0])

    assert race_with_stop(highs, lows, closes, start=0, stop_price=102.0,
                          target=94.5, direction="down", window=50) == "REACHED"


def test_a_shorter_window_can_turn_a_win_into_a_timeout():
    """Window length is a dial, so it must actually change the outcome."""
    highs = np.array([100.0] * 6 + [105.0])
    lows = np.array([99.0] * 7)
    closes = np.array([100.0] * 7)

    assert race_with_stop(highs, lows, closes, start=0, stop_price=98.0,
                          target=104.5, direction="up", window=3) == "TIMEOUT"
    assert race_with_stop(highs, lows, closes, start=0, stop_price=98.0,
                          target=104.5, direction="up", window=50) == "REACHED"
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_ladder_rebuild.py -q`
Expected: FAIL — `ImportError: cannot import name 'race_with_stop'`

(Add `race_with_stop` to the import block at the top of the test file alongside
`race_to_next_level`.)

- [ ] **Step 3: Implement**

In `study_tool/mining/ladder_rebuild.py`, replace `race_to_next_level` (lines
113-139) with:

```python
def race_with_stop(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
                   start: int, stop_price: float, target: float,
                   direction: str, window: int) -> str:
    """
    Does price reach `target` before closing through `stop_price`?

    Returns REACHED, STOPPED or TIMEOUT. A race truncated by the end of the
    data is a TIMEOUT, not a loss.

    The stop is a **strict** close beyond `stop_price`, so a bar that merely
    touches it - or wicks through and closes back - keeps the race alive. That
    is deliberate: the move being tested is 'breach, dip back, retest, then
    carry on', and a retest that holds must not read as a failure.

    Within a single bar the target wins. The target is tested against the
    bar's high or low, which occur during the bar; the stop is tested against
    the close, which is the bar's last price. So if both conditions hold, the
    target came first.
    """
    last = min(start + 1 + window, len(closes))
    for i in range(start + 1, last):
        if direction == "up":
            if highs[i] >= target:
                return REACHED
            if closes[i] < stop_price:
                return STOPPED
        else:
            if lows[i] <= target:
                return REACHED
            if closes[i] > stop_price:
                return STOPPED
    return TIMEOUT


def race_to_next_level(highs: np.ndarray, lows: np.ndarray,
                       closes: np.ndarray, start: int, level_price: float,
                       target: float, direction: str, window: int) -> str:
    """
    The strict race: the stop sits on the breached level itself.

    Kept as a named function because the confirmed holdout result was measured
    with exactly this definition. It is the zero-depth case of race_with_stop.
    """
    return race_with_stop(highs, lows, closes, start=start,
                          stop_price=level_price, target=target,
                          direction=direction, window=window)
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_ladder_rebuild.py -q`
Expected: `26 passed` (20 from Task 1 + 6 new). The 13 original race tests must
all still pass through the delegating wrapper — that is the regression guard on
the confirmed result.

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/study_tool/mining/ladder_rebuild.py
git add -f gann-visualizer/backend/tests/study_tool/mining/test_ladder_rebuild.py
git commit -m "feat: race against an arbitrary stop price, not only the breached level

Generalising the stop turns the strict race into the zero-depth case of a
family, so one function covers every variant and the confirmed result keeps
its exact definition through a delegating wrapper.

The stop stays a strict close beyond the price, so a retest that touches it
and holds survives - which is the move this whole change exists to score."
```

---

### Task 3: One outcome column per (stop depth, window)

**Files:**
- Modify: `study_tool/mining/ladder_rebuild.py`
- Test: `tests/study_tool/mining/test_ladder_rebuild.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/study_tool/mining/test_ladder_rebuild.py`:

```python
def reach_events():
    return pd.DataFrame({
        "event_type": ["LADDER_BREACH_CONFIRMED", "LADDER_TOUCH"],
        "bar_index": [0, 0],
        "shadow_id": [None, None],
        "level_source": ["center", "center"],
        "level_price": [1307.0, 1307.0],
        "direction": ["up", None],
    })


def reach_bars():
    return pd.DataFrame({
        "high": [1310.0, 1400.0], "low": [1300.0, 1305.0],
        "close": [1308.0, 1390.0],
    })


def test_outcome_column_named_per_depth_and_window():
    result = add_reach_outcomes(
        reach_events(), reach_bars(), LadderCache(keys_frame(), 1), meta(),
        stop_depths=(0.0, 0.5, 1.0), windows=(50,))

    for name in ("reach_d0_w50", "reach_d0p5_w50", "reach_d1_w50"):
        assert name in result.columns, f"missing {name}"


def test_the_legacy_column_still_exists_and_is_the_strict_case():
    """
    The confirmed holdout result was measured on `reach_outcome`. It must
    keep meaning exactly what it meant: depth 0, the corpus's own window.
    """
    result = add_reach_outcomes(
        reach_events(), reach_bars(), LadderCache(keys_frame(), 1), meta(),
        stop_depths=(0.0, 1.0), windows=(50,))

    assert "reach_outcome" in result.columns
    assert list(result["reach_outcome"]) == list(result["reach_d0_w50"])


def test_a_deeper_stop_never_turns_a_win_into_a_loss():
    """
    Loosening the stop can only keep a race alive longer. A breach that
    reached the target with a tight stop must still reach it with a wider one.
    """
    result = add_reach_outcomes(
        reach_events(), reach_bars(), LadderCache(keys_frame(), 1), meta(),
        stop_depths=(0.0, 2.0), windows=(50,))

    tight, wide = result.loc[0, "reach_d0_w50"], result.loc[0, "reach_d2_w50"]
    if tight == "REACHED":
        assert wide == "REACHED"


def test_non_breach_rows_stay_none_in_every_column():
    result = add_reach_outcomes(
        reach_events(), reach_bars(), LadderCache(keys_frame(), 1), meta(),
        stop_depths=(0.0, 1.0), windows=(50, 100))

    for name in ("reach_d0_w50", "reach_d1_w50", "reach_d0_w100",
                 "reach_d1_w100"):
        assert result.loc[1, name] is None


def test_target_already_hit_is_recorded():
    """
    A breach confirms after two closes beyond the level, which can already
    carry price past the target. Those wins cost no travel, so their share
    has to be visible rather than buried in the rate.
    """
    result = add_reach_outcomes(
        reach_events(), reach_bars(), LadderCache(keys_frame(), 1), meta(),
        stop_depths=(0.0,), windows=(50,))

    assert "target_already_hit" in result.columns
    assert result.loc[0, "target_already_hit"] in (True, False)
    assert result.loc[1, "target_already_hit"] is None


def test_the_ladder_is_queried_once_per_row_not_once_per_column(monkeypatch):
    """
    Eight columns must not mean eight ladder lookups per breach - that is the
    hot path over half a million rows.
    """
    cache = LadderCache(keys_frame(), 1)
    calls = {"n": 0}
    real = cache.level_steps_away

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(cache, "level_steps_away", counting)

    add_reach_outcomes(reach_events(), reach_bars(), cache, meta(),
                       stop_depths=(0.0, 0.5, 1.0, 2.0), windows=(50, 100))

    # one target + one stop per distinct depth, for the single breach row
    assert calls["n"] <= 5, f"{calls['n']} lookups for one breach"
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_ladder_rebuild.py -q`
Expected: FAIL — `TypeError: add_reach_outcomes() got an unexpected keyword argument 'stop_depths'`

- [ ] **Step 3: Implement**

Replace `add_reach_outcomes` in `study_tool/mining/ladder_rebuild.py` with:

```python
def depth_label(depth: float) -> str:
    """`0.5` -> `0p5`. Column names cannot carry a dot without pain."""
    text = f"{depth:g}"
    return text.replace(".", "p").replace("-", "m")


def outcome_column(depth: float, window: int) -> str:
    return f"reach_d{depth_label(depth)}_w{window}"


def add_reach_outcomes(events: pd.DataFrame, bars: pd.DataFrame,
                       cache: LadderCache, meta: CorpusMeta,
                       stop_depths: Sequence[float] = (0.0,),
                       windows: Optional[Sequence[int]] = None) -> pd.DataFrame:
    """
    Add one REACHED/STOPPED/TIMEOUT column per (stop depth, window) pair.

    `stop_depths` is in ladder steps behind the breached level. 0.0 is the
    strict test: the stop sits on the level itself. 1.0 puts it one level
    behind, so a dip back that retests the level and holds stays alive.

    Also adds:
      reach_outcome       - alias of the (0.0, corpus window) column, because
                            the confirmed holdout result was measured on that
                            name and must not change meaning.
      target_already_hit  - True when the breach's own confirmation bar had
                            already reached the target. Those wins cost no
                            travel; their share must be visible.

    None means the row was not raced: not a confirmed breach, no direction, or
    the ladder ran out before the target or the stop. None is not a loss.

    The ladder is queried once per row per distinct depth, then every window
    reuses those prices - the lookup is the expensive half over ~560k rows.
    """
    highs = bars["high"].to_numpy(dtype=float)
    lows = bars["low"].to_numpy(dtype=float)
    closes = bars["close"].to_numpy(dtype=float)

    if windows is None:
        windows = (meta.resolution_window_bars,)
    depths = tuple(stop_depths)
    windows = tuple(windows)

    frame = events.reset_index(drop=True)
    columns = {(d, w): [None] * len(frame) for d in depths for w in windows}
    already_hit: List[Optional[bool]] = [None] * len(frame)

    is_confirmed = (frame["event_type"] == CONFIRMED).to_numpy()
    bar_indices = frame["bar_index"].to_numpy()
    level_prices = frame["level_price"].to_numpy()
    directions = frame["direction"].to_numpy()
    sources = frame["level_source"].to_numpy()
    shadow_ids = frame["shadow_id"].to_numpy()

    for position in range(len(frame)):
        if not is_confirmed[position]:
            continue
        direction = directions[position]
        if direction not in ("up", "down"):
            continue

        bar = int(bar_indices[position])
        source = sources[position]
        level_price = float(level_prices[position])
        offset = meta.offset_for(shadow_ids[position])

        target = cache.level_steps_away(bar, source, level_price, direction,
                                        offset, 1.0)
        if target is None:
            continue

        already_hit[position] = bool(
            highs[bar] >= target if direction == "up" else lows[bar] <= target)

        for depth in depths:
            stop_price = cache.level_steps_away(
                bar, source, level_price, direction, offset, -float(depth))
            if stop_price is None:
                continue
            for window in windows:
                columns[(depth, window)][position] = race_with_stop(
                    highs, lows, closes, start=bar, stop_price=stop_price,
                    target=target, direction=direction, window=window)

    for (depth, window), values in columns.items():
        frame[outcome_column(depth, window)] = values
    frame["target_already_hit"] = already_hit

    legacy = outcome_column(0.0, meta.resolution_window_bars)
    if legacy in frame.columns:
        frame["reach_outcome"] = frame[legacy]

    return frame
```

Add `Sequence` to the `typing` import line.

- [ ] **Step 4: Run to verify they pass**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_ladder_rebuild.py -q`
Expected: `32 passed` (26 from Task 2 + 6 new).

- [ ] **Step 5: Run the whole mining suite for regressions**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/ -q`
Expected: all pass. `test_report.py`'s end-to-end tests call `add_reach_outcomes`
with the old signature — the defaults must keep them working unchanged.

- [ ] **Step 6: Commit**

```bash
git add gann-visualizer/backend/study_tool/mining/ladder_rebuild.py
git add -f gann-visualizer/backend/tests/study_tool/mining/test_ladder_rebuild.py
git commit -m "feat: score every stop depth and window in one pass

One outcome column per (depth, window) pair, so the sweep answers 'which
depth does the effect live at' instead of picking one and hoping.

reach_outcome stays an alias of the zero-depth, corpus-window column: the
confirmed holdout result was measured on that name and must not quietly
change meaning underneath it.

target_already_hit records breaches whose confirmation bar had already
reached the target - those wins cost no travel and their share belongs in
the open rather than inside the headline rate."
```

---

### Task 4: Statistics per column, and the sweep on the command line

**Files:**
- Modify: `study_tool/mining/statistics.py`
- Modify: `scripts/mine_gann_corpus.py`
- Test: `tests/study_tool/mining/test_statistics.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/study_tool/mining/test_statistics.py`:

```python
def test_reach_rate_for_reads_the_column_it_was_given():
    frame = pd.DataFrame({
        "reach_d0_w50": ["REACHED", "STOPPED", "STOPPED", "TIMEOUT"],
        "reach_d1_w50": ["REACHED", "REACHED", "STOPPED", "TIMEOUT"],
    })

    assert reach_rate_for("reach_d0_w50")(frame).value == pytest.approx(1 / 3)
    assert reach_rate_for("reach_d1_w50")(frame).value == pytest.approx(2 / 3)


def test_reach_rate_for_a_missing_column_is_none_not_zero():
    frame = pd.DataFrame({"reach_d0_w50": ["REACHED"]})

    stat = reach_rate_for("reach_d9_w50")(frame)

    assert stat.value is None
    assert stat.n == 0


def test_timeout_share_for_reads_its_own_column():
    frame = pd.DataFrame({
        "reach_d1_w50": ["REACHED", "STOPPED", "TIMEOUT", "TIMEOUT"],
    })

    assert timeout_share_for("reach_d1_w50")(frame).value == 0.5


def test_already_hit_share_measures_free_wins():
    """
    The share of raced breaches whose target was already reached when the
    breach confirmed. A high number would hollow out the headline rate.
    """
    frame = pd.DataFrame({"target_already_hit": [True, True, False, None]})

    stat = already_hit_share(frame)

    assert stat.value == pytest.approx(2 / 3)
    assert stat.n == 3


def test_already_hit_share_is_none_when_nothing_was_raced():
    frame = pd.DataFrame({"target_already_hit": [None, None]})

    assert already_hit_share(frame).value is None
```

Add `reach_rate_for, timeout_share_for, already_hit_share` to that file's import block.

- [ ] **Step 2: Run to verify they fail**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_statistics.py -q`
Expected: FAIL — `ImportError: cannot import name 'reach_rate_for'`

- [ ] **Step 3: Implement in `statistics.py`**

Replace `reach_next_rate` and `timeout_share` with factories, keeping the two
original names as bound instances so nothing downstream breaks:

```python
def reach_rate_for(column: str) -> StatisticFn:
    """
    REACHED / (REACHED + STOPPED) on one outcome column.

    Timeouts are excluded: a race that ran out of window is neither a win nor
    a loss, and folding it into either side would move the rate for a reason
    that has nothing to do with the levels. `timeout_share_for` reports them.
    """
    def reach_rate(events: pd.DataFrame) -> Stat:
        if column not in events.columns:
            return Stat(None, 0)
        decided = events[events[column].isin(("REACHED", "STOPPED"))]
        if decided.empty:
            return Stat(None, 0)
        reached = int((decided[column] == "REACHED").sum())
        return Stat(reached / len(decided), len(decided))

    return reach_rate


def timeout_share_for(column: str) -> StatisticFn:
    """TIMEOUT / all raced breaches, for one outcome column."""
    def timeout_share_of(events: pd.DataFrame) -> Stat:
        if column not in events.columns:
            return Stat(None, 0)
        raced = events[events[column].isin(("REACHED", "STOPPED", "TIMEOUT"))]
        if raced.empty:
            return Stat(None, 0)
        timeouts = int((raced[column] == "TIMEOUT").sum())
        return Stat(timeouts / len(raced), len(raced))

    return timeout_share_of


def already_hit_share(events: pd.DataFrame) -> Stat:
    """
    Share of raced breaches whose target was already reached at confirmation.

    A breach confirms after two closes beyond the level, which can carry price
    past the target before the race even starts. Those wins cost no travel. If
    this share is large the headline reach rate is measuring confirmation lag,
    not progression, so it is reported rather than left implicit.
    """
    if "target_already_hit" not in events.columns:
        return Stat(None, 0)
    flags = events["target_already_hit"].dropna()
    if flags.empty:
        return Stat(None, 0)
    return Stat(float(flags.astype(bool).mean()), len(flags))


# The original names, bound to the strict column, so existing callers and the
# confirmed holdout definition are untouched.
reach_next_rate = reach_rate_for("reach_outcome")
timeout_share = timeout_share_for("reach_outcome")
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/test_statistics.py -q`
Expected: `16 passed` (11 existing + 5 new).

- [ ] **Step 5: Wire the sweep into the entry point**

In `scripts/mine_gann_corpus.py`:

Import the new names:

```python
from study_tool.mining.ladder_rebuild import (
    LadderCache, add_reach_outcomes, outcome_column,
)
from study_tool.mining.statistics import (
    already_hit_share, hold_rate, mean_retest_depth, reach_rate_for,
    rejection_rate, timeout_share_for, touch_density_fn,
)
```

Change `run`'s signature to accept the sweep:

```python
def run(corpus_dir: Path, slice_name: str = "explore",
        stop_depths: Sequence[float] = (0.0,),
        windows: Optional[Sequence[int]] = None) -> str:
```

Replace the `add_reach_outcomes` call with:

```python
    events = add_reach_outcomes(events, bars, cache, meta,
                                stop_depths=stop_depths, windows=windows)
```

Replace the hard-coded statistics dict with one built from the sweep:

```python
    resolved_windows = tuple(windows or (meta.resolution_window_bars,))
    statistics = {
        "hold_rate": hold_rate,
        "rejection_rate": rejection_rate,
        "mean_retest_depth": mean_retest_depth,
        "touch_density": touch_density_fn(bar_count),
        "already_hit_share": already_hit_share,
    }
    for depth in stop_depths:
        for window in resolved_windows:
            column = outcome_column(depth, window)
            statistics[f"reach_rate[{column}]"] = reach_rate_for(column)
            statistics[f"timeout_share[{column}]"] = timeout_share_for(column)
```

Add the CLI arguments in `main()`:

```python
    parser.add_argument(
        "--stop-depths", default="0",
        help="comma-separated ladder steps behind the breached level to place "
             "the stop; 0 is the strict test (stop on the level itself)")
    parser.add_argument(
        "--windows", default="",
        help="comma-separated bar windows for the race; empty uses the "
             "corpus's own resolution_window_bars")
```

and parse them before calling `run`:

```python
    depths = tuple(float(d) for d in args.stop_depths.split(",") if d.strip())
    race_windows = tuple(int(w) for w in args.windows.split(",") if w.strip())
    text = run(Path(args.corpus), slice_name=args.slice,
               stop_depths=depths or (0.0,),
               windows=race_windows or None)
```

Add `Sequence` to the `typing` import line.

- [ ] **Step 6: Run the whole mining suite**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/mining/ -q`
Expected: all pass, including the existing end-to-end report tests — the
defaults (`stop_depths=(0.0,)`, `windows=None`) must reproduce today's behaviour
exactly.

- [ ] **Step 7: Run everything for regressions**

Run: `cd gann-visualizer/backend && python -m pytest tests/study_tool/ tests/test_event_logger_ladder_schema.py tests/test_event_logger_mfe_mae_horizons.py -q`
Expected: no pre-existing test fails.

- [ ] **Step 8: Commit**

```bash
git add gann-visualizer/backend/study_tool/mining/statistics.py gann-visualizer/backend/scripts/mine_gann_corpus.py
git add -f gann-visualizer/backend/tests/study_tool/mining/test_statistics.py
git commit -m "feat: sweep stop depth and race window from the command line

Statistics become factories bound to an outcome column, so every (depth,
window) pair gets its own reach rate and timeout share without duplicating
any logic. The original reach_next_rate and timeout_share names stay bound
to the strict column so the confirmed holdout definition is untouched.

already_hit_share reports the breaches whose target was already reached at
confirmation - if that share is large, the headline rate is measuring
confirmation lag rather than progression."
```

---

### Task 5: Run the sweep on explore, and write down what it says

The holdout for this corpus is spent. This run is exploratory only: it cannot
confirm anything, and nothing from it may be tested against this corpus's
holdout. Say so in the results document.

- [ ] **Step 1: Run the sweep**

```bash
cd gann-visualizer/backend && python scripts/mine_gann_corpus.py --corpus logs/corpus/reliance_5m_x1 --stop-depths 0,0.5,1,2 --windows 50,100 --out ../../docs/superpowers/reports
```

Expect this to take noticeably longer than the ~8m36s strict run: eight race
columns instead of one, and 21 statistics instead of 6. If it runs past ~45
minutes or exhausts memory, cut `--windows` to `50` and rerun rather than
guessing at a fix.

- [ ] **Step 2: Read `already_hit_share` first**

Before anything else. If a large share of breaches had already reached the
target at confirmation, the reach rate is partly measuring how far two
confirmation closes carry price, not whether levels chain. Record the number
and say plainly what it does to the reading.

- [ ] **Step 3: Compare depths against the strict baseline**

The depth-0, window-50 column reproduces the confirmed test exactly, so it is
the baseline every other column is read against. For each depth, record: the
real rate, the shadow range, whether real fell outside it, and the margin.

The question the sweep answers is not "is the rate higher" — a looser stop
mechanically raises the rate for real *and* shadow alike. It is whether the
**gap between real and shadow** widens, narrows, or holds as the stop loosens.
State that explicitly in the document, because a table of rising rates invites
the wrong reading.

- [ ] **Step 4: Write the results document**

Create `docs/superpowers/specs/2026-09-03-gann-pullback-sweep-results.md` with:
run parameters; `already_hit_share`; a depth × window table of real vs shadow
for the pooled case and for the groups that carried the confirmed effect
(`level_source=center`, `level_source=moon`, `level_kind=sub`,
`level_kind=major`, `level_is_halfway=False`, `level_ring_bin=10-19`,
`level_degree=90`, `level_sub_index=5`); the fairness check; and a closing
paragraph stating this is explore-only, unconfirmable on this corpus, and what
fresh data would be needed to confirm it.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-09-03-gann-pullback-sweep-results.md docs/superpowers/reports/gann-mining-report-*.md
git commit -m "docs: pullback-tolerant reach sweep, explore slice only

Answers whether the real-vs-shadow gap survives loosening the stop, which is
the question - not whether the raw rate rises, which it must for real and
shadow alike.

Explore only. This corpus's holdout is spent, so nothing here can be
confirmed on it; confirmation needs a fresh instrument or date range."
```

---

## Notes for whoever executes this

- **Do not change what `reach_outcome` means.** The confirmed 8/13 holdout
  result was measured on the strict definition under that column name. Task 3
  keeps it as an alias of the zero-depth column and Task 4 keeps
  `reach_next_rate` bound to it. If either drifts, the recorded result stops
  being reproducible.
- **The holdout is spent.** No task here touches it, and none may be added that
  does. Confirmation of anything found here needs a corpus built on a different
  instrument or date range.
- A looser stop raises the rate for shadows too. Always read the real-shadow
  gap, never the raw rate.
