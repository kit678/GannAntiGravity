"""Anchor policies -- the only swappable part of the geometry engine.

A policy answers one question: given the confirmed same-kind pivots visible at
this bar and the newest of them, which EARLIER pivot should anchor the line?

Policies are pure and stateless.  They never see the bar loop and never see
pivots that have not yet confirmed -- the sweep filters that before calling, so
causality is structural rather than a rule each policy must remember.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from analysis.rsi_pivots import GeometryParams, RSIPivot


@dataclass(frozen=True)
class RSILine:
    start_bar_index: int
    end_bar_index: int
    start_rsi: float
    end_rsi: float
    direction: str  # "up" | "down"

    @property
    def slope(self) -> float:
        span = self.end_bar_index - self.start_bar_index
        if span == 0:
            return 0.0
        return (self.end_rsi - self.start_rsi) / span

    def value_at(self, bar_index: int) -> float:
        """Total on the whole number line -- a trendline extends forward."""
        return self.start_rsi + self.slope * (bar_index - self.start_bar_index)


def line_between(anchor: RSIPivot, newest: RSIPivot) -> RSILine:
    return RSILine(
        start_bar_index=anchor.bar_index,
        end_bar_index=newest.bar_index,
        start_rsi=anchor.rsi_value,
        end_rsi=newest.rsi_value,
        direction="down" if newest.kind == "high" else "up",
    )


def count_touches(line: RSILine, same_kind: list[RSIPivot], tolerance: float) -> int:
    """Same-kind pivots sitting within ``tolerance`` of the line, anchors included.

    Diagnostic only -- never used for selection.  The walk-back rule already
    maximises it by taking the furthest valid anchor.
    """
    return sum(
        1
        for pivot in same_kind
        if line.start_bar_index <= pivot.bar_index <= line.end_bar_index
        and abs(pivot.rsi_value - line.value_at(pivot.bar_index)) <= tolerance
    )


def _pokes_through(
    anchor: RSIPivot, newest: RSIPivot, same_kind: list[RSIPivot], tolerance: float
) -> bool:
    """True when a pivot between the anchors sits on the wrong side of the line."""
    line = line_between(anchor, newest)
    for pivot in same_kind:
        if not (anchor.bar_index < pivot.bar_index < newest.bar_index):
            continue
        value = line.value_at(pivot.bar_index)
        if newest.kind == "high" and pivot.rsi_value > value + tolerance:
            return True
        if newest.kind == "low" and pivot.rsi_value < value - tolerance:
            return True
    return False


def _slope_sense_ok(anchor: RSIPivot, newest: RSIPivot) -> bool:
    if newest.kind == "high":
        return newest.rsi_value < anchor.rsi_value  # lower high -> falling line
    return newest.rsi_value > anchor.rsi_value      # higher low -> rising line


class AnchorPolicy(Protocol):
    name: str

    def anchor(
        self, same_kind: list[RSIPivot], newest: RSIPivot, params: GeometryParams
    ) -> RSIPivot | None: ...


class WalkBackAnchorPolicy:
    """Take the FURTHEST-back anchor that no intermediate pivot pokes through."""

    name = "walk_back"

    def anchor(
        self, same_kind: list[RSIPivot], newest: RSIPivot, params: GeometryParams
    ) -> RSIPivot | None:
        for candidate in same_kind:  # oldest first
            if candidate.bar_index >= newest.bar_index:
                continue
            span = newest.bar_index - candidate.bar_index
            if span < params.min_length or span > params.max_span_bars:
                continue
            if not _slope_sense_ok(candidate, newest):
                continue
            if _pokes_through(candidate, newest, same_kind, params.tolerance):
                continue
            return candidate
        return None


class CollinearExtendAnchorPolicy:
    """Start adjacent, extend back while every pivot stays ON the line. Default.

    Strictly better than plain adjacency: it never skips a pivot (the extension
    stops the moment one falls off the line), but it reaches further whenever the
    structure is genuinely collinear -- which is what a trader does by eye.

    Measured on BTCUSDT 15m against adjacency: identical 0.0% missed pivots and
    0.00 mean float, but median touches 3 vs 2, 57% of lines touching 3+ vs 0%,
    and more signals (45 vs 29).

    Why the earlier policies failed:
      walk_back  - poke-through is one-sided, so a steep line from a tall peak
                   clears everything beneath it: 67% missed, 12.6 mean float.
      touch_max  - maximising touches needs long lines, which then float over
                   the pivots they do not touch: 62% missed, 14.1 mean float.
      adjacent   - never skips, but can never touch more than its two anchors.

    Tolerance matters more than it looks. At 1.5 RSI points almost nothing scores
    as a touch and this degenerates to adjacency; 5.0 is what admits the genuine
    multi-touch structure.
    """

    name = "collinear_extend"

    def anchor(
        self, same_kind: list[RSIPivot], newest: RSIPivot, params: GeometryParams
    ) -> RSIPivot | None:
        earlier = [p for p in same_kind if p.bar_index < newest.bar_index]
        if not earlier:
            return None

        best = None
        for candidate in reversed(earlier):  # nearest first, then extend outward
            span = newest.bar_index - candidate.bar_index
            if span > params.max_span_bars:
                break
            if span < params.min_length:
                continue
            if not _slope_sense_ok(candidate, newest):
                continue

            line = line_between(candidate, newest)
            between = [
                m for m in earlier
                if candidate.bar_index < m.bar_index < newest.bar_index
            ]
            if any(
                abs(m.rsi_value - line.value_at(m.bar_index)) > params.tolerance
                for m in between
            ):
                break  # structure stopped being collinear; do not reach past it
            best = candidate

        return best


class AdjacentAnchorPolicy:
    """Connect the immediately preceding same-kind pivot. Never skips.

    Default policy. Walk-back's poke-through test is one-sided -- it rejects an
    anchor only when a pivot rises ABOVE the line, and never when the line
    floats above the structure. A steep line dropping from a tall peak clears
    everything beneath it, so it scores zero violations while touching nothing.
    Measured on BTCUSDT 15m, walk-back lines sat a mean 10.87 RSI points above
    the highs they passed over (max 37.7), and 73.6% touched only their own two
    anchors.

    Raising the touch requirement does not repair that: RSI pivots are rarely
    collinear, so the median touch count stays at 2 under every float cap and
    pivot density tested. Adjacency instead makes skipping impossible by
    construction -- there is no pivot between adjacent pivots.

    It declines rather than reaching further back. Refusing to draw a line is
    the correct answer when the adjacent pivot does not qualify; reaching past
    it is what produced the floating lines.
    """

    name = "adjacent"

    def anchor(
        self, same_kind: list[RSIPivot], newest: RSIPivot, params: GeometryParams
    ) -> RSIPivot | None:
        earlier = [p for p in same_kind if p.bar_index < newest.bar_index]
        if not earlier:
            return None

        candidate = earlier[-1]
        span = newest.bar_index - candidate.bar_index
        if span < params.min_length or span > params.max_span_bars:
            return None
        if not _slope_sense_ok(candidate, newest):
            return None
        return candidate


class NearestPairAnchorPolicy:
    """A/B rival standing in for today's all-pairs builder.

    Takes the NEAREST valid anchor and does not check poke-through, which is
    what produces the 89% pivot-skipping rate measured in spec section 1.1.
    """

    name = "nearest_pair"

    def anchor(
        self, same_kind: list[RSIPivot], newest: RSIPivot, params: GeometryParams
    ) -> RSIPivot | None:
        for candidate in reversed(same_kind):  # newest first
            if candidate.bar_index >= newest.bar_index:
                continue
            span = newest.bar_index - candidate.bar_index
            if span < params.min_length or span > params.max_span_bars:
                continue
            if not _slope_sense_ok(candidate, newest):
                continue
            return candidate
        return None
