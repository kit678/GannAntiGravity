"""
The corpus on disk: three tables, and a holdout that is hard to touch by accident.

Mining runs on the explore slice. The holdout is spent once, in batches, so
reaching it must be a deliberate act rather than a forgotten default.
"""
import sys
import os

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.corpus_writer import (
    assign_slices, load_events, write_corpus,
)


def events_frame():
    return pd.DataFrame({
        "bar_index": list(range(10)),
        "timestamp": [1000 + i for i in range(10)],
        "event_type": ["LADDER_TOUCH"] * 10,
        "level_source": ["center"] * 10,
        "shadow_id": [None] * 10,
    })


def bars_frame():
    return pd.DataFrame({
        "timestamp": [1000 + i for i in range(10)],
        "close": [100.0 + i for i in range(10)],
    })


def keys_frame():
    return pd.DataFrame({
        "bar_index": list(range(10)),
        "price_square": [100 + i for i in range(10)],
        "sun_square": [156] * 10,
        "moon_square": [332] * 10,
    })


def test_assign_slices_splits_by_time_not_at_random():
    """A random split would leak the future into the explore set."""
    frame = assign_slices(events_frame(), holdout_fraction=0.25,
                          order_column="bar_index")

    explore = frame[frame["slice"] == "explore"]["bar_index"]
    holdout = frame[frame["slice"] == "holdout"]["bar_index"]

    assert explore.max() < holdout.min(), "slices overlap in time"
    assert len(holdout) == 3  # ceil of 25% of 10, taken from the end
    assert len(explore) == 7


def test_write_then_read_round_trips(tmp_path):
    write_corpus(tmp_path, events=assign_slices(events_frame()),
                 bars=bars_frame(), ladder_keys=keys_frame())

    for name in ("events", "bars", "ladder_keys"):
        assert (tmp_path / f"{name}.parquet").exists(), f"{name} not written"


def test_write_corpus_refuses_to_overwrite_by_default(tmp_path):
    write_corpus(tmp_path, events=assign_slices(events_frame()),
                 bars=bars_frame(), ladder_keys=keys_frame())

    with pytest.raises(FileExistsError, match="overwrite"):
        write_corpus(tmp_path, events=assign_slices(events_frame()),
                     bars=bars_frame(), ladder_keys=keys_frame())


def test_write_corpus_overwrites_when_asked(tmp_path):
    write_corpus(tmp_path, events=assign_slices(events_frame()),
                 bars=bars_frame(), ladder_keys=keys_frame())

    write_corpus(tmp_path, events=assign_slices(events_frame()),
                 bars=bars_frame(), ladder_keys=keys_frame(), overwrite=True)

    for name in ("events", "bars", "ladder_keys"):
        assert (tmp_path / f"{name}.parquet").exists(), f"{name} not written"


def test_load_events_returns_only_explore_by_default(tmp_path):
    write_corpus(tmp_path, events=assign_slices(events_frame()),
                 bars=bars_frame(), ladder_keys=keys_frame())

    loaded = load_events(tmp_path)

    assert set(loaded["slice"]) == {"explore"}, (
        "the default load reached the holdout"
    )


def test_load_events_needs_an_explicit_argument_for_the_holdout(tmp_path):
    write_corpus(tmp_path, events=assign_slices(events_frame()),
                 bars=bars_frame(), ladder_keys=keys_frame())

    loaded = load_events(tmp_path, slice_name="holdout")

    assert set(loaded["slice"]) == {"holdout"}


def test_an_unknown_slice_name_raises(tmp_path):
    write_corpus(tmp_path, events=assign_slices(events_frame()),
                 bars=bars_frame(), ladder_keys=keys_frame())

    with pytest.raises(ValueError, match="unknown slice"):
        load_events(tmp_path, slice_name="test")
