"""Tests for the 0DTE opening range breakout core."""

from datetime import date, datetime, time

import pandas as pd
import pytest

from strategy.zero_dte.core import (
    ET,
    atm_strike,
    find_breakout,
    occ_symbol,
    simulate_option_trade,
    split_sessions,
    summarise,
)


def ts(hour: int, minute: int, day: int = 4) -> int:
    return int(datetime(2026, 9, day, hour, minute, tzinfo=ET).timestamp())


def bars(rows, day: int = 4) -> pd.DataFrame:
    """rows: (hour, minute, open, high, low, close)"""
    return pd.DataFrame(
        [
            {
                "timestamp": ts(h, m, day),
                "open": o,
                "high": hi,
                "low": lo,
                "close": c,
                "volume": 100.0,
            }
            for h, m, o, hi, lo, c in rows
        ]
    )


class TestOccSymbol:
    def test_builds_standard_call(self):
        assert occ_symbol("SPY", date(2026, 9, 4), "C", 770.0) == "SPY260904C00770000"

    def test_builds_put_with_fractional_strike(self):
        assert occ_symbol("SPY", date(2026, 9, 4), "P", 770.5) == "SPY260904P00770500"

    def test_rejects_bad_right(self):
        with pytest.raises(ValueError):
            occ_symbol("SPY", date(2026, 9, 4), "X", 770.0)


class TestAtmStrike:
    def test_rounds_to_nearest_dollar(self):
        assert atm_strike(770.4) == 770.0
        assert atm_strike(770.6) == 771.0

    def test_honours_increment(self):
        assert atm_strike(772.4, increment=5.0) == 770.0


class TestFindBreakout:
    def test_long_breakout_enters_on_next_bar_open(self):
        # OR (9:30-9:34) tops at 101. The 9:35 bar closes above it, so entry is
        # the 9:36 OPEN, not the 9:35 close.
        frame = bars(
            [
                (9, 30, 100, 101, 99, 100),
                (9, 31, 100, 101, 99, 100),
                (9, 32, 100, 101, 99, 100),
                (9, 33, 100, 101, 99, 100),
                (9, 34, 100, 101, 99, 100),
                (9, 35, 100, 103, 100, 102),
                (9, 36, 105, 106, 104, 105),
            ]
        )
        session = split_sessions(frame)[date(2026, 9, 4)]
        result = find_breakout(session, or_minutes=5)

        assert result.triggered
        assert result.side == "CALL"
        assert result.or_high == 101
        assert result.signal_time.hour == 9 and result.signal_time.minute == 35
        assert result.entry_time.minute == 36
        assert result.spot_at_entry == 105  # the 9:36 open

    def test_short_breakout_is_a_put(self):
        frame = bars(
            [
                (9, 30, 100, 101, 99, 100),
                (9, 31, 100, 101, 99, 100),
                (9, 32, 100, 101, 99, 100),
                (9, 33, 100, 101, 99, 100),
                (9, 34, 100, 101, 99, 100),
                (9, 35, 100, 100, 97, 98),
                (9, 36, 97, 98, 96, 96),
            ]
        )
        session = split_sessions(frame)[date(2026, 9, 4)]
        result = find_breakout(session, or_minutes=5)

        assert result.side == "PUT"
        assert result.or_low == 99

    def test_touching_the_range_without_closing_beyond_is_not_a_breakout(self):
        frame = bars(
            [
                (9, 30, 100, 101, 99, 100),
                (9, 31, 100, 101, 99, 100),
                (9, 32, 100, 101, 99, 100),
                (9, 33, 100, 101, 99, 100),
                (9, 34, 100, 101, 99, 100),
                (9, 35, 100, 104, 99, 100),  # pierces the high, closes inside
                (9, 36, 100, 104, 99, 100),
            ]
        )
        session = split_sessions(frame)[date(2026, 9, 4)]
        result = find_breakout(session, or_minutes=5)

        assert not result.triggered
        assert result.reason == "no_breakout"

    def test_incomplete_opening_range_is_skipped(self):
        frame = bars([(9, 30, 100, 101, 99, 100), (9, 31, 100, 105, 99, 104)])
        session = split_sessions(frame)[date(2026, 9, 4)]
        result = find_breakout(session, or_minutes=5)

        assert not result.triggered
        assert result.reason == "short_opening_range"


def a_breakout(session):
    return find_breakout(session, or_minutes=5)


UNDERLYING = [
    (9, 30, 100, 101, 99, 100),
    (9, 31, 100, 101, 99, 100),
    (9, 32, 100, 101, 99, 100),
    (9, 33, 100, 101, 99, 100),
    (9, 34, 100, 101, 99, 100),
    (9, 35, 100, 103, 100, 102),
    (9, 36, 105, 106, 104, 105),
]


class TestSimulateOptionTrade:
    def setup_method(self):
        self.breakout = a_breakout(split_sessions(bars(UNDERLYING))[date(2026, 9, 4)])

    def option(self, rows):
        return bars(rows)

    def test_take_profit_at_double(self):
        # Entry at the 9:36 open of 1.00. Target is 2.00, hit on the 9:38 bar.
        opt = self.option(
            [
                (9, 36, 1.00, 1.20, 0.95, 1.10),
                (9, 37, 1.10, 1.50, 1.05, 1.40),
                (9, 38, 1.40, 2.30, 1.35, 2.20),
            ]
        )
        trade = simulate_option_trade(
            self.breakout, opt, "SPY260904C00105000", 105.0, fee_per_contract=0.0
        )

        assert trade.exit_reason == "take_profit"
        assert trade.observed_entry == 1.00
        assert trade.observed_exit == pytest.approx(2.00)
        assert trade.pnl > 0

    def test_stop_loss_at_half(self):
        opt = self.option(
            [
                (9, 36, 1.00, 1.05, 0.95, 1.00),
                (9, 37, 1.00, 1.02, 0.40, 0.45),
            ]
        )
        trade = simulate_option_trade(
            self.breakout, opt, "SPY260904C00105000", 105.0, fee_per_contract=0.0
        )

        assert trade.exit_reason == "stop_loss"
        assert trade.observed_exit == pytest.approx(0.50)
        assert trade.pnl < 0

    def test_bar_containing_both_target_and_stop_is_scored_as_a_loss(self):
        opt = self.option(
            [
                (9, 36, 1.00, 1.05, 0.95, 1.00),
                (9, 37, 1.00, 2.50, 0.30, 1.00),  # spans both
            ]
        )
        trade = simulate_option_trade(
            self.breakout, opt, "SPY260904C00105000", 105.0, fee_per_contract=0.0
        )

        assert trade.exit_reason == "stop_loss"

    def test_time_stop_exits_at_the_last_holdable_close(self):
        opt = self.option(
            [
                (9, 36, 1.00, 1.05, 0.95, 1.00),
                (9, 37, 1.00, 1.10, 0.90, 0.95),
                (15, 30, 0.95, 1.00, 0.90, 0.92),
                (15, 45, 0.92, 0.95, 0.10, 0.11),  # after flat-by, must be ignored
            ]
        )
        trade = simulate_option_trade(
            self.breakout, opt, "SPY260904C00105000", 105.0, fee_per_contract=0.0
        )

        assert trade.exit_reason == "time_stop"
        assert trade.observed_exit == pytest.approx(0.92)

    def test_spread_and_fees_strictly_worsen_pnl(self):
        opt = self.option(
            [
                (9, 36, 1.00, 1.20, 0.95, 1.10),
                (9, 37, 1.10, 2.30, 1.05, 2.20),
            ]
        )
        free = simulate_option_trade(
            self.breakout, opt, "S", 105.0, spread_pct=0.0, fee_per_contract=0.0
        )
        spread_only = simulate_option_trade(
            self.breakout, opt, "S", 105.0, spread_pct=0.04, fee_per_contract=0.0
        )
        both = simulate_option_trade(
            self.breakout, opt, "S", 105.0, spread_pct=0.04, fee_per_contract=0.05
        )

        assert free.pnl > spread_only.pnl > both.pnl

    def test_expensive_premium_still_trades_one_contract(self):
        # Dropping sessions the notional cannot afford would systematically
        # remove the highest-volatility days, which is exactly where a breakout
        # strategy makes or loses its money.
        opt = self.option([(9, 36, 99.0, 120.0, 95.0, 110.0)])
        trade = simulate_option_trade(self.breakout, opt, "S", 105.0, notional=500.0)

        assert trade is not None
        assert trade.contracts == 1

    def test_contract_count_does_not_change_with_spread(self):
        # Sizing off the spread-adjusted fill would make position size a
        # function of the cost axis, confounding the whole spread sweep.
        opt = self.option([(9, 36, 1.60, 1.80, 1.50, 1.70), (9, 37, 1.70, 1.90, 1.60, 1.80)])
        counts = {
            simulate_option_trade(self.breakout, opt, "S", 105.0, spread_pct=s).contracts
            for s in (0.0, 0.02, 0.08, 0.20)
        }

        assert len(counts) == 1


class TestPublishedFidelityModes:
    """The two places my honest rules differ from the published description."""

    PIERCE_BUT_CLOSE_INSIDE = [
        (9, 30, 100, 101, 99, 100),
        (9, 31, 100, 101, 99, 100),
        (9, 32, 100, 101, 99, 100),
        (9, 33, 100, 101, 99, 100),
        (9, 34, 100, 101, 99, 100),
        (9, 35, 100, 104, 99, 100),  # pierces the high, closes back inside
        (9, 36, 100, 102, 99, 100),
    ]

    def session(self, rows):
        return split_sessions(bars(rows))[date(2026, 9, 4)]

    def test_touch_rule_fires_where_close_rule_does_not(self):
        session = self.session(self.PIERCE_BUT_CLOSE_INSIDE)

        assert not find_breakout(session, or_minutes=5, breakout_rule="close").triggered
        touch = find_breakout(session, or_minutes=5, breakout_rule="touch")
        assert touch.triggered
        assert touch.side == "CALL"

    def test_signal_close_entry_fills_the_breakout_bar_close(self):
        session = self.session(UNDERLYING)
        result = find_breakout(session, or_minutes=5, entry_timing="signal_close")

        assert result.entry_time == result.signal_time
        assert result.entry_price_field == "close"
        assert result.spot_at_entry == 102  # the 9:35 close, not the 9:36 open

    def test_close_filled_entry_bar_is_not_scanned_for_stop(self):
        # The 9:35 option bar dips to 0.10, but we only got filled at its 1.00
        # close. That dip is in the past and must not stop us out.
        session = self.session(UNDERLYING)
        breakout = find_breakout(session, or_minutes=5, entry_timing="signal_close")
        opt = bars(
            [
                (9, 35, 0.80, 1.05, 0.10, 1.00),
                (9, 36, 1.00, 2.10, 0.95, 2.00),
            ]
        )
        trade = simulate_option_trade(breakout, opt, "S", 105.0, fee_per_contract=0.0)

        assert trade.observed_entry == 1.00
        assert trade.exit_reason == "take_profit"


class TestSummarise:
    def test_empty(self):
        assert summarise([]) == {"trades": 0}
