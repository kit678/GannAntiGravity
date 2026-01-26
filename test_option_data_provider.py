"""
Test script for Option Data Provider

Tests fetching historical option data and enriching signals.
"""

import sys
sys.path.append('c:\\Dev\\GannTesting\\gann-visualizer\\backend')

import pandas as pd
from datetime import datetime, timedelta
from dhan_client import DhanClient
from option_data_provider import OptionDataProvider

print("=" * 60)
print("OPTION DATA PROVIDER TEST")
print("=" * 60)

# Initialize Dhan client
client = DhanClient()
print(f"✓ Dhan Client initialized")

# Create Option Data Provider
provider = OptionDataProvider(client)
print(f"✓ Option Data Provider created")

# Test 1: Find security ID for a known option
print("\n" + "=" * 60)
print("TEST 1: Finding Security ID for NIFTY option")
print("=" * 60)

strike = 24000
option_type = 'CE'
expiry = '16-Jan'  # Next Thursday from Jan 12, 2026

print(f"Looking for: NIFTY {strike} {option_type} expiring {expiry}")

# Convert to full date
expiry_full = '2026-01-16'

security_id = provider._find_option_security_id('NIFTY', strike, option_type, expiry_full)

if security_id:
    print(f"✓ Found Security ID: {security_id}")
    
    # Test 2: Fetch historical data for this option
    print("\n" + "=" * 60)
    print("TEST 2: Fetching Historical Option Data")
    print("=" * 60)
    
    from_date = '2026-01-10'
    to_date = '2026-01-12'
    
    print(f"Fetching data from {from_date} to {to_date}")
    
    df = provider.fetch_option_historical_data(
        security_id=security_id,
        from_date=from_date,
        to_date=to_date,
        interval='5'
    )
    
    if df is not None and not df.empty:
        print(f"✓ Fetched {len(df)} bars")
        print(f"\nFirst 3 bars:")
        print(df.head(3))
        print(f"\nLast 3 bars:")
        print(df.tail(3))
        
        # Test 3: Get price at specific timestamp
        print("\n" + "=" * 60)
        print("TEST 3: Getting Price at Specific Timestamp")
        print("=" * 60)
        
        test_timestamp = int(df.iloc[10]['timestamp'])
        test_time_str = pd.to_datetime(test_timestamp, unit='s')
        expected_price = df.iloc[10]['close']
        
        print(f"Test timestamp: {test_time_str}")
        print(f"Expected price: ₹{expected_price}")
        
        price = provider.get_option_price_at_timestamp(
            underlying='NIFTY',
            strike=strike,
            option_type=option_type,
            expiry_date=expiry_full,
            timestamp=test_timestamp,
            from_date=from_date,
            to_date=to_date,
            interval='5'
        )
        
        if price:
            print(f"✓ Retrieved price: ₹{price}")
            print(f"Match: {'✓' if abs(price - expected_price) < 0.01 else '✗'}")
        else:
            print("✗ Failed to retrieve price")
    else:
        print("✗ Failed to fetch option data")
else:
    print("✗ Failed to find security ID")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
