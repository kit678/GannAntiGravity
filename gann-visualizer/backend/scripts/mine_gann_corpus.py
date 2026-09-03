"""
Mine the Gann corpus against its shadow control and write the report.

Usage:
    python scripts/mine_gann_corpus.py --corpus logs/corpus/reliance_5m_x1 \
        --out docs/superpowers/reports

Defaults to the explore slice. Pass --slice holdout for the one-time
confirmation pass over the holdout slice, once a shortlist has been declared
against explore. The boundary buffer-drop exists only to protect explore
events from having their outcome decided by holdout price action, which sits
chronologically after explore; holdout is the last slice, so that drop does
not apply and does not run when mining it.
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Dict, List

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from study_tool.corpus_writer import load_events
from study_tool.mining.boundary import boundary_bar_index, drop_boundary_events
from study_tool.mining.corpus_meta import load_corpus_meta
from study_tool.mining.groups import GROUPINGS, add_ring_bin, iter_groups
from study_tool.mining.ladder_rebuild import LadderCache, add_reach_outcomes
from study_tool.mining.report import GroupResult, render_report
from study_tool.mining.shadow_compare import compare
from study_tool.mining.statistics import (
    hold_rate, mean_retest_depth, reach_next_rate, rejection_rate,
    timeout_share, touch_density_fn,
)


def _check_ladder_tables(bars: pd.DataFrame, keys: pd.DataFrame) -> None:
    """
    A duplicate bar_index in ladder_keys would silently overwrite in
    LadderCache's internal dict, mis-racing every event built from that bar.
    Bars must also cover every bar_index the keys reference, or
    race_to_next_level would silently read past valid data. Both failures are
    the kind that produce a plausible-looking wrong report rather than a
    crash, so they are checked here and raised loudly instead.
    """
    if not keys["bar_index"].is_unique:
        dupes = keys.loc[keys["bar_index"].duplicated(), "bar_index"].unique()
        raise ValueError(
            f"ladder_keys has duplicate bar_index values {list(dupes)[:5]}; "
            "LadderCache would silently overwrite one with the other"
        )

    max_key_bar = int(keys["bar_index"].max())
    if len(bars) < max_key_bar + 1:
        raise ValueError(
            f"bars has {len(bars)} rows but ladder_keys references bar_index "
            f"up to {max_key_bar}; race_to_next_level would read past the "
            "end of bars"
        )


def run(corpus_dir: Path, slice_name: str = "explore") -> str:
    """Mine one corpus and return the report Markdown."""
    meta = load_corpus_meta(corpus_dir)

    # Only bar_index and slice are read from the full events table, to find
    # the boundary. That is structural bookkeeping, not price action, so it
    # does not spend the holdout. Computed unconditionally for context/display
    # even when mining holdout, since it is cheap and useful either way.
    all_slices = pd.read_parquet(corpus_dir / "events.parquet",
                                 columns=["bar_index", "slice"])
    boundary = boundary_bar_index(all_slices)
    del all_slices

    print(f"explore/holdout boundary at bar {boundary}")

    if slice_name == "explore":
        events = load_events(corpus_dir, slice_name="explore")
        buffered = drop_boundary_events(
            events, boundary=boundary, buffer_bars=meta.resolution_window_bars)
        print(f"dropped {buffered.dropped} events inside the "
              f"{meta.resolution_window_bars}-bar buffer")
        events = buffered.events
        dropped_to_buffer = buffered.dropped
    else:
        # The buffer-drop exists only to protect explore events from having
        # their outcome decided by holdout price action, which sits
        # chronologically after explore. Holdout is the last slice - there is
        # no data after it that could leak into it - so the buffer-drop does
        # not apply here and must not run.
        events = load_events(corpus_dir, slice_name="holdout")
        dropped_to_buffer = 0

    events = add_ring_bin(events)

    bars = pd.read_parquet(corpus_dir / "bars.parquet")
    keys = pd.read_parquet(corpus_dir / "ladder_keys.parquet")
    _check_ladder_tables(bars, keys)

    started = time.time()
    cache = LadderCache(keys, meta.price_scale)
    events = add_reach_outcomes(events, bars, cache, meta)
    print(f"raced {int(events['reach_outcome'].notna().sum())} breaches "
          f"in {time.time() - started:.0f}s")

    bar_count = int(events["bar_index"].nunique())
    statistics = {
        "hold_rate": hold_rate,
        "rejection_rate": rejection_rate,
        "reach_next_rate": reach_next_rate,
        "timeout_share": timeout_share,
        "mean_retest_depth": mean_retest_depth,
        "touch_density": touch_density_fn(bar_count),
    }

    results: List[GroupResult] = []
    for grouping in GROUPINGS:
        for label, rows in iter_groups(events, grouping):
            for name, fn in statistics.items():
                results.append(GroupResult(
                    grouping, label, name,
                    compare(rows, fn, shadow_count=meta.shadow_count)))

    context: Dict = {
        "slice": slice_name,
        "corpus_dir": str(corpus_dir),
        "symbol": meta.symbol,
        "interval": meta.interval,
        "price_scale": meta.price_scale,
        "shadow_count": meta.shadow_count,
        "explore_events": len(events),
        "dropped_to_buffer": dropped_to_buffer,
        "boundary_bar_index": boundary,
        "buffer_bars": meta.resolution_window_bars,
        "touch_density": compare(events, statistics["touch_density"],
                                 shadow_count=meta.shadow_count),
    }
    return render_report(results, context)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--out", default="docs/superpowers/reports")
    parser.add_argument("--slice", choices=["explore", "holdout"],
                        default="explore")
    args = parser.parse_args()

    text = run(Path(args.corpus), slice_name=args.slice)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d-%H%M")
    path = out_dir / f"gann-mining-report-{stamp}.md"
    path.write_text(text, encoding="utf-8")

    print(text)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
