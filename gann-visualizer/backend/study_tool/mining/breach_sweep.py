"""
The breach definition sweep, as pure functions.

Spec: docs/superpowers/specs/2026-10-16-gann-breach-definition-sweep-design.md

Everything that decides an outcome - which breach rule is chosen, whether
AAPL passes - is here and takes only events frames or comparisons, so the
pre-registered rules are tested on hand-made inputs before any real corpus
is read.
"""

from dataclasses import dataclass
from typing import Dict, List, Mapping, NamedTuple, Optional, Tuple

import pandas as pd

from study_tool.mining.groups import NULL_LABEL
from study_tool.mining.report import display_label
from study_tool.mining.shadow_compare import Comparison, compare
from study_tool.mining.statistics import (
    already_hit_share, dropped_share, entry_dropped_share,
    lag_free_reach_rate, reach_next_rate, touch_density_fn,
)

SPEC_PATH = ("docs/superpowers/specs/"
             "2026-10-16-gann-breach-definition-sweep-design.md")


class BreachRule(NamedTuple):
    name: str
    breach_mode: str
    confirmation_closes: int


# In tie order: fewer closes first; close before wick because close is the
# house rule.
RULES: Tuple[BreachRule, ...] = (
    BreachRule("close1", "close", 1),
    BreachRule("wick1", "wick", 1),
    BreachRule("close2", "close", 2),
    BreachRule("close3", "close", 3),
)
RULE_ORDER: Tuple[str, ...] = tuple(rule.name for rule in RULES)
RULES_BY_NAME: Dict[str, BreachRule] = {rule.name: rule for rule in RULES}
TIE_WINDOW = 0.1
STRONG_PASS_GROUPS = 7

# Pre-declared for the 2026-09-03 RELIANCE confirmation; kept because they
# were declared in advance, not because they suit the lag-free statistic.
CONFIRMATION_GROUPS: Tuple[Tuple[str, str], ...] = (
    ("level_source", "center"),
    ("level_source", "moon"),
    ("level_source", "sun"),
    ("level_ring_bin", "10-19"),
    ("level_kind", "sub"),
    ("level_kind", "major"),
    ("level_is_halfway", "False"),
    ("level_is_halfway", "True"),
    ("level_degree", "0"),
    ("level_degree", "90"),
    ("level_degree", "135"),
    ("level_degree", "225"),
    ("level_sub_index", "5"),
)


def group_name(column: str, label: str) -> str:
    return f"{column}={label}"


def confirmation_groups(events: pd.DataFrame) -> List[Tuple[str, pd.DataFrame]]:
    """
    (name, rows) for each of the 13 groups, real and shadow rows together.

    Labels are matched the way the report prints them. A group with no rows
    comes back empty rather than missing: compare() then counts every shadow
    missing, and the group cannot be above all shadows.
    """
    labels: Dict[str, pd.Series] = {}
    out: List[Tuple[str, pd.DataFrame]] = []
    for column, label in CONFIRMATION_GROUPS:
        name = group_name(column, label)
        if column not in events.columns:
            out.append((name, events.iloc[0:0]))
            continue
        if column not in labels:
            labels[column] = events[column].map(
                lambda v: NULL_LABEL if pd.isna(v) else display_label(str(v)))
        out.append((name, events[labels[column] == label]))
    return out


@dataclass(frozen=True)
class RuleScore:
    rule: str
    lag_free: Comparison
    dropped: Comparison
    entry_dropped: Comparison
    reach_next: Comparison
    already_hit: Comparison
    touch_density: Comparison
    groups: Dict[str, Comparison]


def score_rule(rule: str, events: pd.DataFrame, shadow_count: int) -> RuleScore:
    """
    Every number the sweep reads for one breach rule, pooled and per group.

    `events` must already carry the reach race and level_ring_bin -
    mine_gann_corpus.load_scored_events supplies both.
    """
    bar_count = int(events["bar_index"].nunique())

    def pooled(statistic) -> Comparison:
        return compare(events, statistic, shadow_count=shadow_count)

    return RuleScore(
        rule=rule,
        lag_free=pooled(lag_free_reach_rate),
        dropped=pooled(dropped_share),
        entry_dropped=pooled(entry_dropped_share),
        reach_next=pooled(reach_next_rate),
        already_hit=pooled(already_hit_share),
        touch_density=pooled(touch_density_fn(bar_count)),
        groups={name: compare(rows, lag_free_reach_rate,
                              shadow_count=shadow_count)
                for name, rows in confirmation_groups(events)},
    )


@dataclass(frozen=True)
class Selection:
    chosen: Optional[str]
    eligible: List[str]
    candidates: List[str]
    z: Dict[str, Optional[float]]
    reason: str


def select_rule(pooled: Mapping[str, Comparison],
                tie_window: float = TIE_WINDOW) -> Selection:
    """
    The pre-registered selection rule, on the pooled lag-free reach rate.

    1. Gate: a rule is eligible only if it is above all shadows.
    2. Choose the eligible rule with the largest z.
    3. Ties: candidates are eligible rules with z >= max z - tie_window;
       take the earliest in RULE_ORDER.
    4. No eligible rule: a null. AAPL is not built.
    """
    unknown = sorted(set(pooled) - set(RULE_ORDER))
    if unknown:
        raise ValueError(f"unknown breach rules {unknown}; expected {RULE_ORDER}")

    present = [name for name in RULE_ORDER if name in pooled]
    z = {name: pooled[name].z for name in present}
    eligible = [name for name in present if pooled[name].above_all_shadows]

    if not eligible:
        return Selection(
            chosen=None, eligible=[], candidates=[], z=z,
            reason="no breach rule is above all shadows on the pooled "
                   "lag-free reach rate; the sweep is null and AAPL is not "
                   "built")

    undefined = [name for name in eligible if z[name] is None]
    if undefined:
        raise ValueError(
            f"z is undefined for eligible rules {undefined} (shadow sd is 0); "
            "the pre-registered rule cannot rank them - stop and report")

    best = max(z[name] for name in eligible)
    candidates = [name for name in eligible if z[name] >= best - tie_window]
    chosen = candidates[0]
    return Selection(
        chosen=chosen, eligible=eligible, candidates=candidates, z=z,
        reason=(f"{chosen} chosen: best z {best:.3f}; candidates within "
                f"{tie_window} of it: {', '.join(candidates)}; the earliest "
                f"in the order {', '.join(RULE_ORDER)} wins"))
