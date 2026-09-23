"""
Data plumbing and sweep orchestration for the 0DTE ORB test.

Alpaca will not list expired option contracts, so each session's contract
symbol is constructed from the breakout spot rather than looked up. Bars are
cached on disk because the same sessions get re-read across every sweep cell.
"""

import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests

sys.path.append(str(Path(__file__).resolve().parents[2]))

from strategy.zero_dte.core import (
    Breakout,
    OptionTrade,
    atm_strike,
    find_breakout,
    occ_symbol,
    simulate_option_trade,
    split_sessions,
    summarise,
)

CACHE_DIR = Path(__file__).resolve().parents[2] / "data_cache" / "zero_dte"


class BarSource:
    """Alpaca bars with a disk cache keyed by symbol and date range."""

    def __init__(self, client, cache_dir: Path = CACHE_DIR):
        self.client = client
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._misses = 0

    def _cached(self, key: str, fetch) -> pd.DataFrame:
        path = self.cache_dir / f"{key}.parquet"
        if path.exists():
            return self._normalise(pd.read_parquet(path))

        self._misses += 1
        frame = pd.DataFrame(self._fetch_with_retry(fetch))
        # An empty frame is a real answer (no contract traded); cache it too.
        frame.to_parquet(path)
        return self._normalise(frame)

    @staticmethod
    def _fetch_with_retry(fetch, attempts: int = 6):
        """Retry through Alpaca's 429s. A sweep re-reads hundreds of contracts."""
        for attempt in range(attempts):
            try:
                return fetch()
            except requests.HTTPError as exc:
                throttled = exc.response is not None and exc.response.status_code == 429
                if not throttled or attempt == attempts - 1:
                    raise
                time.sleep(2**attempt)
        raise RuntimeError("unreachable")

    @staticmethod
    def _normalise(frame: pd.DataFrame) -> pd.DataFrame:
        # The Alpaca client emits bar-open epochs as 'time'; the session maths
        # expects 'timestamp'.
        if "time" in frame.columns and "timestamp" not in frame.columns:
            return frame.rename(columns={"time": "timestamp"})
        return frame

    def underlying(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        key = f"{symbol}_1Min_{start}_{end}"
        return self._cached(
            key,
            lambda: self.client.fetch_bars(
                symbol, "1Min", start=f"{start}T00:00:00Z", end=f"{end}T23:59:59Z"
            ),
        )

    def option(self, occ: str, session_date: date) -> pd.DataFrame:
        key = f"{occ}_{session_date}"
        nxt = session_date + timedelta(days=1)
        return self._cached(
            key,
            lambda: self.client.fetch_bars(
                occ, "1Min", start=f"{session_date}T00:00:00Z", end=f"{nxt}T23:59:59Z"
            ),
        )


def run_cell(
    sessions: Dict[date, pd.DataFrame],
    bar_source: BarSource,
    underlying: str,
    or_minutes: int,
    spread_pct: float,
    take_profit_pct: float = 1.0,
    stop_loss_pct: float = 0.5,
    fee_per_contract: float = 0.05,
    notional: float = 500.0,
    strike_increment: float = 1.0,
    breakout_rule: str = "close",
    entry_timing: str = "next_open",
) -> Tuple[List[OptionTrade], Dict[str, int]]:
    """Run one (or_minutes, spread) combination across every session."""
    trades: List[OptionTrade] = []
    skips: Dict[str, int] = {}

    for session_date, session in sessions.items():
        breakout = find_breakout(
            session,
            or_minutes=or_minutes,
            bar_minutes=1,
            breakout_rule=breakout_rule,
            entry_timing=entry_timing,
        )
        if not breakout.triggered:
            skips[breakout.reason] = skips.get(breakout.reason, 0) + 1
            continue

        strike = atm_strike(breakout.spot_at_entry, increment=strike_increment)
        right = "C" if breakout.side == "CALL" else "P"
        symbol = occ_symbol(underlying, session_date, right, strike)

        option_bars = bar_source.option(symbol, session_date)
        if option_bars.empty:
            skips["no_option_data"] = skips.get("no_option_data", 0) + 1
            continue

        trade = simulate_option_trade(
            breakout,
            option_bars,
            symbol=symbol,
            strike=strike,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            spread_pct=spread_pct,
            fee_per_contract=fee_per_contract,
            notional=notional,
        )
        if trade is None:
            skips["unfillable"] = skips.get("unfillable", 0) + 1
            continue

        trades.append(trade)

    return trades, skips


def load_sessions(
    bar_source: BarSource, underlying: str, start: date, end: date
) -> Dict[date, pd.DataFrame]:
    """Regular-hours sessions for the underlying, keyed by Eastern date."""
    raw = bar_source.underlying(underlying, start, end)
    if raw.empty:
        raise RuntimeError(f"no {underlying} bars returned for {start}..{end}")

    sessions = split_sessions(raw)
    # Alpaca includes pre/post market bars; the opening-range logic keys off
    # clock time, so out-of-hours bars are harmless but sessions with no
    # regular-hours data are not worth carrying.
    return {d: s for d, s in sessions.items() if len(s) > 60}
