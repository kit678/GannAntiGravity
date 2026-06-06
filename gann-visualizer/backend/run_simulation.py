import sys
import os
import json
import logging
import argparse
import shutil
from datetime import datetime, timedelta, timezone
import pandas as pd
import numpy as np
import pytz

# Add current directory to path so we can import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from study_tool.angular_coverage_study import AngularPriceCoverageStudy

# Warmup constants: must match main.py WARMUP_DAYS exactly for corpus ↔ frontend parity.
# This is the authoritative source for simulation lookback — not the old lookback_bars formula.
WARMUP_DAYS = {
    "1":  30,
    "4":  30,
    "5":  75,
    "15": 120,
    "30": 120,
    "60": 90,
    "240": 250,
    "1D": 365,
    "D":  365,
    "W":  730,
    "M":  1825,
}
from study_tool.event_logger import EventType
from main import get_data_client, get_dynamic_scale_ratio
from scripts.run_paths import build_run_dir, build_run_id

def setup_logging():
    """Set up logging to both console and a file in the logs directory."""
    log_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "logs", "backend"
    )
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

def get_frontend_parity_data(symbol="^NSEI", resolution="4", data_source="yfinance", lookback_bars=5000, from_date=None, to_date=None, warmup_days=0):
    """Fetch data exactly how the frontend's /fetch_candles endpoint does."""
    logging.info(f"Fetching {resolution}m data for {symbol} using {data_source} with {lookback_bars} lookback bars...")
    client = get_data_client(data_source)
    
    if not to_date:
        to_date = datetime.now().strftime("%Y-%m-%d")
        
    # Use from_date-anchored warmup strategy (matches main.py /fetch_candles exactly).
    # The user's chosen from_date is always the reference point.
    # Subtract WARMUP_DAYS[resolution] calendar days to get the warmup start.
    if from_date:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        target_from_dt = from_dt
        from_dt_utc = from_dt
        ideal_warmup_from_dt = from_dt_utc - timedelta(days=warmup_days)

        # Check if YFinance can provide this warmup depth
        SOURCE_HISTORY_LIMITS = {
            "yfinance_1m": 8,
            "yfinance_4m": 8,
            "yfinance_other": 700,
        }
        source_key = f"yfinance_{resolution}" if data_source == "yfinance" else "unlimited"
        if data_source == 'yfinance' and resolution not in ['1', '4']:
            source_key = "yfinance_other"
        elif data_source == 'yfinance' and resolution == '4':
            source_key = "yfinance_4m"
        elif data_source == 'yfinance':
            source_key = "yfinance_1m"

        source_max_days = SOURCE_HISTORY_LIMITS.get(source_key, 700)

        if warmup_days > source_max_days:
            # Source can't provide enough warmup — use today-anchored fetch
            warmup_from_dt = datetime.now() - timedelta(days=source_max_days)
            logging.warning(f"[Simulation] {data_source} {resolution}m has ~{source_max_days} days "
                           f"of history (requested {warmup_days} days warmup). Using today-anchored fetch.")
        else:
            warmup_from_dt = ideal_warmup_from_dt

        start_str = warmup_from_dt.strftime("%Y-%m-%d")
    else:
        # No from_date provided — fetch maximum available history (today-anchored)
        target_from_dt = datetime.now()
        lookback_days = WARMUP_DAYS.get(resolution, 250)
        if data_source == 'yfinance' and resolution in ['1', '4']:
            lookback_days = min(lookback_days, 8)
        from_dt = datetime.now() - timedelta(days=lookback_days)
        start_str = from_dt.strftime("%Y-%m-%d")
        target_from_dt = from_dt
        
    end_str = to_date

    # log warmup_days consistently whether from_date was provided or not
    _log_days = warmup_days if from_date else lookback_days
    logging.info(f"Calculated date range: {start_str} to {end_str} (lookback: {_log_days} days)")
    
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

def run_simulation(symbol="^NSEI", resolution="4", data_source="yfinance", from_date=None, to_date=None, lookback_bars=5000, left_bars=5, right_bars=5, warmup_days=0, timezone="UTC"):
    log_file = setup_logging()
    logging.info(f"Starting simulation run for {symbol} at {resolution}m resolution")
    
    # Setup - Fetch data with frontend parity
    candles, target_from_dt, actual_start_dt = get_frontend_parity_data(
        symbol=symbol, 
        resolution=resolution, 
        data_source=data_source, 
        lookback_bars=lookback_bars,
        from_date=from_date,
        to_date=to_date,
        warmup_days=warmup_days
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
        'left_bars': left_bars, 
        'right_bars': right_bars,
        'successive_closes_required': 2,
        'run_mode': 'simulation',
        'timezone': timezone
    })
    
    logging.info("Starting simulation...")
    
    # Run through all candles - maintain state like frontend progressive replay
    all_intersection_events = []
    target_start_ts = int(target_from_dt.timestamp())
    
    # Replicate exact frontend API behavior, but optimize for backend simulation
    # We don't need to serialize/deserialize state on every step since we hold the study instance
    
    # Find the index corresponding to the target_from_dt
    start_index = 0
    for i, c in enumerate(candles):
        if int(c['time']) >= target_start_ts:
            start_index = i
            break
            
    logging.info(f"Simulation starting at bar index {start_index} (total bars: {len(candles)})")
    
    # Initialize history up to the start index (just like frontend does before replay)
    if start_index > 0:
        logging.info(f"Initializing history up to bar {start_index}...")
        # We pass the subset of candles up to start_index
        study.initialize_history(candles[:start_index])
        study._initialized = True
    
    for i in range(start_index, len(candles)):
        # Process single bar sequentially
        result = study.process_bar(candles, i, state=None)
        
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
    
    # Build partitioned run directory
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    runs_base = os.path.join(repo_root, "logs", "backend", "runs")
    run_id = build_run_id()
    run_dir = build_run_dir(
        base=runs_base,
        instrument=symbol,
        timeframe=resolution,
        run_id=run_id,
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    csv_path = str(run_dir / "events.csv")
    # Enrich with forward-looking outcomes before exporting
    logging.info("Enriching events with forward-looking outcomes (MFE/MAE)...")
    study.event_logger.enrich_with_forward_outcomes(candles)

    for ev in study.event_logger.events:
        ev.instrument = symbol
        ev.timeframe = resolution

    # Create a lookup for enriched events by timestamp+rounded_price and timestamp+fan_id
    enriched_events = {}
    for event in study.event_logger.events:
        fan_id = (event.details or {}).get('fan_id', '')
        enrichment = {
            'mfe_5':  getattr(event, 'mfe_5',  0) or 0,
            'mae_5':  getattr(event, 'mae_5',  0) or 0,
            'mfe_10': getattr(event, 'mfe_10', 0) or 0,
            'mae_10': getattr(event, 'mae_10', 0) or 0,
            'mfe_20': getattr(event, 'mfe_20', 0) or 0,
            'mae_20': getattr(event, 'mae_20', 0) or 0,
            'mfe_50': getattr(event, 'mfe_50', 0) or 0,
            'mae_50': getattr(event, 'mae_50', 0) or 0,
            'bars_elapsed': getattr(event, 'bars_elapsed', 0) or 0,
            'direction': getattr(event, 'direction', '') or '',
            'exc_up_10': getattr(event, 'exc_up_10', None),
            'exc_down_10': getattr(event, 'exc_down_10', None),
            'reversal_outcome': getattr(event, 'reversal_outcome', None),
        }
        enriched_events[(event.timestamp, round(event.price, 2))] = enrichment
        if fan_id:
            enriched_events[(event.timestamp, fan_id)] = enrichment

        # Build direct reversal_outcome lookup from event_logger + candle fallback  
    logger_reversal = {}
    for levent in study.event_logger.events:
        lfan = (levent.details or {}).get('fan_id', '')
        if lfan and getattr(levent, 'reversal_outcome', None):
            logger_reversal[(levent.timestamp, lfan)] = levent.reversal_outcome

    candle_idx_by_ts = {int(c['time']): i for i, c in enumerate(candles)}

    def compute_first_break(ievent: dict, n_bars: int = 10):
        fraction = ievent.get('fraction')
        if str(fraction if fraction is not None else '') != '0.25':
            return None
        etype = ievent.get('type', '')
        if etype not in ('SUPPORT_TEST', 'RESISTANCE_TEST', 'TARGET_HIT'):
            return None
        event_high = ievent.get('high')
        event_low = ievent.get('low')
        if not event_high or not event_low:
            return None
        fan = ievent.get('fan', '')
        is_ha = '(H' in fan
        if not is_ha and '(L' not in fan:
            return None
        if etype == 'SUPPORT_TEST':
            exp = 'up' if is_ha else 'down'
        elif etype == 'RESISTANCE_TEST':
            exp = 'down' if is_ha else 'up'
        else:
            exp = 'up' if is_ha else 'down'
        ts = int(ievent['time'])
        idx = candle_idx_by_ts.get(ts)
        if idx is None:
            return None
        end_i = min(idx + n_bars + 1, len(candles))
        for i in range(idx + 1, end_i):
            cl = candles[i].get('close', 0)
            if exp == 'up':
                if cl > event_high:
                    return 'WIN'
                if cl < event_low:
                    return 'LOSS'
            else:
                if cl < event_low:
                    return 'WIN'
                if cl > event_high:
                    return 'LOSS'
        return None

# Write the exact frontend intersection events to CSV
    import csv
    if all_intersection_events:
        # Sort events chronologically by timestamp for pure chronological order
        all_intersection_events = sorted(all_intersection_events, key=lambda e: e['time'])
        
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['#', 'Time', 'Fan', 'Fraction', 'Price', 'Type', 'Details',
                             'Open', 'High', 'Low', 'Close', 'Active_Angles',
                             'Cluster', 'Zone', 'Zone_Highest_Close', 'Zone_Lowest_Close',
                             'Next_Angle_Line',
                             'Instrument', 'Timeframe', 'Start_Date',
                             'MFE_5', 'MAE_5', 'MFE_10', 'MAE_10',
                             'MFE_20', 'MAE_20', 'MFE_50', 'MAE_50',
                             'Raw_Timestamp', 'Direction', 'bar_index', 'bars_elapsed',
                             'Exc_Up_10', 'Exc_Down_10', 'Reversal_Outcome',
                             'anchor_bar_index', 'scale_ratio', 'anchor_price',
                         'origin_bar_index', 'origin_price'])
            
            # Use configured timezone for timestamp formatting
            tz = pytz.timezone(timezone)
            
            for i, event in enumerate(all_intersection_events):
                # Convert timestamp to configured timezone
                dt_utc = datetime.fromtimestamp(event['time'], pytz.utc)
                dt_tz = dt_utc.astimezone(tz)
                
                # Format: 3/11/2026, 11:07:00 AM
                m = dt_tz.month
                d = dt_tz.day
                y = dt_tz.year
                time_str = dt_tz.strftime("%I:%M:%S %p")
                if time_str.startswith('0'):
                    time_str = time_str[1:]
                    
                dt_str = f"{m}/{d}/{y}, {time_str}"
                
                # Format details exactly like frontend JS does
                details_str = str(event.get('details', '')).replace(',', ';')
                
                # Get enriched data (MFE/MAE) from event_logger lookup
                event_key = (event['time'], round(event.get('price', 0), 2))
                enriched = enriched_events.get(event_key, {})
                if not enriched:
                    fan_id = event.get('fan', '')
                    if fan_id:
                        fan_key = (event['time'], fan_id)
                        enriched = enriched_events.get(fan_key, {})
                if not enriched:
                    logging.debug(f"No enriched data for event at time={event.get('time')} price={event.get('price', 0):.2f}")
                mfe_5  = enriched.get('mfe_5',  0)
                mae_5  = enriched.get('mae_5',  0)
                mfe_10 = enriched.get('mfe_10', 0)
                mae_10 = enriched.get('mae_10', 0)
                mfe_20 = enriched.get('mfe_20', 0)
                mae_20 = enriched.get('mae_20', 0)
                mfe_50 = enriched.get('mfe_50', 0)
                mae_50 = enriched.get('mae_50', 0)
                bars_elapsed = enriched.get('bars_elapsed', 0)
                direction = enriched.get('direction', '')
                reversal_outcome = enriched.get('reversal_outcome') or compute_first_break(event) or ''
                exc_up_10 = enriched.get('exc_up_10')
                exc_down_10 = enriched.get('exc_down_10')
                bar_idx = event.get('bar_index', '')

                writer.writerow([
                    i + 1,
                    dt_str,
                    event.get('fan', ''),
                    event.get('fraction', ''),
                    f"{event.get('price', 0):.2f}",
                    event.get('type', ''),
                    details_str,
                    f"{event.get('open', 0):.2f}",
                    f"{event.get('high', 0):.2f}",
                    f"{event.get('low', 0):.2f}",
                    f"{event.get('close', 0):.2f}",
                    json.dumps(event.get('activeAngles', {})),
                    event.get('cluster', False),
                    event.get('zone', ''),
                    f"{event.get('zoneExtremes', {}).get('highest_close', 0):.2f}" if event.get('zoneExtremes', {}).get('highest_close') else '',
                    f"{event.get('zoneExtremes', {}).get('lowest_close', 0):.2f}" if event.get('zoneExtremes', {}).get('lowest_close') else '',
                    event.get('nextAngleLine', ''),
                    symbol,
                    resolution,
                    from_date,
                    f"{mfe_5:.4f}"  if isinstance(mfe_5, (int, float)) and mfe_5 else "",
                    f"{mae_5:.4f}"  if isinstance(mae_5, (int, float)) and mae_5 else "",
                    f"{mfe_10:.4f}" if isinstance(mfe_10, (int, float)) and mfe_10 else "",
                    f"{mae_10:.4f}" if isinstance(mae_10, (int, float)) and mae_10 else "",
                    f"{mfe_20:.4f}" if isinstance(mfe_20, (int, float)) and mfe_20 else "",
                    f"{mae_20:.4f}" if isinstance(mae_20, (int, float)) and mae_20 else "",
                    f"{mfe_50:.4f}" if isinstance(mfe_50, (int, float)) and mfe_50 else "",
                    f"{mae_50:.4f}" if isinstance(mae_50, (int, float)) and mae_50 else "",
                    int(event['time']),
                    direction,
                    bar_idx,
                    bars_elapsed,
                    f"{exc_up_10:.4f}" if exc_up_10 is not None else "",
                    f"{exc_down_10:.4f}" if exc_down_10 is not None else "",
                    reversal_outcome,
                    # Fan geometry for true angular fan ray reconstruction
                    event.get('anchor_bar_index', ''),
                    event.get('scale_ratio', ''),
                    event.get('anchor_price', ''),
                    event.get('origin_bar_index', ''),
                    event.get('origin_price', ''),
                ])
                
        logging.info(f"Exported {len(all_intersection_events)} identical frontend events to {csv_path}")

        # Export raw OHLC candles for EMA crossover and other indicator-based hypotheses
        candles_csv_path = str(run_dir / "candles.csv")
        # Filter to candles within the tracking window only (not the full warmup period)
        if target_start_ts is not None:
            filtered_candles = [c for c in candles if int(c['time']) >= target_start_ts]
        else:
            filtered_candles = candles
        candles_df = pd.DataFrame(filtered_candles)
        candles_df.to_csv(candles_csv_path, index=False)
        logging.info(f"Exported {len(candles_df)} candles to {candles_csv_path}")

        # Export hypothesis navigator JSON with fan geometry
        hypothesis_json_path = str(run_dir / "hypothesis_events.json")
        study.event_logger.export_hypothesis_json(hypothesis_json_path, symbol=symbol, resolution=resolution)
        logging.info(f"Exported hypothesis navigator JSON to {hypothesis_json_path}")
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

    # Mirror session artifacts into the run directory for reproducibility
    try:
        session_log = os.path.join(repo_root, "logs", "backend", "simulation_run.log")
        simulation_trace_log = os.path.join(repo_root, "logs", "backend", "simulation_trace.log")
        replay_trace_log = os.path.join(repo_root, "logs", "backend", "replay_trace.log")
        if os.path.exists(session_log):
            shutil.copy2(session_log, run_dir / "simulation_run.log")
        if os.path.exists(simulation_trace_log):
            shutil.copy2(simulation_trace_log, run_dir / "simulation_trace.log")
        if os.path.exists(replay_trace_log):
            shutil.copy2(replay_trace_log, run_dir / "replay_trace.log")
    except Exception as e:
        logging.warning(f"Failed to mirror logs to run dir: {e}")

    logging.info(f"Simulation run finished. Log saved to {log_file}")
    return str(run_dir)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Gann Angular Price Coverage Simulation")
    parser.add_argument("--symbol", type=str, default="^NSEI", help="Ticker symbol (e.g., ^NSEI, RELIANCE.NS)")
    parser.add_argument("--resolution", type=str, default="4", help="Timeframe resolution (e.g., 1, 4, 5, 15, 60, D)")
    parser.add_argument("--source", type=str, default="yfinance", choices=["yfinance", "dhan", "binance"], help="Data source")
    parser.add_argument("--from-date", type=str, default=None, help="Start date (YYYY-MM-DD). Defaults to earliest available data.")
    parser.add_argument("--to-date", type=str, default=None, help="End date (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--lookback", type=int, default=5000, help="Number of lookback bars for context building")
    parser.add_argument("--left-bars", type=int, default=5, help="Number of bars to the left for pivot detection (default: 5)")
    parser.add_argument("--right-bars", type=int, default=5, help="Number of bars to the right for pivot confirmation (default: 5)")
    parser.add_argument("--warmup-days", type=int, default=0, help="Days of history to fetch before from-date for macro fans. Defaults to 0.")
    parser.add_argument("--timezone", type=str, default="UTC", help="Timezone for output timestamps (default: UTC). Use 'Asia/Kolkata' for IST.")
    
    args = parser.parse_args()
    
    run_simulation(
        symbol=args.symbol,
        resolution=args.resolution,
        data_source=args.source,
        from_date=args.from_date,
        to_date=args.to_date,
        lookback_bars=args.lookback,
        left_bars=args.left_bars,
        right_bars=args.right_bars,
        warmup_days=args.warmup_days,
        timezone=args.timezone
    )
