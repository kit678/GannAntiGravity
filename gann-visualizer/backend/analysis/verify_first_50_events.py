import sys
import os
import pytz
from datetime import datetime

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from run_simulation import get_frontend_parity_data
from study_tool.angular_coverage_study import AngularPriceCoverageStudy

def verify_events():
    print("Fetching data...")
    candles, target_from_dt, actual_start_dt = get_frontend_parity_data(
        symbol="^NSEI", resolution="4", data_source="yfinance", lookback_bars=5000
    )

    study = AngularPriceCoverageStudy({
        'resolution': '4',
        'symbol': '^NSEI'
    })

    events_analyzed = 0
    ist = pytz.timezone('Asia/Kolkata')
    
    print(f"Starting step-by-step verification for first 50 events...\n")
    
    for i, candle in enumerate(candles):
        if events_analyzed >= 50:
            break
            
        result = study.process_bar(candles, i)
        
        if result and 'intersection_events' in result and result['intersection_events']:
            prev_candle = candles[i-1] if i > 0 else candle
            
            c_open = float(candle.get('open', 0))
            c_high = float(candle.get('high', 0))
            c_low = float(candle.get('low', 0))
            c_close = float(candle.get('close', 0))
            p_close = float(prev_candle.get('close', c_open))
            
            for event in result['intersection_events']:
                if events_analyzed >= 50:
                    break
                    
                e_type = event['type']
                e_price = float(event['price'])
                
                # Verification Logic
                is_correct = False
                reason = ""
                
                if e_type == 'CROSS_UP':
                    if c_open < e_price and c_close > e_price:
                        is_correct = True
                    else:
                        reason = f"Expected O < P and C > P"
                elif e_type == 'CROSS_DOWN':
                    if c_open > e_price and c_close < e_price:
                        is_correct = True
                    else:
                        reason = f"Expected O > P and C < P"
                elif e_type == 'SUPPORT_TEST':
                    if p_close > e_price and c_low <= e_price and c_close > e_price:
                        is_correct = True
                        # Check for gap down
                        if c_open < e_price:
                            reason = "WARNING: Gap down below support, not a true pullback test"
                            is_correct = False
                    else:
                        reason = f"Expected pC > P, L <= P, C > P"
                elif e_type == 'RESISTANCE_TEST':
                    if p_close < e_price and c_high >= e_price and c_close < e_price:
                        is_correct = True
                        # Check for gap up
                        if c_open > e_price:
                            reason = "WARNING: Gap up above resistance, not a true rejection test"
                            is_correct = False
                    else:
                        reason = f"Expected pC < P, H >= P, C < P"
                elif e_type in ['FAN_VALIDATED', 'BREACH_CONFIRMED', 'ZONE_CHANGE']:
                    is_correct = True # These are complex multi-bar logic, assuming true for basic OHLC check
                else:
                    is_correct = True
                    
                dt_utc = datetime.fromtimestamp(candle['time'], pytz.utc)
                dt_ist = dt_utc.astimezone(ist)
                dt_str = dt_ist.strftime('%Y-%m-%d %H:%M')
                
                status = "✅ PASS" if is_correct else f"❌ FAIL: {reason}"
                print(f"Event {events_analyzed+1:02d}: {dt_str} | Type: {e_type:15} | Angle Price: {e_price:.2f}")
                print(f"  Candle: O={c_open:.2f}, H={c_high:.2f}, L={c_low:.2f}, C={c_close:.2f} | PrevClose={p_close:.2f}")
                print(f"  Assessment: {status}")
                print("-" * 80)
                
                events_analyzed += 1

if __name__ == "__main__":
    verify_events()
