"""Helpers for building partitioned run output directories.

A run directory has the shape:
    <base>/<instrument>/<timeframe>/<run_id>/

run_id format: YYYY-MM-DD_<short_hash>
"""
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional


_PATH_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]")


def _sanitize(component: str) -> str:
    return _PATH_SAFE_RE.sub("_", component)


def build_run_dir(base: str, instrument: str, timeframe: str, run_id: str) -> Path:
    """Construct the run output directory path (does NOT create it on disk)."""
    return Path(base) / _sanitize(instrument) / _sanitize(timeframe) / _sanitize(run_id)


def build_run_id(commit_hash: Optional[str] = None) -> str:
    """Return a run_id of the form 'YYYY-MM-DD_<short_hash_or_nogit>'."""
    date_part = datetime.now().strftime("%Y-%m-%d")
    if commit_hash is None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True, timeout=2,
            )
            commit_hash = result.stdout.strip()
        except Exception:
            commit_hash = None

    short = commit_hash[:6] if commit_hash else "nogit"
    return f"{date_part}_{short}"
