# Binance Testnet & Simulation Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align Binance Testnet replay logic with the backend simulation by introducing an explicit `--warmup-days` configuration, splitting historical replay and live execution into separate scripts, and unifying data fetching bounds.

**Architecture:** We will modify `run_simulation.py` to accept `--warmup-days` (default 0), bypassing the hardcoded `WARMUP_DAYS` map when provided. We will clone `run_binance_live.py` into `run_binance_replay.py`, switching it to `--from-date` and `--to-date` arguments, and modifying its core engine to silently ingest `fetch_klines_range` history up until `from_date`, after which trading/logging triggers. Finally, we'll strip backtesting code out of `run_binance_live.py`.

**Tech Stack:** Python 3, argparse, Binance API.

---

### Task 1: Add `--warmup-days` to `run_simulation.py`

**Files:**
- Modify: `c:\Dev\GannTesting\gann-visualizer\backend\run_simulation.py`

- [ ] **Step 1: Add the CLI argument**

In `if __name__ == "__main__":` block, add `--warmup-days`:

```python
    parser.add_argument("--to-date", type=str, default=None, help="End date (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--warmup-days", type=int, default=0, help="Days of history to fetch before from-date for macro fans. Defaults to 0.")
    parser.add_argument("--lookback", type=int, default=5000, help="Number of lookback bars for context building")
```

Also pass it to `run_simulation`:

```python
    run_simulation(
        symbol=args.symbol,
        resolution=args.resolution,
        data_source=args.source,
        from_date=args.from_date,
        to_date=args.to_date,
        warmup_days=args.warmup_days,
        lookback_bars=args.lookback,
        left_bars=args.left_bars,
        right_bars=args.right_bars
    )
```

- [ ] **Step 2: Update `run_simulation` signature**

Update `def run_simulation(symbol="^NSEI", resolution="4", data_source="yfinance", from_date=None, to_date=None, warmup_days=0, lookback_bars=5000, left_bars=5, right_bars=5):` and pass `warmup_days` down to `get_frontend_parity_data`.

- [ ] **Step 3: Update `get_frontend_parity_data` signature and logic**

Update signature: `def get_frontend_parity_data(symbol="^NSEI", resolution="4", data_source="yfinance", lookback_bars=5000, from_date=None, to_date=None, warmup_days=0):`

Modify the `if from_date:` block to use the passed `warmup_days` instead of `WARMUP_DAYS.get()`:

```python
    if from_date:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d")
        target_from_dt = from_dt
        from_dt_utc = from_dt.astimezone(timezone.utc)
        ideal_warmup_from_dt = from_dt_utc - timedelta(days=warmup_days)
```

- [ ] **Step 4: Verify syntax**

Run: `python c:/Dev/GannTesting/gann-visualizer/backend/run_simulation.py --help`
Expected: Passes without syntax error and shows `--warmup-days`.

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/run_simulation.py
git commit -m "feat: add explicit --warmup-days argument to run_simulation"
```

### Task 2: Create `run_binance_replay.py` and implement unified args

**Files:**
- Create: `c:\Dev\GannTesting\gann-visualizer\backend\run_binance_replay.py`

- [ ] **Step 1: Duplicate script**

Run: `cp c:/Dev/GannTesting/gann-visualizer/backend/run_binance_live.py c:/Dev/GannTesting/gann-visualizer/backend/run_binance_replay.py`

- [ ] **Step 2: Update CLI args in `run_binance_replay.py`**

In `def main():` of `run_binance_replay.py`, replace the `bars`, `--live`, and `--qty` args with the date/warmup ones:

```python
    parser = argparse.ArgumentParser(description="Target Progression Strategy Replay on Binance Testnet")
    parser.add_argument("symbol", default="BTCUSDT", nargs="?", help="Trading pair (default: BTCUSDT)")
    parser.add_argument("interval", default="1h", nargs="?", help="Kline interval (default: 1h)")
    parser.add_argument("--from-date", type=str, required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to-date", type=str, required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--warmup-days", type=int, default=0, help="Days of history to fetch before from-date (default: 0)")
    parser.add_argument("--momentum-filter", action="store_true", dest="momentum_filter",
                        help="Only enter on retest if breach momentum was 'momentum'")
    parser.add_argument('--target-progression', action='store_true',
                        help='Run Model B (target progression sequential) alongside Model A')
    args = parser.parse_args()

    client = BinanceClient(use_testnet=True)
    run_replay(args.symbol.upper(), args.interval, args.from_date, args.to_date, args.warmup_days, client, momentum_filter=args.momentum_filter)
```

- [ ] **Step 3: Remove `run_live` function**

Delete the entire `def run_live` function from `run_binance_replay.py`.

- [ ] **Step 4: Verify syntax**

Run: `python c:/Dev/GannTesting/gann-visualizer/backend/run_binance_replay.py --help`
Expected: Passes without syntax error and shows date arguments.

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/run_binance_replay.py
git commit -m "feat: create dedicated binance replay script with date arguments"
```

### Task 3: Implement execution boundary in `run_binance_replay.py`

**Files:**
- Modify: `c:\Dev\GannTesting\gann-visualizer\backend\run_binance_replay.py`

- [ ] **Step 1: Update `run_replay` logic for date calculation**

Change `def run_replay(symbol, interval, bars, client, momentum_filter=False):` to:
`def run_replay(symbol, interval, from_date, to_date, warmup_days, client, momentum_filter=False):`

Inside `run_replay`, calculate timestamps:

```python
    from_dt = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    to_dt = datetime.strptime(to_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    
    warmup_from_dt = from_dt - timedelta(days=warmup_days)
    
    start_ms = int(warmup_from_dt.timestamp() * 1000)
    end_ms = int(to_dt.timestamp() * 1000)
    execution_start_ts = int(from_dt.timestamp())

    print(f"Fetching candles from {warmup_from_dt.strftime('%Y-%m-%d')} to {to_dt.strftime('%Y-%m-%d')}...")
    raw_candles = client.fetch_klines_range(symbol, interval, start_ms, end_ms)
```

- [ ] **Step 2: Update `warmup_end` indexing**

Instead of using `len(candles) // 4`, we find the index of the first candle at or after `execution_start_ts`:

```python
    start_index = 0
    for i, c in enumerate(candles):
        if int(c['time']) >= execution_start_ts:
            start_index = i
            break
            
    warmup_end = max(study.config["left_bars"] + study.config["right_bars"] + 1, start_index)
```

- [ ] **Step 3: Update tracking loop**

The loop `for i in range(warmup_end, len(candles)):` remains correct because `warmup_end` is now perfectly aligned with `from_date`.

- [ ] **Step 4: Verify syntax**

Run: `python -m py_compile c:/Dev/GannTesting/gann-visualizer/backend/run_binance_replay.py`
Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add gann-visualizer/backend/run_binance_replay.py
git commit -m "feat: align replay engine with frontend execution boundaries and warmup"
```

### Task 4: Strip replay logic from `run_binance_live.py`

**Files:**
- Modify: `c:\Dev\GannTesting\gann-visualizer\backend\run_binance_live.py`

- [ ] **Step 1: Update CLI args**

Remove replay args from `def main():`

```python
def main():
    parser = argparse.ArgumentParser(description="Target Progression Strategy - Live on Binance Testnet")
    parser.add_argument("symbol", default="BTCUSDT", nargs="?", help="Trading pair (default: BTCUSDT)")
    parser.add_argument("interval", default="1h", nargs="?", help="Kline interval (default: 1h)")
    parser.add_argument("--qty", type=float, default=0.01, help="Position size in contracts (default: 0.01)")
    parser.add_argument("--momentum-filter", action="store_true", dest="momentum_filter",
                        help="Only enter on retest if breach momentum was 'momentum'")
    parser.add_argument('--target-progression', action='store_true',
                        help='Run Model B (target progression sequential) alongside Model A')
    args = parser.parse_args()

    client = BinanceClient(use_testnet=True)
    run_live(args.symbol.upper(), args.interval, args.qty, client, momentum_filter=args.momentum_filter)
```

- [ ] **Step 2: Remove `run_replay` function**

Delete the entire `def run_replay` function from `run_binance_live.py`.

- [ ] **Step 3: Verify syntax**

Run: `python -m py_compile c:/Dev/GannTesting/gann-visualizer/backend/run_binance_live.py`
Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add gann-visualizer/backend/run_binance_live.py
git commit -m "refactor: strip replay logic from live script"
```

### Task 5: Add Documentation

**Files:**
- Create/Modify: `c:\Dev\GannTesting\README_BINANCE_TESTING.md`

- [ ] **Step 1: Write README content**

Create the file with the following content:

```markdown
# Binance Testing & Simulation

This project contains two primary tools for testing against the Binance Testnet:

## 1. Historical Replay (`run_binance_replay.py`)
Used for backtesting the strategy over a specific historical time window.

**Usage:**
```bash
python gann-visualizer/backend/run_binance_replay.py BTCUSDT 1h --from-date 2026-05-04 --to-date 2026-05-25 --warmup-days 90
```

**Arguments:**
* `--from-date`: Start date of trading execution (YYYY-MM-DD)
* `--to-date`: End date of trading execution (YYYY-MM-DD)
* `--warmup-days`: (Default: 0). The number of days *prior* to `from-date` to fetch and silently process. This builds the macro Gann fans (historical context) so they are active on Day 1 of your test window. Use `0` for fast manual testing, or `90` to perfectly mirror backend simulation data parity.

## 2. Live Execution (`run_binance_live.py`)
Used for forward-testing on the live websocket feed.

**Usage:**
```bash
python gann-visualizer/backend/run_binance_live.py BTCUSDT 1h --qty 0.01
```
```

- [ ] **Step 2: Commit**

```bash
git add README_BINANCE_TESTING.md
git commit -m "docs: add Binance testing instructions"
```
