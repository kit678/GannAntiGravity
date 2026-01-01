from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import pandas as pd
from dhan_client import DhanClient
from gann_logic import GannStrategyEngine
import time
from datetime import datetime, timedelta
import pytz

app = FastAPI()
print("--- BACKEND RESTART v3 - REGEX CORS ---")

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

@app.get("/")
def read_root():
    return {"status": "Gann Backend Online"}

# --- UDF (Universal Data Feed) Endpoints for TradingView Advanced Charts ---

@app.get("/config")
def udf_config():
    return {
        "supported_resolutions": ["1", "5", "15", "60", "D", "W"],
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
            {"name": "Options", "value": "options"},
        ],
    }

@app.get("/search")
def udf_search(query: str, type: str, exchange: str, limit: int):
    results = []
    
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
                if sym in ["NIFTY 50", "NIFTY OPTIONS"]: continue # Skip dupes
                
                results.append({
                    "symbol": sym, # displayed symbol
                    "full_name": sym, 
                    "description": row.get('SEM_CUSTOM_SYMBOL', sym),
                    "exchange": row['SEM_EXM_EXCH_ID'],
                    "ticker": sym, # value sent to history
                    "type": "stock" if row['SEM_INSTRUMENT_NAME'] == 'EQUITY' else "index"
                })
    except Exception as e:
        print(f"Search Error: {e}")
        
    return results

@app.get("/symbols")
def udf_symbols(symbol: str):
    # Return info based on requested symbol
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
def udf_history(symbol: str, resolution: str, from_: int = Query(..., alias="from"), to: int = Query(...)):
    client = DhanClient()
    df = pd.DataFrame()
    
    # Convert timestamps to Date Strings
    # CRITICAL: For V2 API, must include Time Component for Intraday queries!
    # Otherwise it defaults to 00:00 to 00:00 (single point) or 1 day.
    from_date_str = datetime.fromtimestamp(from_).strftime('%Y-%m-%d %H:%M:%S')
    to_date_str = datetime.fromtimestamp(to).strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"Chart Request: {symbol} in {from_date_str} to {to_date_str} Resolution: {resolution}")
    print(f"DEBUG: Backend using Token: {client.access_token[:10]}...")
    
    # Limit the date range to prevent fetching excessive data in a SINGLE request
    # However, to support dynamic scrolling (pagination), we must allow larger chunks
    # TradingView will handle the "initial" zoom, but we shouldn't artificially cut off history if requested
    MAX_BARS_PER_REQUEST = 2000 
    
    to_dt = datetime.fromtimestamp(to)
    from_dt = datetime.fromtimestamp(from_)
    
    # Calculate appropriate lookback based on resolution
    # We want to return enough data to fill the screen + buffer, but not entire history in one go if unnecessary
    if resolution == "1D" or resolution == "D":
        # For daily: 2000 days = ~6-7 years (lots of history)
        max_lookback_days = 3000
    elif resolution == "60":
        # For 60-min: 2000 bars = ~250 trading days
        max_lookback_days = 300
    elif resolution == "15":
        # For 15-min: 2000 bars = ~60 trading days
        max_lookback_days = 80
    elif resolution == "5":
        # For 5-min: 2000 bars = ~25 trading days
        max_lookback_days = 30
    else:  # resolution == "1" (1-minute)
        # For 1-min: 2000 bars = ~5 trading days
        max_lookback_days = 7
    
    # Limit the from_date ONLY if the requested range is excessively large
    # This prevents backend timeouts, but allows pagination
    calculated_from_dt = to_dt - timedelta(days=max_lookback_days)
    if from_dt < calculated_from_dt:
        from_dt = calculated_from_dt
        from_date_str = from_dt.strftime('%Y-%m-%d')
        print(f"Range limited to {max_lookback_days} days for resolution {resolution}: {from_date_str} to {to_date_str}")
    
    # Use Generic Fetcher which handles NIFTY/OPTIONS/Generic
    # Pass resolution to fetch_data for proper interval handling
    df = client.fetch_data(symbol, from_date_str, to_date_str, interval=resolution)
    
    if df is None or df.empty:
        print(f"Data fetch returned empty for {symbol}.")
        # DON'T return no_data here - it breaks pagination!
        # Return "ok" with empty bars so TradingView continues to request older data
        return {
            "s": "ok",
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
    print(f"DEBUG: from_={from_} ({datetime.fromtimestamp(from_).isoformat()})")
    print(f"DEBUG: to={to} ({datetime.fromtimestamp(to).isoformat()})")
    print(f"DEBUG: df['timestamp'] dtype={df['timestamp'].dtype}")
    if len(df) > 0:
        print(f"DEBUG: df timestamp range: {df['timestamp'].min()} - {df['timestamp'].max()}")
        print(f"DEBUG: df timestamp as dates: {datetime.fromtimestamp(df['timestamp'].min()).isoformat()} - {datetime.fromtimestamp(df['timestamp'].max()).isoformat()}")
    
    # CRITICAL: Filter data to only include bars within the requested time range
    # TradingView expects data in the from-to range for pagination to work
    original_len = len(df)
    
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
    print(f"Filtered data from {original_len} to {len(df)} bars (range: {from_} to {to})")
    
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

@app.post("/run_backtest")
def run_backtest(req: BacktestRequest):
    try:
        client = DhanClient()
        df = pd.DataFrame()
        
        # Determine Data Source based on Symbol
        # Note: Frontend currently focuses on NIFTY OPTIONS (Index Fallback) or NIFTY 50
        if req.symbol == "NIFTY OPTIONS" or req.symbol == "NIFTY 50":
             if req.from_date and req.to_date:
                 # Generic Fetch handles Index/Options fallback logic internally now
                 # For Options, we ideally want to fetch specific stuff, but sticking to logic
                 df = client.fetch_data("NIFTY 50", req.from_date, req.to_date, interval=req.resolution) 
             else:
                 df = client.fetch_options_data(days_back=req.days)
        else:
             # Generic Search logic
             if req.from_date and req.to_date:
                 df = client.fetch_data(req.symbol, req.from_date, req.to_date, interval=req.resolution)
             else:
                  # Fallback default
                  end_d = datetime.now()
                  start_d = end_d - timedelta(days=req.days)
                  df = client.fetch_data(req.symbol, start_d.strftime("%Y-%m-%d"), end_d.strftime("%Y-%m-%d"))

        
        if df is None or df.empty:
            raise HTTPException(status_code=500, detail=f"Failed to fetch data for {req.symbol}")

        engine = GannStrategyEngine(df)
        trades = []
        
        if req.strategy == "mechanical_3day":
            trades = engine.run_mechanical_3day_swing()
        elif req.strategy == "gann_square_9":
            trades = engine.run_square_of_9_reversion()
        elif req.strategy == "ichimoku_cloud":
             # Placeholder for future strategy
             trades = []
        
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
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
