"""
Tests for GannLadderAnalyzer, on synthetic bars so every case is unambiguous.
"""
import sys
import os

import pytest

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.gann_ladder_analyzer import GannLadderAnalyzer
from study_tool.event_logger import EventType


def bar(open_, high, low, close, timestamp=0):
    return {
        "open": open_, "high": high, "low": low,
        "close": close, "timestamp": timestamp,
    }


def level(price, source="center", kind="major", degree=0,
          ring=3, sub_index=None, segment_start=100.0, segment_end=110.0):
    """One ladder level. Segment span 10.0 means a sub-level gap of 1.25."""
    return {
        "price": price, "square": price, "source": source, "kind": kind,
        "degree": degree, "ring": ring, "sub_index": sub_index,
        "is_halfway": sub_index == 4,
        "segment_start": segment_start, "segment_end": segment_end,
        "direction": "up",
    }


LEVELS = [level(105.0)]


def analyzer(**overrides):
    config = {
        "breach_mode": "close",
        "confirmation_closes": 2,
        "touch_tolerance_sublevels": 0.1,
        "resolution_window_bars": 50,
        "retest_window_bars": 50,
        "instrument": "RELIANCE",
        "timeframe": "5",
        "price_scale": 1,
    }
    config.update(overrides)
    return GannLadderAnalyzer(config)


def types_of(events):
    return [e.event_type for e in events]


def run(an, bars, levels=None):
    """Feed bars in order, returning every event produced."""
    levels = levels if levels is not None else LEVELS
    out = []
    for index, b in enumerate(bars):
        out.extend(an.process_bar(b, index, levels))
    return out


def test_touch_within_tolerance_emits_only_a_touch():
    an = analyzer()
    events = run(an, [bar(104.0, 105.0, 103.5, 104.2)])
    assert types_of(events) == [EventType.LADDER_TOUCH]


def test_a_bar_nowhere_near_a_level_emits_nothing():
    an = analyzer()
    events = run(an, [bar(90.0, 91.0, 89.0, 90.5)])
    assert events == []


def test_cross_without_enough_closes_is_rejected_and_never_confirmed():
    an = analyzer()
    events = run(an, [
        bar(104.0, 106.0, 103.5, 105.5),   # crosses and closes above
        bar(105.5, 105.8, 103.0, 103.5),   # falls back before a 2nd close
    ])
    kinds = types_of(events)
    assert EventType.LADDER_CROSS in kinds
    assert EventType.LADDER_BREACH_REJECTED in kinds
    resolved = [e for e in events if e.event_type == EventType.LADDER_BREACH_RESOLVED]
    assert resolved and resolved[0].details["outcome"] == "NEVER_CONFIRMED"


def test_two_successive_closes_confirm_the_breach_with_an_id():
    an = analyzer()
    events = run(an, [
        bar(104.0, 106.0, 103.5, 105.5),
        bar(105.5, 107.0, 105.2, 106.5),
    ])
    confirmed = [e for e in events if e.event_type == EventType.LADDER_BREACH_CONFIRMED]
    assert len(confirmed) == 1
    assert confirmed[0].breach_id
    assert confirmed[0].level_price == 105.0
    assert confirmed[0].direction == "up"


def test_breach_id_is_deterministic_across_identical_runs():
    bars = [
        bar(104.0, 106.0, 103.5, 105.5),
        bar(105.5, 107.0, 105.2, 106.5),
    ]
    first = run(analyzer(), bars)
    second = run(analyzer(), bars)
    ids_first = [e.breach_id for e in first if e.breach_id]
    ids_second = [e.breach_id for e in second if e.breach_id]
    assert ids_first == ids_second
    assert ids_first


def test_retest_carries_the_parent_breach_id():
    an = analyzer()
    events = run(an, [
        bar(104.0, 106.0, 103.5, 105.5),
        bar(105.5, 107.0, 105.2, 106.5),   # confirmed here
        bar(106.5, 106.8, 105.0, 105.6),   # comes back to the level
    ])
    confirmed = next(e for e in events if e.event_type == EventType.LADDER_BREACH_CONFIRMED)
    retests = [e for e in events if e.event_type == EventType.LADDER_RETEST]
    assert retests
    assert retests[0].parent_breach_id == confirmed.breach_id


def test_retest_records_raw_measurements_not_a_verdict():
    an = analyzer()
    events = run(an, [
        bar(104.0, 106.0, 103.5, 105.5),
        bar(105.5, 107.0, 105.2, 106.5),
        bar(106.5, 106.8, 105.0, 105.6),
    ])
    retest = next(e for e in events if e.event_type == EventType.LADDER_RETEST)
    for key in ("bars_since_breach", "retest_extreme",
                "depth_in_sublevels", "crossed_back", "closes_beyond"):
        assert key in retest.details


def test_depth_in_sublevels_is_negative_when_price_stops_short():
    an = analyzer()
    events = run(an, [
        bar(104.0, 106.0, 103.5, 105.5),
        bar(105.5, 107.0, 105.2, 106.5),
        bar(106.5, 106.9, 106.0, 106.4),   # low 106.0, a full sub-level short
    ])
    retests = [e for e in events if e.event_type == EventType.LADDER_RETEST]
    if retests:
        assert retests[0].details["depth_in_sublevels"] < 0


def test_price_that_never_returns_resolves_never_retested():
    an = analyzer(resolution_window_bars=3, retest_window_bars=3)
    bars = [
        bar(104.0, 106.0, 103.5, 105.5),
        bar(105.5, 107.0, 105.2, 106.5),   # confirmed
        bar(106.5, 112.0, 106.4, 111.0),
        bar(111.0, 118.0, 110.8, 117.0),
        bar(117.0, 124.0, 116.5, 123.0),
    ]
    events = run(an, bars)
    resolved = [e for e in events if e.event_type == EventType.LADDER_BREACH_RESOLVED]
    assert resolved
    assert resolved[0].details["outcome"] == "NEVER_RETESTED"


def test_a_breach_still_open_at_the_end_resolves_with_none():
    an = analyzer()
    run(an, [
        bar(104.0, 106.0, 103.5, 105.5),
        bar(105.5, 107.0, 105.2, 106.5),
    ])
    events = an.finalize()
    resolved = [e for e in events if e.event_type == EventType.LADDER_BREACH_RESOLVED]
    assert resolved
    assert resolved[0].details["outcome"] is None
    assert resolved[0].details["truncated"] is True


def test_wick_mode_confirms_on_range_rather_than_close():
    # Rewritten 2026-10-16: the old version fed a single bar, which now has
    # no previous close and so cannot cross. A lead-in bar closing below the
    # level gives the wick bar a side to come from.
    an = analyzer(breach_mode="wick", confirmation_closes=1)
    events = run(an, [
        bar(104.0, 104.5, 103.5, 104.2),   # closes below 105, not reached
        bar(104.2, 106.0, 103.5, 104.2),   # wicks up through 105, closes back
    ])
    confirmed = [e for e in events if e.event_type == EventType.LADDER_BREACH_CONFIRMED]
    assert len(confirmed) == 1
    assert confirmed[0].direction == "up"


def test_wick_mode_first_bar_has_no_previous_close_and_cannot_cross():
    an = analyzer(breach_mode="wick", confirmation_closes=1)
    events = run(an, [bar(104.0, 106.0, 103.5, 104.2)])
    assert types_of(events) == [EventType.LADDER_TOUCH]


def test_events_carry_level_identity_and_scale():
    an = analyzer()
    events = run(an, [bar(104.0, 105.0, 103.5, 104.2)])
    touch = events[0]
    assert touch.level_source == "center"
    assert touch.level_kind == "major"
    assert touch.level_degree == 0
    assert touch.level_ring == 3
    assert touch.price_scale == 1
    assert touch.instrument == "RELIANCE"
    assert touch.timeframe == "5"


def test_state_round_trips_without_changing_output():
    bars = [
        bar(104.0, 106.0, 103.5, 105.5),
        bar(105.5, 107.0, 105.2, 106.5),
        bar(106.5, 106.8, 105.0, 105.6),
    ]
    straight = run(analyzer(), bars)

    split = analyzer()
    out = list(split.process_bar(bars[0], 0, LEVELS))
    saved = split.get_state()

    resumed = analyzer()
    resumed.restore_state(saved)
    for index in (1, 2):
        out.extend(resumed.process_bar(bars[index], index, LEVELS))

    assert types_of(out) == types_of(straight)


# -- Regression tests from the post-Task-6 code review -----------------------
#
# These four cover real defects found by tracing the state machine across
# multiple bars and multiple levels, rather than single isolated branches:
# same-price levels from different crosses colliding, a confirmed breach
# spawning a second independent cycle while still open, replayed bar_index
# silently corrupting counters, and wick mode never accumulating past 1.


def test_same_price_different_sources_do_not_cross_contaminate():
    # A Sun/Moon conjunction: two distinct levels happen to share a price.
    # Each must be tracked independently - one must not "confirm" using
    # closes accumulated by the other.
    an = analyzer()
    sun_level = level(105.0, source="sun")
    moon_level = level(105.0, source="moon")
    events = run(an, [bar(104.0, 106.0, 103.5, 105.5)], levels=[sun_level, moon_level])

    assert [e for e in events if e.event_type == EventType.LADDER_BREACH_CONFIRMED] == []
    crosses = [e for e in events if e.event_type == EventType.LADDER_CROSS]
    assert len(crosses) == 2
    assert {e.level_source for e in crosses} == {"sun", "moon"}


def test_confirmed_breach_does_not_spawn_a_second_cycle_while_open():
    an = analyzer()
    events = run(an, [
        bar(104.0, 106.0, 103.5, 105.5),
        bar(105.5, 107.0, 105.2, 106.5),   # confirmed here
        bar(106.5, 106.8, 105.0, 105.6),   # retest bar, not a fresh cycle
    ])
    confirmed = [e for e in events if e.event_type == EventType.LADDER_BREACH_CONFIRMED]
    assert len(confirmed) == 1

    after_confirm = [e for e in events if e.bar_index is not None and e.bar_index >= 2]
    spurious = [e for e in after_confirm
                if e.event_type in (EventType.LADDER_CROSS, EventType.LADDER_TOUCH)]
    assert spurious == []


def test_process_bar_rejects_a_replayed_or_out_of_order_bar_index():
    an = analyzer()
    an.process_bar(bar(104.0, 106.0, 103.5, 105.5), 0, LEVELS)
    an.process_bar(bar(105.5, 107.0, 105.2, 106.5), 1, LEVELS)
    try:
        an.process_bar(bar(105.5, 107.0, 105.2, 106.5), 1, LEVELS)
        assert False, "expected a ValueError for a repeated bar_index"
    except ValueError:
        pass


def test_wick_mode_pending_cross_needs_a_close_beyond_to_confirm():
    # Rewritten 2026-10-16: a pending wick cross is confirmed by a close
    # beyond the level, the same as close mode. A second wick alone no
    # longer counts.
    an = analyzer(breach_mode="wick", confirmation_closes=2)
    events = run(an, [
        bar(104.0, 104.5, 103.5, 104.2),   # lead-in, closes below
        bar(104.2, 106.0, 103.5, 104.2),   # wicks up through 105: cross, pending
        bar(104.2, 106.0, 104.1, 105.5),   # closes above 105: confirmed
    ])
    confirmed = [e for e in events if e.event_type == EventType.LADDER_BREACH_CONFIRMED]
    assert len(confirmed) == 1
    assert confirmed[0].direction == "up"
    assert confirmed[0].bar_index == 2


def test_wick_mode_a_second_wick_that_closes_back_rejects_the_pending_cross():
    an = analyzer(breach_mode="wick", confirmation_closes=2)
    events = run(an, [
        bar(104.0, 104.5, 103.5, 104.2),
        bar(104.2, 106.0, 103.5, 104.2),   # cross, pending
        bar(104.2, 106.0, 103.5, 104.3),   # wicks again but closes below
    ])
    kinds = types_of(events)
    assert EventType.LADDER_BREACH_CONFIRMED not in kinds
    assert EventType.LADDER_BREACH_REJECTED in kinds


def test_pending_cross_expires_when_level_leaves_the_ladder():
    # The level crosses but hasn't confirmed yet. The next bar's ladder no
    # longer contains it (e.g. the Moon moved to a different square) - the
    # pending cross must get a terminal event now, not linger forever.
    an = analyzer()
    events = list(an.process_bar(bar(104.0, 106.0, 103.5, 105.5), 0, LEVELS))
    events.extend(an.process_bar(bar(105.5, 105.8, 104.0, 105.6), 1, []))
    resolved = [e for e in events if e.event_type == EventType.LADDER_BREACH_RESOLVED]
    assert len(resolved) == 1
    assert resolved[0].details["outcome"] is None
    assert resolved[0].details["truncated"] is True
    assert resolved[0].details["reason"] == "level_left_ladder"
    assert an.pending == {}


def test_a_key_reused_after_expiry_starts_a_fresh_cycle():
    # Once a pending cross expires because its level left the ladder, a
    # later level reusing the same (source, square) key must not inherit
    # the old accumulated close count.
    an = analyzer()
    an.process_bar(bar(104.0, 106.0, 103.5, 105.5), 0, LEVELS)   # crosses, pending
    an.process_bar(bar(105.5, 105.8, 104.0, 105.6), 1, [])       # level dropped, expires
    events = list(an.process_bar(bar(104.0, 106.0, 103.5, 105.5), 2, LEVELS))
    kinds = types_of(events)
    assert EventType.LADDER_CROSS in kinds
    assert EventType.LADDER_BREACH_CONFIRMED not in kinds


def test_finalize_resolves_a_pending_cross_left_open_at_the_end():
    an = analyzer()
    run(an, [bar(104.0, 106.0, 103.5, 105.5)])   # crosses, never confirms
    events = an.finalize()
    resolved = [e for e in events if e.event_type == EventType.LADDER_BREACH_RESOLVED]
    assert len(resolved) == 1
    assert resolved[0].details["outcome"] is None
    assert resolved[0].details["truncated"] is True
    assert resolved[0].details["reason"] == "end_of_data"
    assert an.pending == {}


def test_finalize_stamps_the_true_last_bars_timestamp_not_a_bare_index():
    # Previously finalize() passed an empty bar dict into _make_event, so
    # the resolved event's timestamp fell back to the raw bar_index integer
    # - e.g. bar_index=1 read back as an epoch timestamp near 1970, not the
    # bar's actual timestamp.
    an = analyzer()
    run(an, [
        bar(104.0, 106.0, 103.5, 105.5, timestamp=1_700_000_000),
        bar(105.5, 107.0, 105.2, 106.5, timestamp=1_700_000_300),
    ])
    resolved = an.finalize()
    assert resolved
    for event in resolved:
        assert event.timestamp == 1_700_000_300


def test_finalize_carries_full_level_identity():
    an = analyzer()
    run(an, [
        bar(104.0, 106.0, 103.5, 105.5),
        bar(105.5, 107.0, 105.2, 106.5),
    ])
    resolved = an.finalize()[0]
    assert resolved.level_segment_start == LEVELS[0]["segment_start"]
    assert resolved.level_segment_end == LEVELS[0]["segment_end"]
    assert resolved.level_sub_index == LEVELS[0]["sub_index"]
    assert resolved.level_is_halfway == LEVELS[0]["is_halfway"]


# -- Wick mode as a breach rule (2026-10-16 breach sweep) ---------------------
#
# Wick up: previous close below the level, this bar's high above it.
# Wick down: previous close above the level, this bar's low below it.
# The "reached" gate still runs first.


def test_wick_mode_a_wick_down_from_above_that_closes_back_above_is_a_down_cross():
    an = analyzer(breach_mode="wick", confirmation_closes=1)
    events = run(an, [
        bar(106.5, 107.0, 106.0, 106.5),   # above 105, not reached
        bar(106.5, 106.6, 104.5, 105.8),   # wicks down through 105, closes above
    ])
    crosses = [e for e in events if e.event_type == EventType.LADDER_CROSS]
    assert [e.direction for e in crosses] == ["down"]


def test_wick_mode_a_bar_within_tolerance_that_never_goes_through_is_a_touch():
    an = analyzer(breach_mode="wick", confirmation_closes=1)
    events = run(an, [
        bar(104.0, 104.5, 103.5, 104.2),   # below, not reached
        bar(104.2, 104.9, 104.0, 104.5),   # high within 0.125 of 105, not through
    ])
    assert types_of(events) == [EventType.LADDER_TOUCH]


def test_wick_mode_a_bar_wholly_above_with_its_low_inside_tolerance_is_a_touch():
    an = analyzer(breach_mode="wick", confirmation_closes=1)
    events = run(an, [
        bar(105.6, 106.0, 105.4, 105.5),   # above, not reached
        bar(105.5, 106.0, 105.1, 105.5),   # low 105.1 within tolerance, never below
    ])
    assert types_of(events) == [EventType.LADDER_TOUCH]


def test_wick_mode_a_clean_wick_up_from_below_is_an_up_cross():
    an = analyzer(breach_mode="wick", confirmation_closes=1)
    events = run(an, [
        bar(104.0, 104.5, 103.5, 104.2),
        bar(104.2, 105.6, 104.0, 105.4),
    ])
    crosses = [e for e in events if e.event_type == EventType.LADDER_CROSS]
    confirmed = [e for e in events if e.event_type == EventType.LADDER_BREACH_CONFIRMED]
    assert [e.direction for e in crosses] == ["up"]
    assert len(confirmed) == 1


def test_wick_mode_a_gap_wholly_past_the_tolerance_is_not_tested():
    an = analyzer(breach_mode="wick", confirmation_closes=1)
    events = run(an, [
        bar(104.0, 104.5, 103.5, 104.2),
        bar(106.0, 107.0, 105.9, 106.5),   # gaps over 105 by more than 0.125
    ])
    assert events == []


def test_wick_mode_previous_close_survives_a_state_round_trip():
    bars = [bar(104.0, 104.5, 103.5, 104.2), bar(104.2, 105.6, 104.0, 105.4)]
    straight = run(analyzer(breach_mode="wick", confirmation_closes=1), bars)

    split = analyzer(breach_mode="wick", confirmation_closes=1)
    out = list(split.process_bar(bars[0], 0, LEVELS))
    resumed = analyzer(breach_mode="wick", confirmation_closes=1)
    resumed.restore_state(split.get_state())
    out.extend(resumed.process_bar(bars[1], 1, LEVELS))

    assert types_of(out) == types_of(straight)
    assert EventType.LADDER_CROSS in types_of(out)


def test_an_unknown_breach_mode_is_refused():
    with pytest.raises(ValueError, match="breach_mode"):
        analyzer(breach_mode="body")
