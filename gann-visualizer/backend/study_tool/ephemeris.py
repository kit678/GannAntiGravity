"""
Sun and Moon ecliptic longitude for a bar timestamp.

Ported from the GannSq9 repo's backend/app/utils/ephemeris.py, reduced to the
one question this corpus asks: where were the Sun and Moon at this instant?

Dhan returns bar timestamps as epoch seconds in true UTC (verified: epoch
1787629500 is 03:45 UTC, the 09:15 IST open), and swisseph's calc_ut expects
Universal Time, so the epoch is used directly. Applying an IST offset here
would shift the Moon by about 3 degrees - 3 grid squares - on every bar.
"""

import datetime
from typing import Tuple

import swisseph as swe

_FLAGS = swe.FLG_SWIEPH | swe.FLG_SPEED


def _julian_day(epoch_seconds: float) -> float:
    when = datetime.datetime.fromtimestamp(
        epoch_seconds, tz=datetime.timezone.utc
    )
    return swe.julday(
        when.year,
        when.month,
        when.day,
        when.hour + when.minute / 60.0 + when.second / 3600.0,
    )


def sun_moon_longitudes(epoch_seconds: float) -> Tuple[float, float]:
    """
    Return (sun_longitude, moon_longitude) in degrees, each in [0, 360).

    Args:
        epoch_seconds: UTC epoch seconds, as Dhan supplies on every bar.
    """
    jd = _julian_day(epoch_seconds)
    sun, _ = swe.calc_ut(jd, swe.SUN, _FLAGS)
    moon, _ = swe.calc_ut(jd, swe.MOON, _FLAGS)
    return sun[0] % 360.0, moon[0] % 360.0
