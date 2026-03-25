import sys
import os
import json
import logging
import argparse
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import pytz

# Add current directory to path so we can import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from study_tool.angular_coverage_study import AngularPriceCoverageStudy
from study_tool.event_logger import EventType
from main import get_data_client, get_dynamic_scale_ratio

def setup_logging():
    """Set up logging to both console and a file in the logs directory."""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, "simulation_run.log")
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers if any
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    # Create file handler (overwrite mode)
    file_handler = logging.FileHandler(log_file, mode='w')
    file_handler.setLevel(logging.INFO)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.__stdout__)
    console_handler.setLevel(logging.INFO)
    
    # Create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add the handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logging.info(f"Logging initialized. Output writing to {log_file}")
    return log_file

def get_frontend_parity_data(symbol="^NSEI", resolution="4", data_source="yfinance", lookback_bars=5000, from_date=None, to_date=None):
    """Fetch data exactly how the frontend's /fetch_candles endpoint does."""
    logging.info(f"Fetching {resolution}m data for {symbol} using {data_source} with {lookback_bars} lookback bars...")
    client = get_data_client(data_source)
    
    if not to_date:
        to_date = datetime.now().strftime("%Y-%m-%d")
        
    # Simulate frontend's "first available candle" by going back as far as YFinance allows for 4m (60 days)
    # The frontend calculates lookback_days based on lookback_bars
    lookback_days = max(1, lookback_bars // 90) # ~90 bars per day for 4m
    lookback_days = int(lookback_days * 4.0) + 30
    
    if data_source == 'yfinance':
        if resolution in ['1', '4']:
            lookback_days = min(lookback_days, 60)
            
    if not from_date:
        # If no from_date is provided, we want to fetch the maximum allowed history
        # and start the simulation from the very first candle we get.
        # We don't need to add lookback_days to this because we are already fetching the max history.
        from_dt = datetime.now() - timedelta(days=lookback_days)
        start_str = from_dt.strftime("%Y-%m-%d")
        # Set target_from_dt to the same start date so we don't filter out any events
        target_from_dt = from_dt
    else:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d")
        target_from_dt = from_dt
        adjusted_from_dt = from_dt - timedelta(days=lookback_days)
        start_str = adjusted_from_dt.strftime("%Y-%m-%d")
        
    end_str = to_date
    
    logging.info(f"Calculated date range: {start_str} to {end_str} (lookback: {lookback_days} days)")
    
    df = client.fetch_data(symbol, start_str, end_str, interval=resolution)
    
    # FALLBACK LOGIC: If explicit fetch returned empty (likely due to invalid/old date range),
    # automatically fetch the *latest* available data so the user sees something.
    if (df is None or df.empty) and data_source == 'yfinance':
        logging.warning(f"[Replay] Data empty for range {start_str} to {end_str}. Attempting fallback to latest available data...")
        
        # Define safe fallback duration based on resolution
        fallback_days = 5 # Default for 1m/4m
        if resolution in ['2', '5', '15', '30']: fallback_days = 55
        elif resolution in ['60', '240']: fallback_days = 700
        elif resolution in ['1D', 'D', 'W', 'M']: fallback_days = 365
        
        fallback_from = datetime.now() - timedelta(days=fallback_days)
        fallback_from_str = fallback_from.strftime('%Y-%m-%d')
        # Use current time as end date to ensure we get data
        fallback_to_str = datetime.now().strftime('%Y-%m-%d')
        
        logging.info(f"[Replay] Fallback fetch: {fallback_from_str} to {fallback_to_str}")
        df = client.fetch_data(symbol, fallback_from_str, fallback_to_str, interval=resolution)
    
    if df is None or df.empty:
        logging.error("Failed to fetch data or dataframe is empty.")
        return [], target_from_dt, target_from_dt
        
    # Ensure 'time' column exists for the study tool
    if 'timestamp' in df.columns and 'time' not in df.columns:
        df['time'] = df['timestamp']
        
    candles = df.to_dict('records')
    logging.info(f"Loaded {len(candles)} candles from {data_source}.")
    
    # DETERMINE ACTUAL START: Use the first candle's timestamp as the true start
    # This handles cases where YFinance clamped an old date to its maximum available data
    if len(candles) > 0:
        actual_start_ts = int(candles[0]['time'])
        actual_start_dt = datetime.fromtimestamp(actual_start_ts)
        
        # If the actual first candle is newer than the requested from_date, use the actual start
        requested_ts = int(target_from_dt.timestamp())
        if actual_start_ts > requested_ts:
            logging.info(f"[Simulation] YFinance clamped date: requested {from_date or 'default'} ({requested_ts}) -> actual {actual_start_dt.strftime('%Y-%m-%d')} ({actual_start_ts})")
            target_from_dt = actual_start_dt
        else:
            target_from_dt = datetime.fromtimestamp(requested_ts)
    else:
        actual_start_ts = int(target_from_dt.timestamp())
        
    logging.info(f"Simulation will track events from: {target_from_dt.strftime('%Y-%m-%d')} (ts: {int(target_from_dt.timestamp())})")
        
    return candles, target_from_dt, actual_start_dt

def run_simulation(symbol="^NSEI", resolution="4", data_source="yfinance", from_date=None, to_date=None, lookback_bars=5000):
    log_file = setup_logging()
    logging.info(f"Starting simulation run for {symbol} at {resolution}m resolution")
    
    # Setup - Fetch data with frontend parity
    candles, target_from_dt, actual_start_dt = get_frontend_parity_data(
        symbol=symbol, 
        resolution=resolution, 
        data_source=data_source, 
        lookback_bars=lookback_bars,
        from_date=from_date,
        to_date=to_date
    )
    
    if not candles:
        logging.error("No data available to run simulation.")
        return
        
    # Get dynamic scale ratio just like the frontend
    try:
        # The frontend passes "NIFTY 50" to get_dynamic_scale_ratio even if the YFinance symbol is "^NSEI"
        config_symbol = "NIFTY 50" if symbol == "^NSEI" else symbol
        scale_ratio = get_dynamic_scale_ratio(config_symbol, resolution)
        logging.info(f"Dynamically resolved scale_ratio for {config_symbol} at {resolution}m: {scale_ratio}")
    except Exception as e:
        logging.warning(f"Failed to get dynamic scale ratio: {e}. Falling back to 3.6603")
        scale_ratio = 3.6603
        
    study = AngularPriceCoverageStudy(config={
        'symbol': symbol,
        'resolution': resolution,
        'scale_ratio': scale_ratio,
        'left_bars': 5, 
        'right_bars': 5,
        'successive_closes_required': 2
    })
    
    logging.info("Starting simulation...")
    
    # Run through all candles - maintain state like frontend progressive replay
    all_intersection_events = []
    target_start_ts = int(target_from_dt.timestamp())
    
    # Replicate exact frontend API behavior
    study_cache = {'index': -1, 'state': None}
    
    for i in range(len(candles)):
        # Determine if this is sequential processing (like frontend progressive replay)
        is_sequential = study_cache['index'] == i - 1 and study_cache['state'] is not None
        
        if is_sequential:
            # FAST PATH: Restore state and process single bar (like frontend)
            study.restore_state(study_cache['state'])
            result = study.process_bar(candles, i, state=None)  # State already restored
            
            # Update cache (like frontend)
            study_cache['index'] = i
            study_cache['state'] = result.get('state', {})
            
        else:
            # SLOW PATH: Rebuild from 0 to current bar (like frontend reset)
            logging.info(f"[Simulation] Slow path: Rebuilding from 0 to {i}")
            study_cache = {'index': -1, 'state': None}
            
            # Single call - process_bar auto-initializes history up to bar_index
            result = study.process_bar(candles, i, state=None)
            
            if result:
                study_cache['index'] = i
                study_cache['state'] = result.get('state', {})
        
        # Collect the exact frontend-bound intersection events
        if result and 'intersection_events' in result:
            for event in result['intersection_events']:
                # Only include events that occur on or after the requested from_date
                if event['time'] >= target_start_ts:
                    all_intersection_events.append(event)
        
        if i > 0 and i % 500 == 0:
            logging.info(f"Processed {i}/{len(candles)} bars...")
            
    logging.info(f"Processed {len(candles)}/{len(candles)} bars...")
    logging.info("Simulation complete.")
    
    # Export logs
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    csv_path = os.path.join(log_dir, "simulation_events.csv")
    
    # Enrich with forward-looking outcomes before exporting
    logging.info("Enriching events with forward-looking outcomes (MFE/MAE)...")
    study.event_logger.enrich_with_forward_outcomes(candles)
    
    # Create a lookup for enriched events by timestamp and price
    enriched_events = {}
    for event in study.event_logger.events:
        key = (event.timestamp, event.price)
        enriched_events[key] = {
            'mfe_10': getattr(event, 'mfe_10', 0),
            'mae_10': getattr(event, 'mae_10', 0),
            'bars_elapsed': getattr(event, 'bars_elapsed', 0)
        }
    
    # Write the exact frontend intersection events to CSV
    import csv
    if all_intersection_events:
        # Sort events chronologically by timestamp for pure chronological order
        all_intersection_events = sorted(all_intersection_events, key=lambda e: e['time'])
        
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['#', 'Time', 'Fan', 'Fraction', 'Price', 'Type', 'Details', 'MFE_10', 'MAE_10', 'bars_elapsed'])
            
            # Use IST timezone for formatting to match frontend
            ist = pytz.timezone('Asia/Kolkata')
            
            for i, event in enumerate(all_intersection_events):
                # Convert timestamp to IST datetime
                # Assuming event['time'] is a unix timestamp in seconds
                dt_utc = datetime.fromtimestamp(event['time'], pytz.utc)
                dt_ist = dt_utc.astimezone(ist)
                
                # Format: 3/11/2026, 11:07:00 AM
                m = dt_ist.month
                d = dt_ist.day
                y = dt_ist.year
                time_str = dt_ist.strftime("%I:%M:%S %p")
                if time_str.startswith('0'):
                    time_str = time_str[1:]
                    
                dt_str = f"{m}/{d}/{y}, {time_str}"
                
                # Format details exactly like frontend JS does
                details_str = str(event.get('details', '')).replace(',', ';')
                
                # Get enriched data - match by timestamp and price
                event_key = (event['time'], event.get('price', 0))
                enriched = enriched_events.get(event_key, {})
                mfe_10 = enriched.get('mfe_10', 0)
                mae_10 = enriched.get('mae_10', 0)
                bars_elapsed = enriched.get('bars_elapsed', 0)
                
                writer.writerow([
                    i + 1,
                    dt_str,
                    event.get('fan', ''),
                    event.get('fraction', ''),
                    f"{event.get('price', 0):.2f}",
                    event.get('type', ''),
                    details_str,
                    f"{mfe_10:.4f}" if mfe_10 else "0",
                    f"{mae_10:.4f}" if mae_10 else "0",
                    bars_elapsed
                ])
                
        logging.info(f"Exported {len(all_intersection_events)} identical frontend events to {csv_path}")
    else:
        logging.warning("No intersection events found to export.")
    
    # Print stats
    stats = study.event_logger.get_statistics()
    logging.info("\n--- Simulation Statistics ---")
    logging.info(json.dumps(stats, indent=2))
    
    # Check if we have any confirmed breaches
    breaches = study.event_logger.get_events_by_type(EventType.BREACH_CONFIRMED)
    logging.info(f"\nConfirmed Breaches: {len(breaches)}")
    if breaches:
        logging.info(f"Sample breach: {breaches[0].to_dict()}")
        
    logging.info(f"Simulation run finished. Log saved to {log_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Gann Angular Price Coverage Simulation")
    parser.add_argument("--symbol", type=str, default="^NSEI", help="Ticker symbol (e.g., ^NSEI, RELIANCE.NS)")
    parser.add_argument("--resolution", type=str, default="4", help="Timeframe resolution (e.g., 1, 4, 5, 15, 60, D)")
    parser.add_argument("--source", type=str, default="yfinance", choices=["yfinance", "dhan"], help="Data source")
    parser.add_argument("--from-date", type=str, default=None, help="Start date (YYYY-MM-DD). Defaults to earliest available data.")
    parser.add_argument("--to-date", type=str, default=None, help="End date (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--lookback", type=int, default=5000, help="Number of lookback bars for context building")
    
    args = parser.parse_args()
    
    run_simulation(
        symbol=args.symbol,
        resolution=args.resolution,
        data_source=args.source,
        from_date=args.from_date,
        to_date=args.to_date,
        lookback_bars=args.lookback
    )
