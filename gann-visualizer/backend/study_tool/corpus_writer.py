"""
The corpus on disk.

Three tables:
  events       - one row per level interaction, real and shadow
  bars         - the OHLC used, with the Sun and Moon degree per bar
  ladder_keys  - (bar_index, price_square, sun_square, moon_square)

ladder_keys stores the ladder as its inputs rather than as a snapshot.
build_all_ladders is a pure function of exactly those three integers, so any
ladder is reconstructible on demand. A snapshot per rebuild would be roughly 63
million rows on the x10 corpus, because the price square changes on nearly
every bar.

The explore/holdout split is stamped into the data rather than left as a
convention, and the loader defaults to explore, so reaching the holdout takes a
deliberate argument and shows up in code review.
"""

import json
import math
from pathlib import Path
from typing import Dict, Union

import pandas as pd

SLICES = ("explore", "holdout")
TABLES = ("events", "bars", "ladder_keys")
META_FILENAME = "meta.json"

# Everything the mining phase needs and cannot recover from the events.
REQUIRED_META_FIELDS = (
    "corpus_meta_version", "symbol", "from_date", "to_date", "interval",
    "price_scale", "shadow_count", "seed", "median_sub_gap",
    "shadow_offsets", "resolution_window_bars", "bar_count",
)


def assign_slices(events: pd.DataFrame, holdout_fraction: float = 0.25,
                  order_column: str = "bar_index") -> pd.DataFrame:
    """
    Stamp each row `explore` or `holdout`, split by time.

    The split is by time, never at random: a random split puts future bars in
    the explore set, and the holdout then measures nothing.
    """
    frame = events.sort_values(order_column).reset_index(drop=True).copy()
    holdout_rows = math.ceil(len(frame) * holdout_fraction)
    cutoff = len(frame) - holdout_rows

    frame["slice"] = ["explore"] * cutoff + ["holdout"] * holdout_rows
    return frame


def _validate_meta(meta: Dict) -> None:
    missing = [f for f in REQUIRED_META_FIELDS if f not in meta]
    if missing:
        raise ValueError(f"meta is missing {missing}")

    if len(meta["shadow_offsets"]) != meta["shadow_count"]:
        raise ValueError(
            f"shadow_offsets has {len(meta['shadow_offsets'])} entries but "
            f"shadow_count is {meta['shadow_count']}; a short list would "
            "silently mis-target most shadows"
        )


def write_corpus(corpus_dir: Union[str, Path], events: pd.DataFrame,
                 bars: pd.DataFrame, ladder_keys: pd.DataFrame,
                 meta: Dict, overwrite: bool = False) -> None:
    """
    Write the three tables as Parquet, plus meta.json.

    `meta` is required, not optional. The shadow offsets it carries are not
    recoverable from the events - joining real to shadow on
    (bar_index, source, degree, sub_index) yields 178-182 conflicting deltas
    per shadow - so a corpus written without them cannot be mined at all. An
    optional argument would let that gap reappear silently.

    Refuses to touch a directory that already holds any corpus file unless
    overwrite=True. A corpus can take hours to build, and to_parquet would
    otherwise replace it with no warning.
    """
    _validate_meta(meta)

    corpus_dir = Path(corpus_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)

    if not overwrite:
        existing = [name for name in TABLES
                    if (corpus_dir / f"{name}.parquet").exists()]
        if (corpus_dir / META_FILENAME).exists():
            existing.append(META_FILENAME)
        if existing:
            raise FileExistsError(
                f"{corpus_dir} already has {existing}; pass overwrite=True to replace"
            )

    for name, frame in zip(TABLES, (events, bars, ladder_keys)):
        frame.to_parquet(corpus_dir / f"{name}.parquet", index=False)

    (corpus_dir / META_FILENAME).write_text(
        json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")


def load_meta(corpus_dir: Union[str, Path]) -> Dict:
    """
    The corpus build metadata.

    Raises:
        FileNotFoundError: if meta.json is absent. Guessing the offsets is
            worse than stopping - a wrong offset puts every shadow's
            next-level target on the wrong price and the report still prints.
    """
    path = Path(corpus_dir) / META_FILENAME
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found; run scripts/backfill_corpus_meta.py for a "
            "corpus built before meta.json existed"
        )
    meta = json.loads(path.read_text(encoding="utf-8"))
    _validate_meta(meta)
    return meta


def load_events(corpus_dir: Union[str, Path],
                slice_name: str = "explore") -> pd.DataFrame:
    """
    Events for one slice. Defaults to `explore`.

    Getting the holdout requires naming it. The holdout is consumable - each
    look followed by a change turns it into training data - so it should not
    arrive by default.
    """
    if slice_name not in SLICES:
        raise ValueError(
            f"unknown slice {slice_name!r}; expected one of {SLICES}"
        )
    frame = pd.read_parquet(Path(corpus_dir) / "events.parquet")
    return frame[frame["slice"] == slice_name].reset_index(drop=True)
