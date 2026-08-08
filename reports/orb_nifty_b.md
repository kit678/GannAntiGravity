# ORB B — NIFTY

## VERDICT: FAIL

- headline avg net P&L at base costs is -15.2894
- headline avg net P&L at 2x costs is -31.9106
- first-half avg net P&L is -4.2292, so the halves disagree
- placebo percentile 50.0 is below 95 — random entries do about as well

**Breakeven slippage: 0.0 index points per side.**

This is the number to judge margin by — the slippage level at which the edge reaches zero. Compare it against real execution cost for this instrument.

## Sessions

- Available: 1146
- Traded: 1039
- Skipped: 107
    - no_anchor_bar: 5
    - no_atr: 20
    - no_bars_before_flat: 2
    - no_breakout: 80

## Robustness grid (second half)

| Cell | Headline | Trades | Avg net P&L (base) | Avg net P&L (2x costs) | First half |
|---|---|---|---|---|---|
| k=0.25,r=2.0 | yes | 525 | -15.28936 | -31.910627 | -4.22916 |
| k=0.15,r=2.0 |  | 562 | -17.160232 | -33.782503 | -6.746889 |
| k=0.40,r=2.0 |  | 412 | -11.225234 | -27.834269 | -6.829119 |
| k=0.25,r=1.5 |  | 525 | -16.672545 | -33.29381 | -4.938395 |
| k=0.25,r=3.0 |  | 525 | -16.142784 | -32.763962 | -4.465879 |

R = 1.0, second half, base costs: -20.018247 — reported for information, **not the verdict**.

## Slippage sweep (second half, headline cell)

| Slippage per side | Avg net P&L |
|---|---|
| 0.0 | -13.28936 |
| 0.25 | -13.78936 |
| 0.5 | -14.28936 |
| 1.0 | -15.28936 |
| 1.5 | -16.28936 |
| 2.0 | -17.28936 |
| 3.0 | -19.28936 |

## Placebo

Real result beat 50.0% of 200 random-entry runs. Entries were randomised in bar and direction while holding stop distance and holding period fixed. The pass bar is 95.

Used 200/200 placebo seeds (0 full strength, reproducing all 1039 real signals; the thinnest seed had only 1014).
> **Caution:** fewer than half of placebo seeds were full strength — the comparison distribution is built from a degraded sample.

## Assumptions

- Fee rate: 0.0003 base / 0.0006 stressed. This is an **estimate** of NSE brokerage plus STT, exchange charges, stamp duty and GST, not a measured figure. Refine it against a real contract note.
- Gap-through-stop fills use the exact stop price, which is optimistic. A strategy that fails under this flattering assumption definitely fails.
