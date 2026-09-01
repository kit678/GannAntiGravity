"""
Tests for run_study's wiring, on synthetic bars.
"""
import sys
import os

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.run_ladder_study import run_study, degree_to_square, summarise


def bar(open_, high, low, close, timestamp=0):
    return {
        "open": open_, "high": high, "low": low,
        "close": close, "timestamp": timestamp,
    }


def test_sun_and_moon_events_carry_the_bodys_degree_and_square():
    bars = [
        bar(104.0, 106.0, 103.5, 105.5),
        bar(105.5, 107.0, 105.2, 106.5),
    ]
    sun_degrees = [154.0, 154.2]
    moon_degrees = [321.9, 322.4]

    events = run_study(
        bars, instrument="RELIANCE", timeframe="5", price_scale=1,
        sun_degrees=sun_degrees, moon_degrees=moon_degrees,
    )

    sun_events = [e for e in events if e.level_source == "sun"]
    moon_events = [e for e in events if e.level_source == "moon"]
    assert sun_events, "expected at least one sun-sourced event"
    assert moon_events, "expected at least one moon-sourced event"

    for e in sun_events:
        assert e.body_degree == sun_degrees[e.bar_index]
        assert e.body_square == degree_to_square(sun_degrees[e.bar_index])
    for e in moon_events:
        assert e.body_degree == moon_degrees[e.bar_index]
        assert e.body_square == degree_to_square(moon_degrees[e.bar_index])


def test_center_sourced_events_have_no_body_degree():
    bars = [bar(104.0, 106.0, 103.5, 105.5)]
    events = run_study(
        bars, instrument="RELIANCE", timeframe="5", price_scale=1,
        sun_degrees=[154.0], moon_degrees=[321.9],
    )
    center_events = [e for e in events if e.level_source == "center"]
    assert center_events
    for e in center_events:
        assert e.body_degree is None
        assert e.body_square is None


def test_summarise_counts_by_event_type():
    bars = [bar(104.0, 106.0, 103.5, 105.5)]
    events = run_study(
        bars, instrument="RELIANCE", timeframe="5", price_scale=1,
        sun_degrees=[154.0], moon_degrees=[321.9],
    )
    counts = summarise(events)
    assert sum(counts.values()) == len(events)
