"""
The sweep runner, end to end on a tiny cached bar set. No network: every
build passes no_fetch, and the cache is written by the test.
"""
import sys
import os
import json

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend/scripts'))

import build_gann_corpus
import run_breach_sweep as sweep
from build_gann_corpus import build_to_disk
from study_tool.bar_cache import cache_path
from study_tool.mining.breach_sweep import (
    RULE_ORDER, RULES_BY_NAME, Selection, read_choice,
)

FROM, TO = "2026-08-01", "2026-08-31"
SHADOWS = 5


def write_cache(tmp_path):
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
    cache = tmp_path / "bars"
    cache.mkdir()
    pd.DataFrame(rows).to_parquet(
        cache_path(cache, "RELIANCE", FROM, TO, "5"), index=False)
    return cache


def write_reference(tmp_path, cache, seed=7, shadows=SHADOWS):
    out = tmp_path / f"reference_seed{seed}_shadows{shadows}"
    build_to_disk(symbol="RELIANCE", from_date=FROM, to_date=TO, interval="5",
                  price_scale=1, shadow_count=shadows, seed=seed,
                  cache_dir=cache, out_dir=out, allow_fetch=False)
    return out / "events.parquet"


def paths(tmp_path):
    return {"out_root": tmp_path / "sweep",
            "choice_path": tmp_path / "docs" / "choice.json",
            "results_path": tmp_path / "docs" / "results.md"}


def run(tmp_path, cache, reference, **overrides):
    kwargs = dict(cache_dir=cache, reference=reference, from_date=FROM,
                  to_date=TO, shadows=SHADOWS, **paths(tmp_path))
    kwargs.update(overrides)
    return sweep.run_sweep(**kwargs)


def test_a_sweep_with_no_shadows_is_a_pinned_null(tmp_path):
    """
    The whole pipeline, with an outcome known in advance: with zero shadows
    no rule can be above all shadows, so the pre-registered rule must return
    a null and the choice file must say so.
    """
    cache = write_cache(tmp_path)
    reference = write_reference(tmp_path, cache, shadows=0)
    p = paths(tmp_path)

    selection = run(tmp_path, cache, reference, shadows=0)

    assert selection.chosen is None
    assert selection.eligible == []
    record = json.loads(p["choice_path"].read_text(encoding="utf-8"))
    assert record["chosen"] is None
    assert record["breach_mode"] is None
    assert record["regression_gate"]["passed"] is True
    assert set(record["rules"]) == set(RULE_ORDER)
    text = p["results_path"].read_text(encoding="utf-8")
    assert "**PASSED**" in text
    assert "AAPL is not built" in text
    with pytest.raises(ValueError, match="null"):
        read_choice(p["choice_path"])


def test_a_chosen_rule_reaches_the_choice_file_and_the_report(tmp_path,
                                                              monkeypatch):
    """
    Real builds, real gate and real scoring on five shadows; only the
    selection is forced, so the chosen-rule path is checked end to end.
    """
    cache = write_cache(tmp_path)
    reference = write_reference(tmp_path, cache)
    p = paths(tmp_path)
    seen = {}

    def forced(pooled, tie_window=0.1):
        seen["rules"] = sorted(pooled)
        return Selection(chosen="wick1", eligible=["wick1"],
                         candidates=["wick1"],
                         z={name: c.z for name, c in pooled.items()},
                         reason="forced by the test")

    monkeypatch.setattr(sweep, "select_rule", forced)

    selection = run(tmp_path, cache, reference)

    assert selection.chosen == "wick1"
    assert seen["rules"] == sorted(RULE_ORDER)
    record = json.loads(p["choice_path"].read_text(encoding="utf-8"))
    assert (record["chosen"], record["breach_mode"],
            record["confirmation_closes"]) == ("wick1", "wick", 1)
    assert read_choice(p["choice_path"]) == RULES_BY_NAME["wick1"]
    assert "Chosen rule: `wick1`" in         p["results_path"].read_text(encoding="utf-8")
    for name in RULE_ORDER:
        meta = json.loads(
            (sweep.corpus_dir_for(p["out_root"], name) / "meta.json").read_text())
        rule = RULES_BY_NAME[name]
        assert (meta["breach_mode"], meta["confirmation_closes"]) ==             (rule.breach_mode, rule.confirmation_closes)

    # A second run reuses every corpus instead of rebuilding.
    def boom(*args, **kwargs):
        raise AssertionError("a finished corpus was rebuilt")

    monkeypatch.setattr(build_gann_corpus, "build_corpus", boom)
    assert run(tmp_path, cache, reference).chosen == "wick1"


def test_peak_memory_is_reported_on_windows():
    peak = sweep.peak_memory_gb()
    if sys.platform == "win32":
        assert peak is not None and peak > 0
    else:
        assert peak is None


def test_a_failing_gate_stops_before_any_other_build_or_score(tmp_path):
    cache = write_cache(tmp_path)
    reference = write_reference(tmp_path, cache, seed=8)   # other shadows
    p = paths(tmp_path)

    with pytest.raises(sweep.RegressionGateError, match="close2"):
        run(tmp_path, cache, reference)

    assert not p["choice_path"].exists()
    assert not p["results_path"].exists()
    assert not sweep.corpus_dir_for(p["out_root"], "close1").exists()


def test_main_exits_2_on_a_failing_gate(tmp_path):
    cache = write_cache(tmp_path)
    reference = write_reference(tmp_path, cache, seed=8)
    p = paths(tmp_path)

    code = sweep.main(["--cache", str(cache), "--reference", str(reference),
                       "--out-root", str(p["out_root"]),
                       "--choice", str(p["choice_path"]),
                       "--results", str(p["results_path"]),
                       "--from", FROM, "--to", TO,
                       "--shadows", str(SHADOWS)])

    assert code == 2
    assert not p["choice_path"].exists()


def test_build_only_builds_just_the_named_rules(tmp_path):
    cache = write_cache(tmp_path)
    p = paths(tmp_path)

    result = run(tmp_path, cache, tmp_path / "unused.parquet",
                 rules=("close1",), build_only=True)

    assert result is None
    assert (sweep.corpus_dir_for(p["out_root"], "close1") / "meta.json").exists()
    assert not sweep.corpus_dir_for(p["out_root"], "close2").exists()
    assert not p["choice_path"].exists()


def test_scoring_needs_all_four_rules(tmp_path):
    with pytest.raises(ValueError, match="all four"):
        run(tmp_path, tmp_path / "bars", tmp_path / "unused.parquet",
            rules=("close1",))


def test_an_unknown_rule_is_refused(tmp_path):
    with pytest.raises(ValueError, match="close9"):
        run(tmp_path, tmp_path / "bars", tmp_path / "unused.parquet",
            rules=("close9",), build_only=True)
