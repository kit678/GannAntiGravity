# Gann Ladder Event Logger — Design

Date: 2026-08-31
Status: approved, not yet implemented
Scope: Phase 2 of three
Repo: `C:\Dev\GannTesting` (this one). Phase 1 lives in `C:\Dev\GannSq9`.

## Purpose

Walk historical bars and record every interaction between price and a Gann
Square-of-9 level, producing a dataset Phase 3 can mine for a tradeable edge.

This phase records. It does not predict, score, or rank. The movement rules in
the Phase 1 spec are hypotheses this dataset exists to test, and must not be
encoded as logic here.

## Why this lives in GannTesting

The angular coverage strategy in `gann-visualizer/backend/study_tool/` already
has the vocabulary this needs: `breach_mode` of `'wick' | 'close'`, a
successive-closes confirmation, and a reversal case for crossings that fail to
confirm. Rebuilding that in the GannSq9 repo would produce two datasets that
can never be compared.

Inspection of `event_logger.py` confirms `Event` is already schema-flexible —
every field optional, no fan logic in the logger itself — and already carries
what a multi-strategy corpus needs:

- `instrument`, `timeframe` — multi-instrument, multi-timeframe corpora
- `mfe_5/10/20/50`, `mae_5/10/20/50` — forward-looking outcomes
- `reversal_outcome`, `body_break`
- `export_csv`, `export_json`, `export_hypothesis_json`

So this design **extends** `EventType` and `Event`, and adds one new analyzer
alongside `BreachAnalyzer`. It does not fork any of them.

## Phase 1 dependency

The level ladder engine is `utils/gannLevels.js` in `C:\Dev\GannSq9`, exporting
`buildLadder`, `crossMarks`, `armDegree`, `subdivide`, `ringOf`. It is
JavaScript; this repo's study tooling is Python.

**Decision: port the ladder maths to Python rather than bridge to Node.**

A subprocess or HTTP bridge would add a failure mode and a serialisation cost
to the innermost loop of a bar walk that may run millions of iterations. The
maths is small — five pure functions, no dependencies — and is pinned by 37
existing JS tests whose expected values can be reused verbatim as the Python
tests' expected values. That makes the port verifiable rather than a rewrite.

The port lives at `gann-visualizer/backend/study_tool/gann_ladder.py` and must
reproduce, exactly:

- `arm_degree` — ring 3 of the centre cross labels as
  `25→0, 28→45, 31→90, 34→135, 37→180, 40→225, 43→270, 46→315, 49→0`
- `subdivide(25, 28)` → `[25.375, 25.75, 26.125, 26.5, 26.875, 27.25, 27.625, 28]`
- `ring_of` — `1..8→1, 9..24→2, 25..48→3, 49..80→4, 361..440→10`
- `build_ladder` — the straddling segment is subdivided; sub-indices 1–7 only;
  `direction` computed per level against the price; a price sitting exactly on
  a major is itself listed as a major

Any divergence between the two implementations is a bug in the port.

## Instrument scaling and resolution

A price becomes a grid square by multiplying by a per-instrument scale (1 or
10) and rounding. Which scale reads better was previously judged by eye. It is
measurable: the useful resolution is the one where a typical bar's range is
roughly one sub-level.

Measured for RELIANCE (NSE, security ID 2885) on 2026-08-27, against real Dhan
bars:

| Timeframe | Avg bar range | ×1 (sub gap 2.75) | ×10 (sub gap 0.76) |
|---|---|---|---|
| 1 min | 0.78 | 0.28 too fine | **1.02 fits** |
| 5 min | 1.81 | **0.66 fits** | 2.37 too coarse |
| 15 min | 3.21 | **1.17 fits** | 4.22 too coarse |
| 25 min | 4.25 | **1.55 fits** | 5.58 too coarse |
| 60 min | 7.35 | 2.67 too coarse | 9.65 too coarse |

The two scales are therefore not competitors. They are two resolutions of the
same structure: **×10 pairs with 1-minute bars, ×1 pairs with 5–25 minute
bars.** Both are logged, tagged by `timeframe` and a new `price_scale` field,
so Phase 3 can compare them.

A "fits" verdict means the ratio falls in `0.5 ≤ ratio ≤ 2.0`. Outside that
band the logger should warn but still run — the band is a heuristic, and
whether it predicts anything is itself a Phase 3 question.

## The three crosses

Every bar is evaluated against three independent ladders:

| Source | Cross centre | Moves over time |
|---|---|---|
| `center` | square 1, the grid centre | never |
| `sun` | the Sun's degree square | ~1°/day |
| `moon` | the Moon's degree square | ~13°/day, ~1.8h per degree |

Because the Sun and Moon move, **their ladders must be rebuilt as the walk
advances**, not computed once per run. The Moon changes square roughly every
1.8 hours, so on 1-minute bars its levels shift several times per session.

Rebuild rule: recompute a body's ladder when its rounded degree changes.
Recomputing every bar is wasteful; recomputing once per day is wrong.

Ephemeris timing must use the bar's own timestamp converted to UTC. Indian
market bars arrive from Dhan as epoch seconds; IST is UTC+05:30 with no DST.

## Events

### New event types

Added to the existing `EventType` enum. Prefixed `LADDER_` so ladder events and
angular-coverage events remain separable in a shared corpus.

```python
LADDER_TOUCH = "LADDER_TOUCH"                    # bar's range reached a level
LADDER_CROSS = "LADDER_CROSS"                    # price moved through, unconfirmed
LADDER_BREACH_CONFIRMED = "LADDER_BREACH_CONFIRMED"    # N successive closes beyond
LADDER_BREACH_REJECTED = "LADDER_BREACH_REJECTED"      # crossed, failed to confirm
LADDER_RETEST = "LADDER_RETEST"                  # returned to a previously breached level
LADDER_BREACH_RESOLVED = "LADDER_BREACH_RESOLVED"      # terminal outcome assigned
```

### New Event fields

`Event` is a dataclass of optional fields, so these are additive and break no
existing consumer.

```python
# Which level this event concerns
level_source: Optional[str] = None       # 'center' | 'sun' | 'moon'
level_price: Optional[float] = None
level_square: Optional[float] = None     # fractional for sub-levels
level_kind: Optional[str] = None         # 'major' | 'sub'
level_degree: Optional[int] = None       # 0/45/.../315 - the arm
level_ring: Optional[int] = None         # value ring (band between odd squares)
level_sub_index: Optional[int] = None    # 1..7, None for majors
level_is_halfway: Optional[bool] = None
level_segment_start: Optional[float] = None
level_segment_end: Optional[float] = None

# Instrument scaling in use
price_scale: Optional[int] = None        # 1 or 10

# Body position at the time of the event
body_degree: Optional[float] = None      # raw ecliptic longitude
body_square: Optional[int] = None        # the square it mapped to

# Breach linkage - the gap this design exists to close
breach_id: Optional[str] = None          # stable id of a confirmed breach
parent_breach_id: Optional[str] = None   # set on RETEST and RESOLVED events
```

### The breach linkage

The existing `SUPPORT_TEST` / `RESISTANCE_TEST` events carry no reference to an
earlier breach. Verified by reading every field on `Event`: there is no such
link. That makes the central question unanswerable — *of the breaches that
confirmed, how many were retested, and how many held?*

So: every `LADDER_BREACH_CONFIRMED` event is assigned a `breach_id`, and every
subsequent `LADDER_RETEST` and `LADDER_BREACH_RESOLVED` carries it as
`parent_breach_id`. A breach and its retests are then a single joinable group.

`breach_id` format: `{instrument}:{timeframe}:{price_scale}:{source}:{square}:{bar_index}`.
Deterministic, so re-running a walk reproduces identical ids.

### Retest measurement — raw, not classified

The logger records what happened; it does not decide what "held" means. That
threshold is itself something to mine, so committing to one now would bake in
a guess and discard the evidence needed to test alternatives.

Each `LADDER_RETEST` records:

```python
{
  "bars_since_breach": int,       # how long price took to come back
  "retest_extreme": float,        # furthest price reached back toward/through the level
  "depth_in_sublevels": float,    # that distance measured in sub-levels, signed
  "crossed_back": bool,           # did it close back on the pre-breach side
  "closes_beyond": int,           # successive closes on the pre-breach side
}
```

`depth_in_sublevels` is the measurement the ladder makes possible and the angle
fans cannot: with levels an eighth apart, "how far back did it come" is a
number, not a judgement. Negative means it stopped short of the level, zero
means it touched exactly, positive means it went through.

Phase 3 can then apply any threshold it likes after the fact.

### Four-outcome classification

Every confirmed breach eventually gets one `LADDER_BREACH_RESOLVED` event
carrying an `outcome`:

| Outcome | Meaning |
|---|---|
| `NEVER_RETESTED` | price moved away and did not return within the window |
| `RETEST_HELD` | returned, then resumed in the breach direction |
| `RETEST_FAILED` | returned and continued through — a false breakout |
| `NEVER_CONFIRMED` | crossed but never achieved N closes; rejected at the level |

`RETEST_HELD` and `RETEST_FAILED` are assigned from the recorded raw fields
using a **default** threshold, stored alongside the raw data rather than
replacing it. Phase 3 may recompute the outcome under a different threshold at
any time, because every input remains in the record.

Default threshold, to be treated as a starting point and not a finding:
`crossed_back == False` and price subsequently exceeds the breach extreme →
`RETEST_HELD`. `crossed_back == True` with 2+ closes on the pre-breach side →
`RETEST_FAILED`.

Resolution window: 50 bars, matching the existing `mfe_50`/`mae_50` horizon so
the outcome and the forward-return measurement cover the same span. A breach
unresolved at the end of the data is emitted with `outcome = None` rather than
being silently dropped — truncation is a fact about the dataset, not a reason
to discard a sample.

## Module: `gann_ladder_analyzer.py`

Sits beside `breach_analyzer.py` and mirrors its shape: constructed with a
config dict, fed one bar at a time via `process_bar`, holds its own state.

```python
class GannLadderAnalyzer:
    def __init__(self, config: Dict[str, Any]): ...
    def process_bar(self, bar, bar_index, ladders) -> List[Event]: ...
    def get_state(self) -> Dict[str, Any]: ...
    def restore_state(self, state: Dict[str, Any]): ...
```

Config keys, with defaults:

- `breach_mode` — `'close'` (also `'wick'`), matching the existing analyzer
- `confirmation_closes` — `2`
- `touch_tolerance_sublevels` — `0.1`, how near counts as a touch
- `resolution_window_bars` — `50`
- `retest_window_bars` — `50`

`process_bar` is pure with respect to its inputs: same bar plus same state in,
same events out. State is explicit and serialisable so a long walk can be
checkpointed and resumed.

## Testing

Unit tests in `gann-visualizer/backend/study_tool/tests/`:

**Ladder port** (`test_gann_ladder.py`) — the JS suite's expected values reused
verbatim, including the worked example, the ring boundaries, the straddling
segment, sub-indices 1–7 only, and a price landing exactly on a major.

**Analyzer** (`test_gann_ladder_analyzer.py`), on synthetic bars so each case
is unambiguous:

- A touch within tolerance emits `LADDER_TOUCH` and nothing else.
- A cross without the required closes emits `LADDER_CROSS` then
  `LADDER_BREACH_REJECTED`, and resolves `NEVER_CONFIRMED`.
- A cross with N closes emits `LADDER_BREACH_CONFIRMED` with a `breach_id`.
- A return to a breached level emits `LADDER_RETEST` whose `parent_breach_id`
  matches that breach.
- `depth_in_sublevels` is negative when price stops short, ~0 on an exact
  touch, positive when it goes through.
- Price that never returns resolves `NEVER_RETESTED`.
- A retest that resumes in the breach direction resolves `RETEST_HELD`.
- A retest that continues through resolves `RETEST_FAILED`.
- A breach still open at the end of data is emitted with `outcome = None`.
- Sun and Moon ladders are rebuilt when the body's rounded degree changes, and
  not rebuilt when it does not.
- `breach_id` is stable across two identical runs.
- `get_state` / `restore_state` round-trips mid-walk without changing output.

## Out of scope

- **Bar fetching and caching.** Bars are assumed available. Note for whoever
  runs a long walk: Dhan access tokens expire every 24 hours and the data API
  is capped at 100,000 requests/day, so a multi-day run will need either a
  cache or token refresh handling. Deliberately deferred, not overlooked.
- Prediction, scoring, ranking, or position sizing.
- Feature engineering and models — Phase 3.
- US market data. Dhan's Global Stocks API covers orders and a live feed only;
  it exposes no historical bars, confirmed against the DhanHQ-py library's
  function list. A separate US provider is being arranged.
- Bodies beyond Sun and Moon, though `level_source` is a free string so adding
  one later needs no schema change.

## Open questions for Phase 3

Recorded so they are not lost, and deliberately not answered here:

- Which breach definition actually predicts — wick or close, and how many
  closes?
- Do levels from one cross outperform another, and does that vary by regime?
- Does the doubling progression (1st → 2nd → 4th → 8th) appear in the data?
- Do skipped intermediate levels really act as support and resistance later?
- Does the arm angle matter — are 0°/90°/180°/270° stronger than the diagonals?
- Does ring size condition anything, given segment width grows as `8k`?
- Does confluence between two or three crosses at nearby prices matter more
  than any single level?
