"""
Mining a whole corpus (--slice all), and the lag-free statistics in the
report. Synthetic corpus, no network, no 113 MB of Parquet.
"""
import sys
import os

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend/scripts'))

from build_gann_corpus import build_corpus
from mine_gann_corpus import load_scored_events, run
from study_tool.corpus_writer import assign_slices, write_corpus


def tiny_corpus(corpus_dir, with_holdout=True):
    epoch = 1787629500
    rows = []
    for i in range(400):
        open_ = 1300.0 + (i % 40) * 0.6
        close = open_ + 0.5
        rows.append({"open": open_, "high": close + 0.4, "low": open_ - 0.4,
                     "close": close, "volume": 1000.0,
                     "timestamp": float(epoch + i * 300),
                     "sun_degree": 155.0 + i * 0.0007,
                     "moon_degree": (331.0 + i * 0.009) % 360})
    result = build_corpus(bars=pd.DataFrame(rows), instrument="RELIANCE",
                          timeframe="5", price_scale=1, shadow_count=3, seed=7)
    meta = dict(result["meta"])
    meta["from_date"], meta["to_date"] = "2026-08-01", "2026-08-31"
    events = assign_slices(result["events"])
    if not with_holdout:
        events["slice"] = "explore"
    write_corpus(corpus_dir, events=events,
                 bars=result["bars"], ladder_keys=result["ladder_keys"],
                 meta=meta)
    return len(pd.read_parquet(corpus_dir / "events.parquet"))


def test_load_scored_events_all_returns_every_row_with_lag_free_columns(tmp_path):
    total = tiny_corpus(tmp_path)

    scored = load_scored_events(tmp_path, slice_name="all")

    assert len(scored.events) == total
    assert scored.slice_name == "all"
    assert scored.dropped_to_buffer == 0
    for column in ("reach_outcome", "target_hit_before_entry",
                   "entry_beyond_level", "level_ring_bin"):
        assert column in scored.events.columns
    # Not just present: a column of all None would pass the loop above.
    assert scored.events["target_hit_before_entry"].notna().any()


def test_slice_all_mines_every_row_without_the_buffer_drop(tmp_path):
    total = tiny_corpus(tmp_path)

    text = run(tmp_path, slice_name="all")

    run_section = text.split("## Run")[1].split("## Fairness")[0]
    assert "slice: all" in run_section
    assert f"all events used: {total}" in run_section
    assert "dropped to the boundary buffer: 0" in run_section


def test_the_report_carries_the_lag_free_statistics(tmp_path):
    tiny_corpus(tmp_path)

    text = run(tmp_path, slice_name="all")

    for name in ("lag_free_reach_rate", "dropped_share", "entry_dropped_share"):
        assert f"### {name}" in text, f"missing {name}"


def test_an_unknown_slice_is_refused(tmp_path):
    tiny_corpus(tmp_path)

    with pytest.raises(ValueError, match="unknown slice"):
        run(tmp_path, slice_name="test")


def test_the_command_line_accepts_slice_all(tmp_path):
    import mine_gann_corpus as miner
    corpus, out = tmp_path / "corpus", tmp_path / "reports"
    corpus.mkdir()
    tiny_corpus(corpus)

    miner.main(["--corpus", str(corpus), "--out", str(out), "--slice", "all"])

    reports = list(out.glob("gann-mining-report-*.md"))
    assert len(reports) == 1
    assert "slice: all" in reports[0].read_text(encoding="utf-8")


def test_slice_all_needs_no_holdout_rows(tmp_path):
    """A corpus with no holdout has no boundary; --slice all must not ask."""
    total = tiny_corpus(tmp_path, with_holdout=False)

    scored = load_scored_events(tmp_path, slice_name="all")

    assert len(scored.events) == total
    assert scored.boundary is None
    text = run(tmp_path, slice_name="all")
    assert "slice: all" in text


def test_explore_still_refuses_a_corpus_with_no_holdout(tmp_path):
    tiny_corpus(tmp_path, with_holdout=False)

    with pytest.raises(ValueError, match="no holdout rows"):
        load_scored_events(tmp_path, slice_name="explore")


def test_lag_free_reach_rate_is_absent_without_the_strict_column(tmp_path):
    tiny_corpus(tmp_path)

    scored = load_scored_events(tmp_path, slice_name="all", stop_depths=(1.0,))

    assert "reach_outcome" not in scored.events.columns
    from mine_gann_corpus import mining_statistics
    names = mining_statistics(scored)
    assert "lag_free_reach_rate" not in names
    assert "dropped_share" in names


def test_run_refuses_an_aapl_corpus(tmp_path):
    import json
    tiny_corpus(tmp_path)
    meta_path = tmp_path / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["symbol"] = "AAPL"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    with pytest.raises(ValueError, match="run_aapl_holdout"):
        run(tmp_path, slice_name="all")


def test_run_still_mines_a_reliance_corpus(tmp_path):
    tiny_corpus(tmp_path)

    assert "slice: all" in run(tmp_path, slice_name="all")
