from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class RSIPivot:
    bar_index: int
    rsi_value: float
    kind: str
    confirmation_bar_index: int | None = None

    def __post_init__(self) -> None:
        if self.confirmation_bar_index is None:
            object.__setattr__(self, "confirmation_bar_index", self.bar_index)


@dataclass(frozen=True)
class RSILine:
    start_bar_index: int
    end_bar_index: int
    start_rsi: float
    end_rsi: float
    direction: str
    end_confirmation_bar_index: int | None = None
    score: float = 0.0

    def __post_init__(self) -> None:
        if self.end_confirmation_bar_index is None:
            object.__setattr__(self, "end_confirmation_bar_index", self.end_bar_index)

    def value_at(self, bar_index: int) -> float | None:
        if bar_index < self.start_bar_index:
            return None
        if bar_index == self.start_bar_index:
            return self.start_rsi
        if self.end_bar_index == self.start_bar_index:
            return self.end_rsi

        slope = (self.end_rsi - self.start_rsi) / (self.end_bar_index - self.start_bar_index)
        return self.start_rsi + slope * (bar_index - self.start_bar_index)


@dataclass(frozen=True)
class RSIBreakSignal:
    bar_index: int
    direction: str
    line: RSILine
    line_value_at_break: float
    rsi_value: float
    rsi_window: list[dict]


def compute_rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    close = close.astype(float)
    rsi = pd.Series(50.0, index=close.index, dtype=float)
    if len(close) <= period:
        return rsi

    delta = close.diff().fillna(0.0)
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = float(gain.iloc[1 : period + 1].mean())
    avg_loss = float(loss.iloc[1 : period + 1].mean())

    def to_rsi(current_avg_gain: float, current_avg_loss: float) -> float:
        if current_avg_loss == 0.0:
            return 100.0
        rs = current_avg_gain / current_avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    rsi.iloc[period] = to_rsi(avg_gain, avg_loss)

    for idx in range(period + 1, len(close)):
        avg_gain = ((avg_gain * (period - 1)) + float(gain.iloc[idx])) / period
        avg_loss = ((avg_loss * (period - 1)) + float(loss.iloc[idx])) / period
        rsi.iloc[idx] = to_rsi(avg_gain, avg_loss)

    return rsi


def detect_rsi_pivots(
    rsi: pd.Series, left_bars: int, right_bars: int, min_swing: float = 0.0
) -> list[RSIPivot]:
    """Detect local RSI pivots.

    Parameters
    ----------
    min_swing : float
        Minimum RSI point move from the last *opposite-kind* pivot before a
        new pivot is registered.  e.g. 5.0 means a high pivot is only kept if
        the RSI has risen at least 5 points since the last confirmed low.
        Set to 0 to disable.
    """
    pivots: list[RSIPivot] = []
    values = rsi.astype(float)
    last_opposite: tuple[int, float, str] | None = None  # (bar, rsi, kind) of last confirmed pivot

    for idx in range(left_bars, len(values) - right_bars):
        center = values.iloc[idx]
        if pd.isna(center):
            continue

        left = values.iloc[idx - left_bars : idx]
        right = values.iloc[idx + 1 : idx + 1 + right_bars]
        neighbors = pd.concat([left, right])
        if neighbors.isna().any():
            continue

        if (center > neighbors).all():
            kind = "high"
        elif (center < neighbors).all():
            kind = "low"
        else:
            continue

        # --- minimum swing filter (#1) ---
        if min_swing > 0 and last_opposite is not None:
            if last_opposite[2] != kind:  # last pivot is opposite kind
                if kind == "high":
                    swing = float(center) - last_opposite[1]
                else:
                    swing = last_opposite[1] - float(center)
                if swing < min_swing:
                    continue  # not enough of a move — skip this pivot

        pivot = RSIPivot(
            bar_index=idx,
            rsi_value=float(center),
            kind=kind,
            confirmation_bar_index=idx + right_bars,
        )
        pivots.append(pivot)
        last_opposite = (idx, float(center), kind)

    return pivots


class DeterministicPivotLineBuilder:
    """Builds trendlines from RSI pivots with quality filters.

    Improvements over the original:
      #3  Structural tolerance — pivots close to the line are treated as touches,
          not violations.  Only pivots that are *significantly* beyond the line
          cause rejection.
      #4  Multi-touch scoring — score = (touch_count * 100) + start_rsi + end_rsi,
          so lines that RSI repeatedly respects outrank two-point-only lines.
      #5  Minimum length — lines shorter than *min_length* bars are dropped.
      #6  Deduplication — lines with nearly identical slope and overlapping bar
          ranges are collapsed to the highest-scored representative.
      #7  Maximum slope — lines with |RSI delta / bars| > max_slope are dropped.
    """

    def build_lines(
        self,
        pivots: Iterable[RSIPivot],
        rsi: pd.Series | None = None,
        structural_tolerance: float = 3.0,
        min_length: int = 8,
        max_slope: float = 1.0,
    ) -> list[RSILine]:
        ordered_pivots = sorted(
            pivots, key=lambda pivot: (pivot.bar_index, pivot.kind, pivot.rsi_value)
        )
        lines: list[RSILine] = []

        for current_idx, current in enumerate(ordered_pivots):
            for previous in reversed(ordered_pivots[:current_idx]):
                if previous.kind != current.kind:
                    continue

                line = self._build_compatible_line(
                    previous, current, rsi, structural_tolerance, min_length, max_slope
                )
                if line is not None:
                    lines.append(line)

        # Deduplicate overlapping / near-identical lines, keeping the best
        lines = self._deduplicate(lines)
        return lines

    @staticmethod
    def _build_compatible_line(
        previous: RSIPivot,
        current: RSIPivot,
        rsi: pd.Series | None = None,
        structural_tolerance: float = 3.0,
        min_length: int = 8,
        max_slope: float = 1.0,
    ) -> RSILine | None:
        if previous.kind == "high" and current.rsi_value <= previous.rsi_value:
            direction = "down"
        elif previous.kind == "low" and current.rsi_value >= previous.rsi_value:
            direction = "up"
        else:
            return None

        bars = current.bar_index - previous.bar_index

        # #5 — minimum length check (bar count)
        if bars < min_length:
            return None

        # #7 — maximum slope check (RSI points per bar)
        rsi_delta = abs(current.rsi_value - previous.rsi_value)
        if rsi_delta / bars > max_slope:
            return None

        line = RSILine(
            start_bar_index=previous.bar_index,
            end_bar_index=current.bar_index,
            start_rsi=previous.rsi_value,
            end_rsi=current.rsi_value,
            direction=direction,
            end_confirmation_bar_index=current.confirmation_bar_index,
            score=0.0,  # filled in below
        )

        # #3 + #4: structural check with tolerance, touch counting
        is_valid, touch_count = DeterministicPivotLineBuilder._check_structural(
            line, previous.kind, rsi, structural_tolerance
        )
        if not is_valid:
            return None

        # #4: score = (touches * weight) + raw RSI sum
        object.__setattr__(
            line,
            "score",
            float(touch_count * 100) + float(previous.rsi_value + current.rsi_value),
        )
        return line

    def build_best_fit_lines(
        self,
        pivots: Iterable[RSIPivot],
        rsi: pd.Series | None = None,
        structural_tolerance: float = 3.0,
        min_length: int = 8,
        max_slope: float = 0.5,
        ransac_iterations: int = 50,
        min_pivot_inliers: int = 3,
        keep_fraction: float = 0.5,
        max_lines_per_direction: int = 3,
        max_span_bars: int = 200,
    ) -> list[RSILine]:
        """Find the **best-fit RSI trendlines** using **RANSAC** robust
        regression — produces 1-3 lines per direction organically based
        on how clean the RSI trend actually is.

        Algorithm (per direction: ``high`` pivots → downtrend, ``low``
        pivots → uptrend)
        ---------------------------------------------------------
        1. **RANSAC iterations** (*ransac_iterations* times):
           a. Sample 2 random pivots.
           b. Fit a line through them.
           c. Count *inliers* — pivots where
              ``|pivot.rsi - line.at(pivot.bar_index)| <= tolerance``.
           d. Track the best line across all iterations.
        2. **Refit** the best line using OLS on its inliers (so the line
           is the *best fit* through the inlier pivots, not just two).
        3. **Remove inliers** from the pivot pool.
        4. **Repeat** to find the next-best line in the remaining pivots.
        5. **Stop** when the new line has fewer than
           ``best.inliers * keep_fraction`` inliers — meaning RSI no
           longer has another clean trend.
        6. Cap at *max_lines_per_direction* (default 3).

        This is the gold-standard robust line fitting approach used in
        computer vision.  It naturally produces:
        - **1 line** when RSI has a single clean trend
        - **2-3 lines** when RSI is choppy with multiple sub-trends
        """
        pivots_list = list(pivots)
        ordered = sorted(pivots_list, key=lambda p: (p.kind, p.bar_index))
        by_kind: dict[str, list[RSIPivot]] = {"high": [], "low": []}
        for p in ordered:
            by_kind[p.kind].append(p)

        out: list[RSILine] = []
        import random as _random

        for kind, plist in by_kind.items():
            if len(plist) < min_pivot_inliers:
                continue
            direction = "down" if kind == "high" else "up"

            available = list(plist)
            direction_lines: list[RSILine] = []
            best_inlier_count = None

            for round_idx in range(max_lines_per_direction):
                if len(available) < min_pivot_inliers:
                    break

                # --- RANSAC: try many random pivot pairs ---
                best_line: RSILine | None = None
                best_inliers: list[RSIPivot] = []
                best_score = -1.0

                for _ in range(ransac_iterations):
                    if len(available) < 2:
                        break
                    sample = _random.sample(available, 2)
                    sample.sort(key=lambda p: p.bar_index)
                    pa, pb = sample

                    # Reject too-short lines
                    if pb.bar_index - pa.bar_index < min_length:
                        continue

                    # Reject lines that span too much of the chart —
                    # a real trendline is local, not stretched across
                    # the entire run (which causes visual bisection).
                    if pb.bar_index - pa.bar_index > max_span_bars:
                        continue

                    # Slope of this candidate
                    span = pb.bar_index - pa.bar_index
                    slope = (pb.rsi_value - pa.rsi_value) / span

                    # Reject lines with too-shallow a slope — a real
                    # trendline must have a meaningful direction,
                    # otherwise it just bisects the RSI curve as a
                    # near-horizontal line.
                    if abs(slope) < 0.03:
                        continue

                    # Reject too-steep lines
                    if abs(slope) > max_slope:
                        continue

                    # Reject wrong-direction lines
                    if direction == "down" and pb.rsi_value >= pa.rsi_value:
                        continue
                    if direction == "up" and pb.rsi_value <= pa.rsi_value:
                        continue

                    # Find inliers across ALL pivots (not just available)
                    # — this is correct RANSAC: find the line that
                    # explains the most data points overall.
                    inliers = []
                    ssr = 0.0
                    for p in plist:
                        if p.bar_index < pa.bar_index or p.bar_index > pb.bar_index:
                            continue
                        predicted = pa.rsi_value + slope * (p.bar_index - pa.bar_index)
                        if abs(p.rsi_value - predicted) <= structural_tolerance:
                            inliers.append(p)
                            ssr += (p.rsi_value - predicted) ** 2

                    if len(inliers) < min_pivot_inliers:
                        continue

                    # Score: inliers dominate, residuals penalize
                    score = float(len(inliers)) * 1000.0 - ssr * 10.0
                    if score > best_score:
                        best_score = score
                        best_inliers = inliers
                        best_line = RSILine(
                            start_bar_index=pa.bar_index,
                            end_bar_index=pb.bar_index,
                            start_rsi=pa.rsi_value,
                            end_rsi=pb.rsi_value,
                            direction=direction,
                            end_confirmation_bar_index=pb.confirmation_bar_index,
                            score=score,
                        )

                if best_line is None:
                    break

                # --- Refit OLS through the inliers for true best-fit ---
                xs = [float(p.bar_index) for p in best_inliers]
                ys = [float(p.rsi_value) for p in best_inliers]
                n = len(xs)
                mean_x = sum(xs) / n
                mean_y = sum(ys) / n
                sxx = sum((x - mean_x) ** 2 for x in xs)
                sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
                if sxx > 1e-12:
                    refit_slope = sxy / sxx
                    refit_intercept = mean_y - refit_slope * mean_x

                    # Validate refit
                    if 0.03 <= abs(refit_slope) <= max_slope:
                        if (direction == "down" and refit_slope < 0) or (
                            direction == "up" and refit_slope > 0
                        ):
                            refit_start_bar = min(xs)
                            refit_end_bar = max(xs)
                            refit_span = refit_end_bar - refit_start_bar
                            if min_length <= refit_span <= max_span_bars:
                                best_line = RSILine(
                                    start_bar_index=int(refit_start_bar),
                                    end_bar_index=int(refit_end_bar),
                                    start_rsi=float(
                                        refit_intercept + refit_slope * refit_start_bar
                                    ),
                                    end_rsi=float(
                                        refit_intercept + refit_slope * refit_end_bar
                                    ),
                                    direction=direction,
                                    end_confirmation_bar_index=best_line.end_confirmation_bar_index,
                                    score=best_score,
                                )

                # Decide whether to keep this line
                inlier_count = len(best_inliers)
                if best_inlier_count is None:
                    best_inlier_count = inlier_count
                else:
                    # Stop if this round's line is much weaker than the best
                    if inlier_count < best_inlier_count * keep_fraction:
                        break

                direction_lines.append(best_line)
                # Remove inliers from the pool for the next round
                inlier_keys = {(p.bar_index, p.rsi_value) for p in best_inliers}
                available = [
                    p for p in available
                    if (p.bar_index, p.rsi_value) not in inlier_keys
                ]

            out.extend(direction_lines)

        # Sort by score descending — best lines first
        out.sort(key=lambda ln: ln.score, reverse=True)
        return out

    @staticmethod
    def _ols_best_fit(
        pivots: list[RSIPivot],
        direction: str,
        tolerance: float,
        min_length: int,
        max_slope: float,
        min_pivot_touches: int,
        residual_penalty: float,
    ) -> RSILine | None:
        """Fit an OLS line through *pivots* and iteratively refine.

        OLS minimizes Σ(rsi_actual − rsi_predicted)² — the classic
        "least squares" best fit for y as a function of x.

        Algorithm
        ---------
        1. Fit OLS through all *pivots*.
        2. While the worst pivot's residual exceeds *tolerance* and we
           still have >= *min_pivot_touches* pivots: drop the worst
           pivot, refit OLS.
        3. Score = ``pivot_count * 1000 - ssr * residual_penalty``.
        4. Drop the line if it doesn't reach *min_pivot_touches* or
           violates slope/length constraints.
        """
        if len(pivots) < min_pivot_touches:
            return None

        current = list(pivots)

        while len(current) >= min_pivot_touches:
            xs = [float(p.bar_index) for p in current]
            ys = [float(p.rsi_value) for p in current]
            n = len(xs)
            mean_x = sum(xs) / n
            mean_y = sum(ys) / n
            sxx = sum((x - mean_x) ** 2 for x in xs)
            sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
            if sxx <= 1e-12:
                break
            slope = sxy / sxx
            intercept = mean_y - slope * mean_x

            if abs(slope) > max_slope:
                return None  # any further iteration won't help

            # Find worst residual
            worst_idx = -1
            worst_abs_residual = -1.0
            for i, (x, y) in enumerate(zip(xs, ys)):
                residual = abs(y - (slope * x + intercept))
                if residual > worst_abs_residual:
                    worst_abs_residual = residual
                    worst_idx = i

            if worst_abs_residual <= tolerance:
                break  # all pivots fit

            # Drop worst pivot and retry
            current.pop(worst_idx)

        if len(current) < min_pivot_touches:
            return None

        # Final OLS fit on the cleaned cluster
        xs = [float(p.bar_index) for p in current]
        ys = [float(p.rsi_value) for p in current]
        n = len(xs)
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        sxx = sum((x - mean_x) ** 2 for x in xs)
        sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        if sxx <= 1e-12:
            return None
        slope = sxy / sxx
        intercept = mean_y - slope * mean_x

        if abs(slope) > max_slope:
            return None

        # Direction enforcement on final fit
        if direction == "down" and slope >= 0:
            return None
        if direction == "up" and slope <= 0:
            return None

        start_pivot = current[0]
        end_pivot = current[-1]
        span = end_pivot.bar_index - start_pivot.bar_index
        if span < min_length:
            return None

        ssr = sum(
            (y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys)
        )
        pivot_count = len(current)

        # Score: pivot count dominates, residuals penalize
        score = float(pivot_count) * 1000.0 - ssr * residual_penalty

        return RSILine(
            start_bar_index=start_pivot.bar_index,
            end_bar_index=end_pivot.bar_index,
            start_rsi=float(slope * start_pivot.bar_index + intercept),
            end_rsi=float(slope * end_pivot.bar_index + intercept),
            direction=direction,
            end_confirmation_bar_index=end_pivot.confirmation_bar_index,
            score=score,
        )

    @staticmethod
    def _check_structural(
        line: RSILine,
        pivot_kind: str,
        rsi: pd.Series | None,
        tolerance: float = 3.0,
    ) -> tuple[bool, int]:
        """Returns (is_valid, touch_count).

        is_valid  — False only if an intermediate same-kind RSI point
                    exceeds the line by more than *tolerance*.
        touch_count — number of RSI bars (including endpoints) within
                      *tolerance* of the line.
        """
        if rsi is None:
            return True, 2

        values = rsi.astype(float).reset_index(drop=True)
        touch_count = 2  # endpoints always count

        for idx in range(line.start_bar_index + 1, line.end_bar_index):
            line_value = line.value_at(idx)
            if line_value is None:
                continue
            point_value = float(values.iloc[idx])
            distance = point_value - line_value

            if pivot_kind == "high":
                # A resistance line: point above the line by > tolerance → invalid
                if distance > tolerance:
                    return False, 0
                if abs(distance) <= tolerance:
                    touch_count += 1
            else:  # low → support line
                # Point below the line by > tolerance → invalid
                if distance < -tolerance:
                    return False, 0
                if abs(distance) <= tolerance:
                    touch_count += 1

        return True, touch_count

    @staticmethod
    def _deduplicate(lines: list[RSILine]) -> list[RSILine]:
        """Merge lines with similar slope and overlapping bar ranges.

        Two lines are considered duplicates when:
          - Same direction (up / down)
          - Slopes differ by less than 15 %
          - Bar ranges overlap by at least 50 % of the smaller range
        The highest-scored line is kept.
        """
        if len(lines) <= 1:
            return lines

        kept: list[RSILine] = []
        used = [False] * len(lines)

        # Sort by score descending so the best line wins each group
        indexed = sorted(enumerate(lines), key=lambda t: t[1].score, reverse=True)

        for orig_idx, line in indexed:
            if used[orig_idx]:
                continue
            kept.append(line)
            used[orig_idx] = True

            # Mark near-duplicates of this line
            for other_idx, other in enumerate(lines):
                if used[other_idx] or other_idx == orig_idx:
                    continue
                if other.direction != line.direction:
                    continue
                if not DeterministicPivotLineBuilder._is_near_duplicate(line, other):
                    continue
                used[other_idx] = True

        return kept

    @staticmethod
    def _is_near_duplicate(a: RSILine, b: RSILine) -> bool:
        """True when *a* and *b* have similar slope and overlapping range."""
        a_range = a.end_bar_index - a.start_bar_index
        b_range = b.end_bar_index - b.start_bar_index
        if a_range <= 0 or b_range <= 0:
            return False

        a_slope = (a.end_rsi - a.start_rsi) / a_range
        b_slope = (b.end_rsi - b.start_rsi) / b_range
        max_slope = max(abs(a_slope), abs(b_slope), 1e-6)
        if max_slope > 0 and abs(a_slope - b_slope) / max_slope > 0.15:
            return False  # slopes differ by more than 15 %

        # Bar-range overlap
        overlap_start = max(a.start_bar_index, b.start_bar_index)
        overlap_end = min(a.end_bar_index, b.end_bar_index)
        overlap = max(0, overlap_end - overlap_start)
        min_range = min(a_range, b_range)
        return overlap >= min_range * 0.5  # at least 50 % overlap

    # ------------------------------------------------------------------
    # Best-fit cluster algorithm (Total Least Squares)
    # ------------------------------------------------------------------
    def cluster_best_fit_lines(
        self,
        pivots: Iterable[RSIPivot],
        rsi: pd.Series | None = None,
        structural_tolerance: float = 3.0,
        min_length: int = 8,
        max_slope: float = 1.0,
        pivot_tolerance: float = 3.0,
        min_pivot_touches: int = 3,
    ) -> list[RSILine]:
        """Build lines via TLS (Total Least Squares) best-fit through
        pivots, then return ONE line per pivot cluster.

        Algorithm
        ---------
        1. Split pivots by kind (``high`` for downtrend, ``low`` for uptrend).
        2. Group same-kind pivots into clusters using a sliding window of
           *pivot_tolerance* bars (default 3.0 bars apart).
        3. For each cluster of >= 3 pivots, fit a line via Total Least
           Squares (orthogonal regression — minimizes *perpendicular*
           distance, treating x and y symmetrically).
        4. Score = (pivots_within_tolerance * 1000) + (rsi_bars_within_tolerance)
             + rsi_sum.
           This means lines passing through more pivots always rank higher.
        5. Drop lines with fewer than *min_pivot_touches* pivots on them
           or with |slope| > *max_slope*.

        Notes
        -----
        Unlike :meth:`build_lines` (which constructs a line between every
        pivot pair), this method produces a *single* best-fit line per
        cluster of pivots — addressing the user's concern that the
        current implementation produces many near-parallel lines.
        """
        ordered = sorted(pivots, key=lambda p: (p.kind, p.bar_index))
        by_kind: dict[str, list[RSIPivot]] = {"high": [], "low": []}
        for p in ordered:
            by_kind[p.kind].append(p)

        out: list[RSILine] = []

        for kind, plist in by_kind.items():
            if len(plist) < 3:
                continue
            direction = "down" if kind == "high" else "up"

            # Cluster pivots that are close in bar_index space
            clusters: list[list[RSIPivot]] = []
            current: list[RSIPivot] = [plist[0]]
            for prev, curr in zip(plist, plist[1:]):
                gap_bars = curr.bar_index - prev.bar_index
                gap_rsi = abs(curr.rsi_value - prev.rsi_value)
                # Two pivots are "close" if close in BOTH bar_index and rsi
                if gap_bars <= pivot_tolerance * 5 and gap_rsi <= pivot_tolerance * 2:
                    current.append(curr)
                else:
                    if len(current) >= 3:
                        clusters.append(current)
                    current = [curr]
            if len(current) >= 3:
                clusters.append(current)

            for cluster in clusters:
                line = self._fit_cluster(
                    cluster, direction, rsi,
                    structural_tolerance, min_length, max_slope,
                    min_pivot_touches,
                )
                if line is not None:
                    out.append(line)

        # Sort by score descending — best-fit lines first
        out.sort(key=lambda ln: ln.score, reverse=True)
        return out

    @staticmethod
    def _fit_cluster(
        cluster: list[RSIPivot],
        direction: str,
        rsi: pd.Series | None,
        tolerance: float,
        min_length: int,
        max_slope: float,
        min_pivot_touches: int,
    ) -> RSILine | None:
        """Fit ONE best-fit line through *cluster* using Total Least Squares.

        Score-based: pivot count * 1000 (most important), with larger
        clusters always beating smaller ones even when they have a
        slightly worse fit — because the user asked for "the line that
        passes through the most pivots."
        """
        if len(cluster) < 3:
            return None

        pivots = list(cluster)
        slope, intercept = DeterministicPivotLineBuilder._total_least_squares(pivots)

        if abs(slope) > max_slope:
            return None

        start_pivot = pivots[0]
        end_pivot = pivots[-1]
        span = end_pivot.bar_index - start_pivot.bar_index
        if span < min_length:
            return None

        # Count pivots within tolerance (this is what the user cares about)
        pivot_touches = sum(
            1 for p in pivots
            if abs(p.rsi_value - (intercept + slope * p.bar_index)) <= tolerance
        )
        if pivot_touches < min_pivot_touches:
            return None

        # Count RSI bars within tolerance (gives more weight to longer lines)
        bar_touches = 0
        if rsi is not None:
            values = rsi.astype(float).reset_index(drop=True)
            for idx in range(start_pivot.bar_index, end_pivot.bar_index + 1):
                predicted = intercept + slope * idx
                actual = float(values.iloc[idx])
                if abs(actual - predicted) <= tolerance:
                    bar_touches += 1

        # Score = (pivot_touches * 1000) + (bar_touches) + RSI_sum
        # Pivot touches dominate (each pivot is worth 1000 bar-touches)
        score = (
            float(pivot_touches) * 1000.0
            + float(bar_touches)
            + float(start_pivot.rsi_value + end_pivot.rsi_value)
        )

        return RSILine(
            start_bar_index=start_pivot.bar_index,
            end_bar_index=end_pivot.bar_index,
            start_rsi=float(intercept + slope * start_pivot.bar_index),
            end_rsi=float(intercept + slope * end_pivot.bar_index),
            direction=direction,
            end_confirmation_bar_index=end_pivot.confirmation_bar_index,
            score=score,
        )

    @staticmethod
    def _total_least_squares(pivots: list[RSIPivot]) -> tuple[float, float]:
        """Total Least Squares (orthogonal) regression on (bar_index, rsi_value).

        Minimizes the sum of *perpendicular* distances from each pivot to
        the fitted line.  This is the right fit when both x and y carry
        noise — unlike OLS which only fits y.

        Returns
        -------
        (slope, intercept)
        """
        n = len(pivots)
        xs = [float(p.bar_index) for p in pivots]
        ys = [float(p.rsi_value) for p in pivots]
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n

        sxx = sum((x - mean_x) ** 2 for x in xs)
        syy = sum((y - mean_y) ** 2 for y in ys)
        sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))

        # Slope via eigenvector of [[sxx, sxy], [sxy, syy]] corresponding
        # to the smaller eigenvalue — i.e. the direction of least spread.
        # Closed-form:
        denom = (sxx + syy) - ((sxx - syy) ** 2 + 4 * sxy * sxy) ** 0.5
        if abs(denom) < 1e-12:
            # Fall back to OLS slope when data is degenerate
            slope = sxy / sxx if sxx > 0 else 0.0
        else:
            slope = (2 * sxy) / denom

        intercept = mean_y - slope * mean_x
        return slope, intercept


def detect_rsi_line_breaks(
    candles: pd.DataFrame,
    rsi: pd.Series,
    lines: Iterable[RSILine],
    window_bars: int,
) -> list[RSIBreakSignal]:
    signals_by_bar: dict[int, RSIBreakSignal] = {}
    aligned_rsi = rsi.astype(float).reset_index(drop=True)
    aligned_candles = candles.reset_index(drop=True)

    if "bar_index" not in aligned_candles.columns:
        aligned_candles = aligned_candles.copy()
        aligned_candles["bar_index"] = aligned_candles.index

    for line in lines:
        break_scan_start = max(line.end_bar_index + 1, line.end_confirmation_bar_index)
        for idx in range(break_scan_start, len(aligned_rsi)):
            previous_idx = idx - 1
            previous_rsi = float(aligned_rsi.iloc[previous_idx])
            current_rsi = float(aligned_rsi.iloc[idx])
            previous_line_value = line.value_at(previous_idx)
            current_line_value = line.value_at(idx)
            if previous_line_value is None or current_line_value is None:
                continue

            crossed_up = line.direction == "down" and previous_rsi <= previous_line_value and current_rsi > current_line_value
            crossed_down = line.direction == "up" and previous_rsi >= previous_line_value and current_rsi < current_line_value

            if crossed_up or crossed_down:
                window_start = max(0, idx - window_bars + 1)
                window = []
                for window_idx in range(window_start, idx + 1):
                    bar_index = int(aligned_candles.iloc[window_idx]["bar_index"])
                    line_value = line.value_at(bar_index)
                    if line_value is None:
                        continue
                    window.append(
                        {
                            "bar_index": bar_index,
                            "rsi": float(aligned_rsi.iloc[window_idx]),
                            "line_value": float(line_value),
                        }
                    )
                signal = RSIBreakSignal(
                    bar_index=int(aligned_candles.iloc[idx]["bar_index"]),
                    direction="LONG" if crossed_up else "SHORT",
                    line=line,
                    line_value_at_break=current_line_value,
                    rsi_value=current_rsi,
                    rsi_window=window,
                )
                existing_signal = signals_by_bar.get(signal.bar_index)
                if existing_signal is None or _is_more_recent_break(signal, existing_signal):
                    signals_by_bar[signal.bar_index] = signal
                break

    signals = sorted(signals_by_bar.values(), key=lambda signal: signal.bar_index)
    return signals


def _is_more_recent_break(candidate: RSIBreakSignal, incumbent: RSIBreakSignal) -> bool:
    candidate_rank = (
        float(candidate.line.score),
        candidate.line.start_bar_index,
        candidate.line.end_bar_index,
    )
    incumbent_rank = (
        float(incumbent.line.score),
        incumbent.line.start_bar_index,
        incumbent.line.end_bar_index,
    )
    return candidate_rank > incumbent_rank
