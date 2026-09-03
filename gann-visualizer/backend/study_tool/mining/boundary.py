"""
The buffer that stops holdout price action leaking into the explore slice.

Every outcome in this corpus looks forward: a breach is resolved by the next
50 bars, mfe/mae read the next 50 bars, and the reach-next-level race runs over
the next 50 bars. So an explore event opening in the last 50 bars of the
explore slice has its outcome decided by holdout data, even though the row
itself is labelled explore.

It is about 50 bars out of 37,110 - roughly 0.1% of events - which is exactly
why it would never be noticed. It is also a leak in the single mechanism every
later conclusion depends on, so it is closed rather than tolerated, and the
number dropped is returned so the cost is visible in the report.
"""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class BufferedEvents:
    events: pd.DataFrame
    dropped: int
    boundary: int
    buffer_bars: int


def boundary_bar_index(events: pd.DataFrame) -> int:
    """
    The first bar index that belongs to the holdout.

    Reads only `bar_index` and `slice`. That is structural bookkeeping, not
    price action or outcomes, so it does not spend the holdout.

    Raises:
        ValueError: if no row is labelled holdout. A corpus with no holdout
            never had the split applied, and guessing a boundary would place
            the buffer somewhere meaningless.
    """
    holdout = events[events["slice"] == "holdout"]
    if holdout.empty:
        raise ValueError(
            "no holdout rows in this events frame; the explore/holdout split "
            "was never applied, so there is no boundary to buffer"
        )
    return int(holdout["bar_index"].min())


def drop_boundary_events(explore_events: pd.DataFrame, boundary: int,
                         buffer_bars: int) -> BufferedEvents:
    """
    Drop explore events whose forward window reaches past `boundary`.

    An event at bar b reads bars up to b + buffer_bars, so it is safe only
    when b + buffer_bars < boundary.

    Raises:
        ValueError: if that leaves nothing. An empty frame downstream produces
            a report full of Nones rather than an error.
    """
    cutoff = boundary - buffer_bars
    kept = explore_events[explore_events["bar_index"] < cutoff]
    dropped = len(explore_events) - len(kept)

    if kept.empty:
        raise ValueError(
            f"a {buffer_bars}-bar buffer before boundary {boundary} drops "
            f"every one of the {len(explore_events)} explore events"
        )

    return BufferedEvents(
        events=kept.reset_index(drop=True),
        dropped=dropped,
        boundary=boundary,
        buffer_bars=buffer_bars,
    )
