import sys
import os
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

import csv
import tempfile
from pathlib import Path
from analysis.phase1_edge_test import discover_slices, run_phase1


def _write_minimal_events_csv(path: Path, instrument: str, timeframe: str):
    """Write a tiny events.csv with the schema produced by EventLogger.export_csv."""
    fieldnames = [
        "#", "Time", "Fan", "Fraction", "Price", "Type", "Details",
        "Open", "High", "Low", "Close", "Active_Angles",
        "Cluster", "Zone", "Zone_Highest_Close", "Zone_Lowest_Close",
        "Next_Angle_Line",
        "Instrument", "Timeframe",
        "MFE_5", "MAE_5", "MFE_10", "MAE_10",
        "MFE_20", "MAE_20", "MFE_50", "MAE_50",
        "Raw_Timestamp", "Direction",
    ]
    rows = [
        {f: "" for f in fieldnames},
        {f: "" for f in fieldnames},
    ]
    rows[0].update({
        "#": 1, "Time": "1/1/2026, 10:00:00 AM", "Fan": "P1 (H1-L1)",
        "Fraction": "0.5", "Price": 100.0, "Type": "BREACH_CONFIRMED",
        "Open": 99.5, "High": 100.5, "Low": 99.0, "Close": 100.5,
        "Instrument": instrument, "Timeframe": timeframe,
        "Raw_Timestamp": 1700000000, "Direction": "up",
        "MFE_10": 0.0, "MAE_10": 0.0, "bar_index": 1,
    })
    rows[1].update({
        "#": 2, "Time": "1/1/2026, 10:30:00 AM", "Fan": "P1 (H1-L1)",
        "Fraction": "0.5", "Price": 100.0, "Type": "SUPPORT_TEST",
        "Open": 100.5, "High": 101.0, "Low": 99.5, "Close": 100.8,
        "Instrument": instrument, "Timeframe": timeframe,
        "Raw_Timestamp": 1700001500, "Direction": "",
        "MFE_10": 5.0, "MAE_10": 1.0, "bar_index": 4,
    })
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames + ["bar_index"])
        w.writeheader()
        w.writerows(rows)


def test_discover_slices_walks_partitioned_runs():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        for inst in ("NIFTY", "BANKNIFTY"):
            for tf in ("5", "60"):
                rd = base / inst / tf / "2026-04-28_abc123"
                rd.mkdir(parents=True)
                (rd / "events.csv").touch()

        slices = discover_slices(str(base))
        assert len(slices) == 4
        for inst, tf, rd in slices:
            assert inst in ("NIFTY", "BANKNIFTY")
            assert tf in ("5", "60")


def test_run_phase1_produces_summary_table_with_required_columns():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        rd = base / "NIFTY" / "60" / "2026-04-28_abc123"
        rd.mkdir(parents=True)
        _write_minimal_events_csv(rd / "events.csv", "NIFTY", "60")

        out_csv = base / "phase1_summary.csv"
        run_phase1(str(base), str(out_csv))

        assert out_csv.exists()
        rows = list(csv.DictReader(out_csv.open()))
        assert len(rows) > 0
        required = {"hypothesis", "instrument", "timeframe", "sample_size", "win_rate"}
        assert required.issubset(rows[0].keys())