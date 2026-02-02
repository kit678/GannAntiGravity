from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
import pandas as pd
from dhan_client import DhanClient
from yfinance_client import YFinanceClient
from gann_logic import GannStrategyEngine  # Keep for backward compatibility
from strategies import get_strategy, STRATEGY_REGISTRY  # New strategy system
from backtest_engine import BacktestEngine  # New backtesting engine
import time
from datetime import datetime, timedelta
import pytz
import logging
import sys
import os

# --- LOGGING CONFIGURATION ---
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = f"backend_session_{timestamp}.log"

# Create root logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Formatter
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# File Handler (overwrite each restart)
file_handler = logging.FileHandler(LOG_FILE, mode='w')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Stream Handler (maintain console output)
# We use the original stdout to avoid recursion when redirecting sys.stdout
console_handler = logging.StreamHandler(sys.__stdout__)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Redirect print statements to logger
class StreamToLogger(object):
    def __init__(self, logger, level=logging.INFO):
        self.logger = logger
        self.level = level
        self.linebuf = ''

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.level, line.rstrip())

    def flush(self):
        pass

    def isatty(self):
        return False

# Redirect stdout and stderr
sys.stdout = StreamToLogger(logger, logging.INFO)
sys.stderr = StreamToLogger(logger, logging.ERROR)

print(f"Logging initialized. Output writing to {os.path.abspath(LOG_FILE)}")
# -----------------------------

app = FastAPI()
print("--- BACKEND RESTART v4 - PNL TRACKING ---")

# Position tracking for progressive replay PnL calculation
# Key: strategy name, Value: { position_type, entry_price, entry_time, entry_label, option_price }
# Position tracking for progressive replay PnL calculation
# Key: strategy name, Value: { position_type, entry_price, entry_time, entry_label, option_price }
_replay_positions = {}
_study_cache = {'index': -1, 'strategy': None, 'state': None}

# Enable CORS for React Frontend
# Manual CORS Middleware to guarantee headers
from fastapi import Request

@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    # Process request
    if request.method == "OPTIONS":
        # Preflight response
        response = Response(status_code=204)
    else:
        response = await call_next(request)
    
    # Add CORS Headers
    origin = request.headers.get("origin")
    print(f"DEBUG CORS: Origin header received: '{origin}'")
    if origin:
        # Echo back the origin (allow all specific origins)
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
        response.headers["Access-Control-Allow-Headers"] = "*"
    else:
        # Fallback for non-browser calls
        response.headers["Access-Control-Allow-Origin"] = "*"
        
    return response

# app.add_middleware(CORSMiddleware...) - Disabled

print(f"Middleware Stack: {app.user_middleware}")

class BacktestRequest(BaseModel):
    strategy: str
    symbol: str = "NIFTY OPTIONS" # Default
    from_date: str = None # YYYY-MM-DD
    to_date: str = None   # YYYY-MM-DD
    days: int = 5
    resolution: str = "1" # Default to 1-minute
    data_source: str = "dhan"  # "dhan" or "yfinance"

class FetchCandlesRequest(BaseModel):
    symbol: str
    from_date: str
    to_date: str  
    resolution: str = "1"
    strategy: Optional[str] = None  # Optional: if provided, prefetch option data for option strategies
    data_source: str = "dhan"  # "dhan" or "yfinance"
    lookback_bars: int = 50  # Number of bars to fetch before from_date for pivot context


def get_data_client(data_source: str = "dhan"):
    """Factory function to get appropriate data client."""
    if data_source == "yfinance":
        return YFinanceClient()
    return DhanClient()

class EvaluateStrategyRequest(BaseModel):
    strategy: str
    candles: list
    current_index: int
    last_action: str | None = None  # 'buy', 'sell', or None
    instrument_type: str = "options"  # 'options' or 'spot'
    scale_ratio: float | None = None  # Chart's Price-to-Bar ratio for angle calculations
    left_bars: int | None = None  # Configurable pivot detection
    right_bars: int | None = None  # Configurable pivot detection

@app.get("/")
def read_root():
    return {"status": "Gann Backend Online"}

# --- UDF (Universal Data Feed) Endpoints for TradingView Advanced Charts ---

@app.get("/config")
def udf_config():
    return {
        "supported_resolutions": ["1", "5", "15", "30", "60", "D", "W", "M"],
        "supports_group_request": False,
        "supports_marks": True,
        "supports_search": True,
        "supports_timescale_marks": True,
        "exchanges": [
            {"value": "NSE", "name": "NSE", "desc": "National Stock Exchange"},
        ],
        "symbols_types": [
            {"name": "All types", "value": ""},
            {"name": "Index", "value": "index"},
            {"name": "Stock", "value": "stock"},
            {"name": "Options", "value": "options"},
        ],
    }

@app.get("/search")
def udf_search(query: str, type: str, exchange: str, limit: int, data_source: str = "dhan"):
    results = []
    
    # Route to Yahoo Finance search if selected
    if data_source == "yfinance":
        yf_client = YFinanceClient()
        yf_results = yf_client.search(query, limit=limit)
        for r in yf_results:
            results.append({
                "symbol": f"{r['symbol']}:YF", # Add suffix for easier routing
                "full_name": r["full_name"],
                "description": r["description"],
                "exchange": r["exchange"],
                "ticker": f"{r['symbol']}:YF",
                "type": r["type"]
            })
        return results
    
    # --- DHAN SEARCH ---
    # Always include our Hardcoded favorites first
    # NIFTY 50 Index
    if "NIFTY" in query.upper() or query == "":
        results.append({
            "symbol": "NIFTY 50",
            "full_name": "NIFTY 50 INDEX",
            "description": "Nifty 50 Index (Spot)",
            "exchange": "NSE",
            "ticker": "NIFTY 50",
            "type": "index"
        })
        
    # NIFTY Options
    if "OPT" in query.upper() or "NIFTY" in query.upper() or query == "":
        results.append({
            "symbol": "NIFTY OPTIONS",
            "full_name": "NIFTY OPTIONS ATM",
            "description": "Nifty Options ATM Premium",
            "exchange": "NSE",
            "ticker": "NIFTY OPTIONS",
            "type": "options"
        })
    
    # Dynamic Search from Scrip Master
    try:
        client = DhanClient() # This initializes ScripMaster
        matches = client.scrip_master.search(query)
        if not matches.empty:
            for _, row in matches.iterrows():
                sym = row['SEARCH_SYMBOL']
                instr_name = row['SEM_INSTRUMENT_NAME']
                
                # Filter by Type (if specified)
                row_type = "stock" if instr_name == 'EQUITY' else "index"
                if type and type != "" and type != "all":
                    if type == "stock" and row_type != "stock": continue
                    if type == "index" and row_type != "index": continue
                    # For now we treat others as unmatched or catch-all
                
                if sym in ["NIFTY 50", "NIFTY OPTIONS"]: continue # Skip dupes
                
                results.append({
                    "symbol": sym, # displayed symbol
                    "full_name": sym, 
                    "description": row.get('SEM_CUSTOM_SYMBOL', sym),
                    "exchange": row['SEM_EXM_EXCH_ID'],
                    "ticker": sym, # value sent to history
                    "type": row_type
                })
    except Exception as e:
        print(f"Search Error: {e}")
        
    return results

@app.get("/symbols")
def udf_symbols(symbol: str):
    # Check for YFinance Suffix
    is_yfinance = symbol.endswith(":YF")
    clean_symbol = symbol.replace(":YF", "")
    
    if is_yfinance:
        client = YFinanceClient()
        info = client.get_info(clean_symbol)
        if info:
            # Ensure the returned symbol/ticker has the suffix so future calls maintain context
            info['symbol'] = symbol 
            info['ticker'] = symbol
            return info
            
    # Return info based on requested symbol (Default Dhan)
    return {
        "name": symbol,
        "exchange-traded": "NSE",
        "exchange-listed": "NSE",
        "timezone": "Asia/Kolkata",
        "minmov": 1,
        "minmov2": 0,
        "pointvalue": 1,
        "session": "0915-1530",
        "has_intraday": True,
        "intraday_multipliers": ["1", "5", "15", "60"],
        "has_daily": True,
        "has_weekly_and_monthly": False, 
        "description": symbol,
        "type": "index" if "INDEX" in symbol or "NIFTY" in symbol else "stock",
        "supported_resolutions": ["1", "5", "15", "60", "D"],
        "pricescale": 100, 
        "ticker": symbol,
    }

@app.get("/history")
def udf_history(symbol: str, resolution: str, from_: int = Query(..., alias="from"), to: int = Query(...), data_source: str = "dhan"):
    print(f"\n{'='*60}")
    print(f"[UDF_HISTORY] === NEW REQUEST ===")
    print(f"[UDF_HISTORY] symbol={symbol}, resolution={resolution}")
    print(f"[UDF_HISTORY] from_={from_}, to={to}, data_source={data_source}")
    print(f"{'='*60}")
    
    # Detect Source via Suffix first (explicit :YF marker)
    is_yfinance = symbol.endswith(":YF")
    clean_symbol = symbol.replace(":YF", "")
    
    # Auto-detect Yahoo Finance symbols by pattern if not explicitly marked
    # This handles cases where TradingView strips the :YF suffix
    if not is_yfinance:
        # Check for Yahoo Finance symbol patterns:
        # - Indices start with ^ (^NSEI, ^GSPC, ^DJI, etc.)
        # - Indian NSE stocks end with .NS
        # - Indian BSE stocks end with .BO
        # - Common US stocks (no suffix, but not Dhan format)
        if (clean_symbol.startswith("^") or 
            clean_symbol.endswith(".NS") or 
            clean_symbol.endswith(".BO")):
            is_yfinance = True
            print(f"[udf_history] Auto-detected Yahoo Finance symbol: {clean_symbol}")
    
    if is_yfinance:
        client = get_data_client("yfinance")
        symbol = clean_symbol  # Use clean symbol for fetching
        data_source = "yfinance"  # Update log var
    else:
        client = get_data_client(data_source)

    df = pd.DataFrame()
    
    # Convert timestamps to Date Strings
    try:
        # Handle potential invalid timestamps (negative or too large)
        from_dt_safe = datetime.fromtimestamp(max(0, from_))
        to_dt_safe = datetime.fromtimestamp(max(0, to))
    except (ValueError, OSError):
        from_dt_safe = datetime.fromtimestamp(0)
        to_dt_safe = datetime.fromtimestamp(0)

    from_date_str = from_dt_safe.strftime('%Y-%m-%d %H:%M:%S')
    to_date_str = to_dt_safe.strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"\n{'='*60}")
    print(f"[UDF_HISTORY] INCOMING REQUEST")
    print(f"  Symbol: {symbol}")
    print(f"  Data Source: {data_source}")
    print(f"  Resolution: {resolution}")
    print(f"  From (Unix): {from_} -> {from_date_str}")
    print(f"  To (Unix): {to} -> {to_date_str}")
    print(f"{'='*60}")
    if data_source == "dhan":
        print(f"DEBUG: Backend using Token: {client.access_token[:10]}...")
    
    # Limit the date range to prevent fetching excessive data in a SINGLE request
    # However, to support dynamic scrolling (pagination), we must allow larger chunks
    # TradingView will handle the "initial" zoom, but we shouldn't artificially cut off history if requested
    MAX_BARS_PER_REQUEST = 2000 
    
    to_dt = to_dt_safe
    from_dt = from_dt_safe
    
    # Calculate appropriate lookback based on resolution
    # We want to return enough data to fill the screen + buffer, but not entire history in one go if unnecessary
    if resolution == "1D" or resolution == "D":
        # For daily: 2000 days = ~6-7 years (lots of history)
        max_lookback_days = 3000
    elif resolution == "60":
        # For 60-min: Increase to 1000 days (~4 years) to support deep history
        max_lookback_days = 2000
    elif resolution == "15":
        # For 15-min: Increase to 500 days
        max_lookback_days = 500
    elif resolution == "5":
        # For 5-min: Increase to 100 days
        max_lookback_days = 100
    else:  # resolution == "1" (1-minute)
        # For 1-min: Keep 30 days as most APIs limit 1m data (except YFinance public limit is 7 days)
        max_lookback_days = 45
    
    # Limit the from_date ONLY if the requested range is excessively large
    # This prevents backend timeouts, but allows pagination
    calculated_from_dt = to_dt - timedelta(days=max_lookback_days)
    
    # USER REQUEST: Remove artificial limitation to allow "organic" lazy loading
    # if from_dt < calculated_from_dt:
    #     from_dt = calculated_from_dt
    #     from_date_str = from_dt.strftime('%Y-%m-%d')
    #     print(f"Range limited to {max_lookback_days} days for resolution {resolution}: {from_date_str} to {to_date_str}")
    
    # Use Generic Fetcher which handles NIFTY/OPTIONS/Generic
    # Pass resolution to fetch_data for proper interval handling
    print(f"[UDF_HISTORY] Calling client.fetch_data({symbol}, {from_date_str}, {to_date_str}, interval={resolution})")
    df = client.fetch_data(symbol, from_date_str, to_date_str, interval=resolution)
    print(f"[UDF_HISTORY] fetch_data returned: type={type(df)}, empty={df.empty if hasattr(df, 'empty') else 'N/A'}")
    if df is not None and not df.empty:
        print(f"[UDF_HISTORY] Raw data shape: {df.shape}, columns: {df.columns.tolist()}")
        print(f"[UDF_HISTORY] Raw timestamp range: {df['timestamp'].min()} - {df['timestamp'].max()}")
        print(f"[UDF_HISTORY] Raw date range: {datetime.fromtimestamp(df['timestamp'].min())} - {datetime.fromtimestamp(df['timestamp'].max())}")
    
    # --- SMART FIX (Year Mismatch / Future Data) ---
    # Case 1: YFinance auto-adjusted to 2026 (returned future data) but we requested 2025
    if not df.empty and 'timestamp' in df.columns:
        min_ts = df['timestamp'].min()
        if min_ts > to: 
             print(f"[SmartFix] Data start ({min_ts}) is > requested end ({to}). Checking for year offset...")
             # Check if we are approx 1 year off (2025 request, 2026 data)
             if from_dt.year == 2025 and datetime.fromtimestamp(int(min_ts)).year == 2026:
                  print("[SmartFix] ACCEPTING 2026 data for 2025 request (TV 1-year Bug). Extending 'to' filter.")
                  # Extend 'to' to include the new data
                  to = max(to, int(df['timestamp'].max()) + 1)
                  # Also update 'from_' to reflect we are showing this data
                  from_ = min(from_, int(min_ts))

    # Case 2: Fetch returned nothing for 2025 (no auto-adjust). Try 2026 explicit fetch.
    elif (df is None or df.empty) and from_dt.year == 2025:
        current_year = datetime.now().year
        if current_year == 2026:
            print(f"[SmartFix] Detected empty 2025 request. Attempting to shift dates to 2026...")
            
            # Shift +365 days
            from_dt_26 = from_dt + timedelta(days=365)
            to_dt_26 = to_dt + timedelta(days=365)
            
            from_str_26 = from_dt_26.strftime('%Y-%m-%d %H:%M:%S')
            to_str_26 = to_dt_26.strftime('%Y-%m-%d %H:%M:%S')
            
            print(f"[SmartFix] New Range: {from_str_26} to {to_str_26}")
            df_26 = client.fetch_data(symbol, from_str_26, to_str_26, interval=resolution)
            
            if not df_26.empty:
                print(f"[SmartFix] SUCCESS! Found {len(df_26)} bars in 2026.")
                df = df_26
                # Update filter vars to match the new 2026 data
                from_ = int(from_dt_26.timestamp())
                to = int(to_dt_26.timestamp())
                # Update text dates for logging
                from_date_str = from_str_26
                to_date_str = to_str_26

    print(f"DEBUG: fetch_data result type: {type(df)}")
    if hasattr(df, 'shape'):
        print(f"DEBUG: fetch_data result shape: {df.shape}")
        if not df.empty:
            print(f"DEBUG: Data Head:\n{df.head(2)}")
    
    if df is None or df.empty:
        print(f"Data fetch returned empty for {symbol}. Checking for fallback...")
        
        # RETRY: If empty, it might be a weekend/holiday request. Try extending lookback.
        # especially for YFinance, if 'start' date is Saturday, it returns nothing.
        # We extend back 5 days to ensure we catch the last trading session.
        try:
             # Use 4 days to be safe within 7-day 1m limit of YFinance
             retry_lookback = 4 if resolution == "1" else 30 
             retry_from_dt = to_dt - timedelta(days=retry_lookback)
             
             print(f"[Retry] CHECK: Original from={from_dt}, New from={retry_from_dt}", flush=True)
             
             # Only retry if our new start date is earlier than original
             if retry_from_dt < from_dt:
                 print(f"[Retry] Fetch returned empty. Attempting retry with -{retry_lookback}d lookback: {retry_from_dt}", flush=True)
                 retry_from_str = retry_from_dt.strftime('%Y-%m-%d %H:%M:%S')
                 df_retry = client.fetch_data(symbol, retry_from_str, to_date_str, interval=resolution)
                 if not df_retry.empty:
                      print(f"[Retry] SUCCESS: Fetched {len(df_retry)} bars with extended lookback.")
                      df = df_retry
                      # Update from_ to match the data we found (so filter doesn't kill it?) 
                      # NO, keep 'from_' as original request so SmartFilter at the end detects "from > data_max"
                      # and logic handles passing the data through.
        except Exception as e:
             print(f"[Retry] Error: {e}")

        
        # Fallback Logic: If Dhan/Primary fails, try Yahoo Finance for known indices
        fallback_map = {
            "NIFTY 50": "^NSEI",
            "NIFTY BANK": "^NSEBANK",
            "NIFTY": "^NSEI",
            "BANKNIFTY": "^NSEBANK"
        }
        
        if symbol in fallback_map and data_source != "yfinance":
            fallback_symbol = fallback_map[symbol]
            print(f"[Fallback] Attempting to fetch {fallback_symbol} from Yahoo Finance instead of {symbol}")
            try:
                yf_client_fallback = YFinanceClient()
                df = yf_client_fallback.fetch_data(fallback_symbol, from_date_str, to_date_str, interval=resolution)
                if not df.empty:
                    print(f"[Fallback] SUCCESS: Fetched {len(df)} bars from Yahoo Finance.")
                    # We continue with this 'df'
            except Exception as e:
                print(f"[Fallback] Failed: {e}")

    if df is None or df.empty:
        # CRITICAL FIX: Return "no_data" status to tell TradingView no data exists
        # This prevents infinite pagination requests for historical data
        print(f"[udf_history] No data available for {symbol}, returning no_data status")
        return {
            "s": "no_data",
            "debug_info": f"empty_after_retry (retry_lookback={locals().get('retry_lookback', 'N/A')})",
            "t": [],
            "o": [],
            "h": [],
            "l": [],
            "c": [],
            "v": [],
        }
    
    # Filter by time range requested by TV (only if we have data)
    if 'timestamp' not in df.columns:
         print(f"No timestamp column in data for {symbol}")
         return {"s": "ok", "t": [], "o": [], "h": [], "l": [], "c": [], "v": []}

    # DEBUG: Log timestamp data types and ranges
    print(f"DEBUG: from_={from_} ({from_date_str})")
    print(f"DEBUG: to={to} ({to_date_str})")
    print(f"DEBUG: df['timestamp'] dtype={df['timestamp'].dtype}")
    if len(df) > 0:
        print(f"DEBUG: df timestamp range: {df['timestamp'].min()} - {df['timestamp'].max()}")
        print(f"DEBUG: df timestamp as dates: {datetime.fromtimestamp(df['timestamp'].min()).isoformat()} - {datetime.fromtimestamp(df['timestamp'].max()).isoformat()}")
    
    # CRITICAL: Filter data to only include bars within the requested time range
    # TradingView expects data in the from-to range for pagination to work
    original_len = len(df)
    original_df = df.copy()  # Keep a copy before filtering
    
    # ADJUSTMENT: For Daily (1D/D) resolution, the timestamps might be aligned to Exchange Time (IST) 
    # which is 00:00 IST = 18:30 UTC (Previous Day). 
    # TradingView requests usually align to UTC Midnight.
    # So a bar for "June 11" might have timestamp June 10 18:30 UTC.
    # If TV requests from=June 11 00:00 UTC, strict filtering expels this bar.
    # We apply a buffer for Daily resolution.
    filter_from = from_
    if resolution in ["1D", "D", "W", "1W", "M", "1M"]:
         filter_from = from_ - 43200 # -12 hours buffer
         print(f"Daily/Weekly Resolution detected: Applying -12h buffer to start filter (From: {from_} -> {filter_from})")

    df = df[(df['timestamp'] >= filter_from) & (df['timestamp'] <= to)]
    print(f"Filtered data from {original_len} to {len(df)} bars (filter_from={filter_from}, to={to})")
    
    if len(df) == 0 and original_len > 0:
        print(f"  [DEBUG] Data was filtered out! Data range: {original_df['timestamp'].min()} - {original_df['timestamp'].max()}")
        print(f"  [DEBUG] Filter range: {filter_from} - {to}")
    
    # SMART FIX: If strict filtering eliminated ALL data, but we had valid data,
    # this often means the request's 'from_' timestamp falls outside market hours.
    # Example: TradingView requests from 15:33 IST, but market closes at 15:30.
    # In this case, return the most recent available data that's within 'to' range.
    if df.empty and original_len > 0:
        # Check if data exists that ends before 'from_' but is still relevant
        data_max_ts = original_df['timestamp'].max()
        data_min_ts = original_df['timestamp'].min()
        
        # Case 1: Request 'from_' is AFTER all our data (common with Yahoo Finance)
        # This happens when TradingView calculates 'from' based on current time which
        # may be outside market hours. Return data that's at least within the 'to' range.
        if from_ > data_max_ts:
            print(f"[SmartFilter] Request 'from' ({from_}) is after all available data (max: {data_max_ts})")
            print(f"[SmartFilter] Returning all {original_len} bars since they fall before 'from' but are the best available data")
            # Return data that's <= 'to' (all data before end of request is valid)
            df = original_df[original_df['timestamp'] <= to]
            if not df.empty:
                print(f"[SmartFilter] Recovered {len(df)} bars by relaxing 'from' filter")
        
        # Case 2: Request 'to' is BEFORE all our data (shouldn't happen normally)
        elif to < data_min_ts:
            print(f"[SmartFilter] Request 'to' ({to}) is before all available data (min: {data_min_ts})")
            # This is a genuine no-data scenario for this range
    
    if df.empty:
        print(f"No data in requested range after filtering.")
        # If we return "no_data", TradingView stops requesting history.
        # Ensure we only do this if we are truly at the start of available history (e.g. pre-2010).
        # Otherwise, return "ok" with empty arrays to signal "gap here, keep looking".
        if to < 1262304000: # Jan 1 2010
             return {"s": "no_data"}
        
        return {
            "s": "ok",
            "t": [],
            "o": [],
            "h": [],
            "l": [],
            "c": [],
            "v": [],
        }
    
    # Log pagination support
    print(f"PAGINATION: Returning {len(df)} bars for {symbol} ({resolution})")

    # Valid JSON
    return {
        "s": "ok",
        "t": df['timestamp'].fillna(0).tolist(),
        "o": df['open'].fillna(0).tolist(),
        "h": df['high'].fillna(0).tolist(),
        "l": df['low'].fillna(0).tolist(),
        "c": df['close'].fillna(0).tolist(),
        "v": df['volume'].fillna(0).tolist() if 'volume' in df else [],
    }

@app.get("/timescale_marks")
def udf_timescale_marks(symbol: str, from_: int = Query(..., alias="from"), to: int = Query(...), resolution: str = "D"):
    # Timescale marks are displayed on the X-axis (Time axis).
    # For now, return empty list to satisfy the library.
    return []

@app.get("/marks")
def udf_marks(symbol: str, from_: int = Query(..., alias="from"), to: int = Query(...), resolution: str = "1"):
    # Calculate Signals on the underlying data
    client = DhanClient()
    
    # Convert timestamps to Date Strings for precise fetching
    from_date_str = datetime.fromtimestamp(from_).strftime('%Y-%m-%d')
    to_date_str = datetime.fromtimestamp(to).strftime('%Y-%m-%d')
    
    # Align marks data fetch with history data fetch to ensure indicators match candles
    df = client.fetch_indices_data(from_date=from_date_str, to_date=to_date_str)
    
    if df is None or df.empty: 
        return []

    # Run Strategy
    engine = GannStrategyEngine(df)
    # For visualization, let's run a default strategy (e.g. Mechanical 3-Day) 
    # OR we could accept a query param 'strategy' if TV allows custom params (it does via 'custom_css_url' hack or similar, but simpler is hardcoded for now)
    
    trades = engine.run_mechanical_3day_swing()
    
    marks = []
    # Filter trades in range
    for t in trades:
        # trades have 'time' (str or int)
        t_time = int(t['time'])
        if from_ <= t_time <= to:
            color = "green" if t['type'] == 'buy' else "red"
            text = f"{t['type'].upper()} {t['label']}"
            shape = "arrowUp" if t['type'] == 'buy' else "arrowDown"
            
            marks.append({
                "id": f"{t_time}_{t['type']}",
                "time": t_time,
                # "color": color, 
                "color": {"border": color, "background": color}, # TV structure varies, simple color string usually works in 'minSize'
                "text": text,
                "label": "S" if t['type'] == 'sell' else "B",
                "labelFontColor": "white",
                "minSize": 14
            })
            
    return marks


@app.get("/time")
def udf_time():
    return int(time.time())

# -----------------------------------------------------------
# NEW: Independent Replay Endpoints
# -----------------------------------------------------------

@app.post("/fetch_candles")
async def fetch_candles(req: FetchCandlesRequest):
    """Fetch candlestick data without strategy evaluation - for independent replay"""
    try:
        print(f"[Step-by-Step] Fetching candles: {req.symbol} [{req.data_source}] from {req.from_date} to {req.to_date}, resolution: {req.resolution}")
        print(f"[Step-by-Step] Lookback bars requested: {req.lookback_bars}")
        
        client = get_data_client(req.data_source)
        
        # Calculate lookback date adjustment based on resolution and lookback_bars
        # This provides pivot/strategy context without fetching unnecessary data
        from_dt = datetime.strptime(req.from_date, '%Y-%m-%d')
        
        if req.lookback_bars > 0:
            # Calculate how many days of data we need for lookback_bars based on resolution
            # USER REQUEST: Remove strict "specific number" limitation.
            # We strictly calculate minimum needed, then multiply by HUGE factor to ensure "everything" is loaded organically
            # within reasonable fetch limits.
            
            if req.resolution in ['1D', 'D']:
                lookback_days = req.lookback_bars  # 1 bar = 1 day
            elif req.resolution == '60':
                lookback_days = max(1, req.lookback_bars // 6)
            elif req.resolution == '15':
                lookback_days = max(1, req.lookback_bars // 25)
            elif req.resolution == '5':
                lookback_days = max(1, req.lookback_bars // 75)
            else:  # resolution == '1' (1-minute)
                lookback_days = max(1, req.lookback_bars // 375)
            
            # Apply massive buffer (4x) to simulate "load everything" while keeping req.lookback_bars as a base
            # This ensures we get years of data for hourly, and months for minutes.
            lookback_days = int(lookback_days * 4.0) + 30
            
            # CAP lookback to avoid API timeouts (e.g. 10 years max)
            lookback_days = min(lookback_days, 3650)
            
            adjusted_from_dt = from_dt - timedelta(days=lookback_days)
            adjusted_from_date = adjusted_from_dt.strftime('%Y-%m-%d')
            print(f"[Step-by-Step] Adjusted from_date: {req.from_date} -> {adjusted_from_date} (expanded lookback: {lookback_days} days)")
        else:
            adjusted_from_date = req.from_date
        
        df = client.fetch_data(req.symbol, adjusted_from_date, req.to_date, interval=req.resolution)
        
        if df is None or df.empty:
            raise HTTPException(
                status_code=404, 
                detail=f"No data found for {req.symbol} ({req.from_date} to {req.to_date}). Resolution '{req.resolution}' on '{req.data_source}' might be limited (e.g. YFinance 1m is last 7 days only)."
            )
        
        # Convert to candlestick format
        candles = df[['timestamp', 'open', 'high', 'low', 'close']].copy()
        if 'volume' in df.columns:
            candles['volume'] = df['volume']
            
        candles_list = candles.to_dict(orient='records')
        
        # Rename timestamp to time
        for c in candles_list:
            c['time'] = c.pop('timestamp')
        
        # PRE-FETCH OPTION DATA if strategy uses options
        # This runs in the background and caches data for use during replay
        option_cache_ready = False
        if req.strategy and req.strategy in ['five_ema']:  # Add other option strategies here
            try:
                from option_price_cache import get_option_cache, clear_option_cache
                
                # Clear old cache for fresh data
                clear_option_cache()
                
                # Create new cache and prefetch
                cache = get_option_cache(client)
                
                # Determine underlying and base price
                underlying = 'NIFTY' if 'NIFTY' in req.symbol else 'BANKNIFTY'
                base_price = df['close'].iloc[-1] if not df.empty else None
                
                print(f"[OptionCache] Pre-fetching option data for {underlying}, base price: {base_price}")
                
                success = cache.prefetch_option_data(
                    underlying=underlying,
                    from_date=req.from_date,
                    to_date=req.to_date,
                    base_price=base_price,
                    strike_range=300,  # +/- 300 points (6 strikes each side for Nifty)
                    interval=req.resolution or '5'
                )
                
                if success:
                    stats = cache.get_cache_stats()
                    print(f"[OptionCache] Ready! {stats['contracts_cached']} contracts, {stats['price_points']} price points")
                    option_cache_ready = True
                else:
                    print("[OptionCache] Pre-fetch failed, will use index prices")
                    
            except Exception as cache_error:
                print(f"[OptionCache] Error during prefetch: {cache_error}")
                import traceback
                traceback.print_exc()
        
        print(f"[Replay] Returning {len(candles_list)} candles, option_cache_ready: {option_cache_ready}")
        
        return {"candles": candles_list, "option_cache_ready": option_cache_ready}
    except HTTPException:
        raise 
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching candles: {str(e)}")


@app.post("/evaluate_strategy_step")
async def evaluate_strategy_step(req: EvaluateStrategyRequest):
    """
    Evaluate strategy at current replay step - progressive evaluation.
    
    UNIFIED LOGIC: Routes to either strategy evaluation or study processing.
    - Strategies: Generate buy/sell signals
    - Studies: Generate drawing commands (angle fans, pivots, etc.)
    """
    try:
        # Check if this is a study or strategy
        from strategies import is_study
        
        if is_study(req.strategy):
            # STUDY PROCESSING
            return await _process_study_bar(req)
        else:
            # STRATEGY PROCESSING (existing logic)
            return await _process_strategy_bar(req)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"type": "none", "signal": None}


# Alias endpoint for backwards compatibility
@app.post("/evaluate_step")
async def evaluate_step(req: EvaluateStrategyRequest):
    """Alias for /evaluate_strategy_step - backwards compatibility"""
    return await evaluate_strategy_step(req)


async def _process_study_bar(req: EvaluateStrategyRequest):
    """
    Process study tools with adaptive fan drawing.
    
    Logic:
    1. Fast Path (Sequential): Process current bar, return delta (adds/removes).
    2. Slow Path (Reset/Jump): Replay history to build state, then return snapshot of ACTIVE fans only.
    """
    try:
        from study_tool.angular_coverage_study import AngularPriceCoverageStudy
        
        # Pass scale_ratio from frontend if provided, otherwise default
        study_config = {}
        if req.scale_ratio is not None and req.scale_ratio > 0:
            study_config['scale_ratio'] = req.scale_ratio
            print(f"[Study] Using scale_ratio from chart: {req.scale_ratio}")
        
        # Pass configurable pivot settings if provided
        if req.left_bars is not None:
            study_config['left_bars'] = req.left_bars
        if req.right_bars is not None:
            study_config['right_bars'] = req.right_bars
        
        study = AngularPriceCoverageStudy(config=study_config)
        
        # Convert candles to expected format
        candles = []
        for c in req.candles:
            candles.append({
                'time': int(c.get('time', 0)),
                'open': float(c.get('open', 0)),
                'high': float(c.get('high', 0)),
                'low': float(c.get('low', 0)),
                'close': float(c.get('close', 0)),
                'volume': float(c.get('volume', 0))
            })
        
        # OPTIMIZATION: Use cached state if available for sequential replay
        global _study_cache
        
        # Initialize cache if needed
        if '_study_cache' not in globals():
            _study_cache = {'index': -1, 'strategy': None, 'state': None}
            
        is_sequential = (
            _study_cache['strategy'] == req.strategy and 
            _study_cache['index'] == req.current_index - 1
        )
        
        output_drawings = []
        output_pivots = []
        output_remove = []
        
        if is_sequential and _study_cache['state']:
            # FAST PATH: Restore state and process single bar
            # print(f"[Study] Fast path: Resuming from index {req.current_index}")
            study.restore_state(_study_cache['state'])
            
            # Process strictly the current bar
            result = study.process_bar(
                candles=candles,
                bar_index=req.current_index,
                state=None # Already restored
            )
            
            # Pass through the Delta updates
            output_drawings = result.get('drawings', [])
            output_pivots = result.get('pivot_markers', [])
            output_remove = result.get('remove_drawings', [])
                
            # Update cache
            _study_cache['index'] = req.current_index
            _study_cache['state'] = result['state']
            
        else:
            # SLOW PATH: Full rebuild (first run or reset)
            print(f"[Study] Slow path: Rebuilding from 0 to {req.current_index}")
            _study_cache = {'index': -1, 'strategy': req.strategy, 'state': None}
            
            # Run history to build state (ignore outputs)
            for bar_idx in range(req.current_index + 1):
                study.process_bar(
                    candles=candles,
                    bar_index=bar_idx,
                    state=None
                )
            
            # Generate SNAPSHOT of currently active fans
            # This ensures we don't send ghost markers from destroyed fans
            active_fans = study.angle_engine.active_fans
            
            print(f"[Study] Index {req.current_index}: Snapshot of {len(active_fans)} active fans")
            
            for fid, fan in active_fans.items():
                print(f"[Study] Fan {fid}: {len(fan.lines)} lines")
                # Add Drawings
                output_drawings.extend(study.angle_engine.fan_to_drawing_commands(fan))
                
                # Add Markers (Regenerate with consistent IDs)
                # The new hierarchical structure stores marker info differently
                marked_times = set()  # Track to avoid duplicates
                
                # Method 1: Use stored hierarchy info (new v2.0 format)
                hierarchy_info = fan.config.get('hierarchy')
                if hierarchy_info:
                    # Mark Origin
                    if hierarchy_info.get('origin'):
                        p = hierarchy_info['origin']
                        if p['time'] not in marked_times:
                            pid = f"pm_{p['time']}_{p['type']}"
                            output_pivots.append({
                                'id': pid,
                                'type': f"pivot_{p['type']}",
                                'time': p['time'],
                                'price': p['price'],
                                'bar_index': p.get('bar_index', 0)
                            })
                            marked_times.add(p['time'])
                    
                    # Mark Outer Container pivots
                    if hierarchy_info.get('outer'):
                        for key in ['from', 'to']:
                            p = hierarchy_info['outer'].get(key)
                            if p and p['time'] not in marked_times:
                                pid = f"pm_{p['time']}_{p['type']}"
                                output_pivots.append({
                                    'id': pid,
                                    'type': f"pivot_{p['type']}",
                                    'time': p['time'],
                                    'price': p['price'],
                                    'bar_index': p.get('bar_index', 0)
                                })
                                marked_times.add(p['time'])
                
                # Method 2: Fallback to legacy format (from/to pivots + extra_pivots)
                else:
                    pivots_to_regen = [fan.from_pivot, fan.to_pivot]
                    if 'extra_pivots' in fan.config:
                        pivots_to_regen.extend(fan.config['extra_pivots'])

                    for p in pivots_to_regen:
                        if p['time'] not in marked_times:
                            pid = f"pm_{p['time']}_{p['type']}"
                            output_pivots.append({
                                'id': pid,
                                'type': f"pivot_{p['type']}",
                                'time': p['time'],
                                'price': p['price'],
                                'bar_index': p.get('bar_index', 0)
                            })
                            marked_times.add(p['time'])
            
            # Update cache after full run
            _study_cache['index'] = req.current_index
            _study_cache['state'] = study._get_state()
            
            # In reset scenario, we don't need to specify removals as the frontend usually clears shapes
            output_remove = []

        
        return {
            "type": "drawing_update",
            "drawings": output_drawings,
            "pivot_markers": output_pivots,
            "remove_drawings": output_remove,
            "state": {}
        }
        
    except Exception as e:
        import traceback
        print(f"[Study] Error processing bar: {e}")
        traceback.print_exc()
        return {"type": "none", "drawings": [], "pivot_markers": []}







async def _process_strategy_bar(req: EvaluateStrategyRequest):
    """Process a single bar for trading strategies (returns signals)"""
    global _replay_positions
    
    try:
        # Clear position state when new replay starts (current_index < 10 suggests new replay)
        if req.current_index < 10 and req.strategy in _replay_positions:
            print(f"[Strategy] New replay detected - clearing position state for {req.strategy}")
            del _replay_positions[req.strategy]
        
        # Convert candles list back to DataFrame
        df = pd.DataFrame(req.candles)
        df.rename(columns={'time': 'timestamp'}, inplace=True)
        
        # Ensure required columns exist
        required_cols = ['timestamp', 'open', 'high', 'low', 'close']
        if not all(col in df.columns for col in required_cols):
            return {"type": "none", "signal": None}
        
        # Ensure numeric types
        for col in ['open', 'high', 'low', 'close']:
            df[col] = pd.to_numeric(df[col])
        
        # UNIFIED STRATEGY LOGIC: Use the SAME strategies.py as /run_backtest
        try:
            from strategies import get_strategy
            from base_strategy import SignalType
            
            strategy = get_strategy(req.strategy, df)
            signals_df = strategy.generate_signals()
            
        except Exception as strategy_error:
            print(f"[Strategy] Strategy error: {strategy_error}")
            import traceback
            traceback.print_exc()
            return {"type": "none", "signal": None}
        
        # Find signal at current candle
        current_trade = None
        if req.current_index < len(signals_df):
            current_row = signals_df.iloc[req.current_index]
            signal_type = current_row.get('signal', SignalType.HOLD)
            
            if signal_type in [SignalType.BUY, SignalType.SELL]:
                trade_type = 'buy' if signal_type == SignalType.BUY else 'sell'
                signal_label = str(current_row.get('signal_label', f'{trade_type.upper()} Signal'))
                
                # --- ON-DEMAND OPTION DATA FETCHING ---
                # Fetch option prices only when instrument_type is 'options'
                fetched_opt_price = None
                contract_details = None
                
                if req.instrument_type == 'options':
                    try:
                        import re
                        from option_contract_service import OptionContractService
                        from dhan_client import DhanClient
                        from datetime import datetime
                        
                        # Initialize service (relies on internal caching of DhanClient/Service)
                        oc_service = OptionContractService(DhanClient())
                        ref_date = datetime.fromtimestamp(int(current_row['timestamp']))
                        
                        # Case A: Entry Signal (Parse details from label)
                        label_match = re.search(r'(\d+)\s+(CE|PE)\s+\(([^)]+)\)', signal_label)
                        if label_match:
                            strike = float(label_match.group(1))
                            opt_type = label_match.group(2)
                            expiry_str = label_match.group(3)
                            
                            contract = oc_service.resolve_contract(
                                underlying='NIFTY',
                                strike=strike,
                                option_type=opt_type,
                                expiry_str=expiry_str,
                                reference_date=ref_date
                            )
                            
                            if contract:
                                res = oc_service.get_price_at_timestamp(contract, int(current_row['timestamp']))
                                if res and res.price > 0:
                                    fetched_opt_price = res.price
                                    contract_details = {
                                        'strike': strike,
                                        'option_type': opt_type,
                                        'expiry_str': expiry_str
                                    }
                        
                        # Case B: Exit Signal (Retrieve details from active position)
                        elif 'Exit' in signal_label and req.strategy in _replay_positions:
                            pos = _replay_positions[req.strategy]
                            if 'contract_details' in pos and pos['contract_details']:
                                cd = pos['contract_details']
                                contract = oc_service.resolve_contract(
                                    underlying='NIFTY',
                                    strike=cd['strike'],
                                    option_type=cd['option_type'],
                                    expiry_str=cd['expiry_str'],
                                    reference_date=ref_date
                                )
                                if contract:
                                    res = oc_service.get_price_at_timestamp(contract, int(current_row['timestamp']))
                                    if res and res.price > 0:
                                        fetched_opt_price = res.price
                        
                    except Exception as opt_err:
                        print(f"[Strategy] Option Fetch Warning: {opt_err}")

                # Apply fetched price
                signal_price = float(current_row.get('signal_price', current_row['close']))
                option_price_val = None
                
                if fetched_opt_price:
                    signal_price = fetched_opt_price
                    option_price_val = fetched_opt_price
                    # append price to label for visibility
                    signal_label += f" | Opt: {fetched_opt_price:.2f}"
                    print(f"[Strategy] Fetched Price: {fetched_opt_price:.2f} for {signal_label}")
                
                current_trade = {
                    "time": int(current_row['timestamp']),
                    "type": trade_type,
                    "price": signal_price,
                    "label": signal_label,
                    "pnl": None,
                    "option_price": option_price_val
                }
                
                # POSITION TRACKING FOR PNL CALCULATION
                is_entry = 'Buy' in signal_label and ('CE' in signal_label or 'PE' in signal_label)
                is_exit = 'Exit' in signal_label
                
                if is_entry:
                    # Open new position
                    _replay_positions[req.strategy] = {
                        'position_type': 'long' if 'CE' in signal_label else 'short',
                        'entry_price': signal_price,
                        'entry_time': int(current_row['timestamp']),
                        'entry_label': signal_label,
                        'contract_details': contract_details  # Store for exit lookup
                    }
                    print(f"[Strategy] ENTRY: {signal_label} @ ₹{signal_price:.2f}")
                    
                elif is_exit and req.strategy in _replay_positions:
                    # Close position and calculate PnL
                    position = _replay_positions[req.strategy]
                    entry_price = position['entry_price']
                    exit_price = signal_price
                    
                    # PnL = exit - entry (for options, profit when premium increases)
                    pnl = exit_price - entry_price
                    
                    current_trade['pnl'] = pnl
                    current_trade['label'] = f"{signal_label} (PnL: {pnl:+.2f})"
                    
                    print(f"[Strategy] EXIT: {signal_label} @ ₹{exit_price:.2f} | Entry: ₹{entry_price:.2f} | PnL: {pnl:+.2f}")
                    
                    # Clear position
                    del _replay_positions[req.strategy]
                else:
                    print(f"[Strategy] Signal: {signal_label} @ ₹{signal_price:.2f}")
        
        # FOR 5 EMA STRATEGY: Include EMA line as indicator drawing
        indicator_drawings = []
        if req.strategy == 'five_ema' and 'ema_5' in signals_df.columns:
            # Build EMA line from all visible candles (up to current index)
            visible_df = signals_df.iloc[:req.current_index + 1]
            
            if len(visible_df) >= 2:
                # Create polyline points for EMA
                ema_points = []
                for idx in range(len(visible_df)):
                    row = visible_df.iloc[idx]
                    ema_val = row.get('ema_5')
                    if ema_val is not None and not pd.isna(ema_val):
                        ema_points.append({
                            "time": int(row['timestamp']),
                            "price": float(ema_val)
                        })
                
                if len(ema_points) >= 2:
                    indicator_drawings.append({
                        "id": "ema_5_line",
                        "type": "polyline",
                        "points": ema_points,
                        "options": {
                            "shape": "polyline",
                            "overrides": {
                                "lineColor": "#FFD700",  # Gold color for EMA
                                "lineWidth": 2,
                                "lineStyle": 0  # Solid line
                            }
                        }
                    })
        
        # ENRICH SIGNAL WITH ACTUAL OPTION PRICE FROM CACHE

        
        # Return both signal and indicator drawings
        return {
            "type": "signal", 
            "signal": current_trade,
            "indicator_drawings": indicator_drawings  # New field for indicators
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"type": "none", "signal": None}


# -----------------------------------------------------------

@app.post("/run_backtest")
def run_backtest(req: BacktestRequest):
    """
    Run backtest using the new separated architecture.
    Strategies generate signals, BacktestEngine handles execution.
    """
    try:
        # Get Client based on source
        client = get_data_client(req.data_source)
        df = pd.DataFrame()
        
        print(f"Backtest Request: {req.symbol} [{req.data_source}] {req.from_date} to {req.to_date}")
        
        # Determine Data Source based on Symbol
        # Note: Frontend currently focuses on NIFTY OPTIONS (Index Fallback) or NIFTY 50
        if req.data_source == "dhan":
            if req.symbol == "NIFTY OPTIONS" or req.symbol == "NIFTY 50":
                 if req.from_date and req.to_date:
                     # Generic Fetch handles Index/Options fallback logic internally now
                     df = client.fetch_data("NIFTY 50", req.from_date, req.to_date, interval=req.resolution) 
                 else:
                     df = client.fetch_options_data(days_back=req.days)
            else:
                 # Generic Search logic/Dhan Scrip Master
                 if req.from_date and req.to_date:
                     df = client.fetch_data(req.symbol, req.from_date, req.to_date, interval=req.resolution)
                 else:
                      # Fallback default
                      end_d = datetime.now()
                      start_d = end_d - timedelta(days=req.days)
                      df = client.fetch_data(req.symbol, start_d.strftime("%Y-%m-%d"), end_d.strftime("%Y-%m-%d"))
        
        elif req.data_source == "yfinance":
            # Simple direct fetch for Yahoo
            # req.symbol needs to be the Yahoo Ticker (e.g. "RELIANCE.NS")
            if req.from_date and req.to_date:
                df = client.fetch_data(req.symbol, req.from_date, req.to_date, interval=req.resolution)
            else:
                end_d = datetime.now()
                start_d = end_d - timedelta(days=req.days)
                df = client.fetch_data(req.symbol, start_d.strftime("%Y-%m-%d"), end_d.strftime("%Y-%m-%d"), interval=req.resolution)

        
        if df is None or df.empty:
            raise HTTPException(status_code=500, detail=f"Failed to fetch data for {req.symbol}")

        # NEW ARCHITECTURE: Use separated strategy and backtesting engine
        try:
            # Prepare strategy parameters
            strategy_params = {}
            
            # For five_ema strategy, pass dhan_client for option data enrichment
            if req.strategy == 'five_ema':
                strategy_params['dhan_client'] = client
                strategy_params['underlying'] = 'NIFTY' if 'NIFTY' in req.symbol else 'BANKNIFTY'
                strategy_params['use_option_data'] = True
            
            # Get strategy instance (pure signal generator)
            strategy = get_strategy(req.strategy, df, params=strategy_params)
            
            # Create backtesting engine (handles position management and P&L)
            backtest_engine = BacktestEngine(strategy)
            
            # Run backtest
            result = backtest_engine.run(symbol=req.symbol)
            
            # Convert trades to old format for frontend compatibility
            trades = [t.to_dict() for t in result.trades]
            
            print(f"NEW ENGINE: Backtest completed - {result.metrics['total_trades']} trades, P&L: {result.metrics['total_pnl']}")
            
        except Exception as strategy_error:
            print(f"CRITICAL: Strategy Execution Failed: {strategy_error}")
            import traceback
            traceback.print_exc()
            # STRICT MODE: Do not fallback. Fail the request.
            raise HTTPException(status_code=500, detail=str(strategy_error))
            
            # Legacy Fallback Removed
            # engine = GannStrategyEngine(df)
            # ...
        
        # Prepare response
        # We return EVERYTHING so frontend can replay it
        # Ensure volume is included
        chart_data = df[['timestamp', 'open', 'high', 'low', 'close']].copy()
        if 'volume' in df.columns:
            chart_data['volume'] = df['volume']
            
        chart_data_list = chart_data.to_dict(orient='records')
        
        for c in chart_data_list:
            c['time'] = c.pop('timestamp')

        # STRICT FILTERING: Ensure only data/trades within requested range are returned
        # User explicitly requested: "only those candles should appear... within the range mentioned"
        
        # CRITICAL FIX: Use IST timezone since Dhan data is in IST
        # Convert request strings to timestamps for comparison
        # Format is YYYY-MM-DD
        ist = pytz.timezone('Asia/Kolkata')
        
        # Parse dates as IST (not system local time)
        from_dt = ist.localize(datetime.strptime(req.from_date, "%Y-%m-%d"))
        from_ts = int(from_dt.timestamp())
        
        # For end date, we want to include the full day
        to_dt = ist.localize(datetime.strptime(req.to_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59))
        to_ts = int(to_dt.timestamp())
        
        print(f"DEBUG: Filtering range (IST): {from_dt} to {to_dt}")
        print(f"DEBUG: Filtering range (Unix): {from_ts} to {to_ts}")
        
        # Filter Candles
        filtered_candles = [
            c for c in chart_data_list 
            if from_ts <= c['time'] <= to_ts
        ]
        
        # Filter Trades
        filtered_trades = [
            t for t in trades 
            if from_ts <= int(t['time']) <= to_ts
        ]
        
        print(f"Backtest Filtering: {len(chart_data_list)} -> {len(filtered_candles)} bars, {len(trades)} -> {len(filtered_trades)} trades (Range: {req.from_date} to {req.to_date})")

        return {
            "candles": filtered_candles,
            "trades": filtered_trades,
            "strategy": req.strategy,
            "symbol": req.symbol
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Backend Error: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8005, reload=True)
