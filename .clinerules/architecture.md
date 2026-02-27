# Gann Backtesting Framework: Core Architecture
You are an expert developer specializing in this modular backtesting and visualization framework.

## 1. Separation of Concerns
- **Strategy Layer** (`strategies.py`): Pure signal generation (BUY/SELL/HOLD). Returns a DataFrame with signals but maintains NO internal position state.
- **Execution Layer** (`backtest_engine.py`): Universal engine. Consumes signals and manages entry, exit, stop-losses, and P&L calculation.
- **API Layer** (`main.py`): Coordinates data flow between data clients, strategies, and the backtesting engine.

## 2. Modular Strategy Design
- All new strategies MUST inherit from `BaseStrategy` (found in `base_strategy.py`).
- Implement the `generate_signals(self)` method to return a DataFrame with `signal` and `signal_label` columns.
- Use `SignalType` enum for consistency.

## 3. Tech Stack
- **Backend**: Python (FastAPI, Pandas, Pytest).
- **Frontend**: React (Vite), TradingView Advanced Charts.
- **Data Clients**: `DhanClient` (India Markets) and `YahooFinanceClient` (Indices/Global).
