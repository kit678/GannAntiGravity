import yfinance as yf
from datetime import datetime, timedelta

print(f"System Time: {datetime.now()}")

# Simulate main.py expansion
req_from = "2025-11-07"
req_to = "2026-01-27"
lookback_bars = 5000
resolution = "60" # 1h

from_dt = datetime.strptime(req_from, '%Y-%m-%d')
lookback_days = max(1, lookback_bars // 6) # 833
lookback_days = int(lookback_days * 4.0) + 30 # ~3363
lookback_days = min(lookback_days, 3650) # 3363

adjusted_from_dt = from_dt - timedelta(days=lookback_days)
print(f"Main.py Adjusted Start: {adjusted_from_dt}")

# Simulate yfinance_client.py
start_dt = adjusted_from_dt
end_dt = datetime.strptime(req_to, '%Y-%m-%d') + timedelta(hours=23, minutes=59) # as per yfinance_client logic
interval = "1h"

# Date clamping logic from YFinanceClient
requested_days = (end_dt - start_dt).days
max_days = 730
if requested_days > max_days:
    print(f"Clamping: Requested {requested_days} > {max_days}")
    start_dt = end_dt - timedelta(days=max_days)
    print(f"Clamped Start: {start_dt}")

# Age Check Logic from YFinanceClient
now = datetime.now()
limit_from_now = 730
age_days = (now - start_dt).days

print(f"Age Check: Age={age_days} vs Limit={limit_from_now}")

if age_days > limit_from_now:
    print(f"Age Check Triggered!")
    start_dt = now - timedelta(days=limit_from_now - 1)
    print(f"Age Adjusted Start: {start_dt}")

# Final Prepare
start_str = start_dt.strftime("%Y-%m-%d")
end_str = (end_dt + timedelta(days=1)).strftime("%Y-%m-%d")

print(f"Final Request: {start_str} to {end_str}")

try:
    print("Downloading...")
    # Using download matches yfinance_client (mostly) but client uses ticker.history
    # Let's use ticker.history to be exact
    ticker = yf.Ticker("^NSEI")
    df = ticker.history(start=start_str, end=end_str, interval="1h", auto_adjust=True, prepost=False)
    print(f"Rows: {len(df)}")
    if not df.empty:
        print(f"First: {df.index[0]}")
        print(f"Last: {df.index[-1]}")
    else:
        print("EMPTY DATAFRAME")
except Exception as e:
    print(f"Error: {e}")
