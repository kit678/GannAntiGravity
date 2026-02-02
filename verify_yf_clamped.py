import yfinance as yf
from datetime import datetime
import pandas as pd

# Simulate the clamping logic
# User Time: Jan 27 2026
# Limit: 730 days
# Earliest Allowed: Jan 27 2024 (approx)

start_date = "2024-01-28"
end_date = "2026-01-27"
symbol = "^NSEI"

print(f"Attempting download for {symbol}")
print(f"Start: {start_date}")
print(f"End:   {end_date}")
print("Interval: 1h")

try:
    df = yf.download(symbol, start=start_date, end=end_date, interval="1h", progress=False)
    print(f"\nStatus: Success")
    print(f"Rows received: {len(df)}")
    if not df.empty:
        print(f"First Index: {df.index[0]}")
        print(f"Last Index:  {df.index[-1]}")
    else:
        print("DataFrame is empty.")

except Exception as e:
    print(f"\nStatus: Failed")
    print(f"Error: {e}")
