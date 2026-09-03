"""
The label groups every statistic is reported across.

Pooling can wash out a real effect: 41% on halfway levels and 22% everywhere
else averages to something that looks dead. So nothing is reported pooled
alone.
"""
import sys
import os

import pandas as pd

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.groups import (
    GROUPINGS, add_ring_bin, iter_groups,
)


def frame():
    return pd.DataFrame({
        "shadow_id": [None, None, 0.0, 0.0],
        "level_source": ["center", "sun", "center", "sun"],
        "level_degree": [0, 90, 0, 90],
        "level_sub_index": [1, None, 1, None],
        "level_is_halfway": [True, False, True, False],
        "level_ring": [3, 47, 3, 47],
        "level_kind": ["sub", "major", "sub", "major"],
    })


def test_the_six_spec_groupings_are_all_present():
    assert set(GROUPINGS) == {
        "level_source", "level_degree", "level_sub_index",
        "level_is_halfway", "level_ring_bin", "level_kind",
    }


def test_ring_bin_buckets_rings_so_groups_are_not_one_row_each():
    binned = add_ring_bin(frame(), width=10)

    assert list(binned["level_ring_bin"]) == ["0-9", "40-49", "0-9", "40-49"]


def test_iter_groups_yields_a_frame_per_distinct_value():
    binned = add_ring_bin(frame())

    found = dict(iter_groups(binned, "level_source"))

    assert set(found) == {"center", "sun"}
    assert len(found["center"]) == 2, "real and shadow rows must stay together"


def test_each_group_frame_keeps_both_real_and_shadow_rows():
    """
    compare() splits real from shadow itself. A grouping that dropped the
    shadows would silently remove the control.
    """
    binned = add_ring_bin(frame())

    _, group = next(iter(iter_groups(binned, "level_source")))

    assert group["shadow_id"].isna().any()
    assert group["shadow_id"].notna().any()


def test_null_group_values_become_their_own_labelled_group():
    """
    level_sub_index is null for majors. Dropping nulls would silently exclude
    every major level from the sub-index breakdown rather than showing them.
    """
    binned = add_ring_bin(frame())

    found = dict(iter_groups(binned, "level_sub_index"))

    assert "none" in found
    assert len(found["none"]) == 2


def test_groups_come_back_in_a_stable_order():
    """The report is diffed across runs, so ordering must not float."""
    binned = add_ring_bin(frame())

    first = [label for label, _ in iter_groups(binned, "level_source")]
    second = [label for label, _ in iter_groups(binned, "level_source")]

    assert first == second == sorted(first)
