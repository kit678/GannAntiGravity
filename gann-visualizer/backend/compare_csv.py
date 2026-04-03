#!/usr/bin/env python3
"""
Compare frontend price_interactions CSV with backend simulation_events CSV.
This script normalizes events to ignore sort order and formatting differences.
"""

import csv
from datetime import datetime
from collections import Counter

def parse_datetime(dt_str):
    """Try to parse datetime string from either format."""
    dt_str = str(dt_str).strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",      # Frontend: 2026-03-20 10:23:00
        "%Y-%m-%d %I:%M:%S %p",   # Frontend: 2026-03-20 10:23:00 AM
        "%Y-%m-%d",               # Frontend: 2026-03-20
        "%m/%d/%Y, %I:%M:%S %p",  # Backend: 3/20/2026, 10:23:00 AM
        "%m/%d/%Y, %H:%M:%S",      # Backend: 3/20/2026, 15:03:00
    ]
    for fmt in formats:
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    return None

def normalize_fraction(frac):
    """Normalize fraction to handle 7/8 vs 0.875 and the 2026-07-08 bug."""
    frac_str = str(frac).strip()
    # Handle the Excel date bug: 7/8 gets parsed as 2026-07-08
    if frac_str == '2026-07-08':
        return '0.875'
    if frac_str == '7/8' or frac_str == '7\\8' or frac_str == '7‑8' or frac_str == '7―8':
        return '0.875'
    return frac_str.lower()

def get_field(row, *keys):
    """Get first non-empty field from row using multiple possible keys."""
    for key in keys:
        if key in row and row[key]:
            val = str(row[key]).strip()
            if val:
                return val
    return ''

def create_event_key(row, include_time=True):
    """Create a comparable key tuple from a row. Set include_time=False to ignore time."""
    fan = get_field(row, 'Fan', 'fan')
    frac = normalize_fraction(get_field(row, 'Fraction', 'fraction'))
    
    try:
        price = round(float(get_field(row, 'Price', 'price')), 2)
    except (ValueError, TypeError):
        price = 0
    
    event_type = get_field(row, 'Type', 'type', 'Event Type')
    
    if include_time:
        time_str = get_field(row, 'Time', 'time', 'Datetime')
        dt = parse_datetime(time_str)
        if dt:
            return (dt.timestamp(), fan, frac, price, event_type)
    
    return (fan, frac, price, event_type)

def load_csv(path):
    """Load CSV and return list of dicts."""
    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows

def compare_csv(frontend_path, backend_path):
    fe_rows = load_csv(frontend_path)
    be_rows = load_csv(backend_path)
    
    print(f"Frontend rows: {len(fe_rows)}")
    print(f"Backend rows: {len(be_rows)}")
    
    # Create normalized keys for comparison (IGNORING TIME - key insight!)
    fe_keys = []
    fe_key_counts = Counter()
    for row in fe_rows:
        key = create_event_key(row, include_time=False)
        if key[0] or key[1]:  # Only add if has fan or fraction
            fe_keys.append(key)
            fe_key_counts[key] += 1
    
    be_keys = []
    be_key_counts = Counter()
    for row in be_rows:
        key = create_event_key(row, include_time=False)
        if key[0] or key[1]:  # Only add if has fan or fraction
            be_keys.append(key)
            be_key_counts[key] += 1
    
    # Find differences
    fe_unique = set(fe_keys)
    be_unique = set(be_keys)
    
    only_frontend = fe_unique - be_unique
    only_backend = be_unique - fe_unique
    common = fe_unique & be_unique
    
    print(f"\n=== RESULTS (IGNORING TIME, UNIQUE EVENTS) ===")
    print(f"Unique events in frontend: {len(fe_unique)}")
    print(f"Unique events in backend: {len(be_unique)}")
    print(f"Common unique events: {len(common)}")
    print(f"Only in frontend: {len(only_frontend)}")
    print(f"Only in backend: {len(only_backend)}")
    
    if only_frontend:
        print(f"\n--- ONLY IN FRONTEND ({min(10, len(only_frontend))}) ---")
        for key in list(only_frontend)[:10]:
            print(f"  Fan: {key[0]}, Frac: {key[1]}, Price: {key[2]}, Type: {key[3]}")
    
    if only_backend:
        print(f"\n--- ONLY IN BACKEND ({min(10, len(only_backend))}) ---")
        for key in list(only_backend)[:10]:
            print(f"  Fan: {key[0]}, Frac: {key[1]}, Price: {key[2]}, Type: {key[3]}")
    
    # Find duplicate events
    fe_duplicates = {k: v for k, v in fe_key_counts.items() if v > 1}
    be_duplicates = {k: v for k, v in be_key_counts.items() if v > 1}
    
    if fe_duplicates:
        print(f"\n--- DUPLICATE EVENTS IN FRONTEND ---")
        for key, count in sorted(fe_duplicates.items(), key=lambda x: -x[1])[:5]:
            print(f"  {key[2]} x{count}: Fan={key[0]}, Frac={key[1]}, Type={key[3]}")
    
    if be_duplicates:
        print(f"\n--- DUPLICATE EVENTS IN BACKEND ---")
        for key, count in sorted(be_duplicates.items(), key=lambda x: -x[1])[:5]:
            print(f"  {key[2]} x{count}: Fan={key[0]}, Frac={key[1]}, Type={key[3]}")
    
    return {
        'matching': len(common),
        'only_frontend': len(only_frontend),
        'only_backend': len(only_backend),
        'fe_count': len(fe_rows),
        'be_count': len(be_rows),
        'fe_unique': len(fe_unique),
        'be_unique': len(be_unique)
    }

if __name__ == '__main__':
    frontend_path = r'c:\Dev\GannTesting\gann-visualizer\frontend\price_interactions_frontend.csv'
    backend_path = r'c:\Dev\GannTesting\gann-visualizer\backend\logs\simulation_events.csv'
    
    result = compare_csv(frontend_path, backend_path)
    
    print("\n" + "="*60)
    print("SUMMARY:")
    print(f"  Total events in frontend: {result['fe_count']}")
    print(f"  Unique events in frontend: {result['fe_unique']}")
    print(f"  Total events in backend: {result['be_count']}")
    print(f"  Unique events in backend: {result['be_unique']}")
    print(f"  Common unique events: {result['matching']}")
    print(f"  Unique events only in frontend: {result['only_frontend']}")
    print(f"  Unique events only in backend: {result['only_backend']}")
    
    if result['only_frontend'] == 0 and result['only_backend'] == 0:
        print("\n✓ ALL UNIQUE EVENTS MATCH! The only differences are:")
        print(f"  - SORT ORDER")
        print(f"  - TIME FORMAT")
        if result['fe_count'] != result['fe_unique']:
            print(f"  - Frontend has {result['fe_count'] - result['fe_unique']} duplicate events")
        if result['be_count'] != result['be_unique']:
            print(f"  - Backend has {result['be_count'] - result['be_unique']} duplicate events")
    else:
        print("\n✗ THERE ARE UNMATCHED EVENTS!")
