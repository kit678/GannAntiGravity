# Status: Gann Phase 3 — Corpus Built, Mining Designed — 2026-09-02

Handoff doc for resuming in a fresh session. Read this first, then the linked
specs if you need depth.

## The project in one paragraph

`GannSq9` / `GannTesting` are not about the chart. The goal is to collect
price-action data around Gann Square-of-9 levels and mine it — statistically
first, then with ML — for a consistently profitable strategy. The trading
theory is the user's own market observation, explicitly **hypothesis, not
established fact**. What counts as a valid breach is itself something to be
mined, never assumed or hard-coded.

## Three phases

| Phase | What | State |
|---|---|---|
| 1. Level engine | Labeled levels from three crosses: centre (fixed at square 1), Sun, Moon | **DONE**, in `C:\Dev\GannSq9` |
| 2. Event logger | Walk bars, record every price/level interaction | **DONE & merged to `main`** |
| 3a. Corpus | Build the event corpus + a 50-strong shadow control, split explore/holdout | **DONE & merged to `main`** |
| 3b. Mining | Measure the corpus against its shadow, per label group | **SPEC WRITTEN, NOT IMPLEMENTED** ← you are here |
| 3c. ML | Models on whatever survives 3b | Not started, not designed |

## Where the work lives

Repo: `C:\Dev\GannTesting`, branch `main`, everything pushed to
`origin/GannAntiGravity`. No open feature branches, no worktrees for this work.

Phase 1 (the JS level engine) lives in the sibling repo `C:\Dev\GannSq9`, on
branch `gann-zoom-moon-levels` — **still unmerged there**, separate decision.

### Documents

- **Phase 3a spec** — `docs/superpowers/specs/2026-09-02-gann-phase3-corpus-design.md`
- **Phase 3a plan** — `docs/superpowers/plans/2026-09-02-gann-phase3-corpus.md` (all 7 tasks complete)
- **Corpus census** — `docs/superpowers/specs/2026-09-02-gann-corpus-census.md` (the real numbers)
- **Phase 3b spec** — `docs/superpowers/specs/2026-09-02-gann-phase3b-mining-design.md` ← **the next thing to build**
- Phase 2 handoff — `docs/superpowers/STATUS-2026-09-01-gann-ladder-event-logger.md` (untracked; sits in a git stash, see Loose ends)

### Code (all on `main`, `gann-visualizer/backend/`)

| File | Job |
|---|---|
| `study_tool/gann_ladder.py` | Pure Square-of-9 spiral/ladder maths, ported from `GannSq9/utils/gannLevels.js` |
| `study_tool/gann_ladder_analyzer.py` | Stateful bar-by-bar: touch → cross → confirm/reject → retest → resolve |
| `study_tool/run_ladder_study.py` | `run_study` / `run_study_chunk`, resumable across day boundaries |
| `study_tool/event_logger.py` | `Event` schema (69 columns) + forward-outcome enrichment |
| `study_tool/ephemeris.py` | Sun/Moon ecliptic longitude for a bar's UTC epoch |
| `study_tool/bar_cache.py` | Fetch bars once from Dhan, cache to Parquet, stamp Sun/Moon |
| `study_tool/shadow_ladder.py` | Derive shifted control ladders — never rebuilds the grid |
| `study_tool/corpus_writer.py` | The corpus tables + the explore/holdout guard |
| `scripts/build_gann_corpus.py` | Entry point that wires it all together |

Test suite: **122 passing** (`pytest tests/study_tool/ tests/test_event_logger_ladder_schema.py tests/test_event_logger_mfe_mae_horizons.py`).

## The corpus that exists right now

`gann-visualizer/backend/logs/corpus/reliance_5m_x1/` — **gitignored, 113 MB,
local only.** Not in git and never should be.

RELIANCE, 2024-09-02 → 2026-09-01, 5-minute bars, price scale ×1, 50 shadows,
seed 7.

- 37,110 bars → **105,807 real events**, 5,220,952 shadow events
- **13,412 breaches with a definite outcome**: 10,006 RETEST_FAILED, 3,406 RETEST_HELD
- Split 75/25 into `explore` / `holdout` slices, by time, never randomly

**Rebuild command** (deterministic — same seed, same corpus, verified by having
rebuilt it once already):

```bash
cd gann-visualizer/backend && python scripts/build_gann_corpus.py \
  --symbol RELIANCE --from 2024-09-02 --to 2026-09-01 \
  --interval 5 --scale 1 --shadows 50 \
  --out logs/corpus/reliance_5m_x1
```

Takes ~40 minutes. **Requires a live Dhan token** — they expire every 24 hours.
Check before running:

```bash
cd gann-visualizer/backend && python -c "
import os, base64, json, time
from dotenv import load_dotenv
load_dotenv('.env', override=True)
t = os.environ.get('DHAN_ACCESS_TOKEN','').split('.')
c = json.loads(base64.urlsafe_b64decode(t[1] + '='*(-len(t[1])%4)))
print('hours left:', round((c.get('exp',0)-time.time())/3600, 1))"
```

If negative, paste a fresh token into `gann-visualizer/backend/.env`.

## The core discipline — do not erode this

The RSI trendline strategy in this repo looked profitable until
`scripts/placebo_test_rsi.py` compared it against a control. It landed inside
the control spread and two shifted variants beat it outright. That is the
standard everything here is held to.

**Two independent checks, answering different questions:**

| Check | Question it answers |
|---|---|
| **Shadow** (50 shifted ladders) | Would this appear if the levels carried no information? |
| **Holdout** (final 25% by time) | Does this survive on data the search never saw? |

**Exploration is unlimited.** An earlier draft of the corpus spec demanded
hypotheses be declared in advance; that was **withdrawn** as wrong — discovering
hypotheses nobody thought of is the point of mining. Search anything.

What is protected is the step *after* searching. The holdout is **consumable**:
each look followed by a tweak turns it into training data. Spend it in batches,
against a shortlist, and record the result whichever way it falls.

`corpus_writer.load_events()` defaults to the explore slice and requires an
explicit `slice_name="holdout"`. Reaching the holdout should be a deliberate act
visible in review.

## What Phase 3b builds (the next task)

Full detail in the 3b spec. Summary:

**One reusable comparison** — `compare(events, statistic_fn)` runs any statistic
on the real events and on all 50 shadows, and reports where real sits in the
shadow spread. Build once; every future question inherits the control instead of
depending on someone remembering it.

**Five statistics:** hold rate, rejection rate, reach-next-level rate (the
headline hypothesis), mean retest depth, and touch density (a *fairness check* —
if real and shadow get touched at very different rates, every other comparison
is suspect; read it first).

**Reported per label group, never pooled** — by cross (centre/Sun/Moon), arm
(0–315°), sub-index (1–7), halfway or not, ring, major vs sub. Pooling washes out
an effect that lives in one group.

**Output is a shortlist of candidates, not findings.**

### Two gaps the 3b spec found, which must be fixed as part of it

1. **The corpus records no build metadata.** Shadow offsets are *not*
   recoverable from the events — this was tested, and the natural join key
   yields 178–182 conflicting deltas per shadow. Without the offsets, a shadow's
   next-level target is wrong. Fix: `meta.json` in the corpus, plus a backfill
   script so the existing 113 MB corpus doesn't need a 40-minute rebuild.
2. **Boundary leak.** Events within 50 bars of the explore/holdout boundary have
   forward-looking outcomes determined by holdout bars — 0.1% of events, but it
   is a leak in the one mechanism protecting every later conclusion. Fix: drop
   that buffer and report the count.

### Recorded so it is not re-proposed

A second "scrambled gaps" control was proposed and **withdrawn**. Random gaps
make *reach the next level* measure the random gap width rather than the theory,
and clumped levels get touched at a different rate, so the control stops being a
fair twin. The shifted shadow, read per label group, already covers the
structural questions — because shadows keep every label while moving every
price, so a level still labelled "halfway" sits at an ordinary price.

The shadow genuinely **cannot** test whether eighths are the right division;
every ladder uses them. That needs a differently-built corpus. Out of scope.

## Bugs found and fixed — context, no action needed

- **Sub-level gap measured in grid squares, not price** (`fcb8e5a`). At scale
  ×10 the touch tolerance came out 10× too wide — wider than the gap between
  levels, so every bar would have registered a touch. **The ×10 / 1-minute
  corpus must not be built from any commit before `fcb8e5a`.** The existing ×1
  corpus is post-fix and unaffected. Invisible until then because every test ran
  at scale 1, where squares and prices are the same number.
- **Forward returns discarded at 3 of 4 horizons** (`86dc9ac`). `exc_up_10` /
  `exc_down_10` already existed and worked; horizons 5, 20 and 50 threw theirs
  away with `_, _`.
- **Chunked walks lost celestial degrees** (Phase 2). A breach opened on an
  earlier day and resolved later came back with `body_degree = None`, because
  the resolving chunk never had that day's degrees. Now carried in state,
  bounded to bars still open.
- **`write_corpus` clobbered silently** — now takes `overwrite: bool = False`
  and raises `FileExistsError`. `build_gann_corpus.py` exposes `--overwrite`.
- **Bar cache wrote non-atomically** — now temp-file + `os.replace`.

## Loose ends

- **Four git stashes** in `GannTesting` holding 100+ unrelated files — logs,
  scratch scripts, other features' WIP, and the Phase 2 STATUS doc. Nothing
  lost, needs manual sorting:
  ```
  stash@{0} test-run log noise before worktree creation
  stash@{1} test-run log noise before main merge
  stash@{2} pre-merge cleanup: unrelated WIP, logs, scratch scripts
  stash@{3} pre-merge: untracked files superseded by feat/rsi-geometry-redesign
  ```
- **6 pre-existing test failures + 10 collection errors** in the wider backend
  suite, unrelated to any Gann work: `test_angle_zone_tracker`,
  `test_intersection`, `test_pivot_stacks`, a stale `AngleSetup` import, and two
  files whose source sits in stash@{2}. Present on `main` before and after all
  this work.
- **`GannSq9` branch `gann-zoom-moon-levels`** — Phase 1 UI work, still unmerged
  in that repo. Independent decision.
- **`.gitignore` quirk:** `**/tests/` is blanket-excluded. New test files need
  `git add -f` or they silently go untracked. This has bitten this work before.

## Open questions for 3b

- Is 50 shadows enough? A percentile lands on a 2% grid; cheap to raise to 200.
- Does the 50-bar window suit a target/stop race, given it was chosen for breach
  resolution?
- Do majors and sub-levels need separating everywhere, or only where the report
  shows they differ?

## How to resume

Point a fresh session at this file. The immediate next step is **writing the
implementation plan for Phase 3b** from its spec, then executing it with
subagent-driven development, the same way Phase 3a was built.
