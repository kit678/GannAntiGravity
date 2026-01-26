"""
Quick test to verify 5 EMA strategy with option data enrichment
"""

import sys
sys.path.append('c:\\Dev\\GannTesting\\gann-visualizer\\backend')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from strategies import get_strategy
from backtest_engine import BacktestEngine
from dhan_client import DhanClient

print("Testing 5 EMA with Option Data Enrichment")
print("=" * 60)

# Initialize client
client = DhanClient()

# Fetch real NIFTY data for a recent period
from_date = '2026-01-08'
to_date = '2026-01-10'

print(f"Fetching NIFTY data from {from_date} to {to_date}")
df = client.fetch_data('NIFTY 50', from_date, to_date, interval='5')

if df is None or df.empty:
    print("No data fetched. Using sample data instead...")
    # Generate sample data
    num_bars = 100
    timestamps = [int((datetime.now() - timedelta(minutes=100-i)).timestamp()) for i in range(num_bars)]
    
    df = pd.DataFrame({
        'timestamp': timestamps,
        'open': 24000 + np.random.randn(num_bars) * 10,
        'high': 24010 + np.random.randn(num_bars) * 10,
        'low': 23990 + np.random.randn(num_bars) * 10,
        'close': 24000 + np.random.randn(num_bars) * 10,
        'volume': np.random.randint(1000, 10000, size=num_bars)
    })

print(f"✓ Data loaded: {len(df)} bars")

# Test WITHOUT option data
print("\n" + "=" * 60)
print("TEST 1: Without Option Data (Index-based P&L)")
print("=" * 60)

strategy1 = get_strategy('five_ema', df, params={'use_option_data': False})
engine1 = BacktestEngine(strategy1)
result1 = engine1.run(symbol='NIFTY')

print(f"Trades: {result1.metrics['total_trades']}")
print(f"P&L: {result1.metrics['total_pnl']:.2f} points")

if result1.trades:
    print(f"First trade: {result1.trades[0].to_dict()}")

# Test WITH option data
print("\n" + "=" * 60)
print("TEST 2: With Option Data (Real Option Premiums)")
print("=" * 60)

try:
    strategy2 = get_strategy('five_ema', df, params={
        'use_option_data': True,
        'dhan_client': client,
        'underlying': 'NIFTY'
    })
    engine2 = BacktestEngine(strategy2)
    result2 = engine2.run(symbol='NIFTY')
    
    print(f"Trades: {result2.metrics['total_trades']}")
    print(f"P&L: {result2.metrics['total_pnl']:.2f} ₹")
    
    if result2.trades:
        print(f"First trade: {result2.trades[0].to_dict()}")
    
    print("\n✓ Option data enrichment SUCCESS!")
except Exception as e:
    print(f"\n✗ Option data enrichment FAILED: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
