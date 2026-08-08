"""
Variant A — classic opening range breakout.

The first ``or_minutes`` of the session define a box. The first bar afterwards
that CLOSES beyond the box triggers a trade in that direction, with the stop on
the opposite side of the box.

This module decides only where to enter and where the stop sits. Targets, costs
and P&L belong to analysis/signal_trade_simulator.py.
"""

from datetime import time
from typing import Any, Dict

import pandas as pd

from analysis.signal_trade_simulator import CandleSignal
from strategy.orb.session import (
    FLAT_BY,
    SESSION_START,
    bars_until_flat,
    opening_range_bars,
    post_range_bars,
)
from strategy.orb.types import OrbSignal

DEFAULTS: Dict[str, Any] = {
    "or_minutes": 15,
    "bar_minutes": 5,
    "session_start": SESSION_START,
    "flat_by": FLAT_BY,
}


def generate_signal(session: pd.DataFrame, params: Dict[str, Any]) -> OrbSignal:
    """Evaluate one session. Returns at most one signal."""
    settings = {**DEFAULTS, **params}
    or_minutes: int = settings["or_minutes"]
    bar_minutes: int = settings["bar_minutes"]
    session_start: time = settings["session_start"]
    flat_by: time = settings["flat_by"]

    session_date = session["session_date"].iloc[0]

    expected_or_bars = or_minutes // bar_minutes
    or_bars = opening_range_bars(session, or_minutes=or_minutes, session_start=session_start)
    if len(or_bars) < expected_or_bars:
        return OrbSignal.skipped(
            session_date,
            "short_opening_range",
            or_bars_seen=len(or_bars),
            or_bars_expected=expected_or_bars,
        )

    orh = float(or_bars["high"].max())
    orl = float(or_bars["low"].min())
    if orh <= orl:
        return OrbSignal.skipped(session_date, "degenerate_range", orh=orh, orl=orl)

    tradable = post_range_bars(
        session, or_minutes=or_minutes, session_start=session_start, flat_by=flat_by
    )

    for _, bar in tradable.iterrows():
        close = float(bar["close"])
        if close > orh:
            side, stop_price = "LONG", orl
        elif close < orl:
            side, stop_price = "SHORT", orh
        else:
            continue

        bar_index = int(bar["bar_index"])
        remaining = bars_until_flat(
            session, bar_index=bar_index, session_start=session_start, flat_by=flat_by
        )
        if remaining < 1:
            # Triggered on the last holdable bar — nothing left to simulate.
            return OrbSignal.skipped(
                session_date, "no_bars_before_flat", orh=orh, orl=orl, trigger_bar=bar_index
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
            orh=orh,
            orl=orl,
            range_width=orh - orl,
        )

    return OrbSignal.skipped(session_date, "no_breakout", orh=orh, orl=orl)
