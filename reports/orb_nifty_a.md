# ORB A — NIFTY

## VERDICT: FAIL

- headline avg net P&L at base costs is -14.9654
- headline avg net P&L at 2x costs is -31.5864
- first-half avg net P&L is -9.7084, so the halves disagree
- placebo percentile 52.0 is below 95 — random entries do about as well

**Breakeven slippage: 0.0 index points per side.**

This is the number to judge margin by — the slippage level at which the edge reaches zero. Compare it against real execution cost for this instrument.

## Sessions

- Available: 1146
- Traded: 1120
- Skipped: 26
    - degenerate_range: 2
    - no_breakout: 16
    - short_opening_range: 8

## Robustness grid (second half)

| Cell | Headline | Trades | Avg net P&L (base) | Avg net P&L (2x costs) | First half |
|---|---|---|---|---|---|
| or=15,r=2.0 | yes | 562 | -14.965375 | -31.586355 | -9.708418 |
| or=30,r=2.0 |  | 546 | -14.168941 | -30.793834 | -7.212244 |
| or=15,r=1.5 |  | 562 | -15.235785 | -31.856758 | -10.659197 |
| or=15,r=3.0 |  | 562 | -13.845487 | -30.466152 | -7.065241 |

R = 1.0, second half, base costs: -15.464787 — reported for information, **not the verdict**.

## Slippage sweep (second half, headline cell)

| Slippage per side | Avg net P&L |
|---|---|
| 0.0 | -12.965375 |
| 0.25 | -13.465375 |
| 0.5 | -13.965375 |
| 1.0 | -14.965375 |
| 1.5 | -15.965375 |
| 2.0 | -16.965375 |
| 3.0 | -18.965375 |

## Placebo

Real result beat 52.0% of 200 random-entry runs. Entries were randomised in bar and direction while holding stop distance and holding period fixed. The pass bar is 95.

Used 200/200 placebo seeds (0 full strength, reproducing all 1120 real signals; the thinnest seed had only 1093).
> **Caution:** fewer than half of placebo seeds were full strength — the comparison distribution is built from a degraded sample.

## Assumptions

- Fee rate: 0.0003 base / 0.0006 stressed. This is an **estimate** of NSE brokerage plus STT, exchange charges, stamp duty and GST, not a measured figure. Refine it against a real contract note.
- Gap-through-stop fills use the exact stop price, which is optimistic. A strategy that fails under this flattering assumption definitely fails.
