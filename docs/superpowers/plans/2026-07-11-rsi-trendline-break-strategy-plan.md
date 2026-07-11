# RSI Trendline Break Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a trade-scored RSI trendline-break hypothesis that reuses the current reporting pipeline and exposes RSI verification data inside the Hypothesis Navigator.

**Architecture:** Build a focused backend RSI geometry engine, a reusable candle-signal trade simulator, and a new RSI hypothesis that plugs into the unified hypothesis runner. Preserve custom `detailed_log` fields through the backend API and add a selected-event RSI verification panel in the frontend so the strategy can be checked visually without building a full custom chart pane.

**Tech Stack:** Python, pandas, pytest, FastAPI backend payload enrichment, React frontend, plain Node test scripts for frontend helpers

---

## File Structure

### Backend

- Create: `gann-visualizer/backend/analysis/rsi_geometry.py`
  - Pure RSI series, pivot, line, and breakout generation
- Create: `gann-visualizer/backend/analysis/signal_trade_simulator.py`
  - Actual-trade simulation for candle-based signals using structural SL + `R`-multiple TP
- Create: `gann-visualizer/backend/analysis/rsi_trendline_hypothesis.py`
  - Orchestrates geometry + trend filter + trade simulation into the standard hypothesis result format
- Modify: `gann-visualizer/backend/analysis/hypothesis_framework.py`
  - Register the new hypothesis and avoid clobbering a hypothesis that already returns trade-scored results
- Modify: `gann-visualizer/backend/main.py`
  - Preserve custom `detailed_log` fields during per-hypothesis enrichment so RSI verification payloads survive API serving

### Backend Tests

- Create: `gann-visualizer/backend/tests/test_hypothesis_report_enrichment.py`
  - Proves backend enrichment preserves non-fan RSI fields
- Create: `gann-visualizer/backend/tests/test_rsi_geometry.py`
  - Covers RSI series, pivot detection, line construction, and breakout timing
- Create: `gann-visualizer/backend/tests/test_signal_trade_simulator.py`
  - Covers TP hit, SL hit, time exit, fees, and `R`-grid summaries
- Create: `gann-visualizer/backend/tests/test_rsi_trendline_hypothesis.py`
  - Covers end-to-end hypothesis output shape and trade-scored payload content

### Frontend

- Create: `gann-visualizer/frontend/src/hypothesisRsiVerification.js`
  - Builds a selected-event verification model from normalized hypothesis events
- Create: `gann-visualizer/frontend/src/hypothesisRsiVerification.test.mjs`
  - Tests the selected-event verification model builder
- Modify: `gann-visualizer/frontend/src/hypothesisEventFormatting.js`
  - Normalize RSI-specific fields explicitly
- Modify: `gann-visualizer/frontend/src/hypothesisEventFormatting.test.mjs`
  - Prove RSI fields pass through normalization
- Modify: `gann-visualizer/frontend/src/App.jsx`
  - Render an RSI verification panel for selected hypothesis events

## Task 1: Preserve Custom Hypothesis Payload Fields End-to-End

**Files:**
- Create: `gann-visualizer/backend/tests/test_hypothesis_report_enrichment.py`
- Modify: `gann-visualizer/backend/main.py`

- [ ] **Step 1: Write the failing backend enrichment test**

```python
import copy

from main import _enrich_detailed_log


def test_enrich_detailed_log_preserves_rsi_specific_fields(monkeypatch):
    detailed_log = [{
        "time": "2026-07-10T10:15:00",
        "type": "RSI_TRENDLINE_BREAK_LONG",
        "outcome": "WIN",
        "rsi_window": [{"bar_index": 101, "rsi": 46.2}, {"bar_index": 102, "rsi": 49.4}],
        "pivot_a_bar_index": 88,
        "pivot_b_bar_index": 96,
        "line_value_at_break": 48.7,
        "trend_filter_passed": True,
        "best_r": 2.0,
        "stop_price": 104325.5,
    }]

    monkeypatch.setattr("main._build_hypothesis_lookup", lambda run_dir: {})

    enriched = _enrich_detailed_log(copy.deepcopy(detailed_log), "unused-run-dir")

    assert enriched[0]["rsi_window"][0]["rsi"] == 46.2
    assert enriched[0]["pivot_a_bar_index"] == 88
    assert enriched[0]["line_value_at_break"] == 48.7
    assert enriched[0]["trend_filter_passed"] is True
    assert enriched[0]["best_r"] == 2.0
    assert enriched[0]["stop_price"] == 104325.5
```

- [ ] **Step 2: Run the backend enrichment test and confirm it fails**

Run: `python -m pytest gann-visualizer/backend/tests/test_hypothesis_report_enrichment.py -v`

Expected: FAIL because `_enrich_detailed_log()` rebuilds a narrow dict and drops unknown RSI fields.

- [ ] **Step 3: Update `main.py` to preserve custom `detailed_log` fields before fan enrichment**

```python
def _enrich_detailed_log(detailed_log: list, run_dir: str) -> list:
    lookup = _build_hypothesis_lookup(run_dir)
    enriched = []

    preserved_keys = {
        "event_id", "event_type", "event_type_display", "time", "test_time",
        "fan", "fraction", "type", "price", "is_retro", "outcome", "mfe", "mae",
        "anchor_bar_index", "scale_ratio", "anchor_price", "details",
        "confirmation_details", "entry_price", "entry_time", "exit_price",
        "exit_time", "exit_reason", "exit_label", "net_pnl", "pnl_pct",
        "bars_held", "entry_side",
    }

    for i, entry in enumerate(detailed_log):
        ts = _parse_detailed_log_time(entry.get("time", ""))
        fan_id = _extract_fan_identity(entry.get("fan", ""))
        frac = str(entry.get("fraction", ""))

        custom_fields = {
            key: value for key, value in entry.items()
            if key not in preserved_keys
        }

        enriched_entry = {
            **custom_fields,
            "event_id": i + 1,
            "event_type": entry.get("type", ""),
            "time": entry.get("time", ""),
            "test_time": entry.get("test_time", ""),
            "fan": entry.get("fan", ""),
            "fraction": entry.get("fraction", ""),
            "type": entry.get("type", ""),
            "price": entry.get("price"),
            "is_retro": entry.get("is_retro", False),
            "outcome": entry.get("outcome"),
            "mfe": entry.get("mfe"),
            "mae": entry.get("mae"),
            "anchor_bar_index": entry.get("anchor_bar_index"),
            "scale_ratio": entry.get("scale_ratio"),
            "anchor_price": entry.get("anchor_price"),
            "details": entry.get("details", ""),
            "confirmation_details": entry.get("confirmation_details") or entry.get("details", ""),
            "entry_price": entry.get("entry_price"),
            "entry_time": entry.get("entry_time", ""),
            "exit_price": entry.get("exit_price"),
            "exit_time": entry.get("exit_time", ""),
            "exit_reason": entry.get("exit_reason"),
            "exit_label": entry.get("exit_label", ""),
            "net_pnl": entry.get("net_pnl"),
            "pnl_pct": entry.get("pnl_pct"),
            "bars_held": entry.get("bars_held"),
            "entry_side": entry.get("entry_side"),
        }
```

- [ ] **Step 4: Re-run the backend enrichment test**

Run: `python -m pytest gann-visualizer/backend/tests/test_hypothesis_report_enrichment.py -v`

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit the enrichment safeguard**

```bash
git add gann-visualizer/backend/main.py gann-visualizer/backend/tests/test_hypothesis_report_enrichment.py
git commit -m "test: preserve custom hypothesis payload fields"
```

## Task 2: Build the RSI Geometry Engine

**Files:**
- Create: `gann-visualizer/backend/analysis/rsi_geometry.py`
- Create: `gann-visualizer/backend/tests/test_rsi_geometry.py`

- [ ] **Step 1: Write failing geometry tests**

```python
import pandas as pd

from analysis.rsi_geometry import (
    compute_rsi_series,
    detect_rsi_pivots,
    DeterministicPivotLineBuilder,
    detect_rsi_line_breaks,
)


def test_detect_rsi_pivots_marks_repeatable_highs_and_lows():
    rsi = pd.Series([42, 45, 51, 58, 53, 49, 44, 47, 55, 61, 57, 50, 46])
    pivots = detect_rsi_pivots(rsi, left_bars=1, right_bars=1)
    pivot_kinds = [(p.bar_index, p.kind) for p in pivots]
    assert (3, "high") in pivot_kinds
    assert (6, "low") in pivot_kinds
    assert (9, "high") in pivot_kinds


def test_line_builder_uses_newest_compatible_pivot_pair():
    rsi = pd.Series([45, 50, 58, 54, 51, 48, 52, 57, 55, 53, 49])
    pivots = detect_rsi_pivots(rsi, left_bars=1, right_bars=1)
    lines = DeterministicPivotLineBuilder().build_lines(pivots)
    assert any(line.direction == "down" for line in lines)


def test_break_detector_emits_long_break_with_local_rsi_window():
    candles = pd.DataFrame({
        "bar_index": range(8),
        "close": [100, 101, 102, 103, 104, 105, 106, 107],
        "high": [101, 102, 103, 104, 105, 106, 107, 108],
        "low": [99, 100, 101, 102, 103, 104, 105, 106],
    })
    rsi = pd.Series([62, 59, 56, 53, 51, 50, 54, 58])
    pivots = detect_rsi_pivots(rsi, left_bars=1, right_bars=1)
    lines = DeterministicPivotLineBuilder().build_lines(pivots)
    signals = detect_rsi_line_breaks(candles, rsi, lines, window_bars=5)
    assert signals
    assert signals[-1].direction == "LONG"
    assert len(signals[-1].rsi_window) >= 3
```

- [ ] **Step 2: Run geometry tests and confirm they fail**

Run: `python -m pytest gann-visualizer/backend/tests/test_rsi_geometry.py -v`

Expected: FAIL because `analysis.rsi_geometry` does not exist yet.

- [ ] **Step 3: Implement the geometry module**

```python
from dataclasses import dataclass
from typing import List

import pandas as pd


@dataclass(frozen=True)
class RSIPivot:
    bar_index: int
    rsi_value: float
    kind: str  # "high" | "low"


@dataclass(frozen=True)
class RSILine:
    start_bar_index: int
    end_bar_index: int
    start_rsi: float
    end_rsi: float
    direction: str  # "up" | "down"


@dataclass(frozen=True)
class RSIBreakSignal:
    bar_index: int
    direction: str  # "LONG" | "SHORT"
    line: RSILine
    line_value_at_break: float
    rsi_value: float
    rsi_window: list[dict]


def compute_rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(method="bfill")


class DeterministicPivotLineBuilder:
    def build_lines(self, pivots: List[RSIPivot]) -> List[RSILine]:
        lines = []
        for idx in range(1, len(pivots)):
            a = pivots[idx - 1]
            b = pivots[idx]
            if a.kind == "high" and b.kind == "high" and b.rsi_value <= a.rsi_value:
                lines.append(RSILine(a.bar_index, b.bar_index, a.rsi_value, b.rsi_value, "down"))
            if a.kind == "low" and b.kind == "low" and b.rsi_value >= a.rsi_value:
                lines.append(RSILine(a.bar_index, b.bar_index, a.rsi_value, b.rsi_value, "up"))
        return lines
```

- [ ] **Step 4: Re-run geometry tests**

Run: `python -m pytest gann-visualizer/backend/tests/test_rsi_geometry.py -v`

Expected: PASS with `3 passed`.

- [ ] **Step 5: Commit the geometry engine**

```bash
git add gann-visualizer/backend/analysis/rsi_geometry.py gann-visualizer/backend/tests/test_rsi_geometry.py
git commit -m "feat: add RSI geometry engine"
```

## Task 3: Add a Reusable Actual-Trade Simulator for Candle Signals

**Files:**
- Create: `gann-visualizer/backend/analysis/signal_trade_simulator.py`
- Create: `gann-visualizer/backend/tests/test_signal_trade_simulator.py`

- [ ] **Step 1: Write failing simulator tests**

```python
import pandas as pd

from analysis.signal_trade_simulator import CandleSignal, simulate_trade_grid


def test_trade_grid_marks_target_hit_as_win_when_net_pnl_positive():
    candles = pd.DataFrame({
        "bar_index": [10, 11, 12, 13],
        "open": [100, 101, 102, 103],
        "high": [101, 104, 108, 109],
        "low": [99, 100, 101, 102],
        "close": [100, 103, 107, 108],
    })
    signal = CandleSignal(
        bar_index=10,
        side="LONG",
        entry_price=100.0,
        stop_price=99.0,
        signal_time="2026-07-10T10:15:00",
    )

    result = simulate_trade_grid(candles, [signal], r_values=[1.0, 2.0], max_hold_bars=3)

    assert result["best"]["r_value"] in (1.0, 2.0)
    assert result["all_r_results"][0]["n"] == 1
    assert result["per_signal"][10]["outcome"] == "WIN"


def test_trade_grid_marks_stop_loss_as_loss():
    candles = pd.DataFrame({
        "bar_index": [20, 21, 22],
        "open": [200, 199, 198],
        "high": [201, 200, 199],
        "low": [199, 196, 195],
        "close": [200, 196, 195],
    })
    signal = CandleSignal(
        bar_index=20,
        side="LONG",
        entry_price=200.0,
        stop_price=198.0,
        signal_time="2026-07-10T11:00:00",
    )

    result = simulate_trade_grid(candles, [signal], r_values=[1.0], max_hold_bars=2)
    assert result["per_signal"][20]["exit_reason"] == "stop_loss"
    assert result["per_signal"][20]["net_pnl"] < 0
```

- [ ] **Step 2: Run simulator tests and confirm they fail**

Run: `python -m pytest gann-visualizer/backend/tests/test_signal_trade_simulator.py -v`

Expected: FAIL because the simulator module does not exist yet.

- [ ] **Step 3: Implement the reusable signal trade simulator**

```python
from dataclasses import dataclass

from analysis.exit_optimizer import MAX_HOLD_BARS, R_VALUES, TAKER_FEE


@dataclass(frozen=True)
class CandleSignal:
    bar_index: int
    side: str
    entry_price: float
    stop_price: float
    signal_time: str


def simulate_trade_grid(candles_df, signals, r_values=None, max_hold_bars: int = MAX_HOLD_BARS):
    r_grid = list(r_values or R_VALUES)
    all_results = []
    per_signal_by_r = {}
    for r_value in r_grid:
        combo = _simulate_r(candles_df, signals, r_value, max_hold_bars=max_hold_bars)
        all_results.append(combo)
        per_signal_by_r[r_value] = combo["per_signal"]

    best = max(all_results, key=lambda row: (row["profit_factor"], row["expectancy"], row["n"]))
    return {
        "best": best,
        "all_r_results": all_results,
        "per_signal": per_signal_by_r[best["r_value"]],
    }
```

- [ ] **Step 4: Re-run simulator tests**

Run: `python -m pytest gann-visualizer/backend/tests/test_signal_trade_simulator.py -v`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit the reusable simulator**

```bash
git add gann-visualizer/backend/analysis/signal_trade_simulator.py gann-visualizer/backend/tests/test_signal_trade_simulator.py
git commit -m "feat: add candle signal trade simulator"
```

## Task 4: Implement and Register the RSI Trendline Break Hypothesis

**Files:**
- Create: `gann-visualizer/backend/analysis/rsi_trendline_hypothesis.py`
- Create: `gann-visualizer/backend/tests/test_rsi_trendline_hypothesis.py`
- Modify: `gann-visualizer/backend/analysis/hypothesis_framework.py`

- [ ] **Step 1: Write the failing hypothesis integration test**

```python
import pandas as pd

from analysis.rsi_trendline_hypothesis import RSITrendlineBreakHypothesis


def test_rsi_trendline_hypothesis_returns_trade_scored_detailed_log():
    candles = pd.DataFrame({
        "time": [1, 2, 3, 4, 5, 6, 7, 8],
        "bar_index": list(range(8)),
        "open": [100, 101, 102, 103, 104, 105, 106, 107],
        "high": [101, 102, 103, 104, 105, 106, 110, 111],
        "low": [99, 100, 101, 102, 103, 104, 105, 106],
        "close": [100, 101, 102, 103, 104, 105, 109, 110],
    })

    hyp = RSITrendlineBreakHypothesis()
    result = hyp.evaluate(pd.DataFrame(), candles_df=candles)

    assert "exit_optimization" in result
    assert "trade_scored" in result and result["trade_scored"] is True
    assert isinstance(result["detailed_log"], list)
    if result["detailed_log"]:
        entry = result["detailed_log"][0]
        assert "rsi_window" in entry
        assert "stop_price" in entry
        assert "best_r" in entry
```

- [ ] **Step 2: Run the hypothesis test and confirm it fails**

Run: `python -m pytest gann-visualizer/backend/tests/test_rsi_trendline_hypothesis.py -v`

Expected: FAIL because the hypothesis file and runner registration do not exist yet.

- [ ] **Step 3: Implement the hypothesis class**

```python
import pandas as pd

from analysis.rsi_geometry import (
    compute_rsi_series,
    detect_rsi_pivots,
    DeterministicPivotLineBuilder,
    detect_rsi_line_breaks,
)
from analysis.signal_trade_simulator import CandleSignal, simulate_trade_grid
from analysis.strategy_analyzer import Hypothesis


class RSITrendlineBreakHypothesis(Hypothesis):
    def __init__(self):
        super().__init__(
            name="RSI Trendline Break Strategy",
            description="Trade-scored RSI trendline breaks filtered by price vs SMA(200).",
        )
        self.set_parameters(
            rsi_period=14,
            sma_period=200,
            pivot_left_bars=2,
            pivot_right_bars=2,
            r_values=[1.0, 1.5, 2.0, 2.5, 3.0],
            max_hold_bars=10,
        )

    def evaluate(self, df: pd.DataFrame, candles_df: pd.DataFrame = None):
        if candles_df is None or candles_df.empty:
            return self._empty_result()

        candles = candles_df.copy()
        candles["rsi"] = compute_rsi_series(candles["close"], self.parameters["rsi_period"])
        candles["sma_200"] = candles["close"].rolling(self.parameters["sma_period"]).mean()

        pivots = detect_rsi_pivots(
            candles["rsi"],
            left_bars=self.parameters["pivot_left_bars"],
            right_bars=self.parameters["pivot_right_bars"],
        )
        lines = DeterministicPivotLineBuilder().build_lines(pivots)
        breaks = detect_rsi_line_breaks(candles, candles["rsi"], lines, window_bars=40)

        trade_signals = []
        for signal in breaks:
            close_price = float(candles.loc[candles["bar_index"] == signal.bar_index, "close"].iloc[0])
            sma_value = float(candles.loc[candles["bar_index"] == signal.bar_index, "sma_200"].iloc[0])
            filter_passed = (
                signal.direction == "LONG" and close_price > sma_value
            ) or (
                signal.direction == "SHORT" and close_price < sma_value
            )
            if not filter_passed:
                continue

            stop_price = float(candles.loc[candles["bar_index"] == signal.bar_index, "low"].iloc[0]) \
                if signal.direction == "LONG" else \
                float(candles.loc[candles["bar_index"] == signal.bar_index, "high"].iloc[0])

            trade_signals.append(CandleSignal(
                bar_index=signal.bar_index,
                side=signal.direction,
                entry_price=close_price,
                stop_price=stop_price,
                signal_time=str(candles.loc[candles["bar_index"] == signal.bar_index, "time"].iloc[0]),
            ))
```

- [ ] **Step 4: Register the hypothesis in the unified runner and skip duplicate exit optimization**

```python
from .rsi_trendline_hypothesis import RSITrendlineBreakHypothesis


class HypothesisRunner:
    HYPOTHESIS_CONFIG = [
        ("strong_sr_rule", StrongSRHypothesis, False),
        ("quarter_reversal_anomaly", QuarterReversalAnomalyHypothesis, False),
        ("confluence_bounce", ConfluenceBounceHypothesis, False),
        ("target_progression", TargetProgressionHypothesis, True),
        ("post_breach_pullback", PostBreachPullbackHypothesis, False),
        ("rsi_trendline_break", RSITrendlineBreakHypothesis, True),
    ]

    def run_all(self) -> Dict[str, Any]:
        result = {
            "hypothesis_name": hypothesis.name,
            "description": hypothesis.description,
            "in_sample": {
                "sample_size": in_sample.get("sample_size", 0),
                "win_rate": in_sample.get("win_rate", 0.0),
                "live_sample_size": in_sample.get("live_sample_size", 0),
                "live_win_rate": in_sample.get("live_win_rate", 0.0),
                "retro_sample_size": in_sample.get("retro_sample_size", 0),
                "retro_win_rate": in_sample.get("retro_win_rate", 0.0),
                "avg_mfe_10": in_sample.get("avg_mfe_10", 0.0),
                "avg_mae_10": in_sample.get("avg_mae_10", 0.0),
                "composite": in_sample.get("composite", 0.0),
            },
            "walk_forward": wf,
            "groups": in_sample.get("groups", {}),
            "detailed_log": in_sample.get("detailed_log", []),
        }
        if "exit_optimization" in in_sample:
            result["exit_optimization"] = in_sample["exit_optimization"]
        if in_sample.get("trade_scored"):
            result["trade_scored"] = True

        if not result.get("trade_scored") and candles_df is not None and result["detailed_log"]:
            optimizer = ExitOptimizer(
                events_df=qualified,
                candles_df=candles_df,
                train_pct=0.7,
            )
            result["exit_optimization"] = optimizer.optimize()
```

- [ ] **Step 5: Re-run the hypothesis integration test**

Run: `python -m pytest gann-visualizer/backend/tests/test_rsi_trendline_hypothesis.py -v`

Expected: PASS with `1 passed`.

- [ ] **Step 6: Run a real report generation smoke test on an existing BTCUSDT run**

Run: `python gann-visualizer/backend/generate_hypothesis_reports.py 2026-07-10 --15m -H "RSI Trendline Break Strategy"`

Expected: the command completes and writes `analysis/hypotheses/rsi_trendline_break.json` inside the selected `logs/backend/runs/BTCUSDT/15/2026-07-10_*` run directory.

- [ ] **Step 7: Commit the hypothesis integration**

```bash
git add gann-visualizer/backend/analysis/rsi_trendline_hypothesis.py gann-visualizer/backend/analysis/hypothesis_framework.py gann-visualizer/backend/tests/test_rsi_trendline_hypothesis.py
git commit -m "feat: add RSI trendline break hypothesis"
```

## Task 5: Surface RSI Verification Data in the Hypothesis Navigator

**Files:**
- Create: `gann-visualizer/frontend/src/hypothesisRsiVerification.js`
- Create: `gann-visualizer/frontend/src/hypothesisRsiVerification.test.mjs`
- Modify: `gann-visualizer/frontend/src/hypothesisEventFormatting.js`
- Modify: `gann-visualizer/frontend/src/hypothesisEventFormatting.test.mjs`
- Modify: `gann-visualizer/frontend/src/App.jsx`

- [ ] **Step 1: Write failing frontend normalization and verification-model tests**

```javascript
import assert from 'node:assert/strict';

import { normalizeHypothesisEvent } from './hypothesisEventFormatting.js';
import { buildRsiVerificationModel } from './hypothesisRsiVerification.js';

const normalized = normalizeHypothesisEvent({
  event_type: 'RSI_TRENDLINE_BREAK_LONG',
  time: '2026-07-10T10:15:00',
  rsi_value: 52.4,
  sma_200: 103455.1,
  trend_filter_passed: true,
  pivot_a_bar_index: 88,
  pivot_b_bar_index: 96,
  line_value_at_break: 48.7,
  rsi_window: [
    { bar_index: 92, rsi: 44.1 },
    { bar_index: 93, rsi: 45.6 },
    { bar_index: 94, rsi: 52.4 },
  ],
}, 0);

assert.equal(normalized.rsi_value, 52.4);
assert.equal(normalized.trend_filter_passed, true);
assert.equal(normalized.rsi_window.length, 3);

const model = buildRsiVerificationModel(normalized);
assert.equal(model.summary.bestRLabel, '-');
assert.equal(model.windowPoints.length, 3);
assert.equal(model.breakPoint.rsi, 52.4);
```

- [ ] **Step 2: Run frontend tests and confirm they fail**

Run: `node gann-visualizer/frontend/src/hypothesisEventFormatting.test.mjs && node gann-visualizer/frontend/src/hypothesisRsiVerification.test.mjs`

Expected: FAIL because the verification helper file does not exist and the normalizer does not explicitly expose RSI fields yet.

- [ ] **Step 3: Add explicit RSI field normalization and a verification-model helper**

```javascript
// hypothesisEventFormatting.js
return {
  ...event,
  event_id: event.event_id || index + 1,
  event_type: event.event_type || event.type || '-',
  event_type_display: event.event_type_display || event.event_type || '-',
  datetime: formatHypothesisDatetime(event.timestamp ?? timestamp, timeStr),
  rsi_value: event.rsi_value ?? null,
  sma_200: event.sma_200 ?? null,
  trend_filter_passed: event.trend_filter_passed ?? null,
  pivot_a_bar_index: event.pivot_a_bar_index ?? null,
  pivot_b_bar_index: event.pivot_b_bar_index ?? null,
  line_value_at_break: event.line_value_at_break ?? null,
  best_r: event.best_r ?? null,
  stop_price: event.stop_price ?? null,
  rsi_window: Array.isArray(event.rsi_window) ? event.rsi_window : [],
};
```

```javascript
// hypothesisRsiVerification.js
export function buildRsiVerificationModel(event) {
  if (!event || !Array.isArray(event.rsi_window) || event.rsi_window.length === 0) {
    return null;
  }

  return {
    windowPoints: event.rsi_window.map(point => ({
      barIndex: point.bar_index,
      rsi: point.rsi,
    })),
    breakPoint: {
      barIndex: event.break_bar_index ?? event.bar_index,
      rsi: event.rsi_value,
      lineValue: event.line_value_at_break,
    },
    summary: {
      side: event.entry_side || event.direction || '-',
      bestRLabel: event.best_r != null ? `${event.best_r}R` : '-',
      trendFilter: event.trend_filter_passed ? 'PASS' : 'FAIL',
      stopPrice: event.stop_price ?? null,
    },
  };
}
```

- [ ] **Step 4: Render the selected-event RSI verification panel in `App.jsx`**

```jsx
import { buildRsiVerificationModel } from './hypothesisRsiVerification';

// inside the component:
const selectedRsiModel = useMemo(
  () => buildRsiVerificationModel(selectedHypothesisEvent),
  [selectedHypothesisEvent]
);

// below the hypothesis table:
{selectedRsiModel && (
  <div style={{ marginTop: '12px', padding: '10px', background: '#111827', borderRadius: '6px' }}>
    <div style={{ fontSize: '12px', fontWeight: 600, marginBottom: '8px' }}>
      RSI Verification
    </div>
    <div style={{ fontSize: '11px', color: '#cbd5e1', marginBottom: '6px' }}>
      Side: {selectedRsiModel.summary.side} | Trend Filter: {selectedRsiModel.summary.trendFilter} | Best TP: {selectedRsiModel.summary.bestRLabel}
    </div>
    <pre style={{ fontSize: '10px', whiteSpace: 'pre-wrap', margin: 0 }}>
      {JSON.stringify(selectedRsiModel.windowPoints, null, 2)}
    </pre>
  </div>
)}
```

- [ ] **Step 5: Re-run the frontend tests**

Run: `node gann-visualizer/frontend/src/hypothesisEventFormatting.test.mjs && node gann-visualizer/frontend/src/hypothesisRsiVerification.test.mjs`

Expected: PASS with both scripts printing their success messages.

- [ ] **Step 6: Commit the navigator verification UI**

```bash
git add gann-visualizer/frontend/src/hypothesisEventFormatting.js gann-visualizer/frontend/src/hypothesisEventFormatting.test.mjs gann-visualizer/frontend/src/hypothesisRsiVerification.js gann-visualizer/frontend/src/hypothesisRsiVerification.test.mjs gann-visualizer/frontend/src/App.jsx
git commit -m "feat: add RSI verification panel to hypothesis navigator"
```

## Task 6: Full Verification Pass

**Files:**
- Modify: none unless a verification failure reveals a small fix

- [ ] **Step 1: Run all backend tests for the new feature**

Run:

```bash
python -m pytest gann-visualizer/backend/tests/test_hypothesis_report_enrichment.py gann-visualizer/backend/tests/test_rsi_geometry.py gann-visualizer/backend/tests/test_signal_trade_simulator.py gann-visualizer/backend/tests/test_rsi_trendline_hypothesis.py -v
```

Expected: PASS for all four test files.

- [ ] **Step 2: Run all frontend helper tests touched by this feature**

Run:

```bash
node gann-visualizer/frontend/src/hypothesisEventFormatting.test.mjs
node gann-visualizer/frontend/src/hypothesisRsiVerification.test.mjs
```

Expected: PASS and print the existing hypothesis formatting success summary plus the new RSI verification success summary.

- [ ] **Step 3: Rebuild reports for a known run and inspect the JSON payload**

Run:

```bash
python gann-visualizer/backend/generate_hypothesis_reports.py 2026-07-10 --15m -H "RSI Trendline Break Strategy"
```

Then inspect:

```bash
python - <<'PY'
import json
from pathlib import Path

paths = sorted(Path("logs/backend/runs/BTCUSDT/15").glob("2026-07-10_*/analysis/hypotheses/rsi_trendline_break.json"))
assert paths, "No RSI report generated"
payload = json.loads(paths[-1].read_text(encoding="utf-8"))
event = payload["detailed_log"][0] if payload["detailed_log"] else {}
print(sorted(k for k in event.keys() if k.startswith("rsi") or k in {"best_r", "stop_price", "trend_filter_passed"}))
PY
```

Expected: printed keys include `rsi_value`, `rsi_window`, `best_r`, `stop_price`, and `trend_filter_passed`.

- [ ] **Step 4: Manual Hypothesis Navigator smoke test**

Run the backend and frontend normally, load the generated RSI report in the Hypothesis Navigator, click at least one RSI signal, and confirm:

- the row renders without errors
- entry / exit / exit reason are visible
- the selected-event RSI verification panel appears
- the panel reflects the selected event's local RSI window and summary fields

- [ ] **Step 5: Commit any final verification fix only if a code change was required**

```bash
git add -A
git commit -m "fix: finalize RSI trendline break verification"
```

Skip this step if verification required no further code changes.

## Plan Self-Review

### Spec Coverage

- RSI geometry engine: Task 2
- actual-trade scoring and `R` grid: Tasks 3 and 4
- unified runner integration: Task 4
- custom `detailed_log` field preservation: Task 1
- Hypothesis Navigator visibility: Task 5
- verification and real-run smoke: Task 6
- follow-up variations list: already captured in the spec, not re-implemented here

### Placeholder Scan

- No `TODO`, `TBD`, or “similar to above” shortcuts remain
- Every task includes exact file paths
- Every code-writing step includes concrete code snippets
- Every verification step includes an exact command

### Type Consistency

- Geometry layer uses `RSIPivot`, `RSILine`, and `RSIBreakSignal`
- Trade layer uses `CandleSignal`
- Frontend verification layer expects `rsi_window`, `rsi_value`, `best_r`, `stop_price`, and `trend_filter_passed`
- Hypothesis result contract preserves `detailed_log`, `groups`, `walk_forward`, and optional `exit_optimization`
