"""
Twelve Data Market Data Client for Gann Visualizer

This module provides spot FX data from Twelve Data, and matches the existing
DhanClient/YFinanceClient/BinanceClient/AlpacaClient interface patterns.

Twelve Data is the FX counterpart to AlpacaClient (US), DhanClient (India) and
BinanceClient (crypto). None of those carry fiat-to-fiat pairs: Alpaca's forex
endpoint returns rates rather than bars, and Binance's EUR/USDT-style markets
are crypto order books quoted against a stablecoin, not FX.

Base URL: https://api.twelvedata.com

Credentials come from TWELVEDATA_API_KEY in the repo-root .env.

PRICES ARE MID, AND THERE IS NO VOLUME. Twelve Data's Forex API v2 builds each
bar from a weighted average across 60+ liquidity providers, so open/high/low/close
are real OHLC but sit at the midpoint of the spread — no bid or ask is exposed.
Backtests must therefore subtract the spread explicitly in the cost model; the
feed will never do it for you. FX has no central exchange to count turnover, so
the volume column is always 0.0 and must not be read as "no trading happened".

4Min is NOT a native Twelve Data interval, so it is synthesized by aggregating
1min bars — same approach as the yfinance and Binance clients.

Pagination is by date window, not page token: outputsize caps at 5000 bars, so
a full range is walked forward from the last datetime returned.
"""

import os
import re
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any

import requests
import pandas as pd

from cache_manager import get_cache
from timeframe_utils import aggregate_1m_to_4m


class TwelveDataClient:
    """Twelve Data client covering spot FX (and, incidentally, stocks/crypto)."""

    BASE = "https://api.twelvedata.com"

    # Twelve Data native intervals. "4" is absent deliberately — see SYNTHESIZED.
    RESOLUTION_MAP = {
        "1": "1min",
        "5": "5min",
        "15": "15min",
        "30": "30min",
        "45": "45min",
        "60": "1h",
        "1H": "1h",
        "120": "2h",
        "240": "4h",
        "480": "8h",
        "D": "1day",
        "1D": "1day",
        "W": "1week",
        "1W": "1week",
        "M": "1month",
        "1M": "1month",
    }

    # Resolutions built by aggregating a lower native interval: {resolution: source}
    SYNTHESIZED = {"4": "1min"}

    # Bars per request. 5000 is Twelve Data's documented maximum for outputsize.
    PAGE_LIMIT = 5000

    # Guard against an unbounded walk if the cursor ever fails to advance.
    MAX_PAGES = 200

    # Fiat-to-fiat pair, e.g. EUR/USD
    FOREX_SYMBOL_RE = re.compile(r"^[A-Z]{3}/[A-Z]{3}$")

    # Shape alone cannot separate FX from crypto: BTC/USD and XAU/USD are both
    # three-on-three. An explicit code list is the only reliable discriminator.
    # ISO 4217, restricted to codes Twelve Data actually quotes, plus the
    # precious-metal codes (X*) that trade and chart exactly like FX pairs.
    CURRENCY_CODES = frozenset({
        "AED", "ARS", "AUD", "BGN", "BHD", "BRL", "CAD", "CHF", "CLP", "CNH",
        "CNY", "COP", "CZK", "DKK", "EGP", "EUR", "GBP", "HKD", "HRK", "HUF",
        "IDR", "ILS", "INR", "ISK", "JPY", "KRW", "KWD", "MXN", "MYR", "NGN",
        "NOK", "NZD", "OMR", "PEN", "PHP", "PKR", "PLN", "QAR", "RON", "RUB",
        "SAR", "SEK", "SGD", "THB", "TRY", "TWD", "UAH", "USD", "VND", "ZAR",
        "XAU", "XAG", "XPT", "XPD",
    })

    POPULAR_SYMBOLS = {
        "EUR/USD": {"name": "Euro / US Dollar", "exchange": "FOREX", "type": "forex"},
        "GBP/USD": {"name": "British Pound / US Dollar", "exchange": "FOREX", "type": "forex"},
        "USD/JPY": {"name": "US Dollar / Japanese Yen", "exchange": "FOREX", "type": "forex"},
        "USD/CHF": {"name": "US Dollar / Swiss Franc", "exchange": "FOREX", "type": "forex"},
        "AUD/USD": {"name": "Australian Dollar / US Dollar", "exchange": "FOREX", "type": "forex"},
        "USD/CAD": {"name": "US Dollar / Canadian Dollar", "exchange": "FOREX", "type": "forex"},
        "NZD/USD": {"name": "New Zealand Dollar / US Dollar", "exchange": "FOREX", "type": "forex"},
        "EUR/GBP": {"name": "Euro / British Pound", "exchange": "FOREX", "type": "forex"},
        "EUR/JPY": {"name": "Euro / Japanese Yen", "exchange": "FOREX", "type": "forex"},
        "GBP/JPY": {"name": "British Pound / Japanese Yen", "exchange": "FOREX", "type": "forex"},
        "USD/INR": {"name": "US Dollar / Indian Rupee", "exchange": "FOREX", "type": "forex"},
        "XAU/USD": {"name": "Gold / US Dollar", "exchange": "FOREX", "type": "forex"},
        "XAG/USD": {"name": "Silver / US Dollar", "exchange": "FOREX", "type": "forex"},
    }

    @staticmethod
    def _load_env_credentials() -> str:
        api_key = os.environ.get("TWELVEDATA_API_KEY", "")

        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
        if os.path.exists(env_file):
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    if key.strip() == "TWELVEDATA_API_KEY" and not api_key:
                        api_key = value.strip()

        return api_key

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or self._load_env_credentials()
        self.session = requests.Session()
        self.cache = get_cache()
        print("[TwelveData] Client initialized")

    # ─── Asset Class Routing ────────────────────────────────────────

    @classmethod
    def classify_symbol(cls, symbol: str) -> str:
        """Return 'forex' or 'other' for a symbol.

        Only forex is routed specially: it is the asset class this client exists
        for, and the one that needs the zero-volume and mid-price handling.
        Both legs must be known currency codes, or BTC/USD would classify as FX.
        """
        upper = symbol.upper()
        if not cls.FOREX_SYMBOL_RE.match(upper):
            return "other"

        base, _, quote = upper.partition("/")
        if base in cls.CURRENCY_CODES and quote in cls.CURRENCY_CODES:
            return "forex"
        return "other"

    @classmethod
    def tv_resolution_to_interval(cls, resolution: str) -> str:
        """Map a TradingView resolution to the interval actually requested.

        Synthesized resolutions return their SOURCE interval, so "4" maps to
        "1min" — the caller aggregates afterwards.
        """
        if resolution in cls.SYNTHESIZED:
            return cls.SYNTHESIZED[resolution]
        return cls.RESOLUTION_MAP.get(resolution, "1day")

    @staticmethod
    def _strip_suffix(symbol: str) -> str:
        return symbol[:-3] if symbol.endswith(":TD") else symbol

    # ─── Request Plumbing ───────────────────────────────────────────

    def _get(self, path: str, params: Dict[str, Any]) -> Dict:
        """GET a Twelve Data endpoint, surfacing in-body errors as exceptions.

        Twelve Data answers HTTP 200 for most application errors (bad symbol,
        credit limit reached, plan restriction) and signals them only via
        status/code in the JSON body, so checking the status code is not enough.
        """
        resp = self.session.get(f"{self.BASE}/{path}", params={**params, "apikey": self.api_key})
        resp.raise_for_status()
        data = resp.json()

        if isinstance(data, dict) and data.get("status") == "error":
            raise RuntimeError(f"Twelve Data error {data.get('code')}: {data.get('message')}")

        return data

    @staticmethod
    def _to_unix_seconds(value: str) -> int:
        """Parse a Twelve Data datetime as UTC.

        Intraday rows are 'YYYY-MM-DD HH:MM:SS'; daily and above are date-only.
        Requests pin timezone=UTC, so neither carries an offset.
        """
        text = value.strip()
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S") if " " in text else datetime.strptime(text, "%Y-%m-%d")
        return int(dt.replace(tzinfo=timezone.utc).timestamp())

    @staticmethod
    def _to_api_datetime(value: str) -> str:
        """Normalize 'YYYY-MM-DD' or a datetime to Twelve Data's expected format."""
        text = value.strip().replace("Z", "")
        if " " in text or "T" in text:
            return datetime.fromisoformat(text).strftime("%Y-%m-%d %H:%M:%S")
        return datetime.strptime(text, "%Y-%m-%d").strftime("%Y-%m-%d %H:%M:%S")

    # ─── Bars ───────────────────────────────────────────────────────

    def fetch_bars(
        self,
        symbol: str,
        interval: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch OHLC bars for one symbol, walking the date range in pages.

        `interval` is a NATIVE Twelve Data interval (1min, 1h, 1day, ...), not a
        TradingView resolution. Returns candle dicts in the shared state-machine
        format: {time (unix seconds), open, high, low, close, volume}.
        """
        symbol = self._strip_suffix(symbol)

        params: Dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "timezone": "UTC",
            "order": "ASC",
            "dp": 5,
        }
        if end:
            params["end_date"] = end

        cursor = start
        all_bars: List[Dict[str, Any]] = []

        for _ in range(self.MAX_PAGES):
            params["outputsize"] = min(limit - len(all_bars), self.PAGE_LIMIT) if limit else self.PAGE_LIMIT
            if params["outputsize"] <= 0:
                break
            if cursor:
                params["start_date"] = cursor

            data = self._get("time_series", params)
            page = self._parse_bars(data.get("values") or [])
            if not page:
                break

            all_bars.extend(page)

            # No page token exists: advance past the last bar and ask again.
            # A full page is the only signal that more data may remain.
            if len(page) < params["outputsize"] or (limit and len(all_bars) >= limit):
                break

            next_cursor = datetime.fromtimestamp(page[-1]["time"], tz=timezone.utc) + timedelta(seconds=1)
            cursor = next_cursor.strftime("%Y-%m-%d %H:%M:%S")

        return all_bars

    @classmethod
    def _parse_bars(cls, raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Map Twelve Data rows to candle dicts.

        Every numeric field arrives as a string. Forex rows carry no volume key
        at all, so volume defaults to 0.0 rather than being treated as missing.
        """
        candles = []
        for b in raw:
            candles.append({
                "time": cls._to_unix_seconds(b["datetime"]),
                "open": float(b["open"]),
                "high": float(b["high"]),
                "low": float(b["low"]),
                "close": float(b["close"]),
                "volume": float(b.get("volume") or 0.0),
            })
        return candles

    def fetch_data(self, symbol: str, from_date: str, to_date: str, interval: str = "1") -> pd.DataFrame:
        """Compatible interface with DhanClient/YFinanceClient/BinanceClient/AlpacaClient.

        Returns DataFrame with columns: timestamp, open, high, low, close, volume.
        """
        symbol = self._strip_suffix(symbol)
        native_interval = self.tv_resolution_to_interval(interval)

        cached_df = self.cache.get(symbol, from_date, to_date, interval)
        if cached_df is not None:
            return cached_df

        print(f"[TwelveData] Fetching {symbol} | interval={interval} -> {native_interval} | {from_date} to {to_date}")

        try:
            candles = self.fetch_bars(
                symbol,
                native_interval,
                start=self._to_api_datetime(from_date),
                end=self._to_api_datetime(to_date),
            )
        except Exception as e:
            print(f"[TwelveData] fetch_data error for '{symbol}': {e}")
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        if not candles:
            print(f"[TwelveData] No data returned for {symbol}")
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = pd.DataFrame(candles).rename(columns={"time": "timestamp"})
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)

        if interval in self.SYNTHESIZED:
            df = aggregate_1m_to_4m(df)

        print(f"[TwelveData] Returning {len(df)} bars, range: "
              f"{datetime.fromtimestamp(df['timestamp'].iloc[0], tz=timezone.utc)} to "
              f"{datetime.fromtimestamp(df['timestamp'].iloc[-1], tz=timezone.utc)}")

        self.cache.put(symbol, from_date, to_date, interval, df, ttl=300.0)
        return df

    def fetch_candles(
        self,
        symbol: str,
        resolution: str,
        from_timestamp: int,
        to_timestamp: int,
    ) -> List[Dict[str, Any]]:
        """Compatible interface with BinanceClient.fetch_candles/AlpacaClient.fetch_candles."""
        native_interval = self.tv_resolution_to_interval(resolution)
        start = datetime.fromtimestamp(from_timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        end = datetime.fromtimestamp(to_timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        candles = self.fetch_bars(symbol, native_interval, start=start, end=end)

        if resolution in self.SYNTHESIZED and candles:
            df = pd.DataFrame(candles).rename(columns={"time": "timestamp"})
            df = aggregate_1m_to_4m(df)
            return df.rename(columns={"timestamp": "time"}).to_dict("records")

        return candles

    def get_current_price(self, symbol: str) -> float:
        """Latest mid price for the symbol."""
        symbol = self._strip_suffix(symbol)
        data = self._get("price", {"symbol": symbol})
        return float(data["price"])

    # ─── TradingView Compatibility ──────────────────────────────────

    @staticmethod
    def _pricescale(symbol: str) -> int:
        """Ticks per whole unit for chart rendering.

        FX quotes to 5 decimals, except JPY-quoted pairs which quote to 3.
        """
        return 1000 if symbol.upper().endswith("/JPY") else 100000

    def search(self, query: str, limit: int = 20) -> list:
        """Search symbols. Returns list of symbol info dicts."""
        query_upper = query.upper()
        results = []

        for symbol, info in self.POPULAR_SYMBOLS.items():
            if query_upper in symbol.upper() or query_upper in info["name"].upper():
                results.append({
                    "symbol": symbol,
                    "full_name": info["name"],
                    "exchange": info["exchange"],
                    "type": info["type"],
                    "description": f"{info['name']} ({info['exchange']})",
                })
                if len(results) >= limit:
                    break

        if not results:
            try:
                data = self._get("forex_pairs", {"symbol": query_upper})
                for pair in data.get("data", [])[:limit]:
                    results.append({
                        "symbol": pair["symbol"],
                        "full_name": pair["symbol"],
                        "exchange": "FOREX",
                        "type": "forex",
                        "description": f"{pair.get('currency_base', '')} / {pair.get('currency_quote', '')}".strip(" /"),
                    })
            except Exception as e:
                print(f"[TwelveData] Search error for '{query}': {e}")

        return results[:limit]

    def get_info(self, symbol: str) -> Optional[dict]:
        """Symbol information for TradingView resolveSymbol."""
        symbol = self._strip_suffix(symbol)

        info = self.POPULAR_SYMBOLS.get(symbol.upper())
        if info is None:
            if self.classify_symbol(symbol) != "forex":
                print(f"[TwelveData] get_info: '{symbol}' is not a recognized FX pair")
                return None
            info = {"name": symbol.upper(), "exchange": "FOREX", "type": "forex"}

        return {
            "symbol": symbol.upper(),
            "name": info["name"],
            "full_name": info["name"],
            "exchange": info["exchange"],
            "type": info["type"],
            "description": info["name"],
            # FX runs continuously from Sunday evening to Friday evening UTC.
            "timezone": "Etc/UTC",
            "session": "24x7",
            "has_intraday": True,
            "intraday_multipliers": ["1", "4", "5", "15", "30", "60", "240"],
            "has_daily": True,
            "has_weekly_and_monthly": True,
            "supported_resolutions": ["1", "4", "5", "15", "30", "60", "240", "D", "W", "M"],
            "has_no_volume": True,
            "pricescale": self._pricescale(symbol),
            "minmov": 1,
        }


# Simple test
if __name__ == "__main__":
    client = TwelveDataClient()

    print("\n=== FX Daily (EUR/USD) ===")
    print(client.fetch_data("EUR/USD", "2026-08-01", "2026-09-08", "D").tail(3))

    print("\n=== FX 1h (GBP/USD) ===")
    print(client.fetch_data("GBP/USD", "2026-09-08", "2026-09-12", "60").head(3))

    print("\n=== FX 4m synthesized (EUR/USD) ===")
    print(client.fetch_data("EUR/USD", "2026-09-11", "2026-09-12", "4").head(3))

    print("\n=== Current price (EUR/USD) ===")
    print(f"  {client.get_current_price('EUR/USD')}")

    print("\n=== Search ===")
    for r in client.search("JPY", limit=5):
        print(f"  {r['symbol']} - {r['description']}")
