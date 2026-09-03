# Gann Corpus Census — RELIANCE, 5-min, ×1 scale

Date: 2026-09-02
Corpus: `logs/corpus/reliance_5m_x1` (not tracked in git — Parquet, local only)
Built by: `scripts/build_gann_corpus.py` at commit `3b9e45b` (branch `feat/gann-phase3-corpus`)

## Build parameters

```
--symbol RELIANCE --from 2024-09-02 --to 2026-09-01
--interval 5 --scale 1 --shadows 50 --seed 7
```

## Pilot (1 month, 5 shadows) — 2026-08-01..2026-08-31

- 1,587 bars
- 3,721 real events, 18,024 shadow events
- Slices: explore 16,308 / holdout 5,437 (75.0% / 25.0%)
- `level_degree` nulls: 0 / 3,721
- `exc_up_5` nulls: 30 / 3,721 (tail-of-data, expected)
- Sources: moon 1,630 / sun 1,191 / center 900

Real events by type:

| Event | Count |
|---|---|
| LADDER_TOUCH | 1,112 |
| LADDER_CROSS | 722 |
| LADDER_BREACH_RESOLVED | 722 |
| LADDER_BREACH_CONFIRMED | 510 |
| LADDER_RETEST | 471 |
| LADDER_BREACH_REJECTED | 184 |

Breach outcomes: RETEST_FAILED 319, NEVER_CONFIRMED 184, RETEST_HELD 128,
None (truncated) 53, NEVER_RETESTED 38.

## Full build (2 years, 50 shadows) — 2024-09-02..2026-09-01

- 37,110 bars
- **105,807 real events**, 5,220,952 shadow events
- Slices: explore 3,995,069 / holdout 1,331,690 (75.0% / 25.0%, all rows incl. shadows)
- `level_degree` nulls: 0 / 105,807
- `exc_up_5` nulls: 17 / 105,807 (0.02%, tail-of-data, expected)
- Sources: moon 46,501 / sun 31,796 / center 27,510

Real events by type:

| Event | Count |
|---|---|
| LADDER_TOUCH | 29,963 |
| LADDER_CROSS | 20,964 |
| LADDER_BREACH_RESOLVED | 20,964 |
| LADDER_BREACH_CONFIRMED | 14,803 |
| LADDER_RETEST | 13,425 |
| LADDER_BREACH_REJECTED | 5,688 |

Breach outcomes:

| Outcome | Count |
|---|---|
| RETEST_FAILED | 10,006 |
| NEVER_CONFIRMED | 5,688 |
| RETEST_HELD | 3,406 |
| NEVER_RETESTED | 1,378 |
| None (truncated) | 486 |

## Reading

**13,412 breaches resolved to a definite held/failed outcome** (RETEST_HELD +
RETEST_FAILED). That is ample statistical power for the shadow-comparison and
holdout-confirmation machinery designed in the corpus spec — no need to widen
to more instruments or a longer window before starting Phase 3b.

RETEST_FAILED outdoes RETEST_HELD roughly 3:1 in the raw counts. This is
descriptive only — it says nothing yet about real levels versus the shadow
controls, which is the actual test Phase 3b runs. Do not read a directional
conclusion into this ratio on its own.
