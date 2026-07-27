from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import glob as _glob
import json as _json
import os as _os
import uvicorn
import pandas as pd
from dhan_client import DhanClient
from yfinance_client import YFinanceClient
from binance_client import BinanceClient
from gann_logic import GannStrategyEngine  # Keep for backward compatibility
from strategies import get_strategy, STRATEGY_REGISTRY  # New strategy system
from backtest_engine import BacktestEngine  # New backtesting engine
import time
import re
from datetime import datetime, timedelta, timezone
import pytz
import logging
import sys
import os
import json
from scripts.run_paths import build_run_dir
from hypothesis_report_transform import enrich_detailed_log

# --- LOGGING CONFIGURATION ---
LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs", "backend"
)

# Ensure log directory exists
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Clean up old session logs in the logs directory
for filename in os.listdir(LOG_DIR):
    if filename.startswith("backend_session_") and filename.endswith(".log"):
        file_path = os.path.join(LOG_DIR, filename)
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Failed to delete old log {file_path}: {e}")

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = os.path.join(LOG_DIR, f"backend_session_{timestamp}.log")

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

# --- REPLAY EVENTS CSV ---
import csv

REPLAY_EVENTS_CSV = os.path.join(LOG_DIR, "replay_events.csv")

# Warmup constants: how many days of history to process before the visible chart start.
# Ensures pivot numbering is stable and matches across corpus, backend simulation, and frontend replay.
# For limited sources (YFinance 1m/4m ~8 days), uses whatever is available.
WARMUP_DAYS = {
    "1":  30,    # 1-minute: ~30 days warmup (YFinance limited to ~8, capped)
    "4":  30,    # 4-minute: same as 1m (YFinance ~8 day limit)
    "5":  75,    # 5-minute
    "15": 120,   # 15-minute
    "30": 120,   # 30-minute
    "60": 90,    # 60-minute / 1-hour
    "240": 250,  # 4-hour
    "1D": 365,   # Daily
    "D":  365,
    "W":  730,   # Weekly
    "M":  1825,  # Monthly
}

def _write_replay_event_to_csv(event: dict):
    """Append a single intersection event to replay_events.csv in simulation_events.csv format."""
    if not event:
        return
    ist = pytz.timezone('Asia/Kolkata')
    dt_utc = datetime.fromtimestamp(event.get('time', 0), pytz.utc)
    dt_ist = dt_utc.astimezone(ist)
    m = dt_ist.month
    d = dt_ist.day
    y = dt_ist.year
    time_str = dt_ist.strftime("%I:%M:%S %p")
    if time_str.startswith('0'):
        time_str = time_str[1:]
    dt_str = f"{m}/{d}/{y}, {time_str}"
    details_str = str(event.get('details', '')).replace(',', ';')
    file_exists = os.path.exists(REPLAY_EVENTS_CSV)
    with open(REPLAY_EVENTS_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['#', 'Time', 'Fan', 'Fraction', 'Price', 'Type', 'Details',
                             'Open', 'High', 'Low', 'Close', 'Active_Angles',
                             'Cluster', 'Zone', 'Zone_Highest_Close', 'Zone_Lowest_Close',
                             'Next_Angle_Line',
                             'MFE_10', 'MAE_10', 'bars_elapsed', 'bar_index'])
        writer.writerow([
            '',  # row_num filled by post-processing if needed
            dt_str,
            event.get('fan', ''),
            event.get('fraction', ''),
            f"{event.get('price', 0):.2f}",
            event.get('type', ''),
            details_str,
            f"{event.get('open', 0):.2f}",
            f"{event.get('high', 0):.2f}",
            f"{event.get('low', 0):.2f}",
            f"{event.get('close', 0):.2f}",
            json.dumps(event.get('activeAngles', {})),
            event.get('cluster', False),
            event.get('zone', ''),
            f"{event.get('zoneExtremes', {}).get('highest_close', 0):.2f}" if event.get('zoneExtremes', {}).get('highest_close') else '',
            f"{event.get('zoneExtremes', {}).get('lowest_close', 0):.2f}" if event.get('zoneExtremes', {}).get('lowest_close') else '',
            event.get('nextAngleLine', ''),
            '0', '0', 0,
            event.get('bar_index', 0)
        ])

def _truncate_replay_events_csv():
    """Truncate replay_events.csv for a new replay session."""
    with open(REPLAY_EVENTS_CSV, 'w', newline='') as f:
        pass  # empty file

# -----------------------------
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ticker_config.json")
try:
    with open(CONFIG_FILE, 'r') as f:
        TICKER_CONFIG = json.load(f)
    print(f"Successfully loaded ticker configuration from {CONFIG_FILE}")
except Exception as e:
    print(f"Warning: Could not load ticker_config.json: {e}")
    TICKER_CONFIG = {}
# -----------------------------

app = FastAPI()
print("--- BACKEND RESTART v4 - PNL TRACKING ---")

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

print(f"Middleware Stack: {app.user_middleware}")

class BacktestRequest(BaseModel):
    strategy: str
    symbol: str = "NIFTY OPTIONS" # Default
    from_date: str = None # YYYY-MM-DD
    to_date: str = None   # YYYY-MM-DD
    days: int = 5
    resolution: str = "1" # Default to 1-minute
    data_source: str = "dhan"  # "dhan" or "yfinance"
    pivotSettings: Optional[Dict[str, Any]] = None  # Settings like leftBars, rightBars, showIntersectionLabels

class FetchCandlesRequest(BaseModel):
    symbol: str
    from_date: str
    to_date: str  
    resolution: str = "1"
    strategy: Optional[str] = None  # Optional: if provided, prefetch option data for option strategies
    data_source: str = "dhan"  # "dhan" or "yfinance"
    lookback_bars: int = 50  # Number of bars to fetch before from_date for pivot context
    pivotSettings: Optional[Dict[str, Any]] = None  # Settings like leftBars, rightBars, showIntersectionLabels

def get_data_client(data_source: str = "dhan"):
    """Factory function to get appropriate data client."""
    if data_source == "yfinance":
        return YFinanceClient()
    if data_source == "binance":
        return BinanceClient(use_testnet=False)
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
    show_intersection_labels: bool = False  # Toggle for drawing price labels on intersection
    symbol: str | None = None
    resolution: str | None = None
    cycle_type: str = "24_hour"
    session_duration: str = "standard"

@app.get("/")
def read_root():
    return {"status": "Gann Backend Online"}

# Centralized logic for Ticker + Timeframe geometric ratios
def get_dynamic_scale_ratio(symbol: str, resolution: str, cycle_type: str = "24_hour", session_duration: str = "standard") -> float:
    """
    Given a ticker symbol, timeframe (resolution), cycle type, and session duration,
    return the correct Price-to-Bar ratio from the configuration.
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty")
        
    symbol_upper = symbol.upper()
    
    # Map common symbols to config keys
    mapped_symbol = symbol_upper
    if 'AAPL' in symbol_upper:
        mapped_symbol = 'AAPL'
    elif 'NSEI' in symbol_upper or 'NIFTY' in symbol_upper:
        mapped_symbol = 'NIFTY 50'
        
    # Map TradingView resolutions to config keys
    res_map = {
        "1": "1-Minute",
        "4": "4-Minute",
        "15": "15-Minute",
        "60": "60-Minute",
        "1H": "60-Minute",
        "240": "240-Minute",
        "4H": "240-Minute"
    }
    mapped_res = res_map.get(resolution, f"{resolution}-Minute")
    
    if mapped_symbol not in TICKER_CONFIG:
        raise ValueError(f"Increment configuration not found for ticker {symbol} ({mapped_symbol})")
        
    if cycle_type not in TICKER_CONFIG[mapped_symbol]:
        raise ValueError(f"Cycle type '{cycle_type}' not found for ticker {mapped_symbol}")
        
    if session_duration not in TICKER_CONFIG[mapped_symbol][cycle_type]:
        raise ValueError(f"Session duration '{session_duration}' not found for ticker {mapped_symbol} under cycle '{cycle_type}'")
        
    if mapped_res not in TICKER_CONFIG[mapped_symbol][cycle_type][session_duration]:
        raise ValueError(f"Increment configuration not found for ticker {mapped_symbol} on {mapped_res} timeframe ({cycle_type}/{session_duration})")
        
    return TICKER_CONFIG[mapped_symbol][cycle_type][session_duration][mapped_res]

@app.get("/api/scale_ratio")
def api_scale_ratio(symbol: str, resolution: str, cycle_type: str = "24_hour", session_duration: str = "standard"):
    try:
        ratio = get_dynamic_scale_ratio(symbol, resolution, cycle_type, session_duration)
        return {"scale_ratio": ratio}
    except ValueError as e:
        # Return 404 so the frontend knows it failed and can handle it gracefully
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/api/binance-strategy-trades")
def api_binance_strategy_trades(symbol: str = "BTCUSDT", interval: str = "1h"):
    pattern = f"strategy_trades_{symbol}_{interval}*.json"
    matches = _glob.glob(pattern)
    if not matches:
        matches = _glob.glob("strategy_trades_*.json")
    if not matches:
        raise HTTPException(status_code=404, detail="No strategy trades file found. Run replay first with: python run_binance_live.py BTCUSDT 1h 500 --target-progression")
    matches.sort(key=lambda f: _os.path.getmtime(f), reverse=True)
    latest_file = matches[0]
    mtime = _os.path.getmtime(latest_file)
    with open(latest_file, 'r') as f:
        data = _json.load(f)
    data['file_name'] = _os.path.basename(latest_file)
    data['file_mtime'] = mtime
    data['file_mtime_iso'] = datetime.fromtimestamp(mtime).isoformat()
    return JSONResponse(content=data)

# --- UDF (Universal Data Feed) Endpoints for TradingView Advanced Charts ---

@app.get("/config")
def udf_config():
    return {
        "supported_resolutions": ["1", "4", "5", "15", "30", "60", "240", "D", "W", "M"],
        "supports_group_request": False,
        "supports_marks": True,
        "supports_search": True,
        "supports_timescale_marks": True,
        "exchanges": [
            {"value": "NSE", "name": "NSE", "desc": "National Stock Exchange"},
        ],
        "symbols_types": [
            {"name": "All types", "value": ""},
            {"name": "Crypto", "value": "crypto"},
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

    # Route to Binance search if selected
    if data_source == "binance":
        q = query.upper().strip()
        # Fetch all available USDT pairs from Binance exchange info
        try:
            # Use mainnet for exchange info to get the full list of pairs (no auth needed)
            bc = BinanceClient(use_testnet=False)
            exchange_info = bc.get_exchange_info()
            all_symbols = exchange_info.get("symbols", [])
            # Filter for USDT pairs that are TRADING and have "USDT" as quote asset
            usdt_pairs = [
                s["symbol"] for s in all_symbols
                if s.get("quoteAsset") == "USDT"
                and s.get("status") == "TRADING"
                and s.get("contractType") == "PERPETUAL"
            ]
            # Sort alphabetically for consistent ordering
            usdt_pairs.sort()
            print(f"[Binance Search] Found {len(usdt_pairs)} USDT perpetual pairs from exchange info")
        except Exception as e:
            print(f"[Binance Search] Failed to fetch exchange info: {e}, falling back to hardcoded list")
            usdt_pairs = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"]

        for pair in usdt_pairs:
            if q and q not in pair:
                continue
            results.append({
                "symbol": pair,
                "full_name": f"Binance:{pair}",
                "description": f"{pair} Binance Futures",
                "exchange": "Binance",
                "ticker": pair,
                "type": "crypto"
            })
        if not results and q:
            # If no exact match, try a fuzzy guess
            if len(q) >= 2:
                guess = f"{q}USDT" if not q.endswith("USDT") else q
                # Check if the guess exists in the pairs list
                if guess in usdt_pairs:
                    results.append({
                        "symbol": guess,
                        "full_name": f"Binance:{guess}",
                        "description": f"{guess} Binance Futures",
                        "exchange": "Binance",
                        "ticker": guess,
                        "type": "crypto"
                    })
                else:
                    # Return closest matches for the query
                    for pair in usdt_pairs:
                        if q in pair:
                            results.append({
                                "symbol": pair,
                                "full_name": f"Binance:{pair}",
                                "description": f"{pair} Binance Futures",
                                "exchange": "Binance",
                                "ticker": pair,
                                "type": "crypto"
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

    # Check for Binance Suffix
    is_binance = symbol.endswith(":BN")
    clean_symbol = clean_symbol.replace(":BN", "")

    # Auto-detect Binance crypto pairs
    if not is_yfinance and not is_binance:
        if re.match(r'^[A-Z0-9]{2,12}USDT$', clean_symbol):
            is_binance = True
    
    if is_yfinance:
        client = YFinanceClient()
        info = client.get_info(clean_symbol)
        if info:
            info['symbol'] = symbol
            info['ticker'] = symbol
            return info

    if is_binance:
        return {
            "name": clean_symbol,
            "exchange-traded": "Binance",
            "exchange-listed": "Binance",
            "timezone": "Etc/UTC",
            "minmov": 1,
            "minmov2": 0,
            "pointvalue": 1,
            "session": "24x7",
            "has_intraday": True,
            "intraday_multipliers": ["1", "4", "5", "15", "30", "60", "240"],
            "has_daily": True,
            "has_weekly_and_monthly": True,
            "description": clean_symbol,
            "type": "crypto",
            "supported_resolutions": ["1", "4", "5", "15", "30", "60", "240", "D", "W", "M"],
            "pricescale": 100,
            "ticker": symbol,
        }
            
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
        "intraday_multipliers": ["1", "4", "5", "15", "30", "60", "240"],
        "has_daily": True,
        "has_weekly_and_monthly": True, 
        "description": symbol,
        "type": "index" if "INDEX" in symbol or "NIFTY" in symbol else "stock",
        "supported_resolutions": ["1", "4", "5", "15", "30", "60", "240", "D", "W", "M"],
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

    # Detect explicit Binance marker
    is_binance = symbol.endswith(":BN") or data_source == "binance"
    clean_symbol = clean_symbol.replace(":BN", "")

    # Auto-detect Yahoo Finance symbols by pattern if not explicitly marked
    # This handles cases where TradingView strips the :YF suffix
    if not is_yfinance and not is_binance:
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

    # Auto-detect Binance crypto pairs (e.g. BTCUSDT, ETHUSDT)
    if not is_yfinance and not is_binance:
        if re.match(r'^[A-Z0-9]{2,12}USDT$', clean_symbol):
            is_binance = True
            print(f"[udf_history] Auto-detected Binance crypto symbol: {clean_symbol}")
    
    if is_yfinance:
        client = get_data_client("yfinance")
        symbol = clean_symbol
        data_source = "yfinance"
    elif is_binance:
        client = get_data_client("binance")
        symbol = clean_symbol
        data_source = "binance"
        print(f"[udf_history] Using Binance client for {symbol}")

    df = pd.DataFrame()
    
    # Convert timestamps to Date Strings.
    # Binance & YFinance expect UTC; Dhan API expects local time (IST).
    _tz = timezone.utc if data_source in ("binance", "yfinance") else None
    try:
        from_dt_safe = datetime.fromtimestamp(max(0, from_), tz=_tz)
        to_dt_safe = datetime.fromtimestamp(max(0, to), tz=_tz)
    except (ValueError, OSError):
        from_dt_safe = datetime.fromtimestamp(0, tz=_tz)
        to_dt_safe = datetime.fromtimestamp(0, tz=_tz)

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
    
    if from_dt < calculated_from_dt:
        from_dt = calculated_from_dt
        from_date_str = from_dt.strftime('%Y-%m-%d')
        print(f"Range limited to {max_lookback_days} days for resolution {resolution}: {from_date_str} to {to_date_str}")
    
    # PREVENT INFINITE PAGINATION FOR YFINANCE
    # If TradingView requests a small chunk, it will paginate infinitely
    # By expanding the request here, we force a large chunk to be fetched and cached by TV
    if data_source == "yfinance":
        if resolution in ["60", "1H"]:
            # For 1h, YFinance supports up to 730 days. Expand to fetch a large chunk.
            expanded_from = to_dt_safe - timedelta(days=700)
            if from_dt_safe > expanded_from:
                from_dt_safe = expanded_from
                from_date_str = from_dt_safe.strftime('%Y-%m-%d %H:%M:%S')
                print(f"[Pagination Fix] Expanded 60m request to {from_date_str} to prevent TV pagination barrage")
        elif resolution in ["15", "30", "5", "2"]:
            # For 15m/30m, YFinance supports up to 60 days
            expanded_from = to_dt_safe - timedelta(days=58)
            if from_dt_safe > expanded_from:
                from_dt_safe = expanded_from
                from_date_str = from_dt_safe.strftime('%Y-%m-%d %H:%M:%S')
                print(f"[Pagination Fix] Expanded {resolution}m request to {from_date_str} to prevent TV pagination barrage")

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
    
    # Lenient time-range filter for ALL resolutions.
    # Returning unfiltered data causes TradingView to see bars far before the
    # requested range, triggering an infinite scroll-back loop: it keeps requesting
    # earlier data, gets the same full dataset again, and repeats forever.
    original_df = df.copy()
    original_len = len(df)

    if original_len > 0 and 'timestamp' in df.columns:
        try:
            res_minutes = int(resolution)
        except ValueError:
            res_minutes = 1
        buffer_seconds = max(86400, res_minutes * 60 * 300)  # 1 day or 300 bars
        filter_from = from_ - buffer_seconds

        # For daily+ resolutions, use a larger buffer to handle IST/UTC misalignment
        if resolution in ["1D", "D", "W", "1W", "M", "1M"]:
            filter_from = from_ - 86400  # 1 day buffer

        df = df[(df['timestamp'] >= filter_from) & (df['timestamp'] <= to)]

        # If buffer eliminated all data, determine WHY before falling back.
        if len(df) == 0:
            data_max_ts = original_df['timestamp'].max()
            data_min_ts = original_df['timestamp'].min()
            # Case 1: Requested from_ is past the last available bar.
            # Extend the filter backwards to include recent data so the chart
            # has something to display. (Returning no_data here would break the
            # initial chart load on weekends/holidays when "now" is past data end.)
            if from_ > data_max_ts:
                extended_filter_from = data_max_ts - buffer_seconds * 2
                df = original_df[original_df['timestamp'] >= extended_filter_from]
                print(f"[History] from_ ({from_}, {datetime.fromtimestamp(from_)}) is past last bar "
                      f"({data_max_ts}, {datetime.fromtimestamp(data_max_ts)}). "
                      f"Extended filter back to include last {len(df)} bars.")
            # Case 2: Requested range is entirely before available data.
            elif to < data_min_ts:
                print(f"[History] to ({to}) is before first bar. Returning no_data.")
                return {
                    "s": "no_data",
                    "t": [], "o": [], "h": [], "l": [], "c": [], "v": [],
                }
            # Case 3: Genuine gap (e.g. outside market hours within data range).
            # Return the full dataset so TradingView can fill the screen.
            else:
                df = original_df
                print(f"[History] Filter eliminated all {original_len} bars (from={from_}, to={to}). Returning full dataset.")
        else:
            print(f"[History] Filtered from {original_len} to {len(df)} bars (from={from_}, to={to})")
    else:
        print(f"[History] No data or no timestamp column. Skipping filter.")

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
        
        # Prepare valid symbol for fetching (strip YF tag)
        clean_symbol = req.symbol
        if clean_symbol.endswith(":YF"):
            clean_symbol = clean_symbol.replace(":YF", "")
        
        # Determine warmup window using from_date-anchored strategy.
        # The user's chosen from_date is always the reference point.
        # Treat the date string as UTC (not local) to match simulation & binance replay scripts.
        from_dt_utc = datetime.strptime(req.from_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        target_start_ts = int(from_dt_utc.timestamp())  # Used to filter initial markers
        if req.lookback_bars == 0:
            warmup_from_dt = from_dt_utc
            warmup_days = 0
            print(f"[FetchCandles] lookback_bars=0: using from_date directly, no warmup")
        else:
            warmup_days = WARMUP_DAYS.get(req.resolution, 250)
            warmup_from_dt = from_dt_utc - timedelta(days=warmup_days)

        # Check if source has enough history for this warmup
        # Sources like Dhan have years; YFinance 1m/4m has ~8 days only
        SOURCE_HISTORY_LIMITS = {
            "yfinance_1m": 8,
            "yfinance_4m": 8,
            "yfinance_other": 700,  # 1y for most other intervals
        }

        source_key = f"yfinance_{req.resolution}" if req.data_source == "yfinance" else "unlimited"
        if req.data_source == 'yfinance' and req.resolution not in ['1', '4']:
            source_key = "yfinance_other"
        elif req.data_source == 'yfinance' and req.resolution == '4':
            source_key = "yfinance_4m"
        elif req.data_source == 'yfinance':
            source_key = "yfinance_1m"

        source_max_days = SOURCE_HISTORY_LIMITS.get(source_key, 700)

        if warmup_days > source_max_days:
            # Source can't provide enough warmup — use today-anchored fetch
            # This is the best we can do; warn the caller
            warmup_from_dt = datetime.now() - timedelta(days=source_max_days)
            print(f"[FetchCandles] WARNING: {req.data_source} {req.resolution}m has ~{source_max_days} days "
                  f"of history (requested {warmup_days} days warmup). Using today-anchored fetch.")
        else:
            pass  # warmup_from_dt already set above

        fetch_from_date = warmup_from_dt.strftime('%Y-%m-%d')
        print(f"[FetchCandles] Fetching {req.resolution}m from {fetch_from_date} to {req.to_date} "
              f"(warmup_days={warmup_days})")

        df = client.fetch_data(clean_symbol, fetch_from_date, req.to_date, interval=req.resolution)
        
        # FALLBACK LOGIC: If explicit fetch returned empty (likely due to invalid/old date range),
        # automatically fetch the *latest* available data so the user sees something.
        if (df is None or df.empty) and req.data_source == 'yfinance':
            print(f"[Replay] Data empty for range {fetch_from_date} to {req.to_date}. Attempting fallback to latest available data...")
            
            # Define safe fallback duration based on resolution
            fallback_days = 5 # Default for 1m/4m
            if req.resolution in ['2', '5', '15', '30']: fallback_days = 55
            elif req.resolution in ['60', '240']: fallback_days = 700
            elif req.resolution in ['1D', 'D', 'W', 'M']: fallback_days = 365
            
            fallback_from = datetime.now() - timedelta(days=fallback_days)
            fallback_from_str = fallback_from.strftime('%Y-%m-%d')
            # Use current time as end date to ensure we get data
            fallback_to_str = datetime.now().strftime('%Y-%m-%d')
            
            print(f"[Replay] Fallback fetch: {fallback_from_str} to {fallback_to_str}")
            df = client.fetch_data(clean_symbol, fallback_from_str, fallback_to_str, interval=req.resolution)

        if df is None or df.empty:
            raise HTTPException(
                status_code=404, 
                detail=f"No data found for {req.symbol}. Resolution '{req.resolution}' on '{req.data_source}' might be limited (e.g. YFinance 1m is last 7 days only)."
            )
        
        # Convert to candlestick format
        candles = df[['timestamp', 'open', 'high', 'low', 'close']].copy()
        if 'volume' in df.columns:
            candles['volume'] = df['volume']
            
        candles_list = candles.to_dict(orient='records')
        
        # Rename timestamp to time
        for c in candles_list:
            c['time'] = c.pop('timestamp')
        
        # DETERMINE ACTUAL START DATE: Use the first candle's timestamp as the true start
        # This handles cases where YFinance clamped an old date to its maximum available data
        actual_start_timestamp = int(df['timestamp'].iloc[0]) if len(df) > 0 else int(datetime.now().timestamp())
        actual_start_date = datetime.fromtimestamp(actual_start_timestamp).strftime('%Y-%m-%d')
        
        # Only override if the clamped date differs from requested date (indicating YFinance limited the range)
        if req.from_date and req.data_source == 'yfinance':
            requested_dt = datetime.strptime(req.from_date, '%Y-%m-%d')
            requested_ts = int(requested_dt.timestamp())
            if actual_start_timestamp > requested_ts:
                print(f"[FetchCandles] YFinance clamped date: requested {req.from_date} ({requested_ts}) -> actual {actual_start_date} ({actual_start_timestamp})")
        
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

        # PROCESS STUDY for INITIAL MARKERS AND DRAWINGS
        initial_markers = []
        initial_drawings = []
        
        from strategies import is_study
        if is_study(req.strategy):
            print(f"[FetchCandles] Pre-calculating historical state for {req.strategy}")
            
            # Map request pivotSettings to study config format
            study_config = {}
            study_config['resolution'] = getattr(req, 'resolution', None)
            if req.pivotSettings:
                if 'leftBars' in req.pivotSettings: study_config['left_bars'] = req.pivotSettings['leftBars']
                if 'rightBars' in req.pivotSettings: study_config['right_bars'] = req.pivotSettings['rightBars']
                if 'showIntersectionLabels' in req.pivotSettings: study_config['show_intersection_labels'] = req.pivotSettings['showIntersectionLabels']
            
            if req.strategy == 'pivot_points_only':
                from study_tool.pivot_points_study import PivotPointsStudy
                study = PivotPointsStudy(config=study_config)
            elif req.strategy == 'angular_coverage':
                from study_tool.angular_coverage_study import AngularPriceCoverageStudy
                study = AngularPriceCoverageStudy(config=study_config)
            else:
                study = None
                
            if study and len(candles_list) > 0:
                try:
                    print(f"[FetchCandles] Initializing study state on {len(candles_list)} bars...")
                    
                    # Calculate the index corresponding to the "start" of the replay (end of lookback)
                    # We want the state just BEFORE the requested from_date
                    cutoff_index = -1
                    
                    # Ensure target_start_ts is available (it's calculated earlier in fetch_candles)
                    # If for some reason it's not, recalculate it
                    if 'target_start_ts' not in locals():
                         from_dt_temp = datetime.strptime(req.from_date, '%Y-%m-%d')
                         target_start_ts = int(from_dt_temp.replace(tzinfo=timezone.utc).timestamp()) if from_dt_temp.tzinfo is None else int(from_dt_temp.astimezone(timezone.utc).timestamp())

                    for i, c in enumerate(candles_list):
                        if c['time'] < target_start_ts:
                            cutoff_index = i
                        else:
                            # We found the first candle that is >= from_date
                            # So the previous one (cutoff_index) is the last lookback candle
                            break
                    
                    print(f"[FetchCandles] Replay Start: {req.from_date} ({target_start_ts}). Cutoff Index: {cutoff_index} (Last Lookback Bar)")
                    
                    # Only process if we have lookback data
                    if cutoff_index >= 0:
                         # Run the slow-path initialization for the lookback period only
                         final_result = study.process_bar(
                             candles=candles_list,
                             bar_index=cutoff_index,
                             state=None
                         )
                         
                         if final_result:
                             initial_markers = final_result.get('pivot_markers', [])
                             initial_drawings = final_result.get('drawings', [])
                             print(f"[FetchCandles] Generated {len(initial_markers)} initial markers and {len(initial_drawings)} initial drawings from lookback context")
                    else:
                        print("[FetchCandles] No lookback context found (cutoff_index=-1). Starting with empty state.")
                        initial_markers = []
                        initial_drawings = []

                except Exception as e:
                    print(f"[FetchCandles] Error precalculating history: {e}")
                    import traceback
                    traceback.print_exc()
        
        print(f"[Replay] Returning {len(candles_list)} candles, option_cache_ready: {option_cache_ready}, Initial Markers: {len(initial_markers)}")

        strategy_meta = None
        if is_study(req.strategy):
            strategy_meta = {
                "name": req.strategy,
                "display_name": "Angular Price Coverage" if req.strategy == "angular_coverage" else "Pivot Points Only",
                "is_study": True,
                "column_schema": [
                    {"key": "time", "label": "Time", "width": "140px", "format": "datetime"},
                    {"key": "strategy_data.fan", "label": "Fan", "width": "120px", "format": "text"},
                    {"key": "strategy_data.fraction", "label": "Fraction", "width": "70px", "format": "text"},
                    {"key": "type", "label": "Type", "width": "110px", "format": "text"},
                    {"key": "price", "label": "Price", "width": "80px", "format": "price"},
                    {"key": "details", "label": "Details", "width": "200px", "format": "text"},
                    {"key": "open", "label": "O", "width": "60px", "format": "price"},
                    {"key": "high", "label": "H", "width": "60px", "format": "price"},
                    {"key": "low", "label": "L", "width": "60px", "format": "price"},
                    {"key": "close", "label": "C", "width": "60px", "format": "price"},
                    {"key": "strategy_data.cluster", "label": "Cluster", "width": "70px", "format": "text"},
                    {"key": "strategy_data.zone", "label": "Zone", "width": "80px", "format": "text"},
                    {"key": "strategy_data.zoneExtremes", "label": "Zone Extremes", "width": "140px", "format": "text"},
                    {"key": "strategy_data.nextAngleLine", "label": "Next Angle Line", "width": "110px", "format": "text"},
                ],
                "filter_field": "strategy_data.fanIdentity",
                "filter_options": [],
            }

        return {
            "candles": candles_list,
            "option_cache_ready": option_cache_ready,
            "markers": initial_markers,
            "drawings": initial_drawings,
            "strategy_meta": strategy_meta,
            "actual_start_date": actual_start_date,
            "actual_start_timestamp": actual_start_timestamp
        }
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
        return {"type": "step_update", "signal": None, "drawings": [], "remove_drawings": [], "pivot_markers": [], "intersection_events": [], "indicator_series": None, "candle_pattern": None, "debug_info": None, "hypothesis_updates": [], "strategy_meta": None}


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
        # Resolve the definitive ratio to use
        study_config = {}
        study_config['resolution'] = getattr(req, 'resolution', None)
        study_config['symbol'] = getattr(req, 'symbol', None)
        
        # We attempt to auto-resolve dynamically purely on the backend if available
        # from the provided symbol and resolution, acting as the absolute source of truth.
        if hasattr(req, 'symbol') and req.symbol and hasattr(req, 'resolution') and req.resolution:
            try:
                study_config['scale_ratio'] = get_dynamic_scale_ratio(req.symbol, req.resolution, req.cycle_type, req.session_duration)
            except ValueError as e:
                print(f"[Study] Config error: {e}. Falling back to default.")
                study_config['scale_ratio'] = req.scale_ratio if req.scale_ratio and req.scale_ratio > 0 else 5.5
        elif req.scale_ratio is not None and req.scale_ratio > 0:
            study_config['scale_ratio'] = req.scale_ratio
        else:
            study_config['scale_ratio'] = 5.5
        
        # Pass configurable pivot settings if provided
        if req.left_bars is not None:
            study_config['left_bars'] = req.left_bars
        if req.right_bars is not None:
            study_config['right_bars'] = req.right_bars
        if req.show_intersection_labels is not None:
            study_config['show_intersection_labels'] = req.show_intersection_labels
            
        study_config['run_mode'] = 'replay'
            
        # OPTIMIZATION: Use cached state if available for sequential replay
        global _study_cache
        
        # Initialize cache if needed
        if '_study_cache' not in globals():
            _study_cache = {'index': -1, 'strategy': None, 'state': None}
            
        is_sequential = (
            _study_cache['strategy'] == req.strategy and 
            _study_cache['index'] == req.current_index - 1
        )
        
        # A new replay session is started if we go backwards in time, 
        # or if the cache was just initialized (index == -1)
        is_new_replay = _study_cache['index'] == -1 or _study_cache['index'] >= req.current_index
        
        study_config['is_new_replay'] = is_new_replay

        # Truncate replay_events.csv on new replay session
        if is_new_replay:
            _truncate_replay_events_csv()
            print(f"[Replay] New session detected — replay_events.csv truncated")

        if req.strategy == 'pivot_points_only':
            from study_tool.pivot_points_study import PivotPointsStudy
            study = PivotPointsStudy(config=study_config)
            print(f"[Study] Evaluating PivotPointsStudy (config: {study_config})")
        else:
            from study_tool.angular_coverage_study import AngularPriceCoverageStudy
            study = AngularPriceCoverageStudy(config=study_config)
            print(f"[Study] Evaluating AngularPriceCoverageStudy (config: {study_config})")
        
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
        
        output_drawings = []
        output_pivots = []
        output_remove = []
        output_intersection_events = []
        output_candle_pattern = None

        if is_sequential and _study_cache['state']:
            # FAST PATH: Restore state and process single bar
            print(f"[Study] FAST PATH at index {req.current_index}")
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
            output_intersection_events = result.get('intersection_events', [])
            output_candle_pattern = result.get('candle_pattern')
            if output_intersection_events:
                print(f"[Study] Index {req.current_index}: Returning {len(output_intersection_events)} events")
                for evt in output_intersection_events[:5]:  # Log first 5
                    print(f"  - {evt.get('type')}: {evt.get('fraction')} @ {evt.get('price')} | fan={evt.get('fan')}")
                for evt in output_intersection_events:
                    _write_replay_event_to_csv(evt)
                
            # Update cache
            _study_cache['index'] = req.current_index
            _study_cache['state'] = result['state']
            print(f"[Study] Cache updated: index={req.current_index}, state_keys={list(result['state'].keys())}")
            
        else:
            # SLOW PATH: Full rebuild (first run or reset)
            print(f"[Study] SLOW PATH: Rebuilding from 0 to {req.current_index}")
            _study_cache = {'index': -1, 'strategy': req.strategy, 'state': None}
            
            # NO SPECIAL CORPUS HANDLING HERE.
            # Warmup is already computed correctly in fetch_candles using the
            # from_date-anchored WARMUP_DAYS strategy. initialize_history() will
            # process all available warmup bars correctly.
            
            # Final call for the requested bar
            final_result = study.process_bar(
                candles=candles,
                bar_index=req.current_index,
                state=None
            )
            
            if final_result:
                output_pivots.extend(final_result.get('pivot_markers', []))
                output_drawings.extend(final_result.get('drawings', []))
                output_remove.extend(final_result.get('remove_drawings', []))
                output_intersection_events.extend(final_result.get('intersection_events', []))
                output_candle_pattern = final_result.get('candle_pattern')
                if output_intersection_events:
                    print(f"[Study] SLOW PATH Index {req.current_index}: Returning {len(output_intersection_events)} events")
                    for evt in output_intersection_events[:10]:  # Log first 10
                        print(f"  - {evt.get('type')}: {evt.get('fraction')} @ {evt.get('price')} | fan={evt.get('fan')}")
                    for evt in output_intersection_events:
                        _write_replay_event_to_csv(evt)
            print(f"[Study] Index {req.current_index}: Added {len(output_pivots)} pivot markers from study")
            
            # Update cache after full run
            _study_cache['index'] = req.current_index
            _study_cache['state'] = study.get_state()
            
            # Note: _sync_fans in the study handles all drawing creation/removal.
            # No need for a separate snapshot here.

        # Add debug info for frontend console
        debug_info = {}
        if hasattr(study, 'stacks') and study.stacks:
            debug_info = {
                'context': study.stacks.context,
                'anchor': study.stacks.anchor,
                'inner_stack_count': len(study.stacks.inner_stack),
                'outer_stack_count': len(study.stacks.outer_stack),
                'inner_stack': study.stacks.inner_stack,
                'outer_stack': study.stacks.outer_stack,
                'total_confirmed_pivots': len(study.pivot_detector.confirmed_pivots),
                'left_bars': study.config.get('left_bars', 5),
                'right_bars': study.config.get('right_bars', 5)
            }
        
        # Wrap intersection_events: move angle-specific fields into strategy_data
        wrapped_events = []
        for evt in output_intersection_events:
            wrapped_events.append({
                "time": evt.get("time", 0),
                "price": evt.get("price", 0),
                "type": evt.get("type", ""),
                "details": evt.get("details", ""),
                "open": evt.get("open", 0),
                "high": evt.get("high", 0),
                "low": evt.get("low", 0),
                "close": evt.get("close", 0),
                "strategy_data": {
                    "fan": evt.get("fan", ""),
                    "fanIdentity": evt.get("fanIdentity", evt.get("fan", "")),
                    "fraction": evt.get("fraction", ""),
                    "activeAngles": evt.get("activeAngles", {}),
                    "zone": evt.get("zone", ""),
                    "zoneExtremes": evt.get("zoneExtremes", {}),
                    "nextAngleLine": evt.get("nextAngleLine", ""),
                    "cluster": evt.get("cluster", False),
                    "bar_index": evt.get("bar_index", 0),
                }
            })

        study_meta = {
            "name": "angular_coverage",
            "display_name": "Angular Price Coverage",
            "is_study": True,
            "column_schema": [
                {"key": "time",                          "label": "Time",            "width": "140px", "format": "datetime"},
                {"key": "strategy_data.fan",             "label": "Fan",             "width": "120px", "format": "text"},
                {"key": "strategy_data.fraction",        "label": "Fraction",        "width": "70px",  "format": "text"},
                {"key": "type",                          "label": "Type",            "width": "110px", "format": "text"},
                {"key": "price",                         "label": "Price",           "width": "80px",  "format": "price"},
                {"key": "details",                       "label": "Details",         "width": "200px", "format": "text"},
                {"key": "open",                          "label": "O",               "width": "60px",  "format": "price"},
                {"key": "high",                          "label": "H",               "width": "60px",  "format": "price"},
                {"key": "low",                           "label": "L",               "width": "60px",  "format": "price"},
                {"key": "close",                         "label": "C",               "width": "60px",  "format": "price"},
                {"key": "strategy_data.cluster",         "label": "Cluster",         "width": "70px",  "format": "text"},
                {"key": "strategy_data.zone",            "label": "Zone",            "width": "80px",  "format": "text"},
                {"key": "strategy_data.zoneExtremes",    "label": "Zone Extremes",   "width": "140px", "format": "text"},
                {"key": "strategy_data.nextAngleLine",   "label": "Next Angle Line", "width": "110px", "format": "text"},
            ],
            "filter_field": "strategy_data.fanIdentity",
            "filter_options": [],
        }

        return {
            "type": "step_update",
            "signal": None,
            "drawings": output_drawings,
            "pivot_markers": output_pivots,
            "remove_drawings": output_remove,
            "intersection_events": wrapped_events,
            "indicator_series": None,
            "candle_pattern": output_candle_pattern,
            "debug_info": debug_info,
            "hypothesis_updates": [],
            "strategy_meta": study_meta,
        }
        
    except Exception as e:
        import traceback
        print(f"[Study] Error processing bar: {e}")
        traceback.print_exc()
        return {"type": "step_update", "signal": None, "drawings": [], "remove_drawings": [], "pivot_markers": [], "intersection_events": [], "indicator_series": None, "candle_pattern": None, "debug_info": None, "hypothesis_updates": [], "strategy_meta": None}







async def _process_strategy_bar(req: EvaluateStrategyRequest):
    """Process a single bar for trading strategies (returns signals)"""
    global _replay_positions
    
    indicator_series = None
    
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
            return {"type": "step_update", "signal": None, "drawings": [], "remove_drawings": [], "pivot_markers": [], "intersection_events": [], "indicator_series": indicator_series, "candle_pattern": None, "debug_info": None, "hypothesis_updates": [], "strategy_meta": None}
        
        # Ensure numeric types
        for col in ['open', 'high', 'low', 'close']:
            df[col] = pd.to_numeric(df[col])
        
        # UNIFIED STRATEGY LOGIC: Use the SAME strategies.py as /run_backtest
        try:
            from strategies import get_strategy
            from base_strategy import SignalType
            
            strategy = get_strategy(req.strategy, df)
            signals_df = strategy.generate_signals()
            
            indicator_series = None
            if hasattr(strategy, 'get_indicator_series'):
                indicator_series = strategy.get_indicator_series()
            
        except Exception as strategy_error:
            print(f"[Strategy] Strategy error: {strategy_error}")
            import traceback
            traceback.print_exc()
            return {"type": "step_update", "signal": None, "drawings": [], "remove_drawings": [], "pivot_markers": [], "intersection_events": [], "indicator_series": indicator_series, "candle_pattern": None, "debug_info": None, "hypothesis_updates": [], "strategy_meta": None}
        
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

        # Extract interaction events from strategy
        interaction_events = []
        try:
            if hasattr(strategy, 'extract_events'):
                interaction_events = strategy.extract_events(signals_df, req.current_index)
        except Exception as evt_err:
            print(f"[Strategy] Error extracting events: {evt_err}")

        # Build strategy_meta
        strategy_meta = None
        try:
            if hasattr(strategy, 'get_strategy_meta'):
                strategy_meta = strategy.get_strategy_meta()
        except Exception as meta_err:
            print(f"[Strategy] Error getting meta: {meta_err}")

        return {
            "type": "step_update",
            "signal": current_trade,
            "drawings": indicator_drawings,
            "remove_drawings": [],
            "pivot_markers": [],
            "intersection_events": interaction_events,
            "indicator_series": indicator_series,
            "candle_pattern": None,
            "debug_info": None,
            "hypothesis_updates": [],
            "strategy_meta": strategy_meta
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"type": "step_update", "signal": None, "drawings": [], "remove_drawings": [], "pivot_markers": [], "intersection_events": [], "indicator_series": indicator_series, "candle_pattern": None, "debug_info": None, "hypothesis_updates": [], "strategy_meta": None}


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


        # NEW ARCHITECTURE: Handle Studies vs Strategies
        from strategies import is_study
        
        drawings = []
        markers = []
        indicator_series = None
        filtered_trades = []
        
        if is_study(req.strategy):
            print(f"Running STUDY backtest: {req.strategy}")
            # Instantiate Study
            study_config = {
                'left_bars': 5, # Default
                'right_bars': 5,
                'resolution': getattr(req, 'resolution', None)
            }
            
            if getattr(req, 'pivotSettings', None):
                if 'leftBars' in req.pivotSettings:
                    study_config['left_bars'] = req.pivotSettings['leftBars']
                if 'rightBars' in req.pivotSettings:
                    study_config['right_bars'] = req.pivotSettings['rightBars']
                if 'showIntersectionLabels' in req.pivotSettings:
                    study_config['show_intersection_labels'] = req.pivotSettings['showIntersectionLabels']

            if req.strategy == 'pivot_points_only':
                from study_tool.pivot_points_study import PivotPointsStudy
                study = PivotPointsStudy(config=study_config)
            else:
                from study_tool.angular_coverage_study import AngularPriceCoverageStudy
                study = AngularPriceCoverageStudy(config=study_config)
            
            # Prepare candles for study
            # Study expects dicts: {'time', 'open', 'high', 'low', 'close'}
            # Chart data already has 'time' (from pop timestamp) but we are before that conversion in the flow 
            # We must use df which has 'timestamp'
            study_candles = []
            records = df.to_dict('records')
            for r in records:
                study_candles.append({
                    'time': int(r['timestamp']),
                    'open': float(r['open']),
                    'high': float(r['high']),
                    'low': float(r['low']),
                    'close': float(r['close']),
                    'volume': float(r.get('volume', 0))
                })
            
            # Run Study (Full History Scan)
            # Both studies support some form of history init
            if hasattr(study, 'initialize_history'):
                 study.initialize_history(study_candles)
            elif hasattr(study, '_initialize_history'):
                 # For PivotPointsStudy, we can force a scan
                 study._initialize_history(study_candles, len(study_candles))

            # Extract Markers/Drawings
            # 1. Pivot Markers
            if hasattr(study, 'pivot_detector'):
                 for p in study.pivot_detector.confirmed_pivots:
                     # Add markers
                     marker_type = 'pivot_high' if p.pivot_type == 'high' else 'pivot_low'
                     color = '#26a69a' if p.pivot_type == 'high' else '#ef5350'
                     shape = 'arrow_down' if p.pivot_type == 'high' else 'arrow_up'
                     
                     markers.append({
                        'id': f"{marker_type}_{p.time}",
                        'type': marker_type,
                        'time': p.time,
                        'price': p.price,
                        'bar_index': p.bar_index,
                        'text': '',
                        'color': color,
                        'shape': shape
                     })
                     
            # 2. Fan Drawings (Angular Study Only)
            if hasattr(study, 'angle_engine') and req.strategy != 'pivot_points_only':
                 # Angular study needs a different extraction method usually done via process_bar
                 # For "Instant" results, we might need to rely on what initialize_history set up, 
                 # or run a quick loop if stacks were created.
                 # initialize_history in AngularStudy sets up `self.stacks`.
                 # We can use that to draw the *current* state (last active fans).
                 if study.stacks:
                      # This is a simplification: it only draws the state at the END of history
                      # Ideally "Backtest" for a visual study means "show me the final result"
                      pass 

        else:
            # STRATEGY Execution (Trades)
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
                
                # Extract indicator series for chart rendering (e.g., EMA lines)
                indicator_series = None
                if hasattr(strategy, 'get_indicator_series'):
                    indicator_series = strategy.get_indicator_series()
                
                # Create backtesting engine (handles position management and P&L)
                backtest_engine = BacktestEngine(strategy)
                
                # Run backtest
                result = backtest_engine.run(symbol=req.symbol)
                
                # Convert trades to old format for frontend compatibility
                trades = [t.to_dict() for t in result.trades]
                
                print(f"NEW ENGINE: Backtest completed - {result.metrics['total_trades']} trades, P&L: {result.metrics['total_pnl']}")
                
                # Filter Trades by Date
                # CRITICAL FIX: Use IST timezone since Dhan data is in IST
                ist = pytz.timezone('Asia/Kolkata')
                from_dt = ist.localize(datetime.strptime(req.from_date, "%Y-%m-%d"))
                from_ts = int(from_dt.timestamp())
                to_dt = ist.localize(datetime.strptime(req.to_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59))
                to_ts = int(to_dt.timestamp())
                
                filtered_trades = [
                    t for t in trades 
                    if from_ts <= int(t['time']) <= to_ts
                ]
                
            except Exception as strategy_error:
                print(f"CRITICAL: Strategy Execution Failed: {strategy_error}")
                import traceback
                traceback.print_exc()
                # STRICT MODE: Do not fallback. Fail the request.
                raise HTTPException(status_code=500, detail=str(strategy_error))
        
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
        
        # Filter Markers (for studies)
        filtered_markers = [
            m for m in markers
            if from_ts <= int(m['time']) <= to_ts
        ]
        
        print(f"Backtest Filtering: {len(chart_data_list)} -> {len(filtered_candles)} bars, {len(filtered_trades)} trades, {len(filtered_markers)} markers (Range: {req.from_date} to {req.to_date})")

        return {
            "candles": filtered_candles,
            "trades": filtered_trades,
            "markers": filtered_markers,
            "drawings": drawings,
            "strategy": req.strategy,
            "symbol": req.symbol,
            "indicator_series": indicator_series,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Backend Error: {str(e)}")

# --- Hypothesis Navigator Endpoints ---

@app.get("/api/hypothesis-reports")
def list_hypothesis_reports():
    """List available hypothesis event JSON files from runs directory."""
    import glob
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    runs_base = os.path.join(repo_root, "logs", "backend", "runs")
    files = []
    for pattern in [
        os.path.join(runs_base, "**", "hypothesis_events.json"),
        os.path.join(runs_base, "**", "hypothesis_reports", "**", "*_report.json"),
        os.path.join(runs_base, "**", "analysis", "hypotheses", "*.json"),
    ]:
        files.extend(glob.glob(pattern, recursive=True))
    reports = []
    for f in sorted(files, reverse=True):
        rel = os.path.relpath(f, runs_base).replace("\\", "/")
        parts = rel.split("/")
        is_per_hypothesis = "hypothesis_reports" in parts or "analysis" in parts
        is_run_summary = parts[-1] == "run_summary.json"
        symbol = parts[0] if len(parts) >= 1 else ""
        # Restore ^ prefix sanitized to _ by Windows-safe path encoding
        if symbol.startswith("_") and len(symbol) > 1 and symbol[1].isalpha():
            symbol = "^" + symbol[1:]
        resolution = parts[1] if len(parts) >= 2 else ""
        run_id = parts[2] if len(parts) >= 3 else ""
        filename = parts[-1]
        if filename == "hypothesis_events.json":
            report_name = "All Events"
        elif is_run_summary:
            report_name = "Run Summary"
        else:
            report_name = filename.replace("_report.json", "").replace(".json", "").replace("_", " ").title()
        try:
            mtime = os.path.getmtime(f)
        except OSError:
            mtime = 0
        reports.append({
            "path": rel,
            "symbol": symbol,
            "resolution": resolution,
            "run_id": run_id,
            "report_name": report_name,
            "is_per_hypothesis": is_per_hypothesis,
            "is_run_summary": is_run_summary,
            "modified": mtime,
        })
    return {"reports": reports}


def _coerce_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_fraction_value(value):
    if value is None:
        return ""
    text = str(value).strip()
    if text in {"", "-", "nan", "None"}:
        return ""
    return text


def _normalize_event_type(value):
    return str(value or "").strip().upper()


def _sanitize_for_json(obj):
    """Recursively replace NaN/Infinity values (including numpy) with None for JSON compliance."""
    import math

    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]

    # Handle float-like types (standard float AND numpy float64/float32 etc.)
    try:
        f = float(obj)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        pass

    return obj


def _build_hypothesis_event_lookup(run_dir):
    events_csv_path = os.path.join(run_dir, "events.csv")
    if not os.path.exists(events_csv_path):
        return {}

    try:
        events_df = pd.read_csv(events_csv_path)
    except Exception:
        return {}

    lookup = {}
    for row in events_df.to_dict(orient="records"):
        timestamp = row.get("Raw_Timestamp")
        if pd.isna(timestamp) or timestamp in (None, ""):
            continue

        try:
            timestamp = int(timestamp)
        except (TypeError, ValueError):
            continue

        event_type = _normalize_event_type(row.get("Type"))
        fraction = _normalize_fraction_value(row.get("Fraction"))
        price = _coerce_float(row.get("Price"))
        rounded_price = round(price, 4) if price is not None else None

        keys = [
            (timestamp, event_type, rounded_price, fraction),
            (timestamp, event_type, rounded_price, ""),
            (timestamp, event_type, None, fraction),
            (timestamp, event_type, None, ""),
        ]
        for key in keys:
            if key not in lookup:
                lookup[key] = row

    return lookup


def _enrich_hypothesis_events_payload(payload, run_dir):
    """Enrich old run-level hypothesis_events.json with all descriptive fields from events.csv."""

    # Human-readable display names for event types (mirrored from event_logger.py)
    _EVENT_TYPE_DISPLAY: dict = {
        "CROSS_UP": "Cross Up (Bullish)",
        "CROSS_DOWN": "Cross Down (Bearish)",
        "GAP_CROSS_UP": "Gap Cross Up (Bullish)",
        "GAP_CROSS_DOWN": "Gap Cross Down (Bearish)",
        "SUPPORT_TEST": "Support Test",
        "RESISTANCE_TEST": "Resistance Test",
        "SUPPORT_BOUNCE": "Support Bounce",
        "RESISTANCE_REJECTION": "Resistance Rejection",
        "BREACH_CONFIRMED": "Breach Confirmed",
        "BREACH_CONFIRMED_NO_ALPHA": "Breach Confirmed (No Alpha)",
        "REST_ON_ANGLE": "Rest on Angle",
        "TARGET_HIT": "Target Hit",
        "TARGET_FAILED": "Target Failed",
        "FAN_VALIDATED": "Fan Validated (7/8)",
        "ZONE_CHANGE": "Zone Change",
        "FAN_DEACTIVATED": "Fan Deactivated",
        "breach_confirmed": "Breach Confirmed",
        "target_hit": "Target Hit",
        "target_failed": "Target Failed",
        "fan_validated": "Fan Validated (7/8)",
        "zone_change": "Zone Change",
    }

    events = payload.get("events")
    if not isinstance(events, list) or not events:
        return payload

    lookup = _build_hypothesis_event_lookup(run_dir)
    if not lookup:
        return payload

    enriched_events = []
    for event in events:
        timestamp = event.get("timestamp")
        event_type = _normalize_event_type(event.get("event_type") or event.get("type"))
        fraction = _normalize_fraction_value(event.get("fraction"))
        price = _coerce_float(event.get("price") if event.get("price") is not None else event.get("target_price"))
        rounded_price = round(price, 4) if price is not None else None

        row = None
        for key in [
            (timestamp, event_type, rounded_price, fraction),
            (timestamp, event_type, rounded_price, ""),
            (timestamp, event_type, None, fraction),
            (timestamp, event_type, None, ""),
        ]:
            row = lookup.get(key)
            if row:
                break

        if row:
            # Fan label
            fan_label = str(row.get("Fan", "") or "").strip()
            if fan_label:
                event["fan_display"] = fan_label
                event["fan_identity"] = fan_label

            # Fraction
            if event.get("fraction") in (None, "", "-"):
                csv_fraction = _normalize_fraction_value(row.get("Fraction"))
                if csv_fraction:
                    event["fraction"] = csv_fraction

            # Event type display name (already human-readable from CSV)
            csv_type = str(row.get("Type", "") or "").strip()
            if csv_type and not event.get("event_type_display"):
                event["event_type_display"] = csv_type

            # Description / Details
            csv_details = str(row.get("Details", "") or "").strip()
            if csv_details and not event.get("description"):
                event["description"] = csv_details

            # Direction
            csv_direction = str(row.get("Direction", "") or "").strip()
            if csv_direction and not event.get("direction"):
                event["direction"] = csv_direction

            # OHLC
            for col, key in [("Open", "open"), ("High", "high"), ("Low", "low"), ("Close", "close")]:
                val = _coerce_float(row.get(col))
                if val is not None and event.get(key) is None:
                    event[key] = val

            # Zone and cluster
            csv_zone = str(row.get("Zone", "") or "").strip()
            if csv_zone and not event.get("current_zone"):
                event["current_zone"] = csv_zone

            csv_cluster = row.get("Cluster")
            if csv_cluster is not None and event.get("cluster_state") is None:
                event["cluster_state"] = bool(csv_cluster) if not isinstance(csv_cluster, bool) else csv_cluster

            # Next angle line
            csv_next = str(row.get("Next_Angle_Line", "") or "").strip()
            if csv_next and not event.get("next_angle_line"):
                event["next_angle_line"] = csv_next

            # MFE/MAE horizons
            for col, key in [
                ("MFE_5", "mfe_5"), ("MAE_5", "mae_5"),
                ("MFE_10", "mfe_10"), ("MAE_10", "mae_10"),
                ("MFE_20", "mfe_20"), ("MAE_20", "mae_20"),
                ("MFE_50", "mfe_50"), ("MAE_50", "mae_50"),
            ]:
                val = _coerce_float(row.get(col))
                if val is not None and event.get(key) is None:
                    event[key] = abs(val)  # MFE/MAE should be positive

            # Excursions
            for col, key in [("Exc_Up_10", "exc_up_10"), ("Exc_Down_10", "exc_down_10")]:
                val = _coerce_float(row.get(col))
                if val is not None and event.get(key) is None:
                    event[key] = abs(val)

            # Reversal outcome
            csv_rev = str(row.get("Reversal_Outcome", "") or "").strip()
            if csv_rev and not event.get("reversal_outcome"):
                event["reversal_outcome"] = csv_rev

            # Geometry context
            for col, key in [
                ("anchor_bar_index", "anchor_bar_index"),
                ("scale_ratio", "scale_ratio"),
                ("anchor_price", "anchor_price"),
                ("origin_bar_index", "origin_bar_index"),
                ("origin_price", "origin_price"),
            ]:
                if col in ("anchor_price", "origin_price", "scale_ratio"):
                    val = _coerce_float(row.get(col))
                else:
                    val = row.get(col)
                    try:
                        val = int(float(val)) if val not in (None, "", "-") else None
                    except (TypeError, ValueError):
                        val = None
                if val is not None and event.get(key) is None:
                    event[key] = val

            # Instrument
            csv_instr = str(row.get("Instrument", "") or "").strip()
            if csv_instr and not event.get("instrument"):
                event["instrument"] = csv_instr

            # Timeframe
            csv_tf = str(row.get("Timeframe", "") or "").strip()
            if csv_tf and not event.get("timeframe"):
                event["timeframe"] = csv_tf

            # is_retro
            is_retro_val = row.get("is_retro")
            if is_retro_val is not None and not event.get("is_retro"):
                event["is_retro"] = is_retro_val if isinstance(is_retro_val, bool) else str(is_retro_val).strip().lower() == "true"

            # Bar index
            bar_index_val = row.get("Bar_Index")
            if bar_index_val is not None and bar_index_val != "" and not event.get("bar_index"):
                try:
                    event["bar_index"] = int(float(bar_index_val))
                except (TypeError, ValueError):
                    pass

            # Bars in zone
            biz_val = row.get("Bars_In_Zone")
            if biz_val is not None and biz_val != "" and not event.get("bars_in_zone"):
                try:
                    event["bars_in_zone"] = int(float(biz_val))
                except (TypeError, ValueError):
                    pass

            # Is gap cross
            igc_val = row.get("Is_Gap_Cross")
            if igc_val is not None and not event.get("is_gap_cross"):
                event["is_gap_cross"] = igc_val if isinstance(igc_val, bool) else str(igc_val).strip().lower() == "true"

            # Anchor type
            at_val = str(row.get("Anchor_Type", "") or "").strip()
            if at_val and not event.get("anchor_type"):
                event["anchor_type"] = at_val

            # Priority label
            pl_val = str(row.get("Priority_Label", "") or "").strip()
            if pl_val and not event.get("priority_label"):
                event["priority_label"] = pl_val

        # Compute event_type_display from event_type if not present
        if not event.get("event_type_display"):
            raw_type = event.get("event_type") or ""
            event["event_type_display"] = _EVENT_TYPE_DISPLAY.get(raw_type, raw_type)

        enriched_events.append(event)

    return _sanitize_for_json({
        **payload,
        "events": enriched_events,
    })


def _transform_per_hypothesis_payload(payload: dict, run_dir: str = None) -> dict:
    """Transform per-hypothesis JSON into frontend-compatible format.

    Enriches sparse detailed_log events by cross-referencing with hypothesis_events.json
    to fill in fan_geometry, event_type, direction, zone, and other contextual fields.
    """
    transformed = {}

    # Pass through metadata
    for key in ("hypothesis_name", "description", "in_sample", "walk_forward", "groups",
                "rsi_series", "line_timeline", "skipped"):
        if key in payload:
            transformed[key] = payload[key]

    # For run_summary.json (no detailed_log, has hypotheses array), pass through as-is
    if "hypotheses" in payload:
        transformed["hypotheses"] = payload["hypotheses"]

    # Enrich detailed_log -> events
    if "detailed_log" in payload and run_dir:
        transformed["events"] = enrich_detailed_log(payload["detailed_log"], run_dir)
    elif "detailed_log" in payload:
        transformed["events"] = payload["detailed_log"]

    return transformed


def _extract_fan_identity(fan_label: str) -> str:
    """Extract fan identity like 'H64-L57' from label like 'P1 (H64-L57)'."""
    if not fan_label:
        return ""
    label = str(fan_label).strip()
    # Pattern: "P1 (H64-L57)" or just "H64-L57"
    import re
    match = re.search(r'([HL]\d+-[HL]\d+)', label)
    return match.group(1) if match else label


def _parse_detailed_log_time(time_str: str) -> int:
    """Parse detailed_log time string to epoch timestamp (UTC)."""
    if not time_str:
        return 0
    try:
        from datetime import datetime, timezone
        # Format: "4/1/2025, 1:32:00 PM" -- these are UTC timestamps
        clean = str(time_str).replace(',', '')
        dt = datetime.strptime(clean, '%m/%d/%Y %I:%M:%S %p')
        dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (ValueError, OSError):
        return 0


def _build_hypothesis_lookup(run_dir: str) -> dict:
    """Build lookup from hypothesis_events.json keyed by (timestamp, fan_identity, fraction_str)."""
    import os as _os
    hypo_path = _os.path.join(run_dir, "hypothesis_events.json")
    if not _os.path.exists(hypo_path):
        return {}

    with open(hypo_path, "r", encoding="utf-8") as f:
        hypo_data = json.load(f)

    lookup = {}
    events = hypo_data.get("events", []) or hypo_data.get("live_events", []) or []
    for evt in events:
        ts = evt.get("timestamp", 0)
        fi = (evt.get("fan_identity") or evt.get("fan_display") or "")
        frac = str(evt.get("fraction", ""))
        key = (ts, fi, frac)
        # Keep first match; prefer earlier bar_index
        if key not in lookup:
            lookup[key] = evt

    return lookup


def _enrich_detailed_log(detailed_log: list, run_dir: str) -> list:
    """Enrich detailed_log entries with data from hypothesis_events.json."""
    lookup = _build_hypothesis_lookup(run_dir)
    enriched = []

    for i, entry in enumerate(detailed_log):
        ts = _parse_detailed_log_time(entry.get("time", ""))
        fan_id = _extract_fan_identity(entry.get("fan", ""))
        frac = str(entry.get("fraction", ""))

        # Try matching by timestamp+fan+fraction, fallback by fan+fraction only
        match = lookup.get((ts, fan_id, frac))
        if not match:
            # Fallback: match by fan + fraction only (ignore timestamp)
            for (k_ts, k_fi, k_fr), v in lookup.items():
                if k_fi == fan_id and k_fr == frac:
                    match = v
                    break

        enriched_entry = {
            "event_id": i + 1,
            # Fields from detailed_log (keep as primary)
            "event_type": entry.get("type", ""),  # Use detailed_log type, not matched event_type
            "time": entry.get("time", ""),
            "test_time": entry.get("test_time", ""),
            "fan": entry.get("fan", ""),
            "fraction": entry.get("fraction", ""),
            "type": entry.get("type", ""),
            "price": entry.get("price"),
            "is_retro": entry.get("is_retro", False),
            "outcome": entry.get("outcome"),
            "mfe": entry.get("mfe"),
            "mae": entry.get("mae"),
            "anchor_bar_index": entry.get("anchor_bar_index"),
            "scale_ratio": entry.get("scale_ratio"),
            "anchor_price": entry.get("anchor_price"),
            "details": entry.get("details", ""),  # e.g., "Bounced (T+2 bars)"
            "confirmation_details": entry.get("confirmation_details") or entry.get("details", ""),
            # Trade simulation fields from exit optimizer
            "entry_price": entry.get("entry_price"),
            "entry_time": entry.get("entry_time", ""),
            "exit_price": entry.get("exit_price"),
            "exit_time": entry.get("exit_time", ""),
            "exit_reason": entry.get("exit_reason"),
            "exit_label": entry.get("exit_label", ""),
            "net_pnl": entry.get("net_pnl"),
            "pnl_pct": entry.get("pnl_pct"),
            "bars_held": entry.get("bars_held"),
            "entry_side": entry.get("entry_side"),
        }

        # Enrich from matched hypothesis event — only geometry/context, not type override
        _TYPE_DISPLAY = {
            "SUPPORT_BOUNCE": "Support Bounce",
            "RESISTANCE_REJECTION": "Resistance Rejection",
            "SUPPORT_TEST": "Support Test",
            "RESISTANCE_TEST": "Resistance Test",
            "BREACH_CONFIRMED": "Breach Confirmed",
            "TARGET_HIT": "Target Hit",
            "TARGET_FAILED": "Target Failed",
            "FAN_VALIDATED": "Fan Validated",
        }
        enriched_entry["event_type_display"] = _TYPE_DISPLAY.get(entry.get("type", ""), entry.get("type", ""))

        if match:
            enriched_entry["direction"] = match.get("direction")
            enriched_entry["fan_geometry"] = match.get("fan_geometry")
            enriched_entry["fan_identity"] = match.get("fan_identity") or fan_id
            enriched_entry["fan_display"] = match.get("fan_display") or entry.get("fan", "")
            enriched_entry["priority_label"] = match.get("priority_label", "")
            enriched_entry["description"] = match.get("description", "")
            enriched_entry["current_zone"] = match.get("current_zone")
            enriched_entry["bars_in_zone"] = match.get("bars_in_zone")
            enriched_entry["is_gap_cross"] = match.get("is_gap_cross", False)
            enriched_entry["anchor_type"] = match.get("anchor_type")
            enriched_entry["bar_index"] = match.get("bar_index")
            enriched_entry["timestamp"] = match.get("timestamp", ts)
        else:
            enriched_entry["timestamp"] = ts

        # Preserve strategy-specific custom fields not in the base whitelist
        _base_keys = set(enriched_entry.keys())
        for k, v in entry.items():
            if k not in _base_keys and v is not None:
                enriched_entry[k] = v

        enriched.append(enriched_entry)

    return enriched


@app.get("/api/hypothesis-reports/{path:path}")
def get_hypothesis_report(path: str):
    """Serve a specific hypothesis events JSON file."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    file_path = os.path.join(repo_root, "logs", "backend", "runs", path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read report: {exc}") from exc

    if "analysis" in path and "hypotheses" in path:
        # Extract run_dir: path is like "BTCUSDT/4/run_id/analysis/hypotheses/file.json"
        run_dir = os.path.join(repo_root, "logs", "backend", "runs", *path.split("/")[:3])
        payload = _transform_per_hypothesis_payload(payload, run_dir)
    elif os.path.basename(file_path) == "hypothesis_events.json":
        run_dir = os.path.dirname(file_path)
        payload = _enrich_hypothesis_events_payload(payload, run_dir)

    # Clean any NaN/Infinity from pandas before serializing
    payload = _sanitize_for_json(payload)
    body = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False)
    return Response(content=body, media_type="application/json")


def _infer_hypothesis_run_source(run_dir) -> str:
    log_path = run_dir / "simulation_run.log"
    if not log_path.exists():
        return "yfinance"

    try:
        with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
            contents = handle.read()
    except OSError:
        return "yfinance"

    for pattern in [
        r"Loaded\s+\d+\s+candles\s+from\s+([a-zA-Z_]+)",
        r"using\s+([a-zA-Z_]+)\s+with",
    ]:
        match = re.search(pattern, contents)
        if match:
            return match.group(1).lower()
    return "yfinance"


@app.get("/api/hypothesis-runs/{symbol}/{resolution}/{run_id}/candles")
def get_hypothesis_run_candles(symbol: str, resolution: str, run_id: str):
    """Return candles for a specific hypothesis run as JSON for the frontend chart."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    runs_base = os.path.join(repo_root, "logs", "backend", "runs")
    run_dir = build_run_dir(runs_base, symbol, resolution, run_id)
    candles_path = run_dir / "candles.csv"

    if not candles_path.exists():
        raise HTTPException(status_code=404, detail="Run candles not found")

    try:
        candles_df = pd.read_csv(candles_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read run candles: {exc}") from exc

    candles = []
    for row in candles_df.to_dict(orient="records"):
        bar_time = row.get("time", row.get("timestamp"))
        candles.append({
            "time": int(bar_time),
            "open": float(row.get("open", 0.0)),
            "high": float(row.get("high", 0.0)),
            "low": float(row.get("low", 0.0)),
            "close": float(row.get("close", 0.0)),
            "volume": float(row.get("volume", 0.0)),
            "bar_index": int(row["bar_index"]) if row.get("bar_index") is not None else None,
        })

    return {
        "symbol": symbol,
        "resolution": resolution,
        "run_id": run_id,
        "data_source": _infer_hypothesis_run_source(run_dir),
        "candles": candles,
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8005, reload=True)
