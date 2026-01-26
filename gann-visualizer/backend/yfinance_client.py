"""
Yahoo Finance Data Client for Gann Visualizer

This module provides market data from Yahoo Finance as a free alternative
to the Dhan API for development and backtesting purposes.

Supported intervals: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo
Intraday data limitations:
  - 1m: last 7 days only
  - 2m-60m: last 60 days only
  - Daily+: extensive history available
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import pytz
from cache_manager import get_cache


class YFinanceClient:
    """Yahoo Finance data client matching DhanClient interface."""
    
    # Popular symbols for search suggestions
    POPULAR_SYMBOLS = {
        # Indian Indices
        "^NSEI": {"name": "NIFTY 50", "exchange": "NSE", "type": "index"},
        "^NSEBANK": {"name": "NIFTY Bank", "exchange": "NSE", "type": "index"},
        # Indian Stocks
        "RELIANCE.NS": {"name": "Reliance Industries", "exchange": "NSE", "type": "equity"},
        "TCS.NS": {"name": "Tata Consultancy Services", "exchange": "NSE", "type": "equity"},
        "HDFCBANK.NS": {"name": "HDFC Bank", "exchange": "NSE", "type": "equity"},
        "INFY.NS": {"name": "Infosys", "exchange": "NSE", "type": "equity"},
        "ICICIBANK.NS": {"name": "ICICI Bank", "exchange": "NSE", "type": "equity"},
        "SBIN.NS": {"name": "State Bank of India", "exchange": "NSE", "type": "equity"},
        "BHARTIARTL.NS": {"name": "Bharti Airtel", "exchange": "NSE", "type": "equity"},
        "ITC.NS": {"name": "ITC Limited", "exchange": "NSE", "type": "equity"},
        "KOTAKBANK.NS": {"name": "Kotak Mahindra Bank", "exchange": "NSE", "type": "equity"},
        "LT.NS": {"name": "Larsen & Toubro", "exchange": "NSE", "type": "equity"},
        "AXISBANK.NS": {"name": "Axis Bank", "exchange": "NSE", "type": "equity"},
        "WIPRO.NS": {"name": "Wipro", "exchange": "NSE", "type": "equity"},
        "TATASTEEL.NS": {"name": "Tata Steel", "exchange": "NSE", "type": "equity"},
        "MARUTI.NS": {"name": "Maruti Suzuki", "exchange": "NSE", "type": "equity"},
        # US Indices
        "^GSPC": {"name": "S&P 500", "exchange": "NYSE", "type": "index"},
        "^DJI": {"name": "Dow Jones", "exchange": "NYSE", "type": "index"},
        "^IXIC": {"name": "NASDAQ Composite", "exchange": "NASDAQ", "type": "index"},
        # US Stocks
        "AAPL": {"name": "Apple Inc", "exchange": "NASDAQ", "type": "equity"},
        "MSFT": {"name": "Microsoft", "exchange": "NASDAQ", "type": "equity"},
        "GOOGL": {"name": "Alphabet (Google)", "exchange": "NASDAQ", "type": "equity"},
        "AMZN": {"name": "Amazon", "exchange": "NASDAQ", "type": "equity"},
        "TSLA": {"name": "Tesla", "exchange": "NASDAQ", "type": "equity"},
        "META": {"name": "Meta Platforms", "exchange": "NASDAQ", "type": "equity"},
        "NVDA": {"name": "NVIDIA", "exchange": "NASDAQ", "type": "equity"},
    }
    
    # Map TradingView-style resolutions to yfinance intervals
    INTERVAL_MAP = {
        "1": "1m",
        "2": "2m",
        "5": "5m",
        "15": "15m",
        "30": "30m",
        "60": "1h",
        "1H": "1h",
        "D": "1d",
        "1D": "1d",
        "W": "1wk",
        "1W": "1wk",
        "M": "1mo",
        "1M": "1mo",
    }
    
    # Maximum historical period for each interval
    INTERVAL_LIMITS = {
        "1m": 7,      # 7 days
        "2m": 60,     # 60 days
        "5m": 60,
        "15m": 60,
        "30m": 60,
        "60m": 730,   # ~2 years (Yahoo allows more for hourly)
        "1h": 730,
        "1d": 10000,  # Effectively unlimited
        "1wk": 10000,
        "1mo": 10000,
    }
    
    def __init__(self):
        """Initialize Yahoo Finance client."""
        print("[YFinance] Client initialized")
        self.cache = get_cache()
    
    def search(self, query: str, limit: int = 20) -> list:
        """
        Search for symbols matching query.
        Returns list of symbol info dicts.
        """
        query_upper = query.upper()
        results = []
        
        # First, search in our predefined popular symbols
        for symbol, info in self.POPULAR_SYMBOLS.items():
            if query_upper in symbol.upper() or query_upper in info["name"].upper():
                results.append({
                    "symbol": symbol,
                    "full_name": info["name"],
                    "exchange": info["exchange"],
                    "type": info["type"],
                    "description": f"{info['name']} ({info['exchange']})"
                })
                if len(results) >= limit:
                    break
        
        # If no results from predefined, try yfinance lookup
        if not results:
            try:
                # Try the symbol directly
                ticker = yf.Ticker(query_upper)
                info = ticker.info
                if info and info.get("symbol"):
                    results.append({
                        "symbol": info.get("symbol", query_upper),
                        "full_name": info.get("shortName", info.get("longName", query_upper)),
                        "exchange": info.get("exchange", ""),
                        "type": info.get("quoteType", "equity").lower(),
                        "description": info.get("shortName", query_upper)
                    })
            except Exception as e:
                print(f"[YFinance] Search error for '{query}': {e}")
        
        return results[:limit]
    
    def get_info(self, symbol: str) -> dict:
        """
        Get symbol information for TradingView resolveSymbol.
        """
        # Check predefined symbols first
        if symbol in self.POPULAR_SYMBOLS:
            info = self.POPULAR_SYMBOLS[symbol]
            return {
                "symbol": symbol,
                "name": info["name"],
                "full_name": info["name"],
                "exchange": info["exchange"],
                "type": info["type"],
                "description": info["name"],
                "timezone": "Asia/Kolkata" if ".NS" in symbol or symbol.startswith("^NSE") else "America/New_York",
                "session": "0915-1530" if ".NS" in symbol or symbol.startswith("^NSE") else "0930-1600",
                "has_intraday": True,
                "has_daily": True,
                "has_weekly_and_monthly": True,
                "supported_resolutions": ["1", "5", "15", "30", "60", "D", "W", "M"],
                "pricescale": 100,
                "minmov": 1,
            }
        
        # Fetch from Yahoo Finance
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            if not info or not info.get("symbol"):
                return None
            
            # Determine timezone based on exchange
            exchange = info.get("exchange", "")
            is_indian = ".NS" in symbol or ".BO" in symbol or "NSE" in exchange or "BSE" in exchange
            
            return {
                "symbol": symbol,
                "name": info.get("shortName", symbol),
                "full_name": info.get("longName", info.get("shortName", symbol)),
                "exchange": exchange,
                "type": info.get("quoteType", "EQUITY").lower(),
                "description": info.get("shortName", symbol),
                "timezone": "Asia/Kolkata" if is_indian else "America/New_York",
                "session": "0915-1530" if is_indian else "0930-1600",
                "has_intraday": True,
                "has_daily": True,
                "has_weekly_and_monthly": True,
                "supported_resolutions": ["1", "5", "15", "30", "60", "D", "W", "M"],
                "pricescale": 100,
                "minmov": 1,
            }
        except Exception as e:
            print(f"[YFinance] get_info error for '{symbol}': {e}")
            return None
    
    def fetch_data(self, symbol: str, from_date: str, to_date: str, interval: str = "1") -> pd.DataFrame:
        """
        Fetch OHLCV data from Yahoo Finance.
        
        Args:
            symbol: Yahoo Finance symbol (e.g., "RELIANCE.NS", "^NSEI", "AAPL")
            from_date: Start date "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS"
            to_date: End date "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS"
            interval: TradingView-style interval ("1", "5", "15", "60", "D", etc.)
        
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        # Map interval
        yf_interval = self.INTERVAL_MAP.get(interval, "1d")
        
        # CHECK CACHE
        cached_df = self.cache.get(symbol, from_date, to_date, interval)
        if cached_df is not None:
            return cached_df
            
        print(f"[YFinance] Fetching {symbol} | interval={interval} -> {yf_interval} | {from_date} to {to_date}")
        
        # Parse dates
        try:
            if " " in from_date:
                start_dt = datetime.strptime(from_date, "%Y-%m-%d %H:%M:%S")
            else:
                start_dt = datetime.strptime(from_date, "%Y-%m-%d")
            
            if " " in to_date:
                end_dt = datetime.strptime(to_date, "%Y-%m-%d %H:%M:%S")
            else:
                end_dt = datetime.strptime(to_date, "%Y-%m-%d")
                # Add end of day for inclusive end date
                end_dt = end_dt + timedelta(hours=23, minutes=59, seconds=59)
        except ValueError as e:
            print(f"[YFinance] Date parse error: {e}")
            return pd.DataFrame()
        
        # Check interval limits and adjust start date if needed
        max_days = self.INTERVAL_LIMITS.get(yf_interval, 60)
        requested_days = (end_dt - start_dt).days
        
        if requested_days > max_days:
            print(f"[YFinance] WARNING: Requested {requested_days} days but {yf_interval} limit is {max_days} days")
            start_dt = end_dt - timedelta(days=max_days)
            print(f"[YFinance] Adjusted start date to {start_dt.strftime('%Y-%m-%d')}")
        
        # NEW: Check if start date is too old for the interval (Yahoo Limitation)
        # 1m: 7 days from NOW
        # 2m-30m: 60 days from NOW
        # 60m-90m: 730 days from NOW
        now = datetime.now()
        age_days = (now - start_dt).days
        
        limit_from_now = 36500 # Default huge
        if interval == "1": limit_from_now = 7
        elif interval in ["2", "5", "15", "30"]: limit_from_now = 60
        elif interval in ["60", "90", "1H"]: limit_from_now = 730
        
        if age_days > limit_from_now:
            # Instead of erroring or risking an empty return from YF, we clamp the start date
            # to the maximum allowed history limit.
            # FIX: Only go back 'limit_from_now' days from NOW.
            
            earliest_allowed_date = now - timedelta(days=limit_from_now - 1)
            
            # If our requested start date is older than the earliest allowed date,
            # we must move our start date forward to the earliest allowed date.
            if start_dt < earliest_allowed_date:
                print(f"[YFinance] Requested data ({interval}m) starts {age_days} days ago (Limit: {limit_from_now}d).")
                print(f"[YFinance] Auto-adjusting start date from {start_dt.strftime('%Y-%m-%d')} to {earliest_allowed_date.strftime('%Y-%m-%d')}")
                start_dt = earliest_allowed_date


        
        try:
            # Fetch data using yfinance
            ticker = yf.Ticker(symbol)
            
            # Use YYYY-MM-DD strings for better compatibility
            # Fetch whole days and we'll filter by timestamp later
            start_str = start_dt.strftime("%Y-%m-%d")
            # For end date, add 1 day to ensure we cover the target end date (history is exclusive of end)
            end_str = (end_dt + timedelta(days=1)).strftime("%Y-%m-%d")

            print(f"[YFinance] Requesting dates: start={start_str}, end={end_str} for {symbol}")

            df = ticker.history(
                start=start_str,
                end=end_str,
                interval=yf_interval,
                auto_adjust=True,
                prepost=False
            )
            
            if df.empty:
                print(f"[YFinance] No data returned for {symbol}")
                return pd.DataFrame()
            
            print(f"[YFinance] Received {len(df)} bars")
            
            # Process and standardize the DataFrame
            df = df.reset_index()
            
            # Handle timezone-aware datetime index
            time_col = 'Datetime' if 'Datetime' in df.columns else 'Date'
            
            if time_col in df.columns:
                # Convert to Unix timestamp (seconds)
                if df[time_col].dt.tz is not None:
                    # Already timezone-aware, convert to UTC then to timestamp
                    df['timestamp'] = df[time_col].apply(lambda x: int(x.timestamp()))
                else:
                    # Naive datetime - assume market timezone
                    is_indian = ".NS" in symbol or ".BO" in symbol or symbol.startswith("^NSE")
                    tz = pytz.timezone("Asia/Kolkata" if is_indian else "America/New_York")
                    df['timestamp'] = df[time_col].apply(
                        lambda x: int(tz.localize(x).timestamp())
                    )
            else:
                print(f"[YFinance] Could not find time column. Available: {df.columns.tolist()}")
                return pd.DataFrame()
            
            # Standardize column names (lowercase)
            df.columns = [c.lower() for c in df.columns]
            
            # Ensure required columns exist
            required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            for col in required_cols:
                if col not in df.columns:
                    print(f"[YFinance] Missing required column: {col}")
                    return pd.DataFrame()
            
            # Select and return only required columns
            result_df = df[required_cols].copy()
            result_df = result_df.sort_values('timestamp')
            result_df = result_df.drop_duplicates(subset=['timestamp'])
            
            print(f"[YFinance] Returning {len(result_df)} bars, range: "
                  f"{datetime.fromtimestamp(result_df['timestamp'].iloc[0])} to "
                  f"{datetime.fromtimestamp(result_df['timestamp'].iloc[-1])}")
            
            # STORE IN CACHE (TTL: 5 minutes)
            self.cache.put(symbol, from_date, to_date, interval, result_df, ttl=300.0)
            
            return result_df
            
        except Exception as e:
            print(f"[YFinance] fetch_data error: {e}")
            import traceback
            traceback.print_exc()
            return pd.DataFrame()


# Simple test
if __name__ == "__main__":
    client = YFinanceClient()
    
    # Test search
    print("\n=== Search Test ===")
    results = client.search("RELIANCE")
    for r in results:
        print(f"  {r['symbol']}: {r['description']}")
    
    # Test data fetch
    print("\n=== Data Fetch Test (NIFTY 50 Daily) ===")
    df = client.fetch_data("^NSEI", "2025-01-01", "2025-01-20", "D")
    if not df.empty:
        print(df.head())
    
    # Test intraday
    print("\n=== Data Fetch Test (RELIANCE.NS 5min) ===")
    df = client.fetch_data("RELIANCE.NS", "2025-01-15", "2025-01-20", "5")
    if not df.empty:
        print(df.head())
