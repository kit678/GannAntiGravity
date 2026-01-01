from dhan_client import DhanClient
from datetime import datetime
import pandas as pd

# Test case: Requesting up to Dec 26 2025 (Friday)
# The input date implies midnight 00:00:00
req_to = "2025-12-26"
req_from = "2025-12-22"

client = DhanClient()
print("Starting Test Fetch for Dec 26 Data...")

# We simulate what run_backtest calls
df = client.fetch_data("NIFTY 50", req_from, req_to)

print(f"Fetch completed. Rows: {len(df)}")
if notdf.empty:
    last_row = df.iloc[-1]
    last_ts = pd.to_datetime(last_row['timestamp'], unit='s')
    print(f"Last Bar Time: {last_ts}")
    
    # Check if we have data for Dec 26
    if last_ts.date() == datetime(2025, 12, 26).date():
        print("SUCCESS: Dec 26 data is present.")
    else:
        print(f"FAIL: Last date is {last_ts.date()}, expected 2025-12-26")
else:
    print("FAIL: No data returned")
