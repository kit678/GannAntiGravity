import yfinance as yf
from datetime import datetime

def test_history():
    symbol = "^NSEI"
    # Try to fetch from Jan 2025 to Jan 2026 (1 year)
    start_date = "2025-01-01" 
    end_date = "2026-01-20"
    interval = "1h"

    print(f"Fetching {symbol} {interval} data from {start_date} to {end_date}...")
    
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start_date, end=end_date, interval=interval)
    
    if df.empty:
        print("No data returned!")
    else:
        print(f"Received {len(df)} rows.")
        print(f"First timestamp: {df.index[0]}")
        print(f"Last timestamp: {df.index[-1]}")
        
    print("-" * 30)

    # Comparison checking '60m' vs '1h'
    print("Checking '60m' interval for comparison...")
    df_60m = ticker.history(start=start_date, end=end_date, interval="60m")
    if df_60m.empty:
         print("No data returned for 60m!")
    else:
        print(f"Received {len(df_60m)} rows.")
        print(f"First timestamp: {df_60m.index[0]}")

if __name__ == "__main__":
    test_history()
