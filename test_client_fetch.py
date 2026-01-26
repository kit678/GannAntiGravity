
import sys
import os
import pandas as pd

# Add backend to path so imports work
sys.path.append(os.path.join(os.getcwd(), 'gann-visualizer', 'backend'))

from yfinance_client import YFinanceClient

def test_client_logic():
    print("Initializing YFinanceClient...")
    client = YFinanceClient()
    
    symbol = "^NSEI"
    start_date = "2025-01-01"
    end_date = "2026-01-20"
    interval = "60" # Testing the exact string frontend sends
    
    print(f"\n--- Testing fetch_data('{symbol}', '{start_date}', '{end_date}', '{interval}') ---")
    
    # We expect this to use '1h' internally and allow >60 days
    df = client.fetch_data(symbol, start_date, end_date, interval)
    
    if df.empty:
        print("RESULT: No data returned!")
    else:
        print(f"RESULT: Received {len(df)} rows.")
        first_ts = pd.to_datetime(df['timestamp'].iloc[0], unit='s')
        last_ts = pd.to_datetime(df['timestamp'].iloc[-1], unit='s')
        print(f"Time Range: {first_ts} to {last_ts}")
        
        if first_ts.year == 2025 and first_ts.month == 1:
            print("SUCCESS: Retrieved data from Jan 2025!")
        else:
            print("FAILURE: Data started later than requested!")

if __name__ == "__main__":
    test_client_logic()
