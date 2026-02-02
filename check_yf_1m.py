import yfinance as yf
from datetime import datetime, timedelta

def test_1m_data():
    symbol = "^NSEI"
    # 1m data is usually available for the last 7 days.
    # We'll ask for the last 5 days to be safe.
    
    print(f"Fetching 1m data for {symbol} (last 5 days)...")
    ticker = yf.Ticker(symbol)
    
    # invalid 'period' for 1m if start/end not specified correctly or too far back.
    # period="5d" is the safest way to get recent 1m data without calculating exact dates manually unless needed.
    df = ticker.history(period="5d", interval="1m")
    
    if df.empty:
        print("No 1m data returned!")
    else:
        print(f"Received {len(df)} rows.")
        print(f"First timestamp: {df.index[0]}")
        print(f"Last timestamp: {df.index[-1]}")
        print("Sample data:")
        print(df.head())

if __name__ == "__main__":
    test_1m_data()
