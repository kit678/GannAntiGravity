import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd

from analysis.rsi_line_policy import WalkBackAnchorPolicy
from analysis.rsi_pivots import GeometryParams
from analysis.rsi_sweep import run_causal_sweep


def falling_then_breaking_rsi():
    """Three descending RSI peaks, then a decisive break upward."""
    return pd.Series(
        [
            50.0, 52.0, 70.0, 55.0, 50.0,      # peak at bar 2
            48.0, 52.0, 64.0, 52.0, 48.0,      # peak at bar 7
            46.0, 50.0, 60.0, 50.0, 45.0,      # peak at bar 12
            44.0, 48.0, 56.0, 50.0, 46.0,      # peak at bar 17
            48.0, 62.0, 75.0, 80.0, 82.0,      # decisive break up
        ]
    )


PARAMS = GeometryParams(
    left_bars=2, right_bars=2, min_swing=6.0,
    tolerance=1.5, min_length=5, max_span_bars=150,
)


def rsi_with_repeated_reanchors():
    """Many descending peaks in a row, so the down-line re-anchors repeatedly.

    A short series that never re-anchors would let the handoff-overlap bug pass
    unnoticed, so this fixture exists specifically to force handoffs.
    """
    values = []
    for cycle in range(9):
        peak = 74.0 - cycle * 2.0
        trough = 36.0 + cycle * 0.4
        values.extend([trough, trough + 5, peak - 3, peak, peak - 4, trough + 3])
    values.extend([60.0, 72.0, 84.0, 88.0, 90.0])  # decisive break up
    return pd.Series(values)


def test_sweep_never_holds_more_than_one_active_line_per_direction():
    for rsi in (falling_then_breaking_rsi(), rsi_with_repeated_reanchors()):
        result = run_causal_sweep(rsi, WalkBackAnchorPolicy(), PARAMS)

        for bar in range(len(rsi)):
            live = [
                s for s in result.segments
                if s.valid_from_bar <= bar <= s.valid_to_bar
            ]
            for direction in ("up", "down"):
                count = len([s for s in live if s.line.direction == direction])
                assert count <= 1, (
                    f"bar {bar}: {count} live {direction} lines "
                    f"(segments {[s.segment_id for s in live if s.line.direction == direction]})"
                )


def test_the_fixture_actually_exercises_re_anchoring():
    """Guards the test above: an invariant only proven on data that never
    re-anchors proves nothing about the handoff boundary."""
    result = run_causal_sweep(rsi_with_repeated_reanchors(), WalkBackAnchorPolicy(), PARAMS)

    assert any(s.end_reason == "re_anchored" for s in result.segments)


def test_segments_never_have_an_inverted_validity_window():
    for rsi in (falling_then_breaking_rsi(), rsi_with_repeated_reanchors()):
        result = run_causal_sweep(rsi, WalkBackAnchorPolicy(), PARAMS)
        for segment in result.segments:
            assert segment.valid_to_bar >= segment.valid_from_bar


def test_sweep_emits_a_long_signal_when_rsi_breaks_a_down_line():
    rsi = falling_then_breaking_rsi()
    result = run_causal_sweep(rsi, WalkBackAnchorPolicy(), PARAMS)

    longs = [s for s in result.signals if s.side == "LONG"]
    assert longs, "expected at least one LONG break"

    signal = longs[0]
    assert signal.rsi_value > signal.line_value_at_break
    assert any(s.segment_id == signal.segment_id for s in result.segments)


def test_a_broken_segment_is_closed_with_the_broken_reason():
    rsi = falling_then_breaking_rsi()
    result = run_causal_sweep(rsi, WalkBackAnchorPolicy(), PARAMS)

    signal = [s for s in result.signals if s.side == "LONG"][0]
    segment = [s for s in result.segments if s.segment_id == signal.segment_id][0]

    assert segment.end_reason == "broken"
    assert segment.valid_to_bar == signal.bar_index


def test_a_broken_line_never_fires_twice():
    rsi = falling_then_breaking_rsi()
    result = run_causal_sweep(rsi, WalkBackAnchorPolicy(), PARAMS)

    fired = [s.segment_id for s in result.signals]
    assert len(fired) == len(set(fired))


def test_no_segment_becomes_valid_before_its_newest_anchor_confirms():
    rsi = falling_then_breaking_rsi()
    result = run_causal_sweep(rsi, WalkBackAnchorPolicy(), PARAMS)

    assert result.segments
    for segment in result.segments:
        assert segment.valid_from_bar >= segment.anchor_b.confirmation_bar_index
        assert segment.anchor_a.bar_index < segment.anchor_b.bar_index


def test_no_pivot_ever_pokes_through_its_own_segment():
    rsi = falling_then_breaking_rsi()
    result = run_causal_sweep(rsi, WalkBackAnchorPolicy(), PARAMS)

    assert result.segments
    for segment in result.segments:
        same_kind = [p for p in result.pivots if p.kind == segment.anchor_b.kind]
        for pivot in same_kind:
            if not (segment.line.start_bar_index < pivot.bar_index < segment.line.end_bar_index):
                continue
            value = segment.line.value_at(pivot.bar_index)
            if segment.line.direction == "down":
                assert pivot.rsi_value <= value + PARAMS.tolerance
            else:
                assert pivot.rsi_value >= value - PARAMS.tolerance


def test_flat_rsi_produces_no_segments_and_no_signals():
    rsi = pd.Series([50.0] * 40)

    result = run_causal_sweep(rsi, WalkBackAnchorPolicy(), PARAMS)

    assert result.segments == []
    assert result.signals == []


def test_segment_ids_are_unique_and_ascending():
    rsi = falling_then_breaking_rsi()
    result = run_causal_sweep(rsi, WalkBackAnchorPolicy(), PARAMS)

    ids = [s.segment_id for s in result.segments]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))
