import sys
import os
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.event_logger import EventLogger, EventType


def make_candles(prices, start_ts=1700000000, step=300):
    return [
        {"time": start_ts + i * step, "open": p, "high": p + 1, "low": p - 1, "close": p}
        for i, p in enumerate(prices)
    ]


def test_enrich_computes_mfe_mae_at_5_10_20_50_horizons():
    candles = make_candles(list(range(100, 151)))  # 51 bars, prices 100..150

    logger = EventLogger()
    logger.log_event(
        timestamp=candles[0]["time"],
        event_type=EventType.BREACH_CONFIRMED,
        price=100.0,
        direction="up",
    )

    logger.enrich_with_forward_outcomes(candles)
    e = logger.events[0]

    assert e.mfe_5 is not None and e.mfe_5 >= 5.0 and e.mfe_5 <= 7.0
    assert e.mfe_10 is not None and e.mfe_10 >= 10.0 and e.mfe_10 <= 12.0
    assert e.mfe_20 is not None and e.mfe_20 >= 20.0 and e.mfe_20 <= 22.0
    assert e.mfe_50 is not None and e.mfe_50 >= 49.0 and e.mfe_50 <= 51.0


def test_event_to_dict_emits_5_and_50_horizon_keys():
    candles = make_candles(list(range(100, 151)))
    logger = EventLogger()
    logger.log_event(
        timestamp=candles[0]["time"],
        event_type=EventType.BREACH_CONFIRMED,
        price=100.0,
        direction="up",
    )
    logger.enrich_with_forward_outcomes(candles)

    d = logger.events[0].to_dict()
    assert "mfe_5" in d
    assert "mae_5" in d
    assert "mfe_50" in d
    assert "mae_50" in d
