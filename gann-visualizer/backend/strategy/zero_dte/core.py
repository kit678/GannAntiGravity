"""
Pure logic for the 0DTE opening range breakout test. No I/O.

Bars are timestamped at bar OPEN in Unix seconds, matching the Alpaca client.
A 1-minute bar stamped 09:30 ET covers 09:30 to 09:31, so a five-minute opening
range is the bars stamped 09:30 through 09:34.

Two price bases are kept deliberately separate:

- The **observed** premium is the traded price in the bar data. Targets and
  stops are evaluated against it, because that is what a trader watching the
  tape would see.
- The **realised** fill is the observed price moved against us by half the
  bid/ask spread, plus a per-contract fee. Backtests that skip this are quoting
  a mid-price fill nobody gets.
"""

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ET = ZoneInfo("America/New_York")
SESSION_START = time(9, 30)
FLAT_BY = time(15, 30)

# Regulatory + exchange pass-through on a US option contract, per side.
# Alpaca charges no commission; this is the part no broker can remove.
DEFAULT_FEE_PER_CONTRACT = 0.05

# Round-trip bid/ask spread as a fraction of premium. Swept, never optimised:
# the best value is always zero, so a single assumed number proves nothing.
SPREAD_SWEEP: List[float] = [0.0, 0.01, 0.02, 0.04, 0.08, 0.12]


def occ_symbol(underlying: str, expiry: date, right: str, strike: float) -> str:
    """Build an OCC option symbol, e.g. SPY260904C00770000.

    Alpaca's contracts endpoint does not list expired contracts, so historical
    0DTE symbols have to be constructed rather than looked up.
    """
    right = right.upper()
    if right not in ("C", "P"):
        raise ValueError(f"right must be 'C' or 'P', got {right!r}")
    if strike <= 0:
        raise ValueError(f"strike must be positive, got {strike}")

    strike_thousandths = int(round(strike * 1000))
    return f"{underlying.upper()}{expiry:%y%m%d}{right}{strike_thousandths:08d}"


def atm_strike(spot: float, increment: float = 1.0) -> float:
    """Nearest tradable strike to spot."""
    if increment <= 0:
        raise ValueError(f"increment must be positive, got {increment}")
    return round(spot / increment) * increment


def attach_et(bars: pd.DataFrame) -> pd.DataFrame:
    """Add Eastern-time columns and a session date, sorted and de-duplicated."""
    if "timestamp" not in bars.columns:
        raise ValueError("bars must have a 'timestamp' column")
    if bars.empty:
        raise ValueError("bars must not be empty")

    out = bars.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
    out["et"] = pd.to_datetime(out["timestamp"], unit="s", utc=True).dt.tz_convert(ET)
    out["session_date"] = out["et"].dt.date
    out["et_time"] = out["et"].dt.time
    return out


def split_sessions(bars: pd.DataFrame) -> Dict[date, pd.DataFrame]:
    """Group bars into one frame per Eastern trading date."""
    enriched = attach_et(bars)
    return {
        session_date: group.reset_index(drop=True)
        for session_date, group in enriched.groupby("session_date", sort=True)
    }


def _minutes_from(reference: time, value: time) -> int:
    return (value.hour * 60 + value.minute) - (reference.hour * 60 + reference.minute)


@dataclass(frozen=True)
class Breakout:
    """One session's breakout signal, or the reason there wasn't one."""

    session_date: date
    side: Optional[str] = None  # 'CALL' or 'PUT'
    signal_time: Optional[datetime] = None
    entry_time: Optional[datetime] = None
    spot_at_entry: Optional[float] = None
    or_high: Optional[float] = None
    or_low: Optional[float] = None
    reason: Optional[str] = None
    # Which field of the entry bar is filled, and therefore whether that bar's
    # own range may still be scanned for the target and stop.
    entry_price_field: str = "open"

    @property
    def triggered(self) -> bool:
        return self.side is not None


def find_breakout(
    session: pd.DataFrame,
    or_minutes: int,
    bar_minutes: int = 1,
    session_start: time = SESSION_START,
    flat_by: time = FLAT_BY,
    breakout_rule: str = "close",
    entry_timing: str = "next_open",
) -> Breakout:
    """First bar after the opening range that breaks beyond it.

    ``breakout_rule``:
      - ``close`` — the bar must CLOSE beyond the range (confirmed, triggers later)
      - ``touch`` — the bar's high/low merely pierces the range (triggers earlier
        and more often, which is how most published descriptions read)

    ``entry_timing``:
      - ``next_open`` — fill the following bar's open. The honest choice: a bar's
        close is only known once the bar has ended, so filling at it is lookahead.
      - ``signal_close`` — fill the signal bar's own close, as the published
        version did. Kept only to reproduce their number, not to trade on.
    """
    if breakout_rule not in ("close", "touch"):
        raise ValueError(f"breakout_rule must be 'close' or 'touch', got {breakout_rule!r}")
    if entry_timing not in ("next_open", "signal_close"):
        raise ValueError(f"entry_timing must be 'next_open' or 'signal_close', got {entry_timing!r}")

    session_date = session["session_date"].iloc[0]
    offsets = session["et_time"].apply(lambda t: _minutes_from(session_start, t))

    or_mask = (offsets >= 0) & (offsets < or_minutes)
    or_bars = session[or_mask]
    expected_or_bars = or_minutes // bar_minutes
    if len(or_bars) < expected_or_bars:
        return Breakout(session_date, reason="short_opening_range")

    or_high = float(or_bars["high"].max())
    or_low = float(or_bars["low"].min())
    if or_high <= or_low:
        return Breakout(session_date, reason="degenerate_range")

    flat_offset = _minutes_from(session_start, flat_by)
    tradable = session[(offsets >= or_minutes) & (offsets <= flat_offset)]

    for position, (_, bar) in enumerate(tradable.iterrows()):
        if breakout_rule == "close":
            above, below = float(bar["close"]) > or_high, float(bar["close"]) < or_low
        else:
            above, below = float(bar["high"]) > or_high, float(bar["low"]) < or_low

        if above:
            side = "CALL"
        elif below:
            side = "PUT"
        else:
            continue

        if entry_timing == "signal_close":
            return Breakout(
                session_date=session_date,
                side=side,
                signal_time=bar["et"],
                entry_time=bar["et"],
                spot_at_entry=float(bar["close"]),
                or_high=or_high,
                or_low=or_low,
                entry_price_field="close",
            )

        # Entry is the next bar's open. If the breakout is the last tradable
        # bar there is nothing left to fill against.
        if position + 1 >= len(tradable):
            return Breakout(session_date, reason="breakout_too_late", or_high=or_high, or_low=or_low)

        entry_bar = tradable.iloc[position + 1]
        return Breakout(
            session_date=session_date,
            side=side,
            signal_time=bar["et"],
            entry_time=entry_bar["et"],
            spot_at_entry=float(entry_bar["open"]),
            or_high=or_high,
            or_low=or_low,
            entry_price_field="open",
        )

    return Breakout(session_date, reason="no_breakout", or_high=or_high, or_low=or_low)


@dataclass(frozen=True)
class OptionTrade:
    """Realised outcome of one bought-premium trade, after costs."""

    session_date: date
    side: str
    symbol: str
    strike: float
    entry_time: datetime
    exit_time: datetime
    observed_entry: float
    observed_exit: float
    fill_entry: float
    fill_exit: float
    contracts: int
    pnl: float
    return_pct: float
    exit_reason: str


def simulate_option_trade(
    breakout: Breakout,
    option_bars: pd.DataFrame,
    symbol: str,
    strike: float,
    take_profit_pct: float = 1.0,
    stop_loss_pct: float = 0.5,
    spread_pct: float = 0.0,
    fee_per_contract: float = DEFAULT_FEE_PER_CONTRACT,
    notional: float = 500.0,
    flat_by: time = FLAT_BY,
) -> Optional[OptionTrade]:
    """Walk the option's own bars forward from entry and resolve the exit.

    When a bar's range contains both the target and the stop, the stop wins.
    The bar data cannot say which came first, and assuming the good one is how
    a backtest flatters itself.
    """
    if not breakout.triggered:
        return None

    bars = attach_et(option_bars)
    at_or_after_entry = bars[bars["et"] >= breakout.entry_time]
    if at_or_after_entry.empty:
        return None

    entry_bar = at_or_after_entry.iloc[0]
    observed_entry = float(entry_bar[breakout.entry_price_field])
    if observed_entry <= 0:
        return None

    half_spread = spread_pct / 2.0
    fill_entry = observed_entry * (1 + half_spread)

    # Size off the OBSERVED price, never the spread-adjusted one. Sizing off the
    # fill makes contract count a function of the spread, which both confounds
    # the spread sweep and silently drops the most expensive premiums — the
    # highest-volatility days a breakout strategy lives on. At least one
    # contract always trades, so no session leaves the sample for being pricey.
    contracts = max(1, int(notional // (observed_entry * 100)))

    target = observed_entry * (1 + take_profit_pct)
    stop = observed_entry * (1 - stop_loss_pct)

    # Filling at a bar's close means that bar's own high and low already
    # happened before we were in the trade — scanning it would resolve the
    # trade against price action we could not have traded.
    scannable = at_or_after_entry.iloc[1:] if breakout.entry_price_field == "close" else at_or_after_entry
    # The date guard matters: et_time alone is a wall-clock time with no date, so
    # a next-day bar would satisfy it. Dead for 0DTE, fatal for anything longer.
    holdable = scannable[
        (scannable["et_time"] <= flat_by)
        & (scannable["session_date"] == breakout.session_date)
    ]
    if holdable.empty:
        return None
    observed_exit = float(holdable.iloc[-1]["close"])
    exit_time = holdable.iloc[-1]["et"]
    exit_reason = "time_stop"

    for _, bar in holdable.iterrows():
        hit_stop = float(bar["low"]) <= stop
        hit_target = float(bar["high"]) >= target
        if hit_stop:
            observed_exit, exit_time, exit_reason = stop, bar["et"], "stop_loss"
            break
        if hit_target:
            observed_exit, exit_time, exit_reason = target, bar["et"], "take_profit"
            break

    fill_exit = observed_exit * (1 - half_spread)
    gross = (fill_exit - fill_entry) * contracts * 100
    fees = fee_per_contract * contracts * 2
    pnl = gross - fees
    cost_basis = fill_entry * contracts * 100

    return OptionTrade(
        session_date=breakout.session_date,
        side=breakout.side,
        symbol=symbol,
        strike=strike,
        entry_time=breakout.entry_time,
        exit_time=exit_time,
        observed_entry=observed_entry,
        observed_exit=observed_exit,
        fill_entry=fill_entry,
        fill_exit=fill_exit,
        contracts=contracts,
        pnl=pnl,
        return_pct=pnl / cost_basis * 100 if cost_basis else 0.0,
        exit_reason=exit_reason,
    )


def summarise(trades: List[OptionTrade]) -> Dict[str, float]:
    """Headline stats for a set of trades.

    ``mean_return`` and its confidence interval are the number to judge on.
    Win rate and profit factor are reported because they are conventional, but
    both are dollar-weighted by contract count and neither carries the magnitude
    information needed to tell a real edge from a small sample.
    """
    if not trades:
        return {"trades": 0}

    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))

    returns = np.array([t.return_pct for t in trades], dtype=float)
    n = len(returns)
    mean_return = float(returns.mean())
    sd = float(returns.std(ddof=1)) if n > 1 else 0.0
    stderr = sd / math.sqrt(n) if n > 1 else 0.0

    return {
        "trades": n,
        "win_rate": len(wins) / n * 100,
        "take_profit_rate": sum(1 for t in trades if t.exit_reason == "take_profit") / n * 100,
        "total_pnl": sum(pnls),
        "avg_pnl": sum(pnls) / n,
        "avg_win": gross_win / len(wins) if wins else 0.0,
        "avg_loss": -gross_loss / len(losses) if losses else 0.0,
        "profit_factor": gross_win / gross_loss if gross_loss else float("inf"),
        "mean_return": mean_return,
        "return_sd": sd,
        "return_stderr": stderr,
        "ci_low": mean_return - 1.96 * stderr,
        "ci_high": mean_return + 1.96 * stderr,
        "t_stat": mean_return / stderr if stderr else 0.0,
    }


def minimum_detectable_effect(return_sd: float, n: int, power: float = 0.8) -> float:
    """Smallest per-trade mean return this sample size could actually detect.

    Reporting this alongside a null result is what separates "is zero" from
    "cannot tell" — the two claims a backtest is easiest to confuse.
    """
    if n < 2 or return_sd <= 0:
        return float("inf")
    z_alpha, z_beta = 1.96, 0.84 if power == 0.8 else 1.28
    return (z_alpha + z_beta) * return_sd / math.sqrt(n)
