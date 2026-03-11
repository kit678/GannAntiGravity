import argparse
import sys
import os
import math
import statistics
from datetime import datetime, timedelta

# Add backend directory to Python path so we can import existing modules
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_dir)

from yfinance_client import YFinanceClient
from study_tool.pivot_detector import PivotDetector

# Define the fixed base digits for each timeframe
BASE_DIGITS = {
    '240': 22.0,
    '4H': 22.0,
    '60': 5.5,
    '1H': 5.5,
    '15': 13.73,
    '5': 1.0,  # Placeholder fallback
    '1': 1.0   # Placeholder fallback
}

def calculate_optimal_ratio(symbol: str, timeframe: str):
    print(f"--- Calculating Optimal Scale Ratio for {symbol} on {timeframe}m ---")
    
    base_val = BASE_DIGITS.get(timeframe)
    if base_val is None:
        print(f"Warning: No base digits defined for timeframe '{timeframe}'. Using 1.0 as fallback.")
        base_val = 1.0

    client = YFinanceClient()
    
    # Determine safe lookback based on timeframe to avoid YF limits
    if timeframe in ['1']:
        days_back = 7
    elif timeframe in ['2', '5', '15', '30']:
        days_back = 58
    else:
        days_back = 365
        
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    print(f"Fetching historical data from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}...")
    df = client.fetch_data(symbol, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), interval=timeframe)
    
    if df is None or df.empty:
        print("Error: Failed to fetch data or returned empty dataset.")
        return

    print(f"Fetched {len(df)} bars. Detecting pivots...")
    
    # Convert to dicts for PivotDetector
    candles = df.to_dict('records')
    for c in candles:
        if 'timestamp' in c:
            c['time'] = c['timestamp']
            
    detector = PivotDetector(left_bars=5, right_bars=5)
    for i in range(len(candles)):
        detector.detect_pivots(candles, i)
        
    pivots = detector.confirmed_pivots
    if len(pivots) < 2:
        print("Error: Not enough pivots detected to calculate slope.")
        return
        
    print(f"Detected {len(pivots)} confirmed pivots.")
    
    # Calculate raw slopes between consecutive pivots
    slopes = []
    pivots.sort(key=lambda p: p.bar_index)
    
    for i in range(1, len(pivots)):
        p1 = pivots[i-1]
        p2 = pivots[i]
        
        dp = abs(p2.price - p1.price)
        dt = abs(p2.bar_index - p1.bar_index)
        
        if dt > 0:
            slopes.append(dp / dt)
            
    if not slopes:
        print("Error: Could not calculate any valid slopes.")
        return
        
    ideal_ratio = statistics.median(slopes)
    
    # Snap to base digits using base-10 logarithm
    shift = math.log10(ideal_ratio / base_val)
    exponent = round(shift)
    multiplier = 10 ** exponent
    final_ratio = base_val * multiplier
    
    print("\n=== RESULTS ===")
    print(f"Symbol:        {symbol}")
    print(f"Timeframe:     {timeframe}")
    print(f"Ideal Ratio:   {ideal_ratio:.6f} (Median raw slope)")
    print(f"Base Digits:   {base_val}")
    print(f"Log10 Shift:   {shift:.4f}")
    print(f"Exponent:      {exponent}")
    print(f"Multiplier:    {multiplier}")
    print(f"FINAL RATIO:   {final_ratio}")
    print("===============\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calculate optimal price-to-bar ratio for a ticker and timeframe.")
    parser.add_argument("symbol", type=str, help="Ticker symbol (e.g., AAPL, ^NSEI)")
    parser.add_argument("timeframe", type=str, help="Timeframe resolution (e.g., 15, 60, 240)")
    
    args = parser.parse_args()
    calculate_optimal_ratio(args.symbol, args.timeframe)
