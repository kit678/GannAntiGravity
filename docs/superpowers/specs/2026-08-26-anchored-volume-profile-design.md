# Anchored Volume Profile — Design

**Date:** 2026-08-26
**Status:** Design — approved, not yet implemented
**Scope:** Backend indicator + REST endpoint + TradingView Charting Library overlay.

## Goal

Produce an anchored volume profile: given a starting bar (the *anchor*), bucket
traded volume by price level from that bar to now, and report where price spent
the most volume.

Outputs: the histogram itself, POC (point of control, the highest-volume price
bucket), VAH/VAL (value area high and low, the band containing a configurable
share of total volume), and HVN/LVN (high/low volume nodes, local peaks and
troughs in the histogram).

Consumers: the chart overlay for visual study, and Python strategies/backtests
that want POC/VAH/VAL as numbers. Both read the same code path.

## Provenance — what is reused and what is not

The instruction was to reuse an open-source implementation rather than write
from scratch. The honest result of that search:

**No drop-in exists for this stack.** The frontend uses TradingView's licensed
**Charting Library** (`gann-visualizer/frontend/public/charting_library/`). Its
Volume Profile is a separately-licensed paid add-on, and a horizontal histogram
cannot be produced by the custom-study plotting API. The good open-source
plugin (`tradingview/lightweight-charts` `plugin-examples/src/plugins/volume-profile/`,
Apache-2.0) targets *Lightweight Charts*, a different library, and does not
apply.

**What is reused:** two functions from
[bfolkens/py-market-profile](https://github.com/bfolkens/py-market-profile),
**BSD-3-Clause, Copyright (c) 2017 Brad Folkens**. Last release 0.1.1, June 2018.

1. `utils.midmax_idx` — selects the POC bucket, breaking volume ties toward the
   middle of the profile instead of taking the first maximum. Correct behaviour
   that most implementations omit.
2. `MarketProfileSlice.calculate_value_area` — the expansion walk that grows
   outward from the POC, always taking the heavier neighbour, until the target
   volume share is met.

These are vendored into the repo (source copied, not pip-installed) because the
package pins 2018-era pandas. Attribution and the full BSD-3 text ship alongside.

**What is deliberately not reused:** `build_profile`. It buckets on **closing
price only**, ignoring each candle's high and low, and rounds with `math.ceil`,
which biases every price upward by up to one row. Our binning is written fresh.

### Upstream bugs that must be fixed on vendoring

Both are in `calculate_value_area`. Both get a regression test.

1. **Falsy-zero.** The guards read `if not high_volume or (low_volume and ...)`.
   A bucket holding exactly `0.0` volume is falsy and is therefore treated as
   "no such bucket / edge of profile", steering the expansion the wrong way.
   Empty buckets are common in a fine-grained crypto profile. Fix: compare with
   `is None`.
2. **Off-by-one expansion.** The loop condition is `while trial_vol <= target_vol`,
   so when the accumulated volume lands exactly on the target it expands one
   bucket too far. Fix: `while trial_vol < target_vol`.
3. **Crash at the profile edges.** When `min_idx` is already `0` and `max_idx`
   is already `len-1`, both neighbours clip to themselves, so both
   `low_volume` and `high_volume` are `None`. The first branch then evaluates
   `trial_vol += None` and raises `TypeError`. The `else: break` is unreachable
   in that case. Triggers whenever the target volume share cannot be reached —
   thin data, or `value_area_pct` near 1.0. Fix: break when both neighbours are
   `None`.

## Architecture

New package `gann-visualizer/backend/indicators/volume_profile/`.

```
indicators/volume_profile/
  __init__.py            public surface: compute_anchored_profile, resolve_anchor
  vendor/
    LICENSE-py-market-profile   BSD-3 text + copyright notice
    market_profile_core.py      midmax_idx + value-area walk, bugs fixed
  binning.py             bars -> price buckets
  profile.py             compute_anchored_profile (the one public entry point)
  anchors.py             anchor resolvers
```

Separation of concerns follows `backend/ARCHITECTURE.md`: the indicator is a
pure computation layer, `main.py` stays the API layer and does the data
fetching.

### The core contract

```python
def compute_anchored_profile(
    bars: pd.DataFrame,          # columns: time, open, high, low, close, volume
    anchor_ts: int,              # epoch SECONDS, UTC
    fine_bars: pd.DataFrame | None = None,   # 1m bars covering the same window
    bins: int = 24,
    value_area_pct: float = 0.70,
    hvn_lvn_order: int = 2,
) -> VolumeProfileResult
```

`bars` always defines the bucket edges and the bar count. `fine_bars` is used
only to distribute volume; when it is `None` the `estimated` path runs. The
caller — `main.py` — owns fetching both and decides whether the fine fetch
succeeded. The indicator itself never touches the network.

`compute_anchored_profile` takes **one plain anchor timestamp** and nothing
else. It does not know how that timestamp was chosen, does not fetch data, and
does not touch the network. This is what makes the anchor configurable at no
cost to the math, and it is what makes the function testable with hand-built
fixtures.

`VolumeProfileResult` is a dataclass with `to_dict()`, matching the style of
`study_tool/study_tool.py`:

| field | meaning |
|---|---|
| `anchor_ts` | echoed anchor, epoch seconds UTC |
| `bin_edges` | `list[float]`, length `bins + 1`, ascending |
| `bin_volumes` | `list[float]`, length `bins` |
| `poc_price` | midpoint of the POC bucket |
| `vah`, `val` | value area high / low, bucket midpoints |
| `total_volume` | sum of `bin_volumes` |
| `hvn`, `lvn` | `list[float]` prices of local peaks / troughs |
| `source` | `"1m"` or `"estimated"` — how volume was distributed |
| `bar_count` | bars actually used |

Degenerate input (no bars after the anchor, or zero total volume) returns a
result with `poc_price`, `vah`, `val` set to `None` and empty node lists. It
does not raise.

### Binning (`binning.py`)

Bucket edges span `[min(low), max(high)]` over the anchored bar range, split
into `bins` equal-height buckets. Explicit edges, no `ceil` rounding.

Two strategies for distributing a candle's volume across buckets:

- **`fine` (default).** Fetch 1-minute bars covering the same window and bucket
  each 1m candle's volume at its own typical price `(H+L+C)/3`. Sets
  `source="1m"`.
- **`estimated` (fallback).** Spread each candle's volume uniformly across every
  bucket its high-low range touches, pro-rata by overlap. Sets
  `source="estimated"`.

The fallback is used automatically when 1m bars are unavailable — Dhan/NIFTY
intraday history, or a requested window older than the venue's 1m retention.
Falling back is logged at WARNING and surfaced in `source`; it never raises.
The frontend displays `source` so a degraded profile is never mistaken for a
precise one.

Note that when the chart resolution is already 1m, `fine` and `estimated`
differ, and `fine` degenerates to typical-price bucketing of the same bars.
This is intended.

### Anchors (`anchors.py`)

Each resolver returns a single epoch-seconds-UTC timestamp. Nothing else.

| resolver | behaviour |
|---|---|
| `manual(ts)` | identity; the bar the user clicked |
| `session_start(bars, session, tz)` | first bar at or after the session open of the most recent session in `bars` |
| `pivot(bars, direction, left_bars, right_bars)` | timestamp of the most recent confirmed swing high/low |

`pivot` does **not** call `study_tool/pivot_detector.py`. That class is stateful
and writes to a module-level pivot registry shared with the fan study; calling
it here would pollute that state as a side effect of drawing an indicator. The
resolver instead runs its own pure left/right-bars swing scan — about fifteen
lines, no shared state, and it uses the same `left_bars`/`right_bars`
convention so results agree with the fan study.

`session_start` is the only place a non-UTC timezone appears, and it converts
back to UTC before returning. Adding a fourth resolver later is one function in
one file, plus one enum value in the request model.

## API

`POST /api/volume_profile` in `main.py`, following the shape of the existing
`/fetch_candles` route.

Request:

```json
{
  "symbol": "BTCUSDT",
  "resolution": "5",
  "data_source": "binance",
  "from_ts": 1756166400,
  "to_ts": 1756252800,
  "anchor": { "mode": "manual", "ts": 1756170000 },
  "bins": 24,
  "value_area_pct": 0.70
}
```

`anchor.mode` is one of `manual` | `session_start` | `pivot`, with mode-specific
extra fields (`session`/`tz`, or `direction`/`lookback`). Response is
`VolumeProfileResult.to_dict()`.

**Timezone rule, stated once and applied everywhere:** every timestamp crossing
this endpoint, in either direction, is **epoch seconds in UTC**. `main.py:605`
shows Binance and yfinance are already UTC while Dhan is IST; the IST
conversion happens inside the data-fetch layer only, never in the indicator,
never in the request or response. This is the same class of defect as the
timezone-shifted RSI Navigator overlay and is being closed by construction.

**Unit rule.** `binance_client._parse_klines` emits `time` in epoch
*milliseconds*, and the frontend candle objects carry milliseconds too, while
TradingView shape points take *seconds*. The indicator works in seconds
throughout. A `normalize_time_seconds` helper in `binning.py` detects
millisecond input (values above 1e11) and divides, so a caller passing raw
Binance bars cannot silently produce an empty profile.

Validation: `bins` in `[4, 50]`, `value_area_pct` in `(0.0, 1.0)`, `anchor.ts`
within `[from_ts, to_ts]`. Out-of-range values return HTTP 422 rather than
being silently clamped.

## Frontend overlay

New `gann-visualizer/frontend/src/study_tool/VolumeProfileOverlay.js`.

Draws, anchored at `anchor_ts` and extending rightward:

- One `rectangle` per bucket via `chart.createMultipointShape`, horizontal
  length scaled to `bin_volume / max(bin_volumes)`. The POC bucket is drawn in
  a distinct colour.
- Three `horizontal_line` shapes for POC, VAH, VAL, each labelled with its price.
- HVN/LVN drawn as short tick marks, toggleable, off by default.

It reuses the creation/disposal conventions already established in
`src/study_tool/StudyDrawingUtils.js` (which uses `createMultipointShape` at
line 144 and `createShape` at line 191): every shape id is retained in an array
and removed on redraw, so repeated anchor changes cannot leak drawings.

**Performance constraint.** Each bucket is a real chart drawing object, not a
canvas primitive. Default `bins` is 24 and the hard cap is 50, enforced on both
the API (422) and the client (input clamp). Redraw is debounced so dragging the
anchor does not fire a request per bar.

Anchor selection UI: a small control offering the three modes. `manual` arms a
one-shot chart click handler that reads the clicked bar's time.

## Testing

Python, under `gann-visualizer/backend/tests/`, matching the existing pytest
layout (e.g. `test_target_progression.py`).

**Vendored-code regression tests** (these are the reason for vendoring rather
than installing):

- A profile containing a `0.0`-volume bucket between two populated buckets:
  the value area must span it correctly. Fails on the upstream falsy-zero bug.
- `value_area_pct = 0.99` on a narrow profile: must return the full profile
  range, not raise `TypeError`. Fails on the upstream edge crash.
- Tied bucket volumes: POC must land on the middle tied bucket, confirming
  `midmax_idx` behaviour survived vendoring.

**Indicator tests**, all on hand-built fixtures with the answer worked out by
hand — no recorded-output snapshots:

- Known POC/VAH/VAL on a small synthetic bar set.
- Determinism: identical input yields byte-identical output across two calls.
- Anchor isolation: bars before `anchor_ts` contribute zero volume.
- Fallback: with the 1m fetch stubbed to fail, the call succeeds, uses the
  even-spread path, and reports `source == "estimated"`.
- Degenerate input: zero bars after the anchor, and all-zero volume, both
  return `None` prices without raising.
- Bin-edge coverage: `sum(bin_volumes)` equals total input volume, so no
  volume is dropped at the boundaries.

**Anchor resolver tests:** `session_start` across a DST-shifting timezone and
across a UTC-day boundary, asserting the returned timestamp is UTC.

**Frontend:** a `.test.mjs` beside the module, matching the existing pattern
(`hypothesisRsiOverlay.test.mjs`), covering shape-id cleanup on redraw and the
bin-count clamp. Rendering itself is not unit-tested.

## Out of scope (YAGNI)

Explicitly not built, to be added only if a concrete need appears:

- Buy/sell volume delta split.
- TPO / letter market profile (`mode='tpo'` upstream) — volume mode only.
- Comparing two anchors on one chart simultaneously.
- Persisting computed profiles to disk or a cache tier beyond the existing
  `cache_manager.py`.
- Naked POC tracking across sessions.
- Any strategy or signal built on the profile. This ships the indicator only.

## Risks

| risk | mitigation |
|---|---|
| Shape count degrades chart performance | 24 default, 50 cap, debounced redraw |
| 1m fetch doubles API calls and latency | Route through existing `cache_manager.py`; `estimated` fallback keeps it working |
| `estimated` profile silently mistaken for precise | `source` field returned and displayed |
| Vendored code drifts from upstream | Upstream is dead since 2018; vendored copy is now ours, covered by its own tests |
| Anchor timezone drift | Single UTC-epoch-seconds rule at the API boundary |
