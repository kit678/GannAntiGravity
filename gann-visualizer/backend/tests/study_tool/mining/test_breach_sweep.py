"""
The pre-registered pieces of the breach sweep, on hand-made inputs: which
rule wins, which rows each of the 13 groups holds, and what gets scored.
"""
import sys
import os

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.breach_sweep import (
    CONFIRMATION_GROUPS, RULE_ORDER, RULES, RULES_BY_NAME, BreachRule,
    confirmation_groups, group_name, score_rule, select_rule,
)
from study_tool.mining.shadow_compare import Comparison


def test_the_four_rules_in_tie_order():
    assert RULE_ORDER == ("close1", "wick1", "close2", "close3")
    assert RULES_BY_NAME["wick1"] == BreachRule("wick1", "wick", 1)
    assert RULES_BY_NAME["close3"] == BreachRule("close3", "close", 3)
    assert len(RULES) == 4


def test_there_are_thirteen_distinct_confirmation_groups():
    assert len(CONFIRMATION_GROUPS) == 13
    assert len(set(CONFIRMATION_GROUPS)) == 13


def label_frame():
    return pd.DataFrame({
        "shadow_id": [None, None, None],
        "level_source": ["center", "moon", "sun"],
        "level_ring_bin": ["10-19", "20-29", "10-19"],
        "level_kind": ["sub", "major", "sub"],
        "level_is_halfway": [False, False, True],
        "level_degree": [90, 0, 225],
        "level_sub_index": [5.0, None, 4.0],
    })


def test_groups_match_labels_the_way_the_report_prints_them():
    groups = dict(confirmation_groups(label_frame()))

    assert len(groups) == 13
    assert len(groups["level_sub_index=5"]) == 1
    assert len(groups["level_degree=90"]) == 1
    assert len(groups["level_is_halfway=True"]) == 1
    assert len(groups["level_ring_bin=10-19"]) == 2
    assert len(groups["level_degree=135"]) == 0


def test_a_missing_column_gives_an_empty_group_not_an_error():
    groups = dict(confirmation_groups(label_frame().drop(columns="level_ring_bin")))

    assert len(groups["level_ring_bin=10-19"]) == 0


def breach_row(shadow_id, outcome, hit=False, beyond=True):
    return {"event_type": "LADDER_BREACH_CONFIRMED", "bar_index": 0,
            "shadow_id": shadow_id, "reach_outcome": outcome,
            "target_hit_before_entry": hit, "entry_beyond_level": beyond,
            "target_already_hit": hit, "level_source": "center",
            "level_degree": 90, "level_sub_index": 5.0, "level_kind": "sub",
            "level_is_halfway": False, "level_ring_bin": "10-19"}


def scored_events():
    rows = [breach_row(None, "REACHED") for _ in range(3)]
    rows += [breach_row(None, "STOPPED"), breach_row(None, "REACHED", hit=True)]
    for shadow in (0.0, 1.0):
        rows += [breach_row(shadow, "REACHED"), breach_row(shadow, "STOPPED")]
    return pd.DataFrame(rows)


def test_score_rule_reads_pooled_and_group_statistics():
    score = score_rule("close2", scored_events(), shadow_count=2)

    assert score.rule == "close2"
    assert score.lag_free.real == 0.75
    assert score.lag_free.shadows == [0.5, 0.5]
    assert score.lag_free.above_all_shadows is True
    assert score.reach_next.real == 0.8
    assert score.dropped.real == 0.2
    assert score.dropped.outside_range is True
    assert score.entry_dropped.real == 0.0
    assert len(score.groups) == 13
    assert score.groups["level_source=center"].real == 0.75
    assert score.groups["level_source=moon"].real is None
    assert score.groups["level_source=moon"].shadows_missing == 2


def z_comparison(z, missing=0):
    """Shadows -1, 0, 1 have mean 0 and sample sd 1, so real == z."""
    return Comparison(real=z, n=100, shadows=[-1.0, 0.0, 1.0],
                      shadows_missing=missing)


def inside():
    return Comparison(real=0.5, n=100, shadows=[-1.0, 0.0, 1.0])


def test_the_eligible_rule_with_the_largest_z_wins():
    selection = select_rule({"close1": z_comparison(2.0),
                             "wick1": z_comparison(3.0),
                             "close2": z_comparison(2.5),
                             "close3": z_comparison(2.2)})

    assert selection.chosen == "wick1"
    assert selection.candidates == ["wick1"]
    assert selection.eligible == ["close1", "wick1", "close2", "close3"]


def test_a_rule_with_a_missing_shadow_is_not_eligible():
    selection = select_rule({"close1": z_comparison(5.0, missing=1),
                             "close2": z_comparison(2.0)})

    assert selection.chosen == "close2"
    assert selection.eligible == ["close2"]


def test_a_rule_inside_the_shadow_range_is_not_eligible():
    selection = select_rule({"close1": inside(), "close3": z_comparison(2.0)})

    assert selection.eligible == ["close3"]


def test_ties_within_the_window_go_to_the_earliest_rule():
    selection = select_rule({"close1": z_comparison(2.95),
                             "close3": z_comparison(3.0)})

    assert selection.chosen == "close1"
    assert selection.candidates == ["close1", "close3"]


def test_a_z_outside_the_window_is_not_a_candidate():
    selection = select_rule({"close1": z_comparison(2.85),
                             "close3": z_comparison(3.0)})

    assert selection.chosen == "close3"
    assert selection.candidates == ["close3"]


def test_close_comes_before_wick_and_wick_before_close2_in_a_tie():
    assert select_rule({"close1": z_comparison(3.0),
                        "wick1": z_comparison(3.0)}).chosen == "close1"
    assert select_rule({"wick1": z_comparison(2.0),
                        "close2": z_comparison(2.0)}).chosen == "wick1"


def test_no_eligible_rule_is_a_null():
    selection = select_rule({name: inside() for name in RULE_ORDER})

    assert selection.chosen is None
    assert selection.eligible == []
    assert "null" in selection.reason


def test_z_is_reported_for_every_rule():
    selection = select_rule({"close1": inside(), "close2": z_comparison(2.0)})

    assert selection.z == {"close1": pytest.approx(0.5),
                           "close2": pytest.approx(2.0)}


def test_an_unknown_rule_name_is_refused():
    with pytest.raises(ValueError, match="close4"):
        select_rule({"close4": z_comparison(2.0)})


def test_an_eligible_rule_with_undefined_z_is_refused():
    no_spread = Comparison(real=2.0, n=5, shadows=[1.0, 1.0])
    assert no_spread.above_all_shadows and no_spread.z is None

    with pytest.raises(ValueError, match="z is undefined"):
        select_rule({"close1": no_spread})
