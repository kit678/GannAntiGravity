"""
Alpaca Market Data Client for Gann Visualizer

This module provides US market data (stocks, options, crypto) from Alpaca.
Matches the existing DhanClient/YFinanceClient/BinanceClient interface patterns.

Alpaca is the US-market counterpart to DhanClient (India) and BinanceClient
(crypto), and replaces YFinanceClient for US symbols — Yahoo caps intraday
history at 8 days for 1m and 60 days for 2m-30m, while Alpaca serves minute
bars back to 2016 with no such window.

Base URLs:
  Data:          https://data.alpaca.markets
  Trading paper: https://paper-api.alpaca.markets
  Trading live:  https://api.alpaca.markets

Credentials come from ALPACA_API_KEY / ALPACA_API_SECRET in the repo-root .env.

Feeds: 'sip' is the full consolidated tape (all US exchanges), 'iex' is the IEX
exchange alone and carries roughly 3% of the volume. Default is sip, falling
back to iex if the account is not entitled — see _get_with_feed_fallback.

4Min is a NATIVE Alpaca timeframe. Unlike the yfinance and Binance clients,
this one never aggregates 1m bars to build 4m candles.
"""

import os
import re
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any

import requests
import pandas as pd

from cache_manager import get_cache


class AlpacaClient:
    """Alpaca data client covering US stocks, options, and crypto."""

    DATA_BASE = "https://data.alpaca.markets"
    PAPER_TRADING_BASE = "https://paper-api.alpaca.markets"
    LIVE_TRADING_BASE = "https://api.alpaca.markets"

    # Alpaca-native timeframes. Minute multiples 1-59, hour multiples 1-23 are
    # all accepted, so every resolution below maps without aggregation.
    RESOLUTION_MAP = {
        "1": "1Min",
        "2": "2Min",
        "4": "4Min",
        "5": "5Min",
        "15": "15Min",
        "30": "30Min",
        "60": "1Hour",
        "1H": "1Hour",
        "120": "2Hour",
        "240": "4Hour",
        "D": "1Day",
        "1D": "1Day",
        "W": "1Week",
        "1W": "1Week",
        "M": "1Month",
        "1M": "1Month",
    }

    # Bars per page. 10000 is Alpaca's documented maximum.
    PAGE_LIMIT = 10000

    # OCC option symbol, e.g. AAPL260909C00205000
    OPTION_SYMBOL_RE = re.compile(r"^[A-Z]{1,6}\d{6}[CP]\d{8}$")

    POPULAR_SYMBOLS = {
        "AAPL": {"name": "Apple Inc", "exchange": "NASDAQ", "type": "equity"},
        "MSFT": {"name": "Microsoft", "exchange": "NASDAQ", "type": "equity"},
        "GOOGL": {"name": "Alphabet (Google)", "exchange": "NASDAQ", "type": "equity"},
        "AMZN": {"name": "Amazon", "exchange": "NASDAQ", "type": "equity"},
        "TSLA": {"name": "Tesla", "exchange": "NASDAQ", "type": "equity"},
        "META": {"name": "Meta Platforms", "exchange": "NASDAQ", "type": "equity"},
        "NVDA": {"name": "NVIDIA", "exchange": "NASDAQ", "type": "equity"},
        "SPY": {"name": "SPDR S&P 500 ETF", "exchange": "NYSE", "type": "equity"},
        "QQQ": {"name": "Invesco QQQ Trust", "exchange": "NASDAQ", "type": "equity"},
        "IWM": {"name": "iShares Russell 2000 ETF", "exchange": "NYSE", "type": "equity"},
        "BTC/USD": {"name": "Bitcoin / US Dollar", "exchange": "CRYPTO", "type": "crypto"},
        "ETH/USD": {"name": "Ethereum / US Dollar", "exchange": "CRYPTO", "type": "crypto"},
    }

    @staticmethod
    def _load_env_credentials():
        api_key = os.environ.get("ALPACA_API_KEY", "")
        api_secret = os.environ.get("ALPACA_API_SECRET", "")

        env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
        if os.path.exists(env_file):
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    if key == "ALPACA_API_KEY" and not api_key:
                        api_key = value
                    elif key == "ALPACA_API_SECRET" and not api_secret:
                        api_secret = value

        return api_key, api_secret

    def __init__(self, api_key: str = "", api_secret: str = "", use_paper: bool = True, feed: str = "sip"):
        self.use_paper = use_paper
        self.trading_base = self.PAPER_TRADING_BASE if use_paper else self.LIVE_TRADING_BASE
        self.feed = feed

        env_key, env_secret = self._load_env_credentials()
        self.api_key = api_key or env_key
        self.api_secret = api_secret or env_secret

        self.session = requests.Session()
        self.session.headers.update({
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
        })

        self.cache = get_cache()
        print(f"[Alpaca] Client initialized (paper={use_paper}, feed={feed})")

    # ─── Asset Class Routing ────────────────────────────────────────

    @classmethod
    def classify_symbol(cls, symbol: str) -> str:
        """Return 'crypto', 'option', or 'stock' for a symbol."""
        if "/" in symbol:
            return "crypto"
        if cls.OPTION_SYMBOL_RE.match(symbol.upper()):
            return "option"
        return "stock"

    @classmethod
    def tv_resolution_to_timeframe(cls, resolution: str) -> str:
        return cls.RESOLUTION_MAP.get(resolution, "1Day")

    @staticmethod
    def _strip_suffix(symbol: str) -> str:
        return symbol[:-4] if symbol.endswith(":ALP") else symbol

    # ─── Request Plumbing ───────────────────────────────────────────

    def _get(self, url: str, params: Dict[str, Any]) -> Dict:
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    def _get_with_feed_fallback(self, url: str, params: Dict[str, Any]) -> Dict:
        """Try the configured feed, dropping to iex if the account lacks entitlement.

        A free account without SIP access answers 403 rather than returning the
        thinner feed, so retry explicitly instead of surfacing the error.
        """
        try:
            return self._get(url, params)
        except requests.HTTPError as e:
            unentitled = e.response is not None and e.response.status_code in (401, 403)
            if unentitled and params.get("feed") == "sip":
                # Free plans may read SIP history but not its newest 15 minutes. A chart asking for
                # bars up to "now" hits that limit, so retry SIP with the end moved back before giving
                # up on SIP (IEX has almost no pre-market / after-hours prints).
                end = params.get("end")
                if end:
                    try:
                        end_dt = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
                        cutoff = datetime.now(timezone.utc) - timedelta(minutes=16)
                        if end_dt.tzinfo is None:
                            end_dt = end_dt.replace(tzinfo=timezone.utc)
                        if end_dt > cutoff:
                            return self._get(url, {**params, "end": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")})
                    except Exception:
                        pass
                print("[Alpaca] SIP feed not entitled, falling back to iex")
                self.feed = "iex"
                return self._get(url, {**params, "feed": "iex"})
            raise

    @staticmethod
    def _to_unix_seconds(rfc3339: str) -> int:
        return int(datetime.fromisoformat(rfc3339.replace("Z", "+00:00")).timestamp())

    @staticmethod
    def _to_rfc3339(value: str) -> str:
        """Normalize 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS' to RFC3339 UTC."""
        text = value.strip().replace("Z", "")
        if " " in text:
            dt = datetime.fromisoformat(text)
        elif "T" in text:
            dt = datetime.fromisoformat(text)
        else:
            dt = datetime.strptime(text, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")

    # ─── Bars ───────────────────────────────────────────────────────

    def fetch_bars(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch OHLCV bars for one symbol, paginating until the range is covered.

        Returns candle dicts in the shared state-machine format:
        {time (unix seconds), open, high, low, close, volume}
        """
        symbol = self._strip_suffix(symbol)
        asset_class = self.classify_symbol(symbol)

        if asset_class == "crypto":
            url = f"{self.DATA_BASE}/v1beta3/crypto/us/bars"
            params: Dict[str, Any] = {"symbols": symbol, "timeframe": timeframe}
            keyed_by_symbol = True
            use_feed = False
        elif asset_class == "option":
            url = f"{self.DATA_BASE}/v1beta1/options/bars"
            params = {"symbols": symbol.upper(), "timeframe": timeframe}
            keyed_by_symbol = True
            use_feed = False
        else:
            url = f"{self.DATA_BASE}/v2/stocks/{symbol.upper()}/bars"
            params = {"timeframe": timeframe, "adjustment": "split"}
            keyed_by_symbol = False
            use_feed = True

        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if use_feed:
            params["feed"] = self.feed

        all_bars: List[Dict[str, Any]] = []
        page_token = None

        while True:
            params["limit"] = min(limit - len(all_bars), self.PAGE_LIMIT) if limit else self.PAGE_LIMIT
            if params["limit"] <= 0:
                break
            if page_token:
                params["page_token"] = page_token

            data = self._get_with_feed_fallback(url, params) if use_feed else self._get(url, params)

            raw = data.get("bars") or {}
            page = raw.get(symbol if asset_class == "crypto" else symbol.upper(), []) if keyed_by_symbol else raw
            all_bars.extend(self._parse_bars(page))

            page_token = data.get("next_page_token")
            if not page_token or (limit and len(all_bars) >= limit):
                break

        return all_bars

    @classmethod
    def _parse_bars(cls, raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        candles = []
        for b in raw:
            candles.append({
                "time": cls._to_unix_seconds(b["t"]),
                "open": float(b["o"]),
                "high": float(b["h"]),
                "low": float(b["l"]),
                "close": float(b["c"]),
                "volume": float(b["v"]),
            })
        return candles

    def fetch_data(self, symbol: str, from_date: str, to_date: str, interval: str = "1") -> pd.DataFrame:
        """Compatible interface with DhanClient/YFinanceClient/BinanceClient.

        Returns DataFrame with columns: timestamp, open, high, low, close, volume.
        """
        symbol = self._strip_suffix(symbol)
        timeframe = self.tv_resolution_to_timeframe(interval)

        cached_df = self.cache.get(symbol, from_date, to_date, interval)
        if cached_df is not None:
            return cached_df

        print(f"[Alpaca] Fetching {symbol} | interval={interval} -> {timeframe} | {from_date} to {to_date}")

        try:
            candles = self.fetch_bars(
                symbol,
                timeframe,
                start=self._to_rfc3339(from_date),
                end=self._to_rfc3339(to_date),
            )
        except Exception as e:
            print(f"[Alpaca] fetch_data error for '{symbol}': {e}")
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        if not candles:
            print(f"[Alpaca] No data returned for {symbol}")
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = pd.DataFrame(candles).rename(columns={"time": "timestamp"})
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)

        print(f"[Alpaca] Returning {len(df)} bars, range: "
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
        """Compatible interface with BinanceClient.fetch_candles."""
        timeframe = self.tv_resolution_to_timeframe(resolution)
        start = datetime.fromtimestamp(from_timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        end = datetime.fromtimestamp(to_timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        return self.fetch_bars(symbol, timeframe, start=start, end=end)

    def get_current_price(self, symbol: str) -> float:
        """Latest trade price. Free-tier SIP quotes lag real time by 15 minutes."""
        symbol = self._strip_suffix(symbol)
        if self.classify_symbol(symbol) == "crypto":
            data = self._get(f"{self.DATA_BASE}/v1beta3/crypto/us/latest/trades", {"symbols": symbol})
            return float(data["trades"][symbol]["p"])
        data = self._get_with_feed_fallback(
            f"{self.DATA_BASE}/v2/stocks/{symbol.upper()}/trades/latest",
            {"feed": self.feed},
        )
        return float(data["trade"]["p"])

    # ─── Options ────────────────────────────────────────────────────

    def get_option_contracts(
        self,
        underlying: str,
        expiration_date: Optional[str] = None,
        contract_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List tradable option contracts for an underlying.

        Contracts live on the trading API, not the data API — the OCC symbols
        returned here are what fetch_bars needs for option price history.
        """
        params: Dict[str, Any] = {"underlying_symbols": underlying.upper(), "limit": limit}
        if expiration_date:
            params["expiration_date"] = expiration_date
        if contract_type:
            params["type"] = contract_type

        data = self._get(f"{self.trading_base}/v2/options/contracts", params)
        return data.get("option_contracts", [])

    # ─── Account ────────────────────────────────────────────────────

    def get_account(self) -> Dict:
        return self._get(f"{self.trading_base}/v2/account", {})

    # ─── TradingView Compatibility ──────────────────────────────────

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
                data = self._get(f"{self.trading_base}/v2/assets/{query_upper}", {})
                results.append({
                    "symbol": data["symbol"],
                    "full_name": data.get("name", data["symbol"]),
                    "exchange": data.get("exchange", ""),
                    "type": data.get("class", "us_equity"),
                    "description": data.get("name", data["symbol"]),
                })
            except Exception as e:
                print(f"[Alpaca] Search error for '{query}': {e}")

        return results[:limit]

    def get_info(self, symbol: str) -> Optional[dict]:
        """Symbol information for TradingView resolveSymbol."""
        symbol = self._strip_suffix(symbol)
        is_crypto = self.classify_symbol(symbol) == "crypto"

        info = self.POPULAR_SYMBOLS.get(symbol)
        if info is None:
            try:
                asset = self._get(f"{self.trading_base}/v2/assets/{symbol.upper()}", {})
                info = {"name": asset.get("name", symbol), "exchange": asset.get("exchange", "")}
            except Exception as e:
                print(f"[Alpaca] get_info error for '{symbol}': {e}")
                return None

        return {
            "symbol": symbol,
            "name": info["name"],
            "full_name": info["name"],
            "exchange": info.get("exchange", ""),
            "type": info.get("type", "equity"),
            "description": info["name"],
            "timezone": "Etc/UTC" if is_crypto else "America/New_York",
            "session": "24x7" if is_crypto else "0930-1600",
            "has_intraday": True,
            "intraday_multipliers": ["1", "4", "5", "15", "30", "60", "240"],
            "has_daily": True,
            "has_weekly_and_monthly": True,
            "supported_resolutions": ["1", "4", "5", "15", "30", "60", "240", "D", "W", "M"],
            "pricescale": 100,
            "minmov": 1,
        }


# Simple test
if __name__ == "__main__":
    client = AlpacaClient()

    print("\n=== Account ===")
    account = client.get_account()
    print(f"  status={account['status']} equity={account['equity']}")

    print("\n=== Stock Daily (AAPL) ===")
    print(client.fetch_data("AAPL", "2026-08-01", "2026-09-08", "D").tail(3))

    print("\n=== Stock 4m native (AAPL) ===")
    print(client.fetch_data("AAPL", "2026-09-08", "2026-09-09", "4").head(3))

    print("\n=== Crypto Daily (BTC/USD) ===")
    print(client.fetch_data("BTC/USD", "2026-09-01", "2026-09-08", "D").tail(3))

    print("\n=== Option Contracts (AAPL) ===")
    contracts = client.get_option_contracts("AAPL", contract_type="call", limit=3)
    for c in contracts:
        print(f"  {c['symbol']} strike={c['strike_price']} exp={c['expiration_date']}")

    if contracts:
        print(f"\n=== Option Bars ({contracts[0]['symbol']}) ===")
        print(client.fetch_data(contracts[0]["symbol"], "2026-09-08", "2026-09-09", "D"))
