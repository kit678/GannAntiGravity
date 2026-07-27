"""
Binance Futures Testnet Client for Gann Visualizer

This module provides data and order execution for Binance USD-M Futures (Testnet).
Matches the existing DhanClient/YFinanceClient interface patterns.

Public data endpoints (klines, exchange info) require no API key.
Private endpoints (orders, account) use HMAC-SHA256 authentication.

Testnet base URLs:
  REST:  https://testnet.binancefuture.com
  WS:    wss://fstream.binancefuture.com

Mainnet base URLs (set use_testnet=False):
  REST:  https://fapi.binance.com
  WS:    wss://fstream.binance.com
"""

import os
import time
import hmac
import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from typing import List, Dict, Optional, Any

import requests
import pandas as pd


class BinanceClient:
    """Binance USD-M Futures client with testnet support."""

    TESTNET_REST = "https://testnet.binancefuture.com"
    TESTNET_WS_PUBLIC = "wss://fstream.binancefuture.com"

    MAINNET_REST = "https://fapi.binance.com"
    MAINNET_WS_PUBLIC = "wss://fstream.binance.com"

    SUPPORTED_INTERVALS = [
        "1m", "3m", "5m", "15m", "30m",
        "1h", "2h", "4h", "6h", "8h", "12h",
        "1d", "3d", "1w", "1M"
    ]

    # Intervals that require aggregation from a lower timeframe (not natively available)
    AGGREGATED_INTERVALS = {"4": "1m"}  # 4m → fetch 1m then aggregate 4×

    @staticmethod
    def _load_env_credentials():
        api_key = os.environ.get("BINANCE_TESTNET_API_KEY", "")
        api_secret = os.environ.get("BINANCE_TESTNET_API_SECRET", "")

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
                    if key == "BINANCE_TESTNET_API_KEY" and not api_key:
                        api_key = value
                    elif key == "BINANCE_TESTNET_API_SECRET" and not api_secret:
                        api_secret = value

        return api_key, api_secret

    def __init__(self, api_key: str = "", api_secret: str = "", use_testnet: bool = True):
        self.use_testnet = use_testnet
        self.base_url = self.TESTNET_REST if use_testnet else self.MAINNET_REST

        env_key, env_secret = self._load_env_credentials()
        self.api_key = api_key or env_key
        self.api_secret = api_secret or env_secret

        self.session = requests.Session()
        self.session.headers.update({
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/json",
        })

    def _sign_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params = params.copy()
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 5000
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def _signed_get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict:
        params = self._sign_params(params or {})
        url = f"{self.base_url}{endpoint}"
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "code" in data and data["code"] < 0:
            raise RuntimeError(f"Binance API error {data['code']}: {data.get('msg', '')}")
        return data

    def _signed_post(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict:
        params = self._sign_params(params or {})
        url = f"{self.base_url}{endpoint}"
        resp = self.session.post(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "code" in data and data["code"] < 0:
            raise RuntimeError(f"Binance API error {data['code']}: {data.get('msg', '')}")
        return data

    def _signed_delete(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict:
        params = self._sign_params(params or {})
        url = f"{self.base_url}{endpoint}"
        resp = self.session.delete(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "code" in data and data["code"] < 0:
            raise RuntimeError(f"Binance API error {data['code']}: {data.get('msg', '')}")
        return data

    # ─── Public Data ────────────────────────────────────────────────

    def get_exchange_info(self) -> Dict:
        url = f"{self.base_url}/fapi/v1/exchangeInfo"
        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()

    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        info = self.get_exchange_info()
        for s in info.get("symbols", []):
            if s["symbol"] == symbol.upper():
                return s
        return None

    def fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_time_ms: Optional[int] = None,
        end_time_ms: Optional[int] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """
        Fetch OHLC kline data from Binance Futures.

        Returns list of candle dicts compatible with existing state machine format:
        {time, open, high, low, close, volume}
        """
        interval = interval.lower()
        if interval not in self.SUPPORTED_INTERVALS:
            raise ValueError(f"Unsupported interval '{interval}'. Supported: {self.SUPPORTED_INTERVALS}")

        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": min(limit, 1000),
        }
        if start_time_ms:
            params["startTime"] = start_time_ms
        if end_time_ms:
            params["endTime"] = end_time_ms

        url = f"{self.base_url}/fapi/v1/klines"
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        raw = resp.json()

        return self._parse_klines(raw)

    def fetch_klines_range(
        self,
        symbol: str,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all klines between start_time_ms and end_time_ms,
        automatically paginating if the range exceeds 1000 bars.
        """
        all_candles = []
        current_start = start_time_ms

        while current_start < end_time_ms:
            batch = self.fetch_klines(
                symbol, interval,
                start_time_ms=current_start,
                end_time_ms=end_time_ms,
                limit=1000,
            )
            if not batch:
                break
            all_candles.extend(batch)
            current_start = batch[-1]["time"] + 1

        return all_candles

    def _parse_klines(self, raw: List) -> List[Dict[str, Any]]:
        candles = []
        for k in raw:
            if not k or len(k) < 6:
                continue
            candles.append({
                "time": int(k[0]),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            })
        return candles

    def get_current_price(self, symbol: str) -> float:
        url = f"{self.base_url}/fapi/v1/ticker/price"
        resp = self.session.get(url, params={"symbol": symbol.upper()})
        resp.raise_for_status()
        return float(resp.json()["price"])

    # ─── Account ────────────────────────────────────────────────────

    def get_account(self) -> Dict:
        return self._signed_get("/fapi/v2/account")

    def get_balance(self) -> List[Dict]:
        account = self.get_account()
        balances = []
        for asset in account.get("assets", []):
            balances.append({
                "asset": asset["asset"],
                "wallet_balance": float(asset["walletBalance"]),
                "available_balance": float(asset["availableBalance"]),
                "unrealized_pnl": float(asset.get("unrealizedProfit", 0)),
            })
        return balances

    def get_positions(self, symbol: Optional[str] = None) -> List[Dict]:
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        return self._signed_get("/fapi/v2/positionRisk", params)

    # ─── Orders ────────────────────────────────────────────────────

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        reduce_only: bool = False,
    ) -> Dict:
        params = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": "MARKET",
            "quantity": str(quantity),
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        return self._signed_post("/fapi/v1/order", params)

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        reduce_only: bool = False,
        time_in_force: str = "GTC",
    ) -> Dict:
        params = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": "LIMIT",
            "quantity": str(quantity),
            "price": str(price),
            "timeInForce": time_in_force,
        }
        if reduce_only:
            params["reduceOnly"] = "true"
        return self._signed_post("/fapi/v1/order", params)

    def cancel_order(self, symbol: str, order_id: int) -> Dict:
        return self._signed_delete("/fapi/v1/order", {
            "symbol": symbol.upper(),
            "orderId": order_id,
        })

    def cancel_all_orders(self, symbol: str) -> Dict:
        return self._signed_delete("/fapi/v1/allOpenOrders", {
            "symbol": symbol.upper(),
        })

    def get_order(self, symbol: str, order_id: int) -> Dict:
        return self._signed_get("/fapi/v1/order", {
            "symbol": symbol.upper(),
            "orderId": order_id,
        })

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        return self._signed_get("/fapi/v1/openOrders", params)

    # ─── Symbol Resolution (TradingView-compatible) ─────────────────

    RESOLUTION_MAP = {
        "1": "1m", "3": "3m", "4": "1m", "5": "5m", "15": "15m", "30": "30m",
        "60": "1h", "1H": "1h", "120": "2h", "240": "4h", "360": "6h",
        "480": "8h", "720": "12h",
        "D": "1d", "1D": "1d", "3D": "3d",
        "W": "1w", "1W": "1w",
        "M": "1M",
    }

    @classmethod
    def tv_resolution_to_interval(cls, resolution: str) -> str:
        interval = cls.RESOLUTION_MAP.get(resolution, "1h")
        return interval

    def fetch_data(self, symbol: str, from_date_str: str, to_date_str: str, interval: str = "1h") -> "pd.DataFrame":
        """Compatible interface with DhanClient/YFinanceClient.
        Returns DataFrame with columns: timestamp, open, high, low, close, volume.
        Supports 4m via 1m fetch + 4× aggregation.
        """
        original_interval = interval  # Preserve before resolution mapping (e.g. "4" → "1m")
        resolution = interval if interval else "1h"
        if resolution.isdigit():
            resolution = self.tv_resolution_to_interval(resolution)

        from_dt = datetime.fromisoformat(from_date_str.replace("Z", "")).replace(tzinfo=timezone.utc)
        to_dt = datetime.fromisoformat(to_date_str.replace("Z", "")).replace(tzinfo=timezone.utc)
        from_ms = int(from_dt.timestamp() * 1000)
        to_ms = int(to_dt.timestamp() * 1000)

        candles = self.fetch_klines_range(symbol, resolution, from_ms, to_ms)
        if not candles:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = pd.DataFrame(candles)
        for c in candles:
            c["time"] = c["time"] // 1000
        df["timestamp"] = df["time"].apply(lambda t: t // 1000 if t > 10000000000 else t)
        df = df.rename(columns={"time": "_raw_time"})
        result = df[["timestamp", "open", "high", "low", "close", "volume"]]

        # --- 4m AGGREGATION ---
        if original_interval == "4":
            from timeframe_utils import aggregate_1m_to_4m
            print(f"[Binance] Aggregating {len(result)} 1m bars into 4m candles...")
            result = aggregate_1m_to_4m(result)
            print(f"[Binance] Aggregated to {len(result)} 4m candles")

        return result

    def fetch_candles(
        self,
        symbol: str,
        resolution: str,
        from_timestamp: int,
        to_timestamp: int,
    ) -> List[Dict[str, Any]]:
        original_resolution = resolution  # Preserve before mapping (e.g. "4" → "1m")
        interval = self.tv_resolution_to_interval(resolution)
        all_candles = self.fetch_klines_range(
            symbol, interval,
            start_time_ms=from_timestamp * 1000,
            end_time_ms=to_timestamp * 1000,
        )
        for c in all_candles:
            c["time"] = c["time"] // 1000

        # --- 4m AGGREGATION ---
        if original_resolution == "4":
            import pandas as pd
            from timeframe_utils import aggregate_1m_to_4m
            df = pd.DataFrame(all_candles)
            if not df.empty:
                # Normalize timestamp field
                if "timestamp" not in df.columns and "time" in df.columns:
                    df["timestamp"] = df["time"]
                df["timestamp"] = df["timestamp"].apply(
                    lambda t: t // 1000 if t > 10000000000 else t
                )
                df = aggregate_1m_to_4m(df)
                # Convert back to list of dicts in the expected format
                all_candles = df.to_dict(orient="records")
                for c in all_candles:
                    c["time"] = c["timestamp"]  # Restore 'time' field for callers
            print(f"[Binance] fetch_candles: aggregated to {len(all_candles)} 4m candles")

        return all_candles
