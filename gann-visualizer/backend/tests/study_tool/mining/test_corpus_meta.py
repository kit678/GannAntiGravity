"""
Mining refuses to start without the corpus metadata.

A missing offset does not crash anything downstream. It silently puts every
shadow's next-level target on the wrong price, and the report still prints a
percentage. So the gate is here, at load time, and it is loud.
"""
import sys
import os
import json

import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.mining.corpus_meta import CorpusMeta, load_corpus_meta


def good_meta():
    return {
        "corpus_meta_version": 1,
        "symbol": "RELIANCE",
        "from_date": "2024-09-02",
        "to_date": "2026-09-01",
        "interval": "5",
        "price_scale": 1,
        "shadow_count": 3,
        "seed": 7,
        "median_sub_gap": 2.25,
        "shadow_offsets": [0.4, 1.1, 1.9],
        "resolution_window_bars": 50,
        "bar_count": 60,
    }


def write_meta(tmp_path, meta):
    (tmp_path / "meta.json").write_text(json.dumps(meta))


def test_loads_into_a_typed_object(tmp_path):
    write_meta(tmp_path, good_meta())

    meta = load_corpus_meta(tmp_path)

    assert isinstance(meta, CorpusMeta)
    assert meta.price_scale == 1
    assert meta.shadow_count == 3
    assert meta.resolution_window_bars == 50
    assert meta.shadow_offsets == [0.4, 1.1, 1.9]


def test_offset_for_returns_the_right_shadows_shift(tmp_path):
    write_meta(tmp_path, good_meta())

    meta = load_corpus_meta(tmp_path)

    assert meta.offset_for(0) == 0.4
    assert meta.offset_for(2) == 1.9


def test_offset_for_a_real_event_is_zero(tmp_path):
    """Real events carry shadow_id None. Their ladder is unshifted."""
    write_meta(tmp_path, good_meta())

    assert load_corpus_meta(tmp_path).offset_for(None) == 0.0


def test_an_unknown_shadow_id_raises_rather_than_defaulting(tmp_path):
    write_meta(tmp_path, good_meta())

    with pytest.raises(KeyError, match="shadow"):
        load_corpus_meta(tmp_path).offset_for(9)


def test_a_missing_meta_file_raises_with_the_fix_in_the_message(tmp_path):
    with pytest.raises(FileNotFoundError, match="backfill_corpus_meta"):
        load_corpus_meta(tmp_path)


def test_a_future_meta_version_raises(tmp_path):
    """Silently reading a newer layout is how a wrong offset gets used."""
    meta = good_meta()
    meta["corpus_meta_version"] = 99
    write_meta(tmp_path, meta)

    with pytest.raises(ValueError, match="corpus_meta_version"):
        load_corpus_meta(tmp_path)


def test_old_meta_without_the_breach_rule_loads_as_close_two(tmp_path):
    """Every corpus built before 2026-10-16 used close / 2 and says nothing."""
    write_meta(tmp_path, good_meta())

    meta = load_corpus_meta(tmp_path)

    assert meta.breach_mode == "close"
    assert meta.confirmation_closes == 2


def test_the_breach_rule_is_read_when_present_and_the_version_stays_one(tmp_path):
    raw = good_meta()
    raw["breach_mode"] = "wick"
    raw["confirmation_closes"] = 1
    write_meta(tmp_path, raw)

    meta = load_corpus_meta(tmp_path)

    assert raw["corpus_meta_version"] == 1
    assert (meta.breach_mode, meta.confirmation_closes) == ("wick", 1)


def test_an_unknown_breach_mode_in_meta_raises(tmp_path):
    raw = good_meta()
    raw["breach_mode"] = "body"
    write_meta(tmp_path, raw)

    with pytest.raises(ValueError, match="breach_mode"):
        load_corpus_meta(tmp_path)


def test_zero_confirmation_closes_in_meta_raises(tmp_path):
    raw = good_meta()
    raw["confirmation_closes"] = 0
    write_meta(tmp_path, raw)

    with pytest.raises(ValueError, match="confirmation_closes"):
        load_corpus_meta(tmp_path)
