"""
The buffer at the explore/holdout boundary.

Outcomes look forward 50 bars. An explore event opening within 50 bars of the
boundary has its outcome decided by holdout price action, so mining drops it.
The count dropped is returned rather than logged quietly - the cost of the
buffer should be visible in the report.
"""
import sys
import os

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.boundary import (
    BufferedEvents, boundary_bar_index, drop_boundary_events,
)


def events_frame(n=100, holdout_from=75):
    return pd.DataFrame({
        "bar_index": list(range(n)),
        "slice": ["explore" if i < holdout_from else "holdout"
                  for i in range(n)],
        "event_type": ["LADDER_TOUCH"] * n,
    })


def test_boundary_is_the_first_holdout_bar():
    assert boundary_bar_index(events_frame()) == 75


def test_boundary_raises_when_there_is_no_holdout():
    """A corpus with no holdout means the split never ran. Do not guess."""
    frame = events_frame(holdout_from=100)
    with pytest.raises(ValueError, match="no holdout"):
        boundary_bar_index(frame)


def test_events_inside_the_buffer_are_dropped():
    explore = events_frame()[lambda f: f["slice"] == "explore"]

    result = drop_boundary_events(explore, boundary=75, buffer_bars=50)

    assert isinstance(result, BufferedEvents)
    assert result.events["bar_index"].max() < 25
    assert result.dropped == 50
    assert result.boundary == 75
    assert result.buffer_bars == 50


def test_a_kept_event_is_far_enough_back_to_resolve_inside_explore():
    """
    The invariant, stated as arithmetic: the last kept bar plus the forward
    window must still land before the first holdout bar.
    """
    explore = events_frame()[lambda f: f["slice"] == "explore"]

    result = drop_boundary_events(explore, boundary=75, buffer_bars=50)

    assert result.events["bar_index"].max() + 50 <= 75


def test_a_zero_buffer_drops_nothing():
    explore = events_frame()[lambda f: f["slice"] == "explore"]

    result = drop_boundary_events(explore, boundary=75, buffer_bars=0)

    assert result.dropped == 0
    assert len(result.events) == 75


def test_dropping_everything_raises_rather_than_returning_an_empty_frame():
    """
    A silent empty frame downstream produces a report full of None. Better to
    stop with the reason.
    """
    explore = events_frame()[lambda f: f["slice"] == "explore"]

    with pytest.raises(ValueError, match="buffer"):
        drop_boundary_events(explore, boundary=75, buffer_bars=200)
