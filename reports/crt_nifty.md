# ORB C — NIFTY

## VERDICT: FAIL

- headline avg net P&L at base costs is -15.1748
- headline avg net P&L at 2x costs is -31.7966
- first-half avg net P&L is -14.2228, so the halves disagree
- placebo percentile 89.0 is below 95 — random entries do about as well

**Breakeven slippage: 0.0 index points per side.**

This is the number to judge margin by — the slippage level at which the edge reaches zero. Compare it against real execution cost for this instrument.

## Sessions

- Available: 1146
- Traded: 1138
- Skipped: 8
    - insufficient_lookback: 4
    - no_bars_before_flat: 1
    - no_sweep: 3

## Robustness grid (second half)

| Cell | Headline | Trades | Avg net P&L (base) | Avg net P&L (2x costs) | First half |
|---|---|---|---|---|---|
| n=12,r=2.0 | yes | 571 | -15.174759 | -31.796629 | -14.222788 |
| n=8,r=2.0 |  | 572 | -14.577743 | -31.200066 | -15.939308 |
| n=20,r=2.0 |  | 568 | -17.727498 | -34.351299 | -15.794872 |
| n=12,r=1.5 |  | 571 | -15.963722 | -32.585806 | -14.673978 |
| n=12,r=3.0 |  | 571 | -15.574893 | -32.196896 | -13.632032 |

R = 1.0, second half, base costs: -17.365124 — reported for information, **not the verdict**.

## Slippage sweep (second half, headline cell)

| Slippage per side | Avg net P&L |
|---|---|
| 0.0 | -13.174759 |
| 0.25 | -13.674759 |
| 0.5 | -14.174759 |
| 1.0 | -15.174759 |
| 1.5 | -16.174759 |
| 2.0 | -17.174759 |
| 3.0 | -19.174759 |

## Placebo

Real result beat 89.0% of 200 random-entry runs. Entries were randomised in bar and direction while holding stop distance and holding period fixed. The pass bar is 95.

Used 200/200 placebo seeds (0 full strength, reproducing all 1138 real signals; the thinnest seed had only 1109).
> **Caution:** fewer than half of placebo seeds were full strength — the comparison distribution is built from a degraded sample.

## Assumptions

- Fee rate: 0.0003 base / 0.0006 stressed. This is an **estimate** of NSE brokerage plus STT, exchange charges, stamp duty and GST, not a measured figure. Refine it against a real contract note.
- Gap-through-stop fills use the exact stop price, which is optimistic. A strategy that fails under this flattering assumption definitely fails.
