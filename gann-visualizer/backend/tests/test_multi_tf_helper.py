import sys
import os
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

import pandas as pd
from analysis.multi_tf_helper import (
    timeframe_seconds,
    compute_bar_close_time,
    merge_asof_htf_to_ltf,
)


def test_timeframe_seconds_known_resolutions():
    assert timeframe_seconds("5") == 300
    assert timeframe_seconds("15") == 900
    assert timeframe_seconds("60") == 3600
    assert timeframe_seconds("240") == 14400


def test_timeframe_seconds_with_minute_suffix():
    assert timeframe_seconds("5m") == 300
    assert timeframe_seconds("15m") == 900


def test_compute_bar_close_time_adds_tf_seconds():
    df = pd.DataFrame({
        "Raw_Timestamp": [1700000000, 1700000300, 1700000600],
        "Timeframe": ["5", "5", "5"],
    })
    out = compute_bar_close_time(df)
    assert list(out["bar_close_time"]) == [1700000300, 1700000600, 1700000900]


def test_merge_asof_attaches_most_recent_htf_event_no_lookahead():
    """LTF bar closing at 11:10 should get HTF state from the HTF bar that closed AT OR BEFORE 11:10."""
    htf = pd.DataFrame({
        "Raw_Timestamp": [1700000000, 1700003600],   # open at 11:00 and 12:00
        "Timeframe":     ["60",        "60"],
        "Type":          ["SUPPORT_TEST", "RESISTANCE_TEST"],
        "Fraction":      ["0.5",        "0.5"],
        "Fan":           ["P1 (H1-L1)", "P1 (H1-L1)"],
    })
    htf = compute_bar_close_time(htf)  # close at 12:00 and 13:00

    ltf = pd.DataFrame({
        "Raw_Timestamp": [1700000300, 1700003900, 1700007500],  # open at 11:05, 12:05, 13:05
        "Timeframe":     ["5", "5", "5"],
    })
    ltf = compute_bar_close_time(ltf)  # close at 11:10, 12:10, 13:10

    out = merge_asof_htf_to_ltf(ltf, htf)
    # LTF closing at 11:10 -> no HTF bar has closed yet (first HTF closes at 12:00) -> NaN
    assert pd.isna(out.loc[0, "htf_event_type"])
    # LTF closing at 12:10 -> most recent closed HTF bar closes at 12:00 (SUPPORT_TEST)
    assert out.loc[1, "htf_event_type"] == "SUPPORT_TEST"
    # LTF closing at 13:10 -> most recent closed HTF bar closes at 13:00 (RESISTANCE_TEST)
    assert out.loc[2, "htf_event_type"] == "RESISTANCE_TEST"


def test_merge_asof_only_pairs_same_instrument():
    """BANKNIFTY LTF should not get NIFTY HTF context."""
    htf = pd.DataFrame({
        "Raw_Timestamp": [1700000000],
        "Timeframe": ["60"],
        "Instrument": ["NIFTY"],
        "Type": ["SUPPORT_TEST"],
        "Fraction": ["0.5"],
        "Fan": ["P1 (H1-L1)"],
    })
    htf = compute_bar_close_time(htf)

    ltf = pd.DataFrame({
        "Raw_Timestamp": [1700003900],
        "Timeframe": ["5"],
        "Instrument": ["BANKNIFTY"],
    })
    ltf = compute_bar_close_time(ltf)

    out = merge_asof_htf_to_ltf(ltf, htf, by="Instrument")
    assert pd.isna(out.loc[0, "htf_event_type"])
