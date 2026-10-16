"""
The breach definition sweep, as pure functions.

Spec: docs/superpowers/specs/2026-10-16-gann-breach-definition-sweep-design.md

Everything that decides an outcome - which breach rule is chosen, whether
AAPL passes - is here and takes only events frames or comparisons, so the
pre-registered rules are tested on hand-made inputs before any real corpus
is read.
"""

import json
import statistics as stats
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, NamedTuple, Optional, Tuple, Union

import pandas as pd

from study_tool.mining.groups import NULL_LABEL
from study_tool.mining.regression_gate import GateResult
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
    """
    reach_next and already_hit are None when the score was made with
    registered_only=True: they are not among the statistics the spec
    registers for AAPL, so that path never computes them.
    """
    rule: str
    lag_free: Comparison
    dropped: Comparison
    entry_dropped: Comparison
    touch_density: Comparison
    groups: Dict[str, Comparison]
    reach_next: Optional[Comparison] = None
    already_hit: Optional[Comparison] = None


SCORING_COLUMNS: Tuple[str, ...] = tuple(sorted({
    "reach_outcome", "target_hit_before_entry", "entry_beyond_level",
    "level_ring_bin", "shadow_id", "bar_index", "event_type",
    *(column for column, _ in CONFIRMATION_GROUPS),
}))


def _check_scorable(rule: str, events: pd.DataFrame) -> None:
    """
    Refuse input that would score as a null for a reason that is not the data.

    A missing column turns every statistic into Stat(None, 0), which reads as
    a pre-registered null - no rule eligible, AAPL not built - when the real
    cause is a wiring bug. So a miswired frame fails loudly instead.
    """
    missing = [column for column in SCORING_COLUMNS
               if column not in events.columns]
    if missing:
        raise ValueError(
            f"{rule}: events lack the columns {missing}; scoring them would "
            "read as a null sweep. Check load_scored_events and the corpus.")
    real = events[events["shadow_id"].isna()]
    if real["reach_outcome"].notna().sum() == 0:
        raise ValueError(
            f"{rule}: no real row has a reach_outcome ({len(real)} real "
            "rows); scoring them would read as a null sweep. The reach race "
            "was not joined or the corpus holds no confirmed breaches.")


def score_rule(rule: str, events: pd.DataFrame, shadow_count: int,
               registered_only: bool = False) -> RuleScore:
    """
    Every number the sweep reads for one breach rule, pooled and per group.

    `events` must already carry the reach race and level_ring_bin -
    mine_gann_corpus.load_scored_events supplies both. With
    registered_only=True (the AAPL look) only the statistics the spec names
    are computed: touch density, the lag-free reach rate pooled and by group,
    and the two dropped shares. reach_next_rate and already_hit_share are
    left None, so the holdout never reads them.

    Raises:
        ValueError: a needed column is missing, or no real row carries a
            reach_outcome.
    """
    _check_scorable(rule, events)
    bar_count = int(events["bar_index"].nunique())

    def pooled(statistic) -> Comparison:
        return compare(events, statistic, shadow_count=shadow_count)

    return RuleScore(
        rule=rule,
        lag_free=pooled(lag_free_reach_rate),
        dropped=pooled(dropped_share),
        entry_dropped=pooled(entry_dropped_share),
        reach_next=None if registered_only else pooled(reach_next_rate),
        already_hit=None if registered_only else pooled(already_hit_share),
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


@dataclass(frozen=True)
class Verdict:
    label: str
    passed: bool
    strong: bool
    groups_above: int
    selection_differs: bool
    touch_busier_than_all_shadows: bool
    touch_shadows_missing: int = 0


def aapl_verdict(score: RuleScore) -> Verdict:
    """
    The pre-registered AAPL reading.

    pass: pooled lag-free reach rate above all shadows. strong pass: pass
    and at least STRONG_PASS_GROUPS of the 13 groups above all shadows. If
    the real dropped share is outside the shadow range the filtered sets are
    not like-for-like, and a pass says so in its label.
    """
    passed = score.lag_free.above_all_shadows
    groups_above = sum(1 for c in score.groups.values() if c.above_all_shadows)
    strong = passed and groups_above >= STRONG_PASS_GROUPS
    selection_differs = score.dropped.outside_range

    label = "fail"
    if passed:
        label = "strong pass" if strong else "pass"
        if selection_differs:
            label += ", selection differs"

    # Busier than every shadow that has a touch density. Shadows with no
    # touches have none, and are reported separately rather than read as
    # "not above" - Comparison.above_all_shadows would do the latter.
    touch = score.touch_density
    busier = (touch.real is not None and bool(touch.shadows)
              and touch.real > max(touch.shadows))

    return Verdict(label=label, passed=passed, strong=strong,
                   groups_above=groups_above,
                   selection_differs=selection_differs,
                   touch_busier_than_all_shadows=busier,
                   touch_shadows_missing=touch.shadows_missing)


def _shadow_mean_sd(shadows: List[float]) -> Tuple[Optional[float],
                                                    Optional[float]]:
    mean = stats.mean(shadows) if shadows else None
    sd = stats.stdev(shadows) if len(shadows) >= 2 else None
    return mean, sd


def choice_record(selection: Selection, scores: Mapping[str, RuleScore],
                  gate: GateResult, shadow_count: int,
                  corpora: Mapping[str, str],
                  tie_window: float = TIE_WINDOW) -> Dict:
    """
    The choice file's contents: the decision and what it rested on.

    Raises:
        ValueError: scores or the selection do not cover exactly the four
            rules, or a rule is chosen although the regression gate did not
            pass. Selection itself stays permissive about subsets; the file
            that AAPL trusts does not.
    """
    expected = set(RULE_ORDER)
    if set(scores) != expected or set(selection.z) != expected:
        raise ValueError(
            f"a choice record needs exactly {RULE_ORDER}; scores cover "
            f"{sorted(scores)}, the selection covers {sorted(selection.z)}")
    if selection.chosen is not None and not gate.passed:
        raise ValueError(
            f"{selection.chosen} was chosen but the regression gate did not "
            f"pass ({gate.reason}); a choice must rest on a verified rebuild")

    chosen = RULES_BY_NAME[selection.chosen] if selection.chosen else None
    rules = {}
    for name in RULE_ORDER:
        lag = scores[name].lag_free
        mean, sd = _shadow_mean_sd(lag.shadows)
        rules[name] = {
            "lag_free_real": lag.real,
            "lag_free_n": lag.n,
            "shadow_max": lag.shadow_max,
            "shadow_mean": mean,
            "shadow_sd": sd,
            "shadows_missing": lag.shadows_missing,
            "above_all_shadows": lag.above_all_shadows,
            "z": lag.z,
        }
    return {
        "spec": SPEC_PATH,
        "chosen": selection.chosen,
        "breach_mode": chosen.breach_mode if chosen else None,
        "confirmation_closes": chosen.confirmation_closes if chosen else None,
        "reason": selection.reason,
        "eligible": list(selection.eligible),
        "candidates": list(selection.candidates),
        "tie_window": tie_window,
        "rule_order": list(RULE_ORDER),
        "shadow_count": shadow_count,
        "corpora": dict(corpora),
        "regression_gate": {"passed": gate.passed, "reason": gate.reason},
        "rules": rules,
    }


def write_choice(path: Union[str, Path], record: Dict) -> None:
    """
    Write the choice file once.

    The pre-registered choice is not revisable: a file already there with
    different contents is an error, and identical contents are a no-op, so a
    rerun over reused corpora is harmless.
    """
    path = Path(path)
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == text:
            return
        raise FileExistsError(
            f"{path} already holds a different choice; the pre-registered "
            "choice is written once and never overwritten")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_choice(path: Union[str, Path]) -> BreachRule:
    """
    The breach rule the RELIANCE sweep chose.

    Raises:
        FileNotFoundError: no choice file - the sweep has not run.
        ValueError: the file is malformed (no `chosen` key), the choice is
            null (the stop rule keeps AAPL unbuilt), it names a rule this
            code does not know, the regression gate did not pass, or the
            record does not hold all four rules' scores.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found: the RELIANCE sweep has not chosen a breach "
            "rule, so AAPL is not built")
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or "chosen" not in record:
        raise ValueError(
            f"{path} is malformed: it has no 'chosen' key, so it is neither "
            "a choice nor a recorded null")
    chosen = record["chosen"]
    if chosen is None:
        raise ValueError(
            f"{path} records a null sweep: no breach rule beat every shadow, "
            "and the pre-registered stop rule keeps AAPL unbuilt")
    if chosen not in RULES_BY_NAME:
        raise ValueError(f"{path} names unknown breach rule {chosen!r}")

    gate = record.get("regression_gate")
    if not isinstance(gate, dict) or gate.get("passed") is not True:
        raise ValueError(
            f"{path}: the regression gate did not pass (or is not "
            "recorded), so the choice does not rest on a verified rebuild")
    rules = record.get("rules")
    if not isinstance(rules, dict) or set(rules) != set(RULE_ORDER):
        found = sorted(rules) if isinstance(rules, dict) else rules
        raise ValueError(
            f"{path}: 'rules' must hold exactly {RULE_ORDER}, found {found}; "
            "a choice made on a subset of the rules is not the registered "
            "sweep")
    rule = RULES_BY_NAME[chosen]
    for key, expected in (("breach_mode", rule.breach_mode),
                          ("confirmation_closes", rule.confirmation_closes)):
        if record.get(key) != expected:
            raise ValueError(
                f"{path}: {key} is {record.get(key)!r} but {chosen} means "
                f"{expected!r}; the choice file disagrees with itself")
    return rule
