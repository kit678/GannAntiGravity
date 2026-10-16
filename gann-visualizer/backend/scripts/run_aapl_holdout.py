"""
The AAPL fresh holdout: one corpus under the breach rule the RELIANCE sweep
chose, read whole, once.

Refuses to run if the choice file is missing or null, if the results file or
its `.started` marker exists, or if the AAPL corpus directory already
exists. Writes the marker before any AAPL statistic is computed. Computes
only what the spec names: touch density, the pooled lag-free reach rate,
the 13 groups, the dropped shares and the verdict. The choice file must
also be committed before this runs (checked by hand; see the plan).

Spec: docs/superpowers/specs/2026-10-16-gann-breach-definition-sweep-design.md

Usage (from gann-visualizer/backend/), after scripts/load_aapl_bars.py:
    python scripts/run_aapl_holdout.py \
        --choice <repo>/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json \
        --cache C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/bars \
        --out C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/aapl_5m_x6 \
        --results <repo>/docs/superpowers/specs/2026-10-16-gann-aapl-holdout-results.md

--from, --to and --shadows exist for tests; the holdout uses the defaults.
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import List, Optional, Union

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from build_gann_corpus import ensure_corpus
from mine_gann_corpus import load_scored_events
from study_tool.corpus_writer import ALL_SLICES
from study_tool.mining.breach_sweep import (
    Verdict, aapl_verdict, read_choice, score_rule,
)
from study_tool.mining.sweep_report import render_aapl_results

SYMBOL = "AAPL"
FROM_DATE = "2024-09-02"
TO_DATE = "2026-09-01"
INTERVAL = "5"
# 228.86 (last close before the window, 2024-08-30) x 6 = 1373, matching
# RELIANCE's median 1375 at x1: the same relative sub-level spacing.
SCALE = 6
SHADOWS = 50
SEED = 7

PathLike = Union[str, Path]


def started_marker(results_path: PathLike) -> Path:
    """`<results>.started`: written once the look begins, never removed."""
    return Path(f"{results_path}.started")


def run_aapl(choice_path: PathLike, cache_dir: PathLike, out_dir: PathLike,
             results_path: PathLike, from_date: str = FROM_DATE,
             to_date: str = TO_DATE, shadows: int = SHADOWS) -> Verdict:
    """Build, read once, write the verdict. Returns the Verdict."""
    rule = read_choice(choice_path)            # before anything touches AAPL
    results_path = Path(results_path)
    marker = started_marker(results_path)
    if results_path.exists():
        raise FileExistsError(
            f"{results_path} exists: AAPL has been read already, and the "
            "holdout gets one look")
    if marker.exists():
        raise FileExistsError(
            f"{marker} exists: a look at AAPL was started already, and the "
            "holdout gets one look even if that run crashed")
    if Path(out_dir).exists():
        raise FileExistsError(
            f"{out_dir} already exists: the AAPL corpus is built by this "
            "command only, never reused")

    status = ensure_corpus(
        symbol=SYMBOL, from_date=from_date, to_date=to_date,
        interval=INTERVAL, price_scale=SCALE, shadow_count=shadows,
        seed=SEED, cache_dir=cache_dir, out_dir=out_dir,
        breach_mode=rule.breach_mode,
        confirmation_closes=rule.confirmation_closes)
    if status != "built":
        raise RuntimeError(
            f"ensure_corpus returned {status!r} for {out_dir}; the AAPL "
            "corpus must be built fresh by this command")
    print(f"AAPL corpus built under {rule.name}")

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        f"AAPL look started {time.strftime('%Y-%m-%d %H:%M')} under "
        f"{rule.name}\n", encoding="utf-8")

    scored = load_scored_events(out_dir, slice_name=ALL_SLICES)
    score = score_rule(rule.name, scored.events, scored.meta.shadow_count)
    verdict = aapl_verdict(score)

    context = {
        "rule": rule.name, "breach_mode": rule.breach_mode,
        "confirmation_closes": rule.confirmation_closes,
        "choice": str(choice_path), "corpus": str(out_dir),
        "price_scale": SCALE,
        "shadow_count": scored.meta.shadow_count,
        "rows": len(scored.events),
        "generated": time.strftime("%Y-%m-%d %H:%M"),
    }
    results_path.write_text(render_aapl_results(score, verdict, context),
                            encoding="utf-8")

    print(f"verdict: {verdict.label}")
    print(f"wrote {results_path}")
    return verdict


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--choice", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--from", dest="from_date", default=FROM_DATE)
    parser.add_argument("--to", dest="to_date", default=TO_DATE)
    parser.add_argument("--shadows", type=int, default=SHADOWS)
    args = parser.parse_args(argv)

    try:
        read_choice(args.choice)
    except (FileNotFoundError, ValueError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    run_aapl(choice_path=args.choice, cache_dir=args.cache, out_dir=args.out,
             results_path=args.results, from_date=args.from_date,
             to_date=args.to_date, shadows=args.shadows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
