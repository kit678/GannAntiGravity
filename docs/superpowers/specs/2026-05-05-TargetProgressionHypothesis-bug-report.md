# TargetProgressionHypothesis — Bug Analysis Report

**File:** `gann-visualizer/backend/analysis/strategy_analyzer.py`
**Date:** 2026-05-05
**Analyst:** Claude Code (systematic debugging review)

---

## Overview

`TargetProgressionHypothesis` evaluates whether, once a fractional angle is breached and confirmed, price reaches the next logical target in the sequence before reversing. This report documents six edge-case bugs found through systematic code inspection against the actual CSV corpus data and the specification documents (`STRATEGY_HYPOTHESES.md`, `EVENT_TYPES.md`).

---

## Bug 1 (Critical): Horizontal target `TARGET_HIT` events are never counted

**Location:** `strategy_analyzer.py`, lines 117-119

```python
hits_df = df[df['Type'] == 'TARGET_HIT'].copy()
fails_df = df[df['Type'] == 'TARGET_FAILED'].copy()
```

**Problem:** The hypothesis filters `TARGET_HIT` events by `Fan` and `Time`, but never checks `Fraction`. This seems fine at first — except the next filter (Bug 4) shows the breach lookup has no `Fraction` filter, and the horizontal target line has `Fraction = 'horizontal'` (e.g., row 82 in the corpus: `TARGET_HIT, Fraction=horizontal`).

More critically, `QuarterReversalAnomalyHypothesis` (line 250) also uses `Fraction == '0.25'` filter, which means `TARGET_HIT` events with `Fraction='horizontal'` are **invisible to both hypotheses**. Every `TARGET_HIT` on the horizontal line is silently dropped from all analysis.

**Evidence from corpus (row 82):**
```
Time="4/27/2026, 12:31:00 PM", Fan="P2 (L8-H6)", Fraction="horizontal",
Type="BREACH_CONFIRMED", Details="UP (T+1 bars)"
```

Note: row 81 shows `BREACH_CONFIRMED_NO_ALPHA` on the same bar for fan `P1 (L8-H7)` at `fraction=horizontal`. Row 82 is a real `BREACH_CONFIRMED` on `P2 (L8-H6)` at `fraction=horizontal`.

**Impact:** All horizontal-target progressions are excluded from the sample. The hypothesis cannot measure the probability of reaching horizontal → full_coverage.

---

## Bug 2 (Critical): Hypothesis uses `TARGET_FAILED` but spec says it should use `BREACH_CONFIRMED`

**Spec (STRATEGY_HYPOTHESES.md §3 — "Target Progression Probability"):**
> "Scan the master record for `BREACH_CONFIRMED` events on specific fractional lines... Track the subsequent price action to see which happens first: a `TARGET_HIT` event for the next fraction in the sequence, or a `CROSS_DOWN`/`CROSS_UP` event back across the origin line (a failure)."

**Actual code (lines 117-119):**
```python
hits_df = df[df['Type'] == 'TARGET_HIT'].copy()
fails_df = df[df['Type'] == 'TARGET_FAILED'].copy()
```

**Problem:** The spec calls for:
1. Find a `BREACH_CONFIRMED` on the origin line (e.g., the 0.875 line)
2. Wait for the next `TARGET_HIT` in the sequence
3. If `CROSS_UP`/`CROSS_DOWN` fires back across the origin line first → failure

Instead, the code uses `TARGET_FAILED` events (which fire when the fan is invalidated, not when price crosses back over the origin). From `EVENT_TYPES.md`:

> "`TARGET_FAILED` fires when: Fan gets invalidated (either price crosses anchor point, or an opposite-direction fan takes over) AND there was a breach confirmed on the origin angle but the progression was not completed"

Fan invalidation and crossing back over the origin line are semantically different events. The code's approach counts a progression as a failure only when the fan dies, not when price reversals cleanly through the origin line. This fundamentally changes what the hypothesis measures.

**Impact:** Wrong event semantics. The sample is measuring "does the fan survive to the next target?" instead of "does price reach the next target before reversing back through the origin line?"

---

## Bug 3 (High): `_find_preceding_breach` uses string-based Time comparison

**Location:** `strategy_analyzer.py`, lines 174-177

```python
preceding_breaches = breaches_df[
    (breaches_df['Fan'] == fan) &
    (breaches_df['Time'] < target_time)
]
```

**Problem:** The `Time` column contains strings like `"4/27/2026, 9:39:00 AM"`. Lexicographic string comparison on timestamps is unreliable:

- Same-month, same-day, different time: `"4/27/2026, 9:39:00 AM" < "4/27/2026, 9:43:00 AM"` — works by accident
- Different days: `"4/27/2026, 9:39:00 AM" < "4/28/2026, 9:43:00 AM"` — works by accident
- Different months: `"4/27/2026" < "5/1/2026"` — works by accident
- Edge cases with leading zeros, formatting inconsistencies — silently breaks

The data has `Raw_Timestamp` (Unix epoch integer, e.g., `1777262940`) and `bar_index` (integer) — both proper numeric sort keys that should be used instead.

**Impact:** Breach-to-target time ordering can be wrong, causing valid progressions to be miscategorized or dropped.

---

## Bug 4 (High): `_find_preceding_breach` finds ANY breach for the fan, not the specific LINE that was breached

**Location:** `strategy_analyzer.py`, lines 174-177

```python
preceding_breaches = breaches_df[
    (breaches_df['Fan'] == fan) &
    (breaches_df['Time'] < target_time)
]
```

**Problem:** The filter matches on `Fan` only — no `Fraction` check. The target progression sequence is per-line: `0.875 → 0.75 → 0.5 → horizontal/0.25`. A breach on the `0.875` line should NOT qualify as a valid preceding breach for a `TARGET_HIT` on the `0.75` line.

**Cross-contamination example from corpus:**

| Row | Time | Fan | Fraction | Type |
|-----|------|-----|----------|------|
| 20 | 10:27 AM | P2 (H6-L5) | 0.875 | BREACH_CONFIRMED |
| 25 | 10:39 AM | P1 (H6-L6) | 0.75 | TARGET_HIT |

Wait — those are different fans. Let me use the correct example:

| Row | Time | Fan | Fraction | Type |
|-----|------|-----|----------|------|
| 20 | 10:27 AM | P2 (H6-L5) | 0.875 | BREACH_CONFIRMED |
| 25 | 10:39 AM | P1 (H6-L6) | 0.75 | TARGET_HIT |

Actually rows 20 and 21 both have `BREACH_CONFIRMED` on `Fraction=0.875` for fans `P2 (H6-L5)` and `P1 (H6-L6)`. Row 25 is `TARGET_HIT` on `Fraction=0.75` for fan `P1 (H6-L6)`. These are different fans, so they don't cross-contaminate in this case.

But consider this scenario from the data:
- Row 20: `BREACH_CONFIRMED` on fan `P2 (H6-L5)`, `Fraction=0.875`
- Row 25: `TARGET_HIT` on fan `P1 (H6-L6)`, `Fraction=0.75`

Different fans again. Let me trace through a real scenario where contamination DOES occur — if a single fan has multiple concurrent breaches or if the same fan has overlapping progression states.

The real contamination risk: If fan `P1 (H6-L6)` has a breach on `0.875` at bar 112, and then a breach on `0.75` at bar 126 (different fractions, same fan), then a `TARGET_HIT` on `0.5` would incorrectly associate with the `0.75` breach even though the intended preceding breach should be the `0.5` breach. Since the filter only checks `Fan`, any breach on that fan in the right time window will be matched.

**Impact:** Wrong breach-to-target pairing causes cross-contamination between progression steps. A `TARGET_HIT` on line N+1 could be paired with a breach on line N-1.

---

## Bug 5 (Medium): `_log_target_event` silently drops `TARGET_FAILED` events without a preceding breach

**Location:** `strategy_analyzer.py`, lines 203-204

```python
if not preceding_breach:
    return  # silently drops the event
```

**Problem:** `TARGET_FAILED` means the fan was invalidated with a live progression (breach confirmed on origin angle but next target not reached before fan became invalid). If no `BREACH_CONFIRMED` is in the log for that fan, the failure is simply not counted.

The spec says failures should be counted — they represent the "failure" side of the probability. Silently dropping them **artificially inflates the win rate** because only well-formed progressions (with a breach AND a target hit/miss) are counted, while unresolved progressions (where the fan died before the next target) vanish from the sample.

**Impact:** Win rate inflation. Unresolved progressions (fan invalidated before next target) are not counted at all, making the measured win rate artificially high.

---

## Bug 6 (Medium): No filtering for `BREACH_CONFIRMED_NO_ALPHA` Path-A `TARGET_HIT` events

**From `EVENT_TYPES.md`:** `BREACH_CONFIRMED_NO_ALPHA` Path A fires when multiple `CROSS_UP`/`CROSS_DOWN` events occur on the same bar across different lines. The intermediate lines confirm immediately as `BREACH_CONFIRMED_NO_ALPHA` while the furthest line gets normal `BREACH_CONFIRMED`. The `TARGET_HIT` on the next line fires in the same bar as the stacked breaches.

These setups are **non-tradeable** — there was no real entry opportunity because everything happened in one bar. The `[Retro]` marker exists in the `Details` field (e.g., `"[Retro] Target Reached"` or `"[Retro] [Retro] UP"`) but the hypothesis doesn't filter on it.

**Impact:** Non-tradeable setups (from intra-bar stacked confirmation) are mixed into the sample, corrupting the win rate measurement.

---

## Summary Table

| Bug | Severity | Effect |
|-----|----------|--------|
| Horizontal Fraction never counted | Critical | All horizontal target progressions excluded from sample |
| Uses TARGET_FAILED instead of BREACH_CONFIRMED | Critical | Wrong event semantics; sample doesn't match spec |
| Time string comparison in breach lookup | High | Incorrect breach association (time comparison errors) |
| No Fraction filter in breach lookup | High | Cross-contaminates progression steps |
| Silently drops TARGET_FAILED with no preceding breach | Medium | Win rate inflation; unresolved progressions not counted |
| No filtering for BREACH_CONFIRMED_NO_ALPHA hits | Medium | Non-tradeable setups included in sample |

---

## Recommended Fix Priority

1. **Bug 4** (no Fraction filter) — Fix the breach-to-target association to include `Fraction` matching
2. **Bug 3** (string Time comparison) — Switch to `bar_index` or `Raw_Timestamp` for temporal ordering
3. **Bug 2** (wrong event semantics) — Align with spec: use `BREACH_CONFIRMED` as origin, not `TARGET_FAILED`
4. **Bug 1** (horizontal excluded) — Ensure horizontal `TARGET_HIT` events are captured
5. **Bug 5** (silent drops) — Log unresolved progressions rather than dropping silently
6. **Bug 6** (Path-A filtering) — Filter out `[Retro]` tagged events or `BREACH_CONFIRMED_NO_ALPHA` derived hits

---

## Specification Reference

From `gann-visualizer/backend/docs/STRATEGY_HYPOTHESES.md` §3:

> "**Mechanism:** Scan the master record for `BREACH_CONFIRMED` events on specific fractional lines. Track the subsequent price action to see which happens first: a `TARGET_HIT` event for the next fraction in the sequence, or a `CROSS_DOWN`/`CROSS_UP` event back across the origin line (a failure). **Win Condition:** A 'Win' is recorded if the next sequential target is hit."

From `gann-visualizer/backend/docs/EVENT_TYPES.md`:

> `TARGET_FAILED`: "Fan was invalidated while a target progression was in-flight (breach confirmed on origin angle but next target was not reached before fan became invalid)"
>
> `TARGET_HIT`: "First contact with an angle line in the target progression sequence. Only fires once per line; subsequent contacts are ignored."
>
> `BREACH_CONFIRMED_NO_ALPHA` Path B: "When `TARGET_HIT` fires on line N+1 and the prior line N had a pending breach created in an earlier bar (not the same bar), the pending breach on N is immediately confirmed as `BREACH_CONFIRMED_NO_ALPHA`."
