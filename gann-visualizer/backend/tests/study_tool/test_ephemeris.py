"""
Sun and Moon ecliptic longitude from a bar's UTC epoch.

Dhan bar timestamps are true UTC epoch seconds - epoch 1787629500 is 03:45
UTC, the 09:15 IST open - so they are passed straight through with no offset.
Getting this wrong would shift the Moon by ~3 degrees over 5.5 hours, which is
3 grid squares, so the convention is pinned by a test rather than a comment.
"""
import sys
import os

sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.ephemeris import sun_moon_longitudes

# 2026-08-25 03:45:00 UTC — the NSE open that day.
NSE_OPEN_EPOCH = 1787629500


def test_returns_both_longitudes_in_range():
    sun, moon = sun_moon_longitudes(NSE_OPEN_EPOCH)
    assert 0.0 <= sun < 360.0
    assert 0.0 <= moon < 360.0


def test_moon_moves_far_faster_than_the_sun():
    """~1 deg/day for the Sun, ~13 deg/day for the Moon. Catches a swapped pair."""
    sun_a, moon_a = sun_moon_longitudes(NSE_OPEN_EPOCH)
    sun_b, moon_b = sun_moon_longitudes(NSE_OPEN_EPOCH + 86400)

    sun_step = (sun_b - sun_a) % 360
    moon_step = (moon_b - moon_a) % 360

    assert 0.7 < sun_step < 1.3, f"sun moved {sun_step} deg/day"
    assert 11.0 < moon_step < 15.5, f"moon moved {moon_step} deg/day"


def test_epoch_is_read_as_utc_not_local():
    """
    5.5 hours of Moon motion is ~3 degrees. If the epoch were shifted by the
    IST offset, this difference would collapse or double.
    """
    _, moon_utc = sun_moon_longitudes(NSE_OPEN_EPOCH)
    _, moon_plus_ist = sun_moon_longitudes(NSE_OPEN_EPOCH + int(5.5 * 3600))

    step = (moon_plus_ist - moon_utc) % 360
    assert 2.0 < step < 4.0, f"5.5h of moon motion came out as {step} deg"


def test_repeated_calls_are_identical():
    """Determinism matters: the corpus must be reproducible."""
    assert sun_moon_longitudes(NSE_OPEN_EPOCH) == sun_moon_longitudes(NSE_OPEN_EPOCH)
