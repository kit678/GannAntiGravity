"""
Matched placebo: same sessions, same stop distance, same holding limit — only
the entry bar and the direction are randomised.

Holding stop distance fixed is what makes the comparison fair. It isolates
"was the ORB trigger informative?" from "does this exit rule make money on any
entry?". Follows the pattern established by scripts/placebo_test_rsi.py.
"""

import random
from datetime import date, time
from typing import Any, Dict, List, Sequence

import pandas as pd

from analysis.signal_trade_simulator import CandleSignal
from strategy.orb.session import FLAT_BY, SESSION_START, bars_until_flat, post_range_bars
from strategy.orb.types import OrbSignal


def build_placebo_signals(
    real: Sequence[OrbSignal],
    sessions: Dict[date, pd.DataFrame],
    params: Dict[str, Any],
    seed: int,
) -> List[CandleSignal]:
    """One placebo signal per real signal, with entry bar and side randomised."""
    or_minutes: int = params.get("or_minutes", params.get("warmup_minutes", 15))
    session_start: time = params.get("session_start", SESSION_START)
    flat_by: time = params.get("flat_by", FLAT_BY)

    rng = random.Random(seed)
    placebos: List[CandleSignal] = []

    for orb_signal in real:
        if not orb_signal.triggered:
            continue

        session = sessions.get(orb_signal.session_date)
        if session is None:
            continue

        candidates = post_range_bars(
            session, or_minutes=or_minutes, session_start=session_start, flat_by=flat_by
        )
        if candidates.empty:
            continue

        stop_distance = abs(orb_signal.signal.entry_price - orb_signal.signal.stop_price)

        row = candidates.iloc[rng.randrange(len(candidates))]
        bar_index = int(row["bar_index"])
        entry_price = float(row["close"])

        remaining = bars_until_flat(
            session, bar_index=bar_index, session_start=session_start, flat_by=flat_by
        )
        if remaining < 1:
            continue

        side = rng.choice(["LONG", "SHORT"])
        stop_price = (
            entry_price - stop_distance if side == "LONG" else entry_price + stop_distance
        )
        if stop_price <= 0:
            continue

        placebos.append(
            CandleSignal(
                bar_index=bar_index,
                side=side,
                entry_price=entry_price,
                stop_price=stop_price,
                signal_time=row["ist"].isoformat(),
                max_hold_bars=remaining,
            )
        )

    return placebos


def placebo_percentile(real_avg_net_pnl: float, placebo_avgs: Sequence[float]) -> float:
    """Percentage of placebo runs the real result beat. 100.0 means it beat all."""
    if not placebo_avgs:
        raise ValueError("placebo distribution is empty")
    beaten = sum(1 for value in placebo_avgs if real_avg_net_pnl > value)
    return round(100.0 * beaten / len(placebo_avgs), 2)
