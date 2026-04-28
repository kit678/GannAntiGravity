"""Phase 1 driver: load every corpus slice, run all hypotheses, emit summary.

Output columns:
    hypothesis, instrument, timeframe, run_id, sample_size, win_rate,
    avg_mfe_10, avg_mae_10

Usage:
    cd gann-visualizer/backend
    python -m analysis.phase1_edge_test --corpus-base ../../logs/backend/runs --out ../../logs/backend/phase1_summary.csv
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path
from typing import List, Tuple

import pandas as pd

# Ensure backend is on sys.path when run as a script
import os as _os
sys.path.append(_os.path.abspath(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))

from analysis.strategy_analyzer import (
    StrongSRHypothesis,
    TargetProgressionHypothesis,
    QuarterReversalAnomalyHypothesis,
    ConfluenceBounceHypothesis,
    PostBreachPullbackHypothesis,
    MultiTFReversalHypothesis,
)


SECONDARY_HYPOTHESES = [
    StrongSRHypothesis,
    TargetProgressionHypothesis,
    QuarterReversalAnomalyHypothesis,
    ConfluenceBounceHypothesis,
]
PRIORITY_HYPOTHESES = [PostBreachPullbackHypothesis]   # MultiTFReversal handled separately (multi-DF)


def discover_slices(base: str) -> List[Tuple[str, str, Path]]:
    """Walk the partitioned runs tree and return (instrument, timeframe, run_dir) tuples."""
    base_path = Path(base)
    out: List[Tuple[str, str, Path]] = []
    if not base_path.exists():
        return out
    for inst_dir in base_path.iterdir():
        if not inst_dir.is_dir():
            continue
        for tf_dir in inst_dir.iterdir():
            if not tf_dir.is_dir():
                continue
            for run_dir in tf_dir.iterdir():
                if not run_dir.is_dir():
                    continue
                if (run_dir / "events.csv").exists():
                    out.append((inst_dir.name, tf_dir.name, run_dir))
    return out


def _load_events(events_csv: Path) -> pd.DataFrame:
    """Load events.csv into a DataFrame with usable types."""
    df = pd.read_csv(events_csv)
    # Coerce numeric columns we care about
    for col in ("Raw_Timestamp", "MFE_5", "MAE_5", "MFE_10", "MAE_10",
                "MFE_20", "MAE_20", "MFE_50", "MAE_50",
                "Open", "High", "Low", "Close"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # bar_index for hypothesis logic that needs it.
    # Fall back to the '#' row-number column if bar_index is absent or all-NaN.
    if "bar_index" in df.columns:
        df["bar_index"] = pd.to_numeric(df["bar_index"], errors="coerce")
    if ("bar_index" not in df.columns) or df["bar_index"].isna().all():
        if "#" in df.columns:
            df["bar_index"] = pd.to_numeric(df["#"], errors="coerce")
        else:
            df["bar_index"] = range(len(df))
    return df


def run_phase1(corpus_base: str, out_path: str) -> None:
    """Run all hypotheses on every slice; write summary CSV."""
    slices = discover_slices(corpus_base)
    logging.info(f"Discovered {len(slices)} slice(s) under {corpus_base}")

    # Group slices by instrument so multi-TF can pair HTF and LTF
    by_inst: dict = {}
    for inst, tf, rd in slices:
        by_inst.setdefault(inst, []).append((tf, rd))

    rows = []

    # 1. Single-DF hypotheses: priority + secondary, run per slice
    for inst, tf, rd in slices:
        try:
            df = _load_events(rd / "events.csv")
        except Exception as e:
            logging.exception(f"Failed loading {rd}: {e}")
            continue

        for hcls in PRIORITY_HYPOTHESES + SECONDARY_HYPOTHESES:
            try:
                h = hcls()
                result = h.evaluate(df)
                rows.append({
                    "hypothesis": h.name,
                    "instrument": inst,
                    "timeframe": tf,
                    "run_id": rd.name,
                    "sample_size": result.get("sample_size", 0),
                    "win_rate": result.get("win_rate", 0.0),
                    "avg_mfe_10": result.get("avg_mfe_10", 0.0),
                    "avg_mae_10": result.get("avg_mae_10", 0.0),
                })
            except Exception as e:
                logging.exception(f"Hypothesis {hcls.__name__} failed on {rd}: {e}")

    # 2. Multi-TF Reversal: pair each LTF with the highest-TF HTF for the same instrument
    # Pairs to try: (5, 60), (15, 60). Skip if either side is missing.
    for inst, tf_runs in by_inst.items():
        tf_to_run = dict(tf_runs)
        for ltf_tf in ("5", "15"):
            for htf_tf in ("60",):
                if ltf_tf not in tf_to_run or htf_tf not in tf_to_run:
                    continue
                ltf_df = _load_events(tf_to_run[ltf_tf] / "events.csv")
                htf_df = _load_events(tf_to_run[htf_tf] / "events.csv")
                try:
                    h = MultiTFReversalHypothesis()
                    h.set_parameters(htf=htf_tf, ltf=ltf_tf)
                    result = h.evaluate(ltf_df, htf_df)
                    rows.append({
                        "hypothesis": f"{h.name} (HTF={htf_tf}m, LTF={ltf_tf}m)",
                        "instrument": inst,
                        "timeframe": ltf_tf,
                        "run_id": tf_to_run[ltf_tf].name,
                        "sample_size": result.get("sample_size", 0),
                        "win_rate": result.get("win_rate", 0.0),
                        "avg_mfe_10": result.get("avg_mfe_10", 0.0),
                        "avg_mae_10": result.get("avg_mae_10", 0.0),
                    })
                except Exception as e:
                    logging.exception(f"MultiTFReversal failed on {inst} HTF={htf_tf} LTF={ltf_tf}: {e}")

    # Write CSV
    out_path_p = Path(out_path)
    out_path_p.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["hypothesis", "instrument", "timeframe", "run_id",
                  "sample_size", "win_rate", "avg_mfe_10", "avg_mae_10"]
    with out_path_p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    logging.info(f"Wrote {len(rows)} rows to {out_path_p}")


def main():
    parser = argparse.ArgumentParser(description="Phase 1 hypothesis edge-test driver")
    parser.add_argument("--corpus-base", required=True, help="Path to logs/backend/runs/")
    parser.add_argument("--out", required=True, help="Output summary CSV path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_phase1(args.corpus_base, args.out)


if __name__ == "__main__":
    main()