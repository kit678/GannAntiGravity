"""
The corpus build metadata, as a typed object mining can rely on.

The shadow offsets are the reason this exists. A shadow ladder is the real
ladder plus a constant, so a shadow breach's next-level target is the real
next level plus that same constant. Get the constant wrong and the target sits
on an arbitrary price - but nothing crashes, and the report still prints a
percentage. So the check is here, at load time, and it fails loudly.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from study_tool.corpus_writer import load_meta

SUPPORTED_META_VERSION = 1


@dataclass(frozen=True)
class CorpusMeta:
    symbol: str
    from_date: str
    to_date: str
    interval: str
    price_scale: int
    shadow_count: int
    seed: int
    median_sub_gap: float
    shadow_offsets: List[float]
    resolution_window_bars: int
    bar_count: int

    def offset_for(self, shadow_id: Optional[float]) -> float:
        """
        The price shift applied to this shadow's ladder.

        Real events carry shadow_id None and an unshifted ladder, so they get
        0.0. Anything else must be a known shadow: defaulting an unknown id to
        zero would quietly measure a shadow against the real ladder's targets.
        """
        if shadow_id is None or (isinstance(shadow_id, float) and shadow_id != shadow_id):
            return 0.0
        index = int(shadow_id)
        if not 0 <= index < len(self.shadow_offsets):
            raise KeyError(
                f"shadow id {shadow_id} is outside the "
                f"{len(self.shadow_offsets)} offsets in meta.json"
            )
        return self.shadow_offsets[index]


def load_corpus_meta(corpus_dir: Union[str, Path]) -> CorpusMeta:
    """
    Read and validate meta.json.

    Raises:
        FileNotFoundError: naming the backfill script, because a corpus built
            before meta.json existed is the common case.
        ValueError: on an unsupported layout version.
    """
    try:
        raw = load_meta(corpus_dir)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"{corpus_dir} has no meta.json; mining cannot guess the shadow "
            "offsets. Run scripts/backfill_corpus_meta.py to write one."
        ) from exc

    version = raw["corpus_meta_version"]
    if version != SUPPORTED_META_VERSION:
        raise ValueError(
            f"corpus_meta_version {version} but this code supports "
            f"{SUPPORTED_META_VERSION}"
        )

    return CorpusMeta(
        symbol=raw["symbol"],
        from_date=raw["from_date"],
        to_date=raw["to_date"],
        interval=raw["interval"],
        price_scale=int(raw["price_scale"]),
        shadow_count=int(raw["shadow_count"]),
        seed=int(raw["seed"]),
        median_sub_gap=float(raw["median_sub_gap"]),
        shadow_offsets=[float(o) for o in raw["shadow_offsets"]],
        resolution_window_bars=int(raw["resolution_window_bars"]),
        bar_count=int(raw["bar_count"]),
    )
