"""
The two write-ups of the breach sweep: the RELIANCE results with the
pre-registered choice, and the one-look AAPL verdict.

Both are rendered from numbers only, so a test pins what each says for a
given outcome - the null, the caveats, the order - before the real run.
"""

from typing import Dict, List, Mapping, Optional, Tuple

from study_tool.mining.breach_sweep import (
    CONFIRMATION_GROUPS, RULE_ORDER, RULES_BY_NAME, SPEC_PATH,
    STRONG_PASS_GROUPS, TIE_WINDOW, RuleScore, Selection, Verdict, group_name,
)
from study_tool.mining.regression_gate import GateResult
from study_tool.mining.shadow_compare import Comparison

COMPARISON_HEAD = ("| {first} | real | n | shadow min | shadow max | missing "
                   "| above all | z |\n|---|---|---|---|---|---|---|---|")


def _num(value: Optional[float], places: int = 4) -> str:
    """None renders as a dash; 0.0000 would read as a measured zero."""
    return "-" if value is None else f"{value:.{places}f}"


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"


def _comparison_table(first: str,
                      rows: List[Tuple[str, Comparison]]) -> List[str]:
    lines = [COMPARISON_HEAD.format(first=first)]
    for label, c in rows:
        lines.append(
            f"| {label} | {_num(c.real)} | {c.n} | {_num(c.shadow_min)} | "
            f"{_num(c.shadow_max)} | {c.shadows_missing} | "
            f"{_yes(c.above_all_shadows)} | {_num(c.z, 2)} |")
    return lines


def _dropped_table(scores: List[RuleScore]) -> List[str]:
    lines = ["| rule | real dropped | targeted n (raced, timeouts included) "
             "| shadow min | shadow max | outside shadow range "
             "| entry-only dropped (real) |",
             "|---|---|---|---|---|---|---|"]
    for s in scores:
        d = s.dropped
        lines.append(
            f"| {s.rule} | {_num(d.real)} | {d.n} | {_num(d.shadow_min)} | "
            f"{_num(d.shadow_max)} | {_yes(d.outside_range)} | "
            f"{_num(s.entry_dropped.real)} |")
    return lines


def _groups_table(score: RuleScore) -> List[str]:
    names = [group_name(c, l) for c, l in CONFIRMATION_GROUPS]
    return _comparison_table(
        "group", [(name, score.groups[name]) for name in names
                  if name in score.groups])


def render_sweep_results(scores: Mapping[str, RuleScore],
                         selection: Selection, gate: GateResult,
                         context: Dict) -> str:
    ordered = [scores[name] for name in RULE_ORDER if name in scores]
    lines = [
        "# Gann Breach Definition Sweep - Results",
        "",
        f"Spec: `{SPEC_PATH}`.",
        "RELIANCE is explore-only (its holdout was spent 2026-09-03), so "
        "every row of each corpus is read (`--slice all`). Nothing here is "
        "confirmed; AAPL is the confirmation.",
        "",
        "## Run",
        "",
        f"- generated: {context['generated']}",
        f"- bars: `{context['cache_dir']}` (no fetching)",
        f"- gate reference: `{context['reference']}`",
    ]
    for name in RULE_ORDER:
        if name in context["corpora"]:
            lines.append(f"- {name}: `{context['corpora'][name]}`")

    lines += [
        "",
        "## Regression gate - close2 rebuild against the existing corpus",
        "",
        f"**{'PASSED' if gate.passed else 'FAILED'}** - {gate.reason}",
        "",
        "## Selection (pre-registered)",
        "",
    ]
    if selection.chosen is None:
        lines.append("**Null: no breach rule is above all shadows on the "
                     "pooled lag-free reach rate. AAPL is not built.**")
    else:
        rule = RULES_BY_NAME[selection.chosen]
        lines.append(f"**Chosen rule: `{rule.name}`** (breach_mode "
                     f"{rule.breach_mode}, confirmation_closes "
                     f"{rule.confirmation_closes})")
    lines += [
        "",
        selection.reason,
        "",
        f"- eligible (above all shadows): "
        f"{', '.join(selection.eligible) or 'none'}",
        f"- tie candidates (z within {TIE_WINDOW} of the best): "
        f"{', '.join(selection.candidates) or 'none'}",
        "",
        "Pooled lag-free reach rate, real against the shadows:",
        "",
    ]
    lines += _comparison_table("rule", [(s.rule, s.lag_free) for s in ordered])

    lines += [
        "",
        "## Dropped share - real against shadow",
        "",
        "Rows removed by either lag-free filter over targeted rows. If the "
        "real share is outside the shadow range, the filtered real and "
        "shadow sets are not like-for-like, and a pass on them reads as "
        "\"pass, selection differs\".",
        "",
    ]
    lines += _dropped_table(ordered)

    lines += ["", "## Plain reach_next_rate (the old, lag-laden statistic, "
              "for reading)", ""]
    lines += _comparison_table("rule", [(s.rule, s.reach_next) for s in ordered])

    lines += ["", "## Touch density - the fairness check", ""]
    lines += _comparison_table("rule",
                               [(s.rule, s.touch_density) for s in ordered])

    lines += ["", "## The 13 pre-declared groups, lag-free reach rate", ""]
    for s in ordered:
        lines += [f"### {s.rule}", ""]
        lines += _groups_table(s)
        lines.append("")
    return "\n".join(lines)


def render_aapl_results(score: RuleScore, verdict: Verdict,
                        context: Dict) -> str:
    lag, dropped = score.lag_free, score.dropped
    lines = [
        "# Gann AAPL Fresh Holdout - Results",
        "",
        f"Spec: `{SPEC_PATH}`. Read once.",
        f"Rule `{context['rule']}` (breach_mode {context['breach_mode']}, "
        f"confirmation_closes {context['confirmation_closes']}) from "
        f"`{context['choice']}`. Scale x{context['price_scale']}, "
        f"{context['shadow_count']} shadows, every row (`--slice all`, "
        f"{context['rows']} rows).",
        "",
        "## Touch density - read first",
        "",
    ]
    lines += _comparison_table("statistic",
                               [("touch_density", score.touch_density)])
    lines.append("")
    if verdict.touch_busier_than_all_shadows:
        lines.append("**The real ladder is touched more than every shadow.** "
                     "A reach statistic can be lifted by that exposure rather "
                     "than by the levels; read the verdict beside it.")
    else:
        lines.append("Real touch density is not above every shadow that has "
                     "one.")
    if verdict.touch_shadows_missing:
        lines.append(f"{verdict.touch_shadows_missing} shadows have no touch "
                     "density (no touches), so they are left out of that "
                     "comparison rather than counted as beaten or unbeaten.")

    caveat = ("; outside the shadow range, so the filtered real and shadow "
              "sets are not like-for-like" if verdict.selection_differs
              else "; inside the shadow range")
    lines += [
        "",
        "## Verdict (pre-registered)",
        "",
        f"**{verdict.label}**",
        "",
        f"- pooled lag-free reach rate: real {_num(lag.real)} (n={lag.n}), "
        f"shadow max {_num(lag.shadow_max)}, missing shadows "
        f"{lag.shadows_missing}, z {_num(lag.z, 2)}",
        f"- groups above all shadows: {verdict.groups_above} of "
        f"{len(CONFIRMATION_GROUPS)} (strong pass needs {STRONG_PASS_GROUPS})",
        f"- dropped share: real {_num(dropped.real)} against shadows "
        f"{_num(dropped.shadow_min)} to {_num(dropped.shadow_max)}{caveat}",
        f"- entry-only dropped share (real): {_num(score.entry_dropped.real)}",
        "",
        "## Pooled",
        "",
    ]
    lines += _comparison_table("statistic", [
        ("lag_free_reach_rate", score.lag_free),
        ("dropped_share", score.dropped),
        ("entry_dropped_share", score.entry_dropped),
    ])
    lines += [
        "",
        "## The 13 pre-declared groups, lag-free reach rate",
        "",
        "Declared for the 2026-09-03 RELIANCE confirmation. At x6, "
        "ring_bin=10-19 covers AAPL only below about $253.5, so the pooled "
        "test is the primary one. A group with no rows or any missing shadow "
        "is not above all shadows.",
        "",
    ]
    lines += _groups_table(score)
    lines += [
        "",
        "Nothing else was computed on AAPL: only the touch density, the "
        "pooled lag-free reach rate, the 13 groups, the dropped and "
        "entry-only dropped shares and the verdict above. The scoring was "
        "run in registered-only mode, which does not evaluate any other "
        "statistic, so the holdout is spent on exactly these tests.",
        f"Corpus: `{context['corpus']}`",
        f"Generated: {context['generated']}",
        "",
    ]
    return "\n".join(lines)
