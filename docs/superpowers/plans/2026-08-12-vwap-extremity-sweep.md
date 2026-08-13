# VWAP Extremity Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answer, with a number, whether fading a liquidity sweep of the Asian session high/low that lands in the 2–3 sigma Anchored VWAP zone makes money after costs on five years of BTCUSDT 5-minute data.

**Architecture:** Split scan from scoring. One slow pass over the candles writes a *ledger* of every confirmed setup with its gross (cost-free) simulated outcome under all six stop×target combinations. Every cost scenario and every filter knob is then post-hoc arithmetic over that ledger, so no cost or filter question ever requires a re-scan. Reuses the existing ORB harness for session splitting, the frozen verdict rule, breakeven interpolation and the matched placebo.

**Tech Stack:** Python 3, pandas, numpy, pytz, pytest. Frontend is React (Vite), plain `.mjs` node tests.

**Spec:** [2026-08-12-vwap-extremity-sweep-design.md](../specs/2026-08-12-vwap-extremity-sweep-design.md)

---

## Conventions used throughout

- All Python commands run from `C:\Dev\GannTesting\gann-visualizer\backend`.
- Test command is `python -m pytest tests/<file> -v`.
- Commit style is Conventional Commits, imperative, lower case, no trailing period (see `AGENTS.md`).
- Every commit message ends with:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  ```
- `session.py` names its local-time column `ist` for historical reasons. It holds
  *session-local* time under whatever timezone is passed. Do not rename it —
  ORB, CRT and their tests all read that column.

---

## File structure

**Create:**

| Path | Responsibility |
|---|---|
| `strategy/vwap_sweep/__init__.py` | Empty package marker |
| `strategy/vwap_sweep/vwap_bands.py` | Anchored VWAP, sigma, anchor policies. Pure numeric, no strategy rules |
| `strategy/vwap_sweep/extremity_sweep.py` | One session in, every confirmed setup out |
| `strategy/vwap_sweep/ledger.py` | Simulate every stop×target path per setup; serialise and load the ledger |
| `strategy/vwap_sweep/scoring.py` | Cost models, cell filters, per-cell scoring, verdict |
| `strategy/vwap_sweep/navigator_report.py` | Ledger + cell → Hypothesis Navigator JSON |
| `scripts/run_vwap_sweep_scan.py` | Slow CLI. Writes the ledger and the Navigator run directory |
| `scripts/score_vwap_sweep.py` | Instant CLI. Ledger → verdict markdown + Navigator JSON |
| `tests/test_vwap_bands.py` | |
| `tests/test_extremity_sweep.py` | |
| `tests/test_vwap_sweep_ledger.py` | |
| `tests/test_vwap_sweep_scoring.py` | |
| `tests/test_vwap_sweep_navigator_report.py` | |
| `../frontend/src/hypothesisColumns.js` | Column resolution and cell formatting for the Navigator table |
| `../frontend/src/hypothesisColumns.test.mjs` | |

**Modify:**

| Path | Change |
|---|---|
| `analysis/signal_trade_simulator.py` | Optional `target_price` on `CandleSignal`; `mfe_r` / `mae_r` on every simulated trade |
| `strategy/orb/session.py` | `tz` parameter, defaulting to `Asia/Kolkata` |
| `strategy/orb/placebo.py` | Hold target distance fixed alongside stop distance |
| `strategy/orb/verdict.py` | Comment only: record that the metric fields carry whatever the caller chose |
| `tests/test_signal_trade_simulator.py` | Additions for the two simulator changes |
| `tests/test_orb_placebo.py` | Additions for the target-distance fix |
| `tests/test_orb_session.py` | Additions for the timezone parameter |
| `../frontend/src/App.jsx` | Drive the events table from `columns` when the report provides it |

---

## Task 0: Worktree

**Files:** none — repository setup only.

- [ ] **Step 1: Confirm the working tree is clean enough to branch from**

Run: `git -C C:/Dev/GannTesting status --short`

There are pre-existing modified and untracked files on this branch. Do **not**
commit, stash or revert them — they belong to other work. A worktree is used
precisely so they are left alone.

- [ ] **Step 2: Create the worktree**

```bash
git -C C:/Dev/GannTesting worktree add .worktrees/vwap-extremity-sweep -b feat/vwap-extremity-sweep
```

Expected: `Preparing worktree (new branch 'feat/vwap-extremity-sweep')` then `HEAD is now at 1b73e13 ...`

- [ ] **Step 3: Verify the spec is present in the worktree**

Run: `ls C:/Dev/GannTesting/.worktrees/vwap-extremity-sweep/docs/superpowers/specs/2026-08-12-vwap-extremity-sweep-design.md`

Expected: the path prints. If it does not, the worktree branched from the wrong commit — delete it and branch from `1b73e13` explicitly.

- [ ] **Step 4: Verify the existing suite passes before changing anything**

Run from `C:/Dev/GannTesting/.worktrees/vwap-extremity-sweep/gann-visualizer/backend`:

```bash
python -m pytest tests/test_orb_session.py tests/test_orb_placebo.py tests/test_crt_swept_level.py -q
```

Expected: all pass. If anything already fails, stop and report it — do not build on a red suite.

**All remaining tasks run inside `C:\Dev\GannTesting\.worktrees\vwap-extremity-sweep\gann-visualizer\backend` unless stated otherwise.**

---

## Task 1: `target_price` on `CandleSignal`

The strategy's exit is the VWAP price, which is a different distance every trade.
The simulator currently derives every target as `entry ± R × risk`.

**Files:**
- Modify: `analysis/signal_trade_simulator.py`
- Test: `tests/test_signal_trade_simulator.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_signal_trade_simulator.py`:

```python
def test_explicit_target_price_overrides_the_r_derived_target():
    candles = pd.DataFrame(
        {
            "bar_index": [0, 1, 2, 3],
            "open": [100.0, 100.0, 100.0, 100.0],
            "high": [100.0, 103.0, 103.0, 103.0],
            "low": [100.0, 99.0, 99.0, 99.0],
            "close": [100.0, 102.0, 102.0, 102.0],
        }
    )
    signal = CandleSignal(
        bar_index=0,
        side="LONG",
        entry_price=100.0,
        stop_price=98.0,
        signal_time="t",
        target_price=101.0,
    )
    result = simulate_trade_grid(candles=candles, signals=[signal], r_values=[5.0], max_hold_bars=3)
    trade = result["best"]["per_signal"]["0:0"]

    # R = 5 would put the target at 110 and never fill. The explicit 101 fills on bar 1.
    assert trade["target_price"] == 101.0
    assert trade["exit_reason"] == "target"
    assert trade["exit_price"] == 101.0


def test_absent_target_price_preserves_r_derived_behaviour():
    candles = pd.DataFrame(
        {
            "bar_index": [0, 1, 2],
            "open": [100.0, 100.0, 100.0],
            "high": [100.0, 105.0, 105.0],
            "low": [100.0, 99.5, 99.5],
            "close": [100.0, 104.0, 104.0],
        }
    )
    signal = CandleSignal(
        bar_index=0, side="LONG", entry_price=100.0, stop_price=98.0, signal_time="t"
    )
    result = simulate_trade_grid(candles=candles, signals=[signal], r_values=[2.0], max_hold_bars=2)
    trade = result["best"]["per_signal"]["0:0"]

    assert trade["target_price"] == 104.0  # 100 + 2 * 2
    assert trade["exit_reason"] == "target"


def test_target_price_on_the_wrong_side_of_entry_raises():
    candles = pd.DataFrame(
        {
            "bar_index": [0, 1],
            "open": [100.0, 100.0],
            "high": [100.0, 101.0],
            "low": [100.0, 99.0],
            "close": [100.0, 100.0],
        }
    )
    signal = CandleSignal(
        bar_index=0,
        side="LONG",
        entry_price=100.0,
        stop_price=98.0,
        signal_time="t",
        target_price=99.0,  # below entry on a LONG
    )
    with pytest.raises(ValueError, match="target_price"):
        simulate_trade_grid(candles=candles, signals=[signal], r_values=[2.0], max_hold_bars=1)
```

If `pytest` and `CandleSignal` are not already imported at the top of that file, add:

```python
import pytest
from analysis.signal_trade_simulator import CandleSignal, simulate_trade_grid
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_signal_trade_simulator.py -k target_price -v
```

Expected: FAIL — `TypeError: CandleSignal.__init__() got an unexpected keyword argument 'target_price'`

- [ ] **Step 3: Add the field**

In `analysis/signal_trade_simulator.py`, inside `class CandleSignal`, after the
`entry_bar_index` field and its docstring, add:

```python
    target_price: Optional[float] = None
    """Explicit target, overriding ``entry ± r_value × risk`` when set.

    Needed by strategies whose exit is a price level rather than a multiple of
    risk -- a VWAP reversion target is a different distance on every trade. The
    R grid still runs, but every R produces the same target, so ``r_value`` in
    the output records which grid slot the trade came from, not the target.
    """
```

- [ ] **Step 4: Honour the field**

In `_simulate_single_trade`, replace this line:

```python
    target_price = _target_price(signal.entry_price, signal.stop_price, side, r_value)
```

with:

```python
    target_price = _resolve_target_price(signal, side, r_value)
```

Then add this function immediately after `_target_price`:

```python
def _resolve_target_price(signal: CandleSignal, side: str, r_value: float) -> float:
    """Explicit target when the signal carries one, else the R-derived target."""
    if signal.target_price is None:
        return _target_price(signal.entry_price, signal.stop_price, side, r_value)

    target = float(signal.target_price)
    if side == "LONG" and target <= signal.entry_price:
        raise ValueError(
            f"signal at bar {signal.bar_index}: LONG target_price {target} is not "
            f"above entry_price {signal.entry_price}"
        )
    if side == "SHORT" and target >= signal.entry_price:
        raise ValueError(
            f"signal at bar {signal.bar_index}: SHORT target_price {target} is not "
            f"below entry_price {signal.entry_price}"
        )
    return target
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/test_signal_trade_simulator.py -v
```

Expected: PASS, including every pre-existing test in the file.

- [ ] **Step 6: Run the whole suite to confirm nothing regressed**

```bash
python -m pytest tests/ -q
```

Expected: same pass/fail counts as the Task 0 Step 4 baseline, plus the three new tests.

- [ ] **Step 7: Commit**

```bash
git add analysis/signal_trade_simulator.py tests/test_signal_trade_simulator.py
git commit -m "feat: explicit target_price on CandleSignal

A VWAP reversion target is a different distance on every trade, so it
cannot be expressed as a multiple of risk. Absent the field, behaviour is
unchanged. A target on the wrong side of entry raises rather than
silently producing an unreachable or instantly-filled trade.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: MFE and MAE on every simulated trade

`mfe_r` and `mae_r` show how close a losing trade came to working. They are the
first thing to look at when a result is marginal, and the ledger needs them
recorded once because they cannot be recovered post-hoc.

**Files:**
- Modify: `analysis/signal_trade_simulator.py`
- Test: `tests/test_signal_trade_simulator.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_signal_trade_simulator.py`:

```python
def test_mfe_and_mae_are_recorded_in_r_units():
    # LONG at 100, stop 98, so risk = 2. Bar 1 ranges 99 to 104 then the trade
    # times out at 100. Best excursion +4 = 2.0R, worst -1 = -0.5R.
    candles = pd.DataFrame(
        {
            "bar_index": [0, 1],
            "open": [100.0, 100.0],
            "high": [100.0, 104.0],
            "low": [100.0, 99.0],
            "close": [100.0, 100.0],
        }
    )
    signal = CandleSignal(
        bar_index=0,
        side="LONG",
        entry_price=100.0,
        stop_price=98.0,
        signal_time="t",
        target_price=110.0,  # unreachable, so the trade times out and both excursions survive
    )
    result = simulate_trade_grid(candles=candles, signals=[signal], r_values=[2.0], max_hold_bars=1)
    trade = result["best"]["per_signal"]["0:0"]

    assert trade["mfe_r"] == 2.0
    assert trade["mae_r"] == -0.5


def test_short_mfe_and_mae_mirror_the_long_case():
    candles = pd.DataFrame(
        {
            "bar_index": [0, 1],
            "open": [100.0, 100.0],
            "high": [100.0, 101.0],
            "low": [100.0, 96.0],
            "close": [100.0, 100.0],
        }
    )
    signal = CandleSignal(
        bar_index=0,
        side="SHORT",
        entry_price=100.0,
        stop_price=102.0,
        signal_time="t",
        target_price=90.0,
    )
    result = simulate_trade_grid(candles=candles, signals=[signal], r_values=[2.0], max_hold_bars=1)
    trade = result["best"]["per_signal"]["0:0"]

    assert trade["mfe_r"] == 2.0   # down to 96 is +4 favourable, risk 2
    assert trade["mae_r"] == -0.5  # up to 101 is -1 adverse
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_signal_trade_simulator.py -k "mfe" -v
```

Expected: FAIL with `KeyError: 'mfe_r'`

- [ ] **Step 3: Track the excursions**

In `_simulate_single_trade`, immediately after this line:

```python
    stop_price = signal.stop_price
```

add:

```python
    best_excursion = 0.0
    worst_excursion = 0.0
```

Inside the `for position in range(start_position, end_position):` loop, directly
after `exit_bar_index = last_observed_bar_index`, add:

```python
        if is_long:
            best_excursion = max(best_excursion, bar_high - signal.entry_price)
            worst_excursion = min(worst_excursion, bar_low - signal.entry_price)
        else:
            best_excursion = max(best_excursion, signal.entry_price - bar_low)
            worst_excursion = min(worst_excursion, signal.entry_price - bar_high)
```

Placing it before the stop/target checks means the exit bar's own range counts,
which is correct — the excursion happened.

- [ ] **Step 4: Report them**

In the returned dict in `_simulate_single_trade`, after the `"net_r"` entry, add:

```python
        "mfe_r": round(best_excursion / risk, 6),
        "mae_r": round(worst_excursion / risk, 6),
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/test_signal_trade_simulator.py -v
```

Expected: PASS.

- [ ] **Step 6: Run the whole suite**

```bash
python -m pytest tests/ -q
```

Expected: no regressions. The change is additive — existing callers reading known
keys are unaffected.

- [ ] **Step 7: Commit**

```bash
git add analysis/signal_trade_simulator.py tests/test_signal_trade_simulator.py
git commit -m "feat: record MFE and MAE in R units per simulated trade

How close a losing trade came to working cannot be recovered after the
fact, so it has to be captured during the walk. Both are signed relative
to the trade's direction: mfe_r is never negative, mae_r never positive.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: Timezone parameter on the session helpers

The session module hardcodes `Asia/Kolkata`. Crypto sessions are UTC days.

**Files:**
- Modify: `strategy/orb/session.py`
- Test: `tests/test_orb_session.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_orb_session.py`:

```python
def test_split_sessions_groups_by_utc_day_when_given_utc():
    import pytz
    from strategy.orb.session import add_bar_index, split_sessions

    utc = pytz.UTC
    rows = []
    # 23:50 and 23:55 on the 1st, then 00:00 and 00:05 on the 2nd.
    for stamp in ["2026-01-01 23:50", "2026-01-01 23:55", "2026-01-02 00:00", "2026-01-02 00:05"]:
        naive = pd.Timestamp(stamp)
        rows.append(
            {
                "timestamp": int(utc.localize(naive.to_pydatetime()).timestamp()),
                "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1.0,
            }
        )
    sessions = split_sessions(add_bar_index(pd.DataFrame(rows)), tz=utc)

    assert sorted(sessions) == [date(2026, 1, 1), date(2026, 1, 2)]
    assert len(sessions[date(2026, 1, 1)]) == 2
    assert len(sessions[date(2026, 1, 2)]) == 2


def test_split_sessions_still_defaults_to_ist():
    import pytz
    from strategy.orb.session import add_bar_index, split_sessions

    utc = pytz.UTC
    # 19:00 UTC on the 1st is 00:30 IST on the 2nd.
    naive = pd.Timestamp("2026-01-01 19:00")
    rows = [
        {
            "timestamp": int(utc.localize(naive.to_pydatetime()).timestamp()),
            "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1.0,
        }
    ]
    sessions = split_sessions(add_bar_index(pd.DataFrame(rows)))

    assert list(sessions) == [date(2026, 1, 2)]


def test_utc_asian_window_and_flat_by_resolve():
    import pytz
    from datetime import time as dtime
    from strategy.orb.session import (
        add_bar_index, opening_range_bars, post_range_bars, split_sessions,
    )

    utc = pytz.UTC
    rows = []
    for minute_offset in range(0, 1440, 5):  # a full UTC day of 5m bars
        naive = pd.Timestamp("2026-01-01 00:00") + pd.Timedelta(minutes=minute_offset)
        rows.append(
            {
                "timestamp": int(utc.localize(naive.to_pydatetime()).timestamp()),
                "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1.0,
            }
        )
    session = split_sessions(add_bar_index(pd.DataFrame(rows)), tz=utc)[date(2026, 1, 1)]

    asian = opening_range_bars(session, or_minutes=480, session_start=dtime(0, 0))
    tradable = post_range_bars(
        session, or_minutes=480, session_start=dtime(0, 0), flat_by=dtime(23, 55)
    )

    assert len(asian) == 96
    assert len(tradable) == 192
    assert len(asian) + len(tradable) == 288
```

If `date` is not already imported in that file, add `from datetime import date` at the top.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_orb_session.py -k "utc or defaults_to_ist" -v
```

Expected: FAIL — `split_sessions() got an unexpected keyword argument 'tz'`

- [ ] **Step 3: Thread the timezone through**

In `strategy/orb/session.py`, replace `_attach_ist` and `split_sessions` with:

```python
def _attach_ist(bars: pd.DataFrame, tz=IST) -> pd.DataFrame:
    """Attach session-local time columns.

    The columns are named ``ist`` / ``ist_time`` for historical reasons; they
    hold local time under whichever ``tz`` is passed. ORB, CRT and their tests
    read those names, so they are not renamed.
    """
    out = bars.copy()
    out["ist"] = pd.to_datetime(out["timestamp"], unit="s", utc=True).dt.tz_convert(tz)
    out["session_date"] = out["ist"].dt.date
    out["ist_time"] = out["ist"].dt.time
    return out


def split_sessions(bars: pd.DataFrame, tz=IST) -> Dict[date, pd.DataFrame]:
    """Group bars into one DataFrame per local trading date, ordered by date.

    Each session keeps its global ``bar_index`` and gains ``ist``,
    ``session_date`` and ``ist_time`` columns. ``tz`` defaults to IST so
    existing callers are unaffected; crypto passes ``pytz.UTC``.
    """
    if "bar_index" not in bars.columns:
        raise ValueError("call add_bar_index before split_sessions")

    enriched = _attach_ist(bars, tz=tz)
    sessions: Dict[date, pd.DataFrame] = {}
    for session_date, group in enriched.groupby("session_date", sort=True):
        sessions[session_date] = group.sort_values("bar_index").reset_index(drop=True)
    return sessions
```

`opening_range_bars`, `post_range_bars` and `bars_until_flat` need no change —
they already take `session_start` and `flat_by` as arguments and read `ist_time`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_orb_session.py -v
```

Expected: PASS, including every pre-existing test.

- [ ] **Step 5: Commit**

```bash
git add strategy/orb/session.py tests/test_orb_session.py
git commit -m "feat: session splitting accepts a timezone

Crypto sessions are UTC days, not IST ones. Defaults to Asia/Kolkata so
ORB and CRT are untouched. The local-time columns keep their ist names
because three modules and their tests read them.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: Anchored VWAP and sigma bands

**Files:**
- Create: `strategy/vwap_sweep/__init__.py`
- Create: `strategy/vwap_sweep/vwap_bands.py`
- Test: `tests/test_vwap_bands.py`

- [ ] **Step 1: Create the package marker**

Create `strategy/vwap_sweep/__init__.py` as an empty file (zero bytes), matching
`strategy/orb/__init__.py` and `strategy/crt/__init__.py`.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_vwap_bands.py`:

```python
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import pytz

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.orb.session import add_bar_index, split_sessions
from strategy.vwap_sweep.vwap_bands import DAILY, WEEKLY, add_vwap_bands

UTC = pytz.UTC


def _bars(rows, start="2026-01-05 00:00"):
    """rows: list of (high, low, close, volume). 5-minute bars from `start` UTC.

    2026-01-05 is a Monday, which the weekly anchor tests rely on.
    """
    records = []
    for i, (h, l, c, v) in enumerate(rows):
        naive = pd.Timestamp(start) + pd.Timedelta(minutes=5 * i)
        records.append(
            {
                "timestamp": int(UTC.localize(naive.to_pydatetime()).timestamp()),
                "open": c, "high": h, "low": l, "close": c, "volume": v,
            }
        )
    frame = add_bar_index(pd.DataFrame(records))
    enriched = pd.concat(split_sessions(frame, tz=UTC).values()).sort_values("bar_index")
    return enriched.reset_index(drop=True)


def test_vwap_matches_a_hand_computed_value():
    # tp = (h + l + c) / 3. Bar 0: (12+6+9)/3 = 9. Bar 1: (24+12+18)/3 = 18.
    frame = add_vwap_bands(_bars([(12, 6, 9, 1.0), (24, 12, 18, 3.0)]), DAILY)

    assert frame["vwap"].iloc[0] == pytest.approx(9.0)
    # (9*1 + 18*3) / 4 = 15.75
    assert frame["vwap"].iloc[1] == pytest.approx(15.75)


def test_sigma_matches_a_hand_computed_value():
    frame = add_vwap_bands(_bars([(12, 6, 9, 1.0), (24, 12, 18, 3.0)]), DAILY)

    # Weighted variance about 15.75: (1*(9-15.75)^2 + 3*(18-15.75)^2) / 4
    #                              = (45.5625 + 15.1875) / 4 = 15.1875
    assert frame["sigma"].iloc[0] == pytest.approx(0.0)
    assert frame["sigma"].iloc[1] == pytest.approx(np.sqrt(15.1875))


def test_a_future_bar_does_not_change_earlier_values():
    rows = [(12, 6, 9, 1.0), (24, 12, 18, 3.0), (30, 20, 25, 2.0)]
    short = add_vwap_bands(_bars(rows[:2]), DAILY)
    long = add_vwap_bands(_bars(rows), DAILY)

    assert long["vwap"].iloc[:2].tolist() == pytest.approx(short["vwap"].tolist())
    assert long["sigma"].iloc[:2].tolist() == pytest.approx(short["sigma"].tolist())


def test_daily_anchor_resets_at_the_utc_day_boundary():
    # 288 bars is exactly one UTC day, so bar 288 opens the next day.
    rows = [(100, 100, 100, 1.0)] * 288 + [(200, 200, 200, 1.0)]
    frame = add_vwap_bands(_bars(rows), DAILY)

    assert frame["bars_since_anchor"].iloc[287] == 288
    assert frame["bars_since_anchor"].iloc[288] == 1
    assert frame["vwap"].iloc[288] == pytest.approx(200.0)  # not blended with the prior day


def test_weekly_anchor_holds_across_a_day_boundary_and_resets_on_monday():
    rows = [(100, 100, 100, 1.0)] * 288 + [(200, 200, 200, 1.0)]
    frame = add_vwap_bands(_bars(rows), WEEKLY)

    # Tuesday's first bar still carries Monday's accumulation.
    assert frame["bars_since_anchor"].iloc[288] == 289
    assert frame["vwap"].iloc[288] == pytest.approx((100.0 * 288 + 200.0) / 289)


def test_zero_volume_bars_contribute_nothing_and_do_not_raise():
    frame = add_vwap_bands(_bars([(10, 10, 10, 0.0), (20, 20, 20, 5.0)]), DAILY)

    assert np.isnan(frame["vwap"].iloc[0])   # no volume yet, so no VWAP exists
    assert frame["vwap"].iloc[1] == pytest.approx(20.0)


def test_shifted_and_naive_variance_agree_on_well_conditioned_input():
    rng = np.random.default_rng(0)
    rows = [(p + 1, p - 1, p, float(v)) for p, v in zip(rng.uniform(90, 110, 200), rng.uniform(1, 5, 200))]
    frame = add_vwap_bands(_bars(rows), DAILY)

    tp = ((frame["high"] + frame["low"] + frame["close"]) / 3.0).to_numpy()
    v = frame["volume"].to_numpy()
    naive_var = np.cumsum(tp * tp * v) / np.cumsum(v) - frame["vwap"].to_numpy() ** 2
    naive_sigma = np.sqrt(np.maximum(naive_var, 0.0))

    assert frame["sigma"].to_numpy() == pytest.approx(naive_sigma, abs=1e-9)
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
python -m pytest tests/test_vwap_bands.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'strategy.vwap_sweep.vwap_bands'`

- [ ] **Step 4: Write the implementation**

Create `strategy/vwap_sweep/vwap_bands.py`:

```python
"""
Anchored VWAP and its volume-weighted standard-deviation bands.

Pure numerics. No strategy rules live here.

Everything is cumulative from an anchor bar and uses only bars up to and
including the bar being valued, so no value ever depends on the future.

Numerical note. The textbook ``var = sum(tp^2 v)/sum(v) - vwap^2`` cancels
catastrophically when sigma is small relative to price. At BTC 100,000 with a
50-dollar sigma those two terms agree to nine significant figures and float64
carries about fifteen, so most of the answer would be rounding error. Shifting
the origin to the anchor period's first typical price fixes it: the accumulated
quantity is then intraday-range sized rather than price-level sized.
"""

from typing import Any, Dict

import numpy as np
import pandas as pd

DAILY = "daily"
WEEKLY = "weekly"
ANCHOR_POLICIES = (DAILY, WEEKLY)


def anchor_key(local_time: pd.Series, policy: str) -> pd.Series:
    """The anchor period each bar belongs to, as a date.

    ``daily`` keys on the local date. ``weekly`` keys on the Monday of the
    local week, so the accumulation carries across day boundaries.
    """
    if policy == DAILY:
        return local_time.dt.date
    if policy == WEEKLY:
        monday = local_time - pd.to_timedelta(local_time.dt.weekday, unit="D")
        return monday.dt.date
    raise ValueError(f"unknown anchor policy {policy!r}, expected one of {ANCHOR_POLICIES}")


def add_vwap_bands(bars: pd.DataFrame, policy: str) -> pd.DataFrame:
    """Attach ``vwap``, ``sigma`` and ``bars_since_anchor`` columns.

    Args:
        bars: needs ``high``, ``low``, ``close``, ``volume`` and the ``ist``
            local-time column produced by ``strategy.orb.session.split_sessions``.
        policy: ``DAILY`` or ``WEEKLY``.

    Returns:
        A copy of ``bars`` with the three columns added. ``vwap`` and ``sigma``
        are NaN for any bar whose anchor period has seen no volume yet -- a VWAP
        with no volume behind it does not exist, and NaN says so rather than
        inventing a number.
    """
    if policy not in ANCHOR_POLICIES:
        raise ValueError(f"unknown anchor policy {policy!r}, expected one of {ANCHOR_POLICIES}")
    for column in ("high", "low", "close", "volume", "ist"):
        if column not in bars.columns:
            raise ValueError(f"bars must have a {column!r} column")

    out = bars.copy()
    out["_anchor"] = anchor_key(out["ist"], policy)

    typical = (out["high"] + out["low"] + out["close"]) / 3.0
    out["_tp"] = typical

    pieces = []
    for _, group in out.groupby("_anchor", sort=False):
        pieces.append(_accumulate(group))

    result = pd.concat(pieces).sort_index()
    return result.drop(columns=["_anchor", "_tp"])


def _accumulate(group: pd.DataFrame) -> pd.DataFrame:
    """Cumulative VWAP and sigma for one anchor period, shifted origin."""
    out = group.copy()
    volume = out["volume"].to_numpy(dtype=float)
    typical = out["_tp"].to_numpy(dtype=float)

    origin = float(typical[0])
    delta = typical - origin

    sum_v = np.cumsum(volume)
    sum_dv = np.cumsum(delta * volume)
    sum_d2v = np.cumsum(delta * delta * volume)

    has_volume = sum_v > 0
    mean_d = np.divide(sum_dv, sum_v, out=np.full_like(sum_v, np.nan), where=has_volume)
    mean_d2 = np.divide(sum_d2v, sum_v, out=np.full_like(sum_v, np.nan), where=has_volume)

    out["vwap"] = origin + mean_d
    # Residual float error can push a genuinely zero variance marginally
    # negative; clamping is correct, not a papering-over.
    out["sigma"] = np.sqrt(np.maximum(mean_d2 - mean_d * mean_d, 0.0))
    out["bars_since_anchor"] = np.arange(1, len(out) + 1)
    return out


def band(vwap: float, sigma: float, multiple: float) -> float:
    """Upper band for a positive multiple, lower for a negative one."""
    return vwap + multiple * sigma
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/test_vwap_bands.py -v
```

Expected: PASS, 8 tests.

- [ ] **Step 6: Commit**

```bash
git add strategy/vwap_sweep/__init__.py strategy/vwap_sweep/vwap_bands.py tests/test_vwap_bands.py
git commit -m "feat: anchored VWAP with volume-weighted sigma bands

Daily and weekly anchor policies, cumulative from the anchor and never
reading past the bar being valued.

Accumulates around the anchor period's first typical price rather than
around zero. The textbook form subtracts two numbers that agree to nine
significant figures at BTC price levels, which leaves mostly rounding
error; shifting the origin keeps the accumulated quantity intraday-range
sized. A test pins the two forms together on well-conditioned input.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: Setup detection

**Files:**
- Create: `strategy/vwap_sweep/extremity_sweep.py`
- Test: `tests/test_extremity_sweep.py`

The scan runs at the loosest settings and records **every** confirmed setup in a
session, not just the first. Tighter cells filter that list afterwards, and a
cell that excludes the day's first setup must be able to take the next one.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_extremity_sweep.py`:

```python
import sys
from datetime import date, time
from pathlib import Path

import pandas as pd
import pytz

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.orb.session import add_bar_index, split_sessions
from strategy.vwap_sweep.extremity_sweep import DAILY, find_setups

UTC = pytz.UTC
DAY = "2026-01-05"

# Short windows keep the fixtures readable. The real run uses 480 / 23:55.
PARAMS = {
    "asian_minutes": 20,          # 4 bars of Asian range
    "session_start": time(0, 0),
    "flat_by": time(1, 30),       # bar 18 is the last tradable bar
    "max_wait_bars": 6,
    "min_sweep_sigma": 2.0,
    "anchor_policy": DAILY,
    # The completeness guards are for real 288-bar days. Switching them off here
    # keeps the fixtures short; Task 7's integration tests exercise them.
    "min_session_bars": 0,
    "min_asian_bars": 0,
}


def _session(rows):
    """rows: list of (high, low, close, volume). 5-minute bars from 00:00 UTC."""
    records = []
    for i, (h, l, c, v) in enumerate(rows):
        naive = pd.Timestamp(f"{DAY} 00:00:00") + pd.Timedelta(minutes=5 * i)
        records.append(
            {
                "timestamp": int(UTC.localize(naive.to_pydatetime()).timestamp()),
                "open": c, "high": h, "low": l, "close": c, "volume": v,
            }
        )
    frame = add_bar_index(pd.DataFrame(records))
    return split_sessions(frame, tz=UTC)[date(2026, 1, 5)]


def _asian(n=4):
    """Quiet Asian-range bars. High 101, low 99, so asian_high = 101."""
    return [(101.0, 99.0, 100.0, 10.0)] * n


def _quiet(n):
    return [(100.2, 99.8, 100.0, 10.0)] * n


def test_a_swept_asian_high_in_the_extremity_zone_produces_a_short():
    # Bars 4-9 stay quiet so sigma settles. Bar 10 spikes to 130 (far beyond 2 sigma
    # and beyond asian_high 101). Bar 11 closes back at 100.
    rows = _asian() + _quiet(6) + [(130.0, 100.0, 128.0, 50.0)] + _quiet(8)
    scan = find_setups(_session(rows), PARAMS)

    assert scan.reason is None
    assert len(scan.setups) == 1
    setup = scan.setups[0]
    assert setup["direction"] == "SHORT"
    assert setup["swept_level"] == "asian_high"
    assert setup["sweep_bar_index"] == 10
    assert setup["confirm_bar_index"] == 11
    assert setup["bars_waited"] == 1
    assert setup["sweep_sigma"] >= 2.0


def test_the_long_side_is_the_exact_mirror():
    rows = _asian() + _quiet(6) + [(100.0, 70.0, 72.0, 50.0)] + _quiet(8)
    scan = find_setups(_session(rows), PARAMS)

    assert len(scan.setups) == 1
    setup = scan.setups[0]
    assert setup["direction"] == "LONG"
    assert setup["swept_level"] == "asian_low"
    assert setup["sweep_bar_index"] == 10


def test_entry_is_the_next_bar_open_not_the_confirmation_close():
    rows = _asian() + _quiet(6) + [(130.0, 100.0, 128.0, 50.0)] + _quiet(8)
    session = _session(rows)
    scan = find_setups(session, PARAMS)
    setup = scan.setups[0]

    entry_row = session[session["bar_index"] == setup["entry_bar_index"]].iloc[0]
    assert setup["entry_bar_index"] == setup["confirm_bar_index"] + 1
    assert setup["entry_price"] == float(entry_row["open"])
    assert setup["entry_price"] != setup["confirm_close"]


def test_a_wick_past_the_level_that_misses_the_extremity_zone_is_not_a_sweep():
    # 101.5 clears asian_high 101 but is nowhere near 2 sigma above VWAP.
    rows = _asian() + _quiet(6) + [(101.5, 99.9, 100.0, 10.0)] + _quiet(8)
    scan = find_setups(_session(rows), PARAMS)

    assert scan.setups == []
    assert scan.reason == "no_sweep"


def test_reaching_the_extremity_zone_without_taking_the_level_is_not_a_sweep():
    # Asian range is deliberately wide, so a big spike still sits under asian_high.
    rows = [(200.0, 99.0, 100.0, 10.0)] * 4 + _quiet(6) + [(150.0, 100.0, 101.0, 50.0)] + _quiet(8)
    scan = find_setups(_session(rows), PARAMS)

    assert scan.setups == []
    assert scan.reason == "no_sweep"


def test_a_sweep_that_never_confirms_is_recorded_and_counted():
    # Spikes and stays above asian_high for the rest of the session.
    rows = _asian() + _quiet(6) + [(130.0, 100.0, 128.0, 50.0)] + [(131.0, 127.0, 130.0, 10.0)] * 8
    scan = find_setups(_session(rows), PARAMS)

    assert scan.setups == []
    assert scan.reason == "unconfirmed_sweep"
    assert scan.diagnostics["unconfirmed_sweeps"] == 1


def test_a_self_confirming_sweep_bar_is_flagged_and_not_traded():
    # One bar both wicks to 130 and closes back at 100. That is the CRT pattern.
    rows = _asian() + _quiet(6) + [(130.0, 99.0, 100.0, 50.0)] + _quiet(8)
    scan = find_setups(_session(rows), PARAMS)

    assert scan.diagnostics["sweep_bar_self_confirmed"] == 1
    assert all(setup["bars_waited"] >= 1 for setup in scan.setups)


def test_every_setup_in_a_session_is_recorded_not_just_the_first():
    rows = (
        _asian()
        + _quiet(6)
        + [(130.0, 100.0, 128.0, 50.0)]   # bar 10 sweep
        + [(129.0, 99.0, 100.0, 20.0)]    # bar 11 confirm
        + _quiet(2)
        + [(140.0, 100.0, 138.0, 50.0)]   # bar 14 second sweep
        + [(139.0, 99.0, 100.0, 20.0)]    # bar 15 second confirm
        + _quiet(3)
    )
    scan = find_setups(_session(rows), PARAMS)

    assert [s["sweep_bar_index"] for s in scan.setups] == [10, 14]


def test_a_confirmation_on_the_last_tradable_bar_leaves_no_entry_bar():
    # flat_by 01:30 makes bar 18 the last tradable bar, so a confirm there
    # cannot be entered on bar 19.
    rows = _asian() + _quiet(13) + [(130.0, 100.0, 128.0, 50.0)] + [(129.0, 99.0, 100.0, 20.0)]
    scan = find_setups(_session(rows), PARAMS)

    assert scan.setups == []
    assert scan.reason == "no_entry_bar_before_flat"


def test_bands_are_read_at_the_confirmation_bar():
    rows = _asian() + _quiet(6) + [(130.0, 100.0, 128.0, 50.0)] + _quiet(8)
    session = _session(rows)
    scan = find_setups(session, PARAMS)
    setup = scan.setups[0]

    assert setup["band_2"] == setup["vwap_at_confirm"] + 2.0 * setup["sigma_at_confirm"]
    assert setup["band_3"] == setup["vwap_at_confirm"] + 3.0 * setup["sigma_at_confirm"]
    assert setup["target_candidates"]["vwap"] == setup["vwap_at_confirm"]


def test_a_degenerate_asian_range_is_skipped_with_a_reason():
    rows = [(100.0, 100.0, 100.0, 10.0)] * 4 + _quiet(14)
    scan = find_setups(_session(rows), PARAMS)

    assert scan.setups == []
    assert scan.reason == "degenerate_asian_range"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_extremity_sweep.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'strategy.vwap_sweep.extremity_sweep'`

- [ ] **Step 3: Write the implementation**

Create `strategy/vwap_sweep/extremity_sweep.py`:

```python
"""
Fade a liquidity sweep that lands in the VWAP extremity zone.

A bar's wick takes out the Asian session high (or low) AND reaches at least the
2-sigma Anchored VWAP band. The break is then rejected: a later bar closes back
inside both the level and the band. Fade the sweep.

Three deliberate choices, each argued in the design spec:

- The sweep bar may not be its own confirmation. ``bars_waited >= 1``. A bar that
  both sweeps and closes back inside is the CRT / failed-breakout pattern, tested
  as ORB variant C and already FAIL on NIFTY. Blending a known loser into a new
  test would make the result uninterpretable. Such bars are counted, not traded.

- Entry is the OPEN of the bar after the confirmation. A bar is only known to
  have qualified once it has closed, so its close is not an available fill.

- Every price the trade depends on is read at the confirmation bar, the last
  fully closed bar before the fill.

This module decides only where to enter and which stop and target candidates
exist. Path simulation, costs and P&L belong to ledger.py and scoring.py.
"""

from dataclasses import dataclass, field
from datetime import date, time
from typing import Any, Dict, List, Optional

import pandas as pd

from strategy.orb.session import FLAT_BY, SESSION_START, bars_until_flat, opening_range_bars, post_range_bars
from strategy.vwap_sweep.vwap_bands import DAILY, add_vwap_bands

DEFAULTS: Dict[str, Any] = {
    "asian_minutes": 480,          # 00:00-08:00 UTC
    "session_start": time(0, 0),
    "flat_by": time(23, 55),
    "max_wait_bars": 6,            # the loosest confirmation window; cells filter tighter
    "min_sweep_sigma": 2.0,        # the loosest extremity rule; cells filter tighter
    "anchor_policy": DAILY,
    "min_session_bars": 240,       # of 288; guards exchange downtime
    "min_asian_bars": 80,          # of 96
}


@dataclass(frozen=True)
class SessionScan:
    """Everything one session produced.

    ``setups`` is empty exactly when ``reason`` is set, so no session is ever
    silently lost. ``diagnostics`` counts what was seen but not traded.
    """

    session_date: date
    setups: List[Dict[str, Any]] = field(default_factory=list)
    reason: Optional[str] = None
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if bool(self.setups) == bool(self.reason):
            raise ValueError(
                "SessionScan must set exactly one of setups or reason, got "
                f"{len(self.setups)} setups and reason={self.reason!r}"
            )


def find_setups(session: pd.DataFrame, params: Dict[str, Any]) -> SessionScan:
    """Every confirmed sweep in one session, at the loosest settings."""
    settings = {**DEFAULTS, **params}
    session_date = session["session_date"].iloc[0]

    diagnostics = {
        "session_bars": len(session),
        "sweeps_seen": 0,
        "unconfirmed_sweeps": 0,
        "sweep_bar_self_confirmed": 0,
    }

    def skipped(reason: str) -> SessionScan:
        return SessionScan(session_date, reason=reason, diagnostics=diagnostics)

    if len(session) < settings["min_session_bars"]:
        return skipped("incomplete_day")

    asian = opening_range_bars(
        session, or_minutes=settings["asian_minutes"], session_start=settings["session_start"]
    )
    if len(asian) < settings["min_asian_bars"]:
        return skipped("incomplete_asian_range")

    asian_high = float(asian["high"].max())
    asian_low = float(asian["low"].min())
    if asian_high <= asian_low:
        return skipped("degenerate_asian_range")
    asian_range_width = asian_high - asian_low

    banded = add_vwap_bands(session, settings["anchor_policy"])
    tradable = post_range_bars(
        banded,
        or_minutes=settings["asian_minutes"],
        session_start=settings["session_start"],
        flat_by=settings["flat_by"],
    )
    if tradable.empty:
        return skipped("no_tradable_bars")

    rows = tradable.to_dict("records")
    last_tradable_bar = int(rows[-1]["bar_index"])

    setups: List[Dict[str, Any]] = []
    failed_sweeps = 0
    no_entry_bar = False
    position = 0

    while position < len(rows):
        bar = rows[position]
        sweep = _classify_sweep(bar, asian_high, asian_low, settings["min_sweep_sigma"])
        if sweep is None:
            position += 1
            continue

        diagnostics["sweeps_seen"] += 1
        if _closes_back_inside(bar, sweep, asian_high, asian_low):
            diagnostics["sweep_bar_self_confirmed"] += 1

        confirm_offset = _find_confirmation(
            rows, position, sweep, asian_high, asian_low, settings["max_wait_bars"]
        )
        if confirm_offset is None:
            diagnostics["unconfirmed_sweeps"] += 1
            failed_sweeps += 1
            position += 1
            continue

        confirm = rows[position + confirm_offset]
        confirm_bar_index = int(confirm["bar_index"])
        if confirm_bar_index >= last_tradable_bar:
            no_entry_bar = True
            position += confirm_offset + 1
            continue

        entry = rows[position + confirm_offset + 1]
        setups.append(
            _build_setup(
                session_date=session_date,
                settings=settings,
                sweep=sweep,
                sweep_bar=bar,
                confirm_bar=confirm,
                entry_bar=entry,
                banded=banded,
                asian_high=asian_high,
                asian_low=asian_low,
                asian_range_width=asian_range_width,
                confirm_offset=confirm_offset,
                failed_sweeps=failed_sweeps,
                # Mean over bars closed up to and including the sweep. Recomputed
                # rather than accumulated: sweeps are rare, and a running total
                # that has to stay in step with the position jumps below is a
                # bookkeeping bug waiting to happen.
                mean_volume=sum(float(r["volume"]) for r in rows[: position + 1]) / (position + 1),
            )
        )
        # Continue past the entry bar so a later, independent sweep can be found.
        position += confirm_offset + 2

    if setups:
        return SessionScan(session_date, setups=setups, diagnostics=diagnostics)
    if no_entry_bar:
        return skipped("no_entry_bar_before_flat")
    if diagnostics["unconfirmed_sweeps"]:
        return skipped("unconfirmed_sweep")
    return skipped("no_sweep")


def _classify_sweep(
    bar: Dict[str, Any], asian_high: float, asian_low: float, min_sigma: float
) -> Optional[str]:
    """``"SHORT"``, ``"LONG"`` or None. Requires level AND extremity together."""
    vwap = bar.get("vwap")
    sigma = bar.get("sigma")
    if vwap is None or sigma is None or pd.isna(vwap) or pd.isna(sigma) or sigma <= 0:
        return None

    if bar["high"] > asian_high and bar["high"] >= vwap + min_sigma * sigma:
        return "SHORT"
    if bar["low"] < asian_low and bar["low"] <= vwap - min_sigma * sigma:
        return "LONG"
    return None


def _closes_back_inside(
    bar: Dict[str, Any], direction: str, asian_high: float, asian_low: float
) -> bool:
    vwap, sigma = bar["vwap"], bar["sigma"]
    if direction == "SHORT":
        return bar["close"] < asian_high and bar["close"] < vwap + 2.0 * sigma
    return bar["close"] > asian_low and bar["close"] > vwap - 2.0 * sigma


def _find_confirmation(
    rows: List[Dict[str, Any]],
    sweep_position: int,
    direction: str,
    asian_high: float,
    asian_low: float,
    max_wait_bars: int,
) -> Optional[int]:
    """Offset of the first confirming bar after the sweep, or None.

    Starts at 1, never 0 -- the sweep bar cannot confirm itself.
    """
    for offset in range(1, max_wait_bars + 1):
        index = sweep_position + offset
        if index >= len(rows):
            return None
        if _closes_back_inside(rows[index], direction, asian_high, asian_low):
            return offset
    return None


def _build_setup(
    session_date: date,
    settings: Dict[str, Any],
    sweep: str,
    sweep_bar: Dict[str, Any],
    confirm_bar: Dict[str, Any],
    entry_bar: Dict[str, Any],
    banded: pd.DataFrame,
    asian_high: float,
    asian_low: float,
    asian_range_width: float,
    confirm_offset: int,
    failed_sweeps: int,
    mean_volume: float,
) -> Dict[str, Any]:
    is_short = sweep == "SHORT"
    vwap = float(confirm_bar["vwap"])
    sigma = float(confirm_bar["sigma"])
    sign = 1.0 if is_short else -1.0

    swept_extreme = float(sweep_bar["high"] if is_short else sweep_bar["low"])
    level = asian_high if is_short else asian_low
    entry_price = float(entry_bar["open"])
    confirm_close = float(confirm_bar["close"])

    # Counted from the confirmation bar, so the entry bar itself is included --
    # a gap through the stop on the entry bar is a real and common loss.
    remaining = bars_until_flat(
        banded,
        bar_index=int(confirm_bar["bar_index"]),
        session_start=settings["session_start"],
        flat_by=settings["flat_by"],
    )

    return {
        "session_date": session_date.isoformat(),
        "anchor_policy": settings["anchor_policy"],
        "direction": sweep,
        "swept_level": "asian_high" if is_short else "asian_low",
        "asian_high": asian_high,
        "asian_low": asian_low,
        "asian_range_width": asian_range_width,
        "asian_range_pct": asian_range_width / asian_high,
        "sweep_bar_index": int(sweep_bar["bar_index"]),
        "sweep_time": sweep_bar["ist"].isoformat(),
        "sweep_extreme": swept_extreme,
        "sweep_penetration": abs(swept_extreme - level),
        "sweep_penetration_pct_range": abs(swept_extreme - level) / asian_range_width,
        "sweep_sigma": abs(swept_extreme - float(sweep_bar["vwap"])) / float(sweep_bar["sigma"]),
        "sweep_volume_ratio": float(sweep_bar["volume"]) / mean_volume if mean_volume else 0.0,
        "confirm_bar_index": int(confirm_bar["bar_index"]),
        "confirm_time": confirm_bar["ist"].isoformat(),
        "confirm_close": confirm_close,
        "confirm_high": float(confirm_bar["high"]),
        "confirm_low": float(confirm_bar["low"]),
        "bars_waited": confirm_offset,
        "failed_sweeps_before_entry": failed_sweeps,
        "vwap_at_confirm": vwap,
        "sigma_at_confirm": sigma,
        "sigma_pct_at_confirm": sigma / vwap if vwap else 0.0,
        "band_2": vwap + sign * 2.0 * sigma,
        "band_3": vwap + sign * 3.0 * sigma,
        "entry_bar_index": int(entry_bar["bar_index"]),
        "entry_time": entry_bar["ist"].isoformat(),
        "entry_price": entry_price,
        "entry_sigma": (entry_price - vwap) / sigma if sigma else 0.0,
        # Positive means the honest next-bar-open fill was worse than the
        # confirmation close the source video claims you can get.
        "entry_slip_vs_confirm_close": (
            confirm_close - entry_price if is_short else entry_price - confirm_close
        ),
        "stop_candidates": {
            "confirm": float(confirm_bar["high"] if is_short else confirm_bar["low"]),
            "sweep": swept_extreme,
        },
        "target_candidates": {
            "vwap": vwap,
            "opp_band": vwap - sign * 2.0 * sigma,
        },
        "max_hold_bars": remaining,
        "hour_utc": entry_bar["ist"].hour,
        "day_of_week": entry_bar["ist"].strftime("%a"),
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_extremity_sweep.py -v
```

Expected: PASS, 11 tests.

- [ ] **Step 5: Commit**

```bash
git add strategy/vwap_sweep/extremity_sweep.py tests/test_extremity_sweep.py
git commit -m "feat: detect Asian-level sweeps into the VWAP extremity zone

Records every confirmed sweep in a session, not just the first, so a
tighter cell that rejects the first one can still take the next. The
sweep bar may not confirm itself -- that is the CRT pattern, already
tested and failed, and blending it in would make this result
uninterpretable. Entry is the next bar's open, since a bar is only known
to have qualified once it has closed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: The trade ledger

**Files:**
- Create: `strategy/vwap_sweep/ledger.py`
- Test: `tests/test_vwap_sweep_ledger.py`

The ledger records **gross** outcomes only. That is what makes every cost
scenario post-hoc arithmetic rather than another scan.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_vwap_sweep_ledger.py`:

```python
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.vwap_sweep.ledger import PATH_KEYS, read_ledger, simulate_paths, write_ledger


def _candles():
    return pd.DataFrame(
        {
            "bar_index": [0, 1, 2, 3, 4],
            "open": [100.0, 100.0, 100.0, 100.0, 100.0],
            "high": [100.0, 101.0, 101.0, 101.0, 101.0],
            "low": [100.0, 95.0, 95.0, 95.0, 95.0],
            "close": [100.0, 96.0, 96.0, 96.0, 96.0],
        }
    )


def _setup():
    return {
        "session_date": "2026-01-05",
        "direction": "SHORT",
        "entry_bar_index": 1,
        "confirm_bar_index": 0,
        "entry_price": 100.0,
        "stop_candidates": {"confirm": 102.0, "sweep": 104.0},
        "target_candidates": {"vwap": 97.0, "opp_band": 94.0},
        "max_hold_bars": 4,
    }


def test_every_path_combination_is_simulated():
    paths = simulate_paths(_candles(), _setup())

    assert sorted(paths) == sorted(PATH_KEYS)
    assert len(PATH_KEYS) == 6
    assert paths["confirm|vwap"]["exit_reason"] == "target"
    assert paths["confirm|vwap"]["exit_price"] == 97.0


def test_the_r2_path_derives_its_target_from_entry_and_stop():
    """The source video's "one to two" claim, measured. Information only."""
    paths = simulate_paths(_candles(), _setup())

    # SHORT entry 100, stop 102, so risk 2 and a 2R target at 96.
    assert paths["confirm|r2"]["target_price"] == 96.0
    assert paths["sweep|r2"]["target_price"] == 92.0  # stop 104, risk 4


def test_gross_figures_are_invariant_to_any_fee_input():
    """The whole scan/score split rests on this. If it ever fails, re-scanning
    for every cost scenario becomes mandatory."""
    cheap = simulate_paths(_candles(), _setup(), fee_rate=0.0)
    dear = simulate_paths(_candles(), _setup(), fee_rate=0.05)

    for key in PATH_KEYS:
        assert cheap[key]["gross_pnl"] == dear[key]["gross_pnl"]
        assert cheap[key]["exit_price"] == dear[key]["exit_price"]
        assert cheap[key]["exit_reason"] == dear[key]["exit_reason"]
        assert cheap[key]["exit_bar_index"] == dear[key]["exit_bar_index"]


def test_paths_carry_no_net_figures():
    """Nothing downstream can mistake a cost-free number for a net one."""
    paths = simulate_paths(_candles(), _setup())

    for key in PATH_KEYS:
        assert "net_pnl" not in paths[key]
        assert "net_r" not in paths[key]
        assert "fees" not in paths[key]


def test_a_stop_on_the_wrong_side_yields_a_null_path_not_an_exception():
    setup = _setup()
    setup["stop_candidates"] = {"confirm": 99.0, "sweep": 104.0}  # 99 is below a SHORT entry

    paths = simulate_paths(_candles(), setup)

    assert paths["confirm|vwap"] is None
    assert paths["sweep|vwap"] is not None


def test_write_then_read_round_trips(tmp_path):
    setup = _setup()
    setup["paths"] = simulate_paths(_candles(), setup)
    out = tmp_path / "ledger.json"

    write_ledger(out, meta={"symbol": "BTCUSDT"}, setups=[setup])
    meta, setups = read_ledger(out)

    assert meta["symbol"] == "BTCUSDT"
    assert len(setups) == 1
    assert setups[0]["paths"]["confirm|vwap"]["exit_price"] == 97.0


def test_read_rejects_a_ledger_carrying_net_figures(tmp_path):
    out = tmp_path / "bad.json"
    out.write_text(
        json.dumps(
            {
                "meta": {},
                "setups": [{"paths": {"confirm|vwap": {"gross_pnl": 1.0, "net_pnl": 0.9}}}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="net"):
        read_ledger(out)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_vwap_sweep_ledger.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'strategy.vwap_sweep.ledger'`

- [ ] **Step 3: Write the implementation**

Create `strategy/vwap_sweep/ledger.py`:

```python
"""
The trade ledger: one slow scan, then unlimited cheap scoring.

A trade's exit -- stop, target or forced flat, and on which bar -- depends only
on price levels. Fees are subtracted afterwards. So the ledger records GROSS
outcomes, and net P&L under any cost model is arithmetic over the recorded entry
price, exit price and exit reason. No cost question ever needs another scan.

Net figures are deliberately absent from the file so nothing downstream can read
a cost-free number as a net one. ``read_ledger`` enforces that on load.

Six paths are simulated per setup, one per stop-rule x target-rule combination.
Those two rules DO change the exit, so unlike costs they cannot be derived after
the fact.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from analysis.signal_trade_simulator import CandleSignal, simulate_trade_grid

STOP_RULES = ("confirm", "sweep")

# "r2" is a fixed 2R target rather than a price level. It exists to test the
# source video's "go for a one to two" claim directly, and is reported as
# information only -- never as the verdict.
TARGET_RULES = ("vwap", "opp_band", "r2")
PATH_KEYS = [f"{stop}|{target}" for stop in STOP_RULES for target in TARGET_RULES]

FIXED_R = 2.0


def simulate_paths(
    candles: pd.DataFrame, setup: Dict[str, Any], fee_rate: float = 0.0
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Gross outcome for each stop x target combination.

    ``fee_rate`` exists only so a test can prove the recorded figures do not
    depend on it. Production callers leave it at zero.

    A combination whose stop or target sits on the wrong side of entry yields
    ``None`` rather than raising -- that is a real, countable outcome for one
    rule and not for the others.
    """
    paths: Dict[str, Optional[Dict[str, Any]]] = {}
    for stop_rule in STOP_RULES:
        for target_rule in TARGET_RULES:
            paths[f"{stop_rule}|{target_rule}"] = _simulate_one(
                candles, setup, stop_rule, target_rule, fee_rate
            )
    return paths


def _simulate_one(
    candles: pd.DataFrame,
    setup: Dict[str, Any],
    stop_rule: str,
    target_rule: str,
    fee_rate: float,
) -> Optional[Dict[str, Any]]:
    stop_price = float(setup["stop_candidates"][stop_rule])
    entry_price = float(setup["entry_price"])
    side = setup["direction"]

    if side == "SHORT" and not stop_price > entry_price:
        return None
    if side == "LONG" and not stop_price < entry_price:
        return None

    # A fixed-R target is derived by the simulator from entry and stop, so it is
    # left unset here and cannot sit on the wrong side by construction.
    if target_rule == "r2":
        target_price = None
    else:
        target_price = float(setup["target_candidates"][target_rule])
        if side == "SHORT" and not entry_price > target_price:
            return None
        if side == "LONG" and not entry_price < target_price:
            return None

    signal = CandleSignal(
        bar_index=int(setup["confirm_bar_index"]),
        side=side,
        entry_price=entry_price,
        stop_price=stop_price,
        signal_time=setup.get("confirm_time"),
        max_hold_bars=int(setup["max_hold_bars"]),
        entry_bar_index=int(setup["entry_bar_index"]),
        target_price=target_price,
    )
    result = simulate_trade_grid(
        candles=candles,
        signals=[signal],
        r_values=[FIXED_R],
        max_hold_bars=int(setup["max_hold_bars"]),
        fee_rate=fee_rate,
        slippage_per_side=0.0,
    )
    trade = next(iter(result["best"]["per_signal"].values()))

    return {
        "stop_rule": stop_rule,
        "target_rule": target_rule,
        "entry_price": trade["entry_price"],
        "stop_price": trade["stop_price"],
        "target_price": trade["target_price"],
        "risk_per_unit": trade["risk_per_unit"],
        "exit_bar_index": trade["exit_bar_index"],
        "exit_time": trade["exit_time"],
        "exit_price": trade["exit_price"],
        "exit_reason": trade["exit_reason"],
        "exit_is_maker": trade["exit_is_maker"],
        "bars_held": int(trade["exit_bar_index"]) - int(setup["entry_bar_index"]) + 1,
        "gross_pnl": trade["gross_pnl"],
        "gross_r": round(trade["gross_pnl"] / trade["risk_per_unit"], 6),
        "mfe_r": trade["mfe_r"],
        "mae_r": trade["mae_r"],
    }


_FORBIDDEN_PATH_KEYS = ("net_pnl", "net_r", "fees")


def write_ledger(path: Path, meta: Dict[str, Any], setups: List[Dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"meta": meta, "setups": setups}, indent=2, default=str), encoding="utf-8"
    )


def read_ledger(path: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Load a ledger, refusing one that carries net figures.

    A ledger with net numbers in it was written under some cost assumption that
    is now invisible, which is exactly the confusion this split exists to
    prevent.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    setups = payload.get("setups", [])
    for setup in setups:
        for path_result in (setup.get("paths") or {}).values():
            if not path_result:
                continue
            present = [key for key in _FORBIDDEN_PATH_KEYS if key in path_result]
            if present:
                raise ValueError(
                    f"ledger {path} carries net figures {present} -- it was written under a "
                    "cost assumption that is no longer visible. Re-run the scan."
                )
    return payload.get("meta", {}), setups
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_vwap_sweep_ledger.py -v
```

Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add strategy/vwap_sweep/ledger.py tests/test_vwap_sweep_ledger.py
git commit -m "feat: gross-only trade ledger for the VWAP sweep scan

A trade's exit depends only on price levels; fees are subtracted after.
So the ledger stores gross outcomes and every cost scenario becomes
arithmetic rather than another five-year scan. A test pins that
invariance directly, and read_ledger refuses a file carrying net figures
written under a now-invisible cost assumption.

Stop rule and target rule do change the exit, so all six combinations
are simulated up front, including a fixed 2R target that measures the
source video's stated reward-to-risk against the same entries.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: The scan runner and CLI

**Files:**
- Create: `scripts/run_vwap_sweep_scan.py`
- Test: `tests/test_vwap_sweep_scan.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_vwap_sweep_scan.py`:

```python
import sys
from pathlib import Path

import pandas as pd
import pytest
import pytz

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))

from run_vwap_sweep_scan import scan_bars

UTC = pytz.UTC


def _day(day: str, spike_at: int | None):
    """288 five-minute bars. Optionally one sweep spike plus a confirmation."""
    rows = []
    for i in range(288):
        naive = pd.Timestamp(f"{day} 00:00:00") + pd.Timedelta(minutes=5 * i)
        high, low, close = 101.0, 99.0, 100.0
        if spike_at is not None and i == spike_at:
            high, low, close = 140.0, 100.0, 138.0
        elif spike_at is not None and i == spike_at + 1:
            high, low, close = 139.0, 99.0, 100.0
        rows.append(
            {
                "timestamp": int(UTC.localize(naive.to_pydatetime()).timestamp()),
                "open": close, "high": high, "low": low, "close": close, "volume": 10.0,
            }
        )
    return rows


def test_two_days_scan_end_to_end():
    bars = pd.DataFrame(_day("2026-01-05", 150) + _day("2026-01-06", 150))
    meta, setups = scan_bars(bars, symbol="TEST", interval="5m", source="synthetic")

    daily = [s for s in setups if s["anchor_policy"] == "daily"]
    assert len(daily) == 2
    assert all(s["direction"] == "SHORT" for s in daily)
    assert all(s["paths"]["confirm|vwap"] is not None for s in daily)


def test_both_anchor_policies_are_scanned():
    bars = pd.DataFrame(_day("2026-01-05", 150) + _day("2026-01-06", 150))
    _, setups = scan_bars(bars, symbol="TEST", interval="5m", source="synthetic")

    assert {s["anchor_policy"] for s in setups} == {"daily", "weekly"}


def test_every_session_is_accounted_for():
    bars = pd.DataFrame(_day("2026-01-05", 150) + _day("2026-01-06", None))
    meta, setups = scan_bars(bars, symbol="TEST", interval="5m", source="synthetic")

    accounting = meta["sessions"]["daily"]
    assert accounting["available"] == 2
    assert accounting["with_setup"] == 1
    assert sum(accounting["skip_reasons"].values()) == 1


def test_the_train_test_split_is_recorded():
    bars = pd.DataFrame(_day("2026-01-05", 150) + _day("2026-01-06", 150))
    meta, _ = scan_bars(bars, symbol="TEST", interval="5m", source="synthetic")

    assert meta["train_dates"] == ["2026-01-05"]
    assert meta["test_dates"] == ["2026-01-06"]


def test_empty_bars_raise_rather_than_reporting_zero_trades():
    with pytest.raises(ValueError, match="empty"):
        scan_bars(pd.DataFrame(), symbol="TEST", interval="5m", source="synthetic")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_vwap_sweep_scan.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'run_vwap_sweep_scan'`

- [ ] **Step 3: Write the implementation**

Create `scripts/run_vwap_sweep_scan.py`:

```python
"""
The slow half of the VWAP extremity sweep test: scan once, write a ledger.

Reads the flat history corpus written by scripts/fetch_binance_history.py,
detects every confirmed setup under both anchor policies at the loosest
settings, simulates every stop x target path, and writes a gross-only
ledger. Everything after this -- cost scenarios, filter cells, verdicts,
Navigator reports -- reads that ledger and never touches the candles again.

Usage:
    python scripts/run_vwap_sweep_scan.py --symbol BTCUSDT
    python scripts/run_vwap_sweep_scan.py --symbol ETHUSDT --interval 5m \\
        --run-id 2026-08-12_a
"""

import argparse
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd
import pytz

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.orb.session import add_bar_index, split_dates_in_half, split_sessions
from strategy.vwap_sweep.extremity_sweep import DEFAULTS, find_setups
from strategy.vwap_sweep.ledger import simulate_paths, write_ledger
from strategy.vwap_sweep.vwap_bands import ANCHOR_POLICIES

REPO_ROOT = Path(__file__).resolve().parents[3]
HISTORY_ROOT = REPO_ROOT / "logs" / "backend" / "history"
LEDGER_ROOT = REPO_ROOT / "logs" / "backend" / "vwap_sweep"
RUNS_ROOT = REPO_ROOT / "logs" / "backend" / "runs"
UTC = pytz.UTC


def scan_bars(
    bars: pd.DataFrame, symbol: str, interval: str, source: str
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Scan every session under every anchor policy. Returns (meta, setups)."""
    if bars is None or bars.empty:
        raise ValueError(f"bars for {symbol} are empty -- refusing to report zero trades")

    indexed = add_bar_index(bars)
    sessions = split_sessions(indexed, tz=UTC)
    session_dates = sorted(sessions)
    if len(session_dates) < 2:
        raise ValueError(f"need at least 2 sessions, got {len(session_dates)}")

    candles = indexed[["bar_index", "open", "high", "low", "close"]].copy()
    train_dates, test_dates = split_dates_in_half(session_dates)
    test_set = set(test_dates)

    all_setups: List[Dict[str, Any]] = []
    accounting: Dict[str, Any] = {}

    for policy in ANCHOR_POLICIES:
        reasons: Counter = Counter()
        diagnostics: Counter = Counter()
        with_setup = 0

        for session_date in session_dates:
            scan = find_setups(
                sessions[session_date], {**DEFAULTS, "anchor_policy": policy}
            )
            diagnostics.update(
                {key: value for key, value in scan.diagnostics.items() if key != "session_bars"}
            )
            if scan.reason:
                reasons[scan.reason] += 1
                continue

            with_setup += 1
            for index, setup in enumerate(scan.setups):
                setup["setup_id"] = len(all_setups)
                setup["setup_index_in_session"] = index
                setup["half"] = "test" if session_date in test_set else "train"
                setup["paths"] = simulate_paths(candles, setup)
                all_setups.append(setup)

        accounting[policy] = {
            "available": len(session_dates),
            "with_setup": with_setup,
            "skipped": len(session_dates) - with_setup,
            "skip_reasons": dict(reasons),
            "diagnostics": dict(diagnostics),
        }

    meta = {
        "symbol": symbol,
        "interval": interval,
        "source": source,
        "bars": len(indexed),
        "first_bar": _iso(indexed["timestamp"].iloc[0]),
        "last_bar": _iso(indexed["timestamp"].iloc[-1]),
        "scan_params": {
            key: str(value) for key, value in DEFAULTS.items()
        },
        "sessions": accounting,
        "train_dates": [d.isoformat() for d in train_dates],
        "test_dates": [d.isoformat() for d in test_dates],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "code_version": _git_sha(),
    }
    return meta, all_setups


def _iso(unix_seconds: Any) -> str:
    return datetime.fromtimestamp(int(unix_seconds), tz=timezone.utc).isoformat()


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_ROOT), text=True
        ).strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


def load_history(symbol: str, interval: str) -> pd.DataFrame:
    path = HISTORY_ROOT / symbol / interval / "candles.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"no history corpus at {path}. Fetch it first:\n"
            f"  python scripts/fetch_binance_history.py --symbols {symbol} --intervals {interval}"
        )
    return pd.read_csv(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scan for VWAP extremity sweeps")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--run-id", default=None, help="defaults to YYYY-MM-DD_<git sha>")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    bars = load_history(args.symbol, args.interval)
    print(f"loaded {len(bars):,} bars from {args.symbol}/{args.interval}")

    meta, setups = scan_bars(bars, args.symbol, args.interval, source="binance_history")
    run_id = args.run_id or f"{datetime.now().strftime('%Y-%m-%d')}_{meta['code_version']}"
    meta["run_id"] = run_id

    ledger_path = LEDGER_ROOT / args.symbol / run_id / "ledger.json"
    write_ledger(ledger_path, meta, setups)
    print(f"wrote {len(setups):,} setups to {ledger_path}")

    # The Navigator globs runs/<SYM>/<RES>/<run_id>/ and loads candles.csv from
    # there, so the scan seeds that directory. Resolution is TradingView style.
    resolution = args.interval.rstrip("m") if args.interval.endswith("m") else args.interval
    run_dir = RUNS_ROOT / args.symbol / resolution / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HISTORY_ROOT / args.symbol / args.interval / "candles.csv", run_dir / "candles.csv")
    print(f"seeded Navigator run directory {run_dir}")

    for policy, stats in meta["sessions"].items():
        print(
            f"  {policy}: {stats['with_setup']}/{stats['available']} sessions produced a setup; "
            f"skips {stats['skip_reasons']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_vwap_sweep_scan.py -v
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_vwap_sweep_scan.py tests/test_vwap_sweep_scan.py
git commit -m "feat: VWAP sweep scan CLI writing a gross ledger

Scans both anchor policies at the loosest settings and simulates every
stop x target path per setup. Accounts for every session by reason
rather than dropping empty ones, because a clean report built from
silently skipped days is the failure mode worth guarding.

Seeds the Navigator run directory with the candles so results can be
inspected trade by trade against the chart.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: Placebo holds the target distance fixed

The existing placebo fixes stop distance only. That is enough for a fixed-R
strategy. This one's target is a price level, so a placebo with a random target
distance would compare two different exit geometries and prove nothing.

**Files:**
- Modify: `strategy/orb/placebo.py`
- Test: `tests/test_orb_placebo.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_orb_placebo.py`:

```python
def test_placebo_holds_target_distance_fixed_when_the_real_signal_has_one():
    from analysis.signal_trade_simulator import CandleSignal
    from strategy.orb.placebo import build_placebo_signals
    from strategy.orb.types import OrbSignal

    session = _session([(100.0, 101.0, 99.0, 100.0)] * 20)  # existing fixture helper
    real = [
        OrbSignal.fired(
            date(2026, 8, 4),
            CandleSignal(
                bar_index=5,
                side="SHORT",
                entry_price=100.0,
                stop_price=102.0,
                signal_time="t",
                max_hold_bars=10,
                target_price=97.0,
            ),
        )
    ]
    sessions = {date(2026, 8, 4): session}
    placebos = build_placebo_signals(real, sessions, {"or_minutes": 0}, seed=1)

    assert placebos
    for placebo in placebos:
        stop_distance = abs(placebo.entry_price - placebo.stop_price)
        target_distance = abs(placebo.entry_price - placebo.target_price)
        assert stop_distance == pytest.approx(2.0)
        assert target_distance == pytest.approx(3.0)


def test_placebo_leaves_target_price_unset_when_the_real_signal_has_none():
    from analysis.signal_trade_simulator import CandleSignal
    from strategy.orb.placebo import build_placebo_signals
    from strategy.orb.types import OrbSignal

    session = _session([(100.0, 101.0, 99.0, 100.0)] * 20)
    real = [
        OrbSignal.fired(
            date(2026, 8, 4),
            CandleSignal(
                bar_index=5, side="SHORT", entry_price=100.0, stop_price=102.0,
                signal_time="t", max_hold_bars=10,
            ),
        )
    ]
    placebos = build_placebo_signals(real, {date(2026, 8, 4): session}, {"or_minutes": 0}, seed=1)

    assert placebos
    assert all(placebo.target_price is None for placebo in placebos)
```

Reuse whatever session-building helper `tests/test_orb_placebo.py` already
defines. If it has none, add this one at the top of the file:

```python
def _session(bars):
    """bars: list of (open, high, low, close) tuples, 5-minute from 09:15 IST."""
    import pytz
    from strategy.orb.session import add_bar_index, split_sessions

    ist = pytz.timezone("Asia/Kolkata")
    rows = []
    for i, (o, h, l, c) in enumerate(bars):
        naive = pd.Timestamp("2026-08-04 09:15:00") + pd.Timedelta(minutes=5 * i)
        rows.append(
            {
                "timestamp": int(ist.localize(naive.to_pydatetime()).timestamp()),
                "open": o, "high": h, "low": l, "close": c, "volume": 100.0,
            }
        )
    return split_sessions(add_bar_index(pd.DataFrame(rows)))[date(2026, 8, 4)]
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_orb_placebo.py -k target -v
```

Expected: FAIL — `AttributeError: 'CandleSignal' object has no attribute 'target_price'`
would already be fixed by Task 1, so expect instead
`assert None is not None` or `TypeError: bad operand type for abs(): 'NoneType'`
because the placebo does not copy the target.

- [ ] **Step 3: Copy the target distance**

In `strategy/orb/placebo.py`, inside the loop, after:

```python
        stop_distance = abs(orb_signal.signal.entry_price - orb_signal.signal.stop_price)
```

add:

```python
        # A price-level target must be matched in DISTANCE, not copied as a
        # price -- the placebo enters somewhere else entirely. Without this the
        # placebo would run a different exit geometry and the comparison would
        # measure nothing.
        real_target = orb_signal.signal.target_price
        target_distance = (
            abs(orb_signal.signal.entry_price - real_target) if real_target is not None else None
        )
```

Then replace the `CandleSignal(...)` construction at the end of the loop with:

```python
        if target_distance is None:
            target_price = None
        else:
            target_price = (
                entry_price + target_distance if side == "LONG" else entry_price - target_distance
            )
            if target_price <= 0:
                continue

        placebos.append(
            CandleSignal(
                bar_index=bar_index,
                side=side,
                entry_price=entry_price,
                stop_price=stop_price,
                signal_time=row["ist"].isoformat(),
                max_hold_bars=remaining,
                target_price=target_price,
            )
        )
```

Update the module docstring's first line to:

```python
"""
Matched placebo: same sessions, same stop distance, same target distance, same
holding limit -- only the entry bar and the direction are randomised.
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_orb_placebo.py -v
```

Expected: PASS, including every pre-existing test — signals without a target are
unaffected.

- [ ] **Step 5: Commit**

```bash
git add strategy/orb/placebo.py tests/test_orb_placebo.py
git commit -m "fix: placebo matches target distance, not just stop distance

A price-level target has to be matched by distance because the placebo
enters somewhere else entirely. Copying the price, or leaving it unset,
would give the placebo a different exit geometry and the comparison would
measure nothing. Signals without a target are unaffected.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 9: Scoring — cost models, cells, verdict

**Files:**
- Create: `strategy/vwap_sweep/scoring.py`
- Modify: `strategy/orb/verdict.py` (comment only)
- Test: `tests/test_vwap_sweep_scoring.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_vwap_sweep_scoring.py`:

```python
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.vwap_sweep.scoring import (
    BASE, CELLS, STRESSED, ZERO, CostModel, headline_cell, net_of, select_trades,
)


def _setup(session_date, sweep_sigma=2.5, bars_waited=2, anchor="daily", gross=10.0, setup_id=0):
    return {
        "setup_id": setup_id,
        "session_date": session_date,
        "anchor_policy": anchor,
        "sweep_sigma": sweep_sigma,
        "bars_waited": bars_waited,
        "half": "test",
        "paths": {
            "confirm|vwap": {
                "entry_price": 100.0, "exit_price": 90.0, "exit_is_maker": True,
                "risk_per_unit": 2.0, "gross_pnl": gross, "gross_r": gross / 2.0,
            },
            "confirm|opp_band": {
                "entry_price": 100.0, "exit_price": 85.0, "exit_is_maker": True,
                "risk_per_unit": 2.0, "gross_pnl": gross, "gross_r": gross / 2.0,
            },
            "sweep|vwap": {
                "entry_price": 100.0, "exit_price": 90.0, "exit_is_maker": True,
                "risk_per_unit": 4.0, "gross_pnl": gross, "gross_r": gross / 4.0,
            },
            "sweep|opp_band": None,
        },
    }


def test_zero_cost_reproduces_gross_exactly():
    path = _setup("2026-01-05")["paths"]["confirm|vwap"]
    fees, net_pnl, net_r = net_of(path, ZERO)

    assert fees == 0.0
    assert net_pnl == path["gross_pnl"]
    assert net_r == path["gross_r"]


def test_net_matches_a_hand_computed_cost():
    path = _setup("2026-01-05")["paths"]["confirm|vwap"]
    cost = CostModel(label="test", taker_bps=5.0, maker_bps=3.0)
    fees, net_pnl, net_r = net_of(path, cost)

    # entry 100 at 5bps = 0.05; exit 90 at maker 3bps = 0.027
    assert fees == pytest.approx(0.077)
    assert net_pnl == pytest.approx(10.0 - 0.077)
    assert net_r == pytest.approx((10.0 - 0.077) / 2.0)


def test_a_taker_exit_pays_the_taker_rate():
    path = dict(_setup("2026-01-05")["paths"]["confirm|vwap"])
    path["exit_is_maker"] = False
    fees, _, _ = net_of(path, CostModel(label="t", taker_bps=5.0, maker_bps=3.0))

    assert fees == pytest.approx(0.05 + 90.0 * 0.0005)


def test_one_trade_per_session_the_first_that_passes():
    cell = headline_cell()
    setups = [
        _setup("2026-01-05", setup_id=0),
        _setup("2026-01-05", setup_id=1),
        _setup("2026-01-06", setup_id=2),
    ]
    selected = select_trades(setups, cell)

    assert [s["setup_id"] for s in selected] == [0, 2]


def test_a_cell_that_rejects_the_first_setup_takes_the_next():
    cell = headline_cell()
    setups = [
        _setup("2026-01-05", bars_waited=5, setup_id=0),  # beyond the headline wait of 3
        _setup("2026-01-05", bars_waited=2, setup_id=1),
    ]
    selected = select_trades(setups, cell)

    assert [s["setup_id"] for s in selected] == [1]


def test_the_band_2to3_cell_excludes_a_deeper_sweep():
    cell = next(c for c in CELLS if c["label"] == "band=2to3")
    setups = [_setup("2026-01-05", sweep_sigma=3.5, setup_id=0), _setup("2026-01-05", sweep_sigma=2.5, setup_id=1)]
    selected = select_trades(setups, cell)

    assert [s["setup_id"] for s in selected] == [1]


def test_cells_filter_by_anchor_policy():
    cell = next(c for c in CELLS if c["label"] == "anchor=weekly")
    setups = [_setup("2026-01-05", anchor="daily", setup_id=0), _setup("2026-01-05", anchor="weekly", setup_id=1)]
    selected = select_trades(setups, cell)

    assert [s["setup_id"] for s in selected] == [1]


def test_a_setup_whose_path_is_null_for_this_cell_is_not_selected():
    cell = next(c for c in CELLS if c["label"] == "stop=sweep" and c["target_rule"] == "vwap")
    setup = _setup("2026-01-05", setup_id=0)
    setup["paths"]["sweep|vwap"] = None

    assert select_trades([setup], cell) == []


def test_the_grid_declares_exactly_one_headline():
    assert sum(1 for cell in CELLS if cell["is_headline"]) == 1


def test_base_and_stressed_costs_are_the_declared_values():
    assert (BASE.taker_bps, BASE.maker_bps) == (5.0, 3.0)
    assert (STRESSED.taker_bps, STRESSED.maker_bps) == (10.0, 6.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_vwap_sweep_scoring.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'strategy.vwap_sweep.scoring'`

- [ ] **Step 3: Write the implementation**

Create `strategy/vwap_sweep/scoring.py`:

```python
"""
Score a ledger. Instant, and repeatable as many times as you like.

Costs are expressed as a RATE ON NOTIONAL, in basis points per side, not as
absolute price points. The existing slippage_per_side is in price units
calibrated for NIFTY around 24,000; BTC traded from ~46,000 to over 100,000
across this window, so no fixed figure is meaningful at both ends. Fees and
slippage in basis points have identical algebraic form, so folding them into
one rate loses nothing.

A target exit is a resting limit order and pays the maker rate. A stop or a
forced flat is a market order and pays taker.

The headline metric is average net R, not net P&L. A dollar figure pools a 2021
BTC trade with a 2026 one of the same quality and reports them as wildly
different, which would corrupt both the half-split and the placebo.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from strategy.orb.verdict import CellResult, decide_verdict


@dataclass(frozen=True)
class CostModel:
    """Cost as a rate on notional, in basis points per side."""

    label: str
    taker_bps: float
    maker_bps: float


ZERO = CostModel(label="zero", taker_bps=0.0, maker_bps=0.0)
BASE = CostModel(label="base", taker_bps=5.0, maker_bps=3.0)
STRESSED = CostModel(label="stressed", taker_bps=10.0, maker_bps=6.0)

# Taker rate per side; maker is held two basis points cheaper, floored at zero.
COST_SWEEP_BPS: List[float] = [0.0, 1.0, 2.0, 4.0, 6.0, 8.0, 10.0, 15.0]


def sweep_cost(taker_bps: float) -> CostModel:
    return CostModel(
        label=f"{taker_bps}bps", taker_bps=taker_bps, maker_bps=max(taker_bps - 2.0, 0.0)
    )


def net_of(path: Dict[str, Any], cost: CostModel) -> Tuple[float, float, float]:
    """(fees, net_pnl, net_r) for one gross path under one cost model.

    This is the whole reason the scan and the score are separate: a trade's exit
    does not depend on cost, so this is arithmetic, not simulation.
    """
    exit_bps = cost.maker_bps if path.get("exit_is_maker") else cost.taker_bps
    fees = path["entry_price"] * cost.taker_bps / 10_000.0 + path["exit_price"] * exit_bps / 10_000.0
    net_pnl = path["gross_pnl"] - fees
    return round(fees, 8), round(net_pnl, 8), round(net_pnl / path["risk_per_unit"], 8)


# Declared before any code ran. See the spec's "Robustness grid" section.
# One knob is moved off the headline per cell; this is not a sweep and no
# winner is selected from it.
CELLS: List[Dict[str, Any]] = [
    {"label": "headline", "is_headline": True, "anchor": "daily",
     "max_bars_waited": 3, "sigma_range": (2.0, None), "stop_rule": "confirm", "target_rule": "vwap"},
    {"label": "wait=1", "is_headline": False, "anchor": "daily",
     "max_bars_waited": 1, "sigma_range": (2.0, None), "stop_rule": "confirm", "target_rule": "vwap"},
    {"label": "wait=6", "is_headline": False, "anchor": "daily",
     "max_bars_waited": 6, "sigma_range": (2.0, None), "stop_rule": "confirm", "target_rule": "vwap"},
    {"label": "band=2to3", "is_headline": False, "anchor": "daily",
     "max_bars_waited": 3, "sigma_range": (2.0, 3.0), "stop_rule": "confirm", "target_rule": "vwap"},
    {"label": "anchor=weekly", "is_headline": False, "anchor": "weekly",
     "max_bars_waited": 3, "sigma_range": (2.0, None), "stop_rule": "confirm", "target_rule": "vwap"},
    {"label": "stop=sweep", "is_headline": False, "anchor": "daily",
     "max_bars_waited": 3, "sigma_range": (2.0, None), "stop_rule": "sweep", "target_rule": "vwap"},
    {"label": "target=oppband", "is_headline": False, "anchor": "daily",
     "max_bars_waited": 3, "sigma_range": (2.0, None), "stop_rule": "confirm", "target_rule": "opp_band"},
]


def headline_cell() -> Dict[str, Any]:
    return next(cell for cell in CELLS if cell["is_headline"])


def path_key(cell: Dict[str, Any]) -> str:
    return f"{cell['stop_rule']}|{cell['target_rule']}"


def passes(setup: Dict[str, Any], cell: Dict[str, Any]) -> bool:
    if setup["anchor_policy"] != cell["anchor"]:
        return False
    if setup["bars_waited"] > cell["max_bars_waited"]:
        return False
    low, high = cell["sigma_range"]
    if setup["sweep_sigma"] < low:
        return False
    if high is not None and setup["sweep_sigma"] > high:
        return False
    return (setup.get("paths") or {}).get(path_key(cell)) is not None


def select_trades(setups: List[Dict[str, Any]], cell: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One trade per session: the first setup that passes this cell's filters.

    Setups must arrive in chronological order, which the scan guarantees. A cell
    that rejects a session's first setup takes the next one, which is what a
    person running that rule would have done.
    """
    taken: List[Dict[str, Any]] = []
    seen = set()
    for setup in setups:
        session_date = setup["session_date"]
        if session_date in seen or not passes(setup, cell):
            continue
        seen.add(session_date)
        taken.append(setup)
    return taken


def score_cell(
    setups: List[Dict[str, Any]], cell: Dict[str, Any], cost: CostModel
) -> Dict[str, Any]:
    """Average net R for one cell under one cost model, split by half."""
    key = path_key(cell)
    trades = select_trades(setups, cell)

    by_half: Dict[str, List[float]] = {"train": [], "test": []}
    for setup in trades:
        _, _, net_r = net_of(setup["paths"][key], cost)
        by_half[setup["half"]].append(net_r)

    return {
        "label": cell["label"],
        "is_headline": cell["is_headline"],
        "n_trades_test": len(by_half["test"]),
        "n_trades_train": len(by_half["train"]),
        "avg_net_r_test": _mean(by_half["test"]),
        "avg_net_r_train": _mean(by_half["train"]),
        "trades": trades,
    }


def _mean(values: List[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


def cell_results(setups: List[Dict[str, Any]]) -> List[CellResult]:
    """Feed the frozen verdict rule.

    ``CellResult``'s fields are named ``avg_net_pnl_*``. They carry average net
    R here; the report states the metric explicitly. The fields are not renamed
    because ``decide_verdict`` is shared with ORB and CRT and renaming its
    fields to satisfy a naming preference would risk a validated harness for no
    behavioural gain.
    """
    results = []
    for cell in CELLS:
        base = score_cell(setups, cell, BASE)
        stressed = score_cell(setups, cell, STRESSED)
        results.append(
            CellResult(
                label=cell["label"],
                is_headline=cell["is_headline"],
                n_trades_test=base["n_trades_test"],
                avg_net_pnl_test_base=base["avg_net_r_test"],
                avg_net_pnl_test_stressed=stressed["avg_net_r_test"],
                avg_net_pnl_train_base=base["avg_net_r_train"],
            )
        )
    return results


def verdict(
    setups: List[Dict[str, Any]], placebo_percentile: Optional[float], data_source: str
) -> Tuple[str, List[str]]:
    return decide_verdict(
        cells=cell_results(setups),
        placebo_percentile=placebo_percentile,
        data_source=data_source,
    )
```

- [ ] **Step 4: Add the clarifying comment to the shared verdict module**

In `strategy/orb/verdict.py`, replace the `CellResult` docstring with:

```python
    """One point in the robustness grid, already simulated.

    The ``avg_net_pnl_*`` fields carry whichever performance metric the caller
    chose. ORB and CRT pass average net P&L in index points; the VWAP sweep
    passes average net R, because a dollar figure is not comparable across BTC
    at 46,000 and BTC at 100,000. Every report states its own metric.
    """
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/test_vwap_sweep_scoring.py tests/test_orb_verdict.py -v
```

Expected: PASS, 10 new tests plus every pre-existing verdict test.

- [ ] **Step 6: Commit**

```bash
git add strategy/vwap_sweep/scoring.py strategy/orb/verdict.py tests/test_vwap_sweep_scoring.py
git commit -m "feat: score a VWAP sweep ledger against the frozen verdict rule

Cost is a rate on notional in basis points, not absolute price points --
the existing slippage units were calibrated for NIFTY around 24,000 and
mean nothing across BTC from 46,000 to over 100,000.

Headline metric is average net R for the same reason. Reuses the ORB
verdict rule unchanged; records in its docstring that its metric fields
carry whatever the caller chose.

Cells select the first setup per session that passes their filters, so a
cell rejecting the first one still takes the next -- which is what
running that rule would actually have done.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 10: Navigator report

**Files:**
- Create: `strategy/vwap_sweep/navigator_report.py`
- Test: `tests/test_vwap_sweep_navigator_report.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_vwap_sweep_navigator_report.py`:

```python
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.vwap_sweep.navigator_report import COLUMNS, build_report
from strategy.vwap_sweep.scoring import BASE, headline_cell


def _setup(session_date, setup_id, bars_waited=2, sweep_sigma=2.5):
    return {
        "setup_id": setup_id,
        "session_date": session_date,
        "anchor_policy": "daily",
        "direction": "SHORT",
        "sweep_sigma": sweep_sigma,
        "bars_waited": bars_waited,
        "half": "test",
        "entry_bar_index": 10,
        "entry_time": "2026-01-05T12:00:00+00:00",
        "entry_price": 100.0,
        "confirm_close": 99.0,
        "vwap_at_confirm": 95.0,
        "sigma_at_confirm": 2.0,
        "paths": {
            "confirm|vwap": {
                "entry_price": 100.0, "exit_price": 95.0, "exit_is_maker": True,
                "risk_per_unit": 2.0, "gross_pnl": 5.0, "gross_r": 2.5,
                "stop_price": 102.0, "target_price": 95.0, "exit_reason": "target",
                "exit_bar_index": 14, "exit_time": "2026-01-05T12:20:00+00:00",
                "bars_held": 5, "mfe_r": 2.5, "mae_r": -0.2,
            }
        },
    }


def test_report_declares_its_columns():
    report = build_report({"symbol": "BTCUSDT"}, [_setup("2026-01-05", 0)], headline_cell(), BASE)

    assert report["columns"] == COLUMNS
    assert all({"key", "label", "format"} <= set(column) for column in COLUMNS)


def test_taken_setups_are_live_and_excluded_ones_are_retro():
    setups = [
        _setup("2026-01-05", 0, bars_waited=5),  # beyond the headline wait of 3
        _setup("2026-01-05", 1),
        _setup("2026-01-06", 2),
    ]
    report = build_report({"symbol": "BTCUSDT"}, setups, headline_cell(), BASE)

    assert [e["setup_id"] for e in report["live_events"]] == [1, 2]
    assert [e["setup_id"] for e in report["retro_events"]] == [0]


def test_every_retro_event_says_why_it_was_excluded():
    setups = [_setup("2026-01-05", 0, bars_waited=5), _setup("2026-01-06", 1, sweep_sigma=1.0)]
    report = build_report({"symbol": "BTCUSDT"}, setups, headline_cell(), BASE)

    reasons = {e["setup_id"]: e["excluded_by"] for e in report["retro_events"]}
    assert reasons[0] == "bars_waited"
    assert reasons[1] == "sweep_sigma"


def test_live_events_carry_net_figures_and_derived_columns():
    report = build_report({"symbol": "BTCUSDT"}, [_setup("2026-01-05", 0)], headline_cell(), BASE)
    event = report["live_events"][0]

    assert event["net_pnl"] < event["gross_pnl"]      # fees were charged
    assert event["planned_rr"] == 2.5                 # |95 - 100| / |102 - 100|
    assert event["target_distance_bps"] == 500.0      # 5 / 100 in bps
    assert event["outcome"] == "WIN"
    assert event["bar_index"] == event["entry_bar_index"]


def test_metadata_reports_the_metric_and_the_cost_model():
    report = build_report({"symbol": "BTCUSDT"}, [_setup("2026-01-05", 0)], headline_cell(), BASE)

    assert report["metadata"]["metric"] == "net_r"
    assert report["metadata"]["cost_scenario"] == "base"
    assert report["metadata"]["cell"] == "headline"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_vwap_sweep_navigator_report.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'strategy.vwap_sweep.navigator_report'`

- [ ] **Step 3: Write the implementation**

Create `strategy/vwap_sweep/navigator_report.py`:

```python
"""
Hypothesis Navigator report for one scored cell.

The envelope matches every other report in the repo -- metadata, live_events,
retro_events -- plus a ``columns`` list. The Navigator's table hardcoded two
column sets before this; a report that declares its own columns renders them
directly, and reports without the key keep the old behaviour.

live_events are the trades this cell took. retro_events are setups the scan
found but this cell's filters excluded, each carrying ``excluded_by``. They
render orange so near-misses can be inspected on the chart, which is the first
thing worth looking at when a result is marginal.
"""

from typing import Any, Dict, List

from strategy.vwap_sweep.scoring import CostModel, net_of, passes, path_key, select_trades

COLUMNS: List[Dict[str, Any]] = [
    {"key": "datetime", "label": "Entry", "format": "text"},
    {"key": "direction", "label": "Dir", "format": "side"},
    {"key": "swept_level", "label": "Swept", "format": "text"},
    {"key": "sweep_sigma", "label": "Sweep σ", "format": "number:2"},
    {"key": "bars_waited", "label": "Waited", "format": "integer"},
    {"key": "entry_price", "label": "Entry", "format": "number:2"},
    {"key": "stop_price", "label": "Stop", "format": "number:2"},
    {"key": "target_price", "label": "Target", "format": "number:2"},
    {"key": "planned_rr", "label": "Planned R:R", "format": "number:2"},
    {"key": "target_distance_bps", "label": "Target bps", "format": "number:1"},
    {"key": "entry_slip_vs_confirm_close", "label": "Fill slip", "format": "number:2"},
    {"key": "exit_price", "label": "Exit", "format": "number:2"},
    {"key": "exit_reason", "label": "Why out", "format": "text"},
    {"key": "bars_held", "label": "Bars", "format": "integer"},
    {"key": "net_r", "label": "Net R", "format": "signed:2"},
    {"key": "net_pnl", "label": "Net", "format": "signed:2"},
    {"key": "mfe_r", "label": "MFE R", "format": "number:2"},
    {"key": "mae_r", "label": "MAE R", "format": "number:2"},
    {"key": "outcome", "label": "Outcome", "format": "outcome"},
    {"key": "hour_utc", "label": "Hour", "format": "integer"},
    {"key": "half", "label": "Half", "format": "text"},
    {"key": "excluded_by", "label": "Excluded by", "format": "text"},
]


def build_report(
    meta: Dict[str, Any], setups: List[Dict[str, Any]], cell: Dict[str, Any], cost: CostModel
) -> Dict[str, Any]:
    """One Navigator report for one cell under one cost model."""
    key = path_key(cell)
    taken = select_trades(setups, cell)
    taken_ids = {setup["setup_id"] for setup in taken}

    live = [_event(setup, key, cost) for setup in taken]
    retro = [
        {**_event(setup, key, cost, allow_missing_path=True), "excluded_by": _excluded_by(setup, cell)}
        for setup in setups
        if setup["setup_id"] not in taken_ids
    ]

    wins = sum(1 for event in live if event["outcome"] == "WIN")
    return {
        "metadata": {
            "symbol": meta.get("symbol"),
            "timeframe": meta.get("interval"),
            "start_date": meta.get("first_bar"),
            "end_date": meta.get("last_bar"),
            "cell": cell["label"],
            "cost_scenario": cost.label,
            "metric": "net_r",
            "total_events": len(live),
            "win_rate": round(wins / len(live), 4) if live else 0.0,
            "live_sample_size": len(live),
            "retro_sample_size": len(retro),
        },
        "columns": COLUMNS,
        "live_events": live,
        "retro_events": retro,
    }


def _excluded_by(setup: Dict[str, Any], cell: Dict[str, Any]) -> str:
    """The first filter this setup failed, or ``not_first_of_session``."""
    if setup["anchor_policy"] != cell["anchor"]:
        return "anchor_policy"
    if setup["bars_waited"] > cell["max_bars_waited"]:
        return "bars_waited"
    low, high = cell["sigma_range"]
    if setup["sweep_sigma"] < low or (high is not None and setup["sweep_sigma"] > high):
        return "sweep_sigma"
    if (setup.get("paths") or {}).get(path_key(cell)) is None:
        return "no_valid_path"
    return "not_first_of_session"


def _event(
    setup: Dict[str, Any], key: str, cost: CostModel, allow_missing_path: bool = False
) -> Dict[str, Any]:
    path = (setup.get("paths") or {}).get(key)
    event = {
        column_key: setup.get(column_key)
        for column_key in (
            "setup_id", "session_date", "anchor_policy", "direction", "swept_level",
            "asian_high", "asian_low", "asian_range_width", "asian_range_pct",
            "sweep_bar_index", "sweep_time", "sweep_penetration",
            "sweep_penetration_pct_range", "sweep_sigma", "sweep_volume_ratio",
            "confirm_bar_index", "confirm_time", "bars_waited",
            "failed_sweeps_before_entry", "vwap_at_confirm", "sigma_at_confirm",
            "sigma_pct_at_confirm", "band_2", "band_3", "entry_bar_index",
            "entry_time", "entry_price", "entry_sigma",
            "entry_slip_vs_confirm_close", "hour_utc", "day_of_week", "half",
        )
    }
    # The Navigator jumps the chart using these three, which name the ENTRY bar.
    event["type"] = "VWAP_EXTREMITY_SWEEP"
    event["bar_index"] = setup.get("entry_bar_index")
    event["time"] = setup.get("entry_time")
    event["datetime"] = setup.get("entry_time")
    event["cost_scenario"] = cost.label

    if path is None:
        if not allow_missing_path:
            raise ValueError(f"setup {setup['setup_id']} has no simulated path for {key}")
        return event

    fees, net_pnl, net_r = net_of(path, cost)
    risk = abs(path["target_price"] - path["entry_price"])
    event.update(
        {
            "stop_rule": path["stop_rule"],
            "target_rule": path["target_rule"],
            "stop_price": path["stop_price"],
            "target_price": path["target_price"],
            "risk_per_unit": path["risk_per_unit"],
            "planned_rr": round(risk / path["risk_per_unit"], 6),
            "target_distance_bps": round(10_000.0 * risk / path["entry_price"], 4),
            "exit_bar_index": path["exit_bar_index"],
            "exit_time": path["exit_time"],
            "exit_price": path["exit_price"],
            "exit_reason": path["exit_reason"],
            "bars_held": path["bars_held"],
            "gross_pnl": path["gross_pnl"],
            "fees": fees,
            "net_pnl": net_pnl,
            "net_r": net_r,
            "mfe_r": path["mfe_r"],
            "mae_r": path["mae_r"],
            "outcome": "WIN" if net_pnl > 0 else "LOSS" if net_pnl < 0 else "BREAKEVEN",
        }
    )
    return event
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_vwap_sweep_navigator_report.py -v
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add strategy/vwap_sweep/navigator_report.py tests/test_vwap_sweep_navigator_report.py
git commit -m "feat: Navigator report declaring its own columns

Setups a cell filtered out become retro events carrying the name of the
filter that rejected them, so near-misses can be inspected on the chart
rather than vanishing from the record.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 11: The scoring CLI and verdict report

**Files:**
- Create: `scripts/score_vwap_sweep.py`
- Test: `tests/test_vwap_sweep_scoring_cli.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_vwap_sweep_scoring_cli.py`:

```python
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))

from score_vwap_sweep import render_report, score_ledger


def _setup(session_date, setup_id, half, gross=5.0):
    return {
        "setup_id": setup_id,
        "session_date": session_date,
        "anchor_policy": "daily",
        "direction": "SHORT",
        "sweep_sigma": 2.5,
        "bars_waited": 2,
        "half": half,
        "entry_bar_index": 10,
        "entry_time": f"{session_date}T12:00:00+00:00",
        "entry_price": 100.0,
        "paths": {
            key: {
                "stop_rule": key.split("|")[0], "target_rule": key.split("|")[1],
                "entry_price": 100.0, "exit_price": 95.0, "exit_is_maker": True,
                "risk_per_unit": 2.0, "gross_pnl": gross, "gross_r": gross / 2.0,
                "stop_price": 102.0, "target_price": 95.0, "exit_reason": "target",
                "exit_bar_index": 14, "exit_time": f"{session_date}T12:20:00+00:00",
                "bars_held": 5, "mfe_r": 2.5, "mae_r": -0.2,
            }
            for key in (
                "confirm|vwap", "confirm|opp_band", "confirm|r2",
                "sweep|vwap", "sweep|opp_band", "sweep|r2",
            )
        },
    }


def _ledger(n=80, placebo_averages=None):
    setups = []
    for i in range(n):
        day = f"2026-01-{(i % 28) + 1:02d}"
        setups.append(_setup(f"{day}-{i}", i, "train" if i < n // 2 else "test"))
    meta = {
        "symbol": "TEST", "interval": "5m", "source": "binance_history",
        "placebo": {"seeds_used": 3, "averages": placebo_averages or [-1.0, -0.5, 0.0]},
    }
    return meta, setups


def test_scoring_produces_every_cell_and_a_verdict():
    meta, setups = _ledger()
    report = score_ledger(meta, setups)

    assert len(report["cells"]) == 7
    assert report["verdict"] in {"PASS", "FRAGILE", "FAIL", "INCONCLUSIVE"}
    assert report["metric"] == "net_r"


def test_all_three_named_cost_scenarios_are_reported():
    meta, setups = _ledger()
    report = score_ledger(meta, setups)

    assert set(report["scenarios"]) == {"zero", "base", "stressed"}


def test_a_missing_placebo_forces_inconclusive_rather_than_a_pass():
    meta, setups = _ledger()
    meta["placebo"] = {"seeds_used": 0, "averages": []}
    report = score_ledger(meta, setups)

    assert report["verdict"] == "INCONCLUSIVE"


def test_a_losing_ledger_is_reported_as_losing():
    """Sign regression. Guards against an error making everything look profitable."""
    meta, setups = _ledger()
    for setup in setups:
        for path in setup["paths"].values():
            path["gross_pnl"] = -5.0
            path["gross_r"] = -2.5
            path["exit_reason"] = "stop_loss"
            path["exit_is_maker"] = False

    report = score_ledger(meta, setups)
    headline = next(cell for cell in report["cells"] if cell["is_headline"])

    assert headline["avg_net_r_test"] < 0
    assert report["verdict"] == "FAIL"


def test_the_breakeven_cost_rate_is_reported():
    meta, setups = _ledger()
    report = score_ledger(meta, setups)

    assert "breakeven_cost_bps" in report
    assert isinstance(report["breakeven_cost_bps"], float)


def test_the_fixed_r_comparison_is_reported_separately():
    meta, setups = _ledger()
    report = score_ledger(meta, setups)

    assert "info_only_fixed_r2_test" in report


def test_the_rendered_report_states_its_metric_and_verdict():
    meta, setups = _ledger()
    text = render_report(score_ledger(meta, setups))

    assert "VERDICT" in text
    assert "average net R" in text
    assert "Breakeven cost rate" in text
    assert "not the verdict" in text
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_vwap_sweep_scoring_cli.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'score_vwap_sweep'`

- [ ] **Step 3: Write the implementation**

Create `scripts/score_vwap_sweep.py`:

```python
"""
The fast half: read a ledger, produce verdicts and Navigator reports.

Runs in seconds. Every cost scenario and every filter cell is arithmetic over
the gross figures the scan already recorded, so this can be re-run as often as
you like without touching the candles.

Usage:
    python scripts/score_vwap_sweep.py --ledger logs/backend/vwap_sweep/BTCUSDT/<run>/ledger.json
    python scripts/score_vwap_sweep.py --ledger <path> --out reports/vwap_sweep_btc.md
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.orb.costs import breakeven_slippage
from strategy.vwap_sweep.ledger import read_ledger
from strategy.vwap_sweep.navigator_report import build_report
from strategy.vwap_sweep.scoring import (
    BASE, CELLS, COST_SWEEP_BPS, STRESSED, ZERO, headline_cell, path_key,
    score_cell, sweep_cost, verdict,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNS_ROOT = REPO_ROOT / "logs" / "backend" / "runs"
SCENARIOS = (ZERO, BASE, STRESSED)


def score_ledger(meta: Dict[str, Any], setups: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Every cell, every named scenario, the cost sweep and the verdict.

    Takes no seed count. The placebo distribution is fixed at scan time, because
    it needs the candles; accepting a seed count here would imply it could be
    changed without a re-scan, which it cannot.
    """
    headline = headline_cell()

    cells = []
    for cell in CELLS:
        base = score_cell(setups, cell, BASE)
        stressed = score_cell(setups, cell, STRESSED)
        zero = score_cell(setups, cell, ZERO)
        cells.append(
            {
                "label": cell["label"],
                "is_headline": cell["is_headline"],
                "n_trades_test": base["n_trades_test"],
                "n_trades_train": base["n_trades_train"],
                "avg_net_r_test": base["avg_net_r_test"],
                "avg_net_r_test_stressed": stressed["avg_net_r_test"],
                "avg_net_r_test_zero": zero["avg_net_r_test"],
                "avg_net_r_train": base["avg_net_r_train"],
            }
        )

    sweep = {
        bps: score_cell(setups, headline, sweep_cost(bps))["avg_net_r_test"]
        for bps in COST_SWEEP_BPS
    }

    percentile = _placebo_percentile(meta, setups, headline)
    decision, reasons = verdict(setups, percentile, meta.get("source", "unknown"))

    # Same entries and stops as the headline, but exiting at a fixed 2R instead
    # of at VWAP. This is the source video's "one to two" claim, measured.
    fixed_r_cell = {**headline, "target_rule": "r2"}
    info_only = score_cell(setups, fixed_r_cell, BASE)

    key = path_key(headline)
    planned_rr = sorted(
        abs(path["target_price"] - path["entry_price"]) / path["risk_per_unit"]
        for path in (setup["paths"][key] for setup in score_cell(setups, headline, BASE)["trades"])
    )

    return {
        "meta": meta,
        "metric": "net_r",
        "cells": cells,
        "scenarios": {scenario.label: scenario.taker_bps for scenario in SCENARIOS},
        "cost_sweep_bps": sweep,
        "breakeven_cost_bps": breakeven_slippage(sweep),
        "placebo_percentile": percentile,
        "placebo_stats": meta.get("placebo") or {},
        "info_only_fixed_r2_test": info_only["avg_net_r_test"],
        "planned_rr_median": round(planned_rr[len(planned_rr) // 2], 3) if planned_rr else 0.0,
        "verdict": decision,
        "verdict_reasons": reasons,
    }


def _placebo_percentile(
    meta: Dict[str, Any], setups: List[Dict[str, Any]], cell: Dict[str, Any]
) -> Optional[float]:
    """Rank the real result against the distribution the scan recorded.

    None when the scan recorded no usable distribution, which forces
    INCONCLUSIVE rather than quietly passing an untested result.
    """
    from strategy.orb.placebo import placebo_percentile

    averages = (meta.get("placebo") or {}).get("averages") or []
    if not averages:
        return None
    return placebo_percentile(score_cell(setups, cell, BASE)["avg_net_r_test"], averages)


def render_report(report: Dict[str, Any]) -> str:
    meta = report["meta"]
    lines: List[str] = []
    lines.append(f"# VWAP Extremity Sweep — {meta.get('symbol')} {meta.get('interval')}")
    lines.append("")
    lines.append(f"## VERDICT: {report['verdict']}")
    lines.append("")
    for reason in report["verdict_reasons"]:
        lines.append(f"- {reason}")
    lines.append("")
    lines.append(
        "Headline metric is **average net R per trade**, second half. Not a dollar "
        "figure — BTC ran from roughly 46,000 to over 100,000 across this window, so "
        "dollars are not comparable between its ends."
    )
    lines.append("")
    lines.append(f"**Breakeven cost rate: {report['breakeven_cost_bps']} bps per side.**")
    lines.append("")
    lines.append(
        "Compare against Binance USD-M futures reality, roughly 4 bps taker and 2 bps "
        "maker. This is the number that judges margin."
    )
    lines.append("")

    lines.append("## Sessions")
    lines.append("")
    for policy, stats in (meta.get("sessions") or {}).items():
        lines.append(
            f"- **{policy}**: {stats['with_setup']}/{stats['available']} sessions produced a setup"
        )
        for reason, count in sorted(stats["skip_reasons"].items()):
            lines.append(f"    - {reason}: {count}")
    lines.append("")

    lines.append("## Robustness grid (second half, average net R)")
    lines.append("")
    lines.append("| Cell | Headline | Trades | Zero cost | Base | 2x cost | First half |")
    lines.append("|---|---|---|---|---|---|---|")
    for cell in report["cells"]:
        lines.append(
            f"| {cell['label']} | {'yes' if cell['is_headline'] else ''} "
            f"| {cell['n_trades_test']} | {cell['avg_net_r_test_zero']} "
            f"| {cell['avg_net_r_test']} | {cell['avg_net_r_test_stressed']} "
            f"| {cell['avg_net_r_train']} |"
        )
    lines.append("")
    lines.append(
        "The zero-cost column is **context, not a pass criterion**. It separates "
        "*no edge* from *edge eaten by fees*. It cannot be traded on Binance."
    )
    lines.append("")

    lines.append("## Cost sweep (second half, headline cell)")
    lines.append("")
    lines.append("| Taker bps per side | Avg net R |")
    lines.append("|---|---|")
    for bps in sorted(report["cost_sweep_bps"]):
        lines.append(f"| {bps} | {report['cost_sweep_bps'][bps]} |")
    lines.append("")

    lines.append("## The source's claim")
    lines.append("")
    lines.append(
        f"Median planned reward-to-risk: **{report['planned_rr_median']}**. "
        "The source video claims to \"go for a one to two, one to three\"."
    )
    lines.append("")
    lines.append(
        f"Same entries and stops, exiting at a fixed 2R instead of at VWAP: "
        f"**{report['info_only_fixed_r2_test']}** average net R, second half, base costs. "
        "Reported for information, **not the verdict**."
    )
    lines.append("")

    lines.append("## Placebo")
    lines.append("")
    stats = report["placebo_stats"]
    if report["placebo_percentile"] is None:
        lines.append(
            "Placebo did not run, so the verdict is forced to INCONCLUSIVE regardless "
            "of the numbers above."
        )
    else:
        lines.append(
            f"Real result beat {report['placebo_percentile']}% of {stats.get('seeds_used')} "
            "random-entry runs, holding stop distance, target distance and holding period "
            "fixed. The pass bar is 95."
        )
        full = stats.get("full_strength_seeds") or 0
        used = stats.get("seeds_used") or 0
        lines.append("")
        lines.append(
            f"{full}/{used} seeds were full strength, reproducing all "
            f"{stats.get('real_signal_count')} real signals; the thinnest had "
            f"{stats.get('min_placebo_signals_in_a_seed')}."
        )
        if used and full / used < 0.5:
            lines.append("")
            lines.append(
                "> **Caution:** fewer than half of placebo seeds were full strength, so "
                "the comparison distribution is built from a degraded sample."
            )
    lines.append("")

    lines.append("## Assumptions")
    lines.append("")
    lines.append(
        "- Costs are a rate on notional: base 5 bps taker in, 3 bps maker out on a "
        "target exit. An **estimate** of Binance USD-M futures fees plus a basis point "
        "of slippage, not a measured figure."
    )
    lines.append(
        "- Entry fills at the bar OPEN after the confirmation bar. The source video "
        "says to enter at the confirmation candle's close, which is not knowable in "
        "time to trade. See the `entry_slip_vs_confirm_close` column for the per-trade "
        "difference."
    )
    lines.append(
        "- Gap-through-stop fills use the exact stop price, which is optimistic. A "
        "strategy that fails under this flattering assumption definitely fails."
    )
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Score a VWAP sweep ledger")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--out", default=None, help="Write the verdict report here as markdown")
    parser.add_argument(
        "--navigator", action="store_true", help="Also write a Navigator report per cell"
    )
    # There is deliberately no --placebo-seeds. The placebo needs the candles,
    # so it runs at scan time; offering the flag here would imply it could be
    # changed without a re-scan.
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    meta, setups = read_ledger(Path(args.ledger))
    report = score_ledger(meta, setups)

    text = render_report(report)
    print(text)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"\nWritten to {out_path}")

    if args.navigator:
        resolution = str(meta.get("interval", "5")).rstrip("m")
        run_dir = RUNS_ROOT / meta["symbol"] / resolution / meta["run_id"] / "hypothesis_reports" / "000000"
        run_dir.mkdir(parents=True, exist_ok=True)
        for cell in CELLS:
            payload = build_report(meta, setups, cell, BASE)
            path = run_dir / f"vwap_extremity_sweep_{cell['label'].replace('=', '_')}_report.json"
            path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(f"Navigator reports written to {run_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python -m pytest tests/test_vwap_sweep_scoring_cli.py -v
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Run the whole suite**

```bash
python -m pytest tests/ -q
```

Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add scripts/score_vwap_sweep.py tests/test_vwap_sweep_scoring_cli.py
git commit -m "feat: score a ledger into a verdict report and Navigator JSON

Runs in seconds over gross figures the scan already recorded, so cost and
filter questions never re-read the candles. Reports zero-cost alongside
base and stressed, labelled as context rather than a pass criterion --
it separates no edge from edge eaten by fees, and cannot be traded.

A sign-regression test asserts a ledger built to lose is reported as
losing.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 12: Run the placebo during the scan

Task 11's scorer already reads `meta["placebo"]["averages"]`, and until something
writes it every verdict is forced to `INCONCLUSIVE`. The placebo needs candles,
which only the scan loads, so the scan is what runs it. This task is scan-side
only — the scorer needs no further change.

**Files:**
- Modify: `scripts/run_vwap_sweep_scan.py`
- Test: `tests/test_vwap_sweep_placebo_wiring.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_vwap_sweep_placebo_wiring.py`:

```python
import sys
from pathlib import Path

import pandas as pd
import pytz

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))

from run_vwap_sweep_scan import scan_bars
from score_vwap_sweep import score_ledger

UTC = pytz.UTC


def _day(day, spike_at):
    rows = []
    for i in range(288):
        naive = pd.Timestamp(f"{day} 00:00:00") + pd.Timedelta(minutes=5 * i)
        high, low, close = 101.0, 99.0, 100.0
        if i == spike_at:
            high, low, close = 140.0, 100.0, 138.0
        elif i == spike_at + 1:
            high, low, close = 139.0, 99.0, 100.0
        rows.append(
            {
                "timestamp": int(UTC.localize(naive.to_pydatetime()).timestamp()),
                "open": close, "high": high, "low": low, "close": close, "volume": 10.0,
            }
        )
    return rows


def test_the_scan_records_a_placebo_distribution():
    bars = pd.DataFrame(
        _day("2026-01-05", 150) + _day("2026-01-06", 150) + _day("2026-01-07", 150)
        + _day("2026-01-08", 150)
    )
    meta, _ = scan_bars(bars, symbol="TEST", interval="5m", source="synthetic", placebo_seeds=5)

    assert "placebo" in meta
    assert meta["placebo"]["seeds_requested"] == 5
    assert len(meta["placebo"]["averages"]) > 0


def test_scoring_uses_the_recorded_placebo_distribution():
    bars = pd.DataFrame(
        _day("2026-01-05", 150) + _day("2026-01-06", 150) + _day("2026-01-07", 150)
        + _day("2026-01-08", 150)
    )
    meta, setups = scan_bars(bars, symbol="TEST", interval="5m", source="synthetic", placebo_seeds=5)
    report = score_ledger(meta, setups)

    assert report["placebo_percentile"] is not None
    assert 0.0 <= report["placebo_percentile"] <= 100.0
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python -m pytest tests/test_vwap_sweep_placebo_wiring.py -v
```

Expected: FAIL — `scan_bars() got an unexpected keyword argument 'placebo_seeds'`

- [ ] **Step 3: Record the placebo in the scan**

In `scripts/run_vwap_sweep_scan.py`, add these imports:

```python
from analysis.signal_trade_simulator import CandleSignal, simulate_trade_grid
from strategy.orb.placebo import build_placebo_signals
from strategy.orb.types import OrbSignal
from strategy.vwap_sweep.extremity_sweep import DEFAULTS, find_setups
from strategy.vwap_sweep.scoring import BASE, headline_cell, net_of, path_key, select_trades
```

Change the `scan_bars` signature to:

```python
def scan_bars(
    bars: pd.DataFrame,
    symbol: str,
    interval: str,
    source: str,
    placebo_seeds: int = 200,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
```

Then, just before `meta = {` is built, insert:

```python
    placebo = _run_placebo(all_setups, sessions, candles, placebo_seeds)
```

and add `"placebo": placebo,` to the `meta` dict.

Add this function at module level:

```python
def _run_placebo(
    setups: List[Dict[str, Any]],
    sessions: Dict[Any, pd.DataFrame],
    candles: pd.DataFrame,
    seeds: int,
) -> Dict[str, Any]:
    """Matched placebo over the headline cell's trades.

    Stop distance, target distance and holding period are held fixed; only the
    entry bar and the direction are randomised. That isolates "was the sweep
    informative?" from "does this exit geometry make money on any entry?".

    Lives in the scan because it needs the candles, which the scoring half never
    loads. The resulting distribution is recorded so scoring stays instant.
    """
    from datetime import date as date_type

    cell = headline_cell()
    key = path_key(cell)
    real = select_trades(setups, cell)
    if not real or seeds <= 0:
        return {"seeds_requested": seeds, "seeds_used": 0, "averages": [], "test_averages": []}

    orb_signals = []
    for setup in real:
        path = setup["paths"][key]
        orb_signals.append(
            OrbSignal.fired(
                date_type.fromisoformat(setup["session_date"]),
                CandleSignal(
                    bar_index=int(setup["confirm_bar_index"]),
                    side=setup["direction"],
                    entry_price=float(path["entry_price"]),
                    stop_price=float(path["stop_price"]),
                    signal_time=setup["confirm_time"],
                    max_hold_bars=int(setup["max_hold_bars"]),
                    entry_bar_index=int(setup["entry_bar_index"]),
                    target_price=float(path["target_price"]),
                ),
            )
        )

    test_dates = {setup["session_date"] for setup in real if setup["half"] == "test"}
    bar_to_date = {
        int(bar_index): session_date.isoformat()
        for session_date, session in sessions.items()
        for bar_index in session["bar_index"].tolist()
    }
    max_hold = max(int(setup["max_hold_bars"]) for setup in real)
    params = {
        "or_minutes": DEFAULTS["asian_minutes"],
        "session_start": DEFAULTS["session_start"],
        "flat_by": DEFAULTS["flat_by"],
    }

    averages: List[float] = []
    counts: List[int] = []
    for seed in range(seeds):
        signals = build_placebo_signals(orb_signals, sessions, params, seed=seed)
        if not signals:
            continue
        result = simulate_trade_grid(
            candles=candles,
            signals=signals,
            r_values=[2.0],
            max_hold_bars=max_hold,
            fee_rate=0.0,
            slippage_per_side=0.0,
        )
        trades = list(result["best"]["per_signal"].values())
        net_rs = []
        for trade, signal in zip(trades, signals):
            if bar_to_date.get(signal.bar_index) not in test_dates:
                continue
            _, _, net_r = net_of(
                {
                    "entry_price": trade["entry_price"],
                    "exit_price": trade["exit_price"],
                    "exit_is_maker": trade["exit_is_maker"],
                    "gross_pnl": trade["gross_pnl"],
                    "risk_per_unit": trade["risk_per_unit"],
                },
                BASE,
            )
            net_rs.append(net_r)
        if not net_rs:
            continue
        averages.append(round(sum(net_rs) / len(net_rs), 6))
        counts.append(len(signals))

    return {
        "seeds_requested": seeds,
        "seeds_used": len(averages),
        "real_signal_count": len(orb_signals),
        "min_placebo_signals_in_a_seed": min(counts) if counts else None,
        "full_strength_seeds": sum(1 for count in counts if count == len(orb_signals)),
        "averages": averages,
    }
```

Add `--placebo-seeds` to the parser and pass it through `main`:

```python
    parser.add_argument("--placebo-seeds", type=int, default=200)
```

```python
    meta, setups = scan_bars(
        bars, args.symbol, args.interval, source="binance_history",
        placebo_seeds=args.placebo_seeds,
    )
```

- [ ] **Step 4: Confirm the scorer needs no change**

`score_vwap_sweep._placebo_percentile` already reads
`meta["placebo"]["averages"]` and returns `None` when it is empty. Nothing to
edit here — this step exists so the absence of a change is deliberate rather
than an oversight. Re-read that function and confirm the key it reads matches
the key `_run_placebo` writes.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/test_vwap_sweep_placebo_wiring.py tests/test_vwap_sweep_scoring_cli.py -v
```

Expected: PASS.

- [ ] **Step 6: Run the whole suite**

```bash
python -m pytest tests/ -q
```

Expected: no regressions.

- [ ] **Step 7: Commit**

```bash
git add scripts/run_vwap_sweep_scan.py tests/test_vwap_sweep_placebo_wiring.py
git commit -m "feat: record the matched placebo during the scan

The placebo needs candles, which the scoring half never loads, so the
scan runs it once and records the distribution. Stop distance, target
distance and holding period are held fixed and only the entry bar and
direction are randomised, which isolates whether the sweep was
informative from whether the exit geometry works on any entry.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 13: Navigator column-driven table

Purely frontend. If this is dropped, the strategy still produces its verdict —
the Navigator just renders wrong headers. Do it last for that reason.

**Files:**
- Create: `../frontend/src/hypothesisColumns.js`
- Create: `../frontend/src/hypothesisColumns.test.mjs`
- Modify: `../frontend/src/App.jsx:1121-1135` (the `<thead>` block) and the
  matching `<tbody>` cell block

All commands in this task run from
`C:\Dev\GannTesting\.worktrees\vwap-extremity-sweep\gann-visualizer\frontend`.

- [ ] **Step 1: Write the failing test**

Create `src/hypothesisColumns.test.mjs`:

```javascript
import assert from 'node:assert/strict';
import test from 'node:test';

import { formatCell, resolveColumns } from './hypothesisColumns.js';

test('a report declaring columns uses them', () => {
  const report = { columns: [{ key: 'net_r', label: 'Net R', format: 'signed:2' }] };
  assert.deepEqual(resolveColumns(report), report.columns);
});

test('a report without columns falls back to null so the caller keeps legacy rendering', () => {
  assert.equal(resolveColumns({ live_events: [] }), null);
  assert.equal(resolveColumns({}), null);
  assert.equal(resolveColumns(null), null);
});

test('an empty columns array is treated as absent', () => {
  assert.equal(resolveColumns({ columns: [] }), null);
});

test('number formats round to the requested precision', () => {
  assert.equal(formatCell(3.14159, 'number:2'), '3.14');
  assert.equal(formatCell(3.14159, 'number:0'), '3');
});

test('signed formats keep a leading plus so wins and losses scan apart', () => {
  assert.equal(formatCell(1.5, 'signed:2'), '+1.50');
  assert.equal(formatCell(-1.5, 'signed:2'), '-1.50');
});

test('missing values render as a dash rather than undefined', () => {
  assert.equal(formatCell(null, 'number:2'), '-');
  assert.equal(formatCell(undefined, 'text'), '-');
});

test('zero is a value, not a missing one', () => {
  assert.equal(formatCell(0, 'number:2'), '0.00');
  assert.equal(formatCell(0, 'signed:2'), '+0.00');
});

test('integer and text pass through', () => {
  assert.equal(formatCell(7, 'integer'), '7');
  assert.equal(formatCell('asian_high', 'text'), 'asian_high');
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
node --test src/hypothesisColumns.test.mjs
```

Expected: FAIL — `Cannot find module './hypothesisColumns.js'`

- [ ] **Step 3: Write the module**

Create `src/hypothesisColumns.js`:

```javascript
// Column resolution for the hypothesis events table.
//
// A report may declare its own `columns`. When it does, the table renders them
// directly. When it does not, this returns null and the caller keeps the older
// hardcoded column sets, so every existing report is unaffected.

export function resolveColumns(report) {
    if (!report) return null;
    const columns = report.columns;
    if (!Array.isArray(columns) || columns.length === 0) return null;
    return columns;
}

export function formatCell(value, format) {
    if (value === null || value === undefined || value === '') return '-';

    const [kind, precisionText] = String(format || 'text').split(':');
    const precision = Number.parseInt(precisionText ?? '2', 10);

    switch (kind) {
        case 'number': {
            const numeric = Number(value);
            return Number.isFinite(numeric) ? numeric.toFixed(precision) : '-';
        }
        case 'signed': {
            const numeric = Number(value);
            if (!Number.isFinite(numeric)) return '-';
            const sign = numeric < 0 ? '' : '+';
            return `${sign}${numeric.toFixed(precision)}`;
        }
        case 'integer': {
            const numeric = Number(value);
            return Number.isFinite(numeric) ? String(Math.round(numeric)) : '-';
        }
        default:
            return String(value);
    }
}

export function cellColor(column, value) {
    if (column.format === 'side') return value === 'SHORT' ? '#F44336' : '#4CAF50';
    if (column.format === 'outcome') {
        if (value === 'WIN') return '#4CAF50';
        if (value === 'LOSS') return '#F44336';
        return '#888';
    }
    if (String(column.format || '').startsWith('signed')) {
        return Number(value) >= 0 ? '#4CAF50' : '#F44336';
    }
    return undefined;
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
node --test src/hypothesisColumns.test.mjs
```

Expected: PASS, 8 tests.

- [ ] **Step 5: Use it in the table**

In `src/App.jsx`, add to the import block near line 7:

```javascript
import { cellColor, formatCell, resolveColumns } from './hypothesisColumns.js'
```

Store the loaded report so its columns survive. In the `.then(data => { ... })`
handler around line 1050, after `setHypothesisEvents(events);` add:

```javascript
                                                    setReportColumns(resolveColumns(data));
```

Declare that state alongside the other `useState` calls for hypothesis data:

```javascript
    const [reportColumns, setReportColumns] = useState(null);
```

and reset it wherever `setHypothesisEvents([])` is called, by adding
`setReportColumns(null);` on the following line each time.

Then replace the `<thead>` block that currently begins:

```javascript
                                                    <th>DateTime</th>
                                                    {(filteredHypothesisEvents[0]?.rsi_value != null || filteredHypothesisEvents[0]?.best_r != null) ? (
```

so the declared-columns case is checked first:

```javascript
                                                    <th>DateTime</th>
                                                    {reportColumns ? (
                                                        reportColumns.map(column => (
                                                            <th key={column.key}>{column.label}</th>
                                                        ))
                                                    ) : (filteredHypothesisEvents[0]?.rsi_value != null || filteredHypothesisEvents[0]?.best_r != null) ? (
```

And in the `<tbody>`, replace:

```javascript
                                                        {(evt.rsi_value != null || evt.best_r != null) ? (
```

with:

```javascript
                                                        {reportColumns ? (
                                                            reportColumns.map(column => (
                                                                <td
                                                                    key={column.key}
                                                                    style={{ fontSize: '10px', color: cellColor(column, evt[column.key]) }}
                                                                >
                                                                    {formatCell(evt[column.key], column.format)}
                                                                </td>
                                                            ))
                                                        ) : (evt.rsi_value != null || evt.best_r != null) ? (
```

- [ ] **Step 6: Verify the build still compiles**

```bash
npm run build
```

Expected: build succeeds with no errors. If `npm run build` is not defined,
run `npx vite build` instead.

- [ ] **Step 7: Commit**

```bash
git add src/hypothesisColumns.js src/hypothesisColumns.test.mjs src/App.jsx
git commit -m "feat: hypothesis table renders columns the report declares

The table picked between two hardcoded column sets by sniffing for
rsi_value or best_r, so any new strategy rendered under the wrong
headers. A report may now declare its own columns; one that does not
keeps the existing behaviour untouched.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 14: Run it and record the result

**Files:**
- Create: `reports/vwap_sweep_btcusdt.md`, `reports/vwap_sweep_ethusdt.md`, `reports/vwap_sweep_solusdt.md`
- Modify: `docs/superpowers/backlog/2026-08-07-strategy-research-backlog.md`

- [ ] **Step 1: Confirm the corpus is present**

```bash
ls C:/Dev/GannTesting/logs/backend/history/BTCUSDT/5m/candles.csv
```

Expected: the file exists. If it does not:

```bash
python scripts/fetch_binance_history.py --years 5 --symbols BTCUSDT ETHUSDT SOLUSDT --intervals 5m
```

- [ ] **Step 2: Run the full suite one last time**

```bash
python -m pytest tests/ -q
```

Expected: all pass. Do not run the scan on a red suite.

- [ ] **Step 3: Scan BTCUSDT**

```bash
python scripts/run_vwap_sweep_scan.py --symbol BTCUSDT --interval 5m
```

Expected output ends with per-policy session accounting. Note the ledger path it
prints — the next step needs it.

Sanity checks before going further. Any of these failing is a bug signal, not a
finding:
- `available` should be roughly 1,800 sessions for five years.
- `with_setup` far below ~50% or at ~100% means the sweep definition is wrong.
- Any single skip reason dominating means a guard is misfiring.

- [ ] **Step 4: Score BTCUSDT**

```bash
python scripts/score_vwap_sweep.py --ledger <path printed in step 3> --navigator --out ../../reports/vwap_sweep_btcusdt.md
```

- [ ] **Step 5: Inspect twenty trades in the Navigator before believing anything**

Start the backend and frontend, open the Navigator, select
`BTCUSDT / 5 / <run_id>` and the `Vwap Extremity Sweep Headline` report.

For twenty randomly chosen trades, confirm against the chart that:
- the sweep bar's wick genuinely exceeds the Asian level
- the confirmation bar closes back inside both the level and the 2-sigma band
- the entry sits at the next bar's open, not the confirmation close
- the exit lands where `exit_reason` claims

A profitable-looking result is the most likely place for a bug to hide. If any
of the twenty disagrees with the chart, stop and debug before recording anything.

- [ ] **Step 6: Repeat for ETHUSDT and SOLUSDT**

```bash
python scripts/run_vwap_sweep_scan.py --symbol ETHUSDT --interval 5m
python scripts/run_vwap_sweep_scan.py --symbol SOLUSDT --interval 5m
```

Then score each into `reports/vwap_sweep_ethusdt.md` and
`reports/vwap_sweep_solusdt.md`. Report them separately. Do not pool them —
pooling three symbols into one number is a non-goal in the spec.

- [ ] **Step 7: Record the outcome in the backlog**

Insert this section into
`docs/superpowers/backlog/2026-08-07-strategy-research-backlog.md` immediately
after the `## ORB — CLOSED OUT` section, filling in the real numbers:

```markdown
## VWAP extremity sweep — <VERDICT> (2026-08-12)

Tested on 5 years of Binance USD-M 5m data. Reports in
[vwap_sweep_btcusdt.md](../../../reports/vwap_sweep_btcusdt.md),
[vwap_sweep_ethusdt.md](../../../reports/vwap_sweep_ethusdt.md) and
[vwap_sweep_solusdt.md](../../../reports/vwap_sweep_solusdt.md).

| | BTCUSDT | ETHUSDT | SOLUSDT |
|---|---|---|---|
| Sessions with a setup | | | |
| Avg net R per trade, base costs | | | |
| Breakeven cost rate (bps/side) | | | |
| Placebo percentile (bar: 95) | | | |
| Robustness grid | | | |
| Median planned R:R (source claims 2–3) | | | |

**Root cause (verified, not assumed):** <what the trade distribution actually
shows — exit-reason mix, where the R went, and how the honest next-bar-open fill
compares with the source's claimed fill via `entry_slip_vs_confirm_close`>

Level 2 candidate #4 ("VWAP band mean reversion") is now tested and closed.
```

If the verdict is anything other than `PASS`, do not tune to rescue it. Take the
next backlog candidate.

- [ ] **Step 8: Commit**

```bash
git add ../../reports/vwap_sweep_*.md ../../docs/superpowers/backlog/2026-08-07-strategy-research-backlog.md
git commit -m "chore: VWAP extremity sweep results on BTC, ETH and SOL

<one line stating the verdict per symbol and the breakeven cost rate>

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

- [ ] **Step 9: Finish the branch**

Use the superpowers:finishing-a-development-branch skill to decide between
merging to `main`, opening a PR, or discarding. Per `AGENTS.md`, merge one
branch at a time and rebase remaining worktrees afterwards.
