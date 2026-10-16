"""
The close2 regression gate: does the rebuilt corpus reproduce the old one?
"""
import sys
import os

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.regression_gate import (
    GateResult, check_regression, compare_event_tables,
)


def events():
    return pd.DataFrame({
        "bar_index": [0, 1, 1, 2],
        "event_type": ["LADDER_TOUCH", "LADDER_CROSS", "LADDER_TOUCH",
                       "LADDER_BREACH_CONFIRMED"],
        "level_price": [1306.0, 1306.0, 1308.25, 1306.0],
        "shadow_id": [None, None, 0.0, None],
        "angle_name": [None, None, None, None],     # an Arrow null column
        "outcome": [None, None, None, "x"],
    })


def write(frame, path):
    frame.to_parquet(path, index=False)
    return path


def test_identical_tables_pass(tmp_path):
    result = check_regression(write(events(), tmp_path / "a.parquet"),
                              write(events(), tmp_path / "b.parquet"))

    assert isinstance(result, GateResult)
    assert result.passed is True
    assert "4 rows" in result.reason


def test_row_order_does_not_matter(tmp_path):
    shuffled = events().iloc[[3, 1, 0, 2]].reset_index(drop=True)

    result = check_regression(write(events(), tmp_path / "a.parquet"),
                              write(shuffled, tmp_path / "b.parquet"))

    assert result.passed is True


def test_one_changed_value_fails_and_names_the_column(tmp_path):
    changed = events()
    changed.loc[2, "level_price"] = 1308.5

    result = check_regression(write(events(), tmp_path / "a.parquet"),
                              write(changed, tmp_path / "b.parquet"))

    assert result.passed is False
    assert "'level_price'" in result.reason


def test_every_differing_column_is_named(tmp_path):
    changed = events()
    changed.loc[2, "level_price"] = 1308.5
    changed.loc[3, "outcome"] = "y"

    result = check_regression(write(events(), tmp_path / "a.parquet"),
                              write(changed, tmp_path / "b.parquet"))

    assert result.passed is False
    assert "['level_price', 'outcome']" in result.reason


def test_a_slice_only_difference_still_fails_and_names_slice(tmp_path):
    reference = events().assign(slice=["explore", "explore", "holdout",
                                       "holdout"])
    relabelled = reference.copy()
    relabelled.loc[1, "slice"] = "holdout"

    result = check_regression(write(reference, tmp_path / "a.parquet"),
                              write(relabelled, tmp_path / "b.parquet"))

    assert result.passed is False
    assert "['slice']" in result.reason


def test_an_extra_column_fails(tmp_path):
    extra = events()
    extra["extra"] = 1

    result = check_regression(write(events(), tmp_path / "a.parquet"),
                              write(extra, tmp_path / "b.parquet"))

    assert result.passed is False
    assert "only in rebuilt ['extra']" in result.reason


def test_a_missing_row_fails(tmp_path):
    result = check_regression(write(events(), tmp_path / "a.parquet"),
                              write(events().iloc[1:], tmp_path / "b.parquet"))

    assert result.passed is False
    assert "row count" in result.reason


def test_a_changed_type_fails(tmp_path):
    floats = events()
    floats["bar_index"] = floats["bar_index"].astype(float)

    result = check_regression(write(events(), tmp_path / "a.parquet"),
                              write(floats, tmp_path / "b.parquet"))

    assert result.passed is False
    assert "'bar_index'" in result.reason


def test_schema_metadata_is_ignored(tmp_path):
    bare = pa.Table.from_pandas(events(), preserve_index=False) \
        .replace_schema_metadata(None)
    pq.write_table(bare, tmp_path / "b.parquet")

    result = check_regression(write(events(), tmp_path / "a.parquet"),
                              tmp_path / "b.parquet")

    assert result.passed is True


def test_nan_and_null_compare_equal():
    with_nan = pa.table({"x": pa.array([1.0, float("nan")])})
    with_null = pa.table({"x": pa.array([1.0, None], pa.float64())})

    assert compare_event_tables(with_nan, with_null).passed is True


def test_a_changed_mid_table_column_does_not_name_the_later_ones():
    """Ties in an early column reorder rows; later columns must not look wrong."""
    reference = pa.table({"a": [1, 1, 1], "price": [5.0, 6.0, 7.0],
                          "later": ["x", "y", "z"]})
    rebuilt = pa.table({"a": [1, 1, 1], "price": [8.0, 6.0, 7.0],
                        "later": ["x", "y", "z"]})

    result = compare_event_tables(reference, rebuilt)

    assert result.passed is False
    assert "['price']" in result.reason
    assert "later" not in result.reason


def test_same_values_paired_differently_is_reported_as_pairing():
    reference = pa.table({"a": [1, 2], "b": ["x", "y"]})
    rebuilt = pa.table({"a": [1, 2], "b": ["y", "x"]})

    result = compare_event_tables(reference, rebuilt)

    assert result.passed is False
    assert "every column's values match" in result.reason
    assert "pair up differently" in result.reason


def test_every_mismatched_type_is_named():
    reference = pa.table({"a": [1, 2], "b": [1, 2], "c": [1, 2]})
    rebuilt = pa.table({"a": [1.0, 2.0], "b": [1, 2], "c": ["1", "2"]})

    result = compare_event_tables(reference, rebuilt)

    assert result.passed is False
    assert "'a'" in result.reason and "'c'" in result.reason
    assert "'b'" not in result.reason
