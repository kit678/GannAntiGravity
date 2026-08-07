# Agent Instructions

Gann-inspired backtesting and visualization framework. The point of this repository is
to find a profitable trading strategy by iterating on hypotheses — favour fast, correct
iteration over polish.

## Commit Convention

Conventional Commits: `<type>: <subject>` — imperative mood, lower case, no trailing period.

| Type | Use for |
|---|---|
| `feat` | A new strategy, hypothesis, detector, or capability |
| `fix` | Corrected behaviour in existing logic |
| `refactor` | Restructuring with no behaviour change |
| `test` | Tests only |
| `docs` | Documentation only |
| `chore` | Tooling, config, comparison runs |
| `spec` | A design document under `docs/superpowers/specs/` |
| `plan` | An implementation plan under `docs/superpowers/plans/` |
| `baseline` | Checking in existing code untouched, before a redesign modifies it |

## Skills

Write a skill when a **research loop** repeats — running a sweep, scoring a hypothesis,
adding a new hypothesis, comparing anchor policies. Those are the workflows retyped from
memory each session, and the ones where a forgotten step silently corrupts a result.

Do not write a skill for ordinary code changes done twice. The bar is deliberately high:
time spent growing the skill library is time not spent testing hypotheses.

## Worktree Convention

One worktree per line of work, under `.worktrees/<name>/`:

```bash
git worktree add .worktrees/<name> -b <branch>
```

`.worktrees/` is gitignored. Never run two agents against the same working tree — they
overwrite each other's edits mid-run.

## Merge Convention

Merge one branch at a time. When a worktree's work is finished and its tests pass, merge
it into `main`, then rebase the remaining worktrees onto the new `main` before continuing
in them.

Do not batch several branches into one merge. With no CI to thrash and one developer,
batching only delays conflicts and makes them land together.

## Architecture

Backend lives in `gann-visualizer/backend/`. Separation of concerns:

- **Strategy layer** (`strategies.py`) — pure signal generation (BUY/SELL/HOLD). Returns a
  DataFrame of signals; holds no position state.
- **Execution layer** (`backtest_engine.py`) — universal engine. Consumes signals and
  manages entry, exit, stop-loss, and P&L.
- **API layer** (`main.py`) — coordinates data clients, strategies, and the engine.

New strategies inherit from `BaseStrategy` (`base_strategy.py`) and implement
`generate_signals(self)`, returning `signal` and `signal_label` columns. Use the
`SignalType` enum.

**Stack:** Python backend (FastAPI, pandas, pytest); React frontend (Vite, TradingView
Advanced Charts); data via `DhanClient` (India), `BinanceClient` (crypto), and
`YFinanceClient` (global indices).

## Geometry Standards

- **Coordinates** — the backend works in price and Unix seconds. The frontend uses a fixed
  price-to-bar ratio (5.5) for rendering sanity.
- **Pivots** — use `PivotDetector` (`study_tool/pivot_detector.py`) for all anchor
  identification.
- **Angular Price Coverage (v4)** — follow the Unified Backward Traversal exactly as
  documented in `docs/strategy/angular_coverage_strategy_v4.md`. Breach direction is fixed
  by anchor type: a low anchor tracks upward breaches, a high anchor downward. Say
  "Division Line Reversal", never "Breach Failure".

## Verification

Run `python -m pytest` from `gann-visualizer/backend/` before claiming a task is complete.
New logic needs a matching test in `gann-visualizer/backend/tests/`.

A hypothesis result that looks profitable is the most likely place for a bug to hide.
Before trusting one, check the run for lookahead: an entry priced off a bar that had not
closed, a target scored against data the strategy could not have seen, or a retro-tagged
event counted in live performance.
