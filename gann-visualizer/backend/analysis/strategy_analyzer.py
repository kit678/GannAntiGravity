import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
import os

class Hypothesis:
    """Base class for all strategy hypotheses."""
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.parameters = {}
        
    def set_parameters(self, **kwargs):
        """Allow altering hypothesis parameters dynamically."""
        self.parameters.update(kwargs)
        
    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Evaluate the hypothesis against the dataset.
        Must return a dictionary with at least:
        - 'win_rate': float
        - 'sample_size': int
        - 'avg_mfe_10': float
        - 'avg_mae_10': float
        """
        raise NotImplementedError("Subclasses must implement evaluate()")

class TimeDecayHypothesis(Hypothesis):
    def __init__(self):
        super().__init__(
            name="Time-Decay Rule (Consolidation Exhaustion)",
            description="The longer price rests on an angle, the higher the probability of a breakthrough vs bounce."
        )
        self.set_parameters(rest_threshold_bars=3)
        
    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        threshold = self.parameters['rest_threshold_bars']
        
        # Filter for REST_ON_ANGLE
        rests = df[df['Type'] == 'REST_ON_ANGLE'].copy()
        if rests.empty or 'detail_bars_elapsed' not in rests.columns:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0}
            
        # Convert detail_bars_elapsed to numeric
        rests['detail_bars_elapsed'] = pd.to_numeric(rests['detail_bars_elapsed'], errors='coerce')
        
        # Long rests
        long_rests = rests[rests['detail_bars_elapsed'] >= threshold]
        
        if long_rests.empty:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0}
            
        wins = 0
        total_mfe = 0
        total_mae = 0
        
        for _, row in long_rests.iterrows():
            price = row['Price']
            mfe_raw = row.get('MFE_10', np.nan)
            mae_raw = row.get('MAE_10', np.nan)
            
            if pd.isna(mfe_raw) or pd.isna(mae_raw) or pd.isna(price):
                continue
                
            # MFE and MAE are now correctly calculated as excursions in event_logger.py
            # We just need to use them directly.
            if mfe_raw > mae_raw * 2:
                wins += 1
                
            total_mfe += mfe_raw
            total_mae += mae_raw
                
        sample_size = len(long_rests)
        win_rate = wins / sample_size if sample_size > 0 else 0.0
        
        return {
            "sample_size": sample_size,
            "win_rate": win_rate,
            "avg_mfe_10": total_mfe / sample_size if sample_size > 0 else 0.0,
            "avg_mae_10": total_mae / sample_size if sample_size > 0 else 0.0,
            "threshold_used": threshold
        }

class ConfluenceBounceHypothesis(Hypothesis):
    def __init__(self):
        super().__init__(
            name="Confluence Bounce Rule",
            description="Touches on angles that are near other active angles have a higher reversal probability."
        )
        self.set_parameters(price_band_pct=0.002) # 0.2%
        
    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        # Find all touch-related events
        # Updated to use aligned Frontend Types: CROSS_UP, CROSS_DOWN, SUPPORT_TEST, RESISTANCE_TEST, TOUCH
        # Also include backend states like FAN_VALIDATED and REST_ON_ANGLE which are also relevant
        target_types = [
            'CROSS_UP', 'CROSS_DOWN', 'SUPPORT_TEST', 'RESISTANCE_TEST', 'TOUCH', 
            'FAN_VALIDATED', 'REST_ON_ANGLE', 'FAKE_OUT', 'ANGLE_TOUCH'
        ]
        touches = df[df['Type'].isin(target_types)].copy()
        if touches.empty:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0}
            
        band_pct = self.parameters['price_band_pct']
        
        wins = 0
        total_mfe = 0
        total_mae = 0
        valid_confluence_events = 0
        
        print("\n" + "="*60)
        print("DETAILED LOG: Confluence Bounce Rule Verification")
        print("="*60)
        
        # Group by time for better logging readability and logic
        grouped_touches = touches.groupby('Time')
        
        for time_str, group in grouped_touches:
            # 1. Ensure distinct lines (unique Fan + Fraction)
            group['Line_ID'] = group['Fan'] + "_" + group['Fraction'].astype(str)
            distinct_lines = group.drop_duplicates(subset=['Line_ID'])
            
            if len(distinct_lines) < 2:
                continue # Not a confluence, just multiple events on the same line
                
            # 2. Ensure lines are within the price band
            max_price = distinct_lines['Price'].max()
            min_price = distinct_lines['Price'].min()
            
            if min_price == 0 or pd.isna(min_price) or pd.isna(max_price):
                continue
                
            price_diff_pct = (max_price - min_price) / min_price
            if price_diff_pct > band_pct:
                continue # Lines are too far apart to be considered confluence
                
            valid_confluence_events += 1
            
            print(f"\n[CONFLUENCE EVENT] Time: {time_str}")
            print(f"Price Band Spread: {price_diff_pct:.4%} (Max allowed: {band_pct:.4%})")
            print("Interacting Lines:")
            
            event_mfe = 0
            event_mae = 0
            
            for _, row in distinct_lines.iterrows():
                price = row['Price']
                mfe_raw = row.get('MFE_10', np.nan)
                mae_raw = row.get('MAE_10', np.nan)
                
                print(f"  - Price: {price:.2f} | Fan: {row['Fan']:<15} | Fraction: {row['Fraction']:<5} | Type: {row['Type']}")
                
                if pd.isna(mfe_raw) or pd.isna(mae_raw) or pd.isna(price):
                    continue
                    
                # Since all lines in the confluence event share the same timestamp,
                # their forward-looking MFE and MAE will be identical.
                # We just need to grab it once per event.
                event_mfe = mfe_raw
                event_mae = mae_raw
                
            # Evaluate the event as a whole
            is_win = event_mfe > event_mae * 2
            if is_win:
                wins += 1
                
            total_mfe += event_mfe
            total_mae += event_mae
            
            print(f"  -> Outcome (Next 10 bars): MFE: {event_mfe:.2f} | MAE: {event_mae:.2f} | Result: {'WIN' if is_win else 'LOSS'}")
            
        print("\n" + "="*60 + "\n")
        
        sample_size = valid_confluence_events
        win_rate = wins / sample_size if sample_size > 0 else 0.0
        
        return {
            "sample_size": sample_size,
            "win_rate": win_rate,
            "avg_mfe_10": total_mfe / sample_size if sample_size > 0 else 0.0,
            "avg_mae_10": total_mae / sample_size if sample_size > 0 else 0.0,
            "band_pct_used": band_pct
        }

class VacuumEffectHypothesis(Hypothesis):
    def __init__(self):
        super().__init__(
            name="Vacuum Effect Rule",
            description="Once 1/2 angle is breached, price moves faster to Horizontal Target."
        )
        self.set_parameters(min_mfe_required=10.0)
        
    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        # Look for BREACH_CONFIRMED on 1/2 angle (logged as '0.5')
        breaches = df[(df['Type'] == 'BREACH_CONFIRMED') & (df['Fraction'] == '0.5')].copy()
        if breaches.empty:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0}
            
        wins = 0
        total_mfe = 0
        total_mae = 0
        
        for _, row in breaches.iterrows():
            mfe = row.get('MFE_10', np.nan)
            mae = row.get('MAE_10', np.nan)
            
            if pd.isna(mfe) or pd.isna(mae):
                continue
                
            # If MFE is significantly larger than MAE, it acted as a vacuum
            if mfe > mae * 2 and mfe > self.parameters['min_mfe_required']:
                wins += 1
                
            total_mfe += mfe
            total_mae += mae
            
        sample_size = len(breaches)
        win_rate = wins / sample_size if sample_size > 0 else 0.0
        
        return {
            "sample_size": sample_size,
            "win_rate": win_rate,
            "avg_mfe_10": total_mfe / sample_size if sample_size > 0 else 0.0,
            "avg_mae_10": total_mae / sample_size if sample_size > 0 else 0.0
        }

class StrategyAnalyzer:
    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self.df = None
        self.hypotheses: List[Hypothesis] = []
        
    def load_data(self):
        if not os.path.exists(self.csv_path):
            raise FileNotFoundError(f"CSV file not found: {self.csv_path}")
        self.df = pd.read_csv(self.csv_path)
        print(f"Loaded {len(self.df)} events from {self.csv_path}")
        
    def add_hypothesis(self, hypothesis: Hypothesis):
        self.hypotheses.append(hypothesis)
        
    def run_analysis(self):
        if self.df is None:
            self.load_data()
            
        print("\\n" + "="*50)
        print("STRATEGY ANALYSIS REPORT")
        print("="*50)
        
        for hyp in self.hypotheses:
            print(f"\\nTesting Hypothesis: {hyp.name}")
            print(f"Description: {hyp.description}")
            print(f"Parameters: {hyp.parameters}")
            
            try:
                results = hyp.evaluate(self.df)
                print("-" * 30)
                print(f"Sample Size : {results.get('sample_size', 0)}")
                print(f"Win Rate    : {results.get('win_rate', 0.0):.2%}")
                print(f"Avg MFE (10): {results.get('avg_mfe_10', 0.0):.2f}")
                print(f"Avg MAE (10): {results.get('avg_mae_10', 0.0):.2f}")
                
                # Allow altering hypothesis if it fails (e.g., win rate < 50%)
                if results.get('sample_size', 0) > 0 and results.get('win_rate', 0.0) < 0.50:
                    print(">>> Hypothesis failed to achieve 50% win rate. Suggesting parameter alteration...")
                    # Example of altering:
                    if isinstance(hyp, TimeDecayHypothesis):
                        new_thresh = hyp.parameters['rest_threshold_bars'] + 3
                        print(f"    Retesting {hyp.name} with rest_threshold_bars={new_thresh}")
                        hyp.set_parameters(rest_threshold_bars=new_thresh)
                        new_results = hyp.evaluate(self.df)
                        print(f"    New Win Rate: {new_results.get('win_rate', 0.0):.2%} (Sample: {new_results.get('sample_size', 0)})")
                        
            except Exception as e:
                print(f"Error evaluating hypothesis: {e}")
                
        print("\\n" + "="*50)

if __name__ == "__main__":
    # Path to the generated CSV
    csv_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "simulation_events.csv")
    
    analyzer = StrategyAnalyzer(csv_file)
    
    # Add our hypotheses
    analyzer.add_hypothesis(TimeDecayHypothesis())
    analyzer.add_hypothesis(ConfluenceBounceHypothesis())
    analyzer.add_hypothesis(VacuumEffectHypothesis())
    
    # Run the analysis
    if os.path.exists(csv_file):
        analyzer.run_analysis()
    else:
        print(f"Please run the simulation first to generate {csv_file}")
