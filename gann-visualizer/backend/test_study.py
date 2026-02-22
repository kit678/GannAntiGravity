import sys
import os
sys.path.append(os.path.abspath('C:/Dev/GannTesting/gann-visualizer/backend'))

from study_tool.angular_coverage_study import AngularPriceCoverageStudy
from study_tool.fan_manager import FanManager

def test():
    """
    Scenario: Price forms High->Low->High->Low pivot sequence.
    The fan from target(low@5) -> anchor(high@10) should remain valid 
    since after the anchor, price stays below the target's price level.
    
    Then: the SLOW PATH is simulated by calling process_bar only at bar 20 (replay start).
    Expected: Fan is created and retroactive labels are generated for historical crosses.
    """
    study = AngularPriceCoverageStudy(config={'left_bars': 2, 'right_bars': 2})
    candles = []

    # 0-4: downtrend -> Low at bar 2 (price=60)
    prices = [100, 80, 60, 70, 80]
    for i, p in enumerate(prices):
        candles.append({'time': i*3600, 'open': p, 'high': p+5, 'low': p-5, 'close': p})

    # 5-9: uptrend -> High at bar 7 (price=120)
    prices2 = [90, 110, 120, 115, 105]
    for i, p in enumerate(prices2):
        candles.append({'time': (i+5)*3600, 'open': p, 'high': p+5, 'low': p-5, 'close': p})

    # 10-14: sideways/slight down, BELOW 125 (below target high=120+5=125)
    # so target is NOT breached
    for i in range(5):
        p = 95 - i*3
        candles.append({'time': (i+10)*3600, 'open': p, 'high': p+5, 'low': p-5, 'close': p})
    # bar 10=95, 11=92, 12=89, 13=86, 14=83

    # bar 15: big candle that crosses several fan lines (high enough to trigger intersection)
    candles.append({'time': 15*3600, 'open': 85, 'high': 115, 'low': 70, 'close': 90})

    # bars 16-20: quiet
    for i in range(5):
        p = 90
        candles.append({'time': (i+16)*3600, 'open': p, 'high': p+3, 'low': p-3, 'close': p})

    total_bars = len(candles)  # should be 21 bars (0..20)
    print(f"Total candles: {total_bars}")

    # --- SLOW PATH (replay init): single call at bar 20 ---
    print(f"\n[SLOW PATH] process_bar at index 20")
    result = study.process_bar(candles, 20)

    print(f"\nConfirmed Pivots:")
    for p in study.pivot_detector.confirmed_pivots:
        print(f"  {p.pivot_type} at bar {p.bar_index}, price {p.price:.1f}")

    fan_result = FanManager.find_active_fans(
        confirmed_pivots=study.pivot_detector.confirmed_pivots,
        candles=candles,
        current_bar_index=20
    )
    print(f"\nFanManager fans at bar 20: {len(fan_result)}")
    for f in fan_result:
        print(f"  {f['priority_label']}: target=bar{f['target']['bar_index']} anchor=bar{f['anchor']['bar_index']}")

    print(f"\nActive Fans in engine: {len(study.angle_engine.active_fans)}")

    print(f"\n--- DRAWINGS from process_bar(20) ---")
    labels_found = 0
    for d in result['drawings']:
        if d['type'] == 'price_label':
            labels_found += 1
            print(f"  LABEL: {d['options']['text']} t={d['points'][0]['time']} (Fan: {d['options'].get('fanLabel')})")
        else:
            print(f"  {d['type'].upper()} ({d['id']}) fan={d.get('options',{}).get('fanLabel')}")

    print(f"\nTotal labels generated: {labels_found}")
    if labels_found > 0:
        print("✅ RETROACTIVE SCAN WORKS - Labels generated on slow path")
    else:
        print("❌ NO LABELS - Retroactive scan not working")

if __name__ == "__main__":
    test()
