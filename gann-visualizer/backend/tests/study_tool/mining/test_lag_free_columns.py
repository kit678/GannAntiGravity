"""
The lag-free columns: was the target touched between the cross bar and the
confirmation bar, and did the confirmation bar close beyond the level?

A breach confirms on bar k after `confirmation_closes` consecutive closes, so
its cross bar is c = k - (confirmation_closes - 1). Only bars c..k decide the
filter. The race starts on the bar after k, so the filter must read no bar
after k - that is pinned here.
"""
import sys
import os

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.corpus_meta import CorpusMeta
from study_tool.mining.ladder_rebuild import LadderCache, add_reach_outcomes
from study_tool.run_ladder_study import degree_to_square

SUN = degree_to_square(155.0)
MOON = degree_to_square(331.0)
LEVEL = 1306.0          # a real `center` level for price square 1307
UP_TARGET = 1308.25     # next level up
DOWN_TARGET = 1303.75   # next level down
BAR_COUNT = 8
CONFIRM_BAR = 4         # k in every test


def keys_frame():
    return pd.DataFrame({
        "bar_index": list(range(BAR_COUNT)),
        "price_square": [1307] * BAR_COUNT,
        "sun_square": [SUN] * BAR_COUNT,
        "moon_square": [MOON] * BAR_COUNT,
    })


def meta(confirmation_closes, shadow_offsets=(0.4,)):
    return CorpusMeta(
        symbol="RELIANCE", from_date="a", to_date="b", interval="5",
        price_scale=1, shadow_count=len(shadow_offsets), seed=7,
        median_sub_gap=2.25, shadow_offsets=list(shadow_offsets),
        resolution_window_bars=50, bar_count=BAR_COUNT,
        breach_mode="close", confirmation_closes=confirmation_closes,
    )


def quiet_bars(direction):
    """Bars beyond the level that touch neither target."""
    if direction == "up":
        return pd.DataFrame({"high": [1307.0] * BAR_COUNT,
                             "low": [1306.5] * BAR_COUNT,
                             "close": [1306.8] * BAR_COUNT})
    return pd.DataFrame({"high": [1305.5] * BAR_COUNT,
                         "low": [1305.0] * BAR_COUNT,
                         "close": [1305.2] * BAR_COUNT})


def confirmed(bar_index=CONFIRM_BAR, direction="up", level=LEVEL,
              shadow_id=None):
    return pd.DataFrame({
        "event_type": ["LADDER_BREACH_CONFIRMED"],
        "bar_index": [bar_index],
        "shadow_id": [shadow_id],
        "level_source": ["center"],
        "level_price": [level],
        "direction": [direction],
    })


def outcomes(events, bars, closes):
    return add_reach_outcomes(events, bars, LadderCache(keys_frame(), 1),
                              meta(closes))


@pytest.mark.parametrize("closes, touched_bar, expected", [
    (1, 4, True),     # c = k = 4: the confirmation bar is the cross bar
    (1, 3, False),    # the bar before the cross does not count
    (2, 3, True),     # cross bar c = 3
    (2, 4, True),     # confirmation bar k = 4
    (2, 2, False),    # before the cross
    (3, 2, True),     # cross bar c = 2
    (3, 3, True),     # a middle bar
    (3, 4, True),     # confirmation bar
    (3, 1, False),    # before the cross
    (1, None, False),
    (2, None, False),
    (3, None, False),
])
def test_target_hit_before_entry_reads_bars_from_cross_to_confirmation(
        closes, touched_bar, expected):
    bars = quiet_bars("up")
    if touched_bar is not None:
        bars.loc[touched_bar, "high"] = UP_TARGET + 0.25

    result = outcomes(confirmed(), bars, closes)

    assert bool(result.loc[0, "target_hit_before_entry"]) is expected


def test_the_filter_reads_no_bar_after_confirmation():
    bars = quiet_bars("up")
    before = outcomes(confirmed(), bars, 2)

    later = bars.copy()
    later.loc[CONFIRM_BAR + 1:, "high"] = 1400.0
    later.loc[CONFIRM_BAR + 1:, "low"] = 1200.0
    later.loc[CONFIRM_BAR + 1:, "close"] = 1200.0
    after = outcomes(confirmed(), later, 2)

    for column in ("target_hit_before_entry", "entry_beyond_level"):
        assert bool(before.loc[0, column]) == bool(after.loc[0, column])
    assert bool(after.loc[0, "target_hit_before_entry"]) is False
    assert bool(after.loc[0, "entry_beyond_level"]) is True
    # The race itself does read those bars.
    assert after.loc[0, "reach_outcome"] == "REACHED"


def test_target_hit_before_entry_runs_downward():
    bars = quiet_bars("down")
    bars.loc[3, "low"] = DOWN_TARGET - 0.25

    result = outcomes(confirmed(direction="down"), bars, 2)

    assert bool(result.loc[0, "target_hit_before_entry"]) is True
    assert bool(result.loc[0, "entry_beyond_level"]) is True


def test_target_hit_before_entry_widens_target_already_hit():
    """target_already_hit reads bar k only; the cross bar can be the one."""
    bars = quiet_bars("up")
    bars.loc[3, "high"] = UP_TARGET + 0.25

    result = outcomes(confirmed(), bars, 2)

    assert bool(result.loc[0, "target_hit_before_entry"]) is True
    assert bool(result.loc[0, "target_already_hit"]) is False


def test_entry_beyond_level_is_false_when_the_confirmation_bar_closed_back():
    bars = quiet_bars("up")
    bars.loc[CONFIRM_BAR, "close"] = LEVEL - 0.1

    result = outcomes(confirmed(), bars, 1)

    assert bool(result.loc[0, "entry_beyond_level"]) is False


def test_entry_beyond_level_down_needs_a_close_below():
    bars = quiet_bars("down")
    bars.loc[CONFIRM_BAR, "close"] = LEVEL + 0.1

    result = outcomes(confirmed(direction="down"), bars, 1)

    assert bool(result.loc[0, "entry_beyond_level"]) is False


def test_a_shadow_row_tests_its_own_shifted_target():
    bars = quiet_bars("up")
    bars.loc[CONFIRM_BAR, "high"] = 1308.5   # past 1308.25, short of 1308.65
    events = pd.concat([confirmed(),
                        confirmed(level=LEVEL + 0.4, shadow_id=0.0)],
                       ignore_index=True)

    result = outcomes(events, bars, 2)

    assert bool(result.loc[0, "target_hit_before_entry"]) is True
    assert bool(result.loc[1, "target_hit_before_entry"]) is False


def test_non_breach_rows_stay_none():
    touch = pd.DataFrame({
        "event_type": ["LADDER_TOUCH"], "bar_index": [CONFIRM_BAR],
        "shadow_id": [None], "level_source": ["center"],
        "level_price": [LEVEL], "direction": [None],
    })
    events = pd.concat([confirmed(), touch], ignore_index=True)

    result = outcomes(events, quiet_bars("up"), 2)

    assert result.loc[1, "target_hit_before_entry"] is None
    assert result.loc[1, "entry_beyond_level"] is None
