"""
Build the Gann level-interaction corpus and its shadow control.

Usage:
    python scripts/build_gann_corpus.py --symbol RELIANCE \
        --from 2024-09-02 --to 2026-09-01 --interval 5 --scale 1 \
        --shadows 50 --out logs/corpus/reliance_5m_x1

    --breach-mode close|wick and --confirmation-closes N set the breach rule
    (defaults close / 2, the rule every corpus before 2026-10-16 used).
    --no-fetch makes a bar-cache miss raise instead of calling Dhan.

The ladder is built once per distinct (price square, sun square, moon square)
and every shadow is derived from that build by adding a constant. Grid
construction is 27 ms at scale 10 and dominates the run; rebuilding per shadow
turns roughly 3 hours into roughly 67.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Union

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from study_tool.bar_cache import load_bars, no_fetch
from study_tool.corpus_writer import (
    META_FILENAME, assign_slices, load_meta, write_corpus,
)
from study_tool.event_logger import EventLogger
from study_tool.gann_ladder_analyzer import BREACH_MODES, GannLadderAnalyzer
from study_tool.run_ladder_study import build_all_ladders, degree_to_square
from study_tool.shadow_ladder import shadow_offsets, shift_ladder

HORIZON_CANDLE_KEY = "time"


def _analyzer_settings(instrument: str, timeframe: str, price_scale: int,
                       breach_mode: str = "close",
                       confirmation_closes: int = 2) -> Dict:
    if breach_mode not in BREACH_MODES:
        raise ValueError(
            f"breach_mode {breach_mode!r} is not one of {BREACH_MODES}")
    try:
        whole = (not isinstance(confirmation_closes, bool)
                 and int(confirmation_closes) == confirmation_closes)
    except (TypeError, ValueError, OverflowError):  # None, "two", nan, inf
        whole = False
    if not whole or int(confirmation_closes) < 1:
        raise ValueError(
            "confirmation_closes must be a whole number of at least 1, "
            f"got {confirmation_closes!r}")
    return {
        "breach_mode": breach_mode,
        "confirmation_closes": int(confirmation_closes),
        "touch_tolerance_sublevels": 0.1,
        "resolution_window_bars": 50,
        "retest_window_bars": 50,
        "instrument": instrument,
        "timeframe": timeframe,
        "price_scale": price_scale,
    }


def _median_sub_gap(levels: List[Dict], price_scale: int) -> float:
    """Typical sub-level width in price, used to bound the shadow offsets."""
    gaps = [
        abs(l["segment_end"] - l["segment_start"]) / 8.0 / price_scale
        for l in levels
        if l.get("segment_start") is not None
        and l.get("segment_end") is not None
        and l["segment_end"] != l["segment_start"]
    ]
    if not gaps:
        return 1.0
    gaps.sort()
    return gaps[len(gaps) // 2]


def _candles_for_enrichment(bars: pd.DataFrame) -> List[Dict]:
    return [
        {HORIZON_CANDLE_KEY: int(row.timestamp), "open": row.open,
         "high": row.high, "low": row.low, "close": row.close}
        for row in bars.itertuples()
    ]


def _walk(bars: pd.DataFrame, ladders_by_bar: List[List[Dict]],
          settings: Dict) -> List:
    analyzer = GannLadderAnalyzer(settings)
    events = []
    for index, row in enumerate(bars.itertuples()):
        bar = {"open": row.open, "high": row.high, "low": row.low,
               "close": row.close, "timestamp": int(row.timestamp)}
        events.extend(analyzer.process_bar(bar, index, ladders_by_bar[index]))
    events.extend(analyzer.finalize())
    return events


def _events_to_frame(events: List, candles: List[Dict],
                     shadow_id: Optional[int]) -> pd.DataFrame:
    logger = EventLogger()
    logger.events = events
    logger.enrich_with_forward_outcomes(candles)

    frame = pd.DataFrame([event.to_dict() for event in events])
    frame["shadow_id"] = shadow_id

    # to_dict emits two dict-valued columns, which Parquet cannot store as-is.
    # The breach outcome lives inside `details` and is the single most-queried
    # field in the corpus, so it is lifted into a real column; the rest of
    # details is kept verbatim as JSON so nothing is lost.
    if "details" in frame.columns:
        frame["outcome"] = frame["details"].apply(
            lambda d: d.get("outcome") if isinstance(d, dict) else None)
    for column in ("details", "active_angle_prices"):
        if column in frame.columns:
            frame[column] = frame[column].apply(
                lambda v: json.dumps(v) if isinstance(v, (dict, list)) else v)

    return frame


CORPUS_META_VERSION = 1


def build_corpus(bars: pd.DataFrame, instrument: str, timeframe: str,
                 price_scale: int, shadow_count: int, seed: int,
                 breach_mode: str = "close",
                 confirmation_closes: int = 2) -> Dict:
    """
    Walk `bars` against the real ladder and `shadow_count` shifted ones.

    Returns a dict with `events`, `bars`, `ladder_keys` and `meta`. The meta
    carries the shadow offsets, which nothing downstream can recompute, and
    the breach rule, which mining needs to find each breach's cross bar.
    Shadows walk with the same settings, so they get the same breach rule.
    """
    settings = _analyzer_settings(instrument, timeframe, price_scale,
                                  breach_mode, confirmation_closes)

    # One grid build per distinct key. Everything else reuses the result.
    cache: Dict = {}
    keys: List[Dict] = []
    real_by_bar: List[List[Dict]] = []

    for index, row in enumerate(bars.itertuples()):
        price_square = int(round(row.close * price_scale))
        sun_square = degree_to_square(row.sun_degree)
        moon_square = degree_to_square(row.moon_degree)
        key = (price_square, sun_square, moon_square)

        if key not in cache:
            cache[key] = build_all_ladders(
                row.close, price_scale, sun_square, moon_square)

        real_by_bar.append(cache[key])
        keys.append({"bar_index": index, "price_square": price_square,
                     "sun_square": sun_square, "moon_square": moon_square})

    all_levels = [lv for ladder in cache.values() for lv in ladder]
    gap = _median_sub_gap(all_levels, price_scale)
    offsets = shadow_offsets(shadow_count, gap, seed)

    # Built once and reused for every walk (real + each shadow): the candles
    # are derived from `bars` alone, which none of those walks mutate, so
    # rebuilding this per walk would be O(bars * shadow_count) of pure waste.
    candles = _candles_for_enrichment(bars)

    frames = [_events_to_frame(_walk(bars, real_by_bar, settings), candles, None)]

    for shadow_id, delta in enumerate(offsets):
        shifted_cache = {
            key: shift_ladder(ladder, delta, price_scale)
            for key, ladder in cache.items()
        }
        shadow_by_bar = [
            shifted_cache[(k["price_square"], k["sun_square"], k["moon_square"])]
            for k in keys
        ]
        frames.append(_events_to_frame(
            _walk(bars, shadow_by_bar, settings), candles, shadow_id))

    return {
        "events": pd.concat(frames, ignore_index=True),
        "bars": bars.reset_index(drop=True),
        "ladder_keys": pd.DataFrame(keys),
        "meta": {
            "corpus_meta_version": CORPUS_META_VERSION,
            "symbol": instrument,
            "interval": timeframe,
            "price_scale": price_scale,
            "shadow_count": shadow_count,
            "seed": seed,
            "median_sub_gap": gap,
            "shadow_offsets": list(offsets),
            "resolution_window_bars": settings["resolution_window_bars"],
            "bar_count": int(len(bars)),
            "breach_mode": settings["breach_mode"],
            "confirmation_closes": settings["confirmation_closes"],
        },
    }


def build_to_disk(symbol: str, from_date: str, to_date: str, interval: str,
                  price_scale: int, shadow_count: int, seed: int,
                  cache_dir: Union[str, Path], out_dir: Union[str, Path],
                  breach_mode: str = "close", confirmation_closes: int = 2,
                  overwrite: bool = False,
                  allow_fetch: bool = True) -> pd.DataFrame:
    """
    Load bars, build the corpus, write it. Returns the slice-stamped events.

    allow_fetch=False passes bar_cache.no_fetch, so a cache miss raises
    instead of calling Dhan. Every sweep and holdout build uses that.
    """
    bars = load_bars(symbol, from_date, to_date, interval,
                     cache_dir=cache_dir,
                     fetcher=None if allow_fetch else no_fetch)
    print(f"{len(bars)} bars {from_date}..{to_date}")

    result = build_corpus(
        bars=bars, instrument=symbol, timeframe=interval,
        price_scale=price_scale, shadow_count=shadow_count, seed=seed,
        breach_mode=breach_mode, confirmation_closes=confirmation_closes)

    events = assign_slices(result["events"], order_column="bar_index")
    meta = dict(result["meta"])
    meta["from_date"] = from_date
    meta["to_date"] = to_date
    write_corpus(Path(out_dir), events=events, bars=result["bars"],
                 ladder_keys=result["ladder_keys"], meta=meta,
                 overwrite=overwrite)
    return events


def ensure_corpus(symbol: str, from_date: str, to_date: str, interval: str,
                  price_scale: int, shadow_count: int, seed: int,
                  cache_dir: Union[str, Path], out_dir: Union[str, Path],
                  breach_mode: str, confirmation_closes: int) -> str:
    """
    Build the corpus at `out_dir` unless the same build is already there.

    Returns "built" or "reused". Never fetches.

    write_corpus writes meta.json last, so a meta.json on disk means a
    finished corpus. A build killed mid-write leaves tables without meta;
    write_corpus then refuses to overwrite them, and the directory has to be
    removed by hand.

    A corpus already there with any different setting is an error, never
    reused and never overwritten: a sweep that silently scored the wrong
    breach rule would still print a choice.
    """
    wanted = {
        "symbol": symbol, "from_date": from_date, "to_date": to_date,
        "interval": str(interval), "price_scale": int(price_scale),
        "shadow_count": int(shadow_count), "seed": int(seed),
        "breach_mode": breach_mode,
        "confirmation_closes": int(confirmation_closes),
    }
    if (Path(out_dir) / META_FILENAME).exists():
        found = dict(load_meta(out_dir))
        unrecorded = [key for key in ("breach_mode", "confirmation_closes")
                      if key not in found]
        if unrecorded:
            raise ValueError(
                f"{out_dir} was built before the breach rule was recorded "
                f"(meta.json lacks {unrecorded}); it is never reused, "
                "because nothing says which rule produced it")
        mismatched = {key: (found.get(key), value)
                      for key, value in wanted.items()
                      if found.get(key) != value}
        if mismatched:
            raise ValueError(
                f"{out_dir} already holds a corpus built with different "
                f"settings (found, wanted): {mismatched}"
            )
        return "reused"

    leftovers = sorted(Path(out_dir).glob("*.parquet")) if Path(out_dir).is_dir() else []
    if leftovers:
        raise FileExistsError(
            f"{out_dir} holds {[p.name for p in leftovers]} but no "
            f"{META_FILENAME}: a half-written corpus. Remove the directory "
            "by hand; nothing was rebuilt.")

    build_to_disk(symbol=symbol, from_date=from_date, to_date=to_date,
                  interval=str(interval), price_scale=price_scale,
                  shadow_count=shadow_count, seed=seed, cache_dir=cache_dir,
                  out_dir=out_dir, breach_mode=breach_mode,
                  confirmation_closes=confirmation_closes,
                  allow_fetch=False)
    return "built"


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="RELIANCE")
    parser.add_argument("--from", dest="from_date", required=True)
    parser.add_argument("--to", dest="to_date", required=True)
    parser.add_argument("--interval", default="5")
    parser.add_argument("--scale", type=int, default=1)
    parser.add_argument("--shadows", type=int, default=50)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--cache", default="logs/corpus/bars")
    parser.add_argument("--out", required=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--breach-mode", choices=list(BREACH_MODES),
                        default="close",
                        help="close: travel through the level; wick: the "
                             "previous close on one side, the range past it")
    parser.add_argument("--confirmation-closes", type=int, default=2,
                        help="consecutive bars needed to confirm a breach")
    parser.add_argument("--no-fetch", action="store_true",
                        help="raise on a bar-cache miss instead of fetching")
    args = parser.parse_args(argv)

    events = build_to_disk(
        symbol=args.symbol, from_date=args.from_date, to_date=args.to_date,
        interval=args.interval, price_scale=args.scale,
        shadow_count=args.shadows, seed=args.seed, cache_dir=args.cache,
        out_dir=args.out, breach_mode=args.breach_mode,
        confirmation_closes=args.confirmation_closes,
        overwrite=args.overwrite, allow_fetch=not args.no_fetch)

    real = events[events["shadow_id"].isna()]
    print(f"\nwrote {args.out}")
    print(f"  real events   : {len(real)}")
    print(f"  shadow events : {len(events) - len(real)}")
    print(f"\nreal events by type:")
    print(real["event_type"].value_counts().to_string())
    print(f"\nreal breach outcomes:")
    resolved = real[real["event_type"] == "LADDER_BREACH_RESOLVED"]
    if len(resolved):
        print(resolved["outcome"].value_counts(dropna=False).to_string())
    else:
        print("  none")


if __name__ == "__main__":
    main()
