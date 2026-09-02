"""
The runner that wires bars, ephemeris, ladders and shadows into a corpus.

Runs on a small synthetic bar set so the whole pipeline is exercised in under a
second, with no network and no live token.
"""
import sys
import os

import pandas as pd

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend/scripts'))

from build_gann_corpus import build_corpus

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
