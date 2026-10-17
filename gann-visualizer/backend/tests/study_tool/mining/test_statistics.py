"""
The five statistics. Each is a pure function from an events frame to a value
and its sample size.

`depth_in_sublevels` is not a column - it lives inside the `details` JSON
string on LADDER_RETEST rows - so mean_retest_depth parses it. That is pinned
by a test because it is the kind of thing a refactor silently breaks.
"""
import sys
import os
import json

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.statistics import (
    already_hit_share, dropped_share, entry_dropped_share, hold_rate,
    lag_free_reach_rate, lag_free_reach_rate_for, mean_retest_depth,
    reach_next_rate, reach_rate_for, rejection_rate, timeout_share,
    timeout_share_for, touch_density_fn,
)


def resolved(outcomes):
    return pd.DataFrame({
        "event_type": ["LADDER_BREACH_RESOLVED"] * len(outcomes),
        "outcome": outcomes,
    })


def test_hold_rate_counts_only_breaches_that_came_back():
    frame = resolved(["RETEST_HELD", "RETEST_HELD", "RETEST_FAILED",
                      "NEVER_RETESTED", "NEVER_CONFIRMED"])

    stat = hold_rate(frame)

    assert stat.value == 2 / 3
    assert stat.n == 3, "n must be the retested breaches, not all rows"


def test_hold_rate_is_none_when_nothing_was_retested():
    stat = hold_rate(resolved(["NEVER_RETESTED", "NEVER_CONFIRMED"]))

    assert stat.value is None
    assert stat.n == 0


def test_rejection_rate_is_never_confirmed_over_all_resolved():
    frame = resolved(["NEVER_CONFIRMED", "RETEST_HELD", "RETEST_FAILED",
                      "NEVER_RETESTED"])

    stat = rejection_rate(frame)

    assert stat.value == 0.25
    assert stat.n == 4


def test_rejection_rate_ignores_truncated_breaches():
    """
    A breach still open when the data ended has outcome None. It is neither a
    rejection nor a confirmation, and counting it either way biases the rate.
    """
    frame = resolved(["NEVER_CONFIRMED", "RETEST_HELD", None])

    stat = rejection_rate(frame)

    assert stat.n == 2
    assert stat.value == 0.5


def test_mean_retest_depth_reads_depth_out_of_the_details_json():
    frame = pd.DataFrame({
        "event_type": ["LADDER_RETEST", "LADDER_RETEST", "LADDER_TOUCH"],
        "details": [json.dumps({"depth_in_sublevels": 0.4}),
                    json.dumps({"depth_in_sublevels": 0.8}),
                    json.dumps({"depth_in_sublevels": 99.0})],
    })

    stat = mean_retest_depth(frame)

    assert stat.value == pytest.approx(0.6)
    assert stat.n == 2, "the LADDER_TOUCH row must not be counted"


def test_mean_retest_depth_survives_a_details_string_without_the_key():
    frame = pd.DataFrame({
        "event_type": ["LADDER_RETEST", "LADDER_RETEST"],
        "details": [json.dumps({"depth_in_sublevels": 0.4}),
                    json.dumps({"retest_extreme": 12.0})],
    })

    stat = mean_retest_depth(frame)

    assert stat.value == 0.4
    assert stat.n == 1


def test_touch_density_is_touches_per_bar():
    frame = pd.DataFrame({"event_type": ["LADDER_TOUCH"] * 30 +
                                        ["LADDER_CROSS"] * 5})

    stat = touch_density_fn(bar_count=10)(frame)

    assert stat.value == 3.0
    assert stat.n == 30


def test_touch_density_is_none_for_zero_bars():
    frame = pd.DataFrame({"event_type": ["LADDER_TOUCH"]})

    assert touch_density_fn(bar_count=0)(frame).value is None


def test_reach_next_rate_excludes_timeouts_from_the_ratio():
    """A timeout is neither a win nor a loss, so it must not dilute either."""
    frame = pd.DataFrame({
        "reach_outcome": ["REACHED", "REACHED", "STOPPED", "TIMEOUT",
                          "TIMEOUT", None],
    })

    stat = reach_next_rate(frame)

    assert stat.value == 2 / 3
    assert stat.n == 3


def test_timeout_share_reports_what_reach_next_rate_dropped():
    frame = pd.DataFrame({
        "reach_outcome": ["REACHED", "STOPPED", "TIMEOUT", "TIMEOUT"],
    })

    stat = timeout_share(frame)

    assert stat.value == 0.5
    assert stat.n == 4


def test_every_statistic_returns_none_on_an_empty_frame():
    empty = pd.DataFrame({"event_type": pd.Series(dtype="object"),
                          "outcome": pd.Series(dtype="object"),
                          "details": pd.Series(dtype="object"),
                          "reach_outcome": pd.Series(dtype="object")})

    for fn in (hold_rate, rejection_rate, mean_retest_depth,
               reach_next_rate, timeout_share, touch_density_fn(100)):
        assert fn(empty).value is None, fn
        assert fn(empty).n == 0, fn


def test_reach_rate_for_reads_the_column_it_was_given():
    frame = pd.DataFrame({
        "reach_d0_w50": ["REACHED", "STOPPED", "STOPPED", "TIMEOUT"],
        "reach_d1_w50": ["REACHED", "REACHED", "STOPPED", "TIMEOUT"],
    })

    assert reach_rate_for("reach_d0_w50")(frame).value == pytest.approx(1 / 3)
    assert reach_rate_for("reach_d1_w50")(frame).value == pytest.approx(2 / 3)


def test_reach_rate_for_a_missing_column_is_none_not_zero():
    frame = pd.DataFrame({"reach_d0_w50": ["REACHED"]})

    stat = reach_rate_for("reach_d9_w50")(frame)

    assert stat.value is None
    assert stat.n == 0


def test_timeout_share_for_reads_its_own_column():
    frame = pd.DataFrame({
        "reach_d1_w50": ["REACHED", "STOPPED", "TIMEOUT", "TIMEOUT"],
    })

    assert timeout_share_for("reach_d1_w50")(frame).value == 0.5


def test_already_hit_share_measures_free_wins():
    """
    The share of raced breaches whose target was already reached when the
    breach confirmed. A high number would hollow out the headline rate.
    """
    frame = pd.DataFrame({"target_already_hit": [True, True, False, None]})

    stat = already_hit_share(frame)

    assert stat.value == pytest.approx(2 / 3)
    assert stat.n == 3


def test_already_hit_share_is_none_when_nothing_was_raced():
    frame = pd.DataFrame({"target_already_hit": [None, None]})

    assert already_hit_share(frame).value is None


def lag_free_frame():
    """
    Row 0 kept REACHED, row 1 kept STOPPED, row 2 dropped (target hit),
    row 3 dropped (closed back), row 4 kept TIMEOUT, row 5 not targeted,
    row 6 dropped by both filters.
    """
    return pd.DataFrame({
        "reach_outcome": ["REACHED", "STOPPED", "REACHED", "REACHED",
                          "TIMEOUT", None, "STOPPED"],
        "target_hit_before_entry": [False, False, True, False, False, None,
                                    True],
        "entry_beyond_level": [True, True, True, False, True, None, False],
    })


def test_lag_free_reach_rate_keeps_only_tradeable_breaches():
    stat = lag_free_reach_rate(lag_free_frame())

    assert stat.value == 0.5
    assert stat.n == 2, "timeouts and dropped rows are not decided rows"


def test_lag_free_reach_rate_binds_to_a_named_column():
    frame = lag_free_frame().rename(columns={"reach_outcome": "reach_d0_w100"})

    assert lag_free_reach_rate_for("reach_d0_w100")(frame).value == 0.5
    assert lag_free_reach_rate(frame).value is None


def test_lag_free_reach_rate_is_none_without_the_flag_columns():
    frame = pd.DataFrame({"reach_outcome": ["REACHED"]})

    assert lag_free_reach_rate(frame) == (None, 0)


def test_lag_free_flags_work_as_a_plain_bool_column():
    frame = pd.DataFrame({"reach_outcome": ["REACHED", "STOPPED"],
                          "target_hit_before_entry": [False, True],
                          "entry_beyond_level": [True, True]})
    assert frame["target_hit_before_entry"].dtype == bool

    stat = lag_free_reach_rate(frame)

    assert stat.value == 1.0
    assert stat.n == 1


def test_dropped_share_is_rows_removed_by_either_filter_over_targeted_rows():
    stat = dropped_share(lag_free_frame())

    assert stat.value == 0.5     # rows 2, 3, 6 of 6 targeted
    assert stat.n == 6, "targeted rows include timeouts, exclude untargeted"


def test_entry_dropped_share_counts_only_the_entry_filter():
    stat = entry_dropped_share(lag_free_frame())

    assert stat.value == pytest.approx(2 / 6)   # rows 3 and 6
    assert stat.n == 6


def test_dropped_shares_are_none_with_no_targeted_rows():
    frame = pd.DataFrame({"reach_outcome": [None],
                          "target_hit_before_entry": [None],
                          "entry_beyond_level": [None]})

    assert dropped_share(frame) == (None, 0)
    assert entry_dropped_share(frame) == (None, 0)
