import sys
import os
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.event_logger import Event, EventType


def test_event_has_instrument_and_timeframe_fields():
    e = Event(
        timestamp=1700000000,
        event_type=EventType.SUPPORT_TEST,
        instrument="NIFTY",
        timeframe="5m",
    )
    assert e.instrument == "NIFTY"
    assert e.timeframe == "5m"


def test_event_to_dict_includes_instrument_and_timeframe():
    e = Event(
        timestamp=1700000000,
        event_type=EventType.SUPPORT_TEST,
        instrument="BANKNIFTY",
        timeframe="60m",
    )
    d = e.to_dict()
    assert d["instrument"] == "BANKNIFTY"
    assert d["timeframe"] == "60m"


def test_event_from_dict_round_trips_instrument_and_timeframe():
    src = {
        "timestamp": 1700000000,
        "event_type": "SUPPORT_TEST",
        "instrument": "NIFTY",
        "timeframe": "15m",
    }
    e = Event.from_dict(src)
    assert e.instrument == "NIFTY"
    assert e.timeframe == "15m"


def test_event_defaults_instrument_and_timeframe_to_none():
    e = Event(timestamp=1700000000, event_type=EventType.CROSS_UP)
    assert e.instrument is None
    assert e.timeframe is None
