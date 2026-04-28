import sys
import os
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from pathlib import Path
from scripts.run_paths import build_run_dir, build_run_id


def test_build_run_dir_produces_partitioned_path():
    p = build_run_dir(
        base="/tmp/gann_runs",
        instrument="NIFTY",
        timeframe="5m",
        run_id="2026-04-28_a1b2c3",
    )
    assert isinstance(p, Path)
    assert p.parts[-3:] == ("NIFTY", "5m", "2026-04-28_a1b2c3")


def test_build_run_dir_normalizes_instrument_with_special_chars():
    p = build_run_dir(
        base="/tmp/gann_runs",
        instrument="^NSEI",
        timeframe="5m",
        run_id="2026-04-28_a1b2c3",
    )
    assert "^" not in str(p)


def test_build_run_id_has_date_and_short_hash_format():
    rid = build_run_id(commit_hash="a1b2c3d4e5f6")
    assert rid.endswith("_a1b2c3")
    assert len(rid.split("_")[0]) == 10  # YYYY-MM-DD


def test_build_run_id_handles_missing_commit_hash():
    rid = build_run_id(commit_hash=None)
    # Should either end with _<6-char-hash> from git or _nogit if outside a repo
    parts = rid.split("_")
    assert len(parts[-1]) == 6 or parts[-1] == "nogit"
