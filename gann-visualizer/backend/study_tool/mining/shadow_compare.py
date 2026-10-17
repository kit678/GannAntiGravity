"""
One comparison, reused for every question.

`compare` takes a slice of events - real rows and shadow rows together - and a
statistic. It runs the statistic on the real rows and once per shadow, then
places the real value in the shadow spread.

Building this once means every future question inherits the control
automatically, instead of depending on someone remembering to apply it. That
is the entire reason this file exists.
"""

import statistics as _stats
from dataclasses import dataclass, field
from typing import Callable, List, NamedTuple, Optional

import pandas as pd


class Stat(NamedTuple):
    """
    A statistic and the number of rows behind it.

    Sample size travels with the value rather than beside it. A 100% hold rate
    from four events is noise, and separating the two invites printing the
    percentage without it.
    """
    value: Optional[float]
    n: int


StatisticFn = Callable[[pd.DataFrame], Stat]


@dataclass(frozen=True)
class Comparison:
    real: Optional[float]
    n: int
    shadows: List[float] = field(default_factory=list)
    shadows_missing: int = 0

    @property
    def shadow_min(self) -> Optional[float]:
        return min(self.shadows) if self.shadows else None

    @property
    def shadow_max(self) -> Optional[float]:
        return max(self.shadows) if self.shadows else None

    @property
    def shadow_median(self) -> Optional[float]:
        return _stats.median(self.shadows) if self.shadows else None

    @property
    def percentile(self) -> Optional[float]:
        """Share of shadows strictly below the real value, as a percentage."""
        if self.real is None or not self.shadows:
            return None
        below = sum(1 for s in self.shadows if s < self.real)
        return 100.0 * below / len(self.shadows)

    @property
    def outside_range(self) -> bool:
        """True when real beats or trails every shadow."""
        if self.real is None or not self.shadows:
            return False
        return self.real > self.shadow_max or self.real < self.shadow_min

    @property
    def margin(self) -> float:
        """
        Distance past the shadow range: positive above, negative below, 0 inside.

        Sorting the shortlist by percentile alone cannot separate two groups
        that both sit above all 50 shadows.
        """
        if not self.outside_range:
            return 0.0
        if self.real > self.shadow_max:
            return self.real - self.shadow_max
        return self.real - self.shadow_min

    @property
    def z(self) -> Optional[float]:
        """
        (real - mean of the shadows) / sample sd of the shadows.

        None when real is None, fewer than two shadows have a value, or the
        shadows have no spread. Rule selection uses z rather than margin
        because the shadow spread narrows as row count grows, and breach
        rules have very different row counts.
        """
        if self.real is None or len(self.shadows) < 2:
            return None
        spread = _stats.stdev(self.shadows)
        if spread == 0:
            return None
        return (self.real - _stats.mean(self.shadows)) / spread

    @property
    def above_all_shadows(self) -> bool:
        """
        Real beats every shadow, and no shadow is missing.

        shadows_missing counts shadows with no rows in the group and shadows
        whose statistic was undefined there. Either way that shadow has no
        value to beat, so real has not been shown to beat it.
        """
        if self.real is None or not self.shadows or self.shadows_missing:
            return False
        return self.real > max(self.shadows)


def compare(events: pd.DataFrame, statistic_fn: StatisticFn,
            shadow_count: int) -> Comparison:
    """
    Run `statistic_fn` on the real rows and on each shadow's rows.

    Args:
        events: rows for one group, real and shadow together. Real rows carry
            a null `shadow_id`.
        statistic_fn: events frame -> Stat. Returns Stat(None, n) when the
            statistic is undefined.
        shadow_count: how many shadows the corpus holds. Taken from meta
            rather than from the data, so a shadow that produced no rows in
            this group is counted as missing instead of vanishing.

    A shadow with no rows contributes nothing and is counted in
    `shadows_missing`. Substituting zero would drag the spread down and make
    the real value look extreme.
    """
    is_real = events["shadow_id"].isna()
    real_stat = statistic_fn(events[is_real])

    shadow_values: List[float] = []
    missing = 0
    grouped = {int(key): frame
               for key, frame in events[~is_real].groupby("shadow_id")}

    for shadow_id in range(shadow_count):
        rows = grouped.get(shadow_id)
        if rows is None or len(rows) == 0:
            missing += 1
            continue
        value = statistic_fn(rows).value
        if value is None:
            missing += 1
            continue
        shadow_values.append(value)

    return Comparison(
        real=real_stat.value,
        n=real_stat.n,
        shadows=shadow_values,
        shadows_missing=missing,
    )
