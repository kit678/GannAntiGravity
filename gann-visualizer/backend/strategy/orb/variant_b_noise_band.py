"""
Variant B — noise-band breakout.

Anchored to today's opening price rather than a fixed box, with the band width
scaled by recent daily volatility. This adapts across volatility regimes and
handles gap-open days, because the anchor moves with the gap.

Honesty note: this is a simplified stand-in for the published
volatility-normalised intraday momentum idea, not a reproduction of any
specific paper. Report it that way.
"""

from datetime import time
from typing import Any, Dict, Optional

import pandas as pd

from analysis.signal_trade_simulator import CandleSignal
from strategy.orb.session import (
    FLAT_BY,
    SESSION_START,
    bars_until_flat,
    post_range_bars,
)
from strategy.orb.types import OrbSignal

DEFAULTS: Dict[str, Any] = {
    "warmup_minutes": 15,
    "bar_minutes": 5,
    "k": 0.25,
    "session_start": SESSION_START,
    "flat_by": FLAT_BY,
}


def daily_atr(daily_bars: pd.DataFrame, length: int = 14) -> pd.Series:
    """Simple moving average of true range over daily bars.

    A plain SMA of TR rather than Wilder's smoothing — chosen for being obvious
    to verify by hand. Returns NaN during the warmup period.
    """
    high = daily_bars["high"].astype(float)
    low = daily_bars["low"].astype(float)
    close = daily_bars["close"].astype(float)
    prev_close = close.shift(1)

    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    return true_range.rolling(length, min_periods=length).mean()


def generate_signal(
    session: pd.DataFrame,
    params: Dict[str, Any],
    atr: Optional[float],
) -> OrbSignal:
    """Evaluate one session. ``atr`` must be computed through YESTERDAY's close."""
    settings = {**DEFAULTS, **params}
    warmup_minutes: int = settings["warmup_minutes"]
    k: float = settings["k"]
    session_start: time = settings["session_start"]
    flat_by: time = settings["flat_by"]

    session_date = session["session_date"].iloc[0]

    if atr is None or not float(atr) > 0 or pd.isna(atr):
        return OrbSignal.skipped(session_date, "no_atr", atr=atr)

    anchor = float(session["open"].iloc[0])
    half_width = k * float(atr)
    upper = anchor + half_width
    lower = anchor - half_width

    tradable = post_range_bars(
        session, or_minutes=warmup_minutes, session_start=session_start, flat_by=flat_by
    )

    for _, bar in tradable.iterrows():
        close = float(bar["close"])
        if close > upper:
            side, stop_price = "LONG", lower
        elif close < lower:
            side, stop_price = "SHORT", upper
        else:
            continue

        bar_index = int(bar["bar_index"])
        remaining = bars_until_flat(
            session, bar_index=bar_index, session_start=session_start, flat_by=flat_by
        )
        if remaining < 1:
            return OrbSignal.skipped(
                session_date,
                "no_bars_before_flat",
                anchor=anchor,
                upper=upper,
                lower=lower,
                trigger_bar=bar_index,
            )

        return OrbSignal.fired(
            session_date,
            CandleSignal(
                bar_index=bar_index,
                side=side,
                entry_price=close,
                stop_price=stop_price,
                signal_time=bar["ist"].isoformat(),
                max_hold_bars=remaining,
            ),
            anchor=anchor,
            upper=upper,
            lower=lower,
            atr=float(atr),
        )

    return OrbSignal.skipped(
        session_date, "no_breakout", anchor=anchor, upper=upper, lower=lower, atr=float(atr)
    )
