"""Every hypothesis must be scored on realized futures trades, not MFE/MAE.

18 of 19 hypotheses originally reported win rates from MFE/MAE labels -- "did
price move favourably at some point in the horizon" -- which never has to
survive a stop. Bounce Follow-Through V5 reported 0.721 that way while its
actual simulated trades won 0.176 and lost ~30,000.

The realized trades were already being computed by ExitOptimizer and written
into detailed_log; only the headline in_sample/walk_forward numbers still came
from MFE. These tests pin the rescoring that fixes that.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from analysis.hypothesis_framework import rescore_from_realized_trades


def _entry(ts, outcome, net_pnl, retro=False, matched=True):
    return {
        "time": ts,
        "outcome": outcome,
        "net_pnl": net_pnl,
        "is_retro": retro,
        "trade_matched": matched,
    }


def test_rescore_replaces_mfe_win_rate_with_realized_win_rate():
    result = {
        "in_sample": {"sample_size": 4, "win_rate": 0.75, "avg_mfe_10": 380.0},
        "detailed_log": [
            _entry("2026-01-01T00:00:00", "WIN", 100.0),
            _entry("2026-01-01T01:00:00", "LOSS", -50.0),
            _entry("2026-01-01T02:00:00", "LOSS", -50.0),
            _entry("2026-01-01T03:00:00", "LOSS", -25.0),
        ],
    }

    rescore_from_realized_trades(result)

    assert result["in_sample"]["win_rate"] == 0.25
    assert result["in_sample"]["sample_size"] == 4
    assert result["in_sample"]["net_pnl_total"] == -25.0
    assert result["trade_scored"] is True
    assert result["scoring_basis"] == "realized_trades_live_only"


def test_rescore_preserves_the_mfe_numbers_as_labelled_diagnostics():
    result = {
        "in_sample": {"sample_size": 4, "win_rate": 0.75, "avg_mfe_10": 380.0},
        "detailed_log": [_entry("2026-01-01T00:00:00", "LOSS", -10.0)],
    }

    rescore_from_realized_trades(result)

    assert result["in_sample"]["label_win_rate"] == 0.75, "MFE number must survive as a diagnostic"
    assert result["in_sample"]["label_sample_size"] == 4
    assert result["in_sample"]["avg_mfe_10"] == 380.0


def test_rescore_splits_live_and_retro_from_realized_trades():
    result = {
        "in_sample": {"sample_size": 4, "win_rate": 0.9},
        "detailed_log": [
            _entry("2026-01-01T00:00:00", "WIN", 10.0, retro=False),
            _entry("2026-01-01T01:00:00", "LOSS", -10.0, retro=False),
            _entry("2026-01-01T02:00:00", "WIN", 10.0, retro=True),
            _entry("2026-01-01T03:00:00", "WIN", 10.0, retro=True),
        ],
    }

    rescore_from_realized_trades(result)

    assert result["in_sample"]["live_sample_size"] == 2
    assert result["in_sample"]["live_win_rate"] == 0.5
    assert result["in_sample"]["retro_sample_size"] == 2
    assert result["in_sample"]["retro_win_rate"] == 1.0


def test_rescore_recomputes_walk_forward_from_realized_trades():
    """The 70/30 chronological split must use realized outcomes too.

    V5's headline walk-forward test win rate was 0.855 on MFE labels while its
    realized trades won 0.176 -- the walk-forward number was as misleading as
    the in-sample one.
    """
    log = [_entry(f"2026-01-01T{h:02d}:00:00", "WIN" if h < 7 else "LOSS", 10.0 if h < 7 else -10.0)
           for h in range(10)]
    result = {"in_sample": {"sample_size": 10, "win_rate": 0.9}, "detailed_log": log,
              "walk_forward": {"train_win_rate": 0.9, "test_win_rate": 0.9, "persistent": True}}

    rescore_from_realized_trades(result)

    wf = result["walk_forward"]
    assert wf["train_sample_size"] == 7
    assert wf["test_sample_size"] == 3
    assert wf["train_win_rate"] == 1.0     # first 7 are wins
    assert wf["test_win_rate"] == 0.0      # last 3 are losses
    assert wf["persistent"] is False
    assert wf["basis"] == "realized_trades"


def test_rescore_ignores_entries_with_no_matched_trade():
    """Entries the optimizer could not match keep an MFE-derived outcome.
    Counting them would silently re-mix the two scoring bases."""
    result = {
        "in_sample": {"sample_size": 3, "win_rate": 0.66},
        "detailed_log": [
            _entry("2026-01-01T00:00:00", "WIN", 10.0, matched=True),
            _entry("2026-01-01T01:00:00", "LOSS", -10.0, matched=True),
            _entry("2026-01-01T02:00:00", "WIN", None, matched=False),
        ],
    }

    rescore_from_realized_trades(result)

    assert result["in_sample"]["sample_size"] == 2, "unmatched entry must be excluded"
    assert result["in_sample"]["win_rate"] == 0.5


def test_rescore_leaves_result_untouched_when_no_trades_were_matched():
    """No realized trades -> do not fabricate a score. Flag the basis instead."""
    result = {
        "in_sample": {"sample_size": 5, "win_rate": 0.8},
        "detailed_log": [_entry("2026-01-01T00:00:00", "WIN", None, matched=False)],
    }

    rescore_from_realized_trades(result)

    assert result["in_sample"]["win_rate"] == 0.8
    assert result["scoring_basis"] == "mfe_label"
    assert result.get("trade_scored") is not True


def test_rescore_is_idempotent_for_already_trade_scored_hypotheses():
    """RSI Trendline Break already scores on realized trades; rescoring it must
    not double-apply or clobber its own numbers."""
    result = {
        "in_sample": {"sample_size": 2, "win_rate": 0.5, "net_pnl_total": 5.0},
        "detailed_log": [
            _entry("2026-01-01T00:00:00", "WIN", 10.0),
            _entry("2026-01-01T01:00:00", "LOSS", -5.0),
        ],
        "trade_scored": True,
        "scoring_basis": "realized_trades",
    }

    rescore_from_realized_trades(result)
    first = dict(result["in_sample"])
    rescore_from_realized_trades(result)

    assert result["in_sample"] == first


# --- Retro exclusion -------------------------------------------------------
#
# Retro events are backfilled -- discovered after the fact and untradeable live.
# They were ~50% of every hypothesis's sample and counted toward the headline
# win rate and PnL. Headline performance is now LIVE ONLY; retro is retained as
# a labelled diagnostic so the count per run is still visible.

def test_headline_performance_excludes_retro_entirely():
    result = {
        "in_sample": {"sample_size": 4, "win_rate": 0.9},
        "detailed_log": [
            _entry("2026-01-01T00:00:00", "LOSS", -10.0, retro=False),
            _entry("2026-01-01T01:00:00", "LOSS", -10.0, retro=False),
            _entry("2026-01-01T02:00:00", "WIN", 100.0, retro=True),
            _entry("2026-01-01T03:00:00", "WIN", 100.0, retro=True),
        ],
    }

    rescore_from_realized_trades(result)

    # headline must reflect the two live losers, not the two retro winners
    assert result["in_sample"]["sample_size"] == 2
    assert result["in_sample"]["win_rate"] == 0.0
    assert result["in_sample"]["net_pnl_total"] == -20.0


def test_retro_is_still_reported_as_a_diagnostic():
    result = {
        "in_sample": {"sample_size": 3, "win_rate": 0.5},
        "detailed_log": [
            _entry("2026-01-01T00:00:00", "WIN", 10.0, retro=False),
            _entry("2026-01-01T01:00:00", "WIN", 50.0, retro=True),
            _entry("2026-01-01T02:00:00", "LOSS", -20.0, retro=True),
        ],
    }

    rescore_from_realized_trades(result)

    assert result["in_sample"]["retro_sample_size"] == 2
    assert result["in_sample"]["retro_win_rate"] == 0.5
    assert result["in_sample"]["retro_net_pnl"] == 30.0
    assert result["in_sample"]["live_sample_size"] == 1


def test_walk_forward_is_computed_on_live_trades_only():
    log = [_entry(f"2026-01-01T{h:02d}:00:00", "WIN", 10.0, retro=True) for h in range(10)]
    log += [_entry(f"2026-01-02T{h:02d}:00:00", "LOSS", -10.0, retro=False) for h in range(10)]
    result = {"in_sample": {"sample_size": 20, "win_rate": 0.5}, "detailed_log": log}

    rescore_from_realized_trades(result)

    wf = result["walk_forward"]
    assert wf["train_sample_size"] + wf["test_sample_size"] == 10, "retro must not enter walk-forward"
    assert wf["test_win_rate"] == 0.0


def test_all_retro_leaves_no_tradeable_sample():
    result = {
        "in_sample": {"sample_size": 2, "win_rate": 1.0},
        "detailed_log": [
            _entry("2026-01-01T00:00:00", "WIN", 10.0, retro=True),
            _entry("2026-01-01T01:00:00", "WIN", 10.0, retro=True),
        ],
    }

    rescore_from_realized_trades(result)

    assert result["in_sample"]["sample_size"] == 0
    assert result["in_sample"]["retro_sample_size"] == 2
    assert result["scoring_basis"] == "realized_trades_live_only"
