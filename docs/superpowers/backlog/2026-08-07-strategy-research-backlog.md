# Strategy Research Backlog — What We Skipped and Why

**Created:** 2026-08-07
**Purpose:** A durable record of every option we deliberately did not take while hunting for a short-term, leverage-friendly trading edge. If ORB fails, work down this list rather than re-deriving it.

**Context:** Goal is short-term trading on instruments with implied leverage — index/stock/commodity futures, index options (NIFTY/BANKNIFTY via Dhan), crypto perps (Binance). Candidates were sourced from the TradingView public script library on 2026-08-07 (~72 strategies sampled across three pages sorted by popularity, plus the curated Editors' Picks list).

Current active work: [ORB go/no-go design](../specs/2026-08-07-orb-strategy-design.md).

---

## Level 1 — ORB design choices deferred

Skipped to keep the go/no-go test small and hard to overfit. Revisit **only if ORB passes**; adding these to a failing strategy is how a dead edge gets resurrected as a curve fit.

| Item | Why skipped | What it would take |
|---|---|---|
| Variant C: breakout + retest | Better entry price, but the strongest trending days never retest — and those are exactly the days a 0DTE option pays for | Third signal module with the same `generate_signal` interface |
| Parameter sweeps (range length, R, k) | Sweeping before establishing a base edge produces beautiful backtests that lose money | Grid runner + a proper nested walk-forward, not a single split |
| Trailing stop / move to breakeven | Changes the exit distribution; a v1 with fixed R is the cleanest read on signal quality | Simulator gains a stop-update callback |
| Partial profit taking / scaling out | Same reason; also complicates the R-multiple accounting | Multi-leg exit support in the simulator |
| Re-entry after a stop-out; >1 trade/day | Multiplies trade count, which flatters significance tests | Loosen the one-signal-per-session rule in the runner |
| Entry filters: volume surge, gap size, higher-timeframe trend, prior-day range | Each filter is a free parameter and a chance to fit noise | Filter layer between signal generation and simulation |
| Day-of-week / expiry-day conditioning | Very likely where any real edge concentrates in Indian index options, but it is a slice-and-search over an already small sample | Post-hoc segmentation with multiple-comparison correction |
| Position sizing, leverage, compounding, equity curves | v1 measures per-trade expectancy in R, which is the right unit for a go/no-go | Portfolio layer on top of the trade list |
| Long/short asymmetry analysis | Worth knowing, but not needed to decide go/no-go | Split the report by side |
| US market ORB (SPY/QQQ/ES) | This is where the published evidence actually comes from, but the repo has no US option pricing at all | US option data source + a second `option_contract_service` implementation |

---

## Level 2 — Other strategy candidates parked

Ranked by what we would try next.

### Next up if ORB fails

**1. CRT / liquidity sweep (failed breakout reversal)**
Source: `SATTAM | CRT+TBS` on TradingView. Mechanical core, stripped of the "smart money" narrative: a wick takes out a prior swing high/low, the candle closes back inside, fade the failed break.
*Why it's next:* cheapest possible test. The repo already contains a near-identical detector in `gann-visualizer/backend/strategy/entry_detectors/breach_retest.py`, plus a whole event-logging and hypothesis-testing layer around it. Likely a matter of re-pointing existing machinery rather than new code.
*Fit:* index futures, crypto perps. Reversal trades are shorter and smaller than breakouts, so option suitability is unproven.

**2. Donchian intraday momentum breakout**
Source: <https://www.tradingview.com/script/f2lBhqNS-Donchian-Intraday-Momentum-Breakout/>
Turtle-style N-bar high/low breakout with an ATR trailing stop, flat by end of day. Very few parameters, which is the main attraction.
*Fit:* BTC/ETH perps on Binance (unlimited free history via `binance_client.py`), plus CL/GC commodity futures.
*Note:* structurally close to ORB. If ORB fails for breakout-specific reasons, this probably fails too — test it on a different asset class rather than the same one.

**3. Z-Edge multi-factor Z-score**
Source: <https://www.tradingview.com/script/W67tJltC-Z-Edge-Confluence-Z-score-Strategy/>
Standardises momentum, RSI and relative volume into one composite Z-score; trades either trend-following or mean-reversion off it. ATR-based sizing.
*Why parked:* the quant framing is sound but it carries many weights and thresholds — a large overfitting surface for a first test.

**4. VWAP band mean reversion**
Source: <https://www.tradingview.com/script/CNC6abWu-VWAP-Band-Mean-Reversion/>
Fade stretches beyond a VWAP standard-deviation band, ADX filter to avoid trend days, flat by EOD.
*Why parked:* **futures only.** The moves are too small and too slow for bought options — theta and spread would consume the edge. Useful as a range-day complement to ORB if ORB passes, since the two should be uncorrelated.

### Rejected outright — do not revisit without a specific reason

| Strategy | Reason |
|---|---|
| Martingale / grid systems (`inwCoin Martingale`, `Grid Like Strategy`) | Averaging down under leverage produces liquidation, not profit. The backtest looks perfect right up until the trade that ends the account |
| `TT-Autotune` (Lorentzian classification ML) | ~30 tunable parameters and the published numbers depend on vendor-supplied "sync codes" from a paid service. Unreproducible by construction |
| Single-symbol vendor bots (`RK Gold Sniper AI PRO`, `XAUUSD SCALPING WIZER`, `ryans XAUUSD SMC Signal Bot`, `NAS100 Practical SMC`) | Fitted to one instrument, marketing-led, no out-of-sample evidence |
| Generic EMA / MACD / Supertrend confluence stacks | Dozens of near-identical posts. Well documented as having no standalone edge. May still be useful as a regime *filter* on top of something that works |
| `SVT Big Swing Capture`, `Sector Rotation` variants | Multi-day to multi-week holds. A short-dated option expires before the thesis resolves |

### Observation worth keeping

TradingView's curated **Editors' Picks for strategies is almost entirely infrastructure**, not alpha — backtest templates, trailing-stop examples, position sizing, Kelly ratio, leverage/margin handling, monthly-returns reporting. The platform's own curators are effectively signalling that the community's strategy *logic* is not the valuable part. Treat any high-engagement community strategy as a starting hypothesis, never as evidence.

---

## Level 3 — Infrastructure gaps noticed, not fixed

Found while reading the backend on 2026-08-07. None block ORB; all are real.

**`backtest_engine.py` silently ignores costs.**
The constructor accepts `commission` and `slippage`, stores them, and never uses them — `_close_position` computes raw `exit_price - entry_price`. Every result this engine has ever produced is optimistic by exactly the transaction cost. Either wire the parameters through or delete them so callers cannot be misled. ORB avoids the problem by using `analysis/signal_trade_simulator.py` instead, which does apply both.

**`backtest_engine.py` cannot express intrabar exits.**
It consumes bar-close signals only, so it cannot model a stop and a target competing within one bar. Any strategy needing brackets must use `signal_trade_simulator.py`.

**Gap-through-stop fills are optimistic.**
`signal_trade_simulator._simulate_single_trade` fills at the exact stop price even when the bar gapped straight past it. Acceptable for go/no-go (a strategy that fails under a flattering assumption definitely fails) but must be corrected before any live sizing decision.

**yfinance intraday history is too short for validation.**
`yfinance_client.INTERVAL_LIMITS` caps 5m/15m/30m at 59 days and 1m at 7. Roughly 40 sessions — fine for development, useless for a verdict. Real conclusions need Dhan (blocked on an API key refresh as of 2026-08-07) or another vendor.

**No US options data path.**
`option_contract_service.py`, `option_selector.py` and `option_data_provider.py` are Dhan/NSE-specific: Indian underlyings, Indian expiry conventions. Testing any strategy on US 0DTE options requires a whole second data path.

**Indian index expiry weekdays have changed repeatedly.**
Do not hardcode. Read the live list through `OptionSelector.get_expiry_list()`.
