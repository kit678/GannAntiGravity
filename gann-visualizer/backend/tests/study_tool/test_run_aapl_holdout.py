"""
The AAPL command: refuses without a non-null choice, refuses anything that
looks like a second look, builds one corpus under the chosen rule, reads it
whole once, and writes only the spec's statistics and the verdict.
"""
import sys
import os
import json

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend/scripts'))

import mine_gann_corpus
import run_aapl_holdout as holdout
from study_tool.bar_cache import cache_path

FROM, TO = "2026-08-01", "2026-08-31"
SHADOWS = 5
VALID_LABELS = {"fail", "pass", "strong pass", "pass, selection differs",
                "strong pass, selection differs"}


def write_cache(tmp_path):
    epoch = 1787629500
    rows = []
    for i in range(400):
        open_ = 228.0 + (i % 40) * 0.1
        close = open_ + 0.08
        rows.append({"open": open_, "high": close + 0.06, "low": open_ - 0.06,
                     "close": close, "volume": 1000.0,
                     "timestamp": float(epoch + i * 300),
                     "sun_degree": 155.0 + i * 0.0007,
                     "moon_degree": (331.0 + i * 0.009) % 360})
    cache = tmp_path / "bars"
    cache.mkdir()
    pd.DataFrame(rows).to_parquet(
        cache_path(cache, "AAPL", FROM, TO, "5"), index=False)
    return cache


def write_choice_file(tmp_path, chosen):
    path = tmp_path / "choice.json"
    path.write_text(json.dumps({"chosen": chosen}), encoding="utf-8")
    return path


def kwargs(tmp_path, choice, cache):
    return dict(choice_path=choice, cache_dir=cache,
                out_dir=tmp_path / "aapl_5m_x6",
                results_path=tmp_path / "docs" / "aapl.md",
                from_date=FROM, to_date=TO, shadows=SHADOWS)


def marker(args):
    return holdout.started_marker(args["results_path"])


def test_refuses_without_a_choice_file(tmp_path):
    args = kwargs(tmp_path, tmp_path / "missing.json", write_cache(tmp_path))

    with pytest.raises(FileNotFoundError, match="AAPL is not built"):
        holdout.run_aapl(**args)

    assert not args["out_dir"].exists()
    assert not marker(args).exists()


def test_refuses_a_null_choice(tmp_path):
    args = kwargs(tmp_path, write_choice_file(tmp_path, None),
                  write_cache(tmp_path))

    with pytest.raises(ValueError, match="null"):
        holdout.run_aapl(**args)

    assert not args["out_dir"].exists()


def test_main_returns_1_and_builds_nothing_without_a_choice(tmp_path):
    cache = write_cache(tmp_path)

    code = holdout.main(["--choice", str(tmp_path / "missing.json"),
                         "--cache", str(cache),
                         "--out", str(tmp_path / "aapl_5m_x6"),
                         "--results", str(tmp_path / "aapl.md")])

    assert code == 1
    assert not (tmp_path / "aapl_5m_x6").exists()


def test_refuses_an_existing_aapl_corpus_directory(tmp_path):
    args = kwargs(tmp_path, write_choice_file(tmp_path, "close1"),
                  write_cache(tmp_path))
    args["out_dir"].mkdir()

    with pytest.raises(FileExistsError, match="already exists"):
        holdout.run_aapl(**args)

    assert not marker(args).exists()


def test_refuses_when_ensure_corpus_did_not_build(tmp_path, monkeypatch):
    args = kwargs(tmp_path, write_choice_file(tmp_path, "close1"),
                  write_cache(tmp_path))
    monkeypatch.setattr(holdout, "ensure_corpus", lambda **_: "reused")

    with pytest.raises(RuntimeError, match="reused"):
        holdout.run_aapl(**args)

    assert not marker(args).exists()


def test_the_marker_is_written_before_scoring_and_blocks_a_retry(tmp_path,
                                                                  monkeypatch):
    args = kwargs(tmp_path, write_choice_file(tmp_path, "close1"),
                  write_cache(tmp_path))

    def crash(*_, **__):
        assert marker(args).exists(), "scoring started before the marker"
        raise RuntimeError("scoring crashed")

    monkeypatch.setattr(holdout, "load_scored_events", crash)
    with pytest.raises(RuntimeError, match="scoring crashed"):
        holdout.run_aapl(**args)

    monkeypatch.undo()
    with pytest.raises(FileExistsError, match="started"):
        holdout.run_aapl(**args)


def test_builds_under_the_chosen_rule_and_writes_only_the_spec_statistics(
        tmp_path, monkeypatch):
    def no_report(*_, **__):
        raise AssertionError("the full mining report was rendered on AAPL")

    monkeypatch.setattr(mine_gann_corpus, "render_mining_report", no_report)
    args = kwargs(tmp_path, write_choice_file(tmp_path, "close1"),
                  write_cache(tmp_path))

    verdict = holdout.run_aapl(**args)

    assert verdict.label in VALID_LABELS
    assert not hasattr(holdout, "render_mining_report")
    meta = json.loads((args["out_dir"] / "meta.json").read_text())
    assert meta["symbol"] == "AAPL"
    assert meta["price_scale"] == 6
    assert meta["shadow_count"] == SHADOWS
    assert meta["seed"] == 7
    assert (meta["breach_mode"], meta["confirmation_closes"]) == ("close", 1)
    assert marker(args).exists()
    text = args["results_path"].read_text(encoding="utf-8")
    assert text.index("## Touch density") < text.index("## Verdict")
    assert f"**{verdict.label}**" in text
    assert "hold_rate" not in text
    assert list(tmp_path.rglob("gann-mining-report-*.md")) == []


def test_a_second_look_is_refused(tmp_path):
    args = kwargs(tmp_path, write_choice_file(tmp_path, "close2"),
                  write_cache(tmp_path))
    holdout.run_aapl(**args)

    with pytest.raises(FileExistsError, match="one look"):
        holdout.run_aapl(**args)
