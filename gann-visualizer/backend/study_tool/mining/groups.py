"""
The label groups every statistic is reported across.

Pooling hides signal. A 41% hold rate on halfway levels sitting beside 22%
everywhere else averages out to something that looks dead, so no statistic in
this phase is reported pooled on its own.

Every grouping keeps real and shadow rows together in the same frame, because
compare() does the real/shadow split itself. A grouping that dropped shadows
would remove the control without changing any output shape.
"""

from typing import Iterator, List, Tuple

import pandas as pd

GROUPINGS: Tuple[str, ...] = (
    "level_source",       # center / sun / moon
    "level_degree",       # 0, 45, ... 315 - the arm
    "level_sub_index",    # 1..7, null for majors
    "level_is_halfway",   # true / false
    "level_ring_bin",     # ring, bucketed
    "level_kind",         # major / sub
)

RING_BIN_WIDTH = 10
NULL_LABEL = "none"


def add_ring_bin(events: pd.DataFrame, width: int = RING_BIN_WIDTH) -> pd.DataFrame:
    """
    Add `level_ring_bin`, a bucketed copy of `level_ring`.

    Rings run into the dozens on a two-year corpus, so grouping on the raw
    ring would produce many groups of a handful of events each - every one of
    them noise, and every one of them a chance to land outside the shadow
    range by accident.
    """
    frame = events.copy()

    def label(ring) -> str:
        if pd.isna(ring):
            return NULL_LABEL
        low = (int(ring) // width) * width
        return f"{low}-{low + width - 1}"

    frame["level_ring_bin"] = frame["level_ring"].apply(label)
    return frame


def iter_groups(events: pd.DataFrame,
                column: str) -> Iterator[Tuple[str, pd.DataFrame]]:
    """
    Yield (label, rows) for each distinct value of `column`, in sorted order.

    Nulls become the group `"none"` rather than being dropped:
    level_sub_index is null for every major level, and dropping it would
    quietly exclude majors from that breakdown instead of showing them.

    Sorted so the Markdown report diffs cleanly across runs.
    """
    labelled = events[column].apply(
        lambda v: NULL_LABEL if pd.isna(v) else str(v))
    for label in sorted(labelled.unique()):
        yield label, events[labelled == label]


def grouping_columns() -> List[str]:
    """The groupings, as a list, for callers that want to iterate them."""
    return list(GROUPINGS)
