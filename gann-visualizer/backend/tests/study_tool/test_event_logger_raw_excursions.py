"""
Raw forward excursions, recorded alongside the directional MFE/MAE.

For an event with no direction, enrich_with_forward_outcomes labels the larger
of the two moves as 'favourable'. That is decided after the fact, so nothing
could have predicted it, and using it as a training label would leak. Raw
up/down excursions are recorded so mining can pick the honest one.

The existing directional behaviour must not change - the angular-coverage
strategy already depends on it.
"""
import sys
import os

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.event_logger import Event, EventLogger, EventType


def candle(t, high, low, close=None):
    return {"time": t, "open": low, "high": high, "low": low,
            "close": close if close is not None else low}


def make_logger(event):
    logger = EventLogger()
    logger.events = [event]
    return logger


def base_event(direction=None):
    return Event(
        timestamp=1000,
        event_type=EventType.LADDER_TOUCH,
        price=100.0,
        direction=direction,
        bar_index=0,
    )


def rising_then_falling():
    """From price 100: up to 106 (exc_up 6), down to 97 (exc_down 3)."""
    return [
        candle(1000, 100.0, 100.0),
        candle(1001, 106.0, 99.0),
        candle(1002, 101.0, 97.0),
    ]


def test_raw_excursions_recorded_at_every_horizon_not_just_10():
    """
    exc_up_10 / exc_down_10 already worked. The other three horizons discarded
    theirs with `_, _`.
    """
    event = base_event(direction=None)
    make_logger(event).enrich_with_forward_outcomes(rising_then_falling())

    for horizon in (5, 10, 20, 50):
        assert getattr(event, f"exc_up_{horizon}") is not None, \
            f"exc_up_{horizon} not populated"
        assert getattr(event, f"exc_down_{horizon}") is not None, \
            f"exc_down_{horizon} not populated"


def test_raw_excursions_do_not_depend_on_which_move_was_larger():
    """The whole point: they are not sorted by outcome."""
    event = base_event(direction=None)
    make_logger(event).enrich_with_forward_outcomes(rising_then_falling())

    assert event.exc_up_5 == 6.0, "up must stay up, not become 'mfe'"
    assert event.exc_down_5 == 3.0


def test_directional_mfe_mae_behaviour_is_unchanged():
    """Regression guard for the angular-coverage strategy."""
    event = base_event(direction="up")
    make_logger(event).enrich_with_forward_outcomes(rising_then_falling())

    assert event.mfe_5 == 6.0
    assert event.mae_5 == 3.0


def test_raw_excursions_survive_the_serialisation_round_trip():
    event = base_event(direction=None)
    make_logger(event).enrich_with_forward_outcomes(rising_then_falling())

    restored = Event.from_dict(event.to_dict())
    for horizon in (5, 10, 20, 50):
        assert getattr(restored, f"exc_up_{horizon}") == \
            getattr(event, f"exc_up_{horizon}")
        assert getattr(restored, f"exc_down_{horizon}") == \
            getattr(event, f"exc_down_{horizon}")
