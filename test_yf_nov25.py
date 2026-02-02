import yfinance as yf
from datetime import datetime
import pandas as pd
import sys

print(f"System Time: {datetime.now()}")

def test_fetch(desc, start, end, interval):
    print(f"\n--- Testing {desc} ({interval}) ---")
    try:
        # Requesting data for ^NSEI
        df = yf.download("^NSEI", start=start, end=end, interval=interval, progress=False)
        print(f"Rows: {len(df)}")
        if not df.empty:
            print(f"First: {df.index[0]}")
            print(f"Last: {df.index[-1]}")
    except Exception as e:
        print(f"Error: {e}")

# Test 1: Nov 2025 (1 Hour) - The failing case
test_fetch("Nov 2025 to Jan 2026", "2025-11-07", "2026-01-27", "1h")

# Test 2: Nov 2025 (1 Day) - Control case to check if data exists at all
test_fetch("Nov 2025 to Jan 2026", "2025-11-07", "2026-01-27", "1d")
