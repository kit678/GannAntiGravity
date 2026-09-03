"""
The report.

Its output is a shortlist of candidates, not findings. A table of percentages
invites being read as results, so the document says what it is in its own
header rather than relying on the reader remembering.
"""
import sys
import os

import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.report import GroupResult, render_report
from study_tool.mining.shadow_compare import Comparison


def comparison(real, shadows, n):
    return Comparison(real=real, n=n, shadows=shadows)


def results():
    return [
        GroupResult("level_is_halfway", "True", "hold_rate",
                    comparison(0.41, [0.22, 0.24, 0.25], 900)),
        GroupResult("level_is_halfway", "False", "hold_rate",
                    comparison(0.23, [0.22, 0.24, 0.25], 4000)),
        GroupResult("level_degree", "90", "hold_rate",
                    comparison(0.99, [0.20, 0.30, 0.40], 4)),
    ]


def context():
    return {
        "corpus_dir": "logs/corpus/reliance_5m_x1",
        "symbol": "RELIANCE",
        "interval": "5",
        "price_scale": 1,
        "shadow_count": 3,
        "explore_events": 100000,
        "dropped_to_buffer": 132,
        "boundary_bar_index": 27833,
        "buffer_bars": 50,
        "touch_density": comparison(0.81, [0.79, 0.80, 0.82], 29963),
    }


def test_header_says_these_are_candidates_not_findings():
    text = render_report(results(), context())

    assert "candidates" in text.lower()
    assert "not findings" in text.lower()


def test_fairness_check_appears_before_any_statistic():
    text = render_report(results(), context())

    assert text.index("Fairness check") < text.index("hold_rate")


def test_the_buffer_cost_is_reported_rather_than_silent():
    text = render_report(results(), context())

    assert "132" in text
    assert "27833" in text


def test_shortlist_holds_only_groups_outside_the_whole_shadow_range():
    text = render_report(results(), context())
    shortlist = text.split("## Shortlist")[1]

    assert "level_is_halfway=True" in shortlist
    assert "level_is_halfway=False" not in shortlist


def test_every_shortlist_row_carries_its_sample_size():
    """A 99% rate from four events must not read like the strongest result."""
    text = render_report(results(), context())
    shortlist = text.split("## Shortlist")[1]

    assert "900" in shortlist
    assert "n=4" in shortlist or "| 4 " in shortlist


def test_a_none_valued_comparison_renders_as_dash_not_zero():
    empty = [GroupResult("level_degree", "45", "hold_rate",
                         comparison(None, [], 0))]

    text = render_report(empty, context())

    assert "0.000" not in text.split("## Per group")[1].split("## Shortlist")[0]


def test_the_report_is_stable_across_two_renders():
    """It is written to a file and diffed across runs."""
    assert render_report(results(), context()) == \
        render_report(results(), context())


def test_numeric_looking_labels_render_without_a_dotzero_suffix():
    """
    level_sub_index mixes ints and nulls, which pandas upcasts to float64, so
    iter_groups yields "1.0" instead of "1". The report should show "1".
    """
    upcast = [GroupResult("level_sub_index", "1.0", "hold_rate",
                          comparison(0.5, [0.1, 0.2], 10))]

    text = render_report(upcast, context())
    per_group = text.split("## Per group")[1].split("## Shortlist")[0]

    assert "level_sub_index=1.0" not in per_group
    assert "level_sub_index=1" in per_group


def test_degree_groups_sort_numerically_not_alphabetically():
    """
    Degree labels are strings, so a plain sort puts "180" before "45". The
    per-group table should read in ascending numeric order instead.
    """
    degrees = [
        GroupResult("level_degree", label, "hold_rate", comparison(0.5, [0.1], 10))
        for label in ["270", "45", "0", "180", "90", "315", "135", "225"]
    ]

    text = render_report(degrees, context())
    per_group = text.split("### hold_rate")[1].split("###")[0] \
        if "### hold_rate" in text else text.split("## Per group")[1]

    positions = [per_group.index(f"level_degree={d}") for d in
                 ["0", "45", "90", "135", "180", "225", "270", "315"]]

    assert positions == sorted(positions)


def test_ring_bin_groups_sort_numerically_by_leading_integer():
    bins = [
        GroupResult("level_ring_bin", label, "hold_rate", comparison(0.5, [0.1], 10))
        for label in ["100-109", "0-9", "20-29", "10-19"]
    ]

    text = render_report(bins, context())
    per_group = text.split("## Per group")[1]

    positions = [per_group.index(f"level_ring_bin={b}") for b in
                 ["0-9", "10-19", "20-29", "100-109"]]

    assert positions == sorted(positions)


def test_non_numeric_labels_still_sort_alphabetically():
    sources = [
        GroupResult("level_source", label, "hold_rate", comparison(0.5, [0.1], 10))
        for label in ["sun", "center", "moon"]
    ]

    text = render_report(sources, context())
    per_group = text.split("## Per group")[1]

    positions = [per_group.index(f"level_source={s}") for s in
                 ["center", "moon", "sun"]]

    assert positions == sorted(positions)


def test_run_section_reports_the_slice_that_was_mined():
    ctx = context()
    ctx["slice"] = "holdout"

    text = render_report(results(), ctx)
    run_section = text.split("## Run")[1].split("## Fairness")[0]

    assert "slice: holdout" in run_section


def test_run_section_defaults_to_explore_when_context_omits_slice():
    """Backward compatibility for any caller that predates the --slice flag."""
    text = render_report(results(), context())
    run_section = text.split("## Run")[1].split("## Fairness")[0]

    assert "slice: explore" in run_section


def test_the_entry_point_mines_a_tiny_corpus_end_to_end(tmp_path):
    """
    Everything wired together on a synthetic corpus: no network, no token,
    no 113 MB of Parquet.
    """
    sys.path.append(os.path.abspath(
        'C:/Dev/GannTesting/gann-visualizer/backend/scripts'))
    import pandas as pd
    from build_gann_corpus import build_corpus
    from mine_gann_corpus import run
    from study_tool.corpus_writer import assign_slices, write_corpus

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
    bars = pd.DataFrame(rows)

    result = build_corpus(bars=bars, instrument="RELIANCE", timeframe="5",
                          price_scale=1, shadow_count=3, seed=7)
    meta = dict(result["meta"])
    meta["from_date"], meta["to_date"] = "2026-08-01", "2026-08-31"
    write_corpus(tmp_path, events=assign_slices(result["events"]),
                 bars=result["bars"], ladder_keys=result["ladder_keys"],
                 meta=meta)

    text = run(tmp_path)

    assert "## Shortlist" in text
    assert "Fairness check" in text


def test_the_entry_point_sweeps_depths_and_windows(tmp_path):
    """
    The sweep wiring, end to end. Two depths must produce two reach rates and
    two timeout shares, each named after its own column.

    stop_depths=(1.0,) would leave `reach_outcome` absent, so this also pins
    that the run does not subscript that column blind - a KeyError there would
    land after the whole multi-minute race had already run.
    """
    sys.path.append(os.path.abspath(
        'C:/Dev/GannTesting/gann-visualizer/backend/scripts'))
    import pandas as pd
    from build_gann_corpus import build_corpus
    from mine_gann_corpus import run
    from study_tool.corpus_writer import assign_slices, write_corpus

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
    bars = pd.DataFrame(rows)

    result = build_corpus(bars=bars, instrument="RELIANCE", timeframe="5",
                          price_scale=1, shadow_count=3, seed=7)
    meta = dict(result["meta"])
    meta["from_date"], meta["to_date"] = "2026-08-01", "2026-08-31"
    write_corpus(tmp_path, events=assign_slices(result["events"]),
                 bars=result["bars"], ladder_keys=result["ladder_keys"],
                 meta=meta)

    text = run(tmp_path, stop_depths=(0.0, 1.0), windows=(50,))

    for name in ("reach_rate[reach_d0_w50]", "reach_rate[reach_d1_w50]",
                 "timeout_share[reach_d0_w50]", "timeout_share[reach_d1_w50]",
                 "already_hit_share"):
        assert name in text, f"missing {name}"

    # No strict column in this sweep at all: the run must still complete.
    assert "reach_rate[reach_d1_w50]" in run(
        tmp_path, stop_depths=(1.0,), windows=(50,))


def test_the_entry_point_refuses_a_corpus_with_no_meta(tmp_path):
    """The gate, exercised through the real entry point rather than in unit."""
    sys.path.append(os.path.abspath(
        'C:/Dev/GannTesting/gann-visualizer/backend/scripts'))
    from mine_gann_corpus import run

    with pytest.raises(FileNotFoundError, match="backfill_corpus_meta"):
        run(tmp_path)


def test_run_raises_on_duplicate_bar_index_in_ladder_keys(tmp_path):
    """
    A duplicate bar_index would silently overwrite in LadderCache's internal
    dict, mis-racing every event built from that bar. It must fail loudly
    instead of producing a plausible-looking wrong report.
    """
    sys.path.append(os.path.abspath(
        'C:/Dev/GannTesting/gann-visualizer/backend/scripts'))
    import pandas as pd
    from build_gann_corpus import build_corpus
    from mine_gann_corpus import run
    from study_tool.corpus_writer import assign_slices, write_corpus

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
    bars = pd.DataFrame(rows)

    result = build_corpus(bars=bars, instrument="RELIANCE", timeframe="5",
                          price_scale=1, shadow_count=3, seed=7)
    meta = dict(result["meta"])
    meta["from_date"], meta["to_date"] = "2026-08-01", "2026-08-31"

    bad_keys = pd.concat([result["ladder_keys"], result["ladder_keys"].iloc[[0]]],
                         ignore_index=True)

    write_corpus(tmp_path, events=assign_slices(result["events"]),
                 bars=result["bars"], ladder_keys=bad_keys,
                 meta=meta)

    with pytest.raises(ValueError, match="bar_index"):
        run(tmp_path)


def test_the_entry_point_mines_the_holdout_slice_without_the_buffer_drop(tmp_path):
    """
    Holdout is the last slice - there is no data after it that could leak
    into it, so the explore-only buffer-drop must not run when mining
    holdout. dropped_to_buffer must read 0 and the report must say which
    slice was mined.
    """
    sys.path.append(os.path.abspath(
        'C:/Dev/GannTesting/gann-visualizer/backend/scripts'))
    import pandas as pd
    from build_gann_corpus import build_corpus
    from mine_gann_corpus import run
    from study_tool.corpus_writer import assign_slices, write_corpus

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
    bars = pd.DataFrame(rows)

    result = build_corpus(bars=bars, instrument="RELIANCE", timeframe="5",
                          price_scale=1, shadow_count=3, seed=7)
    meta = dict(result["meta"])
    meta["from_date"], meta["to_date"] = "2026-08-01", "2026-08-31"
    write_corpus(tmp_path, events=assign_slices(result["events"]),
                 bars=result["bars"], ladder_keys=result["ladder_keys"],
                 meta=meta)

    text = run(tmp_path, slice_name="holdout")

    assert "## Shortlist" in text
    run_section = text.split("## Run")[1].split("## Fairness")[0]
    assert "slice: holdout" in run_section
    assert "dropped to the boundary buffer: 0" in run_section


def test_run_raises_when_bars_do_not_cover_every_ladder_key_bar_index(tmp_path):
    sys.path.append(os.path.abspath(
        'C:/Dev/GannTesting/gann-visualizer/backend/scripts'))
    import pandas as pd
    from build_gann_corpus import build_corpus
    from mine_gann_corpus import run
    from study_tool.corpus_writer import assign_slices, write_corpus

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
    bars = pd.DataFrame(rows)

    result = build_corpus(bars=bars, instrument="RELIANCE", timeframe="5",
                          price_scale=1, shadow_count=3, seed=7)
    meta = dict(result["meta"])
    meta["from_date"], meta["to_date"] = "2026-08-01", "2026-08-31"

    truncated_bars = result["bars"].iloc[:-50].reset_index(drop=True)

    write_corpus(tmp_path, events=assign_slices(result["events"]),
                 bars=truncated_bars, ladder_keys=result["ladder_keys"],
                 meta=meta)

    with pytest.raises(ValueError, match="bars"):
        run(tmp_path)
