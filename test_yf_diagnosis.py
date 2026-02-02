import yfinance as yf
from datetime import datetime, timedelta
import sys

print(f"System Time: {datetime.now()}")

symbol = "^NSEI"

# Test 1: Recent 5 days (relative to NOW)
end = datetime.now()
start = end - timedelta(days=5)
print(f"\n--- Test 1: Fetching recent 5 days ({start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}) 1h ---")
try:
    df = yf.download(symbol, start=start, end=end, interval="1h", progress=False)
    print(f"Result: {len(df)} rows")
    if not df.empty:
        print(f"First: {df.index[0]}")
        print(f"Last: {df.index[-1]}")
except Exception as e:
    print(f"Error: {e}")

# Test 2: The problematic range (Nov 2025 to Jan 2026)
start_prob = "2025-11-07"
end_prob = "2026-01-27"
print(f"\n--- Test 2: Fetching user range ({start_prob} to {end_prob}) 1h ---")
try:
    df2 = yf.download(symbol, start=start_prob, end=end_prob, interval="1h", progress=False)
    print(f"Result: {len(df2)} rows")
except Exception as e:
    print(f"Error: {e}")

# Test 3: Probe Years to find "Real" time
print(f"\n--- Test 3: Probing Years ---")

def probe_year(year):
    start_str = f"{year}-01-01"
    end_str = f"{year}-01-10"
    try:
        df = yf.download(symbol, start=start_str, end=end_str, interval="1d", progress=False)
        return len(df)
    except:
        return 0

for y in [2026, 2025, 2024]:
    count = probe_year(y)
    print(f"Year {y}: {count} rows")

