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
    hold_rate, mean_retest_depth, reach_next_rate, rejection_rate,
    timeout_share, touch_density_fn,
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
