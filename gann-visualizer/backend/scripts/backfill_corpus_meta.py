"""
Write meta.json for a corpus built before meta.json existed.

Usage:
    python scripts/backfill_corpus_meta.py \
        --corpus logs/corpus/reliance_5m_x1 \
        --symbol RELIANCE --from 2024-09-02 --to 2026-09-01 \
        --interval 5 --scale 1 --shadows 50 --seed 7

The shadow offsets are a pure function of the ladder keys, the price scale and
the seed - all of which the corpus already stores or the operator already knows
- so they are recomputed here rather than paying a ~40 minute rebuild that also
needs a live Dhan token.

The build's own _median_sub_gap is imported rather than copied. A second copy
would drift, and a drifted gap yields offsets that look plausible and are
wrong. The coupling stops here: mining reads meta.json and recomputes nothing.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Dict, Union

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from build_gann_corpus import CORPUS_META_VERSION, _analyzer_settings, _median_sub_gap
from study_tool.corpus_writer import META_FILENAME, _validate_meta
from study_tool.run_ladder_study import build_all_ladders
from study_tool.shadow_ladder import shadow_offsets

import json


def _rebuild_all_distinct_ladders(keys: pd.DataFrame, price_scale: int):
    """
    Every distinct ladder in the corpus, built once each.

    build_all_ladders uses `price` only as int(round(price * price_scale)),
    which is exactly the stored price_square, so dividing back out reproduces
    the build's ladder with no approximation.
    """
    distinct = keys[["price_square", "sun_square", "moon_square"]].drop_duplicates()
    levels = []
    for row in distinct.itertuples():
        levels.extend(build_all_ladders(
            row.price_square / price_scale, price_scale,
            int(row.sun_square), int(row.moon_square)))
    return levels


def backfill_meta(corpus_dir: Union[str, Path], symbol: str, from_date: str,
                  to_date: str, interval: str, price_scale: int,
                  shadow_count: int, seed: int) -> Dict:
    """
    Recompute and write meta.json. Returns the meta it wrote.

    Raises:
        FileExistsError: if meta.json is already there. It may hold the real
            offsets from the build; overwriting them with recomputed ones
            would destroy the only authoritative copy.
        ValueError: if `shadow_count` disagrees with the shadow ids actually
            present in the events. A wrong count produces a wrong offset list
            that mis-targets every shadow while the report still prints.
    """
    corpus_dir = Path(corpus_dir)
    meta_path = corpus_dir / META_FILENAME
    if meta_path.exists():
        raise FileExistsError(f"{meta_path} already exists; nothing to backfill")

    events = pd.read_parquet(corpus_dir / "events.parquet",
                             columns=["shadow_id"])
    present = int(events["shadow_id"].dropna().nunique())
    if present != shadow_count:
        raise ValueError(
            f"--shadows {shadow_count} but the events hold {present} distinct "
            "shadow ids; the offset list would not line up"
        )

    keys = pd.read_parquet(corpus_dir / "ladder_keys.parquet")
    levels = _rebuild_all_distinct_ladders(keys, price_scale)
    gap = _median_sub_gap(levels, price_scale)
    offsets = shadow_offsets(shadow_count, gap, seed)

    bars = pd.read_parquet(corpus_dir / "bars.parquet", columns=["timestamp"])

    meta = {
        "corpus_meta_version": CORPUS_META_VERSION,
        "symbol": symbol,
        "from_date": from_date,
        "to_date": to_date,
        "interval": interval,
        "price_scale": price_scale,
        "shadow_count": shadow_count,
        "seed": seed,
        "median_sub_gap": gap,
        "shadow_offsets": list(offsets),
        "resolution_window_bars":
            _analyzer_settings(symbol, interval, price_scale)["resolution_window_bars"],
        "bar_count": int(len(bars)),
        "backfilled": True,
    }
    _validate_meta(meta)
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True),
                         encoding="utf-8")
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--symbol", default="RELIANCE")
    parser.add_argument("--from", dest="from_date", required=True)
    parser.add_argument("--to", dest="to_date", required=True)
    parser.add_argument("--interval", default="5")
    parser.add_argument("--scale", type=int, default=1)
    parser.add_argument("--shadows", type=int, default=50)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    meta = backfill_meta(args.corpus, symbol=args.symbol,
                         from_date=args.from_date, to_date=args.to_date,
                         interval=args.interval, price_scale=args.scale,
                         shadow_count=args.shadows, seed=args.seed)

    print(f"wrote {Path(args.corpus) / META_FILENAME}")
    print(f"  median sub gap : {meta['median_sub_gap']:.6f}")
    print(f"  offsets        : {len(meta['shadow_offsets'])}")
    print(f"  first three    : {[round(o, 6) for o in meta['shadow_offsets'][:3]]}")


if __name__ == "__main__":
    main()
