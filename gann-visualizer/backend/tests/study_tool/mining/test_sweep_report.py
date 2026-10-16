"""
The RELIANCE results document and the AAPL verdict document, rendered from
numbers only, so what each says for a given outcome is pinned before the run.
"""
import sys
import os

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.breach_sweep import (
    CONFIRMATION_GROUPS, RULE_ORDER, RuleScore, Selection, Verdict, group_name,
)
from study_tool.mining.regression_gate import GateResult
from study_tool.mining.shadow_compare import Comparison
from study_tool.mining.sweep_report import (
    render_aapl_results, render_sweep_results,
)


def comparison(real=0.6):
    return Comparison(real=real, n=100, shadows=[0.5, 0.55])


def rule_score(rule):
    groups = {group_name(c, l): comparison() for c, l in CONFIRMATION_GROUPS}
    return RuleScore(rule=rule, lag_free=comparison(), dropped=comparison(0.3),
                     entry_dropped=comparison(0.0), reach_next=comparison(),
                     already_hit=comparison(), touch_density=comparison(),
                     groups=groups)


def scores():
    return {name: rule_score(name) for name in RULE_ORDER}


def chosen():
    return Selection(chosen="close1", eligible=["close1"],
                     candidates=["close1"], z={n: 2.0 for n in RULE_ORDER},
                     reason="close1 chosen: best z 2.000")


def null():
    return Selection(chosen=None, eligible=[], candidates=[],
                     z={n: 0.1 for n in RULE_ORDER},
                     reason="no breach rule is above all shadows; null")


def sweep_context():
    return {"generated": "2026-10-16 12:00", "cache_dir": "bars",
            "reference": "ref/events.parquet",
            "corpora": {n: f"out/reliance_5m_x1_{n}" for n in RULE_ORDER}}


def gate():
    return GateResult(True, "4 rows match on all 6 columns", 4)


def test_sweep_results_put_the_gate_before_the_selection():
    text = render_sweep_results(scores(), chosen(), gate(), sweep_context())

    assert text.index("## Regression gate") < text.index("## Selection")
    assert "**PASSED**" in text
    assert "Chosen rule: `close1`" in text


def test_a_null_sweep_says_aapl_is_not_built():
    text = render_sweep_results(scores(), null(), gate(), sweep_context())

    assert "AAPL is not built" in text
    assert "Chosen rule" not in text


def test_sweep_results_report_every_rule_and_every_group():
    text = render_sweep_results(scores(), chosen(), gate(), sweep_context())

    for name in RULE_ORDER:
        assert f"### {name}" in text
        assert f"| {name} |" in text
    for column, label in CONFIRMATION_GROUPS:
        assert f"| {group_name(column, label)} |" in text
    for heading in ("## Dropped share", "## Plain reach_next_rate",
                    "## Touch density"):
        assert heading in text


def test_sweep_results_render_the_same_twice():
    first = render_sweep_results(scores(), chosen(), gate(), sweep_context())
    assert first == render_sweep_results(scores(), chosen(), gate(),
                                         sweep_context())


def aapl_context():
    return {"rule": "close1", "breach_mode": "close", "confirmation_closes": 1,
            "choice": "choice.json", "corpus": "out/aapl_5m_x6",
            "price_scale": 6, "shadow_count": 50,
            "rows": 1234, "generated": "2026-10-17 09:00"}


def verdict(label="pass", differs=False, busier=False):
    return Verdict(label=label, passed=label != "fail",
                   strong=label.startswith("strong"), groups_above=3,
                   selection_differs=differs,
                   touch_busier_than_all_shadows=busier)


def test_aapl_results_read_touch_density_first():
    text = render_aapl_results(rule_score("close1"), verdict(), aapl_context())

    assert text.index("## Touch density") < text.index("## Verdict")
    assert "**pass**" in text
    assert "3 of 13" in text
    assert "Full mining report" not in text


def test_aapl_results_flag_a_busier_real_ladder():
    text = render_aapl_results(rule_score("close1"), verdict(busier=True),
                               aapl_context())

    assert "touched more than every shadow" in text


def test_aapl_results_carry_the_dropped_share_caveat():
    text = render_aapl_results(rule_score("close1"),
                               verdict("pass, selection differs", differs=True),
                               aapl_context())

    assert "**pass, selection differs**" in text
    assert "not like-for-like" in text


FORBIDDEN_ON_AAPL = ("reach_next_rate", "already_hit", "hold_rate")


def registered_score(rule):
    return RuleScore(rule=rule, lag_free=comparison(), dropped=comparison(0.3),
                     entry_dropped=comparison(0.0),
                     touch_density=comparison(),
                     groups={group_name(c, l): comparison()
                             for c, l in CONFIRMATION_GROUPS})


def test_aapl_results_hold_none_of_the_unregistered_statistics():
    text = render_aapl_results(registered_score("close1"), verdict(),
                               aapl_context())

    for forbidden in FORBIDDEN_ON_AAPL:
        assert forbidden not in text


def test_aapl_results_do_not_print_statistics_even_if_the_score_carries_them():
    text = render_aapl_results(rule_score("close1"), verdict(), aapl_context())

    for forbidden in FORBIDDEN_ON_AAPL:
        assert forbidden not in text


def test_aapl_results_name_exactly_the_registered_statistics():
    text = render_aapl_results(registered_score("close1"), verdict(),
                               aapl_context())

    assert "touch_density" in text
    assert "lag_free_reach_rate" in text
    assert "dropped_share" in text
    assert "entry_dropped_share" in text
    assert text.index("touch_density") < text.index("lag_free_reach_rate")
    assert "Nothing else was computed" in text


def test_aapl_results_report_touch_shadows_with_no_value_separately():
    v = Verdict(label="pass", passed=True, strong=False, groups_above=3,
                selection_differs=False, touch_busier_than_all_shadows=True,
                touch_shadows_missing=4)

    text = render_aapl_results(registered_score("close1"), v, aapl_context())

    assert "touched more than every shadow" in text
    assert "4 shadows have no touch density" in text


def test_aapl_results_do_not_call_a_missing_touch_shadow_a_non_exceedance():
    v = Verdict(label="pass", passed=True, strong=False, groups_above=3,
                selection_differs=False, touch_busier_than_all_shadows=False,
                touch_shadows_missing=4)

    text = render_aapl_results(registered_score("close1"), v, aapl_context())

    assert "4 shadows have no touch density" in text
