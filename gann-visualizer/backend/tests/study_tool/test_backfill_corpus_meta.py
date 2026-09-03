"""
Backfilling meta.json onto a corpus built before meta.json existed.

The test builds a tiny corpus with the real builder, deletes its meta.json,
backfills, and checks the offsets came back byte-identical. Anything weaker
would pass while producing plausible-looking wrong offsets.
"""
import sys
import os

import pandas as pd

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend/scripts'))

from build_gann_corpus import build_corpus
from backfill_corpus_meta import backfill_meta
from study_tool.corpus_writer import assign_slices, load_meta, write_corpus

NSE_OPEN_EPOCH = 1787629500


def synthetic_bars(n=60):
    rows = []
    for i in range(n):
        open_ = 1300.0 + i * 0.4
        close = open_ + 0.4
        rows.append({
            "open": open_, "high": close + 0.3, "low": open_ - 0.3,
            "close": close, "volume": 1000.0,
            "timestamp": float(NSE_OPEN_EPOCH + i * 300),
            "sun_degree": 155.0 + i * 0.0007,
            "moon_degree": (331.0 + i * 0.009) % 360,
        })
    return pd.DataFrame(rows)


def make_corpus(tmp_path):
    result = build_corpus(bars=synthetic_bars(), instrument="RELIANCE",
                          timeframe="5", price_scale=1, shadow_count=3, seed=7)
    meta = dict(result["meta"])
    meta["from_date"] = "2026-08-01"
    meta["to_date"] = "2026-08-31"
    write_corpus(tmp_path, events=assign_slices(result["events"]),
                 bars=result["bars"], ladder_keys=result["ladder_keys"],
                 meta=meta)
    return meta


def test_backfilled_offsets_match_the_original_exactly(tmp_path):
    original = make_corpus(tmp_path)
    (tmp_path / "meta.json").unlink()

    backfill_meta(tmp_path, symbol="RELIANCE", from_date="2026-08-01",
                  to_date="2026-08-31", interval="5", price_scale=1,
                  shadow_count=3, seed=7)

    restored = load_meta(tmp_path)
    assert restored["shadow_offsets"] == original["shadow_offsets"]
    assert restored["median_sub_gap"] == original["median_sub_gap"]


def test_backfill_refuses_to_clobber_an_existing_meta(tmp_path):
    make_corpus(tmp_path)

    import pytest
    with pytest.raises(FileExistsError, match="meta.json"):
        backfill_meta(tmp_path, symbol="RELIANCE", from_date="2026-08-01",
                      to_date="2026-08-31", interval="5", price_scale=1,
                      shadow_count=3, seed=7)


def test_backfill_checks_the_shadow_count_against_the_events(tmp_path):
    """
    Passing the wrong --shadows produces the wrong offset list, which would
    mis-target every shadow while the report still prints happily.
    """
    make_corpus(tmp_path)
    (tmp_path / "meta.json").unlink()

    import pytest
    with pytest.raises(ValueError, match="shadow"):
        backfill_meta(tmp_path, symbol="RELIANCE", from_date="2026-08-01",
                      to_date="2026-08-31", interval="5", price_scale=1,
                      shadow_count=7, seed=7)
