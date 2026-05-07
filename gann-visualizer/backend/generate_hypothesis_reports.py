import pandas as pd
import sys
import os

sys.path.append(r"C:\Dev\GannTesting\gann-visualizer\backend")
from analysis.strategy_analyzer import (
    StrongSRHypothesis,
    TargetProgressionHypothesis,
    QuarterReversalAnomalyHypothesis,
    ConfluenceBounceHypothesis,
    PostBreachPullbackHypothesis
)

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
        
        # Extract instrument and timeframe from df
        instrument = df['Instrument'].iloc[0] if not df.empty and 'Instrument' in df.columns else "Unknown"
        timeframe = df['Timeframe'].iloc[0] if not df.empty and 'Timeframe' in df.columns else "Unknown"
        
        # Try to extract the requested start_date from the new column, fallback to the first event's date
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
