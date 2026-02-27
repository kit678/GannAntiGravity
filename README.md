# Gann Testing & Visualizer

A comprehensive backtesting and visualization platform for Gann-inspired geometric trading strategies.

## Project Structure

- **`gann-visualizer/`**: The main application.
  - **`frontend/`**: React-based dashboard using TradingView Advanced Charts for visualization.
  - **`backend/`**: FastAPI server handling data fetching, geometric calculations, and strategy execution.
- **`docs/`**: Documentation for strategies and technical standards.

## Gann Strategy Documentation

The "Angular Price Coverage" strategy is documented across two main versions:

### 1. [Angular Price Coverage Strategy (v4.0)](./docs/angular_coverage_strategy_v4.md)
**Status**: Latest Engine Specification (Source of Truth)
- **Focus**: Algorithmic rules for automated fan detection and tracking.
- **Key Logic**: Unified Backward Traversal, Rule 1-6 Fan Filtering, Precise Horizontal Target Derivation.
- **Terminology**: Uses "Anchor" (recent pivot), "Target" (origin pivot), and "Division Line Reversal".

### 2. [Initial Strategy Guide](./docs/ANGULAR_PRICE_COVERAGE_STRATEGY.md)
**Status**: Manual Trading & Confluence Guide
- **Focus**: Context, Momentum Filters, and Multi-Timeframe analysis.
- **Unique Content**: 
  - **Confluence Factors**: EMAs (9/21), VWAP, and RSI momentum filters.
  - **Trade Execution**: Detailed entry/exit protocols and reaction-based confirmations.
  - **Historical Context**: "Outer Container" vs "Inner Sequence" conceptual grouping.
- **Note**: This document has been updated to use the latest terminology from v4.0 for consistency.

## Getting Started

1. **Backend**: 
   ```bash
   cd gann-visualizer/backend
   pip install -r requirements.txt
   python main.py
   ```
2. **Frontend**:
   ```bash
   cd gann-visualizer/frontend
   npm install
   npm run dev
   ```
3. **Tests**:
   ```bash
   cd gann-visualizer/backend
   python -m pytest study_tool/tests/
   ```
