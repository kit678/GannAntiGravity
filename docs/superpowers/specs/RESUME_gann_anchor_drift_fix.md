## Context: Gann Fan Hypothesis Testing Framework — Anchor Drift Fix

### What We Were Building
An offline **Hypothesis Testing Framework** to statistically test a Gann Fan trading strategy on NIFTY 50 historical data. The core goal is **100% synchronization** between offline corpus results and the frontend visualizer — so when the corpus finds a winning trade (e.g., `BREACH_CONFIRMED` on fan `H71-L47`), the same fan and event appear identically in the frontend replay.

### Original Problems Identified
1. **Anchor Date State Machine Drift** — Frontend and backend started processing data from different historical starting points, causing pivot/fan ID mismatch
2. **TradingView/React Race Conditions** — UI froze when stepping through replay
3. **Unsupported Shape Crashes** — Chart library threw errors on invalid shape names
4. **Timezone Mismatches / Infinite Log Loops** — UTC vs local timezone confusion caused initialization failures

### What We Fixed (Problem 1 only — anchor drift)

**Root Cause:** `main.py` (frontend endpoint) and `run_simulation.py` (corpus) used **different formulas** to compute the warmup anchor date. The frontend had a correct `WARMUP_DAYS` constant with `from_date - timedelta(days=warmup_days)` logic, but `run_simulation.py` used an older bar-count-based formula (`int(lookback_bars/90) * 4.0 + 30 = 250`) that produced slightly different anchors.

**Specific changes made:**

**`main.py` (lines ~89-104):** Already had the correct `WARMUP_DAYS` constant:
```python
WARMUP_DAYS = {
    "1": 30, "4": 30, "5": 75, "15": 120, "30": 120,
    "60": 250, "240": 250, "1D": 365, "D": 365, "W": 730, "M": 1825,
}
```
And the correct `from_date - WARMUP_DAYS[resolution]` warmup logic at lines ~831-860.

**`run_simulation.py` (corpus):** Replaced the old `lookback_bars` formula with the identical `WARMUP_DAYS` constant and `from_date - timedelta(days=warmup_days)` formula. Also fixed an `UnboundLocalError` where `lookback_days` was referenced in the log line but only defined in the `else` branch (no `from_date` provided).

**Key insight:** The old `run_simulation.py` formula computed `2025-01-21` as the 60m warmup anchor for `from_date=2025-09-28`, while `main.py` computed `2025-01-20` — a 1-day difference that caused YFinance to return 1 fewer bar, shifting all pivot numbers by 1, giving fan IDs off by one (`H51` vs `H52`).

### Verified Result
After the fix, both systems produce the **exact same fans** at the same bar position:
- Corpus (fresh run): `Fan_H52_L47`, `Fan_H52_L46`, `Fan_H52_L48`
- Frontend: `H52-L48`, `H52-L47`, `H52-L46` ✓

### Remaining Problems (NOT YET ADDRESSED)
1. **Race conditions** — TradingView/React UI freezing during fast date changes (partially mitigated with `try/catch` but not fully resolved)
2. **Shape crashes** — Unsupported shape names crashing the chart (needs investigation)
3. **Timezone infinite loops** — UTC vs local timezone causing initialization failures (needs verification)

### Files Modified
- `gann-visualizer/backend/main.py` — WARMUP_DAYS constant and clean warmup logic (done before this session)
- `gann-visualizer/backend/run_simulation.py` — Replaced old `lookback_bars` formula with WARMUP_DAYS, fixed UnboundLocalError

### Test Case for Next Session
To verify the fix end-to-end: set frontend `from_date = 2025-09-28`, `to_date = 2025-10-10`, `resolution = 60`, click **Reset to Start** — fans at bar ~1203 should be `H52-L48, H52-L47, H52-L46`, matching the corpus.

---

**Resume instruction:** Continue from here — the anchor drift fix is complete and verified. The next step is to address the remaining problems (race conditions, shape crashes, timezone loops), starting with verifying Problems 2 and 3 on the current codebase.