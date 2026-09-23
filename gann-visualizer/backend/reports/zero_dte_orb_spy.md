# 0DTE Opening Range Breakout — SPY

- Window: 2025-03-01 to 2026-09-19 (390 sessions)
- Direction: **bought premium only** (ATM 0DTE call on an upside break, put on a downside break)
- Exits: +100% / -50% / flat by 15:30 ET
- Sizing: $500 notional per trade, fee $0.05/contract/side
- Entry is the bar AFTER the breakout bar closes, never the breakout close itself
- A bar spanning both target and stop is scored as a **loss**

## Spread stress (round-trip, as a fraction of premium)

| OR | Spread | N | Win% | Total P&L | Avg P&L | PF |
|---|---|---|---|---|---|---|
| 5m | 0% | 384 | 33.6% | 292.50 | 0.76 | 1.01 |
| 5m | 1% | 384 | 33.6% | -1,137.65 | -2.96 | 0.98 |
| 5m | 2% | 384 | 33.6% | -2,889.80 | -7.53 | 0.95 |
| 5m | 4% | 384 | 33.6% | -5,170.21 | -13.46 | 0.90 |
| 5m | 8% | 384 | 33.3% | -10,550.44 | -27.48 | 0.81 |
| 5m | 12% | 384 | 33.3% | -17,680.24 | -46.04 | 0.69 |
| 10m | 0% | 385 | 35.8% | 7,268.40 | 18.88 | 1.15 |
| 10m | 1% | 385 | 35.8% | 5,762.73 | 14.97 | 1.12 |
| 10m | 2% | 385 | 35.8% | 4,091.98 | 10.63 | 1.08 |
| 10m | 4% | 385 | 35.8% | 1,270.78 | 3.30 | 1.02 |
| 10m | 8% | 385 | 35.6% | -4,620.72 | -12.00 | 0.91 |
| 10m | 12% | 385 | 35.3% | -11,078.81 | -28.78 | 0.80 |
| 15m | 0% | 385 | 37.7% | 8,806.80 | 22.87 | 1.18 |
| 15m | 1% | 385 | 37.7% | 7,740.11 | 20.10 | 1.16 |
| 15m | 2% | 385 | 37.7% | 6,061.68 | 15.74 | 1.12 |
| 15m | 4% | 385 | 37.7% | 3,167.85 | 8.23 | 1.06 |
| 15m | 8% | 385 | 37.4% | -3,162.22 | -8.21 | 0.94 |
| 15m | 12% | 385 | 37.1% | -9,290.69 | -24.13 | 0.83 |

## Breakeven spread (where average P&L crosses zero)

- **OR 5m** — dies at a round-trip spread of **0.20%**
- **OR 10m** — dies at a round-trip spread of **4.86%**
- **OR 15m** — dies at a round-trip spread of **6.00%**

## OR 5m, zero-cost reference

_Zero cost is not a tradable result. It is the ceiling._

### By weekday

| Day | N | Win% | Total P&L | Avg P&L | PF |
|---|---|---|---|---|---|
| Mon | 73 | 31.5% | -747.10 | -10.23 | 0.93 |
| Tue | 80 | 35.0% | 616.40 | 7.71 | 1.06 |
| Wed | 80 | 38.8% | 2,824.30 | 35.30 | 1.29 |
| Thu | 76 | 26.3% | -3,356.10 | -44.16 | 0.71 |
| Fri | 75 | 36.0% | 955.00 | 12.73 | 1.10 |

### Chronological halves

| Period | Dates | N | Win% | Avg P&L | PF |
|---|---|---|---|---|---|
| First half | 2025-03-03 to 2025-12-11 | 192 | 33.9% | 2.85 | 1.02 |
| Second half | 2025-12-12 to 2026-09-18 | 192 | 33.3% | -1.33 | 0.99 |

## OR 10m, zero-cost reference

_Zero cost is not a tradable result. It is the ceiling._

### By weekday

| Day | N | Win% | Total P&L | Avg P&L | PF |
|---|---|---|---|---|---|
| Mon | 73 | 37.0% | 1,595.70 | 21.86 | 1.16 |
| Tue | 81 | 35.8% | 1,829.70 | 22.59 | 1.17 |
| Wed | 80 | 40.0% | 3,655.60 | 45.70 | 1.39 |
| Thu | 76 | 28.9% | -1,932.50 | -25.43 | 0.83 |
| Fri | 75 | 37.3% | 2,119.90 | 28.27 | 1.23 |

### Chronological halves

| Period | Dates | N | Win% | Avg P&L | PF |
|---|---|---|---|---|---|
| First half | 2025-03-03 to 2025-12-11 | 193 | 35.2% | 13.86 | 1.11 |
| Second half | 2025-12-12 to 2026-09-18 | 192 | 36.5% | 23.92 | 1.19 |

## OR 15m, zero-cost reference

_Zero cost is not a tradable result. It is the ceiling._

### By weekday

| Day | N | Win% | Total P&L | Avg P&L | PF |
|---|---|---|---|---|---|
| Mon | 74 | 40.5% | 2,138.00 | 28.89 | 1.23 |
| Tue | 81 | 37.0% | 1,515.30 | 18.71 | 1.14 |
| Wed | 80 | 43.8% | 4,846.20 | 60.58 | 1.54 |
| Thu | 75 | 32.0% | -855.70 | -11.41 | 0.92 |
| Fri | 75 | 34.7% | 1,163.00 | 15.51 | 1.12 |

### Chronological halves

| Period | Dates | N | Win% | Avg P&L | PF |
|---|---|---|---|---|---|
| First half | 2025-03-03 to 2025-12-10 | 193 | 40.4% | 38.55 | 1.32 |
| Second half | 2025-12-11 to 2026-09-18 | 192 | 34.9% | 7.12 | 1.05 |