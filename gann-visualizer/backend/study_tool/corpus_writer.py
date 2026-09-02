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

import math
from pathlib import Path
from typing import Union

import pandas as pd

SLICES = ("explore", "holdout")
TABLES = ("events", "bars", "ladder_keys")


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


def write_corpus(corpus_dir: Union[str, Path], events: pd.DataFrame,
                 bars: pd.DataFrame, ladder_keys: pd.DataFrame,
                 overwrite: bool = False) -> None:
    """
    Write all three tables as Parquet.

    Refuses to touch a directory that already holds any of the three files
    unless overwrite=True. A corpus can take hours to build, and to_parquet
    would otherwise replace it with no warning.
    """
    corpus_dir = Path(corpus_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)

    if not overwrite:
        existing = [name for name in TABLES
                    if (corpus_dir / f"{name}.parquet").exists()]
        if existing:
            raise FileExistsError(
                f"{corpus_dir} already has {existing}; pass overwrite=True to replace"
            )

    for name, frame in zip(TABLES, (events, bars, ladder_keys)):
        frame.to_parquet(corpus_dir / f"{name}.parquet", index=False)


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
