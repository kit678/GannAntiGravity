"""Pure RSI pivot detection.

Two stages, deliberately separated:

1. ``detect_fractal_candidates`` finds local extremes with a FIXED confirmation
   lag of ``right_bars``.  A fixed lag is why fractals are used rather than a
   zigzag, whose confirmation lag varies with price and would anchor lines too
   late to catch their own breaks.
2. ``apply_dominance`` reduces those candidates to a strictly alternating
   high-low-high-low sequence.  It is a *step* function taking one candidate at
   a time, so the sweep can drive it incrementally.  Running it as a batch pass
   over the whole series would let a pivot superseded at bar 150 rewrite what
   was anchored at bar 100 -- a repaint.  See test_rsi_causality.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class GeometryParams:
    """Every geometry knob, in one place.

    Lives here rather than in rsi_sweep so the dependency direction stays
    one-way: rsi_pivots <- rsi_line_policy <- rsi_sweep.  The policy layer needs
    these values but must never import the sweep that calls it.
    """

    left_bars: int = 3
    right_bars: int = 3
    min_swing: float = 8.0
    tolerance: float = 1.5
    min_length: int = 8
    max_span_bars: int = 150


@dataclass(frozen=True)
class RSIPivot:
    bar_index: int
    rsi_value: float
    kind: str  # "high" | "low"
    confirmation_bar_index: int


def compute_rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI. Bars before ``period`` are seeded at a neutral 50."""
    close = close.astype(float)
    rsi = pd.Series(50.0, index=close.index, dtype=float)
    if len(close) <= period:
        return rsi

    # Wilder's smoothing is recursive, so the loop stays -- but over numpy
    # scalars rather than `.iloc`, which is ~50x the cost per element.
    delta = np.diff(close.to_numpy(dtype=float), prepend=close.iloc[0])
    gain = np.clip(delta, 0.0, None)
    loss = -np.clip(delta, None, 0.0)

    avg_gain = float(gain[1 : period + 1].mean())
    avg_loss = float(loss[1 : period + 1].mean())

    def to_rsi(current_gain: float, current_loss: float) -> float:
        if current_loss == 0.0:
            return 100.0
        rs = current_gain / current_loss
        return 100.0 - (100.0 / (1.0 + rs))

    out = np.full(len(close), 50.0, dtype=float)
    out[period] = to_rsi(avg_gain, avg_loss)

    for idx in range(period + 1, len(close)):
        avg_gain = ((avg_gain * (period - 1)) + gain[idx]) / period
        avg_loss = ((avg_loss * (period - 1)) + loss[idx]) / period
        out[idx] = to_rsi(avg_gain, avg_loss)

    return pd.Series(out, index=close.index, dtype=float)


def detect_fractal_candidates(
    rsi: pd.Series, left_bars: int, right_bars: int
) -> list[RSIPivot]:
    """Local extremes, each confirmed exactly ``right_bars`` after its own bar.

    Vectorised over sliding windows. The obvious per-bar loop builds a fresh
    ``pd.concat`` of its neighbours on every bar, which costs ~10s on a
    175k-bar series and swamped everything else in the sweep.
    """
    values = rsi.astype(float).reset_index(drop=True)
    array = values.to_numpy(dtype=float)
    width = left_bars + right_bars + 1
    if len(array) < width:
        return []

    if width == 1:
        # No neighbours to compare against: the original `.all()` over an
        # empty set is vacuously true and the high branch wins.
        return [
            RSIPivot(idx, float(v), "high", idx)
            for idx, v in enumerate(array)
            if not np.isnan(v)
        ]

    windows = np.lib.stride_tricks.sliding_window_view(array, width)
    centers = windows[:, left_bars]
    neighbours = np.delete(windows, left_bars, axis=1)

    usable = ~np.isnan(centers) & ~np.isnan(neighbours).any(axis=1)
    is_high = usable & (centers > np.nanmax(neighbours, axis=1))
    is_low = usable & (centers < np.nanmin(neighbours, axis=1))

    candidates: list[RSIPivot] = []
    for offset in np.flatnonzero(is_high | is_low):
        idx = int(offset) + left_bars
        candidates.append(
            RSIPivot(
                bar_index=idx,
                rsi_value=float(centers[offset]),
                kind="high" if is_high[offset] else "low",
                confirmation_bar_index=idx + right_bars,
            )
        )

    return candidates


def apply_dominance(
    pivots: list[RSIPivot], candidate: RSIPivot, min_swing: float
) -> tuple[list[RSIPivot], str | None]:
    """Fold one candidate into the running pivot list.

    Returns ``(new_pivots, changed_kind)``.  ``changed_kind`` is the pivot kind
    whose sequence changed, or ``None`` when the candidate was discarded.  The
    input list is never mutated.
    """
    if not pivots:
        return [candidate], candidate.kind

    last = pivots[-1]

    if last.kind == candidate.kind:
        if candidate.kind == "high":
            more_extreme = candidate.rsi_value > last.rsi_value
        else:
            more_extreme = candidate.rsi_value < last.rsi_value
        if more_extreme:
            return pivots[:-1] + [candidate], candidate.kind
        return pivots, None

    if abs(candidate.rsi_value - last.rsi_value) >= min_swing:
        return pivots + [candidate], candidate.kind

    return pivots, None
