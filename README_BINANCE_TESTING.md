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
