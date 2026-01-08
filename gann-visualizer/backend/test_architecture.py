"""
Test script to verify the new separated architecture works correctly
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from strategies import get_strategy, STRATEGY_REGISTRY
from backtest_engine import BacktestEngine


def generate_sample_data(days=5):
    """Generate sample OHLCV data for testing"""
    start_date = datetime.now() - timedelta(days=days)
    
    # Generate 1-minute bars for N days (375 bars per day = 6.25 hours)
    num_bars = days * 375
    
    timestamps = []
    opens = []
    highs = []
    lows = []
    closes = []
    
    base_price = 24000
    current_price = base_price
    
    for i in range(num_bars):
        timestamp = int((start_date + timedelta(minutes=i)).timestamp())
        timestamps.append(timestamp)
        
        # Random walk
        change = np.random.randn() * 10
        open_price = current_price
        close_price = current_price + change
        high_price = max(open_price, close_price) + abs(np.random.randn() * 5)
        low_price = min(open_price, close_price) - abs(np.random.randn() * 5)
        
        opens.append(open_price)
        highs.append(high_price)
        lows.append(low_price)
        closes.append(close_price)
        
        current_price = close_price
    
    df = pd.DataFrame({
        'timestamp': timestamps,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': np.random.randint(1000, 10000, size=num_bars)
    })
    
    return df


def test_strategy(strategy_name, df):
    """Test a single strategy"""
    print(f"\n{'='*60}")
    print(f"Testing: {strategy_name}")
    print(f"{'='*60}")
    
    try:
        # Get strategy instance
        strategy = get_strategy(strategy_name, df)
        print(f"✓ Strategy instantiated: {strategy.get_strategy_name()}")
        
        # Create backtest engine
        engine = BacktestEngine(strategy, initial_capital=100000)
        print(f"✓ Backtest engine created")
        
        # Run backtest
        result = engine.run(symbol='TEST')
        print(f"✓ Backtest completed")
        
        # Display results
        print(f"\n📊 Results:")
        print(f"   Total Trades: {result.metrics['total_trades']}")
        print(f"   Completed Trades: {result.metrics['completed_trades']}")
        print(f"   Wins: {result.metrics['wins']}")
        print(f"   Losses: {result.metrics['losses']}")
        print(f"   Win Rate: {result.metrics['win_rate']}%")
        print(f"   Total P&L: {result.metrics['total_pnl']}")
        print(f"   Return: {result.metrics['return_pct']}%")
        
        if result.metrics['avg_win'] > 0:
            print(f"   Avg Win: {result.metrics['avg_win']}")
        if result.metrics['avg_loss'] < 0:
            print(f"   Avg Loss: {result.metrics['avg_loss']}")
        if result.metrics['profit_factor'] > 0:
            print(f"   Profit Factor: {result.metrics['profit_factor']}")
        
        # Show first few trades
        if len(result.trades) > 0:
            print(f"\n📝 First few trades:")
            for i, trade in enumerate(result.trades[:6]):
                print(f"   {i+1}. {trade.type.upper()} @ {trade.price:.2f} - {trade.label}")
        
        print(f"\n✅ {strategy_name} test PASSED")
        return True
        
    except Exception as e:
        print(f"\n❌ {strategy_name} test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("="*60)
    print("BACKTESTING ARCHITECTURE TEST SUITE")
    print("="*60)
    
    # Generate sample data
    print("\nGenerating sample data...")
    df = generate_sample_data(days=5)
    print(f"✓ Generated {len(df)} bars of sample data")
    
    # Test each strategy
    results = {}
    for strategy_name in STRATEGY_REGISTRY.keys():
        results[strategy_name] = test_strategy(strategy_name, df)
    
    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for strategy_name, passed_status in results.items():
        status = "✅ PASSED" if passed_status else "❌ FAILED"
        print(f"{strategy_name}: {status}")
    
    print(f"\n{passed}/{total} strategies passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Architecture is working correctly.")
    else:
        print(f"\n⚠️ {total - passed} test(s) failed. Review the errors above.")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
