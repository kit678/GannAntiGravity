"""The causal RSI trendline sweep.

This module owns ALL mutable geometry state and contains the only bar loop in
the system.  It answers exactly one question: what line was a trader looking
at, at bar N?

Invariants, asserted by test_rsi_sweep.py:
  * at most one active line per direction at any bar
  * a segment is never valid before its newest anchor confirms
  * no same-kind pivot pokes through its own segment
  * a broken line never fires twice
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace

import pandas as pd

from analysis.rsi_line_policy import (
    AnchorPolicy,
    RSILine,
    count_touches,
    line_between,
)
from analysis.rsi_pivots import (
    GeometryParams,
    RSIPivot,
    apply_dominance,
    detect_fractal_candidates,
)


@dataclass(frozen=True)
class LineSegment:
    segment_id: int
    line: RSILine
    anchor_a: RSIPivot
    anchor_b: RSIPivot
    valid_from_bar: int
    valid_to_bar: int | None
    end_reason: str | None  # "broken" | "re_anchored" | "end_of_data"
    touch_count: int


@dataclass(frozen=True)
class BreakSignal:
    bar_index: int
    side: str  # "LONG" | "SHORT"
    segment_id: int
    line_value_at_break: float
    rsi_value: float


@dataclass(frozen=True)
class SweepResult:
    pivots: list[RSIPivot]
    segments: list[LineSegment]
    signals: list[BreakSignal]


_SIDE_FOR_DIRECTION = {"down": "LONG", "up": "SHORT"}


def run_causal_sweep(
    rsi: pd.Series, policy: AnchorPolicy, params: GeometryParams
) -> SweepResult:
    values = rsi.astype(float).reset_index(drop=True)
    bar_count = len(values)

    candidates_at: dict[int, list[RSIPivot]] = defaultdict(list)
    for candidate in detect_fractal_candidates(values, params.left_bars, params.right_bars):
        candidates_at[candidate.confirmation_bar_index].append(candidate)

    pivots: list[RSIPivot] = []
    active: dict[str, LineSegment | None] = {"down": None, "up": None}
    segments: list[LineSegment] = []
    signals: list[BreakSignal] = []
    next_segment_id = 1

    for bar in range(bar_count):
        # 1. fold in every pivot that CONFIRMS on this bar
        changed_kinds: list[str] = []
        for candidate in candidates_at.get(bar, []):
            pivots, changed_kind = apply_dominance(pivots, candidate, params.min_swing)
            if changed_kind is not None and changed_kind not in changed_kinds:
                changed_kinds.append(changed_kind)

        # 2. re-anchor the affected directions
        for kind in changed_kinds:
            direction = "down" if kind == "high" else "up"
            same_kind = [p for p in pivots if p.kind == kind]
            newest = same_kind[-1]

            anchor = policy.anchor(same_kind, newest, params)
            if anchor is None:
                continue

            open_segment = active[direction]
            if open_segment is not None:
                # Half-open handoff: the successor owns `bar`, so the outgoing
                # segment ends at bar - 1.  Closing it at `bar` would leave TWO
                # live lines in one direction at every handoff -- precisely the
                # duplicate-line defect this redesign exists to remove.
                # A `broken` segment, by contrast, DOES include its break bar:
                # the line was genuinely live at the moment it broke.
                retired = replace(
                    open_segment, valid_to_bar=bar - 1, end_reason="re_anchored"
                )
                if retired.valid_to_bar >= retired.valid_from_bar:
                    segments.append(retired)

            line = line_between(anchor, newest)
            active[direction] = LineSegment(
                segment_id=next_segment_id,
                line=line,
                anchor_a=anchor,
                anchor_b=newest,
                valid_from_bar=bar,
                valid_to_bar=None,
                end_reason=None,
                touch_count=count_touches(line, same_kind, params.tolerance),
            )
            next_segment_id += 1

        # 3. test the active lines for a break
        for direction in ("down", "up"):
            segment = active[direction]
            if segment is None or bar <= segment.valid_from_bar:
                continue

            line = segment.line
            previous_line = line.value_at(bar - 1)
            current_line = line.value_at(bar)
            previous_rsi = float(values.iloc[bar - 1])
            current_rsi = float(values.iloc[bar])

            if direction == "down":
                crossed = previous_rsi <= previous_line and current_rsi > current_line
            else:
                crossed = previous_rsi >= previous_line and current_rsi < current_line

            if not crossed:
                continue

            segments.append(replace(segment, valid_to_bar=bar, end_reason="broken"))
            signals.append(
                BreakSignal(
                    bar_index=bar,
                    side=_SIDE_FOR_DIRECTION[direction],
                    segment_id=segment.segment_id,
                    line_value_at_break=float(current_line),
                    rsi_value=current_rsi,
                )
            )
            active[direction] = None

    # 4. close whatever is still open when the data runs out
    last_bar = bar_count - 1
    for segment in active.values():
        if segment is not None:
            segments.append(
                replace(segment, valid_to_bar=last_bar, end_reason="end_of_data")
            )

    segments.sort(key=lambda segment: segment.segment_id)
    return SweepResult(pivots=pivots, segments=segments, signals=signals)
