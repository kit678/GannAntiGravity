import sys
import os
import json
import logging
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# Add current directory to path so we can import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from study_tool.angular_coverage_study import AngularPriceCoverageStudy
from study_tool.event_logger import EventType

def get_data(symbol="AAPL", period="1y"):
    """Fetch data from yfinance or generate mock data if unavailable."""
    try:
        import yfinance as yf
        print(f"Fetching data for {symbol}...")
        df = yf.download(symbol, period=period, progress=False)
        if df.empty:
            raise ValueError("Empty dataframe")
        
        # Reset index to get Date column
        df = df.reset_index()
        
        candles = []
        for _, row in df.iterrows():
            # Handle multi-index columns if present (yfinance update)
            close = row['Close'].iloc[0] if isinstance(row['Close'], pd.Series) else row['Close']
            high = row['High'].iloc[0] if isinstance(row['High'], pd.Series) else row['High']
            low = row['Low'].iloc[0] if isinstance(row['Low'], pd.Series) else row['Low']
            open_p = row['Open'].iloc[0] if isinstance(row['Open'], pd.Series) else row['Open']
            
            candles.append({
                'time': int(row['Date'].timestamp()),
                'open': float(open_p),
                'high': float(high),
                'low': float(low),
                'close': float(close),
                'volume': int(row['Volume'].iloc[0] if isinstance(row['Volume'], pd.Series) else row['Volume'])
            })
        print(f"Loaded {len(candles)} candles from yfinance.")
        return candles
    except Exception as e:
        print(f"Failed to fetch data: {e}. Generating mock data.")
        return generate_mock_data()

def generate_mock_data(count=500):
    """Generate synthetic price data with trends and pivots."""
    candles = []
    price = 100.0
    trend = 1
    start_time = int(datetime.now().timestamp()) - (count * 86400)
    
    for i in range(count):
        # Create waves
        if i % 50 == 0:
            trend *= -1
        
        change = np.random.normal(0, 1.0) + (trend * 0.5)
        price += change
        
        high = price + abs(np.random.normal(0, 0.5))
        low = price - abs(np.random.normal(0, 0.5))
        open_p = (high + low) / 2
        
        candles.append({
            'time': start_time + (i * 86400),
            'open': open_p,
            'high': high,
            'low': low,
            'close': price,
            'volume': 1000
        })
    return candles

def run_simulation():
    # Setup
    candles = get_data()
    study = AngularPriceCoverageStudy(config={
        'left_bars': 5, 
        'right_bars': 5,
        'successive_closes_required': 2
    })
    
    print("Starting simulation...")
    
    # Initialize history
    # The study handles initialization internally on the first process_bar call 
    # if we pass the full history, but let's simulate a replay loop
    
    # Run through all candles
    for i in range(len(candles)):
        # We pass the full list of candles, but current index 'i'
        # The study will look back from 'i'
        study.process_bar(candles, i)
        
        if i % 50 == 0:
            print(f"Processed {i}/{len(candles)} bars...")
            
    print("Simulation complete.")
    
    # Export logs
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    csv_path = os.path.join(log_dir, "simulation_events.csv")
    
    study.event_logger.export_csv(csv_path)
    print(f"Events exported to {csv_path}")
    
    # Print stats
    stats = study.event_logger.get_statistics()
    print("\n--- Simulation Statistics ---")
    print(json.dumps(stats, indent=2))
    
    # Check if we have any confirmed breaches
    breaches = study.event_logger.get_events_by_type(EventType.BREACH_CONFIRMED)
    print(f"\nConfirmed Breaches: {len(breaches)}")
    if breaches:
        print("Sample breach:", breaches[0].to_dict())

if __name__ == "__main__":
    run_simulation()
