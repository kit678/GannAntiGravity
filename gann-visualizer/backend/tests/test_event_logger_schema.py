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


import csv
import tempfile
from pathlib import Path
from study_tool.event_logger import EventLogger


def test_export_csv_includes_instrument_timeframe_and_extra_horizon_columns():
    logger = EventLogger()
    logger.log_event(
        timestamp=1700000000,
        event_type=EventType.SUPPORT_TEST,
        angle_name="0.5",
        price=100.0,
        open_price=99.5,
        high_price=100.5,
        low_price=99.0,
        close_price=100.2,
    )
    logger.events[0].instrument = "NIFTY"
    logger.events[0].timeframe = "5m"
    logger.events[0].mfe_5 = 1.1
    logger.events[0].mae_5 = 0.2
    logger.events[0].mfe_50 = 5.5
    logger.events[0].mae_50 = 1.1

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "events.csv"
        logger.export_csv(str(out))
        rows = list(csv.DictReader(out.open()))

    assert len(rows) == 1
    row = rows[0]
    assert row["Instrument"] == "NIFTY"
    assert row["Timeframe"] == "5m"
    assert float(row["MFE_5"]) == 1.1
    assert float(row["MAE_5"]) == 0.2
    assert float(row["MFE_50"]) == 5.5
    assert float(row["MAE_50"]) == 1.1
