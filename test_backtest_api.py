import requests
from datetime import datetime
import json

BASE_URL = "http://localhost:8001"

def test_run_backtest():
    # Define range: Dec 22 (Mon) to Dec 24 (Wed)
    from_date = "2025-12-22"
    to_date = "2025-12-24"
    
    payload = {
        "strategy": "mechanical_3day",
        "symbol": "NIFTY 50",
        "from_date": from_date,
        "to_date": to_date,
        "days": 0
    }
    
    print(f"Sending Request: {json.dumps(payload)}")
    try:
        response = requests.post(f"{BASE_URL}/run_backtest", json=payload)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Request Failed: {e}")
        return

    candles = data.get("candles", [])
    trades = data.get("trades", [])
    
    print(f"Received {len(candles)} candles and {len(trades)} trades")
    
    # Verify Candle Range
    if candles:
        first_ts = candles[0]['time']
        last_ts = candles[-1]['time']
        
        start_ts = int(datetime.strptime(from_date, "%Y-%m-%d").timestamp())
        end_ts = int(datetime.strptime(to_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59).timestamp())
        
        print(f"Request Range TS: {start_ts} to {end_ts}")
        print(f"Actual Candle Range: {first_ts} to {last_ts}")
        
        if first_ts < start_ts:
            print("FAIL: First candle is before start date!")
        elif last_ts > end_ts:
            print("FAIL: Last candle is after end date!")
        else:
            print("SUCCESS: Candles are strictly within range.")
            
    # Verify Trade Range
    if trades:
        out_of_range = [t for t in trades if not (start_ts <= t['time'] <= end_ts)]
        if out_of_range:
             print(f"FAIL: Found {len(out_of_range)} trades outside range!")
        else:
             print("SUCCESS: All trades are strictly within range.")
    else:
        print("WARNING: No trades returned (might be expected for short range, but check logic)")

if __name__ == "__main__":
    test_run_backtest()
