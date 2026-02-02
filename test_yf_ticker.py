import yfinance as yf
from datetime import datetime
print(f"Time: {datetime.now()}")

symbol = "^NSEI"
start = "2025-11-07"
end = "2026-01-27"
interval = "1h"

print(f"\n--- Testing Ticker.history for {symbol} ---")
try:
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start, end=end, interval=interval, auto_adjust=True, prepost=False)
    print(f"Rows: {len(df)}")
    if not df.empty:
        print(f"First: {df.index[0]}")
        print(f"Last: {df.index[-1]}")
        print(f"Columns: {df.columns.tolist()}")
    else:
        print("EMPTY DATAFRAME")
except Exception as e:
    print(f"Error: {e}")
