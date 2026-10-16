"""
The mining report.

What comes out of this phase is a shortlist of candidates to test later, not a
set of results. A table of percentages invites being read as findings, so the
document says what it is in its own header.

Order matters. The fairness check is first, because if the real ladder and the
shadows are touched at very different rates then every other number below it
is suspect and should not be read at all.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from study_tool.mining.shadow_compare import Comparison

HEADER = """# Gann Corpus Mining Report

**These are candidates, not findings.** Nothing below is confirmed. Every
number here comes from the explore slice, which the search has already seen,
so any group that looks strong is a hypothesis to test against the holdout -
once, in a batch, with the result recorded whichever way it falls.

No multiple-comparison correction is applied and none is needed, because
nothing here concludes. Correction belongs at holdout confirmation, against a
shortlist declared before that data is opened.
"""

_DOTZERO = re.compile(r'^(\d+)\.0$')
_PLAIN_INT = re.compile(r'^-?\d+$')
_RANGE = re.compile(r'^(-?\d+)-(-?\d+)$')


def display_label(label: str) -> str:
    """
    A group label as a human should read it.

    level_sub_index mixes ints and nulls, which pandas upcasts to float64,
    so iter_groups yields "1.0" rather than "1". This strips that suffix.
    The breach sweep matches its pre-declared groups through this too.
    """
    match = _DOTZERO.match(label)
    return match.group(1) if match else label


@dataclass(frozen=True)
class GroupResult:
    grouping: str
    label: str
    statistic: str
    comparison: Comparison

    @property
    def display_label(self) -> str:
        """
        The label as a human should read it.

        level_sub_index mixes ints and nulls, which pandas upcasts to
        float64, so iter_groups yields "1.0" rather than "1". Strip that
        suffix here rather than in groups.py, which Task 7 already closed.
        """
        return display_label(self.label)

    @property
    def name(self) -> str:
        return f"{self.grouping}={self.display_label}"

    @property
    def sort_key(self) -> Tuple[int, object]:
        """
        Numeric-looking labels sort numerically; everything else sorts as a
        string. A plain sort would put "180" before "45", and would print
        level_degree in a confusing, non-numeric order.
        """
        label = self.display_label
        if _PLAIN_INT.match(label):
            return (0, int(label))
        range_match = _RANGE.match(label)
        if range_match:
            return (0, int(range_match.group(1)))
        return (1, label)


def _num(value: Optional[float], places: int = 4) -> str:
    """None renders as a dash. 0.0000 would read as a measured zero."""
    return "-" if value is None else f"{value:.{places}f}"


def _comparison_row(name: str, comparison: Comparison) -> str:
    return (
        f"| {name} | {_num(comparison.real)} | {comparison.n} | "
        f"{_num(comparison.shadow_min)} | {_num(comparison.shadow_median)} | "
        f"{_num(comparison.shadow_max)} | {_num(comparison.percentile, 1)} |"
    )


TABLE_HEAD = ("| group | real | n | shadow min | shadow median | "
              "shadow max | pct |\n|---|---|---|---|---|---|---|")


def _fairness_section(context: Dict) -> str:
    touch = context["touch_density"]
    lines = [
        "## Fairness check - read this first",
        "",
        "Touches per bar, real against shadow. These should be close. A large",
        "gap means the two ladders get different exposure to price, and every",
        "comparison below it is measuring that gap rather than the levels.",
        "",
        TABLE_HEAD,
        _comparison_row("touch_density", touch),
        "",
    ]
    return "\n".join(lines)


def _context_section(context: Dict) -> str:
    return "\n".join([
        "## Run",
        "",
        f"- slice: {context.get('slice', 'explore')}",
        f"- corpus: `{context['corpus_dir']}`",
        f"- symbol: {context['symbol']}, interval {context['interval']}, "
        f"scale x{context['price_scale']}",
        f"- shadows: {context['shadow_count']}",
        f"- {context.get('slice', 'explore')} events used: "
        f"{context['explore_events']}",
        f"- dropped to the boundary buffer: {context['dropped_to_buffer']} "
        f"(events within {context['buffer_bars']} bars of holdout boundary "
        f"bar {context['boundary_bar_index']}, whose outcomes would have been "
        "decided by holdout price action)",
        "",
    ])


def _per_group_section(results: List[GroupResult]) -> str:
    lines = ["## Per group", ""]
    for statistic in sorted({r.statistic for r in results}):
        lines += [f"### {statistic}", "", TABLE_HEAD]
        rows = [r for r in results if r.statistic == statistic]
        for result in sorted(rows, key=lambda r: (r.grouping, r.sort_key)):
            lines.append(_comparison_row(result.name, result.comparison))
        lines.append("")
    return "\n".join(lines)


def _shortlist_section(results: List[GroupResult]) -> str:
    outside = [r for r in results if r.comparison.outside_range]
    outside.sort(key=lambda r: abs(r.comparison.margin), reverse=True)

    lines = [
        "## Shortlist",
        "",
        "Groups whose real value falls outside the **entire** shadow range,",
        "sorted by how far outside. Sample size is in the table because a",
        "rate built on a handful of events lands outside the range easily and",
        "means nothing.",
        "",
        "| group | statistic | real | n | shadow min | shadow max | margin |",
        "|---|---|---|---|---|---|---|",
    ]
    if not outside:
        lines.append("| _nothing fell outside the shadow range_ | | | | | | |")
    for result in outside:
        c = result.comparison
        lines.append(
            f"| {result.name} | {result.statistic} | {_num(c.real)} | "
            f"n={c.n} | {_num(c.shadow_min)} | {_num(c.shadow_max)} | "
            f"{_num(c.margin)} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_report(results: List[GroupResult], context: Dict) -> str:
    """
    The whole report as Markdown.

    Deterministic: every section sorts its rows, so two runs over the same
    corpus diff to nothing and a real change stands out.
    """
    return "\n".join([
        HEADER,
        _context_section(context),
        _fairness_section(context),
        _per_group_section(results),
        _shortlist_section(results),
    ])
