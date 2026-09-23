# 0DTE Opening Range Breakout — SPY, QQQ, IWM

- Window: 2025-03-01 to 2026-09-19
- Direction: **bought premium only** (ATM 0DTE call on an upside break, put on a downside break)
- Exits: +100% / -50% / flat by 15:30 ET
- Sizing: $500 notional, sized off the observed premium so contract
  count does not move with the spread; minimum 1 contract so expensive days stay in
- Fee $0.05/contract/side
- Entry is the bar AFTER the breakout bar closes, never the breakout close itself
- A bar spanning both target and stop is scored as a **loss**

**Judge on `Mean ret` and its CI.** `MDE(80%)` is the smallest true edge this
sample could reliably detect — if |Mean ret| < MDE, the run cannot answer the
question either way, whatever the profit factor says.

## Pooled across underlyings, zero spread

| Rule | OR | N | Mean ret | 95% CI | t | MDE(80%) | Win% | PF |
|---|---|---|---|---|---|---|---|---|
| close | 5m | 1169 | +0.84% | [-3.2%, +4.9%] | 0.41 | 5.73% | 34.4% | 1.03 |
| close | 10m | 1168 | +0.38% | [-3.6%, +4.4%] | 0.18 | 5.71% | 34.1% | 1.03 |
| close | 15m | 1168 | +1.25% | [-2.8%, +5.3%] | 0.61 | 5.73% | 34.8% | 1.04 |
| touch | 5m | 1169 | +0.47% | [-3.6%, +4.5%] | 0.23 | 5.74% | 34.0% | 1.03 |
| touch | 10m | 1169 | -0.67% | [-4.6%, +3.3%] | -0.33 | 5.69% | 33.7% | 0.98 |
| touch | 15m | 1170 | -0.27% | [-4.2%, +3.7%] | -0.13 | 5.68% | 34.1% | 1.00 |

## Per-underlying (close rule, zero spread)

| Symbol | OR | N | Mean ret | 95% CI | t | MDE(80%) | Win% | PF |
|---|---|---|---|---|---|---|---|---|
| SPY | 5m | 389 | -0.56% | [-7.5%, +6.4%] | -0.16 | 9.91% | 33.4% | 0.99 |
| QQQ | 5m | 390 | +2.51% | [-4.5%, +9.5%] | 0.70 | 9.97% | 35.6% | 1.10 |
| IWM | 5m | 390 | +0.56% | [-6.4%, +7.5%] | 0.16 | 9.92% | 34.1% | 1.02 |
| SPY | 10m | 389 | +3.22% | [-3.8%, +10.3%] | 0.90 | 10.08% | 35.7% | 1.13 |
| QQQ | 10m | 390 | -1.58% | [-8.4%, +5.2%] | -0.46 | 9.72% | 33.1% | 0.97 |
| IWM | 10m | 389 | -0.51% | [-7.4%, +6.4%] | -0.14 | 9.90% | 33.4% | 0.99 |
| SPY | 15m | 389 | +5.84% | [-1.3%, +13.0%] | 1.61 | 10.18% | 37.8% | 1.19 |
| QQQ | 15m | 390 | -4.64% | [-11.3%, +2.0%] | -1.37 | 9.50% | 31.0% | 0.86 |
| IWM | 15m | 389 | +2.55% | [-4.5%, +9.6%] | 0.71 | 10.07% | 35.5% | 1.08 |

## Spread stress (close rule, pooled)

| OR | Spread | N | Mean ret | 95% CI | t | MDE(80%) | Win% | PF |
|---|---|---|---|---|---|---|---|---|
| 5m | 0% | 1169 | +0.84% | [-3.2%, +4.9%] | 0.41 | 5.73% | 34.4% | 1.03 |
| 5m | 1% | 1169 | -0.17% | [-4.1%, +3.8%] | -0.08 | 5.68% | 34.4% | 1.00 |
| 5m | 2% | 1169 | -1.16% | [-5.1%, +2.8%] | -0.58 | 5.62% | 34.4% | 0.97 |
| 5m | 4% | 1169 | -3.12% | [-7.0%, +0.7%] | -1.59 | 5.51% | 34.1% | 0.91 |
| 5m | 8% | 1169 | -6.92% | [-10.6%, -3.2%] | -3.66 | 5.29% | 34.0% | 0.81 |
| 5m | 12% | 1169 | -10.58% | [-14.1%, -7.0%] | -5.83 | 5.08% | 34.0% | 0.71 |
| 10m | 0% | 1168 | +0.38% | [-3.6%, +4.4%] | 0.18 | 5.71% | 34.1% | 1.03 |
| 10m | 1% | 1168 | -0.62% | [-4.6%, +3.3%] | -0.31 | 5.66% | 34.1% | 1.00 |
| 10m | 2% | 1168 | -1.61% | [-5.5%, +2.3%] | -0.81 | 5.60% | 34.1% | 0.97 |
| 10m | 4% | 1168 | -3.56% | [-7.4%, +0.3%] | -1.82 | 5.49% | 34.0% | 0.91 |
| 10m | 8% | 1168 | -7.35% | [-11.0%, -3.7%] | -3.90 | 5.28% | 33.7% | 0.80 |
| 10m | 12% | 1168 | -10.99% | [-14.5%, -7.4%] | -6.07 | 5.07% | 33.6% | 0.71 |
| 15m | 0% | 1168 | +1.25% | [-2.8%, +5.3%] | 0.61 | 5.73% | 34.8% | 1.04 |
| 15m | 1% | 1168 | +0.24% | [-3.7%, +4.2%] | 0.12 | 5.68% | 34.8% | 1.01 |
| 15m | 2% | 1168 | -0.76% | [-4.7%, +3.2%] | -0.38 | 5.62% | 34.8% | 0.98 |
| 15m | 4% | 1168 | -2.73% | [-6.6%, +1.1%] | -1.39 | 5.51% | 34.7% | 0.92 |
| 15m | 8% | 1168 | -6.55% | [-10.3%, -2.8%] | -3.46 | 5.29% | 34.4% | 0.81 |
| 15m | 12% | 1168 | -10.22% | [-13.8%, -6.7%] | -5.63 | 5.09% | 34.1% | 0.72 |

### Breakeven spread (mean return crosses zero)

- **OR 5m** — crosses zero at a round-trip spread of **0.83%**
- **OR 10m** — crosses zero at a round-trip spread of **0.38%**
- **OR 15m** — crosses zero at a round-trip spread of **1.24%**

## Sessions dropped, and why

_A run that cannot account for every session is not auditable._

| Rule | OR | Skipped |
|---|---|---|
| close | 5m | no_option_data=1 |
| close | 10m | no_option_data=2 |
| close | 15m | no_breakout=1, no_option_data=1 |
| touch | 5m | no_option_data=1 |
| touch | 10m | no_option_data=1 |
| touch | 15m | none |

## OR 5m (close rule), zero spread

### By weekday

_Reported, not used as a filter. Selecting the good days after the fact is how a backtest fools you._

| Day | N | Mean ret | 95% CI | t | MDE(80%) | Win% | PF |
|---|---|---|---|---|---|---|---|
| Mon | 224 | +5.32% | [-4.0%, +14.6%] | 1.12 | 13.31% | 38.4% | 1.19 |
| Tue | 243 | -4.60% | [-13.2%, +4.0%] | -1.04 | 12.35% | 30.0% | 0.86 |
| Wed | 243 | +7.08% | [-1.9%, +16.1%] | 1.54 | 12.89% | 38.7% | 1.23 |
| Thu | 231 | -5.57% | [-14.4%, +3.2%] | -1.24 | 12.54% | 29.9% | 0.84 |
| Fri | 228 | +2.07% | [-7.0%, +11.1%] | 0.45 | 12.96% | 35.1% | 1.09 |

### Chronological halves

| Period | N | Mean ret | 95% CI | t | MDE(80%) | Win% | PF |
|---|---|---|---|---|---|---|---|
| First half (2025-03-03..2025-12-09) | 585 | -0.09% | [-5.7%, +5.5%] | -0.03 | 8.05% | 33.7% | 0.99 |
| Second half (2025-12-09..2026-09-18) | 584 | +1.76% | [-4.0%, +7.5%] | 0.60 | 8.17% | 35.1% | 1.08 |

## OR 10m (close rule), zero spread

### By weekday

_Reported, not used as a filter. Selecting the good days after the fact is how a backtest fools you._

| Day | N | Mean ret | 95% CI | t | MDE(80%) | Win% | PF |
|---|---|---|---|---|---|---|---|
| Mon | 224 | +3.46% | [-5.8%, +12.7%] | 0.73 | 13.18% | 36.6% | 1.11 |
| Tue | 243 | -3.43% | [-12.1%, +5.2%] | -0.78 | 12.35% | 31.3% | 0.92 |
| Wed | 242 | +2.94% | [-5.9%, +11.8%] | 0.65 | 12.67% | 36.0% | 1.10 |
| Thu | 231 | -6.92% | [-15.6%, +1.8%] | -1.56 | 12.43% | 29.0% | 0.83 |
| Fri | 228 | +6.07% | [-3.2%, +15.3%] | 1.28 | 13.25% | 37.7% | 1.24 |

### Chronological halves

| Period | N | Mean ret | 95% CI | t | MDE(80%) | Win% | PF |
|---|---|---|---|---|---|---|---|
| First half (2025-03-03..2025-12-09) | 584 | -0.57% | [-6.2%, +5.1%] | -0.20 | 8.03% | 33.2% | 0.99 |
| Second half (2025-12-09..2026-09-18) | 584 | +1.32% | [-4.4%, +7.0%] | 0.45 | 8.14% | 34.9% | 1.07 |

## OR 15m (close rule), zero spread

### By weekday

_Reported, not used as a filter. Selecting the good days after the fact is how a backtest fools you._

| Day | N | Mean ret | 95% CI | t | MDE(80%) | Win% | PF |
|---|---|---|---|---|---|---|---|
| Mon | 225 | +7.41% | [-1.9%, +16.7%] | 1.56 | 13.26% | 39.6% | 1.24 |
| Tue | 243 | -4.69% | [-13.3%, +3.9%] | -1.07 | 12.24% | 30.9% | 0.85 |
| Wed | 242 | +5.67% | [-3.3%, +14.6%] | 1.24 | 12.83% | 38.0% | 1.22 |
| Thu | 230 | -2.83% | [-11.8%, +6.1%] | -0.62 | 12.78% | 31.7% | 0.91 |
| Fri | 228 | +0.91% | [-8.2%, +10.0%] | 0.20 | 13.00% | 33.8% | 1.03 |

### Chronological halves

| Period | N | Mean ret | 95% CI | t | MDE(80%) | Win% | PF |
|---|---|---|---|---|---|---|---|
| First half (2025-03-03..2025-12-08) | 584 | +4.55% | [-1.2%, +10.3%] | 1.55 | 8.23% | 36.8% | 1.13 |
| Second half (2025-12-09..2026-09-18) | 584 | -2.05% | [-7.6%, +3.5%] | -0.72 | 7.98% | 32.7% | 0.95 |