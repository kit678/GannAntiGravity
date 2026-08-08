import sys
from datetime import date, time
from pathlib import Path

import pandas as pd
import pytest
import pytz

sys.path.append(str(Path(__file__).resolve().parents[1]))

from strategy.orb.session import (
    add_bar_index,
    bars_until_flat,
    opening_range_bars,
    post_range_bars,
    split_sessions,
    split_dates_in_half,
)

IST = pytz.timezone("Asia/Kolkata")


def _bars_for_day(day, start=time(9, 15), count=6, minutes=5, price=100.0):
    """Build `count` bars of `minutes` length starting at `start` IST on `day`."""
    rows = []
    for i in range(count):
        naive = pd.Timestamp(f"{day} {start.hour:02d}:{start.minute:02d}:00") + pd.Timedelta(
            minutes=minutes * i
        )
        ts = int(IST.localize(naive.to_pydatetime()).timestamp())
        rows.append(
            {
                "timestamp": ts,
                "open": price,
                "high": price + 1.0,
                "low": price - 1.0,
                "close": price,
                "volume": 1000,
            }
        )
    return pd.DataFrame(rows)


def test_add_bar_index_is_unique_and_sorted():
    bars = pd.concat([_bars_for_day("2026-08-04", count=3), _bars_for_day("2026-08-03", count=3)])
    indexed = add_bar_index(bars)

    assert indexed["bar_index"].tolist() == [0, 1, 2, 3, 4, 5]
    assert indexed["timestamp"].is_monotonic_increasing


def test_split_sessions_groups_by_ist_trading_date():
    bars = pd.concat([_bars_for_day("2026-08-03", count=3), _bars_for_day("2026-08-04", count=4)])
    sessions = split_sessions(add_bar_index(bars))

    assert list(sessions.keys()) == [date(2026, 8, 3), date(2026, 8, 4)]
    assert len(sessions[date(2026, 8, 3)]) == 3
    assert len(sessions[date(2026, 8, 4)]) == 4


def test_opening_range_bars_takes_the_first_fifteen_minutes():
    session = split_sessions(add_bar_index(_bars_for_day("2026-08-04", count=6)))[date(2026, 8, 4)]
    or_bars = opening_range_bars(session, or_minutes=15)

    assert len(or_bars) == 3
    assert or_bars["bar_index"].tolist() == [0, 1, 2]


def test_post_range_bars_excludes_the_range_and_respects_flat_by():
    session = split_sessions(add_bar_index(_bars_for_day("2026-08-04", count=6)))[date(2026, 8, 4)]
    after = post_range_bars(session, or_minutes=15, flat_by=time(9, 40))

    assert after["bar_index"].tolist() == [3, 4, 5]


def test_post_range_bars_drops_bars_after_flat_by():
    session = split_sessions(add_bar_index(_bars_for_day("2026-08-04", count=6)))[date(2026, 8, 4)]
    after = post_range_bars(session, or_minutes=15, flat_by=time(9, 35))

    assert after["bar_index"].tolist() == [3, 4]


def test_bars_until_flat_counts_remaining_holdable_bars():
    session = split_sessions(add_bar_index(_bars_for_day("2026-08-04", count=6)))[date(2026, 8, 4)]

    assert bars_until_flat(session, bar_index=3, flat_by=time(9, 40)) == 2
    assert bars_until_flat(session, bar_index=5, flat_by=time(9, 40)) == 0


def test_split_dates_in_half_puts_the_extra_day_in_train():
    dates = [date(2026, 8, d) for d in (3, 4, 5, 6, 7)]
    train, test = split_dates_in_half(dates)

    assert train == dates[:3]
    assert test == dates[3:]


def test_split_dates_in_half_rejects_fewer_than_two_dates():
    with pytest.raises(ValueError, match="at least 2"):
        split_dates_in_half([date(2026, 8, 3)])
