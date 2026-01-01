from dhan_client import DhanClient
from datetime import datetime, timedelta
import pandas as pd

# Simulate a request for "Today" or "Last 24 hours"
# TradingView sends UNIX timestamps.
# Example: Let's ask for data from 2024-12-19 to 2024-12-20 (known trading days)
# Adjust these to today if market is open, or recent past.

# Assuming today is Monday Dec 23, 2024 (based on previous logs showing 2025? Wait, system time says 2025-12-22)
# The system time is 2025-12-22. 
# Let's request data for 2025-12-22 (Today) and 2025-12-19 (Previous trading day?)

print("--- DEBUGGING DHAN FETCH ---")
client = DhanClient()

# Test 1: Fetch using 'days_back' (Old Method - Worked partially)
print("\nTest 1: Fetch indices data (days_back=5)...")
df = client.fetch_indices_data(days_back=5)
print(f"Result: {len(df)} rows")
if not df.empty:
    print(df.tail())

# Test 2: Fetch using explicit dates (New Method - Failing?)
# Let's try to fetch just today.
today_str = datetime.now().strftime("%Y-%m-%d")
yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

print(f"\nTest 2: Fetch indices data (from={yesterday_str} to={today_str})...")
df2 = client.fetch_indices_data(from_date=yesterday_str, to_date=today_str)
print(f"Result: {len(df2)} rows")
if not df2.empty:
    print(df2.tail())
else:
    print("Empty DataFrame returned.")

# Test 3: Fetch using a wide range
last_week_str = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
print(f"\nTest 3: Fetch indices data (from={last_week_str} to={today_str})...")
df3 = client.fetch_indices_data(from_date=last_week_str, to_date=today_str)
print(f"Result: {len(df3)} rows")
