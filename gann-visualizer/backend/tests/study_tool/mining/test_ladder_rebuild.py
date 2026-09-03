"""
Rebuilding the ladder at a breach bar, and racing target against stop.

The corpus stores ladders as the three integers they are a pure function of,
so 'the next level up from here' has to be rebuilt. build_all_ladders reads
`price` only as int(round(price * scale)), which is exactly the stored
price_square, so the rebuild is exact rather than approximate - that is pinned
by a test.
"""
import sys
import os

import numpy as np
import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.corpus_meta import CorpusMeta
from study_tool.mining.ladder_rebuild import (
    LadderCache, add_reach_outcomes, race_to_next_level,
)
from study_tool.run_ladder_study import build_all_ladders, degree_to_square

SUN = degree_to_square(155.0)
MOON = degree_to_square(331.0)


def keys_frame():
    return pd.DataFrame({
        "bar_index": [0, 1],
        "price_square": [1307, 1307],
        "sun_square": [SUN, SUN],
        "moon_square": [MOON, MOON],
    })


def meta(shadow_offsets=(0.4,)):
    return CorpusMeta(
        symbol="RELIANCE", from_date="a", to_date="b", interval="5",
        price_scale=1, shadow_count=len(shadow_offsets), seed=7,
        median_sub_gap=2.25, shadow_offsets=list(shadow_offsets),
        resolution_window_bars=50, bar_count=2,
    )


def test_rebuilt_prices_match_a_direct_build_exactly():
    cache = LadderCache(keys_frame(), price_scale=1)
    direct = sorted(l["price"] for l in build_all_ladders(1307, 1, SUN, MOON)
                    if l["source"] == "center")

    rebuilt = list(cache.prices(bar_index=0, source="center"))

    assert rebuilt == pytest.approx(direct)


def test_the_grid_is_built_once_per_distinct_key(monkeypatch):
    """
    14,641 distinct keys at 6.3 ms each is 92 seconds. Rebuilding per event
    would be 14,803 real breaches plus 740,000 shadow ones.
    """
    from study_tool.mining import ladder_rebuild

    calls = {"n": 0}
    real = ladder_rebuild.build_all_ladders

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(ladder_rebuild, "build_all_ladders", counting)

    cache = LadderCache(keys_frame(), price_scale=1)
    for _ in range(20):
        cache.prices(bar_index=0, source="center")
        cache.prices(bar_index=1, source="sun")

    assert calls["n"] == 1, f"{calls['n']} builds for one distinct key"


def test_next_level_up_is_the_smallest_price_above_the_breached_one():
    cache = LadderCache(keys_frame(), price_scale=1)
    prices = list(cache.prices(bar_index=0, source="center"))
    level = prices[len(prices) // 2]

    target = cache.next_level(bar_index=0, source="center",
                              level_price=level, direction="up", offset=0.0)

    assert target > level
    assert target == pytest.approx(min(p for p in prices if p > level))


def test_next_level_down_is_the_largest_price_below():
    cache = LadderCache(keys_frame(), price_scale=1)
    prices = list(cache.prices(bar_index=0, source="center"))
    level = prices[len(prices) // 2]

    target = cache.next_level(bar_index=0, source="center",
                              level_price=level, direction="down", offset=0.0)

    assert target == pytest.approx(max(p for p in prices if p < level))


def test_a_shadow_target_is_the_real_target_shifted_by_its_offset():
    """
    The reason meta.json exists. A shadow ladder is the real one plus a
    constant, so subtracting the offset, looking up, and adding it back gives
    the shadow's own next level without rebuilding anything.
    """
    cache = LadderCache(keys_frame(), price_scale=1)
    prices = list(cache.prices(bar_index=0, source="center"))
    level = prices[len(prices) // 2]

    real_target = cache.next_level(0, "center", level, "up", offset=0.0)
    shadow_target = cache.next_level(0, "center", level + 0.4, "up", offset=0.4)

    assert shadow_target == pytest.approx(real_target + 0.4)


def test_next_level_returns_none_past_the_end_of_the_ladder():
    """The ladder is finite. Beyond its top there is no next level to reach."""
    cache = LadderCache(keys_frame(), price_scale=1)
    top = max(cache.prices(bar_index=0, source="center"))

    assert cache.next_level(0, "center", top, "up", offset=0.0) is None


def test_race_reaches_the_target():
    highs = np.array([100.0, 101.0, 105.0])
    lows = np.array([99.0, 100.0, 101.0])
    closes = np.array([100.0, 101.0, 104.0])

    assert race_to_next_level(highs, lows, closes, start=0, level_price=99.5,
                              target=104.5, direction="up", window=50) == "REACHED"


def test_race_stops_when_price_closes_back_through_the_level():
    highs = np.array([100.0, 101.0, 101.0])
    lows = np.array([99.0, 98.0, 97.0])
    closes = np.array([100.0, 99.0, 98.0])

    assert race_to_next_level(highs, lows, closes, start=0, level_price=99.5,
                              target=104.5, direction="up", window=50) == "STOPPED"


def test_race_times_out_when_neither_happens_in_the_window():
    highs = np.array([100.0] * 10)
    lows = np.array([99.9] * 10)
    closes = np.array([100.0] * 10)

    assert race_to_next_level(highs, lows, closes, start=0, level_price=99.5,
                              target=104.5, direction="up", window=5) == "TIMEOUT"


def test_a_bar_that_both_reaches_and_closes_back_counts_as_reached():
    """
    The target is a high, which happens during the bar. The stop is a close,
    which happens at its end. So within one bar the target came first. This is
    a real judgement call, so it is pinned rather than left to reading order.
    """
    highs = np.array([100.0, 106.0])
    lows = np.array([99.0, 98.0])
    closes = np.array([100.0, 98.5])

    assert race_to_next_level(highs, lows, closes, start=0, level_price=99.5,
                              target=104.5, direction="up", window=50) == "REACHED"


def test_race_runs_down_as_well_as_up():
    highs = np.array([100.0, 100.0, 100.0])
    lows = np.array([99.0, 98.0, 94.0])
    closes = np.array([100.0, 99.0, 95.0])

    assert race_to_next_level(highs, lows, closes, start=0, level_price=100.5,
                              target=94.5, direction="down", window=50) == "REACHED"


def test_race_truncated_by_the_end_of_data_is_a_timeout_not_a_loss():
    highs = np.array([100.0, 101.0])
    lows = np.array([99.0, 100.0])
    closes = np.array([100.0, 101.0])

    assert race_to_next_level(highs, lows, closes, start=0, level_price=99.5,
                              target=104.5, direction="up", window=50) == "TIMEOUT"


def test_add_reach_outcomes_labels_only_confirmed_breaches():
    events = pd.DataFrame({
        "event_type": ["LADDER_BREACH_CONFIRMED", "LADDER_TOUCH"],
        "bar_index": [0, 0],
        "shadow_id": [None, None],
        "level_source": ["center", "center"],
        "level_price": [1307.0, 1307.0],
        "direction": ["up", None],
    })
    bars = pd.DataFrame({
        "high": [1310.0, 1400.0], "low": [1300.0, 1305.0],
        "close": [1308.0, 1390.0],
    })

    result = add_reach_outcomes(events, bars, LadderCache(keys_frame(), 1),
                                meta())

    assert result.loc[1, "reach_outcome"] is None
    assert result.loc[0, "reach_outcome"] in ("REACHED", "STOPPED", "TIMEOUT")
