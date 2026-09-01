"""
Multi-day / checkpoint-resume behaviour for the ladder study runner.

The runner is meant to walk a long stretch of bars in chunks - one day at a
time - saving its place between chunks so a later day picks up the breaches
and pending crosses the earlier day left open. This file pins that down: a
walk split into chunks must produce exactly the events a single unbroken walk
produces.
"""
import sys
import os

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.run_ladder_study import run_study, run_study_chunk


def bar(open_, high, low, close, timestamp):
    return {
        "open": open_, "high": high, "low": low,
        "close": close, "timestamp": timestamp,
    }


DAY = 86400


def trending_walk(count=12, start=100.0, step=3.0):
    """
    A steadily climbing series, one bar per day.

    Climbing matters: a flat series never crosses anything, so nothing would
    stay open across a chunk boundary and the test would pass vacuously.
    """
    bars = []
    for i in range(count):
        open_ = start + step * i
        close = open_ + step
        bars.append(bar(open_, close + 1.0, open_ - 1.0, close, DAY * (i + 1)))
    # Sun moves ~1 deg/day, Moon ~13 deg/day - roughly real daily motion, so
    # the Moon ladder is rebuilt often and the Sun ladder rarely.
    sun = [154.0 + 1.0 * i for i in range(count)]
    moon = [(321.9 + 13.2 * i) % 360 for i in range(count)]
    return bars, sun, moon


def as_dicts(events):
    return [e.to_dict() for e in events]


def test_a_chunked_walk_matches_one_unbroken_walk():
    bars, sun, moon = trending_walk()
    split = 6

    whole = run_study(
        bars, instrument="RELIANCE", timeframe="D", price_scale=1,
        sun_degrees=sun, moon_degrees=moon,
    )

    first, state = run_study_chunk(
        bars[:split], instrument="RELIANCE", timeframe="D", price_scale=1,
        sun_degrees=sun[:split], moon_degrees=moon[:split],
        start_index=0, finalize=False,
    )
    second, _ = run_study_chunk(
        bars[split:], instrument="RELIANCE", timeframe="D", price_scale=1,
        sun_degrees=sun[split:], moon_degrees=moon[split:],
        start_index=split, state=state, finalize=True,
    )

    assert as_dicts(first + second) == as_dicts(whole)


def test_the_split_actually_leaves_work_open_across_the_boundary():
    """
    Guards the test above from passing for the wrong reason: if the first
    chunk finished with nothing pending, resuming would be trivial and the
    comparison would prove nothing.
    """
    bars, sun, moon = trending_walk()
    _, state = run_study_chunk(
        bars[:6], instrument="RELIANCE", timeframe="D", price_scale=1,
        sun_degrees=sun[:6], moon_degrees=moon[:6],
        start_index=0, finalize=False,
    )
    assert state["pending"] or state["open_breaches"], (
        "chunk boundary left nothing open - pick a split that does"
    )


def test_every_split_point_matches_the_unbroken_walk():
    """One working split could be luck. Every split working is the property."""
    bars, sun, moon = trending_walk()
    kw = dict(instrument="RELIANCE", timeframe="D", price_scale=1)
    whole = as_dicts(run_study(bars, sun_degrees=sun, moon_degrees=moon, **kw))

    for split in range(1, len(bars)):
        first, state = run_study_chunk(
            bars[:split], sun_degrees=sun[:split], moon_degrees=moon[:split],
            start_index=0, finalize=False, **kw,
        )
        second, _ = run_study_chunk(
            bars[split:], sun_degrees=sun[split:], moon_degrees=moon[split:],
            start_index=split, state=state, finalize=True, **kw,
        )
        assert as_dicts(first + second) == whole, f"diverged at split {split}"


def test_one_bar_at_a_time_matches_the_unbroken_walk():
    """The extreme case: a chunk per bar, as a daily cron would do it."""
    bars, sun, moon = trending_walk()
    kw = dict(instrument="RELIANCE", timeframe="D", price_scale=1)
    whole = as_dicts(run_study(bars, sun_degrees=sun, moon_degrees=moon, **kw))

    collected = []
    state = None
    for i in range(len(bars)):
        chunk, state = run_study_chunk(
            bars[i:i + 1], sun_degrees=sun[i:i + 1], moon_degrees=moon[i:i + 1],
            start_index=i, state=state, finalize=(i == len(bars) - 1), **kw,
        )
        collected.extend(chunk)

    assert as_dicts(collected) == whole


def test_carried_degrees_do_not_grow_with_the_length_of_the_walk():
    """
    The resume state is saved between days, so it must stay small. It should
    hold degrees only for bars still open, not for every bar ever seen.
    """
    bars, sun, moon = trending_walk(count=40)
    kw = dict(instrument="RELIANCE", timeframe="D", price_scale=1)
    state = None
    for i in range(len(bars)):
        _, state = run_study_chunk(
            bars[i:i + 1], sun_degrees=sun[i:i + 1], moon_degrees=moon[i:i + 1],
            start_index=i, state=state, finalize=False, **kw,
        )
    open_bars = len(state["pending"]) + len(state["open_breaches"])
    assert len(state["degrees"]) <= open_bars


def test_run_study_still_returns_a_plain_event_list():
    """The existing single-shot entry point keeps its old shape."""
    bars, sun, moon = trending_walk(count=4)
    events = run_study(
        bars, instrument="RELIANCE", timeframe="D", price_scale=1,
        sun_degrees=sun, moon_degrees=moon,
    )
    assert isinstance(events, list)
    assert all(hasattr(e, "event_type") for e in events)
