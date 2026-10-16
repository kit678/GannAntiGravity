"""
Mine the Gann corpus against its shadow control and write the report.

Usage:
    python scripts/mine_gann_corpus.py --corpus logs/corpus/reliance_5m_x1 \
        --out docs/superpowers/reports

Defaults to the explore slice. Pass --slice holdout for the one-time
confirmation pass over the holdout slice, once a shortlist has been declared
against explore. Pass --slice all to read every row: for a corpus whose split
means nothing (RELIANCE after its holdout was spent on 2026-09-03) or a fresh
holdout read whole, once (AAPL, 2026-10-16 breach sweep).

The boundary buffer-drop exists only to protect explore events from having
their outcome decided by holdout price action, which sits chronologically
after explore. It runs for explore only: holdout is the last slice, and
`all` has no split to protect.
"""

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from study_tool.corpus_writer import ALL_SLICES, load_events
from study_tool.mining.boundary import boundary_bar_index, drop_boundary_events
from study_tool.mining.corpus_meta import CorpusMeta, load_corpus_meta
from study_tool.mining.groups import GROUPINGS, add_ring_bin, iter_groups
from study_tool.mining.ladder_rebuild import (
    LadderCache, add_reach_outcomes, outcome_column,
)
from study_tool.mining.report import GroupResult, render_report
from study_tool.mining.shadow_compare import compare
from study_tool.mining.statistics import (
    StatisticFn, already_hit_share, dropped_share, entry_dropped_share,
    hold_rate, lag_free_reach_rate, mean_retest_depth, reach_rate_for,
    rejection_rate, timeout_share_for, touch_density_fn,
)

SLICE_CHOICES = ("explore", "holdout", ALL_SLICES)


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


@dataclass
class ScoredCorpus:
    """One slice of a corpus with the reach race run, and how it was cut."""
    corpus_dir: Path
    events: pd.DataFrame
    meta: CorpusMeta
    slice_name: str
    boundary: Optional[int]   # None for --slice all: there is no split
    dropped_to_buffer: int
    sweep_columns: List[str]


def _load_slice(corpus_dir: Path, slice_name: str, boundary: Optional[int],
                buffer_bars: int) -> Tuple[pd.DataFrame, int]:
    """Events for the slice, and how many the boundary buffer dropped."""
    if slice_name == "explore":
        assert boundary is not None, "explore needs the holdout boundary"
        events = load_events(corpus_dir, slice_name="explore")
        buffered = drop_boundary_events(
            events, boundary=boundary, buffer_bars=buffer_bars)
        print(f"dropped {buffered.dropped} events inside the "
              f"{buffer_bars}-bar buffer")
        return buffered.events, buffered.dropped
    if slice_name == "holdout":
        # Holdout is the last slice - no data after it can leak into it.
        return load_events(corpus_dir, slice_name="holdout"), 0
    if slice_name == ALL_SLICES:
        # Every row: there is no split to protect.
        return load_events(corpus_dir, slice_name=ALL_SLICES), 0
    raise ValueError(
        f"unknown slice {slice_name!r}; expected one of {SLICE_CHOICES}")


def load_scored_events(corpus_dir: Union[str, Path],
                       slice_name: str = "explore",
                       stop_depths: Sequence[float] = (0.0,),
                       windows: Optional[Sequence[int]] = None) -> ScoredCorpus:
    """
    Load one slice, add level_ring_bin, and run the reach race.

    `stop_depths` and `windows` sweep the race: every pair gets its own
    outcome column. The defaults - depth 0 at the corpus's own resolution
    window - reproduce the strict test the confirmed result was measured
    with, and give `reach_outcome`, which the lag-free statistic reads.
    """
    corpus_dir = Path(corpus_dir)
    meta = load_corpus_meta(corpus_dir)

    boundary: Optional[int] = None
    if slice_name != ALL_SLICES:
        # Only bar_index and slice are read from the full events table, to
        # find the boundary. That is structural bookkeeping, not price
        # action, so it does not spend the holdout. --slice all skips it: a
        # corpus with no holdout rows has no boundary, and needs none.
        all_slices = pd.read_parquet(corpus_dir / "events.parquet",
                                     columns=["bar_index", "slice"])
        boundary = boundary_bar_index(all_slices)
        del all_slices
        print(f"explore/holdout boundary at bar {boundary}")

    events, dropped_to_buffer = _load_slice(
        corpus_dir, slice_name, boundary, meta.resolution_window_bars)
    events = add_ring_bin(events)

    bars = pd.read_parquet(corpus_dir / "bars.parquet")
    keys = pd.read_parquet(corpus_dir / "ladder_keys.parquet")
    _check_ladder_tables(bars, keys)

    started = time.time()
    cache = LadderCache(keys, meta.price_scale)
    events = add_reach_outcomes(events, bars, cache, meta,
                                stop_depths=stop_depths, windows=windows)

    resolved_windows = tuple(windows or (meta.resolution_window_bars,))
    sweep_columns = [outcome_column(d, w)
                     for d in stop_depths for w in resolved_windows]

    # Per sweep column, not `reach_outcome`. That alias only exists when the
    # sweep actually contains depth 0 at the corpus window.
    elapsed = time.time() - started
    raced = ", ".join(f"{c}={int(events[c].notna().sum())}"
                      for c in sweep_columns if c in events.columns)
    print(f"raced breaches in {elapsed:.0f}s: {raced or 'none'}")

    return ScoredCorpus(corpus_dir=corpus_dir, events=events, meta=meta,
                        slice_name=slice_name, boundary=boundary,
                        dropped_to_buffer=dropped_to_buffer,
                        sweep_columns=sweep_columns)


def mining_statistics(scored: ScoredCorpus) -> Dict[str, StatisticFn]:
    """Every statistic the report runs, by name."""
    bar_count = int(scored.events["bar_index"].nunique())
    statistics: Dict[str, StatisticFn] = {
        "hold_rate": hold_rate,
        "rejection_rate": rejection_rate,
        "mean_retest_depth": mean_retest_depth,
        "touch_density": touch_density_fn(bar_count),
        "already_hit_share": already_hit_share,
        "dropped_share": dropped_share,
        "entry_dropped_share": entry_dropped_share,
    }
    # lag_free_reach_rate reads reach_outcome, which only exists when the
    # sweep contains depth 0 at the corpus window. Without it the statistic
    # would report an all-None row for a reason that is not the data's.
    if "reach_outcome" in scored.events.columns:
        statistics["lag_free_reach_rate"] = lag_free_reach_rate
    for column in scored.sweep_columns:
        statistics[f"reach_rate[{column}]"] = reach_rate_for(column)
        statistics[f"timeout_share[{column}]"] = timeout_share_for(column)
    return statistics


def render_mining_report(scored: ScoredCorpus) -> str:
    """The standard mining report Markdown for an already-raced slice."""
    statistics = mining_statistics(scored)
    events, meta = scored.events, scored.meta

    results: List[GroupResult] = []
    for grouping in GROUPINGS:
        for label, rows in iter_groups(events, grouping):
            for name, fn in statistics.items():
                results.append(GroupResult(
                    grouping, label, name,
                    compare(rows, fn, shadow_count=meta.shadow_count)))

    context: Dict = {
        "slice": scored.slice_name,
        "corpus_dir": str(scored.corpus_dir),
        "symbol": meta.symbol,
        "interval": meta.interval,
        "price_scale": meta.price_scale,
        "shadow_count": meta.shadow_count,
        "explore_events": len(events),
        "dropped_to_buffer": scored.dropped_to_buffer,
        "boundary_bar_index": ("n/a (no split)" if scored.boundary is None
                               else scored.boundary),
        "buffer_bars": meta.resolution_window_bars,
        "touch_density": compare(events, statistics["touch_density"],
                                 shadow_count=meta.shadow_count),
    }
    return render_report(results, context)


def run(corpus_dir: Union[str, Path], slice_name: str = "explore",
        stop_depths: Sequence[float] = (0.0,),
        windows: Optional[Sequence[int]] = None) -> str:
    """Mine one corpus and return the report Markdown."""
    scored = load_scored_events(corpus_dir, slice_name=slice_name,
                                stop_depths=stop_depths, windows=windows)
    return render_mining_report(scored)


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--out", default="docs/superpowers/reports")
    parser.add_argument("--slice", choices=list(SLICE_CHOICES),
                        default="explore")
    parser.add_argument(
        "--stop-depths", default="0",
        help="comma-separated ladder steps behind the breached level to place "
             "the stop; 0 is the strict test (stop on the level itself)")
    parser.add_argument(
        "--windows", default="",
        help="comma-separated bar windows for the race; empty uses the "
             "corpus's own resolution_window_bars")
    args = parser.parse_args(argv)

    depths = tuple(float(d) for d in args.stop_depths.split(",") if d.strip())
    race_windows = tuple(int(w) for w in args.windows.split(",") if w.strip())
    text = run(Path(args.corpus), slice_name=args.slice,
               stop_depths=depths or (0.0,),
               windows=race_windows or None)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d-%H%M")
    path = out_dir / f"gann-mining-report-{stamp}.md"
    path.write_text(text, encoding="utf-8")

    print(text)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
