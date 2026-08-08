# ORB Go/No-Go Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pre-registered Opening Range Breakout test for NIFTY/BANKNIFTY that outputs a single honest verdict — `PASS`, `FRAGILE`, `FAIL`, or `INCONCLUSIVE` — with breakeven slippage as the headline margin number.

**Architecture:** Signal generation is fully separated from P&L. Small pure modules under `strategy/orb/` turn one trading session into at most one `CandleSignal`. The existing `analysis/signal_trade_simulator.py` does all execution and cost maths. Verdict logic is a pure function over cell results so it can be tested without touching data. The only shared-code change is an optional per-signal `max_hold_bars` on `CandleSignal`, which is what keeps a trade from running past the session close.

**Tech Stack:** Python 3, pandas, pytz, pytest. No new dependencies.

**Spec:** [docs/superpowers/specs/2026-08-07-orb-strategy-design.md](../specs/2026-08-07-orb-strategy-design.md)

**Deferred work:** [docs/superpowers/backlog/2026-08-07-strategy-research-backlog.md](../backlog/2026-08-07-strategy-research-backlog.md)

---

## Working directory

Every command in this plan runs from:

```bash
cd C:/Dev/GannTesting/gann-visualizer/backend
```

Tests follow the existing repo convention — see `tests/test_signal_trade_simulator.py`. Every test file starts with:

```python
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
```

## File structure

| File | Responsibility |
|---|---|
| `analysis/signal_trade_simulator.py` | **Modify.** Add optional per-signal `max_hold_bars`. |
| `strategy/orb/__init__.py` | Empty package marker. |
| `strategy/orb/types.py` | `OrbSignal` — the per-session result object (signal, or a reason it was skipped). |
| `strategy/orb/session.py` | Pure session maths: global bar indexing, IST session splitting, opening-range window, bars-until-flat, chronological half split. |
| `strategy/orb/variant_a_range.py` | Variant A signal generator. |
| `strategy/orb/variant_b_noise_band.py` | Variant B signal generator plus the daily ATR helper it alone uses. |
| `strategy/orb/costs.py` | Breakeven slippage interpolation. |
| `strategy/orb/placebo.py` | Matched placebo signal construction and percentile ranking. |
| `strategy/orb/verdict.py` | `CellResult` and the pure verdict decision function. |
| `strategy/orb/runner.py` | Orchestration: sessions → cells → simulation → placebo → sweep → report dict. |
| `scripts/run_orb_test.py` | CLI: fetch data, call the runner, render a markdown report. |

---

### Task 1: Per-signal `max_hold_bars` on `CandleSignal`

Without this a trade opened at 15:05 keeps running into the next trading day, because `_future_bar_window` selects bars by global index with no session boundary.

**Files:**
- Modify: `analysis/signal_trade_simulator.py`
- Test: `tests/test_signal_trade_simulator.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_signal_trade_simulator.py`:

```python
def _flat_candles(n=8, start_bar_index=0):
    """Candles that drift nowhere, so neither stop nor target is ever hit."""
    return pd.DataFrame(
        {
            "bar_index": list(range(start_bar_index, start_bar_index + n)),
            "open": [100.0] * n,
            "high": [100.5] * n,
            "low": [99.5] * n,
            "close": [100.0] * n,
        }
    )


def test_per_signal_max_hold_bars_truncates_the_window():
    candles = _flat_candles(n=8)
    signal = CandleSignal(
        bar_index=0,
        side="LONG",
        entry_price=100.0,
        stop_price=90.0,
        signal_time="2026-08-07T09:35:00",
        max_hold_bars=2,
    )

    result = simulate_trade_grid(
        candles=candles,
        signals=[signal],
        r_values=[2.0],
        max_hold_bars=7,
    )

    trade = result["best"]["per_signal"]["0:0"]
    assert trade["exit_bar_index"] == 2
    assert trade["exit_reason"] == "max_hold"


def test_omitting_max_hold_bars_uses_the_global_limit():
    candles = _flat_candles(n=8)
    signal = CandleSignal(
        bar_index=0,
        side="LONG",
        entry_price=100.0,
        stop_price=90.0,
        signal_time="2026-08-07T09:35:00",
    )

    result = simulate_trade_grid(
        candles=candles,
        signals=[signal],
        r_values=[2.0],
        max_hold_bars=4,
    )

    trade = result["best"]["per_signal"]["0:0"]
    assert trade["exit_bar_index"] == 4
    assert trade["exit_reason"] == "max_hold"


def test_non_positive_per_signal_max_hold_bars_is_rejected():
    candles = _flat_candles(n=8)
    signal = CandleSignal(
        bar_index=0,
        side="LONG",
        entry_price=100.0,
        stop_price=90.0,
        signal_time="2026-08-07T09:35:00",
        max_hold_bars=0,
    )

    with pytest.raises(ValueError, match="max_hold_bars"):
        simulate_trade_grid(
            candles=candles,
            signals=[signal],
            r_values=[2.0],
            max_hold_bars=7,
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_signal_trade_simulator.py -k max_hold -v`
Expected: FAIL — `TypeError: CandleSignal.__init__() got an unexpected keyword argument 'max_hold_bars'`

- [ ] **Step 3: Add the field**

In `analysis/signal_trade_simulator.py`, replace the dataclass:

```python
@dataclass(frozen=True)
class CandleSignal:
    bar_index: int
    side: str
    entry_price: float
    stop_price: float
    signal_time: Any
    max_hold_bars: Optional[int] = None
```

- [ ] **Step 4: Add the effective-limit helper**

Add directly above `_future_bar_window`:

```python
def _effective_max_hold(signal: CandleSignal, max_hold_bars: int) -> int:
    """Per-signal cap overrides the global one when present."""
    if signal.max_hold_bars is None:
        return max_hold_bars
    return signal.max_hold_bars
```

- [ ] **Step 5: Carry the field through normalisation and validate it**

Replace the body of `_normalize_signal`:

```python
def _normalize_signal(signal: CandleSignal) -> CandleSignal:
    if not isinstance(signal, CandleSignal):
        raise ValueError("signals must contain CandleSignal instances")

    max_hold = signal.max_hold_bars
    if max_hold is not None:
        max_hold = _coerce_integer_value("max_hold_bars", max_hold)
        if max_hold <= 0:
            raise ValueError("max_hold_bars must be positive when set")

    return CandleSignal(
        bar_index=_coerce_integer_value("bar_index", signal.bar_index),
        side=signal.side,
        entry_price=_validate_positive_price("entry_price", signal.entry_price),
        stop_price=_validate_positive_price("stop_price", signal.stop_price),
        signal_time=signal.signal_time,
        max_hold_bars=max_hold,
    )
```

- [ ] **Step 6: Use the effective limit in validation**

In `_validate_signal`, replace the `simulation_window` block at the end:

```python
    simulation_window = _future_bar_window(
        candles_by_bar=candles_by_bar,
        signal_bar_index=signal_bar_index,
        max_hold_bars=_effective_max_hold(signal, max_hold_bars),
    )
    if simulation_window.empty:
        raise ValueError(f"signal at bar {signal_bar_index} is not simulatable")
```

- [ ] **Step 7: Use the effective limit in simulation**

In `_simulate_single_trade`, replace the `future_bars` assignment:

```python
    effective_max_hold = _effective_max_hold(signal, max_hold_bars)
    future_bars = _future_bar_window(
        candles_by_bar=candles_by_bar,
        signal_bar_index=signal.bar_index,
        max_hold_bars=effective_max_hold,
    )
```

and further down, replace the `max_hold` reason check:

```python
        if len(future_bars) == effective_max_hold:
            exit_reason = "max_hold"
```

- [ ] **Step 8: Run the full simulator suite**

Run: `python -m pytest tests/test_signal_trade_simulator.py -v`
Expected: PASS — 10 tests (7 pre-existing plus 3 new). The 7 pre-existing tests passing is the proof this change is backward compatible.

- [ ] **Step 9: Commit**

```bash
git add analysis/signal_trade_simulator.py tests/test_signal_trade_simulator.py
git commit -m "feat: optional per-signal max_hold_bars on CandleSignal"
```

---

### Task 2: Session maths

Pure functions, no I/O, no strategy logic. Everything downstream depends on these being right.

**Files:**
- Create: `strategy/orb/__init__.py`
- Create: `strategy/orb/session.py`
- Test: `tests/test_orb_session.py`

- [ ] **Step 1: Create the package marker**

```bash
mkdir -p strategy/orb
printf '' > strategy/orb/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_orb_session.py`:

```python
import sys
from datetime import date, time
from pathlib import Path

import pandas as pd
import pytest
import pytz

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.orb.session import (
    add_bar_index,
    bars_until_flat,
    opening_range_bars,
    post_range_bars,
    split_sessions,
    split_dates_in_half,
)

IST = pytz.timezone("Asia/Kolkata")


def _bars_for_day(day, start=time(9, 15), count=6, minutes=5, price=100.0):
    """Build `count` bars of `minutes` length starting at `start` IST on `day`."""
    rows = []
    for i in range(count):
        naive = pd.Timestamp(f"{day} {start.hour:02d}:{start.minute:02d}:00") + pd.Timedelta(
            minutes=minutes * i
        )
        ts = int(IST.localize(naive.to_pydatetime()).timestamp())
        rows.append(
            {
                "timestamp": ts,
                "open": price,
                "high": price + 1.0,
                "low": price - 1.0,
                "close": price,
                "volume": 1000,
            }
        )
    return pd.DataFrame(rows)


def test_add_bar_index_is_unique_and_sorted():
    bars = pd.concat([_bars_for_day("2026-08-04", count=3), _bars_for_day("2026-08-03", count=3)])
    indexed = add_bar_index(bars)

    assert indexed["bar_index"].tolist() == [0, 1, 2, 3, 4, 5]
    assert indexed["timestamp"].is_monotonic_increasing


def test_split_sessions_groups_by_ist_trading_date():
    bars = pd.concat([_bars_for_day("2026-08-03", count=3), _bars_for_day("2026-08-04", count=4)])
    sessions = split_sessions(add_bar_index(bars))

    assert list(sessions.keys()) == [date(2026, 8, 3), date(2026, 8, 4)]
    assert len(sessions[date(2026, 8, 3)]) == 3
    assert len(sessions[date(2026, 8, 4)]) == 4


def test_opening_range_bars_takes_the_first_fifteen_minutes():
    session = split_sessions(add_bar_index(_bars_for_day("2026-08-04", count=6)))[date(2026, 8, 4)]
    or_bars = opening_range_bars(session, or_minutes=15)

    assert len(or_bars) == 3
    assert or_bars["bar_index"].tolist() == [0, 1, 2]


def test_post_range_bars_excludes_the_range_and_respects_flat_by():
    session = split_sessions(add_bar_index(_bars_for_day("2026-08-04", count=6)))[date(2026, 8, 4)]
    after = post_range_bars(session, or_minutes=15, flat_by=time(9, 40))

    assert after["bar_index"].tolist() == [3, 4, 5]


def test_post_range_bars_drops_bars_after_flat_by():
    session = split_sessions(add_bar_index(_bars_for_day("2026-08-04", count=6)))[date(2026, 8, 4)]
    after = post_range_bars(session, or_minutes=15, flat_by=time(9, 35))

    assert after["bar_index"].tolist() == [3, 4]


def test_bars_until_flat_counts_remaining_holdable_bars():
    session = split_sessions(add_bar_index(_bars_for_day("2026-08-04", count=6)))[date(2026, 8, 4)]

    assert bars_until_flat(session, bar_index=3, flat_by=time(9, 40)) == 2
    assert bars_until_flat(session, bar_index=5, flat_by=time(9, 40)) == 0


def test_split_dates_in_half_puts_the_extra_day_in_train():
    dates = [date(2026, 8, d) for d in (3, 4, 5, 6, 7)]
    train, test = split_dates_in_half(dates)

    assert train == dates[:3]
    assert test == dates[3:]


def test_split_dates_in_half_rejects_fewer_than_two_dates():
    with pytest.raises(ValueError, match="at least 2"):
        split_dates_in_half([date(2026, 8, 3)])
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest tests/test_orb_session.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'strategy.orb.session'`

- [ ] **Step 4: Write the implementation**

Create `strategy/orb/session.py`:

```python
"""
Pure session maths for the ORB test.

No I/O, no strategy rules. Everything here operates on a bars DataFrame with a
``timestamp`` column of Unix seconds and the usual OHLCV columns.

Bars are timestamped at bar OPEN, matching yfinance and Dhan. A 5-minute bar
stamped 09:15 covers 09:15 to 09:20, so the first fifteen minutes of an NSE
session is the three bars stamped 09:15, 09:20 and 09:25.
"""

from datetime import date, time
from typing import Dict, List, Tuple

import pandas as pd
import pytz

IST = pytz.timezone("Asia/Kolkata")
SESSION_START = time(9, 15)
FLAT_BY = time(15, 15)


def add_bar_index(bars: pd.DataFrame) -> pd.DataFrame:
    """Sort by timestamp and attach a unique, globally monotonic ``bar_index``.

    The index must be global rather than per-session because the trade simulator
    selects future bars by index across the whole frame.
    """
    if "timestamp" not in bars.columns:
        raise ValueError("bars must have a 'timestamp' column")
    if bars.empty:
        raise ValueError("bars must not be empty")

    out = bars.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
    out["bar_index"] = range(len(out))
    return out


def _attach_ist(bars: pd.DataFrame) -> pd.DataFrame:
    out = bars.copy()
    out["ist"] = pd.to_datetime(out["timestamp"], unit="s", utc=True).dt.tz_convert(IST)
    out["session_date"] = out["ist"].dt.date
    out["ist_time"] = out["ist"].dt.time
    return out


def split_sessions(bars: pd.DataFrame) -> Dict[date, pd.DataFrame]:
    """Group bars into one DataFrame per IST trading date, ordered by date.

    Each session keeps its global ``bar_index`` and gains ``ist``,
    ``session_date`` and ``ist_time`` columns.
    """
    if "bar_index" not in bars.columns:
        raise ValueError("call add_bar_index before split_sessions")

    enriched = _attach_ist(bars)
    sessions: Dict[date, pd.DataFrame] = {}
    for session_date, group in enriched.groupby("session_date", sort=True):
        sessions[session_date] = group.sort_values("bar_index").reset_index(drop=True)
    return sessions


def _minutes_from(reference: time, value: time) -> int:
    return (value.hour * 60 + value.minute) - (reference.hour * 60 + reference.minute)


def opening_range_bars(
    session: pd.DataFrame,
    or_minutes: int,
    session_start: time = SESSION_START,
) -> pd.DataFrame:
    """Bars whose open time falls in [session_start, session_start + or_minutes)."""
    offsets = session["ist_time"].apply(lambda t: _minutes_from(session_start, t))
    mask = (offsets >= 0) & (offsets < or_minutes)
    return session[mask].reset_index(drop=True)


def post_range_bars(
    session: pd.DataFrame,
    or_minutes: int,
    session_start: time = SESSION_START,
    flat_by: time = FLAT_BY,
) -> pd.DataFrame:
    """Tradable bars: after the opening range, at or before the flat-by time.

    ``flat_by`` names the last bar we are allowed to still be holding through;
    that bar's close is the forced exit.
    """
    offsets = session["ist_time"].apply(lambda t: _minutes_from(session_start, t))
    flat_offset = _minutes_from(session_start, flat_by)
    mask = (offsets >= or_minutes) & (offsets <= flat_offset)
    return session[mask].reset_index(drop=True)


def bars_until_flat(
    session: pd.DataFrame,
    bar_index: int,
    session_start: time = SESSION_START,
    flat_by: time = FLAT_BY,
) -> int:
    """How many bars after ``bar_index`` remain holdable in this session."""
    offsets = session["ist_time"].apply(lambda t: _minutes_from(session_start, t))
    flat_offset = _minutes_from(session_start, flat_by)
    mask = (session["bar_index"] > bar_index) & (offsets <= flat_offset)
    return int(mask.sum())


def split_dates_in_half(dates: List[date]) -> Tuple[List[date], List[date]]:
    """Chronological halves. An odd extra date goes to train, never to test.

    Nothing is fitted on the train half — the split exists only to check the
    result holds up over time.
    """
    if len(dates) < 2:
        raise ValueError("need at least 2 dates to split")
    ordered = sorted(dates)
    cut = (len(ordered) + 1) // 2
    return ordered[:cut], ordered[cut:]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_orb_session.py -v`
Expected: PASS — 8 tests.

- [ ] **Step 6: Commit**

```bash
git add strategy/orb/__init__.py strategy/orb/session.py tests/test_orb_session.py
git commit -m "feat: ORB session splitting and opening-range helpers"
```

---

### Task 3: `OrbSignal` result type

Every session produces one of these — either a signal, or a recorded reason it was skipped. Silent drops are the failure mode this design exists to prevent.

**Files:**
- Create: `strategy/orb/types.py`
- Test: `tests/test_orb_types.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orb_types.py`:

```python
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from analysis.signal_trade_simulator import CandleSignal
from strategy.orb.types import OrbSignal


def test_skipped_records_the_reason_and_has_no_signal():
    result = OrbSignal.skipped(date(2026, 8, 4), "degenerate_range", range_width=0.0)

    assert result.signal is None
    assert result.reason == "degenerate_range"
    assert result.diagnostics["range_width"] == 0.0
    assert result.triggered is False


def test_fired_carries_the_signal_and_no_reason():
    signal = CandleSignal(
        bar_index=3,
        side="LONG",
        entry_price=101.0,
        stop_price=99.0,
        signal_time="2026-08-04T09:35:00+05:30",
        max_hold_bars=60,
    )
    result = OrbSignal.fired(date(2026, 8, 4), signal, orh=100.5, orl=99.0)

    assert result.signal is signal
    assert result.reason is None
    assert result.diagnostics["orh"] == 100.5
    assert result.triggered is True


def test_fired_rejects_a_missing_signal():
    with pytest.raises(ValueError, match="signal"):
        OrbSignal.fired(date(2026, 8, 4), None)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_orb_types.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'strategy.orb.types'`

- [ ] **Step 3: Write the implementation**

Create `strategy/orb/types.py`:

```python
"""Per-session result object shared by both ORB variants."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Optional

from analysis.signal_trade_simulator import CandleSignal


@dataclass(frozen=True)
class OrbSignal:
    """Outcome of evaluating one trading session.

    Exactly one of ``signal`` or ``reason`` is set. A session that produced no
    trade always carries a reason, so the report can account for every session
    instead of quietly losing it.
    """

    session_date: date
    signal: Optional[CandleSignal] = None
    reason: Optional[str] = None
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    @property
    def triggered(self) -> bool:
        return self.signal is not None

    @classmethod
    def skipped(cls, session_date: date, reason: str, **diagnostics: Any) -> "OrbSignal":
        if not reason:
            raise ValueError("a skipped session must carry a reason")
        return cls(session_date=session_date, signal=None, reason=reason, diagnostics=diagnostics)

    @classmethod
    def fired(
        cls,
        session_date: date,
        signal: Optional[CandleSignal],
        **diagnostics: Any,
    ) -> "OrbSignal":
        if signal is None:
            raise ValueError("a fired session must carry a signal")
        return cls(session_date=session_date, signal=signal, reason=None, diagnostics=diagnostics)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_orb_types.py -v`
Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add strategy/orb/types.py tests/test_orb_types.py
git commit -m "feat: OrbSignal per-session result type"
```

---

### Task 4: Variant A — classic opening range

**Files:**
- Create: `strategy/orb/variant_a_range.py`
- Test: `tests/test_orb_variant_a.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orb_variant_a.py`:

```python
import sys
from datetime import date, time
from pathlib import Path

import pandas as pd
import pytz

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.orb.session import add_bar_index, split_sessions
from strategy.orb.variant_a_range import generate_signal

IST = pytz.timezone("Asia/Kolkata")
DAY = "2026-08-04"


def _session(closes, highs=None, lows=None, opens=None):
    """Build one 5-minute session from 09:15 with the given closes."""
    n = len(closes)
    highs = highs or [c + 0.5 for c in closes]
    lows = lows or [c - 0.5 for c in closes]
    opens = opens or list(closes)
    rows = []
    for i in range(n):
        naive = pd.Timestamp(f"{DAY} 09:15:00") + pd.Timedelta(minutes=5 * i)
        rows.append(
            {
                "timestamp": int(IST.localize(naive.to_pydatetime()).timestamp()),
                "open": opens[i],
                "high": highs[i],
                "low": lows[i],
                "close": closes[i],
                "volume": 1000,
            }
        )
    bars = add_bar_index(pd.DataFrame(rows))
    return split_sessions(bars)[date(2026, 8, 4)]


PARAMS = {"or_minutes": 15, "bar_minutes": 5, "flat_by": time(10, 5)}


def test_upward_break_produces_a_long_at_the_trigger_close():
    # OR bars (09:15-09:25) high tops out at 100.5. Bar 3 closes at 102.
    session = _session([100.0, 100.0, 100.0, 102.0, 102.0, 102.0, 102.0, 102.0])
    result = generate_signal(session, PARAMS)

    assert result.triggered
    assert result.signal.side == "LONG"
    assert result.signal.bar_index == 3
    assert result.signal.entry_price == 102.0
    assert result.signal.stop_price == 99.5      # lowest low of the OR window
    assert result.signal.max_hold_bars == 4      # bars 4..7 remain before 10:05


def test_downward_break_produces_a_short():
    session = _session([100.0, 100.0, 100.0, 98.0, 98.0, 98.0, 98.0, 98.0])
    result = generate_signal(session, PARAMS)

    assert result.triggered
    assert result.signal.side == "SHORT"
    assert result.signal.bar_index == 3
    assert result.signal.entry_price == 98.0
    assert result.signal.stop_price == 100.5     # highest high of the OR window


def test_inside_day_produces_no_signal():
    session = _session([100.0] * 8)
    result = generate_signal(session, PARAMS)

    assert not result.triggered
    assert result.reason == "no_breakout"


def test_only_the_first_trigger_is_taken():
    # Breaks down at bar 3, then back up above the range at bar 5.
    session = _session([100.0, 100.0, 100.0, 98.0, 99.0, 102.0, 102.0, 102.0])
    result = generate_signal(session, PARAMS)

    assert result.signal.side == "SHORT"
    assert result.signal.bar_index == 3


def test_degenerate_range_is_skipped():
    session = _session(
        [100.0] * 8,
        highs=[100.0] * 8,
        lows=[100.0] * 8,
    )
    result = generate_signal(session, PARAMS)

    assert not result.triggered
    assert result.reason == "degenerate_range"


def test_short_opening_range_is_skipped():
    session = _session([100.0, 100.0])  # only two bars, need three
    result = generate_signal(session, PARAMS)

    assert not result.triggered
    assert result.reason == "short_opening_range"


def test_trigger_with_no_bars_left_before_flat_is_skipped():
    # Breaks out on bar 7 (09:50), which is the flat-by bar — nothing left to hold.
    session = _session([100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 102.0])
    result = generate_signal(session, {**PARAMS, "flat_by": time(9, 50)})

    assert not result.triggered
    assert result.reason == "no_bars_before_flat"
    assert result.diagnostics["trigger_bar"] == 7


def test_diagnostics_record_the_range():
    session = _session([100.0, 100.0, 100.0, 102.0, 102.0, 102.0, 102.0, 102.0])
    result = generate_signal(session, PARAMS)

    assert result.diagnostics["orh"] == 100.5
    assert result.diagnostics["orl"] == 99.5
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_orb_variant_a.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'strategy.orb.variant_a_range'`

- [ ] **Step 3: Write the implementation**

Create `strategy/orb/variant_a_range.py`:

```python
"""
Variant A — classic opening range breakout.

The first ``or_minutes`` of the session define a box. The first bar afterwards
that CLOSES beyond the box triggers a trade in that direction, with the stop on
the opposite side of the box.

This module decides only where to enter and where the stop sits. Targets, costs
and P&L belong to analysis/signal_trade_simulator.py.
"""

from datetime import time
from typing import Any, Dict

import pandas as pd

from analysis.signal_trade_simulator import CandleSignal
from strategy.orb.session import (
    FLAT_BY,
    SESSION_START,
    bars_until_flat,
    opening_range_bars,
    post_range_bars,
)
from strategy.orb.types import OrbSignal

DEFAULTS: Dict[str, Any] = {
    "or_minutes": 15,
    "bar_minutes": 5,
    "session_start": SESSION_START,
    "flat_by": FLAT_BY,
}


def generate_signal(session: pd.DataFrame, params: Dict[str, Any]) -> OrbSignal:
    """Evaluate one session. Returns at most one signal."""
    settings = {**DEFAULTS, **params}
    or_minutes: int = settings["or_minutes"]
    bar_minutes: int = settings["bar_minutes"]
    session_start: time = settings["session_start"]
    flat_by: time = settings["flat_by"]

    session_date = session["session_date"].iloc[0]

    expected_or_bars = or_minutes // bar_minutes
    or_bars = opening_range_bars(session, or_minutes=or_minutes, session_start=session_start)
    if len(or_bars) < expected_or_bars:
        return OrbSignal.skipped(
            session_date,
            "short_opening_range",
            or_bars_seen=len(or_bars),
            or_bars_expected=expected_or_bars,
        )

    orh = float(or_bars["high"].max())
    orl = float(or_bars["low"].min())
    if orh <= orl:
        return OrbSignal.skipped(session_date, "degenerate_range", orh=orh, orl=orl)

    tradable = post_range_bars(
        session, or_minutes=or_minutes, session_start=session_start, flat_by=flat_by
    )

    for _, bar in tradable.iterrows():
        close = float(bar["close"])
        if close > orh:
            side, stop_price = "LONG", orl
        elif close < orl:
            side, stop_price = "SHORT", orh
        else:
            continue

        bar_index = int(bar["bar_index"])
        remaining = bars_until_flat(
            session, bar_index=bar_index, session_start=session_start, flat_by=flat_by
        )
        if remaining < 1:
            # Triggered on the last holdable bar — nothing left to simulate.
            return OrbSignal.skipped(
                session_date, "no_bars_before_flat", orh=orh, orl=orl, trigger_bar=bar_index
            )

        return OrbSignal.fired(
            session_date,
            CandleSignal(
                bar_index=bar_index,
                side=side,
                entry_price=close,
                stop_price=stop_price,
                signal_time=bar["ist"].isoformat(),
                max_hold_bars=remaining,
            ),
            orh=orh,
            orl=orl,
            range_width=orh - orl,
        )

    return OrbSignal.skipped(session_date, "no_breakout", orh=orh, orl=orl)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_orb_variant_a.py -v`
Expected: PASS — 8 tests.

- [ ] **Step 5: Commit**

```bash
git add strategy/orb/variant_a_range.py tests/test_orb_variant_a.py
git commit -m "feat: ORB variant A classic opening range signal generator"
```

---

### Task 5: Variant B — noise-band breakout

**Files:**
- Create: `strategy/orb/variant_b_noise_band.py`
- Test: `tests/test_orb_variant_b.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orb_variant_b.py`:

```python
import sys
from datetime import date, time
from pathlib import Path

import pandas as pd
import pytest
import pytz

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.orb.session import add_bar_index, split_sessions
from strategy.orb.variant_b_noise_band import daily_atr, generate_signal

IST = pytz.timezone("Asia/Kolkata")
DAY = "2026-08-04"


def _session(closes, opens=None):
    n = len(closes)
    opens = opens or list(closes)
    rows = []
    for i in range(n):
        naive = pd.Timestamp(f"{DAY} 09:15:00") + pd.Timedelta(minutes=5 * i)
        rows.append(
            {
                "timestamp": int(IST.localize(naive.to_pydatetime()).timestamp()),
                "open": opens[i],
                "high": max(opens[i], closes[i]) + 0.5,
                "low": min(opens[i], closes[i]) - 0.5,
                "close": closes[i],
                "volume": 1000,
            }
        )
    bars = add_bar_index(pd.DataFrame(rows))
    return split_sessions(bars)[date(2026, 8, 4)]


# anchor 100.0, atr 40.0, k 0.25 -> band is 100 +/- 10 -> [90, 110]
PARAMS = {"warmup_minutes": 15, "bar_minutes": 5, "k": 0.25, "flat_by": time(10, 5)}


def test_daily_atr_averages_true_range():
    daily = pd.DataFrame(
        {
            "high": [110.0, 112.0, 111.0],
            "low": [100.0, 102.0, 101.0],
            "close": [105.0, 108.0, 106.0],
        }
    )
    atr = daily_atr(daily, length=2)

    # TR: bar0 = 10 (no prev close), bar1 = max(10, 7, 3) = 10, bar2 = max(10, 3, 7) = 10
    assert pd.isna(atr.iloc[0])  # NaN during warmup
    assert atr.iloc[1] == pytest.approx(10.0)
    assert atr.iloc[2] == pytest.approx(10.0)


def test_upward_band_break_produces_a_long():
    session = _session([100.0, 100.0, 100.0, 115.0, 115.0, 115.0, 115.0, 115.0])
    result = generate_signal(session, PARAMS, atr=40.0)

    assert result.triggered
    assert result.signal.side == "LONG"
    assert result.signal.bar_index == 3
    assert result.signal.entry_price == 115.0
    assert result.signal.stop_price == pytest.approx(90.0)


def test_downward_band_break_produces_a_short():
    session = _session([100.0, 100.0, 100.0, 85.0, 85.0, 85.0, 85.0, 85.0])
    result = generate_signal(session, PARAMS, atr=40.0)

    assert result.signal.side == "SHORT"
    assert result.signal.stop_price == pytest.approx(110.0)


def test_no_breach_produces_no_signal():
    session = _session([100.0, 100.0, 100.0, 105.0, 95.0, 104.0, 96.0, 100.0])
    result = generate_signal(session, PARAMS, atr=40.0)

    assert not result.triggered
    assert result.reason == "no_breakout"


def test_band_anchors_to_todays_open_not_yesterdays_close():
    # Session gaps up: opens at 200, so the band is 200 +/- 10, not 100 +/- 10.
    session = _session(
        [200.0, 200.0, 200.0, 205.0, 205.0, 205.0, 205.0, 205.0],
        opens=[200.0] * 8,
    )
    result = generate_signal(session, PARAMS, atr=40.0)

    assert not result.triggered  # 205 is inside 200 +/- 10
    assert result.diagnostics["anchor"] == 200.0
    assert result.diagnostics["upper"] == pytest.approx(210.0)


def test_missing_atr_is_skipped():
    session = _session([100.0] * 8)
    result = generate_signal(session, PARAMS, atr=None)

    assert not result.triggered
    assert result.reason == "no_atr"


def test_non_positive_atr_is_skipped():
    session = _session([100.0] * 8)
    result = generate_signal(session, PARAMS, atr=0.0)

    assert not result.triggered
    assert result.reason == "no_atr"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_orb_variant_b.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'strategy.orb.variant_b_noise_band'`

- [ ] **Step 3: Write the implementation**

Create `strategy/orb/variant_b_noise_band.py`:

```python
"""
Variant B — noise-band breakout.

Anchored to today's opening price rather than a fixed box, with the band width
scaled by recent daily volatility. This adapts across volatility regimes and
handles gap-open days, because the anchor moves with the gap.

Honesty note: this is a simplified stand-in for the published
volatility-normalised intraday momentum idea, not a reproduction of any
specific paper. Report it that way.
"""

from datetime import time
from typing import Any, Dict, Optional

import pandas as pd

from analysis.signal_trade_simulator import CandleSignal
from strategy.orb.session import (
    FLAT_BY,
    SESSION_START,
    bars_until_flat,
    post_range_bars,
)
from strategy.orb.types import OrbSignal

DEFAULTS: Dict[str, Any] = {
    "warmup_minutes": 15,
    "bar_minutes": 5,
    "k": 0.25,
    "session_start": SESSION_START,
    "flat_by": FLAT_BY,
}


def daily_atr(daily_bars: pd.DataFrame, length: int = 14) -> pd.Series:
    """Simple moving average of true range over daily bars.

    A plain SMA of TR rather than Wilder's smoothing — chosen for being obvious
    to verify by hand. Returns NaN during the warmup period.
    """
    high = daily_bars["high"].astype(float)
    low = daily_bars["low"].astype(float)
    close = daily_bars["close"].astype(float)
    prev_close = close.shift(1)

    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    return true_range.rolling(length, min_periods=length).mean()


def generate_signal(
    session: pd.DataFrame,
    params: Dict[str, Any],
    atr: Optional[float],
) -> OrbSignal:
    """Evaluate one session. ``atr`` must be computed through YESTERDAY's close."""
    settings = {**DEFAULTS, **params}
    warmup_minutes: int = settings["warmup_minutes"]
    k: float = settings["k"]
    session_start: time = settings["session_start"]
    flat_by: time = settings["flat_by"]

    session_date = session["session_date"].iloc[0]

    if atr is None or not float(atr) > 0 or pd.isna(atr):
        return OrbSignal.skipped(session_date, "no_atr", atr=atr)

    anchor = float(session["open"].iloc[0])
    half_width = k * float(atr)
    upper = anchor + half_width
    lower = anchor - half_width

    tradable = post_range_bars(
        session, or_minutes=warmup_minutes, session_start=session_start, flat_by=flat_by
    )

    for _, bar in tradable.iterrows():
        close = float(bar["close"])
        if close > upper:
            side, stop_price = "LONG", lower
        elif close < lower:
            side, stop_price = "SHORT", upper
        else:
            continue

        bar_index = int(bar["bar_index"])
        remaining = bars_until_flat(
            session, bar_index=bar_index, session_start=session_start, flat_by=flat_by
        )
        if remaining < 1:
            return OrbSignal.skipped(
                session_date,
                "no_bars_before_flat",
                anchor=anchor,
                upper=upper,
                lower=lower,
                trigger_bar=bar_index,
            )

        return OrbSignal.fired(
            session_date,
            CandleSignal(
                bar_index=bar_index,
                side=side,
                entry_price=close,
                stop_price=stop_price,
                signal_time=bar["ist"].isoformat(),
                max_hold_bars=remaining,
            ),
            anchor=anchor,
            upper=upper,
            lower=lower,
            atr=float(atr),
        )

    return OrbSignal.skipped(
        session_date, "no_breakout", anchor=anchor, upper=upper, lower=lower, atr=float(atr)
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_orb_variant_b.py -v`
Expected: PASS — 7 tests.

- [ ] **Step 5: Commit**

```bash
git add strategy/orb/variant_b_noise_band.py tests/test_orb_variant_b.py
git commit -m "feat: ORB variant B noise-band signal generator"
```

---

### Task 6: Breakeven slippage

The headline margin number. Answers "how much slippage kills this?" instead of arguing about the correct assumption.

**Files:**
- Create: `strategy/orb/costs.py`
- Test: `tests/test_orb_costs.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orb_costs.py`:

```python
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.orb.costs import SLIPPAGE_SWEEP, breakeven_slippage


def test_sweep_is_ascending_and_starts_at_zero():
    assert SLIPPAGE_SWEEP[0] == 0.0
    assert SLIPPAGE_SWEEP == sorted(SLIPPAGE_SWEEP)


def test_interpolates_the_zero_crossing():
    # +2.0 at 0.5 slippage, -2.0 at 1.0 -> crosses exactly halfway, at 0.75
    pnl = {0.0: 4.0, 0.5: 2.0, 1.0: -2.0}
    assert breakeven_slippage(pnl) == pytest.approx(0.75)


def test_already_negative_at_zero_slippage_reports_zero():
    pnl = {0.0: -1.0, 0.5: -2.0, 1.0: -3.0}
    assert breakeven_slippage(pnl) == 0.0


def test_still_positive_at_the_top_reports_the_top_as_a_floor():
    pnl = {0.0: 5.0, 1.0: 4.0, 3.0: 3.0}
    assert breakeven_slippage(pnl) == 3.0


def test_exact_zero_at_a_tested_level_reports_that_level():
    pnl = {0.0: 2.0, 0.5: 0.0, 1.0: -2.0}
    assert breakeven_slippage(pnl) == pytest.approx(0.5)


def test_empty_input_is_rejected():
    with pytest.raises(ValueError, match="at least one"):
        breakeven_slippage({})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_orb_costs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'strategy.orb.costs'`

- [ ] **Step 3: Write the implementation**

Create `strategy/orb/costs.py`:

```python
"""
Slippage as a stress axis, not an assumption.

Optimising slippage is meaningless — the best value is always zero. Instead the
strategy is run across a range of slippage levels and the report leads with the
level at which the edge dies.
"""

from typing import Dict, List

# Index points per side.
SLIPPAGE_SWEEP: List[float] = [0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0]

BASE_SLIPPAGE = 1.0
STRESSED_SLIPPAGE = 2.0

BASE_FEE_RATE = 0.0003
STRESSED_FEE_RATE = 0.0006


def breakeven_slippage(pnl_by_slippage: Dict[float, float]) -> float:
    """Slippage level, in index points per side, where average net P&L hits zero.

    Args:
        pnl_by_slippage: average net P&L per trade at each tested slippage level.

    Returns:
        The linearly interpolated crossing point. If P&L is already non-positive
        at the lowest tested level, returns 0.0 rather than a negative number —
        the strategy loses money even with perfect fills. If P&L is still
        positive at the highest tested level, returns that level, which should be
        read as a floor ("survives at least this much"), not a measurement.
    """
    if not pnl_by_slippage:
        raise ValueError("need at least one slippage level")

    levels = sorted(pnl_by_slippage)

    if pnl_by_slippage[levels[0]] <= 0:
        return 0.0

    for lower, upper in zip(levels, levels[1:]):
        pnl_lower = pnl_by_slippage[lower]
        pnl_upper = pnl_by_slippage[upper]
        if pnl_upper > 0:
            continue
        if pnl_lower == pnl_upper:
            return float(upper)
        fraction = pnl_lower / (pnl_lower - pnl_upper)
        return float(lower + fraction * (upper - lower))

    return float(levels[-1])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_orb_costs.py -v`
Expected: PASS — 6 tests.

- [ ] **Step 5: Commit**

```bash
git add strategy/orb/costs.py tests/test_orb_costs.py
git commit -m "feat: breakeven slippage interpolation"
```

---

### Task 7: Matched placebo

Without this, a positive result could be nothing more than intraday drift plus a favourable exit rule.

**Files:**
- Create: `strategy/orb/placebo.py`
- Test: `tests/test_orb_placebo.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orb_placebo.py`:

```python
import sys
from datetime import date, time
from pathlib import Path

import pandas as pd
import pytest
import pytz

sys.path.append(str(Path(__file__).resolve().parents[1]))

from analysis.signal_trade_simulator import CandleSignal
from strategy.orb.placebo import build_placebo_signals, placebo_percentile
from strategy.orb.session import add_bar_index, split_sessions
from strategy.orb.types import OrbSignal

IST = pytz.timezone("Asia/Kolkata")


def _sessions(day="2026-08-04", n=8):
    rows = []
    for i in range(n):
        naive = pd.Timestamp(f"{day} 09:15:00") + pd.Timedelta(minutes=5 * i)
        rows.append(
            {
                "timestamp": int(IST.localize(naive.to_pydatetime()).timestamp()),
                "open": 100.0,
                "high": 100.5,
                "low": 99.5,
                "close": 100.0,
                "volume": 1000,
            }
        )
    return split_sessions(add_bar_index(pd.DataFrame(rows)))


def _real_signal():
    return OrbSignal.fired(
        date(2026, 8, 4),
        CandleSignal(
            bar_index=3,
            side="LONG",
            entry_price=102.0,
            stop_price=99.0,
            signal_time="2026-08-04T09:30:00+05:30",
            max_hold_bars=4,
        ),
    )


PARAMS = {"or_minutes": 15, "flat_by": time(10, 5)}


def test_placebo_preserves_the_stop_distance():
    placebos = build_placebo_signals([_real_signal()], _sessions(), PARAMS, seed=1)

    assert len(placebos) == 1
    placebo = placebos[0]
    assert abs(placebo.entry_price - placebo.stop_price) == pytest.approx(3.0)


def test_placebo_entry_comes_from_a_tradable_bar_in_the_same_session():
    placebos = build_placebo_signals([_real_signal()], _sessions(), PARAMS, seed=1)

    assert placebos[0].bar_index in {3, 4, 5, 6, 7}


def test_placebo_stop_orientation_matches_its_side():
    for seed in range(20):
        for placebo in build_placebo_signals([_real_signal()], _sessions(), PARAMS, seed=seed):
            if placebo.side == "LONG":
                assert placebo.stop_price < placebo.entry_price
            else:
                assert placebo.stop_price > placebo.entry_price


def test_placebo_is_deterministic_for_a_given_seed():
    first = build_placebo_signals([_real_signal()], _sessions(), PARAMS, seed=7)
    second = build_placebo_signals([_real_signal()], _sessions(), PARAMS, seed=7)

    assert first == second


def test_different_seeds_eventually_differ():
    runs = {
        tuple((s.bar_index, s.side) for s in build_placebo_signals(
            [_real_signal()], _sessions(), PARAMS, seed=seed
        ))
        for seed in range(30)
    }
    assert len(runs) > 1


def test_skipped_sessions_produce_no_placebo():
    skipped = OrbSignal.skipped(date(2026, 8, 4), "no_breakout")
    assert build_placebo_signals([skipped], _sessions(), PARAMS, seed=1) == []


def test_percentile_ranks_the_real_result_against_the_distribution():
    assert placebo_percentile(10.0, [1.0, 2.0, 3.0, 4.0]) == 100.0
    assert placebo_percentile(0.0, [1.0, 2.0, 3.0, 4.0]) == 0.0
    assert placebo_percentile(2.5, [1.0, 2.0, 3.0, 4.0]) == 50.0


def test_percentile_needs_a_distribution():
    with pytest.raises(ValueError, match="empty"):
        placebo_percentile(1.0, [])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_orb_placebo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'strategy.orb.placebo'`

- [ ] **Step 3: Write the implementation**

Create `strategy/orb/placebo.py`:

```python
"""
Matched placebo: same sessions, same stop distance, same holding limit — only
the entry bar and the direction are randomised.

Holding stop distance fixed is what makes the comparison fair. It isolates
"was the ORB trigger informative?" from "does this exit rule make money on any
entry?". Follows the pattern established by scripts/placebo_test_rsi.py.
"""

import random
from datetime import date, time
from typing import Any, Dict, List, Sequence

import pandas as pd

from analysis.signal_trade_simulator import CandleSignal
from strategy.orb.session import FLAT_BY, SESSION_START, bars_until_flat, post_range_bars
from strategy.orb.types import OrbSignal


def build_placebo_signals(
    real: Sequence[OrbSignal],
    sessions: Dict[date, pd.DataFrame],
    params: Dict[str, Any],
    seed: int,
) -> List[CandleSignal]:
    """One placebo signal per real signal, with entry bar and side randomised."""
    or_minutes: int = params.get("or_minutes", params.get("warmup_minutes", 15))
    session_start: time = params.get("session_start", SESSION_START)
    flat_by: time = params.get("flat_by", FLAT_BY)

    rng = random.Random(seed)
    placebos: List[CandleSignal] = []

    for orb_signal in real:
        if not orb_signal.triggered:
            continue

        session = sessions.get(orb_signal.session_date)
        if session is None:
            continue

        candidates = post_range_bars(
            session, or_minutes=or_minutes, session_start=session_start, flat_by=flat_by
        )
        if candidates.empty:
            continue

        stop_distance = abs(orb_signal.signal.entry_price - orb_signal.signal.stop_price)

        row = candidates.iloc[rng.randrange(len(candidates))]
        bar_index = int(row["bar_index"])
        entry_price = float(row["close"])

        remaining = bars_until_flat(
            session, bar_index=bar_index, session_start=session_start, flat_by=flat_by
        )
        if remaining < 1:
            continue

        side = rng.choice(["LONG", "SHORT"])
        stop_price = (
            entry_price - stop_distance if side == "LONG" else entry_price + stop_distance
        )
        if stop_price <= 0:
            continue

        placebos.append(
            CandleSignal(
                bar_index=bar_index,
                side=side,
                entry_price=entry_price,
                stop_price=stop_price,
                signal_time=row["ist"].isoformat(),
                max_hold_bars=remaining,
            )
        )

    return placebos


def placebo_percentile(real_avg_net_pnl: float, placebo_avgs: Sequence[float]) -> float:
    """Percentage of placebo runs the real result beat. 100.0 means it beat all."""
    if not placebo_avgs:
        raise ValueError("placebo distribution is empty")
    beaten = sum(1 for value in placebo_avgs if real_avg_net_pnl > value)
    return round(100.0 * beaten / len(placebo_avgs), 2)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_orb_placebo.py -v`
Expected: PASS — 8 tests.

- [ ] **Step 5: Commit**

```bash
git add strategy/orb/placebo.py tests/test_orb_placebo.py
git commit -m "feat: matched placebo signals and percentile ranking"
```

---

### Task 8: Verdict rule

Pure function over cell results. The whole pass/fail decision lives here so it can be tested without any market data.

**Files:**
- Create: `strategy/orb/verdict.py`
- Test: `tests/test_orb_verdict.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orb_verdict.py`:

```python
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.orb.verdict import CellResult, decide_verdict


def _cell(label="headline", headline=True, n=40, base=5.0, stressed=2.0, train=4.0):
    return CellResult(
        label=label,
        is_headline=headline,
        n_trades_test=n,
        avg_net_pnl_test_base=base,
        avg_net_pnl_test_stressed=stressed,
        avg_net_pnl_train_base=train,
    )


def _neighbour(label, base=3.0):
    return _cell(label=label, headline=False, base=base)


def test_all_criteria_met_is_a_pass():
    verdict, reasons = decide_verdict(
        cells=[_cell(), _neighbour("r=1.5"), _neighbour("r=3.0")],
        placebo_percentile=98.0,
        data_source="dhan",
    )
    assert verdict == "PASS"
    assert reasons == []


def test_yfinance_data_is_always_inconclusive():
    verdict, reasons = decide_verdict(
        cells=[_cell()], placebo_percentile=99.0, data_source="yfinance"
    )
    assert verdict == "INCONCLUSIVE"
    assert any("yfinance" in reason for reason in reasons)


def test_too_few_trades_is_inconclusive_not_a_pass():
    verdict, reasons = decide_verdict(
        cells=[_cell(n=29)], placebo_percentile=99.0, data_source="dhan"
    )
    assert verdict == "INCONCLUSIVE"
    assert any("29" in reason for reason in reasons)


def test_negative_at_base_costs_is_a_fail():
    verdict, _ = decide_verdict(
        cells=[_cell(base=-1.0)], placebo_percentile=99.0, data_source="dhan"
    )
    assert verdict == "FAIL"


def test_negative_at_stressed_costs_is_a_fail():
    verdict, _ = decide_verdict(
        cells=[_cell(stressed=-0.5)], placebo_percentile=99.0, data_source="dhan"
    )
    assert verdict == "FAIL"


def test_negative_train_half_is_a_fail():
    verdict, _ = decide_verdict(
        cells=[_cell(train=-2.0)], placebo_percentile=99.0, data_source="dhan"
    )
    assert verdict == "FAIL"


def test_failing_the_placebo_is_a_fail():
    verdict, reasons = decide_verdict(
        cells=[_cell()], placebo_percentile=80.0, data_source="dhan"
    )
    assert verdict == "FAIL"
    assert any("placebo" in reason for reason in reasons)


def test_headline_passing_with_a_negative_neighbour_is_fragile():
    verdict, reasons = decide_verdict(
        cells=[_cell(), _neighbour("k=0.15", base=-0.5), _neighbour("k=0.40")],
        placebo_percentile=99.0,
        data_source="dhan",
    )
    assert verdict == "FRAGILE"
    assert any("k=0.15" in reason for reason in reasons)


def test_missing_headline_cell_is_inconclusive():
    verdict, reasons = decide_verdict(
        cells=[_neighbour("r=1.5")], placebo_percentile=99.0, data_source="dhan"
    )
    assert verdict == "INCONCLUSIVE"
    assert any("headline" in reason for reason in reasons)


def test_missing_placebo_is_inconclusive():
    verdict, reasons = decide_verdict(
        cells=[_cell()], placebo_percentile=None, data_source="dhan"
    )
    assert verdict == "INCONCLUSIVE"
    assert any("placebo" in reason for reason in reasons)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_orb_verdict.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'strategy.orb.verdict'`

- [ ] **Step 3: Write the implementation**

Create `strategy/orb/verdict.py`:

```python
"""
The pre-registered verdict rule, as a pure function.

Frozen before the first run. Changing any threshold here after seeing results
invalidates the test.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

MIN_TRADES = 30
MIN_PLACEBO_PERCENTILE = 95.0

PASS = "PASS"
FRAGILE = "FRAGILE"
FAIL = "FAIL"
INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class CellResult:
    """One point in the robustness grid, already simulated."""

    label: str
    is_headline: bool
    n_trades_test: int
    avg_net_pnl_test_base: float
    avg_net_pnl_test_stressed: float
    avg_net_pnl_train_base: float


def decide_verdict(
    cells: Sequence[CellResult],
    placebo_percentile: Optional[float],
    data_source: str,
    min_trades: int = MIN_TRADES,
) -> Tuple[str, List[str]]:
    """Return (verdict, reasons). Reasons are empty only on a clean PASS."""
    reasons: List[str] = []

    if data_source.lower() == "yfinance":
        return INCONCLUSIVE, [
            "data source is yfinance, which caps intraday history at ~60 days "
            "(~40 sessions) — far too few sessions to conclude anything"
        ]

    headline = next((cell for cell in cells if cell.is_headline), None)
    if headline is None:
        return INCONCLUSIVE, ["no headline cell in the robustness grid"]

    if placebo_percentile is None:
        return INCONCLUSIVE, ["placebo test did not run"]

    if headline.n_trades_test < min_trades:
        return INCONCLUSIVE, [
            f"only {headline.n_trades_test} second-half trades, need {min_trades}"
        ]

    if headline.avg_net_pnl_test_base <= 0:
        reasons.append(
            f"headline avg net P&L at base costs is {headline.avg_net_pnl_test_base:.4f}"
        )
    if headline.avg_net_pnl_test_stressed <= 0:
        reasons.append(
            f"headline avg net P&L at 2x costs is {headline.avg_net_pnl_test_stressed:.4f}"
        )
    if headline.avg_net_pnl_train_base <= 0:
        reasons.append(
            f"first-half avg net P&L is {headline.avg_net_pnl_train_base:.4f}, "
            "so the halves disagree"
        )
    if placebo_percentile < MIN_PLACEBO_PERCENTILE:
        reasons.append(
            f"placebo percentile {placebo_percentile:.1f} is below "
            f"{MIN_PLACEBO_PERCENTILE:.0f} — random entries do about as well"
        )

    if reasons:
        return FAIL, reasons

    fragile = [
        cell.label
        for cell in cells
        if not cell.is_headline and cell.avg_net_pnl_test_base <= 0
    ]
    if fragile:
        return FRAGILE, [
            f"headline passed but neighbour cell {label} is not positive at base costs"
            for label in fragile
        ]

    return PASS, []
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_orb_verdict.py -v`
Expected: PASS — 10 tests.

- [ ] **Step 5: Commit**

```bash
git add strategy/orb/verdict.py tests/test_orb_verdict.py
git commit -m "feat: pre-registered ORB verdict rule"
```

---

### Task 9: Runner

Ties everything together. Takes bars as an argument rather than fetching, so it is fully testable offline.

**Files:**
- Create: `strategy/orb/runner.py`
- Test: `tests/test_orb_runner.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orb_runner.py`:

```python
import sys
from datetime import time
from pathlib import Path

import pandas as pd
import pytest
import pytz

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.orb.runner import ROBUSTNESS_GRID, run_orb

IST = pytz.timezone("Asia/Kolkata")


def _day(day, closes):
    rows = []
    for i, close in enumerate(closes):
        naive = pd.Timestamp(f"{day} 09:15:00") + pd.Timedelta(minutes=5 * i)
        rows.append(
            {
                "timestamp": int(IST.localize(naive.to_pydatetime()).timestamp()),
                "open": close,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": 1000,
            }
        )
    return pd.DataFrame(rows)


def _winning_day(day):
    """Breaks up at bar 3, then keeps running — target is reached."""
    return _day(day, [100.0, 100.0, 100.0, 102.0, 104.0, 108.0, 112.0, 116.0])


def _losing_day(day):
    """Breaks up at bar 3, then collapses through the stop."""
    return _day(day, [100.0, 100.0, 100.0, 102.0, 100.0, 97.0, 95.0, 93.0])


def _quiet_day(day):
    return _day(day, [100.0] * 8)


RUN_KWARGS = dict(
    symbol="TEST",
    variant="A",
    bar_minutes=5,
    flat_by=time(10, 5),
    placebo_seeds=5,
)


def test_grid_has_exactly_one_headline_cell_per_variant():
    for variant in ("A", "B"):
        headlines = [cell for cell in ROBUSTNESS_GRID[variant] if cell["is_headline"]]
        assert len(headlines) == 1, variant


def test_session_accounting_covers_every_session():
    bars = pd.concat([_winning_day("2026-08-03"), _quiet_day("2026-08-04")])
    report = run_orb(bars=bars, daily_bars=None, data_source="synthetic", **RUN_KWARGS)

    accounting = report["sessions"]
    assert accounting["available"] == 2
    assert accounting["traded"] + accounting["skipped"] == accounting["available"]
    assert accounting["skip_reasons"]["no_breakout"] == 1


def test_train_test_split_lands_on_the_expected_boundary():
    days = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"]
    bars = pd.concat([_winning_day(d) for d in days])
    report = run_orb(bars=bars, daily_bars=None, data_source="synthetic", **RUN_KWARGS)

    assert report["split"]["train_dates"] == days[:2]
    assert report["split"]["test_dates"] == days[2:]


def test_a_losing_synthetic_set_is_reported_as_losing():
    """Sign regression. Guards against an inverted P&L making everything look good."""
    days = [f"2026-08-{d:02d}" for d in (3, 4, 5, 6, 7, 10)]
    bars = pd.concat([_losing_day(d) for d in days])
    report = run_orb(bars=bars, daily_bars=None, data_source="synthetic", **RUN_KWARGS)

    headline = report["headline_cell"]
    assert headline["avg_net_pnl_test_base"] < 0
    assert report["verdict"] in {"FAIL", "INCONCLUSIVE"}


def test_yfinance_source_forces_inconclusive_even_when_profitable():
    days = [f"2026-08-{d:02d}" for d in (3, 4, 5, 6, 7, 10)]
    bars = pd.concat([_winning_day(d) for d in days])
    report = run_orb(bars=bars, daily_bars=None, data_source="yfinance", **RUN_KWARGS)

    assert report["verdict"] == "INCONCLUSIVE"
    assert report["preliminary"] is True


def test_report_contains_the_slippage_sweep_and_breakeven():
    days = [f"2026-08-{d:02d}" for d in (3, 4, 5, 6)]
    bars = pd.concat([_winning_day(d) for d in days])
    report = run_orb(bars=bars, daily_bars=None, data_source="synthetic", **RUN_KWARGS)

    assert set(report["slippage_sweep"]) == {0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0}
    assert isinstance(report["breakeven_slippage"], float)


def test_variant_b_requires_daily_bars():
    bars = _winning_day("2026-08-03")
    with pytest.raises(ValueError, match="daily_bars"):
        run_orb(
            bars=bars,
            daily_bars=None,
            data_source="synthetic",
            symbol="TEST",
            variant="B",
            bar_minutes=5,
            flat_by=time(10, 5),
            placebo_seeds=5,
        )


def test_empty_bars_raise_rather_than_reporting_no_trades():
    with pytest.raises(ValueError, match="empty"):
        run_orb(
            bars=pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"]),
            daily_bars=None,
            data_source="synthetic",
            **RUN_KWARGS,
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_orb_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'strategy.orb.runner'`

- [ ] **Step 3: Write the implementation**

Create `strategy/orb/runner.py`:

```python
"""
ORB test orchestration.

Takes bars as an argument rather than fetching them, so the whole pipeline is
testable offline. Fetching lives in scripts/run_orb_test.py.
"""

from collections import Counter
from datetime import date, time
from typing import Any, Dict, List, Optional

import pandas as pd

from analysis.signal_trade_simulator import CandleSignal, simulate_trade_grid
from strategy.orb import variant_a_range, variant_b_noise_band
from strategy.orb.costs import (
    BASE_FEE_RATE,
    BASE_SLIPPAGE,
    SLIPPAGE_SWEEP,
    STRESSED_FEE_RATE,
    STRESSED_SLIPPAGE,
    breakeven_slippage,
)
from strategy.orb.placebo import build_placebo_signals, placebo_percentile
from strategy.orb.session import (
    FLAT_BY,
    SESSION_START,
    add_bar_index,
    split_dates_in_half,
    split_sessions,
)
from strategy.orb.types import OrbSignal
from strategy.orb.verdict import CellResult, decide_verdict

# Declared before any code ran. See the spec's "Robustness grid" section.
ROBUSTNESS_GRID: Dict[str, List[Dict[str, Any]]] = {
    "A": [
        {"label": "or=15,r=2.0", "is_headline": True, "params": {"or_minutes": 15}, "r": 2.0},
        {"label": "or=30,r=2.0", "is_headline": False, "params": {"or_minutes": 30}, "r": 2.0},
        {"label": "or=15,r=1.5", "is_headline": False, "params": {"or_minutes": 15}, "r": 1.5},
        {"label": "or=15,r=3.0", "is_headline": False, "params": {"or_minutes": 15}, "r": 3.0},
    ],
    "B": [
        {"label": "k=0.25,r=2.0", "is_headline": True, "params": {"k": 0.25}, "r": 2.0},
        {"label": "k=0.15,r=2.0", "is_headline": False, "params": {"k": 0.15}, "r": 2.0},
        {"label": "k=0.40,r=2.0", "is_headline": False, "params": {"k": 0.40}, "r": 2.0},
        {"label": "k=0.25,r=1.5", "is_headline": False, "params": {"k": 0.25}, "r": 1.5},
        {"label": "k=0.25,r=3.0", "is_headline": False, "params": {"k": 0.25}, "r": 3.0},
    ],
}

INFO_ONLY_R = 1.0


def run_orb(
    symbol: str,
    variant: str,
    bars: pd.DataFrame,
    daily_bars: Optional[pd.DataFrame],
    data_source: str,
    bar_minutes: int = 5,
    session_start: time = SESSION_START,
    flat_by: time = FLAT_BY,
    atr_length: int = 14,
    placebo_seeds: int = 200,
) -> Dict[str, Any]:
    """Run the full pre-registered test and return a report dict."""
    variant = variant.upper()
    if variant not in ROBUSTNESS_GRID:
        raise ValueError(f"unknown variant {variant!r}, expected 'A' or 'B'")
    if bars is None or bars.empty:
        raise ValueError(f"bars for {symbol} are empty — refusing to report zero trades")
    if variant == "B" and (daily_bars is None or daily_bars.empty):
        raise ValueError("variant B needs daily_bars to compute ATR")

    indexed = add_bar_index(bars)
    sessions = split_sessions(indexed)
    session_dates = sorted(sessions)
    if len(session_dates) < 2:
        raise ValueError(f"need at least 2 sessions, got {len(session_dates)}")

    atr_by_date = _atr_by_date(daily_bars, atr_length) if variant == "B" else {}

    train_dates, test_dates = split_dates_in_half(session_dates)
    candles = indexed[["bar_index", "open", "high", "low", "close"]].copy()
    max_session_bars = max(len(session) for session in sessions.values())

    # Built once. A per-lookup scan would be O(sessions) inside a 200-seed
    # placebo loop, which is slow enough to matter on multi-year data.
    bar_to_session_date: Dict[int, date] = {
        int(bar_index): session_date
        for session_date, session in sessions.items()
        for bar_index in session["bar_index"].tolist()
    }

    cells: List[CellResult] = []
    cell_reports: List[Dict[str, Any]] = []
    headline_context: Optional[Dict[str, Any]] = None

    for cell in ROBUSTNESS_GRID[variant]:
        params = {
            **cell["params"],
            "bar_minutes": bar_minutes,
            "session_start": session_start,
            "flat_by": flat_by,
        }
        orb_signals = _generate_all(variant, sessions, params, atr_by_date)
        fired = [s for s in orb_signals if s.triggered]

        base = _simulate(
            candles, fired, cell["r"], max_session_bars, BASE_SLIPPAGE, BASE_FEE_RATE
        )
        stressed = _simulate(
            candles, fired, cell["r"], max_session_bars, STRESSED_SLIPPAGE, STRESSED_FEE_RATE
        )

        result = CellResult(
            label=cell["label"],
            is_headline=cell["is_headline"],
            n_trades_test=_count(base, test_dates),
            avg_net_pnl_test_base=_avg(base, test_dates),
            avg_net_pnl_test_stressed=_avg(stressed, test_dates),
            avg_net_pnl_train_base=_avg(base, train_dates),
        )
        cells.append(result)
        cell_reports.append(
            {
                "label": result.label,
                "is_headline": result.is_headline,
                "n_trades_test": result.n_trades_test,
                "avg_net_pnl_test_base": result.avg_net_pnl_test_base,
                "avg_net_pnl_test_stressed": result.avg_net_pnl_test_stressed,
                "avg_net_pnl_train_base": result.avg_net_pnl_train_base,
            }
        )

        if cell["is_headline"]:
            headline_context = {
                "orb_signals": orb_signals,
                "fired": fired,
                "params": params,
                "r": cell["r"],
            }

    assert headline_context is not None  # grid always declares one headline

    sweep = {
        slippage: _avg(
            _simulate(
                candles,
                headline_context["fired"],
                headline_context["r"],
                max_session_bars,
                slippage,
                BASE_FEE_RATE,
            ),
            test_dates,
        )
        for slippage in SLIPPAGE_SWEEP
    }

    info_grid = _simulate(
        candles, headline_context["fired"], INFO_ONLY_R, max_session_bars,
        BASE_SLIPPAGE, BASE_FEE_RATE,
    )

    percentile = _run_placebo(
        headline_context=headline_context,
        sessions=sessions,
        candles=candles,
        max_session_bars=max_session_bars,
        test_dates=test_dates,
        bar_to_session_date=bar_to_session_date,
        real_avg=_avg_from_cells(cells),
        seeds=placebo_seeds,
    )

    verdict, reasons = decide_verdict(
        cells=cells, placebo_percentile=percentile, data_source=data_source
    )

    skip_reasons = Counter(
        s.reason for s in headline_context["orb_signals"] if not s.triggered
    )

    return {
        "symbol": symbol,
        "variant": variant,
        "data_source": data_source,
        "preliminary": data_source.lower() == "yfinance",
        "sessions": {
            "available": len(session_dates),
            "traded": len(headline_context["fired"]),
            "skipped": len(session_dates) - len(headline_context["fired"]),
            "skip_reasons": dict(skip_reasons),
        },
        "split": {
            "train_dates": [d.isoformat() for d in train_dates],
            "test_dates": [d.isoformat() for d in test_dates],
        },
        "cells": cell_reports,
        "headline_cell": next(c for c in cell_reports if c["is_headline"]),
        "info_only_r1_avg_net_pnl_test": _avg(info_grid, test_dates),
        "slippage_sweep": sweep,
        "breakeven_slippage": breakeven_slippage(sweep),
        "placebo_percentile": percentile,
        "placebo_seeds": placebo_seeds,
        "fee_rate_base": BASE_FEE_RATE,
        "fee_rate_stressed": STRESSED_FEE_RATE,
        "verdict": verdict,
        "verdict_reasons": reasons,
    }


def _generate_all(
    variant: str,
    sessions: Dict[date, pd.DataFrame],
    params: Dict[str, Any],
    atr_by_date: Dict[date, float],
) -> List[OrbSignal]:
    results: List[OrbSignal] = []
    for session_date in sorted(sessions):
        session = sessions[session_date]
        if variant == "A":
            results.append(variant_a_range.generate_signal(session, params))
        else:
            band_params = {**params, "warmup_minutes": params.get("warmup_minutes", 15)}
            results.append(
                variant_b_noise_band.generate_signal(
                    session, band_params, atr=atr_by_date.get(session_date)
                )
            )
    return results


def _atr_by_date(daily_bars: pd.DataFrame, length: int) -> Dict[date, float]:
    """ATR through YESTERDAY's close, keyed by session date."""
    frame = daily_bars.copy()
    frame["session_date"] = (
        pd.to_datetime(frame["timestamp"], unit="s", utc=True)
        .dt.tz_convert("Asia/Kolkata")
        .dt.date
    )
    frame = frame.sort_values("session_date").reset_index(drop=True)
    atr = variant_b_noise_band.daily_atr(frame, length=length).shift(1)
    return {
        row_date: float(value)
        for row_date, value in zip(frame["session_date"], atr)
        if pd.notna(value)
    }


def _simulate(
    candles: pd.DataFrame,
    fired: List[OrbSignal],
    r_value: float,
    max_hold_bars: int,
    slippage: float,
    fee_rate: float,
) -> List[Dict[str, Any]]:
    """Simulate the fired signals and return trades tagged with their session date."""
    if not fired:
        return []
    signals: List[CandleSignal] = [s.signal for s in fired]
    result = simulate_trade_grid(
        candles=candles,
        signals=signals,
        r_values=[r_value],
        max_hold_bars=max_hold_bars,
        fee_rate=fee_rate,
        slippage_per_side=slippage,
    )
    trades = list(result["best"]["per_signal"].values())
    for trade, orb_signal in zip(trades, fired):
        trade["session_date"] = orb_signal.session_date
    return trades


def _in(trades: List[Dict[str, Any]], dates: List[date]) -> List[Dict[str, Any]]:
    wanted = set(dates)
    return [t for t in trades if t["session_date"] in wanted]


def _count(trades: List[Dict[str, Any]], dates: List[date]) -> int:
    return len(_in(trades, dates))


def _avg(trades: List[Dict[str, Any]], dates: List[date]) -> float:
    selected = _in(trades, dates)
    if not selected:
        return 0.0
    return round(sum(t["net_pnl"] for t in selected) / len(selected), 6)


def _avg_from_cells(cells: List[CellResult]) -> float:
    headline = next(cell for cell in cells if cell.is_headline)
    return headline.avg_net_pnl_test_base


def _run_placebo(
    headline_context: Dict[str, Any],
    sessions: Dict[date, pd.DataFrame],
    candles: pd.DataFrame,
    max_session_bars: int,
    test_dates: List[date],
    bar_to_session_date: Dict[int, date],
    real_avg: float,
    seeds: int,
) -> Optional[float]:
    fired = headline_context["fired"]
    if not fired:
        return None

    averages: List[float] = []
    for seed in range(seeds):
        placebo_signals = build_placebo_signals(
            fired, sessions, headline_context["params"], seed=seed
        )
        if not placebo_signals:
            continue
        result = simulate_trade_grid(
            candles=candles,
            signals=placebo_signals,
            r_values=[headline_context["r"]],
            max_hold_bars=max_session_bars,
            fee_rate=BASE_FEE_RATE,
            slippage_per_side=BASE_SLIPPAGE,
        )
        trades = list(result["best"]["per_signal"].values())
        for trade, signal in zip(trades, placebo_signals):
            trade["session_date"] = bar_to_session_date.get(signal.bar_index)
        averages.append(_avg(trades, test_dates))

    if not averages:
        return None
    return placebo_percentile(real_avg, averages)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_orb_runner.py -v`
Expected: PASS — 8 tests.

- [ ] **Step 5: Run the whole ORB suite**

Run: `python -m pytest tests/test_orb_*.py tests/test_signal_trade_simulator.py -v`
Expected: PASS — 68 tests total (session 8, types 3, variant A 8, variant B 7, costs 6, placebo 8, verdict 10, runner 8, simulator 10).

- [ ] **Step 6: Commit**

```bash
git add strategy/orb/runner.py tests/test_orb_runner.py
git commit -m "feat: ORB runner with robustness grid, slippage sweep and placebo"
```

---

### Task 10: CLI and report

**Files:**
- Create: `scripts/run_orb_test.py`
- Test: `tests/test_run_orb_test_script.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_run_orb_test_script.py`:

```python
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from scripts.run_orb_test import build_parser, render_report


def _report(verdict="PASS", preliminary=False):
    return {
        "symbol": "^NSEI",
        "variant": "A",
        "data_source": "dhan",
        "preliminary": preliminary,
        "sessions": {
            "available": 500,
            "traded": 380,
            "skipped": 120,
            "skip_reasons": {"no_breakout": 118, "degenerate_range": 2},
        },
        "split": {
            "train_dates": ["2024-01-01", "2024-06-01"],
            "test_dates": ["2024-06-02", "2025-01-01"],
        },
        "cells": [
            {
                "label": "or=15,r=2.0",
                "is_headline": True,
                "n_trades_test": 190,
                "avg_net_pnl_test_base": 3.5,
                "avg_net_pnl_test_stressed": 1.5,
                "avg_net_pnl_train_base": 4.0,
            },
            {
                "label": "or=30,r=2.0",
                "is_headline": False,
                "n_trades_test": 180,
                "avg_net_pnl_test_base": 2.0,
                "avg_net_pnl_test_stressed": 0.5,
                "avg_net_pnl_train_base": 2.5,
            },
        ],
        "headline_cell": {
            "label": "or=15,r=2.0",
            "is_headline": True,
            "n_trades_test": 190,
            "avg_net_pnl_test_base": 3.5,
            "avg_net_pnl_test_stressed": 1.5,
            "avg_net_pnl_train_base": 4.0,
        },
        "info_only_r1_avg_net_pnl_test": 1.2,
        "slippage_sweep": {0.0: 5.5, 1.0: 3.5, 2.0: 1.5, 3.0: -0.5},
        "breakeven_slippage": 2.75,
        "placebo_percentile": 98.5,
        "placebo_seeds": 200,
        "fee_rate_base": 0.0003,
        "fee_rate_stressed": 0.0006,
        "verdict": verdict,
        "verdict_reasons": [],
    }


def test_report_leads_with_the_verdict_and_breakeven_slippage():
    text = render_report(_report())

    assert "VERDICT: PASS" in text
    assert "Breakeven slippage" in text
    assert "2.75" in text


def test_report_flags_preliminary_runs_loudly():
    text = render_report(_report(verdict="INCONCLUSIVE", preliminary=True))

    assert "PRELIMINARY — INSUFFICIENT DATA" in text


def test_report_labels_the_fee_rate_as_an_estimate():
    text = render_report(_report())

    assert "estimate" in text.lower()


def test_report_shows_session_accounting_with_reasons():
    text = render_report(_report())

    assert "no_breakout" in text
    assert "380" in text


def test_report_marks_the_info_only_row_as_not_the_verdict():
    text = render_report(_report())

    assert "not the verdict" in text.lower()


def test_parser_requires_symbol_and_variant():
    parser = build_parser()
    args = parser.parse_args(["--symbol", "^NSEI", "--variant", "A"])

    assert args.symbol == "^NSEI"
    assert args.variant == "A"
    assert args.source == "yfinance"


def test_parser_rejects_an_unknown_variant():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--symbol", "^NSEI", "--variant", "Z"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_run_orb_test_script.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.run_orb_test'`

- [ ] **Step 3: Write the implementation**

Create `scripts/run_orb_test.py`:

```python
"""
CLI for the ORB go/no-go test.

Examples:
    python scripts/run_orb_test.py --symbol ^NSEI --variant A
    python scripts/run_orb_test.py --symbol ^NSEI --variant B --source dhan \\
        --start 2022-01-01 --end 2026-08-01 --out reports/orb_nifty_b.md
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.orb.runner import run_orb


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the pre-registered ORB go/no-go test")
    parser.add_argument("--symbol", required=True, help="e.g. ^NSEI or ^NSEBANK")
    parser.add_argument("--variant", required=True, choices=["A", "B"])
    parser.add_argument("--source", default="yfinance", choices=["yfinance", "dhan"])
    parser.add_argument("--interval", default="5", help="TradingView-style interval")
    parser.add_argument("--start", default=None, help="YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD")
    parser.add_argument("--placebo-seeds", type=int, default=200)
    parser.add_argument("--out", default=None, help="Write the report here as markdown")
    return parser


def fetch_bars(
    symbol: str, source: str, interval: str, start: str, end: str
) -> Tuple[pd.DataFrame, Optional[pd.DataFrame]]:
    """Return (intraday_bars, daily_bars). Daily is needed only by variant B."""
    if source == "yfinance":
        from yfinance_client import YFinanceClient

        client = YFinanceClient()
    else:
        from dhan_client import DhanClient

        client = DhanClient()

    intraday = client.fetch_data(symbol, start, end, interval)
    if intraday is None or intraday.empty:
        raise ValueError(
            f"{source} returned no intraday bars for {symbol} between {start} and {end}"
        )

    daily = client.fetch_data(symbol, start, end, "D")
    if daily is None or daily.empty:
        daily = None

    return intraday, daily


def render_report(report: Dict[str, Any]) -> str:
    lines = []
    lines.append(f"# ORB {report['variant']} — {report['symbol']}")
    lines.append("")

    if report["preliminary"]:
        lines.append("> **PRELIMINARY — INSUFFICIENT DATA.**")
        lines.append(
            "> Sourced from yfinance, which caps intraday history at roughly 60 days. "
            "The verdict is forced to INCONCLUSIVE regardless of the numbers below."
        )
        lines.append("")

    lines.append(f"## VERDICT: {report['verdict']}")
    lines.append("")
    for reason in report["verdict_reasons"]:
        lines.append(f"- {reason}")
    if report["verdict_reasons"]:
        lines.append("")

    lines.append(f"**Breakeven slippage: {report['breakeven_slippage']} index points per side.**")
    lines.append("")
    lines.append(
        "This is the number to judge margin by — the slippage level at which the edge "
        "reaches zero. Compare it against real execution cost for this instrument."
    )
    lines.append("")

    lines.append("## Sessions")
    lines.append("")
    sessions = report["sessions"]
    lines.append(f"- Available: {sessions['available']}")
    lines.append(f"- Traded: {sessions['traded']}")
    lines.append(f"- Skipped: {sessions['skipped']}")
    for reason, count in sorted(sessions["skip_reasons"].items()):
        lines.append(f"    - {reason}: {count}")
    lines.append("")

    lines.append("## Robustness grid (second half)")
    lines.append("")
    lines.append("| Cell | Headline | Trades | Avg net P&L (base) | Avg net P&L (2x costs) | First half |")
    lines.append("|---|---|---|---|---|---|")
    for cell in report["cells"]:
        lines.append(
            f"| {cell['label']} | {'yes' if cell['is_headline'] else ''} "
            f"| {cell['n_trades_test']} | {cell['avg_net_pnl_test_base']} "
            f"| {cell['avg_net_pnl_test_stressed']} | {cell['avg_net_pnl_train_base']} |"
        )
    lines.append("")
    lines.append(
        f"R = 1.0, second half, base costs: {report['info_only_r1_avg_net_pnl_test']} "
        "— reported for information, **not the verdict**."
    )
    lines.append("")

    lines.append("## Slippage sweep (second half, headline cell)")
    lines.append("")
    lines.append("| Slippage per side | Avg net P&L |")
    lines.append("|---|---|")
    for slippage in sorted(report["slippage_sweep"]):
        lines.append(f"| {slippage} | {report['slippage_sweep'][slippage]} |")
    lines.append("")

    lines.append("## Placebo")
    lines.append("")
    lines.append(
        f"Real result beat {report['placebo_percentile']}% of {report['placebo_seeds']} "
        "random-entry runs. Entries were randomised in bar and direction while holding "
        "stop distance and holding period fixed. The pass bar is 95."
    )
    lines.append("")

    lines.append("## Assumptions")
    lines.append("")
    lines.append(
        f"- Fee rate: {report['fee_rate_base']} base / {report['fee_rate_stressed']} stressed. "
        "This is an **estimate** of NSE brokerage plus STT, exchange charges, stamp duty "
        "and GST, not a measured figure. Refine it against a real contract note."
    )
    lines.append(
        "- Gap-through-stop fills use the exact stop price, which is optimistic. "
        "A strategy that fails under this flattering assumption definitely fails."
    )
    lines.append("")

    return "\n".join(lines)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    end = args.end or datetime.now().strftime("%Y-%m-%d")
    start = args.start or "2020-01-01"

    intraday, daily = fetch_bars(args.symbol, args.source, args.interval, start, end)

    report = run_orb(
        symbol=args.symbol,
        variant=args.variant,
        bars=intraday,
        daily_bars=daily,
        data_source=args.source,
        bar_minutes=int(args.interval) if args.interval.isdigit() else 5,
        placebo_seeds=args.placebo_seeds,
    )

    text = render_report(report)
    print(text)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"\nWritten to {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_run_orb_test_script.py -v`
Expected: PASS — 7 tests.

- [ ] **Step 5: Smoke-test against real yfinance data**

Run: `python scripts/run_orb_test.py --symbol ^NSEI --variant A --placebo-seeds 20`

Expected: a printed report whose header carries `PRELIMINARY — INSUFFICIENT DATA` and whose verdict is `INCONCLUSIVE`. Session counts should be roughly 40 available. If `available` is far from 40, or `traded` is 0, stop and investigate before trusting anything — that is a bug signal, not a finding.

- [ ] **Step 6: Run the whole ORB suite one final time**

Run: `python -m pytest tests/test_orb_*.py tests/test_run_orb_test_script.py tests/test_signal_trade_simulator.py -v`
Expected: PASS — 75 tests total.

- [ ] **Step 7: Commit**

```bash
git add scripts/run_orb_test.py tests/test_run_orb_test_script.py
git commit -m "feat: ORB CLI and verdict report rendering"
```

---

## After the plan

Stage 1 is complete when `python scripts/run_orb_test.py` produces a report against Dhan data with a real verdict.

**Blocked on:** the Dhan API key. Until it is refreshed, every run is stamped `PRELIMINARY` and forced to `INCONCLUSIVE` by design — the pipeline is verifiable but the question stays unanswered.

**If the verdict is FAIL or FRAGILE for both variants:** ORB is closed out. Take the next candidate from the [backlog](../backlog/2026-08-07-strategy-research-backlog.md) — CRT / liquidity sweep is first in line because `strategy/entry_detectors/breach_retest.py` already does most of the work.

**If the verdict is PASS:** Stage 2 begins — re-measure using real 0DTE option premiums through `option_contract_service.enrich_strategy_signals()`. That needs its own spec. Read expiry dates via `OptionSelector.get_expiry_list()`; do not hardcode a weekday.
