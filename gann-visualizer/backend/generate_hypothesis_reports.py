import pandas as pd
import sys
import os
import json
import math
import argparse
from datetime import datetime

sys.path.append(r"C:\Dev\GannTesting\gann-visualizer\backend")
from analysis.strategy_analyzer import (
    StrongSRHypothesis,
    TargetProgressionHypothesis,
    QuarterReversalAnomalyHypothesis,
    ConfluenceBounceHypothesis,
    PostBreachPullbackHypothesis,
    EMACrossoverHypothesis
)


def _get_metadata(df):
    instrument = df['Instrument'].iloc[0] if not df.empty and 'Instrument' in df.columns else "Unknown"
    timeframe = df['Timeframe'].iloc[0] if not df.empty and 'Timeframe' in df.columns else "Unknown"
    if not df.empty and 'Start_Date' in df.columns:
        val = df['Start_Date'].iloc[0]
        try:
            if pd.isna(val):
                start_date_str = "Unknown"
            else:
                start_date_str = str(val)
        except:
            start_date_str = "Unknown"
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


def _build_geometry_lookup(hypothesis_events_path):
    if not os.path.exists(hypothesis_events_path):
        return {}
    with open(hypothesis_events_path) as f:
        data = json.load(f)
    lookup = {}
    for evt in data.get("events", []):
        geom = evt.get("fan_geometry")
        if not geom:
            continue
        ts = evt.get("timestamp")
        if ts is None:
            continue
        frac_val = evt.get("fraction")
        if frac_val is None:
            fan_display = evt.get("fan_display", "")
            if fan_display:
                try:
                    if '/' in str(fan_display):
                        num, den = str(fan_display).split('/')
                        frac_val = float(num) / float(den)
                    else:
                        frac_val = float(fan_display)
                except (ValueError, ZeroDivisionError):
                    pass
        if frac_val is not None:
            try:
                frac_float = round(float(frac_val), 4)
                key = (int(ts), frac_float)
                if key not in lookup:
                    lookup[key] = geom
            except (ValueError, TypeError):
                pass
    return lookup


def _sanitize_json(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_json(v) for v in obj]
    return obj


def _attach_geometry(event, geometry_lookup, time_field="time", fraction_field="fraction"):
    time_val = event.get(time_field)
    fraction = event.get(fraction_field)
    if time_val is None:
        return
    try:
        from datetime import timezone, timedelta
        IST = timezone(timedelta(hours=5, minutes=30))
        dt = pd.to_datetime(time_val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        ts = int(dt.timestamp())
    except:
        ts = None
    if ts is None:
        return
    try:
        frac_float = round(float(fraction), 4) if fraction is not None else None
    except (ValueError, TypeError):
        frac_float = None
    if frac_float is not None:
        geom = geometry_lookup.get((ts, frac_float))
        if geom:
            event["fan_geometry"] = geom


def _generate_single_report(hyp, df, geometry_lookup, output_dir, candles_df=None):
    if candles_df is not None:
        try:
            result = hyp.evaluate(df, candles_df=candles_df)
        except TypeError:
            result = hyp.evaluate(df)
    else:
        result = hyp.evaluate(df)
    detailed_log = result.get("detailed_log", [])

    if hyp.name == "Post-Breach Pullback Continuation":
        detailed_log = sorted(detailed_log, key=lambda x: pd.to_datetime(x['breach_time']))
        time_field = "breach_time"
    else:
        detailed_log = sorted(detailed_log, key=lambda x: pd.to_datetime(x['time']))
        time_field = "time"

    live_events = [e for e in detailed_log if not e.get('is_retro')]
    retro_events = [e for e in detailed_log if e.get('is_retro')]

    for e in detailed_log:
        _attach_geometry(e, geometry_lookup, time_field=time_field)

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
                    origin_angle = entry.get('breach_fraction', 'Unknown')
                    target_hit = entry['fraction']
                    f.write(f"TARGET ATTEMPT{retro_flag}: {entry['time']} | {entry['fan']} ({origin_angle}) -> {target_hit} @ Price: {entry.get('target_price', 'N/A')}\n")
                else:
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
                    f.write(f"      Outcome: {entry['outcome']} (MFE: {entry['mfe']:.2f}, MAE: {entry['mae']:.2f}\n")

            else:
                f.write(f"EVENT{retro_flag}: {entry['time']} | {entry['fan']} ({entry['fraction']}) | Type: {entry['type']}\n")
                if is_retro_section:
                    f.write(f"   -> [INFO] This event was generated retroactively during a sweep.\n")
                if entry.get('confluence_lines'):
                    f.write(f"      Confluence With: {', '.join(entry['confluence_lines'])}\n")
                f.write(f"      Price: {entry['price']:.2f}\n")
                f.write(f"      Outcome: {entry['outcome']} (MFE: {entry['mfe']:.2f}, MAE: {entry['mae']:.2f}\n")
            f.write("-" * 60 + "\n")

        if hyp.name == "9/21 EMA Crossover Strategy":
            def write_event(entry, is_retro_section=False):
                direction_arrow = "↑" if entry['direction'] == 'BUY' else "↓"
                f.write(f"CROSSOVER: {entry['time']} | {entry['direction']} {direction_arrow} | Entry: {entry['entry_price']:.2f}\n")
                f.write(f"   Outcome: {entry['outcome']} | MFE: {entry['mfe_pct']:.4f}% | MAE: {entry['mae_pct']:.4f}%\n")
                f.write(f"   EMA9: {entry['ema_9']:.2f} | EMA21: {entry['ema_21']:.2f}\n")
                f.write("-" * 60 + "\n")

            f.write("=== LIVE EVENTS ===\n")
            f.write("All EMA crossovers are inherently live (no pivot confirmation delay).\n")
            f.write("=" * 60 + "\n")
            for e in live_events:
                write_event(e, False)
            return

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

    json_filename = hyp.name.lower().replace(' ', '_').replace('/', '').replace('(', '').replace(')', '') + "_report.json"
    json_filepath = os.path.join(output_dir, json_filename)
    instrument, timeframe, start_date_str, end_date_str = _get_metadata(df)
    json_data = {
        "metadata": {
            "symbol": instrument,
            "timeframe": timeframe,
            "start_date": start_date_str,
            "end_date": end_date_str,
            "total_events": result["sample_size"],
            "win_rate": result["win_rate"],
            "live_sample_size": result.get("live_sample_size", 0),
            "live_win_rate": result.get("live_win_rate", 0),
            "retro_sample_size": result.get("retro_sample_size", 0),
            "retro_win_rate": result.get("retro_win_rate", 0),
        },
        "live_events": live_events,
        "retro_events": retro_events,
    }
    with open(json_filepath, 'w') as f:
        json.dump(_sanitize_json(json_data), f, indent=2, default=str)

    print(f"  - {filename}")


def generate_reports_for_csv(csv_path: str, hypothesis_names: list, time_only: str):
    df = pd.read_csv(csv_path)
    run_dir = os.path.dirname(csv_path)
    hypothesis_events_path = os.path.join(run_dir, "hypothesis_events.json")
    geometry_lookup = _build_geometry_lookup(hypothesis_events_path)

    candles_csv_path = os.path.join(run_dir, "candles.csv")
    candles_df = None
    if os.path.exists(candles_csv_path):
        candles_df = pd.read_csv(candles_csv_path)

    all_hypotheses = [
        StrongSRHypothesis(),
        QuarterReversalAnomalyHypothesis(),
        ConfluenceBounceHypothesis(),
        TargetProgressionHypothesis(),
        PostBreachPullbackHypothesis(),
        EMACrossoverHypothesis()
    ]

    is_full_suite = hypothesis_names is None
    selected_hypotheses = [
        h for h in all_hypotheses
        if hypothesis_names is None or h.name in hypothesis_names
    ]

    parent_folder = time_only if not is_full_suite else f"{time_only}_all"
    output_dir = os.path.join(run_dir, "hypothesis_reports", parent_folder)
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n  [{os.path.basename(run_dir)}] Generating {len(selected_hypotheses)} report(s)...")

    for hyp in selected_hypotheses:
        try:
            _generate_single_report(hyp, df, geometry_lookup, output_dir, candles_df)
        except TypeError:
            _generate_single_report(hyp, df, geometry_lookup, output_dir)


def generate_all_reports(csv_path: str, hypothesis_names: list = None) -> str:
    time_only = datetime.now().strftime("%H%M%S")
    generate_reports_for_csv(csv_path, hypothesis_names, time_only)


if __name__ == "__main__":
    base_runs_path = r"C:\Dev\GannTesting\logs\backend\runs\_NSEI"

    parser = argparse.ArgumentParser(description="Generate hypothesis reports")
    parser.add_argument("run_date", help="Run date (e.g., 2026-05-11)")
    parser.add_argument("--hypothesis", "-H", action="append", dest="hypotheses",
                       help="Specific hypothesis to run (can be specified multiple times). "
                            "If not provided, runs all hypotheses.")
    parser.add_argument("--all-timeframes", "-A", action="store_true",
                       help="Run for all available timeframes")
    parser.add_argument("--4m", action="store_true", dest="tf_4", help="Include 4m timeframe")
    parser.add_argument("--15m", action="store_true", dest="tf_15", help="Include 15m timeframe")
    parser.add_argument("--60m", action="store_true", dest="tf_60", help="Include 60m timeframe")
    args = parser.parse_args()

    time_only = datetime.now().strftime("%H%M%S")
    hypothesis_names = args.hypotheses
    is_full_suite = hypothesis_names is None

    hyp_names_str = "ALL" if is_full_suite else ", ".join(hypothesis_names)
    print(f"\n{'='*60}")
    print(f"Generating reports: {hyp_names_str}")
    print(f"Date: {args.run_date} | Time: {time_only}")
    print(f"{'='*60}")

    if args.all_timeframes:
        selected_tfs = ["4", "15", "60"]
    else:
        selected_tfs = []
        if args.tf_4: selected_tfs.append("4")
        if args.tf_15: selected_tfs.append("15")
        if args.tf_60: selected_tfs.append("60")

    if not selected_tfs:
        print("Error: Specify --all-timeframes or at least one timeframe flag (--4m, --15m, --60m)")
        sys.exit(1)

    print(f"Timeframes: {', '.join(selected_tfs)}m")

    for tf in selected_tfs:
        tf_path = os.path.join(base_runs_path, tf)
        if not os.path.exists(tf_path):
            print(f"  [Skipping {tf}m - folder not found]")
            continue

        found_run = None
        for folder in os.listdir(tf_path):
            if folder.startswith(args.run_date):
                found_run = os.path.join(tf_path, folder)
                break

        if not found_run:
            print(f"  [Skipping {tf}m - no run found for {args.run_date}]")
            continue

        csv_path = os.path.join(found_run, "events.csv")
        if not os.path.exists(csv_path):
            print(f"  [Skipping {tf}m - events.csv not found]")
            continue

        generate_reports_for_csv(csv_path, hypothesis_names, time_only)

    print(f"\n{'='*60}")
    print(f"Done! Reports in: hypothesis_reports/{time_only}{'_all' if is_full_suite else ''}/")
    print(f"{'='*60}")
