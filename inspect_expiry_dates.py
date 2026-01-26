
import sys
import os
import pandas as pd
from datetime import datetime

# Add backend
sys.path.append(os.path.join(os.getcwd(), 'gann-visualizer', 'backend'))
from dhan_client import DhanScripMaster

def list_expiries():
    try:
        sm = DhanScripMaster()
        sm.load()
        print("Scrip Master loaded.")
        
        # Filter NIFTY OPTIDX
        mask = sm.df['SEARCH_SYMBOL'].str.startswith('NIFTY') & \
               ~sm.df['SEARCH_SYMBOL'].str.contains('BANK') & \
               (sm.df['SEM_INSTRUMENT_NAME'] == 'OPTIDX')
               
        df = sm.df[mask]
        
        # Extract Expiry Dates
        # SEM_EXPIRY_DATE format: "2026-01-27 14:30:00"
        expiries = df['SEM_EXPIRY_DATE'].unique()
        expiries = sorted([str(e).split(' ')[0] for e in expiries])
        
        print(f"Found {len(expiries)} unique expiries.")
        print("--- Available Expiries ---")
        for e in expiries:
            print(e)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_expiries()
