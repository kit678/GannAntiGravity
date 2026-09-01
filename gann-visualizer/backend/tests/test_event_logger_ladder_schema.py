import sys
import os
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.event_logger import Event, EventType


LADDER_FIELDS = {
    "level_source": "sun",
    "level_price": 105.5,
    "level_square": 3197.0,
    "level_kind": "sub",
    "level_degree": 45,
    "level_ring": 3,
    "level_sub_index": 4,
    "level_is_halfway": True,
    "level_segment_start": 100.0,
    "level_segment_end": 110.0,
    "price_scale": 10,
    "body_degree": 154.15,
    "body_square": 155,
    "breach_id": "RELIANCE:5:1:sun:105:12",
    "parent_breach_id": "RELIANCE:5:1:sun:105:12",
}


def make_ladder_event():
    return Event(
        timestamp=1700000000,
        event_type=EventType.LADDER_RETEST,
        **LADDER_FIELDS,
    )


def test_event_holds_all_ladder_fields():
    e = make_ladder_event()
    for name, value in LADDER_FIELDS.items():
        assert getattr(e, name) == value


def test_event_defaults_ladder_fields_to_none():
    e = Event(timestamp=1700000000, event_type=EventType.CROSS_UP)
    for name in LADDER_FIELDS:
        assert getattr(e, name) is None


def test_to_dict_includes_every_ladder_field():
    d = make_ladder_event().to_dict()
    for name, value in LADDER_FIELDS.items():
        assert d.get(name) == value, f"{name} missing or wrong in to_dict()"


def test_from_dict_round_trips_every_ladder_field():
    src = {"timestamp": 1700000000, "event_type": "LADDER_RETEST", **LADDER_FIELDS}
    e = Event.from_dict(src)
    for name, value in LADDER_FIELDS.items():
        assert getattr(e, name) == value, f"{name} did not round-trip"


import csv
import json
import tempfile
from pathlib import Path
from study_tool.event_logger import EventLogger


def test_export_csv_includes_ladder_columns():
    logger = EventLogger()
    logger.log_event(timestamp=1700000000, event_type=EventType.LADDER_RETEST, price=105.5)
    event = logger.events[0]
    for name, value in LADDER_FIELDS.items():
        setattr(event, name, value)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "events.csv"
        logger.export_csv(str(out))
        rows = list(csv.DictReader(out.open()))

    assert len(rows) == 1
    row = rows[0]
    assert row["Level_Source"] == "sun"
    assert row["Level_Price"] == "105.5"
    assert row["Level_Kind"] == "sub"
    assert row["Level_Degree"] == "45"
    assert row["Level_Ring"] == "3"
    assert row["Level_Sub_Index"] == "4"
    assert row["Level_Is_Halfway"] == "True"
    assert row["Price_Scale"] == "10"
    assert row["Breach_Id"] == "RELIANCE:5:1:sun:105:12"
    assert row["Parent_Breach_Id"] == "RELIANCE:5:1:sun:105:12"


def test_export_hypothesis_json_includes_ladder_fields():
    logger = EventLogger()
    logger.log_event(timestamp=1700000000, event_type=EventType.LADDER_RETEST, price=105.5)
    event = logger.events[0]
    for name, value in LADDER_FIELDS.items():
        setattr(event, name, value)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "hypothesis.json"
        logger.export_hypothesis_json(str(out), symbol="RELIANCE", resolution="5")
        data = json.loads(out.read_text())

    entry = data["events"][0]
    for name, value in LADDER_FIELDS.items():
        assert entry.get(name) == value, f"{name} missing or wrong in export_hypothesis_json"
