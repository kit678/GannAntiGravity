"""
CRT / liquidity sweep — the failed-breakout reversal.

A bar's WICK pushes past the recent high (or low), but its CLOSE comes back
inside the range. The break failed. Fade it: trade against the direction of the
sweep, with the stop beyond the wick extreme that did the sweeping.

Stripped of the "smart money" narrative this is just a failed breakout, and the
mechanical rule is what gets tested here.

Two deliberate choices worth stating:

- The level is the highest high / lowest low of the ``lookback_bars`` bars that
  CLOSED BEFORE the trigger bar. It never includes the trigger bar's own extreme,
  and it never looks forward.
- It does not use ``study_tool.pivot_detector``. That detector confirms a pivot
  only after ``right_bars`` FUTURE bars have printed, which is fine for drawing
  on a chart but is lookahead bias in a backtest.

This module decides only where to enter and where the stop sits. Targets, costs
and P&L belong to analysis/signal_trade_simulator.py.

The shared harness it builds on (session splitting, costs, placebo, verdict,
runner) lives under ``strategy/orb/`` for historical reasons but is
strategy-agnostic — only the signal rule differs between families.
"""

from datetime import time
from typing import Any, Dict

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
    "lookback_bars": 12,
    "bar_minutes": 5,
    "session_start": SESSION_START,
    "flat_by": FLAT_BY,
}


def generate_signal(session: pd.DataFrame, params: Dict[str, Any]) -> OrbSignal:
    """Evaluate one session. Returns at most one signal."""
    settings = {**DEFAULTS, **params}
    lookback_bars: int = settings["lookback_bars"]
    bar_minutes: int = settings["bar_minutes"]
    session_start: time = settings["session_start"]
    flat_by: time = settings["flat_by"]

    session_date = session["session_date"].iloc[0]

    # Skipping the first `lookback_bars` bars IS the warmup — there is no
    # separate warmup knob, because a level needs that many closed bars to exist.
    warmup_minutes = lookback_bars * bar_minutes
    tradable = post_range_bars(
        session, or_minutes=warmup_minutes, session_start=session_start, flat_by=flat_by
    )
    if tradable.empty:
        return OrbSignal.skipped(
            session_date,
            "insufficient_lookback",
            session_bars=len(session),
            lookback_bars=lookback_bars,
        )

    highs = session["high"].tolist()
    lows = session["low"].tolist()
    bar_indices = session["bar_index"].tolist()
    position_of_bar = {bar_index: pos for pos, bar_index in enumerate(bar_indices)}

    for _, bar in tradable.iterrows():
        bar_index = int(bar["bar_index"])
        pos = position_of_bar[bar_index]
        if pos < lookback_bars:
            continue

        window_start = pos - lookback_bars
        level_high = max(highs[window_start:pos])
        level_low = min(lows[window_start:pos])

        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])

        # A sweep needs the wick through the level AND the close back inside.
        # If the close also clears the level it is a genuine breakout, not a
        # failed one, so it is deliberately not traded here.
        if high > level_high and close < level_high:
            side, stop_price = "SHORT", high
        elif low < level_low and close > level_low:
            side, stop_price = "LONG", low
        else:
            continue

        remaining = bars_until_flat(
            session, bar_index=bar_index, session_start=session_start, flat_by=flat_by
        )
        if remaining < 1:
            return OrbSignal.skipped(
                session_date,
                "no_bars_before_flat",
                level_high=level_high,
                level_low=level_low,
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
            level_high=level_high,
            level_low=level_low,
            sweep_depth=abs(stop_price - close),
        )

    return OrbSignal.skipped(session_date, "no_sweep", lookback_bars=lookback_bars)
