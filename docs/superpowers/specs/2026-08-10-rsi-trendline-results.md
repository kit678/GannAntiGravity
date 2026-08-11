# RSI Trendline Break — measurement fixes and multi-year results

**Date:** 2026-08-10
**Supersedes:** §5.2 and §5.4 of [2026-07-27-hypothesis-profitability-handoff.md](2026-07-27-hypothesis-profitability-handoff.md)

## 1. What was wrong with the numbers

The geometry engine built in July was sound — a re-derivation of every entry,
stop, break and exit from raw candles passes 902 assertions with no lookahead
(`scripts/audit_rsi_report.py`). The *measurement* around it was not.

| Defect | Effect on expectancy |
|---|---|
| `simulate_trade_grid` called without `fee_rate`, so the default 0.0 applied | **−0.15R per trade** |
| Entry priced at the signal bar's close, which is not knowable until it closes | −0.03R per trade |
| Headline R taken as whichever of the grid won in hindsight | inflates the headline |
| PnL summed in price units across a 60,000-dollar BTC and a 24,000-point index | pooling meaningless |

Fees dominate everything else. The stop sits ~0.7% from entry on 15m and a
taker round trip costs 0.08%, so **11% of the risk on every trade was fees** —
and none of it was being charged.

Fixed in `analysis/signal_trade_simulator.py` (`entry_bar_index`,
`maker_fee_rate`, `select_r`, `net_r`, `expectancy_r`) and
`analysis/rsi_trendline_hypothesis.py` (execution-model parameters, R-based
summary). Shipped defaults are now next-bar-open entry, 0.04% taker in,
0.02% maker out, and a declared `selected_r=3.0`.

## 2. The 2026-07-27 placebo failure was a false alarm

That test ran `AdjacentAnchorPolicy` with `min_swing=8.0`. Production ships
`CollinearExtendAnchorPolicy` with `min_swing=2.0, tolerance=5.0`. It measured
a configuration the strategy does not use.

Re-run against the shipped configuration, on 4h across 4 symbols:

```
REAL rsi-break        n=1899  win 0.388  exp +0.098R  PF 1.18   <- best
placebo +7 bars       n=1913  win 0.372  exp +0.042R  PF 1.07
placebo +13 bars      n=1909  win 0.387  exp +0.030R  PF 1.06
placebo +37 bars      n=1875  win 0.369  exp +0.006R  PF 1.01
placebo +23 bars      n=1906  win 0.388  exp -0.002R  PF 1.00
placebo flipped side  n=1926  win 0.389  exp +0.013R  PF 1.02
placebo -11 bars      n=1997  win 0.340  exp -0.153R  PF 0.74
```

The real break beats every time-shifted control. `scripts/rsi_research.py
placebo` now drives this through the shipped entry rule via
`RSITrendlineBreakHypothesis.entry_for_break`, so a research script can no
longer test a configuration that does not ship.

## 3. Data

`scripts/fetch_binance_history.py` pulls Binance USD-M futures klines into
`logs/backend/history/<SYMBOL>/<INTERVAL>/candles.csv`. Current corpus: 8
symbols x 15m/1h/4h/6h/12h/1d, 2021-08 to 2026-08 — about 1.1M bars, against
the ~20k of overlapping windows all prior conclusions rested on.

Train/test is a **fixed date**, `2025-01-01`, so adding symbols cannot move the
boundary. Nothing in `sweep` sees test data.

## 4. Result: the edge is real but only above 1h

Shipped configuration, same 4 symbols at every timeframe:

| TF | n | win | ALL exp(R) | TRAIN | TEST |
|---|---:|---:|---:|---:|---:|
| 15m | 33,356 | 0.352 | −0.075 | −0.067 | −0.090 |
| 1h | 7,904 | 0.356 | −0.023 | −0.024 | −0.021 |
| **4h** | 1,899 | 0.388 | **+0.098** | +0.107 | **+0.079** |
| **6h** | 1,266 | 0.385 | **+0.090** | +0.082 | **+0.107** |
| **12h** | 638 | 0.381 | **+0.077** | +0.083 | **+0.063** |
| 1d | 295 | 0.359 | +0.017 | +0.132 | −0.176 |

This is the fee-drag relationship, not a coincidence: the stop widens with the
timeframe, so the same fixed round-trip cost shrinks as a fraction of risk.
1d fails out of sample and its sample is too small to read.

Pooled 4h+6h+12h across 8 symbols, 24 markets, 175k bars:

```
TRAIN (fitted)         n=5165  win 0.385  exp +0.078R  PF 1.14
TEST  (never fitted)   n=2451  win 0.367  exp +0.043R  PF 1.08
TEST  one at a time    n= 270  win 0.415  exp +0.215R  PF 1.42
```

### Robust to cost assumptions

4h, varying the fee both sides:

| per side | ALL exp(R) | TEST exp(R) |
|---|---:|---:|
| 0.02% (VIP maker) | +0.109 | +0.092 |
| 0.04% in / 0.02% out (shipped) | +0.098 | +0.079 |
| 0.05% | +0.090 | +0.071 |
| 0.07% | +0.078 | +0.057 |
| 0.10% (retail + slippage) | +0.059 | +0.036 |

### The parameter surface is a plateau, not a spike

63 trade-rule configurations on train ranged +0.061R to +0.107R. No knife-edge,
which is the main reason to believe the result is not curve-fit. The train-best
(`R=4, hold=40, swing_lookback=10`) also survives out of sample at +0.059R, but
it is not meaningfully better than the shipped values.

## 5. Performance

The sweep was quadratic in pivot count and the payload helpers scanned the whole
frame per lookup. Now ~13x faster end to end, byte-identical output verified
against captured hashes on real data:

- `detect_fractal_candidates` — vectorised over sliding windows (was one
  `pd.concat` per bar)
- `rsi_sweep` — pivots tracked per kind instead of re-filtered per re-anchor
- `signal_trade_simulator` — numpy arrays instead of `.loc` per bar
- `rsi_trendline_hypothesis` — bar-index lookups instead of boolean scans

## 6. What this does NOT establish

- Crypto perpetuals only. Nothing here says anything about NIFTY.
- One market regime. 2021-2026 is a single bull-bear-bull cycle.
- `n` counts overlapping trades. The independent sample is the
  "one position at a time" row — 270 out-of-sample trades, not 2,451.
- The stop is a 20-bar rolling extreme, which on 4h can sit ~10% from entry.
  Expectancy in R says nothing about how that sizes in an account.
- No live or paper trading has been run.

## 7. Paper trading

`run_rsi_paper.py` polls public klines, marks positions bar by bar and logs to
`logs/backend/paper/<SYMBOL>_<INTERVAL>.json`. It places **no orders** and needs
no API key. Signals come from `entry_for_break`, the backtest's own function.

`--replay N` drives the same loop over history one bar at a time and reconciles
it against the backtest trade by trade. It passes on 12 markets across 4h/6h/12h
— identical signal bars, exit reasons and `net_r` to 1e-9. That is the evidence
the live path and the measured path are the same path.

Two bugs it caught, both silent:

- the loop marked positions *before* opening new ones, so a position was never
  exposed to its own entry bar and a gap straight through the stop vanished
- `net_r` derived from an unrounded net while the backtest rounds to 6dp —
  invisible on a 2,000-dollar BTC stop, 2e-4 R on a 0.0024-dollar ADA stop

## 8. Next

1. Let the paper log run on 4h/6h and compare realised expectancy against the
   +0.043R the backtest predicts. No order placement until it has.
2. Sweep the geometry grid (`--grid geometry`), which has not been touched.
3. `slippage_per_side` is an absolute price amount, so it is not usable across
   a corpus spanning a 60,000-dollar BTC and a 0.50-dollar XRP. Make it
   fractional before using it as a stress axis.
4. Re-run the placebo gate after any entry-rule change. It is the gate.
