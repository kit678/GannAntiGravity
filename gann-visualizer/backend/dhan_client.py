import os
import requests
import pandas as pd
from io import StringIO
import re
from datetime import datetime, timedelta
from cache_manager import get_cache
import pytz

class DhanScripMaster:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DhanScripMaster, cls).__new__(cls)
            cls._instance.df = pd.DataFrame()
            cls._instance.loaded = False
        return cls._instance

    def load(self):
        if self.loaded and not self.df.empty:
            return

        url = "https://images.dhan.co/api-data/api-scrip-master.csv"
        cache_file = "scrip_master_cache.csv"
        
        try:
            if os.path.exists(cache_file):
                # Check age (optional, for now just use it)
                print("Loading Scrip Master from Cache...")
                self.df = pd.read_csv(cache_file)
            else:
                print("Downloading Dhan Scrip Master...")
                response = requests.get(url)
                response.raise_for_status()
                self.df = pd.read_csv(StringIO(response.text))
                self.df.to_csv(cache_file, index=False)
            
            # Helper columns
            # We focus on NSE Index and NSE Equity for now
            # segment: 'I' for Index, 'E' for Equity
            # But CSV has 'SEM_SEGMENT' which might be 'I', 'E' or 'D'
            
            # Normalize
            self.df.columns = [c.strip() for c in self.df.columns]
            
            # Filter for NSE only to save memory/speed
            self.df = self.df[self.df['SEM_EXM_EXCH_ID'] == 'NSE']
            
            # Create a searchable 'symbol' column
            self.df['SEARCH_SYMBOL'] = self.df['SEM_TRADING_SYMBOL'].astype(str).str.upper()
            
            self.loaded = True
            print(f"Scrip Master Loaded: {len(self.df)} symbols.")
            
        except Exception as e:
            print(f"Failed to load Scrip Master: {e}")

    def search(self, query):
        if not self.loaded: self.load()
        q = query.upper()
        # Simple contains search
        mask = self.df['SEARCH_SYMBOL'].str.contains(q, na=False)
        results = self.df[mask].head(20) # Limit 20
        return results

    def get_info(self, symbol):
        if not self.loaded: self.load()
        # Exact match attempt
        row = self.df[self.df['SEARCH_SYMBOL'] == symbol.upper()]
        if row.empty:
            return None
        return row.iloc[0]

class DhanClient:
    # Hardcoded Access Token (Replace with env variable or secure storage in prod)
    ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzY4ODQxMzU2LCJpYXQiOjE3Njg3NTQ5NTYsInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTA5MzgxMTg5In0.wQevy6ZbkxCxOJVGPr_LZAJyNMyodqy819IgYIsiGwghzDrYucvy22Q9Pt5LSnzxYK-JXKCNeI0yeU4PL5miHQ"
    CLIENT_ID = "1109381189"

    def __init__(self):
        # Configuration
        self.base_url = "https://api.dhan.co/v2/charts/intraday" # Correct base for chart fetch
        self.client_id = DhanClient.CLIENT_ID
        self.scrip_master = DhanScripMaster()
        
        self.access_token = DhanClient.ACCESS_TOKEN
        self.session = requests.Session()

        self.headers = {
            "access-token": self.access_token,
            "client-id": self.client_id,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    # NEW Generic Fetcher
    def fetch_data(self, symbol, from_date, to_date, interval="1"):
        # PERFORMANCE OPTIMIZATION: Check cache first
        cache = get_cache()
        cached_data = cache.get(symbol, from_date, to_date, interval)
        if cached_data is not None:
            return cached_data
        
        # 1. Resolve Symbol to ID and Config
        scrip_info = self.scrip_master.get_info(symbol)
        
        # Fallback for NIFTY OPTIONS and NIFTY 50 logic (retained)
        if symbol == "NIFTY OPTIONS":
             return self.fetch_options_data(from_date=from_date, to_date=to_date)
        if symbol == "NIFTY 50":
             security_id = "13"
             segment = "IDX_I" # Index
             instrument = "INDEX"
        elif scrip_info is not None:
             security_id = str(scrip_info['SEM_SMST_SECURITY_ID'])
             # Determine segment
             instr = scrip_info['SEM_INSTRUMENT_NAME']
             if instr == 'INDEX':
                 segment = "IDX_I"
                 instrument = "INDEX"
             elif instr == 'EQUITY':
                 segment = "NSE_EQ"
                 instrument = "EQUITY"
             else:
                 segment = "NSE_EQ"
                 instrument = "EQUITY"
        else:
             print(f"Unknown symbol: {symbol}")
             return pd.DataFrame()

        # 2. Chunking Logic for >90 Days
        # Dhan API limit is ~90 days per request for intraday data.
        all_dfs = []
        
        # PERFORMANCE OPTIMIZATION: Parse and validate dates ONCE before chunking loop
        # This avoids redundant operations in each chunk iteration
        start_dt = None
        end_dt = None
        
        # Parse dates with fallback formats
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
            try:
                if not start_dt: start_dt = datetime.strptime(from_date, fmt)
            except ValueError: pass
            
            try:
                if not end_dt: end_dt = datetime.strptime(to_date, fmt)
            except ValueError: pass
            
        if not start_dt or not end_dt:
            print(f"Error: Could not parse dates: {from_date} / {to_date}")
            return pd.DataFrame()
        
        # Pre-compute current datetime once (avoid repeated datetime.now() calls)
        now = datetime.now()
        
        # Weekend validation for end date
        if end_dt.weekday() >= 5:  # Saturday=5, Sunday=6
            days_back = end_dt.weekday() - 4  # Go back to Friday (4)
            end_dt = end_dt - timedelta(days=days_back)
            print(f"Weekend detected, using last Friday: {end_dt.strftime('%Y-%m-%d')}")
        
        # Weekend validation for start date
        if start_dt.weekday() >= 5:
            days_back = start_dt.weekday() - 4
            start_dt = start_dt - timedelta(days=days_back)
            print(f"Weekend start detected, using last Friday: {start_dt.strftime('%Y-%m-%d')}")
        
        # Future date validation (cap at today)
        if end_dt.date() > now.date():
            end_dt = now
            print(f"Future date detected, capping to today: {end_dt.strftime('%Y-%m-%d')}")
            # Check if today is weekend
            if end_dt.weekday() >= 5:
                days_back = end_dt.weekday() - 4
                end_dt = end_dt - timedelta(days=days_back)
                print(f"Today is weekend, using last Friday: {end_dt.strftime('%Y-%m-%d')}")
        
        # Single-day request expansion (only for recent dates)
        if start_dt.date() == end_dt.date():
            days_ago = (now.date() - end_dt.date()).days
            if days_ago <= 3:
                start_dt = start_dt - timedelta(days=2)
                print(f"Single-day request detected (recent data), expanding to 3-day range: {start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}")
            else:
                print(f"Historical single-day request: {start_dt.strftime('%Y-%m-%d')}")
        
        current_start = start_dt
        
        # Determine if this is a daily/weekly request (use historical endpoint)
        # or intraday (use intraday endpoint)
        is_daily = interval in ["D", "1D", "W", "1W"]
        
        if is_daily:
            # Use historical endpoint for daily data - no chunking needed
            print(f"Using HISTORICAL endpoint for daily data: {from_date} to {to_date}")
            url = "https://api.dhan.co/v2/charts/historical"
            
            payload = {
                "exchangeSegment": segment,
                "instrument": instrument,
                "securityId": security_id,
                "expiryCode": 0,
                "fromDate": start_dt.strftime("%Y-%m-%d"),
                "toDate": end_dt.strftime("%Y-%m-%d")
            }
            
            try:
                response = requests.post(url, headers=self.headers, json=payload)
                print(f"Historical API Response Status: {response.status_code}")
                
                if response.status_code != 200:
                    print(f"Historical API Error Response: {response.text}")
                    return pd.DataFrame()
                
                # Process response - historical endpoint uses flat structure
                df = self._process_response(response, is_flat=True, anchor_datetime=end_dt, interval_str=interval)
                return df
                
            except Exception as e:
                print(f"Historical fetch failed: {e}")
                return pd.DataFrame()
        
        # PERFORMANCE OPTIMIZATION: Pre-compute chunk boundaries to avoid repeated datetime operations
        # Calculate all chunks upfront for better efficiency
        chunk_size_days = 80  # Stay under 90-day API limit
        chunks = []
        current_start = start_dt
        
        while current_start <= end_dt:
            current_end = current_start + timedelta(days=chunk_size_days)
            if current_end > end_dt:
                current_end = end_dt
            
            # Pre-format time strings once per chunk
            chunk_from_str = current_start.strftime("%Y-%m-%d %H:%M:%S")
            
            # If current_end is at midnight, set to 15:30:00 to include that day's trading data
            if current_end.hour == 0 and current_end.minute == 0:
                chunk_to_str = current_end.replace(hour=15, minute=30).strftime("%Y-%m-%d %H:%M:%S")
            else:
                chunk_to_str = current_end.strftime("%Y-%m-%d %H:%M:%S")
            
            # Ensure time component exists
            if " " not in chunk_from_str: 
                chunk_from_str += " 09:15:00"
            
            chunks.append((chunk_from_str, chunk_to_str, current_end))
            current_start = current_end + timedelta(days=1)
        
        # Process all chunks with pre-computed boundaries
        for chunk_from_str, chunk_to_str, anchor in chunks:

            print(f"Fetching intraday chunk: {chunk_from_str} to {chunk_to_str}")
            
            # Using V2 Endpoint
            url = "https://api.dhan.co/v2/charts/intraday" 
            
            payload = {
                "exchangeSegment": segment,
                "instrument": instrument,
                "securityId": security_id,
                "interval": interval,
                "fromDate": chunk_from_str,
                "toDate": chunk_to_str
            }
            
            try:
                response = requests.post(url, headers=self.headers, json=payload)
                
                # Cap anchor at current time if needed
                anchor_time = anchor if anchor <= now else now
                
                # Use is_flat=True for V2 Endpoint
                df_chunk = self._process_response(response, is_flat=True, anchor_datetime=anchor_time, interval_str=interval)
                
                if not df_chunk.empty:
                    all_dfs.append(df_chunk)
                else:
                    # FALLBACK: Try Historical API if Intraday returns nothing (often happens for older dates)
                    # Historical API typically covers EOD but might support Intraday intervals with correct payload
                    print(f"Intraday chunk empty for {chunk_from_str}. Trying Historical endpoint fallback...")
                    hist_url = "https://api.dhan.co/v2/charts/historical"
                    
                    # Ensure format is YYYY-MM-DD for historical? Or keep full string?
                    # Generally historical takes YYYY-MM-DD. Let's try slicing.
                    hist_from = chunk_from_str.split(' ')[0]
                    hist_to = chunk_to_str.split(' ')[0]
                    
                    hist_payload = {
                        "exchangeSegment": segment,
                        "instrument": instrument,
                        "securityId": security_id,
                        "expiryCode": 0,
                        "interval": interval,  # Try passing interval
                        "fromDate": hist_from,
                        "toDate": hist_to
                    }
                    
                    try:
                        resp_hist = requests.post(hist_url, headers=self.headers, json=hist_payload)
                        df_hist = self._process_response(resp_hist, is_flat=True, anchor_datetime=anchor_time, interval_str=interval)
                        
                        if not df_hist.empty:
                            print(f"Historical Fallback SUCCESS: Retrieved {len(df_hist)} bars")
                            all_dfs.append(df_hist)
                        else:
                            print("Historical Fallback returned no data.")
                    except Exception as e_hist:
                        print(f"Historical Fallback failed: {e_hist}")

            except Exception as e:
                print(f"Chunk fetch failed: {e}")


        # 3. Concatenate and Deduplicate
        if not all_dfs:
            return pd.DataFrame()
            
        final_df = pd.concat(all_dfs, ignore_index=True)
        final_df.drop_duplicates(subset=['timestamp'], inplace=True)
        final_df.sort_values('timestamp', inplace=True)
        
        # PERFORMANCE OPTIMIZATION: Cache the result with intelligent TTL
        # Use shorter TTL for recent data, longer for historical data
        cache = get_cache()
        
        # Determine if this is recent data (within last 7 days)
        if not final_df.empty and 'timestamp' in final_df.columns:
            latest_timestamp = final_df['timestamp'].max()
            days_old = (datetime.now().timestamp() - latest_timestamp) / 86400  # Convert to days
            
            if days_old <= 7:
                # Recent data: 60 second TTL (may change frequently)
                cache_ttl = 60
            else:
                # Historical data: 24 hour TTL (unlikely to change)
                cache_ttl = 86400  # 24 hours
            
            cache.put(symbol, from_date, to_date, interval, final_df, ttl=cache_ttl)
        
        return final_df

    def fetch_indices_data(self, days_back=5, interval="1", from_date=None, to_date=None):
         # Wrapper for backward compatibility or direct usage
         if from_date is None: from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
         if to_date is None: to_date = datetime.now().strftime("%Y-%m-%d")
         return self.fetch_data("NIFTY 50", from_date, to_date, interval)

    def fetch_options_data(self, from_date=None, to_date=None, days_back=5, interval="1", opt_type="CALL"):
        # Prepare Dates for Options (Correct Format YYYY-MM-DD HH:MM:SS)
        start_dt = None
        end_dt = None
        anchor = datetime.now()
        
        if from_date and to_date:
             # Try parsing to ensure time component
             # Try parsing to ensure time component
             try:
                 start_dt = datetime.strptime(from_date, "%Y-%m-%d %H:%M:%S")
                 end_dt = datetime.strptime(to_date, "%Y-%m-%d %H:%M:%S")
             except ValueError:
                 try:
                     start_dt = datetime.strptime(from_date, "%Y-%m-%d")
                     end_dt = datetime.strptime(to_date, "%Y-%m-%d")
                 except ValueError:
                     pass
             
             if start_dt and end_dt:
                 anchor = end_dt # Use exact requested end time as anchor
             else:
                 print(f"Warning: Could not parse from_date/to_date for options. Using default logic.")
        
        if start_dt is None or end_dt is None:
             # Default Logic
             end_dt = datetime.now()
             start_dt = end_dt - timedelta(days=days_back)
             anchor = end_dt # Anchor for synthetic generation
        
        # Fallback to NIFTY 50 Index Data for "Options" visualization 
        # because Chart API determines ATM dynamically is likely not supported via this simple call.
        # To get real ATM Options, we would need to look up the specific strike Security ID first.
        payload = {
            "exchangeSegment": "IDX_I",
            "interval": interval,
            "securityId": "13", 
            "instrument": "INDEX",
            "fromDate": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "toDate": end_dt.strftime("%Y-%m-%d %H:%M:%S")
        }

        print(f"Fetching Options data (Index Fallback): {payload}")
        try:
            # Use V2 Endpoint explicitly
            url = "https://api.dhan.co/v2/charts/intraday"
            response = requests.post(url, headers=self.headers, json=payload)
            return self._process_response(response, is_option=False, is_flat=True, anchor_datetime=anchor)
        except Exception as e:
            print(f"Options fetch failed: {e}")
            return pd.DataFrame()



    def _process_response(self, response, is_option=False, is_flat=False, anchor_datetime=None, interval_str="1"):
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and "status" in data and data["status"] == "failure":
                    print(f"API Error Response: {data}")
                    return pd.DataFrame() 
            
            # DEBUG PRINT
            # print(f"API Response Keys: {list(data.keys())}")
            # if 'data' in data: print(f"Data Keys: {list(data['data'].keys())}")
            
            target_data = {}
            if is_flat:
                target_data = data
            else:
                raw_data = data.get("data", {})
                target_data = raw_data
                if is_option:
                    keys = list(raw_data.keys())
                    if 'ce' in keys: target_data = raw_data['ce']
                    elif 'pe' in keys: target_data = raw_data['pe']
            
            if not target_data:
                return pd.DataFrame()

            clean_data = {}
            desired_len = 0
            if 'close' in target_data: desired_len = len(target_data['close'])
            
            if desired_len == 0:
                return pd.DataFrame()

            for k, v in target_data.items():
                if isinstance(v, list) and len(v) == desired_len:
                    clean_data[k] = v
            
            df = pd.DataFrame(clean_data)
            
            # Date Parsing
            col_map = {c.lower(): c for c in df.columns}
            time_col = col_map.get('start_time') or col_map.get('time') or col_map.get('timestamp')
            
            use_real_time = False
            
            # Try to determine if we should use the API time or Synthetic
            if time_col:
                try:
                    # Check if it's already numeric or string
                    sample = df[time_col].iloc[0]
                    
                    if isinstance(sample, str):
                        # Attempt to parse string format "YYYY-MM-DD HH:MM:SS"
                        # Dhan V2 often sends this - CRITICAL: These are in IST timezone!
                        try:
                            # TIMEZONE FIX: Dhan API returns IST times as naive strings
                            # We must localize to IST before converting to Unix epoch (UTC-based)
                            ist = pytz.timezone('Asia/Kolkata')
                            
                            # Parse as naive datetime first
                            naive_datetimes = pd.to_datetime(df[time_col])
                            
                            # Localize to IST and convert to Unix timestamp
                            # This ensures 09:15 IST becomes the correct UTC epoch
                            df['timestamp'] = naive_datetimes.apply(
                                lambda dt: int(ist.localize(dt).timestamp())
                            )
                            
                            # Debug: Log sample conversion
                            if len(df) > 0:
                                sample_naive = naive_datetimes.iloc[0]
                                sample_ts = df['timestamp'].iloc[0]
                                print(f"[TIMEZONE FIX] Sample: '{df[time_col].iloc[0]}' -> IST localized -> Unix: {sample_ts} ({datetime.fromtimestamp(sample_ts)})")
                            
                            use_real_time = True
                        except Exception as e:
                            print(f"Date String Parsing Failed: {e}")
                    else:
                        # Assume Numeric (Epoch or similar)
                        first_ts = float(sample)
                        last_ts = float(df[time_col].iloc[-1])
                        
                        # Basic Epoch check (> year 2000)
                        if last_ts > 946684800: 
                            use_real_time = True
                            
                            # Validate against Anchor if provided
                            if anchor_datetime:
                                anchor_ts = anchor_datetime.timestamp()
                                diff = abs(last_ts - anchor_ts)
                                if diff > 31536000: # 1 Year tolerance
                                    print(f"WARNING: API Timestamp {datetime.fromtimestamp(last_ts)} vs Anchor {anchor_datetime} diff > 1 Year. Forcing Synthetic.")
                                    use_real_time = False
                                else:
                                     # It's good, set column
                                     df['timestamp'] = df[time_col]
                        else:
                             print(f"Timestamps look invalid (small/weird): {last_ts}")
                             
                except Exception as e:
                    print(f"Time validation error: {e}")
                    pass

            if not use_real_time:
                # USER REQUEST: Disable Synthetic Fallback
                print(f"CRITICAL: Data validation failed. Synthetic Fallback is DISABLED.")
                print(f"Debug Info: Time Col: {time_col}")
                if time_col and not df.empty:
                    print(f"Sample Time Value: {df[time_col].iloc[0]}")
                    print(f"Last Time Value: {df[time_col].iloc[-1]}")
                
                # Use raw date if possible, else fail
                # Force attempt to use what we have or return empty
                # returning empty to proving failure
                print("Returning empty DataFrame due to validation failure.")
                return pd.DataFrame()

            # DISABLE SYNTHETIC LOGIC BELOW (Commented out effectively by returning above)
            if False: 
                # Synthetic Generation logic...
                
                base_time = anchor_datetime if anchor_datetime else datetime.now()
                
                # If base_time is midnight (00:00), it's likely a date object or start of day.
                # If we are fetching "Intraday", we should probably align to Market Close (15:30) if it's a past date,
                # or "Now" if it's today.
                
                # Logic: If anchor is today (dates match), use Now (capped at 15:30?). 
                # If anchor is past, use 15:30 of that day.
                
                now = datetime.now()
                is_today = base_time.date() == now.date()
                
                end_time = base_time
                if is_today:
                    if now.hour >= 16: # Update: Market closed
                         end_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
                    elif now.hour < 9:
                         # Pre-market? Use yesterday close?
                         # For simplicity, use Now
                         end_time = now
                    else:
                         end_time = now
                else:
                    # Past Date -> Market Close
                     end_time = base_time.replace(hour=15, minute=30, second=0, microsecond=0)

                # Interval parsing
                interval_mins = 1
                if interval_str == "5": interval_mins = 5
                elif interval_str == "15": interval_mins = 15
                elif interval_str == "60": interval_mins = 60
                
                cnt = len(df)
                timestamps = []
                for i in range(cnt):
                    # backwards from end
                    # i=0 is first index (oldest), i=cnt-1 is last index (newest)
                    # We want last index = end_time
                    # timestamp[j] = end_time - (cnt - 1 - j) * interval
                    
                    delta = timedelta(minutes=(cnt - 1 - i) * interval_mins)
                    dt = end_time - delta
                    timestamps.append(int(dt.timestamp()))
                
                df['timestamp'] = timestamps
            
            # Standardize column names (case-insensitive mapping)
            col_map_lower = {c.lower(): c for c in df.columns}
            rename_dict = {}
            
            # Map common variations to standard names
            if 'open' not in df.columns:
                if col_map_lower.get('o'): rename_dict[col_map_lower['o']] = 'open'
                elif col_map_lower.get('Open'): rename_dict[col_map_lower['Open']] = 'open'
            
            if 'high' not in df.columns:
                if col_map_lower.get('h'): rename_dict[col_map_lower['h']] = 'high'
                elif col_map_lower.get('High'): rename_dict[col_map_lower['High']] = 'high'
            
            if 'low' not in df.columns:
                if col_map_lower.get('l'): rename_dict[col_map_lower['l']] = 'low'
                elif col_map_lower.get('Low'): rename_dict[col_map_lower['Low']] = 'low'
            
            if 'close' not in df.columns:
                if col_map_lower.get('c'): rename_dict[col_map_lower['c']] = 'close'
                elif col_map_lower.get('Close'): rename_dict[col_map_lower['Close']] = 'close'
            
            if 'volume' not in df.columns:
                if col_map_lower.get('v'): rename_dict[col_map_lower['v']] = 'volume'
                elif col_map_lower.get('Volume'): rename_dict[col_map_lower['Volume']] = 'volume'
            
            if rename_dict:
                df.rename(columns=rename_dict, inplace=True)
            
            # Debug: Print column names and sample data
            print(f"DataFrame columns: {list(df.columns)}")
            if not df.empty:
                print(f"Sample row (first): O={df.get('open', [None])[0] if 'open' in df.columns else 'N/A'}, "
                      f"H={df.get('high', [None])[0] if 'high' in df.columns else 'N/A'}, "
                      f"L={df.get('low', [None])[0] if 'low' in df.columns else 'N/A'}, "
                      f"C={df.get('close', [None])[0] if 'close' in df.columns else 'N/A'}")
            
            return df
        else:
            print(f"HTTP Error: {response.status_code}")
            return pd.DataFrame()

if __name__ == "__main__":
    client = DhanClient()
    df = client.fetch_options_data(days_back=2)
    print(df.head())
