# Architectural Assessment: Option Backtesting Framework

## Executive Summary
The current backtesting framework is **partially functional but fundamentally flawed** regarding Options PnL calculation and execution logic. While the visual layer (Replay) works, the underlying engine does not consistently model option trades, often falling back to Spot prices for PnL, leading to inaccurate results.

We **can** do better by unifying the data handling and execution logic to explicitly support Derivative Instruments (Options) instead of treating them as metadata on Spot signals.

## Current Architecture & Limitations

### 1. Hybrid/Duplicate Execution Logic
- **Replay Mode (`main.py/evaluate_strategy_step`)**:
  - Uses `strategy.generate_signals()`.
  - Manually iterates through the dataframe.
  - **Enrichment:** Manually fetches Option Prices via `option_price_cache` and appends them to the JSON response.
  - **Status:** Visuals are correct (showing "Buy PE"), but it doesn't calculate PnL systematically.

- **Batch Backtest (`BacktestEngine`)**:
  - Uses the same `strategy.generate_signals()`.
  - Iterates using internal logic in `_execute_signals`.
  - **Execution:** Uses `row['close']` (Spot Price) for Entry/Exit prices.
  - **PnL:** Calculates PnL based on Spot movement, ignoring Option Strike/Premium.
  - **Status:** The log says "Buy Option", but the math simulates "Long/Short Future" (Delta 1).

### 2. Stateless Strategy Limitations
- `FiveEMAStrategy` operates on the full dataframe (Vectorized/Stateless).
- It generates signals (Buy/Sell) but does not persistently track "Which specific contract was bought".
- **Exit Logic:** Generates `SignalType.SELL` (Exit) based on Spot price action. It does NOT specify *which* option to sell.
- **Result:** The `BacktestEngine` cannot fetch the correct Option Price for the Exit because the contract details (Strike/Expiry) are lost or not passed in the Exit signal.

## Proposed "Better" Architecture

To achieve professional-grade backtesting, we need to refactor the system into a **Execution-First** architecture.

### Phase 1: Fix Data Integrity (Immediate)
**Goal:** Ensure `BacktestEngine` uses Option Prices, not Spot Prices.

1.  **Standardize Signal Data:**
    - Update `BaseStrategy` to define standard columns for derivatives: `contract_symbol` (e.g., "NIFTY25JAN26200PE"), `signal_price` (Premium), `underlying_price` (Spot).
2.  **Stateful Strategy / Signal Context:**
    - Update `FiveEMAStrategy` to store the entered contract details.
    - When generating an Exit signal, populate the `contract_symbol` column with the *same* contract that is being exited.
3.  **Engine Update:**
    - Modify `BacktestEngine` to strictly use `row['signal_price']` for trade execution.
    - Add validation: If `signal_price` is missing for a Trade Signal, fail or warn (don't silently use Spot).

### Phase 2: Unify Execution (Cleanup)
**Goal:** Remove duplicate logic in `main.py`.

1.  **Incremental Engine:** Refactor `BacktestEngine` to support "Step-by-Step" execution (Processing one bar at a time) instead of just "Batch Run".
2.  **Replay Integration:** Update `main.py` Replay endpoint to instantiate a persistent `BacktestEngine` session and call `engine.process_bar(new_bar)`.
    - This ensures Replay visualizes *exactly* what the Backtest calculates.

### Phase 3: Quantity & Portfolio (Features)
1.  **Position Sizing:** Add `RiskModel` class to `BacktestEngine`.
    - `CalculateQuantity(capital, risk_per_trade, stop_loss_amt)`.
2.  **Metrics:** Add Max Drawdown, Sharpe Ratio, and Equity Curve generation.

## Immediate Action Plan (Recommended)

If you agree, we can start with **Phase 1**:
1.  Modify `BacktestEngine` to read `signal_price`.
2.  Refactor `FiveEMAStrategy` to ensure Exits carry the correct Option Contract info so `OptionDataProvider` can fetch the Exit Premium.

This will fix the "I don't see amount" and "PnL is wrong" issues fundamentally.
