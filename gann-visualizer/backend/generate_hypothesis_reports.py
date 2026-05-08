import pandas as pd
import sys
import os
import json
import datetime

sys.path.append(r"C:\Dev\GannTesting\gann-visualizer\backend")
from analysis.strategy_analyzer import (
    StrongSRHypothesis,
    TargetProgressionHypothesis,
    QuarterReversalAnomalyHypothesis,
    ConfluenceBounceHypothesis,
    PostBreachPullbackHypothesis
)


def _row_to_fan_state(active_angles_str, entry, df=None):
    """Extract fan geometry from Active_Angles JSON string."""
    try:
        active_angles = json.loads(active_angles_str)
    except (json.JSONDecodeError, TypeError):
        return {'fans': [], 'intersections': []}

    # Look up bar_index from df if not in entry
    bar_index = entry.get('bar_index', 0)
    if bar_index == 0 and df is not None:
        time_key = str(entry.get('time', ''))
        if not time_key:
            time_key = str(entry.get('breach_time', ''))
        if time_key:
            match = df[df['Time'] == time_key]
            if not match.empty and pd.notna(match.iloc[0]['bar_index']):
                bar_index = int(match.iloc[0]['bar_index'])

    # Group by fan identity
    fan_groups = {}
    for key, price in active_angles.items():
        if not price or price <= 0:
            continue
        parts = key.rsplit('_', 1)
        if len(parts) != 2:
            continue
        fan_id, fraction_str = parts
        if fan_id not in fan_groups:
            fan_groups[fan_id] = []
        fan_groups[fan_id].append({
            'fraction': str(fraction_str),
            'price': float(price)
        })

    fans = []
    for fan_id, lines in fan_groups.items():
        priority_label = fan_id
        fan = {
            'fan_id': fan_id,
            'display_label': priority_label,
            'priority': 1,
            'lines': []
        }

        for line in lines:
            fraction = line['fraction']
            price = float(line['price'])
            fraction_val = float(fraction) if fraction not in ('horizontal', 'full_coverage', 'main') else None
            color_map = {'0.875': '#2196F3', '0.75': '#4CAF50', '0.5': '#FF9800', '0.25': '#F44336'}
            color = color_map.get(fraction, '#888888')
            width = 4 if fraction == '0.5' else 2

            fan['lines'].append({
                'id': f'{fan_id}_{fraction}',
                'fraction': fraction_val,
                'points': [
                    {'time': bar_index - 500, 'price': price},
                    {'time': bar_index + 2000, 'price': price}
                ],
                'options': {
                    'linecolor': color,
                    'linewidth': width,
                    'linestyle': 1,
                    'extendRight': True
                }
            })

        fans.append(fan)

    # Build intersection record
    intersections = []
    event_price = entry.get('target_price') or entry.get('Price', 0)
    if event_price:
        intersections.append({
            'fan_id': entry.get('fan', ''),
            'fraction': entry.get('fraction', ''),
            'price': float(event_price),
            'timestamp': entry.get('bar_index', 0),
            'type': 'target_attempt'
        })

    return {'fans': fans, 'intersections': intersections}


def _get_metadata(df):
    """Extract instrument, timeframe, start_date, end_date from dataframe once."""
    instrument = df['Instrument'].iloc[0] if not df.empty and 'Instrument' in df.columns else "Unknown"
    timeframe = df['Timeframe'].iloc[0] if not df.empty and 'Timeframe' in df.columns else "Unknown"
    if not df.empty and 'Start_Date' in df.columns:
        start_date_str = df['Start_Date'].iloc[0]
    else:
        try:
            start_date_str = pd.to_datetime(df['Time'].iloc[0]).strftime('%Y-%m-%d')
        except:
            start_date_str = "Unknown"
    try:
        end_date_str = pd.to_datetime(df['Time'].iloc[-1]).strftime('%Y-%m-%d')
    except:
        end_date_str = "Unknown"
    return instrument, timeframe, start_date_str, end_date_str


def _row_to_event_record(entry, fan_display_label, active_angles_str, df=None):
    """Convert a single event dict to the frontend's expected event format with fan geometry."""
    fan_id = entry.get('fan', 'Unknown')
    fan_state = _row_to_fan_state(active_angles_str, entry, df)

    return {
        'event_id': int(entry.get('event_id', 0)),
        'type': 'retroactive' if entry.get('is_retro') else 'live',
        'timestamp': float(pd.to_datetime(entry['time']).timestamp()) if entry.get('time') else 0.0,
        'datetime': str(entry.get('time', '')),
        'fan': str(entry.get('fan', '')),
        'fan_identity': str(fan_id),
        'display_label': str(fan_display_label),
        'fraction': str(entry.get('fraction', '')),
        'target_price': float(entry.get('target_price', 0)),
        'outcome': str(entry.get('outcome', '')),
        'is_retro': bool(entry.get('is_retro', False)),
        'breach_time': str(entry.get('breach_time', '')),
        'breach_fraction': str(entry.get('breach_fraction', '')),
        'breach_price': float(entry.get('breach_price', 0)),
        'breach_direction': str(entry.get('breach_direction', '')),
        'mfe': float(entry.get('mfe_10', 0)),
        'mae': float(entry.get('mae_10', 0)),
        'mfe_10': float(entry.get('mfe_10', 0)),
        'mae_10': float(entry.get('mae_10', 0)),
        'O': float(entry.get('O', 0)),
        'H': float(entry.get('H', 0)),
        'L': float(entry.get('L', 0)),
        'C': float(entry.get('C', 0)),
        'bar_index': int(entry.get('bar_index', 0)) if 'bar_index' in entry else 0,
        'fan_state': fan_state
    }


csv_path = r"C:\Dev\GannTesting\logs\backend\runs\_NSEI\4\2026-05-06_94787c\events.csv"
if len(sys.argv) > 1:
    csv_path = sys.argv[1]

if not os.path.exists(csv_path):
    print(f"Error: Could not find events CSV at {csv_path}")
    sys.exit(1)

df = pd.read_csv(csv_path)

hypotheses = [
    StrongSRHypothesis(),
    QuarterReversalAnomalyHypothesis(),
    ConfluenceBounceHypothesis(),
    TargetProgressionHypothesis(),
    PostBreachPullbackHypothesis()
]

# Organize reports inside the specific run folder, right next to the events.csv
output_dir = os.path.join(os.path.dirname(csv_path), "hypothesis_reports")
os.makedirs(output_dir, exist_ok=True)

# Build time -> Active_Angles lookup from raw df (used by all hypotheses)
# Events don't have bar_index but have 'time'; match by Time column
time_to_active_angles = {}
if 'Time' in df.columns and 'Active_Angles' in df.columns:
    for _, row in df.iterrows():
        time_val = row['Time']
        if pd.notna(time_val) and time_val:
            time_to_active_angles[str(time_val)] = row['Active_Angles']

for hyp in hypotheses:
    result = hyp.evaluate(df)
    detailed_log = result.get("detailed_log", [])
    
    # Sort chronologically
    if hyp.name == "Post-Breach Pullback Continuation":
        detailed_log = sorted(detailed_log, key=lambda x: pd.to_datetime(x['breach_time']))
    else:
        detailed_log = sorted(detailed_log, key=lambda x: pd.to_datetime(x['time']))
        
    live_events = [e for e in detailed_log if not e.get('is_retro')]
    retro_events = [e for e in detailed_log if e.get('is_retro')]
    
    filename = hyp.name.lower().replace(' ', '_').replace('/', '').replace('(', '').replace(')', '') + "_report.txt"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w') as f:
        f.write(f"=== {hyp.name.upper()} VERBOSE REPORT ===\n")
        f.write("=== REPRODUCTION INSTRUCTIONS ===\n")

        instrument, timeframe, start_date_str, end_date_str = _get_metadata(df)

        f.write(f"To replicate these results on the frontend, use the following parameters:\n")
        f.write(f"Symbol:     {instrument}\n")
        f.write(f"Timeframe:  {timeframe}m\n")
        f.write(f"Start Date: {start_date_str}\n")
        f.write(f"End Date:   {end_date_str}\n")
        f.write("============================================================\n\n")
        
        f.write(f"Overall Sample Size: {result['sample_size']}\n")
        f.write(f"Overall Win Rate:    {result['win_rate']:.2%}\n\n")
        f.write(f"Live Sample Size:    {result.get('live_sample_size', 0)}\n")
        f.write(f"Live Win Rate:       {result.get('live_win_rate', 0):.2%}\n\n")
        f.write(f"Retro Sample Size:   {result.get('retro_sample_size', 0)}\n")
        f.write(f"Retro Win Rate:      {result.get('retro_win_rate', 0):.2%}\n")
        f.write("=" * 60 + "\n\n")
        
        def write_event(entry, is_retro_section=False):
            retro_flag = " [RETROACTIVE]" if entry.get('is_retro') else ""
            
            if hyp.name == "Target Progression Probability":
                if entry['outcome'] == 'WIN':
                    # For wins, 'fraction' is the target that was hit, and we need to show origin -> target
                    origin_angle = entry.get('breach_fraction', 'Unknown')
                    target_hit = entry['fraction']
                    f.write(f"TARGET ATTEMPT{retro_flag}: {entry['time']} | {entry['fan']} ({origin_angle}) -> {target_hit} @ Price: {entry.get('target_price', 'N/A')}\n")
                else:
                    # For misses, 'fraction' is the origin angle, and 'next_angle' is the target that was missed
                    origin_angle = entry['fraction']
                    target_missed = entry['next_angle']
                    f.write(f"TARGET ATTEMPT{retro_flag}: {entry['time']} | {entry['fan']} ({origin_angle}) -> {target_missed} @ Price: {entry.get('target_price', 'N/A')}\n")
                    
                if is_retro_section:
                    f.write(f"   -> [INFO] This event was generated retroactively during a sweep.\n")
                if entry.get('breach_time'):
                    dir_str = entry.get('breach_direction', '').upper()
                    f.write(f"      Following Breach: {entry['breach_time']} ({entry['breach_fraction']}) | Dir: {dir_str} | Price: {entry.get('breach_price', 'N/A')}\n")
                f.write(f"      Outcome: {entry['outcome']}\n")
                if entry['outcome'] == 'WIN':
                    f.write(f"      Metrics: MFE: {entry.get('mfe_10', 0):.2f}, MAE: {entry.get('mae_10', 0):.2f}\n")
                    
            elif hyp.name == "Post-Breach Pullback Continuation":
                f.write(f"BREACH{retro_flag}: {entry['breach_time']} | {entry['fan']} ({entry['fraction']}) | Dir: {entry['direction'].upper()}\n")
                if is_retro_section:
                    f.write(f"   -> [INFO] This event was generated retroactively during a sweep.\n")
                    f.write(f"             In live replay, it will only appear on the chart once the fan's anchor pivot is confirmed.\n")
                
                if entry['status'] == "NO_PULLBACK_FOUND":
                    f.write(f"   -> [REJECTED] {entry['reason']}\n")
                elif entry['status'] == "REJECTED":
                    f.write(f"   -> [REJECTED] {entry['reason']}\n")
                    f.write(f"      First Test Found: {entry['pullback_time']} ({entry['pullback_type']})\n")
                elif entry['status'] == "ACCEPTED":
                    f.write(f"   -> [ACCEPTED] Pullback at {entry['pullback_time']} ({entry['pullback_type']})\n")
                    f.write(f"      Timing: Occurred {entry['bars_elapsed']} bars after breach\n")
                    f.write(f"      Prices: Breach @ {entry.get('breach_price', 0):.2f}, Pullback @ {entry.get('pullback_price', 0):.2f}\n")
                    f.write(f"      Outcome: {entry['outcome']} (MFE: {entry['mfe']:.2f}, MAE: {entry['mae']:.2f})\n")
                    
            else:
                f.write(f"EVENT{retro_flag}: {entry['time']} | {entry['fan']} ({entry['fraction']}) | Type: {entry['type']}\n")
                if is_retro_section:
                    f.write(f"   -> [INFO] This event was generated retroactively during a sweep.\n")
                if entry.get('confluence_lines'):
                    f.write(f"      Confluence With: {', '.join(entry['confluence_lines'])}\n")
                f.write(f"      Price: {entry['price']:.2f}\n")
                f.write(f"      Outcome: {entry['outcome']} (MFE: {entry['mfe']:.2f}, MAE: {entry['mae']:.2f})\n")
            f.write("-" * 60 + "\n")

        f.write("=== LIVE EVENTS ===\n")
        f.write("These events would have been fully tradable in real-time without future lookahead.\n")
        f.write("=" * 60 + "\n")
        for e in live_events:
            write_event(e, False)
            
        f.write("\n\n=== RETROACTIVE EVENTS ===\n")
        f.write("These events occurred during the 5-bar unconfirmed pivot window and were retroactively inserted.\n")
        f.write("=" * 60 + "\n")
        for e in retro_events:
            write_event(e, True)
            
    print(f"Generated {filename}")

    # Build event records with fan geometry
    live_events_geometry = []
    retro_events_geometry = []

    for e in live_events:
        fan_display = f"{e.get('fan', 'Unknown')}"
        # Use breach_time for PostBreach, time for all others
        if hyp.name == "Post-Breach Pullback Continuation":
            time_key = str(e.get('breach_time', ''))
        else:
            time_key = str(e.get('time', ''))
        active_angles_raw = time_to_active_angles.get(time_key, '{}')
        live_events_geometry.append(_row_to_event_record(e, fan_display, active_angles_raw, df))

    for e in retro_events:
        fan_display = f"{e.get('fan', 'Unknown')} [RETRO]"
        if hyp.name == "Post-Breach Pullback Continuation":
            time_key = str(e.get('breach_time', ''))
        else:
            time_key = str(e.get('time', ''))
        active_angles_raw = time_to_active_angles.get(time_key, '{}')
        retro_events_geometry.append(_row_to_event_record(e, fan_display, active_angles_raw, df))

    # Extract metadata
    instrument, timeframe, start_date_str, end_date_str = _get_metadata(df)

    json_output = {
        'metadata': {
            'symbol': str(instrument),
            'timeframe': str(timeframe),
            'start_date': str(start_date_str),
            'end_date': str(end_date_str),
            'total_events': int(result['sample_size']),
            'win_rate': float(result['win_rate']),
            'live_sample_size': int(result.get('live_sample_size', 0)),
            'live_win_rate': float(result.get('live_win_rate', 0)),
            'retro_sample_size': int(result.get('retro_sample_size', 0)),
            'retro_win_rate': float(result.get('retro_win_rate', 0)),
            'generated_at': datetime.datetime.now().isoformat()
        },
        'live_events': live_events_geometry,
        'retro_events': retro_events_geometry,
        'summary': {
            'sample_size': int(result['sample_size']),
            'win_rate': float(result['win_rate']),
            'live_sample_size': int(result.get('live_sample_size', 0)),
            'live_win_rate': float(result.get('live_win_rate', 0)),
            'retro_sample_size': int(result.get('retro_sample_size', 0)),
            'retro_win_rate': float(result.get('retro_win_rate', 0))
        }
    }

    json_filename = filename.replace('.txt', '.json')
    json_filepath = os.path.join(output_dir, json_filename)
    with open(json_filepath, 'w') as f:
        json.dump(json_output, f, indent=2)
    print(f"Generated {json_filename}")
