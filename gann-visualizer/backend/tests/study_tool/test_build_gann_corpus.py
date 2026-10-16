"""
The runner that wires bars, ephemeris, ladders and shadows into a corpus.

Runs on a small synthetic bar set so the whole pipeline is exercised in under a
second, with no network and no live token.
"""
import sys
import os
import json

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend/scripts'))

from build_gann_corpus import build_corpus
from study_tool.bar_cache import cache_path

NSE_OPEN_EPOCH = 1787629500


def synthetic_bars(n=60):
    """A climbing series, so levels are actually crossed."""
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


def test_produces_real_and_shadow_events():
    result = build_corpus(
        bars=synthetic_bars(), instrument="RELIANCE", timeframe="5",
        price_scale=1, shadow_count=3, seed=7,
    )
    events = result["events"]

    assert len(events) > 0, "no events produced at all"
    assert events["shadow_id"].isna().any(), "no real events"
    assert set(events["shadow_id"].dropna().unique()) == {0, 1, 2}


def test_ladder_keys_has_one_row_per_bar():
    bars = synthetic_bars()
    result = build_corpus(
        bars=bars, instrument="RELIANCE", timeframe="5",
        price_scale=1, shadow_count=2, seed=7,
    )
    keys = result["ladder_keys"]

    assert len(keys) == len(bars)
    for column in ("bar_index", "price_square", "sun_square", "moon_square"):
        assert column in keys.columns


def test_shadow_runs_do_not_rebuild_the_grid(monkeypatch):
    """
    The performance requirement, enforced rather than documented. One build per
    distinct ladder key, no matter how many shadows are run.
    """
    import build_gann_corpus as runner

    calls = {"n": 0}
    real_build = runner.build_all_ladders

    def counting_build(*args, **kwargs):
        calls["n"] += 1
        return real_build(*args, **kwargs)

    monkeypatch.setattr(runner, "build_all_ladders", counting_build)

    bars = synthetic_bars(n=30)
    build_corpus(bars=bars, instrument="RELIANCE", timeframe="5",
                 price_scale=1, shadow_count=20, seed=7)

    assert calls["n"] <= len(bars), (
        f"{calls['n']} grid builds for {len(bars)} bars with 20 shadows - "
        "shadows are rebuilding instead of being derived"
    )


def test_forward_excursions_are_populated():
    """Blank outcome columns would make the corpus useless for mining."""
    result = build_corpus(
        bars=synthetic_bars(), instrument="RELIANCE", timeframe="5",
        price_scale=1, shadow_count=1, seed=7,
    )
    events = result["events"]
    assert events["exc_up_5"].notna().any()
    assert events["exc_down_5"].notna().any()


def test_run_is_reproducible():
    kwargs = dict(bars=synthetic_bars(), instrument="RELIANCE", timeframe="5",
                  price_scale=1, shadow_count=3, seed=7)
    first = build_corpus(**kwargs)["events"]
    second = build_corpus(**kwargs)["events"]
    pd.testing.assert_frame_equal(first, second)


def test_events_frame_is_parquet_safe(tmp_path):
    """
    to_dict emits `details` and `active_angle_prices` as dicts, which Parquet
    cannot store. They must be JSON strings by the time the frame is returned.
    """
    events = build_corpus(
        bars=synthetic_bars(), instrument="RELIANCE", timeframe="5",
        price_scale=1, shadow_count=1, seed=7,
    )["events"]

    for column in ("details", "active_angle_prices"):
        if column in events.columns:
            assert not events[column].apply(
                lambda v: isinstance(v, (dict, list))).any(), \
                f"{column} still holds dicts"

    events.to_parquet(tmp_path / "events.parquet", index=False)
    assert (tmp_path / "events.parquet").exists()


def test_breach_outcome_is_lifted_into_its_own_column():
    """The most-queried field in the corpus should not need JSON parsing."""
    events = build_corpus(
        bars=synthetic_bars(), instrument="RELIANCE", timeframe="5",
        price_scale=1, shadow_count=1, seed=7,
    )["events"]

    assert "outcome" in events.columns
    resolved = events[events["event_type"] == "LADDER_BREACH_RESOLVED"]
    assert len(resolved) > 0, "no resolved breaches to check"
    assert resolved["outcome"].notna().any()


def test_build_returns_one_offset_per_shadow():
    """
    Mining shifts each shadow's target by its own offset. A missing or
    misaligned offset silently prices every shadow target wrongly.
    """
    result = build_corpus(
        bars=synthetic_bars(), instrument="RELIANCE", timeframe="5",
        price_scale=1, shadow_count=3, seed=7,
    )
    meta = result["meta"]

    assert len(meta["shadow_offsets"]) == 3
    assert meta["seed"] == 7
    assert meta["price_scale"] == 1
    assert meta["shadow_count"] == 3
    assert meta["resolution_window_bars"] == 50
    assert meta["bar_count"] == 60


def test_meta_offsets_are_reproducible_from_the_seed():
    kwargs = dict(bars=synthetic_bars(), instrument="RELIANCE", timeframe="5",
                  price_scale=1, shadow_count=3, seed=7)
    assert build_corpus(**kwargs)["meta"]["shadow_offsets"] == \
        build_corpus(**kwargs)["meta"]["shadow_offsets"]


# -- Breach rule plumbing (2026-10-16 breach sweep) ----------------------------

FROM, TO = "2026-08-01", "2026-08-31"


def test_default_breach_rule_is_close_two():
    meta = build_corpus(bars=synthetic_bars(), instrument="RELIANCE",
                        timeframe="5", price_scale=1, shadow_count=1,
                        seed=7)["meta"]
    assert (meta["breach_mode"], meta["confirmation_closes"]) == ("close", 2)


def test_breach_rule_reaches_the_meta():
    meta = build_corpus(bars=synthetic_bars(), instrument="RELIANCE",
                        timeframe="5", price_scale=1, shadow_count=1, seed=7,
                        breach_mode="wick", confirmation_closes=1)["meta"]
    assert (meta["breach_mode"], meta["confirmation_closes"]) == ("wick", 1)


@pytest.mark.parametrize("breach_mode, closes", [
    ("close", 1), ("close", 2), ("close", 3), ("wick", 1),
])
def test_a_confirmed_breach_crossed_exactly_closes_minus_one_bars_earlier(
        breach_mode, closes):
    """
    The lag-free filter finds the cross bar as k - (closes - 1). Pin that
    against the real analyzer: every confirmed real breach has a cross on the
    same level exactly that many bars before it.
    """
    events = build_corpus(bars=synthetic_bars(), instrument="RELIANCE",
                          timeframe="5", price_scale=1, shadow_count=1, seed=7,
                          breach_mode=breach_mode,
                          confirmation_closes=closes)["events"]
    real = events[events["shadow_id"].isna()]
    crosses = {
        (row.level_source, row.level_square, int(row.bar_index))
        for row in real[real["event_type"] == "LADDER_CROSS"].itertuples()
    }
    confirmed = real[real["event_type"] == "LADDER_BREACH_CONFIRMED"]

    assert len(confirmed) > 0, "no confirmed breaches to check"
    for row in confirmed.itertuples():
        cross_bar = int(row.bar_index) - (closes - 1)
        assert (row.level_source, row.level_square, cross_bar) in crosses


def test_an_unknown_breach_mode_is_refused():
    with pytest.raises(ValueError, match="breach_mode"):
        build_corpus(bars=synthetic_bars(), instrument="RELIANCE",
                     timeframe="5", price_scale=1, shadow_count=1, seed=7,
                     breach_mode="body")


def test_zero_confirmation_closes_is_refused():
    with pytest.raises(ValueError, match="confirmation_closes"):
        build_corpus(bars=synthetic_bars(), instrument="RELIANCE",
                     timeframe="5", price_scale=1, shadow_count=1, seed=7,
                     confirmation_closes=0)


def write_cached_bars(cache_dir):
    cache_dir.mkdir(parents=True, exist_ok=True)
    synthetic_bars().to_parquet(
        cache_path(cache_dir, "RELIANCE", FROM, TO, "5"), index=False)


def test_the_command_line_writes_the_breach_rule_into_meta_json(tmp_path):
    import build_gann_corpus as runner
    cache, out = tmp_path / "bars", tmp_path / "corpus"
    write_cached_bars(cache)

    runner.main(["--from", FROM, "--to", TO, "--cache", str(cache),
                 "--out", str(out), "--shadows", "2",
                 "--breach-mode", "wick", "--confirmation-closes", "1",
                 "--no-fetch"])

    meta = json.loads((out / "meta.json").read_text())
    assert (meta["breach_mode"], meta["confirmation_closes"]) == ("wick", 1)


def test_the_command_line_defaults_keep_the_old_rule(tmp_path):
    import build_gann_corpus as runner
    cache, out = tmp_path / "bars", tmp_path / "corpus"
    write_cached_bars(cache)

    runner.main(["--from", FROM, "--to", TO, "--cache", str(cache),
                 "--out", str(out), "--shadows", "2", "--no-fetch"])

    meta = json.loads((out / "meta.json").read_text())
    assert (meta["breach_mode"], meta["confirmation_closes"]) == ("close", 2)


def test_no_fetch_refuses_a_cache_miss(tmp_path):
    import build_gann_corpus as runner
    out = tmp_path / "corpus"

    with pytest.raises(FileNotFoundError, match="fetching is disabled"):
        runner.main(["--from", FROM, "--to", TO,
                     "--cache", str(tmp_path / "empty"),
                     "--out", str(out), "--no-fetch"])

    assert not (out / "meta.json").exists()


def ensure_kwargs(tmp_path, **overrides):
    kwargs = dict(symbol="RELIANCE", from_date=FROM, to_date=TO, interval="5",
                  price_scale=1, shadow_count=2, seed=7,
                  cache_dir=tmp_path / "bars", out_dir=tmp_path / "corpus",
                  breach_mode="close", confirmation_closes=2)
    kwargs.update(overrides)
    return kwargs


def test_ensure_corpus_builds_then_reuses(tmp_path, monkeypatch):
    import build_gann_corpus as runner
    write_cached_bars(tmp_path / "bars")

    assert runner.ensure_corpus(**ensure_kwargs(tmp_path)) == "built"

    def boom(*args, **kwargs):
        raise AssertionError("a matching corpus was rebuilt")

    monkeypatch.setattr(runner, "build_corpus", boom)
    assert runner.ensure_corpus(**ensure_kwargs(tmp_path)) == "reused"


def test_ensure_corpus_refuses_a_corpus_built_with_another_rule(tmp_path):
    import build_gann_corpus as runner
    write_cached_bars(tmp_path / "bars")
    runner.ensure_corpus(**ensure_kwargs(tmp_path))

    with pytest.raises(ValueError, match="confirmation_closes"):
        runner.ensure_corpus(**ensure_kwargs(tmp_path, confirmation_closes=3))


def test_ensure_corpus_never_fetches(tmp_path):
    import build_gann_corpus as runner

    with pytest.raises(FileNotFoundError, match="fetching is disabled"):
        runner.ensure_corpus(**ensure_kwargs(tmp_path))


def test_ensure_corpus_refuses_a_half_written_corpus_before_building(
        tmp_path, monkeypatch):
    import build_gann_corpus as runner
    out = tmp_path / "corpus"
    out.mkdir()
    (out / "events.parquet").write_bytes(b"killed mid-write")

    def boom(*args, **kwargs):
        raise AssertionError("a rebuild was started over a half-written corpus")

    monkeypatch.setattr(runner, "build_to_disk", boom)

    with pytest.raises(FileExistsError, match="half-written"):
        runner.ensure_corpus(**ensure_kwargs(tmp_path))


def test_a_fractional_confirmation_closes_is_refused():
    import build_gann_corpus as runner

    with pytest.raises(ValueError, match="confirmation_closes"):
        runner._analyzer_settings("RELIANCE", "5", 1, "close", 1.5)
    assert runner._analyzer_settings(
        "RELIANCE", "5", 1, "close", 3.0)["confirmation_closes"] == 3
