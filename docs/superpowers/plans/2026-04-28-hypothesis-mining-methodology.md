# Hypothesis Mining Methodology — Lean MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the data-pipeline and analysis code that lets the user generate a multi-instrument × multi-timeframe event corpus, test the four existing hypotheses plus two new priority hypotheses (Multi-TF Reversal, Post-Breach Pullback Continuation), and arrive at backtest-ready survivors.

**Architecture:** Schema additions to the existing `EventLogger` (instrument/timeframe/extra forward-return horizons), output partitioning in `run_simulation.py`, a new corpus-loop wrapper script, parameterization of the verifier, two new `Hypothesis` subclasses, and a multi-TF `merge_asof` helper. All analysis is Python scripts (no notebooks) for testability. Phase 2 backtest modules are NOT in this plan — they get a follow-up plan once Phase 1 surfaces survivors.

**Tech Stack:** Python 3.x, pandas (already a backend dep), pytest, existing `EventLogger`/`AngularPriceCoverageStudy` infrastructure.

**Spec:** [docs/superpowers/specs/2026-04-28-hypothesis-mining-methodology-design.md](../specs/2026-04-28-hypothesis-mining-methodology-design.md)

---

## File Structure

**Created files:**

| Path | Responsibility |
|---|---|
| `gann-visualizer/backend/scripts/__init__.py` | Make `scripts` a package |
| `gann-visualizer/backend/scripts/run_corpus.py` | Hardcoded list of (instrument, timeframe, dates); loops invoking `run_simulation()` per slice |
| `gann-visualizer/backend/scripts/run_paths.py` | Pure helper for building partitioned run directories |
| `gann-visualizer/backend/analysis/multi_tf_helper.py` | `compute_bar_close_time()` + `merge_asof_htf_to_ltf()` for leak-free multi-TF joins |
| `gann-visualizer/backend/analysis/phase1_edge_test.py` | Phase-1 driver script: loads corpus, runs all hypotheses per slice, writes summary |
| `gann-visualizer/backend/tests/test_event_logger_schema.py` | Schema additions to `Event` dataclass |
| `gann-visualizer/backend/tests/test_event_logger_mfe_mae_horizons.py` | MFE/MAE at 5/10/20/50 horizons |
| `gann-visualizer/backend/tests/test_run_paths.py` | Path-builder helper tests |
| `gann-visualizer/backend/tests/test_multi_tf_helper.py` | Multi-TF merge_asof correctness |
| `gann-visualizer/backend/tests/test_post_breach_pullback_hypothesis.py` | Priority #2 hypothesis |
| `gann-visualizer/backend/tests/test_multi_tf_reversal_hypothesis.py` | Priority #1 hypothesis |
| `gann-visualizer/backend/tests/test_phase1_edge_test_driver.py` | Phase-1 driver smoke test |

**Modified files:**

| Path | Change |
|---|---|
| `gann-visualizer/backend/study_tool/event_logger.py` | Add `instrument`, `timeframe`, `mfe_5`, `mae_5`, `mfe_50`, `mae_50` fields; update `to_dict`, `from_dict`, `export_csv`, `enrich_with_forward_outcomes` |
| `gann-visualizer/backend/run_simulation.py` | Accept `instrument` arg; use `run_paths.build_run_dir()` for output paths |
| `gann-visualizer/backend/analysis/verify_trace_events.py` | Add `--run-dir` argument; read trace/events relative to it; write audit outputs into `<run_dir>/audit/` |
| `gann-visualizer/backend/analysis/strategy_analyzer.py` | Add `MultiTFReversalHypothesis` and `PostBreachPullbackHypothesis` classes |

---

## Conventions used by every task

- **Working directory:** `c:/Dev/GannTesting`. All `pytest` invocations run from `gann-visualizer/backend/` unless noted.
- **Run a test:** `cd gann-visualizer/backend && python -m pytest tests/<test_file>::<test_name> -v`
- **Run all tests:** `cd gann-visualizer/backend && python -m pytest tests/ -v`
- **Imports follow the existing pattern** seen at [tests/test_study.py:1-5](../../gann-visualizer/backend/tests/test_study.py): `sys.path.append(...)` then `from study_tool.x import Y`. Do NOT introduce a new package layout.
- **Commit message format:** `feat: ...` for new behavior, `refactor: ...` for cleanup, `test: ...` for tests. Co-author tag at the end as in recent commits.

---

## Task 1: Add `instrument` and `timeframe` to `Event` dataclass

**Why:** Without these fields, multi-instrument/multi-TF event data is ambiguous downstream.

**Files:**
- Modify: `gann-visualizer/backend/study_tool/event_logger.py:42-99` (Event dataclass + `to_dict` + `from_dict`)
- Modify: `gann-visualizer/backend/study_tool/event_logger.py:156-218` (`log_event` method signature)
- Create: `gann-visualizer/backend/tests/test_event_logger_schema.py`

- [ ] **Step 1.1: Write the failing test**

Create `gann-visualizer/backend/tests/test_event_logger_schema.py`:

```python
import sys
import os
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.event_logger import Event, EventType


def test_event_has_instrument_and_timeframe_fields():
    e = Event(
        timestamp=1700000000,
        event_type=EventType.SUPPORT_TEST,
        instrument="NIFTY",
        timeframe="5m",
    )
    assert e.instrument == "NIFTY"
    assert e.timeframe == "5m"


def test_event_to_dict_includes_instrument_and_timeframe():
    e = Event(
        timestamp=1700000000,
        event_type=EventType.SUPPORT_TEST,
        instrument="BANKNIFTY",
        timeframe="60m",
    )
    d = e.to_dict()
    assert d["instrument"] == "BANKNIFTY"
    assert d["timeframe"] == "60m"


def test_event_from_dict_round_trips_instrument_and_timeframe():
    src = {
        "timestamp": 1700000000,
        "event_type": "SUPPORT_TEST",
        "instrument": "NIFTY",
        "timeframe": "15m",
    }
    e = Event.from_dict(src)
    assert e.instrument == "NIFTY"
    assert e.timeframe == "15m"


def test_event_defaults_instrument_and_timeframe_to_none():
    e = Event(timestamp=1700000000, event_type=EventType.CROSS_UP)
    assert e.instrument is None
    assert e.timeframe is None
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/test_event_logger_schema.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'instrument'`.

- [ ] **Step 1.3: Add fields to the `Event` dataclass**

In `gann-visualizer/backend/study_tool/event_logger.py`, locate the `Event` dataclass (around line 42). Add two new optional fields after the existing `next_angle_line` field (which is around line 68, before the `mfe_10` field at line 71):

```python
    # Identity (for multi-instrument / multi-timeframe corpora)
    instrument: Optional[str] = None
    timeframe: Optional[str] = None
```

The `Event` class file location and ordering: place these two lines immediately after the line `next_angle_line: Optional[str] = None` and immediately before `mfe_10: Optional[float] = None`.

- [ ] **Step 1.4: Update `to_dict()` to emit the new fields**

In the same file, in the `to_dict` method (around line 76), add two entries to the returned dict. Insert these immediately after the existing `"next_angle_line": self.next_angle_line,` line and before the `"mfe_10": self.mfe_10,` line:

```python
            "instrument": self.instrument,
            "timeframe": self.timeframe,
```

- [ ] **Step 1.5: Update `from_dict()` to read the new fields**

In the same file, in the `from_dict` classmethod (around line 101), add two `event.instrument = ...` and `event.timeframe = ...` assignments. Insert immediately after the existing `event.next_angle_line = data.get("next_angle_line")` line:

```python
        event.instrument = data.get("instrument")
        event.timeframe = data.get("timeframe")
```

- [ ] **Step 1.6: Run test to verify it passes**

Run: `cd gann-visualizer/backend && python -m pytest tests/test_event_logger_schema.py -v`
Expected: PASS — all 4 tests green.

- [ ] **Step 1.7: Commit**

```bash
git add gann-visualizer/backend/study_tool/event_logger.py gann-visualizer/backend/tests/test_event_logger_schema.py
git commit -m "$(cat <<'EOF'
feat: add instrument and timeframe fields to Event dataclass

Required for multi-instrument × multi-timeframe corpus generation.
Without these, downstream events from different runs are ambiguous.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Extend MFE/MAE computation to horizons 5 and 50

**Why:** The spec requires forward-return measurement at 5/10/20/50 bar horizons. Currently only 10 and 20 exist.

**Files:**
- Modify: `gann-visualizer/backend/study_tool/event_logger.py:71-74` (Event dataclass MFE/MAE fields)
- Modify: `gann-visualizer/backend/study_tool/event_logger.py:76-99` (`to_dict`)
- Modify: `gann-visualizer/backend/study_tool/event_logger.py:101-132` (`from_dict`)
- Modify: `gann-visualizer/backend/study_tool/event_logger.py:414-471` (`enrich_with_forward_outcomes`)
- Create: `gann-visualizer/backend/tests/test_event_logger_mfe_mae_horizons.py`

- [ ] **Step 2.1: Write the failing test**

Create `gann-visualizer/backend/tests/test_event_logger_mfe_mae_horizons.py`:

```python
import sys
import os
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.event_logger import EventLogger, EventType


def make_candles(prices, start_ts=1700000000, step=300):
    """Build a candle list with the same H/L/C as the provided price list."""
    return [
        {"time": start_ts + i * step, "open": p, "high": p + 1, "low": p - 1, "close": p}
        for i, p in enumerate(prices)
    ]


def test_enrich_computes_mfe_mae_at_5_10_20_50_horizons():
    """Synthetic linear ramp up 50 bars from price 100 to 150.
    For an UP-direction event at bar 0 price=100:
      mfe_5 should be 5 (highest high in next 5 bars is ~105+1)
      mfe_10 should be ~10
      mfe_20 should be ~20
      mfe_50 should be ~49 (clipped to last bar)
    """
    candles = make_candles(list(range(100, 151)))  # 51 bars, prices 100..150

    logger = EventLogger()
    logger.log_event(
        timestamp=candles[0]["time"],
        event_type=EventType.BREACH_CONFIRMED,
        price=100.0,
        direction="up",
    )

    logger.enrich_with_forward_outcomes(candles)
    e = logger.events[0]

    assert e.mfe_5 is not None and e.mfe_5 >= 5.0 and e.mfe_5 <= 7.0
    assert e.mfe_10 is not None and e.mfe_10 >= 10.0 and e.mfe_10 <= 12.0
    assert e.mfe_20 is not None and e.mfe_20 >= 20.0 and e.mfe_20 <= 22.0
    assert e.mfe_50 is not None and e.mfe_50 >= 49.0 and e.mfe_50 <= 51.0


def test_event_to_dict_emits_5_and_50_horizon_keys():
    candles = make_candles(list(range(100, 151)))
    logger = EventLogger()
    logger.log_event(
        timestamp=candles[0]["time"],
        event_type=EventType.BREACH_CONFIRMED,
        price=100.0,
        direction="up",
    )
    logger.enrich_with_forward_outcomes(candles)

    d = logger.events[0].to_dict()
    assert "mfe_5" in d
    assert "mae_5" in d
    assert "mfe_50" in d
    assert "mae_50" in d
```

- [ ] **Step 2.2: Run test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/test_event_logger_mfe_mae_horizons.py -v`
Expected: FAIL — `AttributeError: 'Event' object has no attribute 'mfe_5'`.

- [ ] **Step 2.3: Add new MFE/MAE fields to `Event`**

In `gann-visualizer/backend/study_tool/event_logger.py`, locate the existing MFE/MAE fields in the `Event` dataclass (around line 71). Replace the existing block of 4 fields:

```python
    # Forward-looking outcomes (populated post-simulation)
    mfe_10: Optional[float] = None  # Max Favorable Excursion (next 10 bars)
    mae_10: Optional[float] = None  # Max Adverse Excursion (next 10 bars)
    mfe_20: Optional[float] = None  # Max Favorable Excursion (next 20 bars)
    mae_20: Optional[float] = None  # Max Adverse Excursion (next 20 bars)
```

…with this expanded block of 8 fields:

```python
    # Forward-looking outcomes (populated post-simulation)
    mfe_5: Optional[float] = None
    mae_5: Optional[float] = None
    mfe_10: Optional[float] = None
    mae_10: Optional[float] = None
    mfe_20: Optional[float] = None
    mae_20: Optional[float] = None
    mfe_50: Optional[float] = None
    mae_50: Optional[float] = None
```

- [ ] **Step 2.4: Update `to_dict()` to emit new horizons**

In the `to_dict` method (around line 76), replace the existing block:

```python
            "mfe_10": self.mfe_10,
            "mae_10": self.mae_10,
            "mfe_20": self.mfe_20,
            "mae_20": self.mae_20,
```

…with:

```python
            "mfe_5": self.mfe_5,
            "mae_5": self.mae_5,
            "mfe_10": self.mfe_10,
            "mae_10": self.mae_10,
            "mfe_20": self.mfe_20,
            "mae_20": self.mae_20,
            "mfe_50": self.mfe_50,
            "mae_50": self.mae_50,
```

- [ ] **Step 2.5: Update `from_dict()` to read new horizons**

In the `from_dict` classmethod (around line 101), replace:

```python
        event.mfe_10 = data.get("mfe_10")
        event.mae_10 = data.get("mae_10")
        event.mfe_20 = data.get("mfe_20")
        event.mae_20 = data.get("mae_20")
```

…with:

```python
        event.mfe_5 = data.get("mfe_5")
        event.mae_5 = data.get("mae_5")
        event.mfe_10 = data.get("mfe_10")
        event.mae_10 = data.get("mae_10")
        event.mfe_20 = data.get("mfe_20")
        event.mae_20 = data.get("mae_20")
        event.mfe_50 = data.get("mfe_50")
        event.mae_50 = data.get("mae_50")
```

- [ ] **Step 2.6: Update `enrich_with_forward_outcomes()` to compute new horizons**

In the `enrich_with_forward_outcomes` method (around line 414), locate the last two lines that call `calc_excursions(10)` and `calc_excursions(20)`. Replace these two lines:

```python
            event.mfe_10, event.mae_10 = calc_excursions(10)
            event.mfe_20, event.mae_20 = calc_excursions(20)
```

…with:

```python
            event.mfe_5, event.mae_5 = calc_excursions(5)
            event.mfe_10, event.mae_10 = calc_excursions(10)
            event.mfe_20, event.mae_20 = calc_excursions(20)
            event.mfe_50, event.mae_50 = calc_excursions(50)
```

- [ ] **Step 2.7: Run test to verify it passes**

Run: `cd gann-visualizer/backend && python -m pytest tests/test_event_logger_mfe_mae_horizons.py -v`
Expected: PASS — both tests green.

- [ ] **Step 2.8: Commit**

```bash
git add gann-visualizer/backend/study_tool/event_logger.py gann-visualizer/backend/tests/test_event_logger_mfe_mae_horizons.py
git commit -m "$(cat <<'EOF'
feat: extend MFE/MAE forward-return computation to 5/10/20/50 bar horizons

Spec requires multi-horizon forward returns for hypothesis testing.
Adds mfe_5/mae_5/mfe_50/mae_50 alongside the existing 10/20.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Extend `export_csv` to include new schema columns

**Why:** The new fields must reach disk so downstream analysis can read them.

**Files:**
- Modify: `gann-visualizer/backend/study_tool/event_logger.py:473-551` (`export_csv` method)
- Add new test cases to: `gann-visualizer/backend/tests/test_event_logger_schema.py`

- [ ] **Step 3.1: Add the failing test**

Append to `gann-visualizer/backend/tests/test_event_logger_schema.py`:

```python
import csv
import tempfile
from pathlib import Path


def test_export_csv_includes_instrument_timeframe_and_extra_horizon_columns():
    logger = EventLogger()
    logger.log_event(
        timestamp=1700000000,
        event_type=EventType.SUPPORT_TEST,
        angle_name="0.5",
        price=100.0,
        open_price=99.5,
        high_price=100.5,
        low_price=99.0,
        close_price=100.2,
    )
    # Manually set instrument/timeframe and forward returns
    logger.events[0].instrument = "NIFTY"
    logger.events[0].timeframe = "5m"
    logger.events[0].mfe_5 = 1.1
    logger.events[0].mae_5 = 0.2
    logger.events[0].mfe_50 = 5.5
    logger.events[0].mae_50 = 1.1

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "events.csv"
        logger.export_csv(str(out))
        rows = list(csv.DictReader(out.open()))

    assert len(rows) == 1
    row = rows[0]
    assert row["Instrument"] == "NIFTY"
    assert row["Timeframe"] == "5m"
    assert float(row["MFE_5"]) == 1.1
    assert float(row["MAE_5"]) == 0.2
    assert float(row["MFE_50"]) == 5.5
    assert float(row["MAE_50"]) == 1.1
```

- [ ] **Step 3.2: Run to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/test_event_logger_schema.py::test_export_csv_includes_instrument_timeframe_and_extra_horizon_columns -v`
Expected: FAIL — `KeyError: 'Instrument'` (the column doesn't exist yet).

- [ ] **Step 3.3: Update `export_csv` row dict and fieldnames**

In `gann-visualizer/backend/study_tool/event_logger.py` `export_csv` method (around line 473), locate the `row = {...}` dict (around line 511). Update it as follows.

After the line `"Next_Angle_Line": event.next_angle_line or "",` (around line 528), insert these two new entries:

```python
                "Instrument": event.instrument or "",
                "Timeframe": event.timeframe or "",
```

In the same row dict, replace the existing MFE/MAE block:

```python
                "MFE_10": round(event.mfe_10, 2) if event.mfe_10 is not None else "",
                "MAE_10": round(event.mae_10, 2) if event.mae_10 is not None else "",
                "MFE_20": round(event.mfe_20, 2) if event.mfe_20 is not None else "",
                "MAE_20": round(event.mae_20, 2) if event.mae_20 is not None else "",
```

…with:

```python
                "MFE_5": round(event.mfe_5, 4) if event.mfe_5 is not None else "",
                "MAE_5": round(event.mae_5, 4) if event.mae_5 is not None else "",
                "MFE_10": round(event.mfe_10, 4) if event.mfe_10 is not None else "",
                "MAE_10": round(event.mae_10, 4) if event.mae_10 is not None else "",
                "MFE_20": round(event.mfe_20, 4) if event.mfe_20 is not None else "",
                "MAE_20": round(event.mae_20, 4) if event.mae_20 is not None else "",
                "MFE_50": round(event.mfe_50, 4) if event.mfe_50 is not None else "",
                "MAE_50": round(event.mae_50, 4) if event.mae_50 is not None else "",
```

Now update the `fieldnames` list (around line 542). Replace the existing list:

```python
            fieldnames = ["#", "Time", "Fan", "Fraction", "Price", "Type", "Details",
                          "Open", "High", "Low", "Close", "Active_Angles",
                          "Cluster", "Zone", "Zone_Highest_Close", "Zone_Lowest_Close",
                          "Next_Angle_Line",
                          "MFE_10", "MAE_10", "MFE_20", "MAE_20", "Raw_Timestamp", "Direction"]
```

…with:

```python
            fieldnames = ["#", "Time", "Fan", "Fraction", "Price", "Type", "Details",
                          "Open", "High", "Low", "Close", "Active_Angles",
                          "Cluster", "Zone", "Zone_Highest_Close", "Zone_Lowest_Close",
                          "Next_Angle_Line",
                          "Instrument", "Timeframe",
                          "MFE_5", "MAE_5", "MFE_10", "MAE_10",
                          "MFE_20", "MAE_20", "MFE_50", "MAE_50",
                          "Raw_Timestamp", "Direction"]
```

- [ ] **Step 3.4: Run all event_logger tests**

Run: `cd gann-visualizer/backend && python -m pytest tests/test_event_logger_schema.py tests/test_event_logger_mfe_mae_horizons.py -v`
Expected: PASS — all tests green.

- [ ] **Step 3.5: Commit**

```bash
git add gann-visualizer/backend/study_tool/event_logger.py gann-visualizer/backend/tests/test_event_logger_schema.py
git commit -m "$(cat <<'EOF'
feat: include instrument, timeframe, and 5/50-horizon MFE/MAE in CSV export

Round MFE/MAE to 4 decimal places (was 2) so small forward-returns at
5-bar horizons are not lost to rounding.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Create `run_paths.py` helper for partitioned output paths

**Why:** Run output is currently hardcoded to `simulation_events.csv` etc., overwriting on each run. We need `logs/backend/runs/<instrument>/<timeframe>/<run_id>/`. Extracting the path logic into a tested pure helper keeps `run_simulation.py` unchanged in behavior and easy to integrate.

**Files:**
- Create: `gann-visualizer/backend/scripts/__init__.py` (empty file to mark package)
- Create: `gann-visualizer/backend/scripts/run_paths.py`
- Create: `gann-visualizer/backend/tests/test_run_paths.py`

- [ ] **Step 4.1: Write the failing test**

Create `gann-visualizer/backend/tests/test_run_paths.py`:

```python
import sys
import os
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from pathlib import Path
from scripts.run_paths import build_run_dir, build_run_id


def test_build_run_dir_produces_partitioned_path():
    p = build_run_dir(
        base="/tmp/gann_runs",
        instrument="NIFTY",
        timeframe="5m",
        run_id="2026-04-28_a1b2c3",
    )
    assert isinstance(p, Path)
    assert p.parts[-3:] == ("NIFTY", "5m", "2026-04-28_a1b2c3")


def test_build_run_dir_normalizes_instrument_with_special_chars():
    """`^NSEI` is a yfinance symbol — should be sanitized to a path-safe form."""
    p = build_run_dir(
        base="/tmp/gann_runs",
        instrument="^NSEI",
        timeframe="5m",
        run_id="2026-04-28_a1b2c3",
    )
    assert "^" not in str(p)


def test_build_run_id_has_date_and_short_hash_format():
    rid = build_run_id(commit_hash="a1b2c3d4e5f6")
    assert rid.endswith("_a1b2c3")
    assert len(rid.split("_")[0]) == 10  # YYYY-MM-DD


def test_build_run_id_handles_missing_commit_hash():
    """Outside a git repo, fall back to 'nogit'."""
    rid = build_run_id(commit_hash=None)
    assert rid.endswith("_nogit")
```

- [ ] **Step 4.2: Run test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/test_run_paths.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.run_paths'`.

- [ ] **Step 4.3: Create the package marker**

Create `gann-visualizer/backend/scripts/__init__.py` as an empty file:

```python
```

- [ ] **Step 4.4: Implement `run_paths.py`**

Create `gann-visualizer/backend/scripts/run_paths.py`:

```python
"""Helpers for building partitioned run output directories.

A run directory has the shape:
    <base>/<instrument>/<timeframe>/<run_id>/

run_id has the shape:
    YYYY-MM-DD_<short_hash>     when invoked inside a git repo
    YYYY-MM-DD_nogit            otherwise
"""
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional


_PATH_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]")


def _sanitize(component: str) -> str:
    """Replace any character that is not path-safe with '_'."""
    return _PATH_SAFE_RE.sub("_", component)


def build_run_dir(
    base: str,
    instrument: str,
    timeframe: str,
    run_id: str,
) -> Path:
    """Construct the run output directory path. Does NOT create it on disk."""
    return Path(base) / _sanitize(instrument) / _sanitize(timeframe) / _sanitize(run_id)


def build_run_id(commit_hash: Optional[str] = None) -> str:
    """Return a run_id of the form 'YYYY-MM-DD_<short_hash_or_nogit>'.

    If commit_hash is None, attempt to detect the current git HEAD;
    if that also fails, fall back to '_nogit'.
    """
    date_part = datetime.now().strftime("%Y-%m-%d")
    if commit_hash is None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True, timeout=2,
            )
            commit_hash = result.stdout.strip()
        except Exception:
            commit_hash = None

    short = commit_hash[:6] if commit_hash else "nogit"
    return f"{date_part}_{short}"
```

- [ ] **Step 4.5: Run test to verify it passes**

Run: `cd gann-visualizer/backend && python -m pytest tests/test_run_paths.py -v`
Expected: PASS — all 4 tests green.

- [ ] **Step 4.6: Commit**

```bash
git add gann-visualizer/backend/scripts/__init__.py gann-visualizer/backend/scripts/run_paths.py gann-visualizer/backend/tests/test_run_paths.py
git commit -m "$(cat <<'EOF'
feat: add partitioned run-directory path helper

Pure helper for constructing logs/backend/runs/<instrument>/<timeframe>/<run_id>/
paths so run_simulation can stop overwriting outputs across instruments
and timeframes.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Integrate partitioned output paths into `run_simulation.py`

**Why:** Get every run's outputs into a stable, instrument/TF-partitioned location so `scripts/run_corpus.py` (Task 6) can iterate without conflict.

**Files:**
- Modify: `gann-visualizer/backend/run_simulation.py`

There is no clean way to TDD `run_simulation.py` itself (it's heavily side-effectful). We rely on the helper test from Task 4 plus a manual smoke test at the end of this task.

- [ ] **Step 5.1: Update `run_simulation.py` imports**

In `gann-visualizer/backend/run_simulation.py`, near the top with the existing imports, add:

```python
from scripts.run_paths import build_run_dir, build_run_id
```

- [ ] **Step 5.2: Replace the hardcoded log directory with a partitioned `run_dir`**

Locate the block in `run_simulation()` (around line 224) that builds `log_dir`:

```python
    # Export logs
    log_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "logs", "backend"
    )
    os.makedirs(log_dir, exist_ok=True)
    csv_path = os.path.join(log_dir, "simulation_events.csv")
```

Replace with:

```python
    # Build partitioned run directory: logs/backend/runs/<instrument>/<timeframe>/<run_id>/
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    runs_base = os.path.join(repo_root, "logs", "backend", "runs")
    run_id = build_run_id()
    run_dir = build_run_dir(
        base=runs_base,
        instrument=symbol,
        timeframe=resolution,
        run_id=run_id,
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    csv_path = str(run_dir / "events.csv")
    log_dir = str(run_dir)  # back-compat alias used later in this function
```

- [ ] **Step 5.3: Update `setup_logging()` to write into the run directory**

Note: `setup_logging()` is called at the top of `run_simulation()` *before* we know what the run directory should be. Pragmatic fix: keep the existing `simulation_run.log` in `logs/backend/` (it's a coarse-grained debug log), but ALSO copy it into the run directory at the end.

After `csv_path = str(run_dir / "events.csv")` from the previous step, add:

```python
    # Mirror the session log into the run directory for reproducibility
    import shutil
    session_log_src = os.path.join(repo_root, "logs", "backend", "simulation_run.log")
    session_log_dst = run_dir / "simulation_run.log"
```

Then, near the bottom of `run_simulation()`, just before the final log-line `logging.info(f"Simulation run finished. ...")`, add:

```python
    try:
        shutil.copy2(session_log_src, session_log_dst)
    except Exception as e:
        logging.warning(f"Failed to mirror simulation_run.log to run dir: {e}")
```

- [ ] **Step 5.4: Stamp every emitted Event with instrument and timeframe**

In `run_simulation.py`, after the call to `study.event_logger.enrich_with_forward_outcomes(candles)` (around line 233), add a stamping loop:

```python
    # Stamp every event with instrument and timeframe so multi-instrument
    # corpora are unambiguous downstream.
    for ev in study.event_logger.events:
        ev.instrument = symbol
        ev.timeframe = resolution
```

- [ ] **Step 5.4b: Update the inline CSV writer to emit the new schema columns**

`run_simulation.py` writes its events CSV inline (around lines 252-308) using the frontend's intersection events list, NOT `event_logger.export_csv()`. We keep that inline writer (avoiding the dual-track refactor per spec) but extend it to write `Raw_Timestamp`, `Instrument`, `Timeframe`, and the full set of MFE/MAE horizons.

In the writer header (around line 252):

```python
            writer.writerow(['#', 'Time', 'Fan', 'Fraction', 'Price', 'Type', 'Details',
                             'Open', 'High', 'Low', 'Close', 'Active_Angles',
                             'Cluster', 'Zone', 'Zone_Highest_Close', 'Zone_Lowest_Close',
                             'Next_Angle_Line',
                             'MFE_10', 'MAE_10', 'bars_elapsed'])
```

Replace with:

```python
            writer.writerow(['#', 'Time', 'Fan', 'Fraction', 'Price', 'Type', 'Details',
                             'Open', 'High', 'Low', 'Close', 'Active_Angles',
                             'Cluster', 'Zone', 'Zone_Highest_Close', 'Zone_Lowest_Close',
                             'Next_Angle_Line',
                             'Instrument', 'Timeframe',
                             'MFE_5', 'MAE_5', 'MFE_10', 'MAE_10',
                             'MFE_20', 'MAE_20', 'MFE_50', 'MAE_50',
                             'Raw_Timestamp', 'Direction', 'bar_index', 'bars_elapsed'])
```

Then update the `enriched_events` lookup loop (around line 236) to capture all new horizons:

```python
    enriched_events = {}
    for event in study.event_logger.events:
        key = (event.timestamp, event.price)
        enriched_events[key] = {
            'mfe_5': getattr(event, 'mfe_5', 0) or 0,
            'mae_5': getattr(event, 'mae_5', 0) or 0,
            'mfe_10': getattr(event, 'mfe_10', 0) or 0,
            'mae_10': getattr(event, 'mae_10', 0) or 0,
            'mfe_20': getattr(event, 'mfe_20', 0) or 0,
            'mae_20': getattr(event, 'mae_20', 0) or 0,
            'mfe_50': getattr(event, 'mfe_50', 0) or 0,
            'mae_50': getattr(event, 'mae_50', 0) or 0,
            'bars_elapsed': getattr(event, 'bars_elapsed', 0) or 0,
            'direction': getattr(event, 'direction', '') or '',
        }
```

Replace the existing one (which only captured mfe_10, mae_10, bars_elapsed) with the version above.

Then update the row-write loop (around line 287). Replace this entire `writer.writerow([...])` block:

```python
                writer.writerow([
                    i + 1,
                    dt_str,
                    event.get('fan', ''),
                    event.get('fraction', ''),
                    f"{event.get('price', 0):.2f}",
                    event.get('type', ''),
                    details_str,
                    f"{event.get('open', 0):.2f}",
                    f"{event.get('high', 0):.2f}",
                    f"{event.get('low', 0):.2f}",
                    f"{event.get('close', 0):.2f}",
                    json.dumps(event.get('activeAngles', {})),
                    event.get('cluster', False),
                    event.get('zone', ''),
                    f"{event.get('zoneExtremes', {}).get('highest_close', 0):.2f}" if event.get('zoneExtremes', {}).get('highest_close') else '',
                    f"{event.get('zoneExtremes', {}).get('lowest_close', 0):.2f}" if event.get('zoneExtremes', {}).get('lowest_close') else '',
                    event.get('nextAngleLine', ''),
                    f"{mfe_10:.4f}" if mfe_10 else "0",
                    f"{mae_10:.4f}" if mae_10 else "0",
                    bars_elapsed
                ])
```

…with:

```python
                mfe_5 = enriched.get('mfe_5', 0)
                mae_5 = enriched.get('mae_5', 0)
                mfe_20 = enriched.get('mfe_20', 0)
                mae_20 = enriched.get('mae_20', 0)
                mfe_50 = enriched.get('mfe_50', 0)
                mae_50 = enriched.get('mae_50', 0)
                direction = enriched.get('direction', '')
                bar_idx = event.get('bar_index', '')

                writer.writerow([
                    i + 1,
                    dt_str,
                    event.get('fan', ''),
                    event.get('fraction', ''),
                    f"{event.get('price', 0):.2f}",
                    event.get('type', ''),
                    details_str,
                    f"{event.get('open', 0):.2f}",
                    f"{event.get('high', 0):.2f}",
                    f"{event.get('low', 0):.2f}",
                    f"{event.get('close', 0):.2f}",
                    json.dumps(event.get('activeAngles', {})),
                    event.get('cluster', False),
                    event.get('zone', ''),
                    f"{event.get('zoneExtremes', {}).get('highest_close', 0):.2f}" if event.get('zoneExtremes', {}).get('highest_close') else '',
                    f"{event.get('zoneExtremes', {}).get('lowest_close', 0):.2f}" if event.get('zoneExtremes', {}).get('lowest_close') else '',
                    event.get('nextAngleLine', ''),
                    symbol,
                    resolution,
                    f"{mfe_5:.4f}" if mfe_5 else "0",
                    f"{mae_5:.4f}" if mae_5 else "0",
                    f"{mfe_10:.4f}" if mfe_10 else "0",
                    f"{mae_10:.4f}" if mae_10 else "0",
                    f"{mfe_20:.4f}" if mfe_20 else "0",
                    f"{mae_20:.4f}" if mae_20 else "0",
                    f"{mfe_50:.4f}" if mfe_50 else "0",
                    f"{mae_50:.4f}" if mae_50 else "0",
                    int(event['time']),
                    direction,
                    bar_idx,
                    bars_elapsed,
                ])
```

After the smoke test in Step 5.6, the resulting `events.csv` should have columns matching exactly what the Phase 1 driver and hypothesis tests expect.

- [ ] **Step 5.5: Locate the `replay_trace.log` writer and partition it too**

The `unified_state_machine.py` writes the per-bar trace log. Find where it opens that file. Run:

`cd gann-visualizer/backend && python -m pytest tests/ -v --collect-only 2>&1 | head -5`

Then grep:

```bash
grep -rn "replay_trace.log\|replay_trace" --include="*.py" c:/Dev/GannTesting/gann-visualizer/backend/
```

If `replay_trace.log` is written from a hardcoded path inside `unified_state_machine.py` or `angular_coverage_study.py`, **do not modify those files in this task** — their refactor is large and risky. Instead:

After the existing simulation completes, *copy* the trace log into the run directory:

In `run_simulation.py`, in the same final-block where you copy the session log, add:

```python
    trace_log_src = os.path.join(repo_root, "logs", "backend", "replay_trace.log")
    trace_log_dst = run_dir / "trace.log"
    try:
        if os.path.exists(trace_log_src):
            shutil.copy2(trace_log_src, trace_log_dst)
    except Exception as e:
        logging.warning(f"Failed to mirror replay_trace.log to run dir: {e}")
```

- [ ] **Step 5.6: Smoke test the simulation end-to-end**

Run a tiny simulation with a 1-day window to verify file layout. From `gann-visualizer/backend/`:

```bash
python run_simulation.py --symbol "^NSEI" --resolution 60 --source yfinance --lookback 200
```

Expected:
- A new directory `c:/Dev/GannTesting/logs/backend/runs/_NSEI/60/2026-04-28_<hash>/` exists.
- It contains at minimum: `events.csv`, `simulation_run.log`, `trace.log`.
- `events.csv` first row has `Instrument` and `Timeframe` columns populated with `^NSEI` and `60`.

If the smoke test fails, investigate the exact error before proceeding.

- [ ] **Step 5.7: Commit**

```bash
git add gann-visualizer/backend/run_simulation.py
git commit -m "$(cat <<'EOF'
refactor: partition run_simulation outputs by instrument and timeframe

Outputs now go to logs/backend/runs/<instrument>/<timeframe>/<run_id>/,
preventing cross-run overwrites in multi-instrument corpora. Each event
is also stamped with the instrument and timeframe at write time.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Create `scripts/run_corpus.py` corpus loop wrapper

**Why:** The MVP corpus is NIFTY × BANKNIFTY × {5m, 15m, 60m} × ~6 months. A 30-line loop calling `run_simulation()` is enough.

**Files:**
- Create: `gann-visualizer/backend/scripts/run_corpus.py`

There's no automated test for this script — it's a configuration-driven driver whose output is the file system. Smoke-test by running it with a single short slice.

- [ ] **Step 6.1: Implement `run_corpus.py`**

Create `gann-visualizer/backend/scripts/run_corpus.py`:

```python
"""Generate the MVP corpus: NIFTY × BANKNIFTY × {5m, 15m, 60m} × ~6 months.

Held-out month: 2026-03-28 → 2026-04-28 (most recent month). Excluded here.
In-sample: 2025-09-28 → 2026-03-27 (6 months prior).

Run as a script:
    cd gann-visualizer/backend
    python -m scripts.run_corpus
"""
import logging
import sys
from datetime import datetime
from typing import Iterable, NamedTuple

# Path setup so this can run from anywhere
import os
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from run_simulation import run_simulation


class Slice(NamedTuple):
    instrument: str
    resolution: str
    from_date: str
    to_date: str
    source: str = "yfinance"


# ---------------------------------------------------------------------------
# Corpus definition (edit here to expand)
# ---------------------------------------------------------------------------

# NOTE: BANKNIFTY's yfinance symbol is "^NSEBANK". 5m yfinance history is
# capped at ~60 days — for 5m we shrink the in-sample window accordingly.

IN_SAMPLE_FROM = "2025-09-28"
IN_SAMPLE_TO = "2026-03-27"
SHORT_FROM_5M = "2026-01-28"  # ~60 days back from in-sample end (yfinance 5m limit)
SHORT_TO_5M = "2026-03-27"

CORPUS: list[Slice] = [
    # NIFTY
    Slice("^NSEI", "60", IN_SAMPLE_FROM, IN_SAMPLE_TO),
    Slice("^NSEI", "15", IN_SAMPLE_FROM, IN_SAMPLE_TO),
    Slice("^NSEI", "5",  SHORT_FROM_5M,   SHORT_TO_5M),
    # BANKNIFTY
    Slice("^NSEBANK", "60", IN_SAMPLE_FROM, IN_SAMPLE_TO),
    Slice("^NSEBANK", "15", IN_SAMPLE_FROM, IN_SAMPLE_TO),
    Slice("^NSEBANK", "5",  SHORT_FROM_5M,   SHORT_TO_5M),
]


def run_all(slices: Iterable[Slice]) -> None:
    for s in slices:
        logging.info("=" * 80)
        logging.info(f"CORPUS SLICE: {s.instrument} @ {s.resolution}m  {s.from_date} → {s.to_date}")
        logging.info("=" * 80)
        try:
            run_simulation(
                symbol=s.instrument,
                resolution=s.resolution,
                data_source=s.source,
                from_date=s.from_date,
                to_date=s.to_date,
                lookback_bars=5000,
            )
        except Exception:
            logging.exception(f"Slice failed: {s}. Continuing with next slice.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_all(CORPUS)
    logging.info("Corpus generation complete.")
```

- [ ] **Step 6.2: Smoke-test with a single slice**

Edit `CORPUS` temporarily to a single short slice, e.g., 2 days of NIFTY 60m:

```python
CORPUS: list[Slice] = [
    Slice("^NSEI", "60", "2026-04-20", "2026-04-22"),
]
```

Run: `cd gann-visualizer/backend && python -m scripts.run_corpus`
Expected: a new run directory at `logs/backend/runs/_NSEI/60/<run_id>/` containing `events.csv` etc.

If successful, **revert the CORPUS edit** to the full list before committing.

- [ ] **Step 6.3: Commit**

```bash
git add gann-visualizer/backend/scripts/run_corpus.py
git commit -m "$(cat <<'EOF'
feat: add corpus runner for MVP hypothesis-mining dataset

Hardcoded list of (NIFTY, BANKNIFTY) × (5m, 15m, 60m) over the in-sample
6 months ending 2026-03-27. Held-out month begins 2026-03-28 and is
excluded from corpus generation.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Parameterize `verify_trace_events.py` with `--run-dir`

**Why:** The verifier currently hardcodes paths to `logs/backend/replay_trace.log` and `logs/backend/replay_events.csv`. It needs to accept any `<run_dir>` partition.

**Files:**
- Modify: `gann-visualizer/backend/analysis/verify_trace_events.py:64-72` (path constants)
- Modify: `gann-visualizer/backend/analysis/verify_trace_events.py:897-953` (`main`)

There is no automated test for this — the verifier is itself a verification tool. Smoke-test instead.

- [ ] **Step 7.1: Replace module-level path constants with a function**

In `gann-visualizer/backend/analysis/verify_trace_events.py`, remove the existing module-level constants (around lines 64-72):

```python
TRACE_PATH = Path("c:/Dev/GannTesting/logs/backend/replay_trace.log")
EVENTS_CSV = Path("c:/Dev/GannTesting/logs/backend/replay_events.csv")
OUT_DIR    = Path("c:/Dev/GannTesting/logs/backend/trace_audit/")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_REPORT  = OUT_DIR / "TRACE_AUDIT_REPORT.txt"
OUT_EV_CSV  = OUT_DIR / "EVENT_VERIFICATION.csv"
OUT_EVENTS_ML = OUT_DIR / "events_ml.csv"
OUT_BARS_ML   = OUT_DIR / "bars_ml.csv"
```

…and replace with a helper function at the same location:

```python
def resolve_paths(run_dir: Path) -> dict:
    """Return a dict of paths for a given run directory.

    Keys: 'trace', 'events', 'audit_dir', 'report', 'ev_csv', 'events_ml', 'bars_ml'.
    """
    audit_dir = run_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    return {
        "trace": run_dir / "trace.log",
        "events": run_dir / "events.csv",
        "audit_dir": audit_dir,
        "report": audit_dir / "TRACE_AUDIT_REPORT.txt",
        "ev_csv": audit_dir / "EVENT_VERIFICATION.csv",
        "events_ml": audit_dir / "events_ml.csv",
        "bars_ml": audit_dir / "bars_ml.csv",
    }
```

- [ ] **Step 7.2: Update functions that reference the removed constants**

The functions `generate_report()` and `export_ml_data()` previously referenced the module-level constants `OUT_REPORT`, `OUT_EV_CSV`, `OUT_EVENTS_ML`, `OUT_BARS_ML`. Update their signatures to accept a `paths` dict.

In `generate_report()` (around line 666), change the signature from:

```python
def generate_report(
    trace_bars: List[TraceBar],
    csv_events: List[CSVEvent],
    missed_events: List[dict],
    state_lookup: Dict[Tuple, StateBlock],
    ts_lookup: Dict[str, int],
) -> Tuple[float, float]:
```

…to:

```python
def generate_report(
    trace_bars: List[TraceBar],
    csv_events: List[CSVEvent],
    missed_events: List[dict],
    state_lookup: Dict[Tuple, StateBlock],
    ts_lookup: Dict[str, int],
    paths: dict,
) -> Tuple[float, float]:
```

Inside the function, replace `OUT_EV_CSV` with `paths["ev_csv"]` and `OUT_REPORT` with `paths["report"]`. Also replace the references to `EVENTS_CSV.name` and `TRACE_PATH.name` (used in the report header) with `paths["events"].name` and `paths["trace"].name`.

In `export_ml_data()` (around line 803), change the signature from:

```python
def export_ml_data(
    trace_bars: List[TraceBar],
    csv_events: List[CSVEvent],
    missed_events: List[dict],
    state_lookup: Dict[Tuple, StateBlock],
) -> None:
```

…to:

```python
def export_ml_data(
    trace_bars: List[TraceBar],
    csv_events: List[CSVEvent],
    missed_events: List[dict],
    state_lookup: Dict[Tuple, StateBlock],
    paths: dict,
) -> None:
```

Inside the function, replace `OUT_EVENTS_ML` with `paths["events_ml"]` and `OUT_BARS_ML` with `paths["bars_ml"]`.

- [ ] **Step 7.3: Replace `main()` with a `--run-dir`-aware version**

Replace the existing `main()` function (around line 897) with:

```python
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Verify trace events against CSV for a single run directory")
    parser.add_argument("--run-dir", type=str, required=True,
                        help="Run directory: <base>/<instrument>/<timeframe>/<run_id>/")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        print(f"ERROR: run dir not found: {run_dir}")
        sys.exit(1)

    paths = resolve_paths(run_dir)

    if not paths["events"].exists():
        print(f"ERROR: events CSV not found: {paths['events']}")
        sys.exit(1)
    if not paths["trace"].exists():
        print(f"ERROR: trace log not found: {paths['trace']}")
        sys.exit(1)

    print(f"Run directory: {run_dir}")
    print(f"Reading events CSV: {paths['events']}")
    csv_events = parse_events_csv(paths["events"])
    print(f"  Found {len(csv_events)} events in CSV")

    print(f"Reading trace log: {paths['trace']}")
    trace_bars = parse_trace_log(paths["trace"])
    print(f"  Found {len(trace_bars)} bars in trace log")

    print("Building state block lookup...")
    state_lookup = build_state_lookup(trace_bars)
    print(f"  {len(state_lookup)} state blocks indexed")

    print("Building timestamp lookup...")
    ts_lookup = build_timestamp_lookup(trace_bars)
    print(f"  {len(ts_lookup)} timestamps indexed")

    print("Detecting missed events...")
    missed = detect_missed_events(trace_bars, csv_events, ts_lookup)
    print(f"  {len(missed)} missed events detected")

    print("Generating report...")
    acc_pct, comp_pct = generate_report(trace_bars, csv_events, missed, state_lookup, ts_lookup, paths)
    print(f"  Accuracy: {acc_pct:.1f}%, Completeness: {comp_pct:.1f}%")

    print("Exporting ML data...")
    export_ml_data(trace_bars, csv_events, missed, state_lookup, paths)

    print(f"\nOutputs written to {paths['audit_dir']}")
    print(f"  {paths['report'].name}")
    print(f"  {paths['ev_csv'].name}")
    print(f"  {paths['events_ml'].name}")
    print(f"  {paths['bars_ml'].name}")

    if acc_pct < 100.0 or comp_pct < 100.0:
        sys.exit(2)  # non-zero exit so corpus runners can detect failure
```

- [ ] **Step 7.4: Smoke-test against an existing run directory**

Pick a run directory created earlier (e.g., from Task 5's smoke test). Run:

```bash
cd c:/Dev/GannTesting && python gann-visualizer/backend/analysis/verify_trace_events.py --run-dir logs/backend/runs/_NSEI/60/<run_id>
```

Expected:
- `<run_dir>/audit/TRACE_AUDIT_REPORT.txt` and three other files appear in the audit subdirectory.
- The script prints the accuracy and completeness percentages.

- [ ] **Step 7.5: Commit**

```bash
git add gann-visualizer/backend/analysis/verify_trace_events.py
git commit -m "$(cat <<'EOF'
refactor: parameterize verify_trace_events with --run-dir

Replaces hardcoded paths with a resolve_paths() helper that takes a
single run directory. Audit outputs now live under <run_dir>/audit/,
matching the corpus partitioning. Non-zero exit on PASS failure so
corpus runners can detect bad slices.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Implement `multi_tf_helper.py`

**Why:** Multi-TF Reversal hypothesis joins LTF events to "most recent HTF event with bar already closed." This is the substrate that lets us test multi-TF strategies without engine changes.

**Files:**
- Create: `gann-visualizer/backend/analysis/multi_tf_helper.py`
- Create: `gann-visualizer/backend/tests/test_multi_tf_helper.py`

- [ ] **Step 8.1: Write the failing tests**

Create `gann-visualizer/backend/tests/test_multi_tf_helper.py`:

```python
import sys
import os
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

import pandas as pd
from analysis.multi_tf_helper import (
    timeframe_seconds,
    compute_bar_close_time,
    merge_asof_htf_to_ltf,
)


def test_timeframe_seconds_known_resolutions():
    assert timeframe_seconds("5") == 300
    assert timeframe_seconds("15") == 900
    assert timeframe_seconds("60") == 3600
    assert timeframe_seconds("240") == 14400


def test_timeframe_seconds_with_minute_suffix():
    assert timeframe_seconds("5m") == 300
    assert timeframe_seconds("15m") == 900


def test_compute_bar_close_time_adds_tf_seconds():
    df = pd.DataFrame({
        "Raw_Timestamp": [1700000000, 1700000300, 1700000600],
        "Timeframe": ["5", "5", "5"],
    })
    out = compute_bar_close_time(df)
    assert list(out["bar_close_time"]) == [1700000300, 1700000600, 1700000900]


def test_merge_asof_attaches_most_recent_htf_event_no_lookahead():
    """An LTF event at LTF-bar-close 12:00 should pair with an HTF event whose bar closed at 12:00 or earlier — never with a future one."""
    htf = pd.DataFrame({
        "Raw_Timestamp": [1700000000, 1700003600],   # 11:00, 12:00 in 1h bars
        "Timeframe":     ["60",        "60"],
        "Type":          ["SUPPORT_TEST", "RESISTANCE_TEST"],
        "Fraction":      ["0.5",        "0.5"],
        "Fan":           ["P1 (H1-L1)", "P1 (H1-L1)"],
    })
    htf = compute_bar_close_time(htf)  # close at 12:00 and 13:00

    ltf = pd.DataFrame({
        "Raw_Timestamp": [1700000300, 1700003900, 1700007500],  # 11:05, 12:05, 13:05 (5m)
        "Timeframe":     ["5", "5", "5"],
    })
    ltf = compute_bar_close_time(ltf)  # close at 11:10, 12:10, 13:10

    out = merge_asof_htf_to_ltf(ltf, htf)
    # LTF bar closing at 11:10 -> no HTF bar has closed yet -> NaN HTF context
    assert pd.isna(out.loc[0, "htf_event_type"])
    # LTF bar closing at 12:10 -> most recent closed HTF bar is the one closing at 12:00 (SUPPORT_TEST)
    assert out.loc[1, "htf_event_type"] == "SUPPORT_TEST"
    # LTF bar closing at 13:10 -> most recent closed HTF bar is the one closing at 13:00 (RESISTANCE_TEST)
    assert out.loc[2, "htf_event_type"] == "RESISTANCE_TEST"


def test_merge_asof_only_pairs_same_instrument():
    """Multi-instrument data should not cross-contaminate."""
    htf = pd.DataFrame({
        "Raw_Timestamp": [1700000000],
        "Timeframe": ["60"],
        "Instrument": ["NIFTY"],
        "Type": ["SUPPORT_TEST"],
        "Fraction": ["0.5"],
        "Fan": ["P1 (H1-L1)"],
    })
    htf = compute_bar_close_time(htf)

    ltf = pd.DataFrame({
        "Raw_Timestamp": [1700003900],
        "Timeframe": ["5"],
        "Instrument": ["BANKNIFTY"],   # different instrument!
    })
    ltf = compute_bar_close_time(ltf)

    out = merge_asof_htf_to_ltf(ltf, htf, by="Instrument")
    assert pd.isna(out.loc[0, "htf_event_type"])
```

- [ ] **Step 8.2: Run the test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/test_multi_tf_helper.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'analysis.multi_tf_helper'`.

- [ ] **Step 8.3: Implement `multi_tf_helper.py`**

Create `gann-visualizer/backend/analysis/multi_tf_helper.py`:

```python
"""Multi-timeframe analysis helpers.

These utilities let us test "HTF event triggers LTF entry" hypotheses
WITHOUT introducing a multi-TF context table to the engine. All work
happens in pandas at analysis time.

Key concept: bar_close_time
    Events fire at the close of a bar, but the timestamp the engine emits
    is the bar OPEN. To prevent look-ahead leakage when joining HTF events
    to LTF events, we anchor on bar_close_time = bar_open + timeframe_seconds.
"""
from __future__ import annotations

import pandas as pd
from typing import Optional


_TF_SECONDS = {
    "1": 60,
    "2": 120,
    "3": 180,
    "5": 300,
    "15": 900,
    "30": 1800,
    "60": 3600,
    "240": 14400,
    "D": 86400,
    "1D": 86400,
}


def timeframe_seconds(tf: str) -> int:
    """Convert a timeframe string ('5', '5m', '60', '1D', etc.) to seconds."""
    if tf is None:
        raise ValueError("Timeframe must not be None")
    key = tf.rstrip("mM")  # accept '5m' or '5'
    if key in _TF_SECONDS:
        return _TF_SECONDS[key]
    raise ValueError(f"Unknown timeframe: {tf!r}")


def compute_bar_close_time(df: pd.DataFrame, tf_col: str = "Timeframe", ts_col: str = "Raw_Timestamp") -> pd.DataFrame:
    """Return a copy of df with a new 'bar_close_time' column.

    bar_close_time = bar_open_timestamp + timeframe_seconds(timeframe)

    Required columns: tf_col, ts_col.
    """
    if tf_col not in df.columns:
        raise KeyError(f"Column {tf_col!r} not in DataFrame")
    if ts_col not in df.columns:
        raise KeyError(f"Column {ts_col!r} not in DataFrame")

    out = df.copy()
    out["bar_close_time"] = out.apply(
        lambda r: int(r[ts_col]) + timeframe_seconds(str(r[tf_col])),
        axis=1,
    )
    return out


def merge_asof_htf_to_ltf(
    ltf: pd.DataFrame,
    htf: pd.DataFrame,
    by: Optional[str] = None,
) -> pd.DataFrame:
    """Join each LTF row to the most recent HTF event whose bar has CLOSED.

    Both DataFrames must already have 'bar_close_time' (call compute_bar_close_time first).
    The HTF columns are renamed with an 'htf_' prefix to avoid collision.

    Parameters
    ----------
    ltf : DataFrame
        LTF events with at least 'bar_close_time'.
    htf : DataFrame
        HTF events with at least 'bar_close_time' and the columns to attach.
    by : str, optional
        Column to join on (e.g., 'Instrument') to prevent cross-instrument
        contamination. If None, joins purely on time.
    """
    if "bar_close_time" not in ltf.columns:
        raise KeyError("ltf must have a 'bar_close_time' column (call compute_bar_close_time first)")
    if "bar_close_time" not in htf.columns:
        raise KeyError("htf must have a 'bar_close_time' column (call compute_bar_close_time first)")

    ltf_sorted = ltf.sort_values("bar_close_time").reset_index(drop=True)
    htf_sorted = htf.sort_values("bar_close_time").reset_index(drop=True)

    # Rename HTF columns (other than the join keys) with htf_ prefix
    htf_renamed = htf_sorted.copy()
    rename_map = {}
    keep_cols = {"bar_close_time"}
    if by is not None:
        keep_cols.add(by)
    for c in htf_renamed.columns:
        if c in keep_cols:
            continue
        rename_map[c] = f"htf_{c.lower()}"
    htf_renamed = htf_renamed.rename(columns=rename_map)

    merged = pd.merge_asof(
        ltf_sorted,
        htf_renamed,
        on="bar_close_time",
        by=by,
        direction="backward",
        allow_exact_matches=True,
    )
    return merged
```

- [ ] **Step 8.4: Run tests to verify they pass**

Run: `cd gann-visualizer/backend && python -m pytest tests/test_multi_tf_helper.py -v`
Expected: PASS — all 5 tests green.

- [ ] **Step 8.5: Commit**

```bash
git add gann-visualizer/backend/analysis/multi_tf_helper.py gann-visualizer/backend/tests/test_multi_tf_helper.py
git commit -m "$(cat <<'EOF'
feat: add multi-TF helper for leak-free HTF→LTF event joins

Computes bar_close_time = bar_open + timeframe_seconds and uses
pd.merge_asof(direction='backward') to attach the most recent
already-closed HTF event to each LTF event. The 'by' parameter
prevents cross-instrument contamination.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Implement `PostBreachPullbackHypothesis`

**Why:** Priority hypothesis #2 (single-TF, simpler — implement before the multi-TF one).

**Files:**
- Modify: `gann-visualizer/backend/analysis/strategy_analyzer.py` (add new class)
- Create: `gann-visualizer/backend/tests/test_post_breach_pullback_hypothesis.py`

- [ ] **Step 9.1: Write the failing test**

Create `gann-visualizer/backend/tests/test_post_breach_pullback_hypothesis.py`:

```python
import sys
import os
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

import pandas as pd
from analysis.strategy_analyzer import PostBreachPullbackHypothesis


def _row(bar, ts, fan, frac, etype, mfe10, mae10, **extra):
    base = {
        "bar_index": bar,
        "Raw_Timestamp": ts,
        "Fan": fan,
        "Fraction": frac,
        "Type": etype,
        "Direction": extra.get("direction", ""),
        "MFE_5": extra.get("mfe5", 0.0),
        "MAE_5": extra.get("mae5", 0.0),
        "MFE_10": mfe10,
        "MAE_10": mae10,
        "MFE_20": extra.get("mfe20", mfe10),
        "MAE_20": extra.get("mae20", mae10),
        "MFE_50": extra.get("mfe50", mfe10),
        "MAE_50": extra.get("mae50", mae10),
        "Open": extra.get("open", 100.0),
        "High": extra.get("high", 101.0),
        "Low": extra.get("low", 99.0),
        "Close": extra.get("close", 100.5),
    }
    return base


def test_pullback_pair_within_window_is_identified():
    """A BREACH_CONFIRMED UP at bar 5 followed by a SUPPORT_TEST on the same line at bar 8 (within N=10) should be a qualifying entry."""
    rows = [
        _row(5, 1700000000, "P1 (H1-L1)", "0.5", "BREACH_CONFIRMED", 0, 0, direction="up"),
        _row(8, 1700001500, "P1 (H1-L1)", "0.5", "SUPPORT_TEST", 5.0, 1.0),
    ]
    df = pd.DataFrame(rows)
    h = PostBreachPullbackHypothesis()
    h.set_parameters(pullback_window_bars=10)

    result = h.evaluate(df)
    assert result["sample_size"] == 1
    assert result["win_rate"] >= 0.0


def test_pullback_pair_outside_window_ignored():
    """A SUPPORT_TEST that arrives 11 bars after the breach is too late."""
    rows = [
        _row(5, 1700000000, "P1 (H1-L1)", "0.5", "BREACH_CONFIRMED", 0, 0, direction="up"),
        _row(17, 1700004500, "P1 (H1-L1)", "0.5", "SUPPORT_TEST", 5.0, 1.0),
    ]
    df = pd.DataFrame(rows)
    h = PostBreachPullbackHypothesis()
    h.set_parameters(pullback_window_bars=10)

    result = h.evaluate(df)
    assert result["sample_size"] == 0


def test_pullback_pair_wrong_direction_ignored():
    """An UP-breach paired with a RESISTANCE_TEST is not a continuation entry."""
    rows = [
        _row(5, 1700000000, "P1 (H1-L1)", "0.5", "BREACH_CONFIRMED", 0, 0, direction="up"),
        _row(8, 1700001500, "P1 (H1-L1)", "0.5", "RESISTANCE_TEST", 5.0, 1.0),
    ]
    df = pd.DataFrame(rows)
    h = PostBreachPullbackHypothesis()
    h.set_parameters(pullback_window_bars=10)

    result = h.evaluate(df)
    assert result["sample_size"] == 0


def test_pullback_pair_different_line_ignored():
    """The pullback must be on the SAME (fan, fraction) as the breach."""
    rows = [
        _row(5, 1700000000, "P1 (H1-L1)", "0.5", "BREACH_CONFIRMED", 0, 0, direction="up"),
        _row(8, 1700001500, "P1 (H1-L1)", "0.75", "SUPPORT_TEST", 5.0, 1.0),
    ]
    df = pd.DataFrame(rows)
    h = PostBreachPullbackHypothesis()
    h.set_parameters(pullback_window_bars=10)

    result = h.evaluate(df)
    assert result["sample_size"] == 0


def test_returns_required_keys():
    rows = [
        _row(5, 1700000000, "P1 (H1-L1)", "0.5", "BREACH_CONFIRMED", 0, 0, direction="up"),
        _row(8, 1700001500, "P1 (H1-L1)", "0.5", "SUPPORT_TEST", 5.0, 1.0),
    ]
    df = pd.DataFrame(rows)
    result = PostBreachPullbackHypothesis().evaluate(df)
    for key in ("sample_size", "win_rate", "avg_mfe_10", "avg_mae_10"):
        assert key in result
```

- [ ] **Step 9.2: Run test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/test_post_breach_pullback_hypothesis.py -v`
Expected: FAIL — `ImportError: cannot import name 'PostBreachPullbackHypothesis' from 'analysis.strategy_analyzer'`.

- [ ] **Step 9.3: Implement `PostBreachPullbackHypothesis`**

In `gann-visualizer/backend/analysis/strategy_analyzer.py`, append the following class to the end of the file:

```python
class PostBreachPullbackHypothesis(Hypothesis):
    """Continuation entry: enter on the re-test of a breached angle line.

    Trigger sequence (single TF):
      1. BREACH_CONFIRMED on (fan F, line X) in direction D.
      2. Within the next N bars, a SUPPORT_TEST (D=up) or RESISTANCE_TEST (D=down)
         on the SAME (F, X).

    See spec §3.2.1 priority #2 for the full hypothesis specification.
    """
    def __init__(self):
        super().__init__(
            name="Post-Breach Pullback Continuation",
            description="Re-test of a breached line is a continuation entry in the breach direction.",
        )
        self.set_parameters(
            pullback_window_bars=10,
            min_mfe_reward_ratio=2.0,
        )

    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        if df.empty:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0}

        breaches = df[df["Type"] == "BREACH_CONFIRMED"].copy()
        if breaches.empty:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0}

        # Index tests by (Fan, Fraction) for fast lookup
        tests = df[df["Type"].isin(["SUPPORT_TEST", "RESISTANCE_TEST"])].copy()

        N = int(self.parameters["pullback_window_bars"])
        ratio = float(self.parameters["min_mfe_reward_ratio"])

        qualifying_entries = []

        for _, brc in breaches.iterrows():
            direction = str(brc.get("Direction", "")).lower()
            same_line_mask = (
                (tests["Fan"] == brc["Fan"])
                & (tests["Fraction"] == brc["Fraction"])
                & (tests["bar_index"] > brc["bar_index"])
                & (tests["bar_index"] <= brc["bar_index"] + N)
            )
            candidates = tests[same_line_mask]

            for _, test in candidates.iterrows():
                if direction == "up" and test["Type"] == "SUPPORT_TEST":
                    qualifying_entries.append(test)
                elif direction == "down" and test["Type"] == "RESISTANCE_TEST":
                    qualifying_entries.append(test)

        if not qualifying_entries:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0}

        wins = 0
        total_mfe = 0.0
        total_mae = 0.0
        for entry in qualifying_entries:
            mfe = float(entry.get("MFE_10", 0.0) or 0.0)
            mae = float(entry.get("MAE_10", 0.0) or 0.0)
            safe_mae = max(mae, 0.1)
            if mfe > safe_mae * ratio:
                wins += 1
            total_mfe += mfe
            total_mae += mae

        n = len(qualifying_entries)
        return {
            "sample_size": n,
            "win_rate": wins / n,
            "avg_mfe_10": total_mfe / n,
            "avg_mae_10": total_mae / n,
        }
```

- [ ] **Step 9.4: Run tests to verify they pass**

Run: `cd gann-visualizer/backend && python -m pytest tests/test_post_breach_pullback_hypothesis.py -v`
Expected: PASS — all 5 tests green.

- [ ] **Step 9.5: Commit**

```bash
git add gann-visualizer/backend/analysis/strategy_analyzer.py gann-visualizer/backend/tests/test_post_breach_pullback_hypothesis.py
git commit -m "$(cat <<'EOF'
feat: add PostBreachPullbackHypothesis for priority hypothesis #2

Identifies BREACH_CONFIRMED → same-line SUPPORT_TEST/RESISTANCE_TEST
sequences within a configurable pullback window. The qualifying
SUPPORT_TEST (after up-breach) or RESISTANCE_TEST (after down-breach)
is the continuation entry candidate.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Implement `MultiTFReversalHypothesis`

**Why:** Priority hypothesis #1 — depends on `multi_tf_helper` from Task 8.

**Files:**
- Modify: `gann-visualizer/backend/analysis/strategy_analyzer.py` (add new class)
- Create: `gann-visualizer/backend/tests/test_multi_tf_reversal_hypothesis.py`

- [ ] **Step 10.1: Write the failing test**

Create `gann-visualizer/backend/tests/test_multi_tf_reversal_hypothesis.py`:

```python
import sys
import os
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

import pandas as pd
from analysis.strategy_analyzer import MultiTFReversalHypothesis


def _ev(ts, fan, frac, etype, tf, instrument="NIFTY", mfe10=0.0, mae10=0.0,
        body=0.6, open_=100.0, high=101.0, low=99.0, close=100.6):
    return {
        "Raw_Timestamp": ts,
        "Fan": fan,
        "Fraction": frac,
        "Type": etype,
        "Timeframe": tf,
        "Instrument": instrument,
        "MFE_5": mfe10 * 0.5,
        "MAE_5": mae10 * 0.5,
        "MFE_10": mfe10,
        "MAE_10": mae10,
        "MFE_20": mfe10 * 1.5,
        "MAE_20": mae10 * 1.5,
        "MFE_50": mfe10 * 2,
        "MAE_50": mae10 * 2,
        "Open": open_,
        "High": high,
        "Low": low,
        "Close": close,
    }


def test_qualifying_ltf_entry_after_htf_support_test():
    """HTF (60m) SUPPORT_TEST on 0.5 closes at 12:00.
       LTF (5m) bar at 12:05–12:10 closes bullish with body>50%.
       Hypothesis should identify this as a long entry candidate.
    """
    htf = pd.DataFrame([
        _ev(1700003600, "P1 (H1-L1)", "0.5", "SUPPORT_TEST", "60"),  # closes at 13:00
    ])
    # Wait — Raw_Timestamp is bar OPEN, so close = open + 3600 for 60m
    # 1700000000 = 11:00 open -> close at 12:00
    # We want HTF that closes at 12:00, so its open is 1700000000 - 3600 ... let me redo:
    htf = pd.DataFrame([
        _ev(1700000000, "P1 (H1-L1)", "0.5", "SUPPORT_TEST", "60"),  # open 11:00, close 12:00
    ])
    ltf = pd.DataFrame([
        # 12:05 5m bar (open) closes 12:10 — within 1 HTF bar of HTF close at 12:00
        _ev(1700003700, "P1 (H1-L1)", "0.875", "TOUCH", "5",
            body=0.7, open_=100.0, high=101.5, low=99.5, close=101.05, mfe10=2.0, mae10=0.4),
    ])

    h = MultiTFReversalHypothesis()
    h.set_parameters(htf="60", ltf="5", line_filter="0.5", entry_window_htf_bars=1, body_ratio_min=0.5)

    result = h.evaluate(ltf, htf)
    assert result["sample_size"] >= 1
    assert "win_rate" in result


def test_no_qualifying_entry_when_htf_event_too_old():
    """LTF bar more than entry_window_htf_bars after HTF close should not qualify."""
    htf = pd.DataFrame([
        _ev(1700000000, "P1 (H1-L1)", "0.5", "SUPPORT_TEST", "60"),  # closes at 12:00
    ])
    ltf = pd.DataFrame([
        # 13:30 — 1.5 hours after HTF close, well outside 1 HTF-bar window
        _ev(1700008000, "P1 (H1-L1)", "0.875", "TOUCH", "5",
            body=0.7, open_=100.0, high=101.5, low=99.5, close=101.05),
    ])
    h = MultiTFReversalHypothesis()
    h.set_parameters(htf="60", ltf="5", line_filter="0.5", entry_window_htf_bars=1, body_ratio_min=0.5)

    result = h.evaluate(ltf, htf)
    assert result["sample_size"] == 0


def test_no_qualifying_entry_when_htf_line_filter_does_not_match():
    """HTF event on 0.75 line should not trigger (line_filter='0.5' default)."""
    htf = pd.DataFrame([
        _ev(1700000000, "P1 (H1-L1)", "0.75", "SUPPORT_TEST", "60"),  # WRONG LINE
    ])
    ltf = pd.DataFrame([
        _ev(1700003700, "P1 (H1-L1)", "0.875", "TOUCH", "5",
            body=0.7, open_=100.0, high=101.5, low=99.5, close=101.05),
    ])
    h = MultiTFReversalHypothesis()
    h.set_parameters(htf="60", ltf="5", line_filter="0.5", entry_window_htf_bars=1, body_ratio_min=0.5)

    result = h.evaluate(ltf, htf)
    assert result["sample_size"] == 0


def test_no_qualifying_entry_when_ltf_body_ratio_too_small():
    """LTF doji-like bar (body < body_ratio_min) should not trigger."""
    htf = pd.DataFrame([
        _ev(1700000000, "P1 (H1-L1)", "0.5", "SUPPORT_TEST", "60"),
    ])
    ltf = pd.DataFrame([
        # body = abs(close-open) / (high-low) = abs(100.05-100)/2.0 = 0.025
        _ev(1700003700, "P1 (H1-L1)", "0.875", "TOUCH", "5",
            open_=100.0, high=101.0, low=99.0, close=100.05),
    ])
    h = MultiTFReversalHypothesis()
    h.set_parameters(htf="60", ltf="5", line_filter="0.5", entry_window_htf_bars=1, body_ratio_min=0.5)

    result = h.evaluate(ltf, htf)
    assert result["sample_size"] == 0
```

- [ ] **Step 10.2: Run test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/test_multi_tf_reversal_hypothesis.py -v`
Expected: FAIL — `ImportError: cannot import name 'MultiTFReversalHypothesis'`.

- [ ] **Step 10.3: Implement `MultiTFReversalHypothesis`**

In `gann-visualizer/backend/analysis/strategy_analyzer.py`, append the following class to the end of the file:

```python
class MultiTFReversalHypothesis(Hypothesis):
    """HTF respect of a major angle line triggers LTF reversal entry.

    Trigger sequence:
      1. HTF event ∈ {SUPPORT_TEST, RESISTANCE_TEST} on a fan line whose
         fraction matches `line_filter` (default "0.5").
      2. Within `entry_window_htf_bars` HTF-bar durations after the HTF
         close, an LTF bar that:
           - closes in the trigger direction (long if HTF SUPPORT_TEST,
             short if HTF RESISTANCE_TEST), AND
           - has body/range ratio ≥ `body_ratio_min`.

    See spec §3.2.1 priority #1 for the full hypothesis specification.

    Note: this class takes TWO DataFrames (LTF events, HTF events) — unlike
    the single-DataFrame hypotheses. The base Hypothesis.evaluate(df) signature
    is preserved for compatibility but here `df` is the LTF DataFrame and
    HTF events are passed as a second positional argument.
    """
    def __init__(self):
        super().__init__(
            name="Multi-TF Reversal",
            description="HTF respect of a major angle line triggers LTF reversal entry.",
        )
        self.set_parameters(
            htf="60",
            ltf="5",
            line_filter="0.5",
            entry_window_htf_bars=1,
            body_ratio_min=0.5,
            min_mfe_reward_ratio=2.0,
        )

    def evaluate(self, ltf: pd.DataFrame, htf: pd.DataFrame = None) -> Dict[str, Any]:
        from analysis.multi_tf_helper import compute_bar_close_time, merge_asof_htf_to_ltf, timeframe_seconds

        if htf is None or ltf.empty or htf.empty:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0}

        line_filter = str(self.parameters["line_filter"])
        body_ratio_min = float(self.parameters["body_ratio_min"])
        entry_window_htf_bars = int(self.parameters["entry_window_htf_bars"])
        ratio = float(self.parameters["min_mfe_reward_ratio"])
        htf_tf = str(self.parameters["htf"])
        htf_bar_seconds = timeframe_seconds(htf_tf)

        # Filter HTF to qualifying triggers only (right line + right event type)
        htf_filtered = htf[
            (htf["Type"].isin(["SUPPORT_TEST", "RESISTANCE_TEST"]))
            & (htf["Fraction"].astype(str) == line_filter)
        ].copy()
        if htf_filtered.empty:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0}

        # Compute bar_close_time on both
        ltf_bc = compute_bar_close_time(ltf)
        htf_bc = compute_bar_close_time(htf_filtered)

        # Multi-instrument 'by' parameter if column present in both
        join_by = "Instrument" if ("Instrument" in ltf.columns and "Instrument" in htf.columns) else None

        merged = merge_asof_htf_to_ltf(ltf_bc, htf_bc, by=join_by)

        # Apply window: LTF bar_close_time must be within entry_window_htf_bars
        # of the HTF event's bar_close_time. Note: HTF context is attached as 'htf_bar_close_time'.
        if "htf_bar_close_time" in merged.columns:
            window_seconds = entry_window_htf_bars * htf_bar_seconds
            time_gap = merged["bar_close_time"] - merged["htf_bar_close_time"]
            in_window = (time_gap >= 0) & (time_gap <= window_seconds)
        else:
            in_window = pd.Series([False] * len(merged), index=merged.index)

        # Body ratio filter
        rng = (merged["High"] - merged["Low"]).replace(0, 1e-9)
        body = (merged["Close"] - merged["Open"]).abs()
        body_ok = (body / rng) >= body_ratio_min

        # Direction filter: HTF SUPPORT_TEST → look long → LTF must close > open
        # HTF RESISTANCE_TEST → look short → LTF must close < open
        htf_type = merged["htf_type"] if "htf_type" in merged.columns else pd.Series([None] * len(merged), index=merged.index)
        long_signal = (htf_type == "SUPPORT_TEST") & (merged["Close"] > merged["Open"])
        short_signal = (htf_type == "RESISTANCE_TEST") & (merged["Close"] < merged["Open"])
        direction_ok = long_signal | short_signal

        qualifying = merged[in_window & body_ok & direction_ok]

        if qualifying.empty:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0}

        wins = 0
        total_mfe = 0.0
        total_mae = 0.0
        for _, row in qualifying.iterrows():
            mfe = float(row.get("MFE_10", 0.0) or 0.0)
            mae = float(row.get("MAE_10", 0.0) or 0.0)
            safe_mae = max(mae, 0.1)
            if mfe > safe_mae * ratio:
                wins += 1
            total_mfe += mfe
            total_mae += mae

        n = len(qualifying)
        return {
            "sample_size": n,
            "win_rate": wins / n,
            "avg_mfe_10": total_mfe / n,
            "avg_mae_10": total_mae / n,
        }
```

- [ ] **Step 10.4: Run tests to verify they pass**

Run: `cd gann-visualizer/backend && python -m pytest tests/test_multi_tf_reversal_hypothesis.py -v`
Expected: PASS — all 4 tests green.

- [ ] **Step 10.5: Commit**

```bash
git add gann-visualizer/backend/analysis/strategy_analyzer.py gann-visualizer/backend/tests/test_multi_tf_reversal_hypothesis.py
git commit -m "$(cat <<'EOF'
feat: add MultiTFReversalHypothesis for priority hypothesis #1

Joins LTF events to most-recent-closed HTF events via merge_asof_htf_to_ltf,
filters to HTF SUPPORT_TEST/RESISTANCE_TEST on a configurable line
(default 0.5), and requires a confirming LTF body in the trigger direction
within entry_window_htf_bars of HTF close.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Implement `phase1_edge_test.py` driver

**Why:** A single Python script that loads every slice of the corpus, runs all hypotheses, and writes a summary table. Replaces the planned notebook with a testable script.

**Files:**
- Create: `gann-visualizer/backend/analysis/phase1_edge_test.py`
- Create: `gann-visualizer/backend/tests/test_phase1_edge_test_driver.py`

- [ ] **Step 11.1: Write the failing test**

Create `gann-visualizer/backend/tests/test_phase1_edge_test_driver.py`:

```python
import sys
import os
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

import csv
import tempfile
from pathlib import Path
from analysis.phase1_edge_test import discover_slices, run_phase1


def _write_minimal_events_csv(path: Path, instrument: str, timeframe: str):
    """Write a tiny events.csv with the schema produced by EventLogger.export_csv."""
    fieldnames = [
        "#", "Time", "Fan", "Fraction", "Price", "Type", "Details",
        "Open", "High", "Low", "Close", "Active_Angles",
        "Cluster", "Zone", "Zone_Highest_Close", "Zone_Lowest_Close",
        "Next_Angle_Line",
        "Instrument", "Timeframe",
        "MFE_5", "MAE_5", "MFE_10", "MAE_10",
        "MFE_20", "MAE_20", "MFE_50", "MAE_50",
        "Raw_Timestamp", "Direction",
    ]
    rows = [
        {f: "" for f in fieldnames},
        {f: "" for f in fieldnames},
    ]
    rows[0].update({
        "#": 1, "Time": "1/1/2026, 10:00:00 AM", "Fan": "P1 (H1-L1)",
        "Fraction": "0.5", "Price": 100.0, "Type": "BREACH_CONFIRMED",
        "Open": 99.5, "High": 100.5, "Low": 99.0, "Close": 100.5,
        "Instrument": instrument, "Timeframe": timeframe,
        "Raw_Timestamp": 1700000000, "Direction": "up",
        "MFE_10": 0.0, "MAE_10": 0.0, "bar_index": 1,
    })
    rows[1].update({
        "#": 2, "Time": "1/1/2026, 10:30:00 AM", "Fan": "P1 (H1-L1)",
        "Fraction": "0.5", "Price": 100.0, "Type": "SUPPORT_TEST",
        "Open": 100.5, "High": 101.0, "Low": 99.5, "Close": 100.8,
        "Instrument": instrument, "Timeframe": timeframe,
        "Raw_Timestamp": 1700001500, "Direction": "",
        "MFE_10": 5.0, "MAE_10": 1.0, "bar_index": 4,
    })
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames + ["bar_index"])
        w.writeheader()
        w.writerows(rows)


def test_discover_slices_walks_partitioned_runs():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        for inst in ("NIFTY", "BANKNIFTY"):
            for tf in ("5", "60"):
                rd = base / inst / tf / "2026-04-28_abc123"
                rd.mkdir(parents=True)
                (rd / "events.csv").touch()

        slices = discover_slices(str(base))
        assert len(slices) == 4
        # Each entry should be (instrument, timeframe, run_dir)
        for inst, tf, rd in slices:
            assert inst in ("NIFTY", "BANKNIFTY")
            assert tf in ("5", "60")


def test_run_phase1_produces_summary_table_with_required_columns():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        rd = base / "NIFTY" / "60" / "2026-04-28_abc123"
        rd.mkdir(parents=True)
        _write_minimal_events_csv(rd / "events.csv", "NIFTY", "60")

        out_csv = base / "phase1_summary.csv"
        run_phase1(str(base), str(out_csv))

        assert out_csv.exists()
        rows = list(csv.DictReader(out_csv.open()))
        assert len(rows) > 0
        required = {"hypothesis", "instrument", "timeframe", "sample_size", "win_rate"}
        assert required.issubset(rows[0].keys())
```

- [ ] **Step 11.2: Run test to verify it fails**

Run: `cd gann-visualizer/backend && python -m pytest tests/test_phase1_edge_test_driver.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'analysis.phase1_edge_test'`.

- [ ] **Step 11.3: Implement `phase1_edge_test.py`**

Create `gann-visualizer/backend/analysis/phase1_edge_test.py`:

```python
"""Phase 1 driver: load every corpus slice, run all hypotheses, emit summary.

Output columns:
    hypothesis, instrument, timeframe, run_id, sample_size, win_rate,
    avg_mfe_10, avg_mae_10

Usage:
    cd gann-visualizer/backend
    python -m analysis.phase1_edge_test --corpus-base ../../logs/backend/runs --out ../../logs/backend/phase1_summary.csv
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path
from typing import List, Tuple

import pandas as pd

# Ensure backend is on sys.path when run as a script
import os as _os
sys.path.append(_os.path.abspath(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))

from analysis.strategy_analyzer import (
    StrongSRHypothesis,
    TargetProgressionHypothesis,
    QuarterReversalAnomalyHypothesis,
    ConfluenceBounceHypothesis,
    PostBreachPullbackHypothesis,
    MultiTFReversalHypothesis,
)


SECONDARY_HYPOTHESES = [
    StrongSRHypothesis,
    TargetProgressionHypothesis,
    QuarterReversalAnomalyHypothesis,
    ConfluenceBounceHypothesis,
]
PRIORITY_HYPOTHESES = [PostBreachPullbackHypothesis]   # MultiTFReversal handled separately (multi-DF)


def discover_slices(base: str) -> List[Tuple[str, str, Path]]:
    """Walk the partitioned runs tree and return (instrument, timeframe, run_dir) tuples."""
    base_path = Path(base)
    out: List[Tuple[str, str, Path]] = []
    if not base_path.exists():
        return out
    for inst_dir in base_path.iterdir():
        if not inst_dir.is_dir():
            continue
        for tf_dir in inst_dir.iterdir():
            if not tf_dir.is_dir():
                continue
            for run_dir in tf_dir.iterdir():
                if not run_dir.is_dir():
                    continue
                if (run_dir / "events.csv").exists():
                    out.append((inst_dir.name, tf_dir.name, run_dir))
    return out


def _load_events(events_csv: Path) -> pd.DataFrame:
    """Load events.csv into a DataFrame with usable types."""
    df = pd.read_csv(events_csv)
    # Coerce numeric columns we care about
    for col in ("Raw_Timestamp", "MFE_5", "MAE_5", "MFE_10", "MAE_10",
                "MFE_20", "MAE_20", "MFE_50", "MAE_50",
                "Open", "High", "Low", "Close"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # bar_index for hypothesis logic that needs it.
    # Fall back to the '#' row-number column if bar_index is absent or all-NaN.
    if "bar_index" in df.columns:
        df["bar_index"] = pd.to_numeric(df["bar_index"], errors="coerce")
    if ("bar_index" not in df.columns) or df["bar_index"].isna().all():
        if "#" in df.columns:
            df["bar_index"] = pd.to_numeric(df["#"], errors="coerce")
        else:
            df["bar_index"] = range(len(df))
    return df


def run_phase1(corpus_base: str, out_path: str) -> None:
    """Run all hypotheses on every slice; write summary CSV."""
    slices = discover_slices(corpus_base)
    logging.info(f"Discovered {len(slices)} slice(s) under {corpus_base}")

    # Group slices by instrument so multi-TF can pair HTF and LTF
    by_inst: dict[str, list] = {}
    for inst, tf, rd in slices:
        by_inst.setdefault(inst, []).append((tf, rd))

    rows = []

    # 1. Single-DF hypotheses: priority + secondary, run per slice
    for inst, tf, rd in slices:
        try:
            df = _load_events(rd / "events.csv")
        except Exception as e:
            logging.exception(f"Failed loading {rd}: {e}")
            continue

        for hcls in PRIORITY_HYPOTHESES + SECONDARY_HYPOTHESES:
            try:
                h = hcls()
                result = h.evaluate(df)
                rows.append({
                    "hypothesis": h.name,
                    "instrument": inst,
                    "timeframe": tf,
                    "run_id": rd.name,
                    "sample_size": result.get("sample_size", 0),
                    "win_rate": result.get("win_rate", 0.0),
                    "avg_mfe_10": result.get("avg_mfe_10", 0.0),
                    "avg_mae_10": result.get("avg_mae_10", 0.0),
                })
            except Exception as e:
                logging.exception(f"Hypothesis {hcls.__name__} failed on {rd}: {e}")

    # 2. Multi-TF Reversal: pair each LTF with the highest-TF HTF for the same instrument
    # Pairs to try: (5, 60), (15, 60). Skip if either side is missing.
    for inst, tf_runs in by_inst.items():
        tf_to_run = dict(tf_runs)
        for ltf_tf in ("5", "15"):
            for htf_tf in ("60",):
                if ltf_tf not in tf_to_run or htf_tf not in tf_to_run:
                    continue
                ltf_df = _load_events(tf_to_run[ltf_tf] / "events.csv")
                htf_df = _load_events(tf_to_run[htf_tf] / "events.csv")
                try:
                    h = MultiTFReversalHypothesis()
                    h.set_parameters(htf=htf_tf, ltf=ltf_tf)
                    result = h.evaluate(ltf_df, htf_df)
                    rows.append({
                        "hypothesis": f"{h.name} (HTF={htf_tf}m, LTF={ltf_tf}m)",
                        "instrument": inst,
                        "timeframe": ltf_tf,
                        "run_id": tf_to_run[ltf_tf].name,
                        "sample_size": result.get("sample_size", 0),
                        "win_rate": result.get("win_rate", 0.0),
                        "avg_mfe_10": result.get("avg_mfe_10", 0.0),
                        "avg_mae_10": result.get("avg_mae_10", 0.0),
                    })
                except Exception as e:
                    logging.exception(f"MultiTFReversal failed on {inst} HTF={htf_tf} LTF={ltf_tf}: {e}")

    # Write CSV
    out_path_p = Path(out_path)
    out_path_p.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["hypothesis", "instrument", "timeframe", "run_id",
                  "sample_size", "win_rate", "avg_mfe_10", "avg_mae_10"]
    with out_path_p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    logging.info(f"Wrote {len(rows)} rows to {out_path_p}")


def main():
    parser = argparse.ArgumentParser(description="Phase 1 hypothesis edge-test driver")
    parser.add_argument("--corpus-base", required=True, help="Path to logs/backend/runs/")
    parser.add_argument("--out", required=True, help="Output summary CSV path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_phase1(args.corpus_base, args.out)


if __name__ == "__main__":
    main()
```

- [ ] **Step 11.4: Run tests to verify they pass**

Run: `cd gann-visualizer/backend && python -m pytest tests/test_phase1_edge_test_driver.py -v`
Expected: PASS — both tests green.

- [ ] **Step 11.5: Commit**

```bash
git add gann-visualizer/backend/analysis/phase1_edge_test.py gann-visualizer/backend/tests/test_phase1_edge_test_driver.py
git commit -m "$(cat <<'EOF'
feat: add phase1_edge_test driver — runs all hypotheses on full corpus

Walks logs/backend/runs/<instrument>/<timeframe>/<run_id>/, runs the four
secondary hypotheses + PostBreachPullback per slice, and runs
MultiTFReversal per (instrument, HTF=60m, LTF in {5m, 15m}) pair. Emits
a summary CSV with sample_size/win_rate/avg_mfe_10/avg_mae_10 per row.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Final integration check — all tests pass and full pipeline runnable

**Why:** Verify nothing has been broken in passing.

**Files:** none modified.

- [ ] **Step 12.1: Run the entire test suite**

Run: `cd gann-visualizer/backend && python -m pytest tests/ -v`
Expected: PASS — all tests green. If any pre-existing test now fails, investigate before proceeding.

- [ ] **Step 12.2: Smoke-test the corpus runner with a tiny slice**

Edit `scripts/run_corpus.py` temporarily:

```python
CORPUS = [Slice("^NSEI", "60", "2026-04-20", "2026-04-22")]
```

Run: `cd gann-visualizer/backend && python -m scripts.run_corpus`
Expected: a new run directory created with `events.csv`, `trace.log`, `simulation_run.log`.

**Revert the CORPUS edit** before proceeding.

- [ ] **Step 12.3: Smoke-test the verifier on that slice**

```bash
python gann-visualizer/backend/analysis/verify_trace_events.py --run-dir <path-from-step-12.2>
```

Expected: audit report appears in `<run_dir>/audit/`. Note the accuracy/completeness numbers — if not 100/100, investigate but do not block this plan (Phase 0 audit fixes are operational, not implementation work).

- [ ] **Step 12.4: Smoke-test the Phase 1 driver against the smoke-test slice**

```bash
cd gann-visualizer/backend && python -m analysis.phase1_edge_test --corpus-base ../../logs/backend/runs --out /tmp/phase1_smoke.csv
```

Expected: `/tmp/phase1_smoke.csv` exists with at least one row per (hypothesis, slice) combination.

- [ ] **Step 12.5: No commit needed unless smoke tests revealed bugs**

If any smoke test fails, treat the failure as a new task: capture the bug as a failing test in the appropriate test file, fix it, commit. Otherwise, this plan is complete.

---

## What this plan does NOT include (and why)

These are intentionally deferred to a follow-up plan:

- **Phase 2 backtest modules.** The two priority hypotheses' backtest code (`gann-visualizer/backend/analysis/strategies/multi_tf_reversal.py` and `post_breach_pullback.py`) is written *after* Phase 1 results indicate which hypothesis warrants the investment. The hypothesis specs in spec §3.2.1 fully define their parameters; encoding them as backtested strategies is straightforward but premature until we know which one to back.
- **Notebook conversion.** Spec §3.2 mentioned `phase1_edge_test.ipynb`. We've produced a Python script instead (`phase1_edge_test.py`) — fully testable, identical output. If interactive exploration is later wanted, a thin notebook can wrap calls to `run_phase1()`.
- **Engine refactor for `replay_trace.log` to write directly to `<run_dir>/trace.log`.** Currently the trace is written to a hardcoded path and we copy it post-hoc in `run_simulation.py`. A direct-write refactor is bigger surgery in `unified_state_machine.py` and brings risk; deferred unless it actively breaks corpus generation.
- **Dual event-track collapse in `run_simulation.py`.** The spec flagged this as a code smell but said only fix if audit gate fails because of it. Honoured.

## Handoff to corpus operations (post-implementation)

Once this plan is fully merged, the user runs the following sequence to produce the actual corpus and Phase 1 results:

1. `cd gann-visualizer/backend && python -m scripts.run_corpus`  (~30 min depending on data fetch)
2. For each generated run directory:  `python gann-visualizer/backend/analysis/verify_trace_events.py --run-dir <run_dir>` — must pass 100/100. Fix any failing slice's underlying engine bug before continuing with that slice.
3. `cd gann-visualizer/backend && python -m analysis.phase1_edge_test --corpus-base ../../logs/backend/runs --out ../../logs/backend/phase1_summary.csv`
4. Read `phase1_summary.csv`. For any hypothesis × slice combination where `sample_size ≥ 30` and `win_rate × avg_mfe_10 / avg_mae_10` is consistently positive across ≥4 of 6 slices, that's a Phase 2 candidate. Submit a follow-up brainstorming round to design the backtest module for that hypothesis.
