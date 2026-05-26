# Binance Testnet & Simulation Alignment Design

## Objective
Align the data fetching logic of the Binance testnet historical replay script with the backend simulation engine. This ensures both systems process the exact same sequence of historical candles, resulting in identical fan generation, sequential fan IDs, and macro context. It also extracts live trading functionality into a dedicated script.

## Core Changes

### 1. Unified Argument Structure
Both scripts will use the exact same parameters to define the time window and history depth:
* `--from-date`: Start of the actual testing window (YYYY-MM-DD)
* `--to-date`: End of the actual testing window (YYYY-MM-DD)
* `--warmup-days`: Explicit integer defining how many days of history to fetch prior to `from-date` to build macro fans.
  * **Default behavior:** If the user does not provide `--warmup-days`, it defaults to `0` (no macro warmup).

### 2. File Restructuring
`run_binance_live.py` is currently doing double-duty (historical replay and live execution). It will be split:
* **`run_binance_replay.py`**: The historical backtester. It will use the new unified date/warmup arguments and execute the strategy over a bounded time window.
* **`run_binance_live.py`**: Stripped down to strictly run forward-testing on the live websocket feed.

### 3. Data Fetching & Pagination
* Both the simulation and the replay script will calculate the `fetch_start_date` by subtracting `--warmup-days` from `--from-date`.
* The `BinanceClient.fetch_klines_range` method (which handles paginating past Binance's 1000-candle limit) will be utilized to pull the complete dataset from `fetch_start_date` to `--to-date`.
* The engine will feed all candles into `AngularPriceCoverageStudy`.
* **Execution Boundary:** The strategy state machine (tracking trades, PnL, target hits) will be programmed to *ignore* all candles prior to `--from-date`. It will silently build fans during the warmup, but only start executing trades once the chronological timestamp crosses `--from-date`.

## Documentation
* A `README_BINANCE_TESTING.md` will be created (or updated if one exists) explaining how to use both `run_binance_replay.py` and `run_binance_live.py`, with specific examples of how to configure `--warmup-days` for macro context vs. rapid testing.

## Out of Scope
* Modifying the core Gann math (`AngularPriceCoverageStudy`)
* Altering the frontend visualization layer
