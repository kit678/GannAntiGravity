"""
The AAPL bar loader command refuses to run before the RELIANCE sweep has
chosen a breach rule.
"""
import sys
import os
import json

import pandas as pd
import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend/scripts'))

import load_aapl_bars

CACHE_NAME = "AAPL_5_2024-09-02_2026-09-01.parquet"


def minutes(date, start_hm, count, base):
    start = int(pd.Timestamp(f"{date} {start_hm}",
                             tz="America/New_York").timestamp())
    return [{"time": start + 60 * i, "open": base + i,
             "high": base + i + 0.5, "low": base + i - 0.5,
             "close": base + i + 0.25, "volume": 10.0 + i}
            for i in range(count)]


def write_json(tmp_path):
    path = tmp_path / "aapl.json"
    path.write_text(json.dumps({
        "symbol": "AAPL", "source": "test",
        "candles": (minutes("2024-08-30", "15:58", 2, 228.0)
                    + minutes("2024-09-03", "09:30", 10, 230.0))}))
    return path


def write_choice(tmp_path, chosen):
    path = tmp_path / "choice.json"
    path.write_text(json.dumps({
        "chosen": chosen,
        "breach_mode": {"close1": "close", None: None}[chosen],
        "confirmation_closes": {"close1": 1, None: None}[chosen],
        "regression_gate": {"passed": True, "reason": "test"},
        "rules": {name: {} for name in ("close1", "wick1", "close2",
                                        "close3")}}), encoding="utf-8")
    return path


def test_refuses_without_a_choice_file(tmp_path):
    cache = tmp_path / "bars"

    with pytest.raises(FileNotFoundError, match="AAPL is not built"):
        load_aapl_bars.main(["--choice", str(tmp_path / "missing.json"),
                             "--json", str(write_json(tmp_path)),
                             "--cache", str(cache)])

    assert not (cache / CACHE_NAME).exists()


def test_refuses_a_null_choice(tmp_path):
    cache = tmp_path / "bars"

    with pytest.raises(ValueError, match="null"):
        load_aapl_bars.main(["--choice", str(write_choice(tmp_path, None)),
                             "--json", str(write_json(tmp_path)),
                             "--cache", str(cache)])

    assert not (cache / CACHE_NAME).exists()


def test_writes_the_cache_and_prints_the_checks(tmp_path, capsys):
    cache = tmp_path / "bars"

    load_aapl_bars.main(["--choice", str(write_choice(tmp_path, "close1")),
                         "--json", str(write_json(tmp_path)),
                         "--cache", str(cache)])

    out = capsys.readouterr().out
    assert "breach rule close1 is chosen" in out
    assert "2 bars over 1 sessions 2024-09-02..2026-09-01" in out
    assert "2024-08-30 close: 229.25" in out
    assert "last close before 2024-09-02: 229.25 on 2024-08-30" in out
    assert (cache / CACHE_NAME).exists()


def test_prints_the_bars_per_session_histogram(tmp_path, capsys):
    cache = tmp_path / "bars"

    load_aapl_bars.main(["--choice", str(write_choice(tmp_path, "close1")),
                         "--json", str(write_json(tmp_path)),
                         "--cache", str(cache)])

    assert "bars per session (bars x sessions): 2 x 1" in capsys.readouterr().out
