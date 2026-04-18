
import sys
import os
import pandas as pd

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'gann-visualizer', 'backend'))
from dhan_client import DhanScripMaster

def inspect_symbols():
    try:
        sm = DhanScripMaster()
        sm.load()
        print("Scrip Master loaded.")
        
        # Filter for NIFTY 25500 CE JAN 2026
        mask = sm.df['SEARCH_SYMBOL'].str.contains('NIFTY') & \
               sm.df['SEARCH_SYMBOL'].str.contains('25500') & \
               sm.df['SEARCH_SYMBOL'].str.contains('CE') & \
               sm.df['SEARCH_SYMBOL'].str.contains('JAN')
               
        results = sm.df[mask].head(5)
        print("\n--- Sample NIFTY Option Symbols ---")
        for idx, row in results.iterrows():
            print(f"ID: {row.get('SEM_SMST_SECURITY_ID')}")
            print(f"Trading Symbol: {row.get('SEM_TRADING_SYMBOL')}")
            print(f"Custom Symbol: {row.get('SEM_CUSTOM_SYMBOL')}")
            print("-" * 30)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_symbols()
