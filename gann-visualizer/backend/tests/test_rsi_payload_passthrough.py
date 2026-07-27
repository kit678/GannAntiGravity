import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import _transform_per_hypothesis_payload


def test_transform_preserves_rsi_series_and_line_timeline():
    payload = {
        "hypothesis_name": "RSI Trendline Break Strategy",
        "in_sample": {"sample_size": 2},
        "rsi_series": [{"bar_index": 10, "time": "2026-07-10T10:00:00", "rsi": 51.2}],
        "line_timeline": [
            {
                "segment_id": 3,
                "direction": "down",
                "valid_from_bar": 100,
                "valid_to_bar": 140,
                "end_reason": "broken",
                "anchor_a": {"bar_index": 80, "rsi": 68.0, "kind": "high"},
                "anchor_b": {"bar_index": 96, "rsi": 61.0, "kind": "high"},
            }
        ],
    }

    transformed = _transform_per_hypothesis_payload(payload)

    assert transformed["rsi_series"][0]["rsi"] == 51.2
    assert transformed["line_timeline"][0]["segment_id"] == 3
    assert transformed["line_timeline"][0]["end_reason"] == "broken"
