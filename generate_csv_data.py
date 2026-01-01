import pandas as pd
from datetime import datetime, timedelta
import os
import sys

# Ensure backend path is in sys.path to import DhanClient
sys.path.append(os.path.join(os.getcwd(), 'gann-visualizer', 'backend'))
from dhan_client import DhanClient

def generate_csvs():
    client = DhanClient()
    
    # 1. Determine Window
    # The user requested "Maximum length ... in ONE API call".
    # Dhan Limit is 90 days. We use 89 days to be safe.
    days_back = 89
    
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days_back)
    
    f_date_str = from_date.strftime("%Y-%m-%d")
    t_date_str = to_date.strftime("%Y-%m-%d") # Today
    
    # User requested: 1, 5, 15, 25, 60 minutes
    intervals = {
        "1min": "1",
        "5min": "5",
        "15min": "15",
        "25min": "25",
        "60min": "60"
    }
    
    # Focusing on NIFTY 50 only as per request
    symbols = ["NIFTY 50"]

    print(f"Fetching data from {f_date_str} to {t_date_str} (Last {days_back} days)...")

    for label, interval_val in intervals.items():
        for sym in symbols:
            print(f"[{sym}] Fetching {label} ({interval_val})...")
            
            try:
                # Nifty 50 (Index)
                df = client.fetch_data(
                    sym,
                    from_date=f_date_str,
                    to_date=t_date_str,
                    interval=interval_val
                )
                
                if df is not None and not df.empty:
                    # Clean filename
                    safe_sym = sym.replace(" ", "_").lower()
                    filename = f"{safe_sym}_{label}.csv"
                    filepath = os.path.join(os.getcwd(), filename)
                    
                    df.to_csv(filepath, index=False)
                    print(f" -> Saved {len(df)} rows to {filename}")
                else:
                    print(f" -> No data returned for {sym} {label}")
            
            except Exception as e:
                print(f" -> Error fetching {sym} {label}: {e}")
                
                if df is not None and not df.empty:
                    # Clean filename
                    safe_sym = sym.replace(" ", "_").lower()
                    filename = f"{safe_sym}_{label}.csv"
                    filepath = os.path.join(os.getcwd(), filename)
                    
                    df.to_csv(filepath, index=False)
                    print(f" -> Saved {len(df)} rows to {filename}")
                else:
                    print(f" -> No data returned for {sym} {label}")
            
            except Exception as e:
                print(f" -> Error fetching {sym} {label}: {e}")

if __name__ == "__main__":
    generate_csvs()
