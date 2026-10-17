"""
compare(): run one statistic on the real events and on every shadow.

Built once so every future question inherits the control automatically,
instead of depending on someone remembering to apply it.
"""
import sys
import os

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.shadow_compare import Comparison, Stat, compare


def frame(real_value, shadow_values):
    """One row per shadow id (and None for real), carrying a `v` column."""
    rows = [{"shadow_id": None, "v": real_value}]
    for shadow_id, value in enumerate(shadow_values):
        rows.append({"shadow_id": float(shadow_id), "v": value})
    return pd.DataFrame(rows)


def mean_v(events):
    values = events["v"].dropna()
    if len(values) == 0:
        return Stat(None, 0)
    return Stat(float(values.mean()), len(values))


def test_reports_the_real_value_and_every_shadow_value():
    result = compare(frame(9.0, [1.0, 2.0, 3.0]), mean_v, shadow_count=3)

    assert isinstance(result, Comparison)
    assert result.real == 9.0
    assert result.shadows == [1.0, 2.0, 3.0]
    assert result.n == 1


def test_percentile_is_the_share_of_shadows_below_the_real_value():
    result = compare(frame(2.5, [1.0, 2.0, 3.0, 4.0]), mean_v, shadow_count=4)

    assert result.percentile == 50.0


def test_a_real_value_above_every_shadow_is_flagged_outside_the_range():
    result = compare(frame(9.0, [1.0, 2.0, 3.0]), mean_v, shadow_count=3)

    assert result.outside_range is True
    assert result.margin == pytest.approx(6.0)


def test_a_real_value_below_every_shadow_is_also_outside_the_range():
    """Under-performing the control is a finding too, not an absence of one."""
    result = compare(frame(0.5, [1.0, 2.0, 3.0]), mean_v, shadow_count=3)

    assert result.outside_range is True
    assert result.margin == pytest.approx(-0.5)


def test_a_real_value_inside_the_spread_is_not_flagged():
    result = compare(frame(2.0, [1.0, 2.0, 3.0]), mean_v, shadow_count=3)

    assert result.outside_range is False
    assert result.margin == 0.0


def test_shadow_summary_statistics_are_reported():
    result = compare(frame(2.0, [1.0, 2.0, 6.0]), mean_v, shadow_count=3)

    assert result.shadow_min == 1.0
    assert result.shadow_median == 2.0
    assert result.shadow_max == 6.0


def test_an_undefined_statistic_propagates_as_none_not_zero():
    """
    A zero denominator is 'we cannot say', not 'the rate is zero'. Zero would
    read as a strong finding.
    """
    empty = pd.DataFrame({"shadow_id": pd.Series(dtype="float64"),
                          "v": pd.Series(dtype="float64")})

    result = compare(empty, mean_v, shadow_count=3)

    assert result.real is None
    assert result.percentile is None
    assert result.outside_range is False
    assert result.n == 0


def test_shadows_with_no_rows_are_skipped_not_counted_as_zero():
    events = frame(9.0, [1.0, 2.0])  # shadow 2 has no rows at all

    result = compare(events, mean_v, shadow_count=3)

    assert result.shadows == [1.0, 2.0]
    assert result.shadows_missing == 1


def test_sample_size_travels_with_the_result():
    """A 100% rate from four events is noise and must not read as a finding."""
    events = pd.DataFrame([
        {"shadow_id": None, "v": 1.0},
        {"shadow_id": None, "v": 1.0},
        {"shadow_id": 0.0, "v": 1.0},
    ])

    assert compare(events, mean_v, shadow_count=1).n == 2


# -- z and above_all_shadows (2026-10-16 breach sweep) ------------------------


def test_z_is_distance_from_the_shadow_mean_in_sample_sds():
    result = Comparison(real=5.0, n=10, shadows=[1.0, 2.0, 3.0])

    assert result.z == pytest.approx(3.0)


def test_z_is_none_with_fewer_than_two_shadows():
    assert Comparison(real=5.0, n=1, shadows=[1.0]).z is None


def test_z_is_none_when_the_shadows_have_no_spread():
    assert Comparison(real=5.0, n=1, shadows=[2.0, 2.0, 2.0]).z is None


def test_z_is_none_when_real_is_undefined():
    assert Comparison(real=None, n=0, shadows=[1.0, 2.0]).z is None


def test_z_uses_only_shadows_that_have_a_value():
    result = compare(frame(9.0, [1.0, 2.0, 3.0]), mean_v, shadow_count=4)

    assert result.shadows_missing == 1
    assert result.z == pytest.approx(7.0)


def test_above_all_shadows_needs_real_strictly_above_the_max():
    assert Comparison(real=5.0, n=1, shadows=[1.0, 2.0, 3.0]).above_all_shadows
    assert not Comparison(real=3.0, n=1, shadows=[1.0, 2.0, 3.0]).above_all_shadows


def test_above_all_shadows_is_false_when_any_shadow_is_missing():
    result = compare(frame(9.0, [1.0, 2.0]), mean_v, shadow_count=3)

    assert result.shadows_missing == 1
    assert result.above_all_shadows is False
    assert result.outside_range is True, "the old flag ignores missing shadows"


def test_above_all_shadows_is_false_when_real_is_undefined():
    assert Comparison(real=None, n=0, shadows=[1.0]).above_all_shadows is False
