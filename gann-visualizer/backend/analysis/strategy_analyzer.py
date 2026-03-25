import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
import os
import json

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

class StrongSRHypothesis(Hypothesis):
    def __init__(self):
        super().__init__(
            name="Strong Support and Resistance (S/R) Rule",
            description="Angular division lines inherently act as rigid support and resistance boundaries. A S/R test will reliably lead to a significant price reversal."
        )
        self.set_parameters(min_mfe_reward_ratio=2.0)
        
    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        tests = df[df['Type'].isin(['SUPPORT_TEST', 'RESISTANCE_TEST'])].copy()
        if tests.empty:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0}
            
        wins = 0
        total_mfe = 0
        total_mae = 0
        
        ratio = self.parameters['min_mfe_reward_ratio']
        
        for _, row in tests.iterrows():
            mfe = row.get('MFE_10', np.nan)
            mae = row.get('MAE_10', np.nan)
            
            if pd.isna(mfe) or pd.isna(mae):
                continue
                
            # To avoid division by zero, treat mae=0 as 0.1 for ratio check
            safe_mae = max(mae, 0.1)
            
            if mfe > safe_mae * ratio:
                wins += 1
                
            total_mfe += mfe
            total_mae += mae
            
        sample_size = len(tests)
        win_rate = wins / sample_size if sample_size > 0 else 0.0
        
        return {
            "sample_size": sample_size,
            "win_rate": win_rate,
            "avg_mfe_10": total_mfe / sample_size if sample_size > 0 else 0.0,
            "avg_mae_10": total_mae / sample_size if sample_size > 0 else 0.0
        }

class TargetProgressionHypothesis(Hypothesis):
    def __init__(self):
        super().__init__(
            name="Target Progression Probability",
            description="Once a fractional angle is breached and confirmed, price has a high probability of reaching the next logical target."
        )
        
    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        # The Unified State Machine emits TARGET_HIT and TARGET_FAILED events after a BREACH_CONFIRMED.
        # We can just count how many TARGET_HIT vs TARGET_FAILED events exist.
        hits = len(df[df['Type'] == 'TARGET_HIT'])
        fails = len(df[df['Type'] == 'TARGET_FAILED'])
        
        sample_size = hits + fails
        win_rate = hits / sample_size if sample_size > 0 else 0.0
        
        return {
            "sample_size": sample_size,
            "win_rate": win_rate,
            "avg_mfe_10": 0.0,  # Not strictly applicable for this specific metric
            "avg_mae_10": 0.0,
            "total_hits": hits,
            "total_fails": fails
        }

class QuarterReversalAnomalyHypothesis(Hypothesis):
    def __init__(self):
        super().__init__(
            name="The 1/4 Reversal Anomaly",
            description="If price reaches the 1/4 angle line, the trend is exhausted. The 1/4 line will act as a major reversal point."
        )
        self.set_parameters(min_mfe_reward_ratio=2.0)
        
    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        # Interactions specifically on the 0.25 fraction
        interactions = df[(df['Fraction'] == '0.25') & (df['Type'].isin(['TOUCH', 'SUPPORT_TEST', 'RESISTANCE_TEST']))].copy()
        
        if interactions.empty:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0}
            
        wins = 0
        total_mfe = 0
        total_mae = 0
        ratio = self.parameters['min_mfe_reward_ratio']
        
        for _, row in interactions.iterrows():
            mfe = row.get('MFE_10', np.nan)
            mae = row.get('MAE_10', np.nan)
            
            if pd.isna(mfe) or pd.isna(mae):
                continue
                
            safe_mae = max(mae, 0.1)
            if mfe > safe_mae * ratio:
                wins += 1
                
            total_mfe += mfe
            total_mae += mae
            
        sample_size = len(interactions)
        win_rate = wins / sample_size if sample_size > 0 else 0.0
        
        return {
            "sample_size": sample_size,
            "win_rate": win_rate,
            "avg_mfe_10": total_mfe / sample_size if sample_size > 0 else 0.0,
            "avg_mae_10": total_mae / sample_size if sample_size > 0 else 0.0
        }

class ConfluenceBounceHypothesis(Hypothesis):
    def __init__(self):
        super().__init__(
            name="Confluence Bounce Rule",
            description="Touches on angles that are near other active angles from different fans have a higher reversal probability."
        )
        self.set_parameters(price_band_pct=0.002) # 0.2%
        
    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        target_types = ['SUPPORT_TEST', 'RESISTANCE_TEST', 'TOUCH']
        touches = df[df['Type'].isin(target_types)].copy()
        if touches.empty:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0}
            
        band_pct = self.parameters['price_band_pct']
        
        wins = 0
        total_mfe = 0
        total_mae = 0
        valid_confluence_events = 0
        
        for _, row in touches.iterrows():
            price = row['Price']
            active_angles_str = row.get('Active Angles', '{}')
            mfe = row.get('MFE_10', np.nan)
            mae = row.get('MAE_10', np.nan)
            
            if pd.isna(price) or pd.isna(mfe) or pd.isna(mae):
                continue
                
            try:
                # Some JSON strings might use single quotes in pandas string representations, clean it up
                clean_json = str(active_angles_str).replace("'", '"')
                active_angles = json.loads(clean_json)
            except json.JSONDecodeError:
                continue
                
            # Check if there is another line from a DIFFERENT fan within the price band
            has_confluence = False
            current_fan = row['Fan']
            
            for line_key, line_price in active_angles.items():
                # line_key is format "Fan_ID_Fraction"
                if str(current_fan) not in line_key: # Different fan
                    if line_price > 0:
                        diff_pct = abs(price - line_price) / line_price
                        if diff_pct <= band_pct:
                            has_confluence = True
                            break
                            
            if has_confluence:
                valid_confluence_events += 1
                safe_mae = max(mae, 0.1)
                if mfe > safe_mae * 2:
                    wins += 1
                total_mfe += mfe
                total_mae += mae
                
        sample_size = valid_confluence_events
        win_rate = wins / sample_size if sample_size > 0 else 0.0
        
        return {
            "sample_size": sample_size,
            "win_rate": win_rate,
            "avg_mfe_10": total_mfe / sample_size if sample_size > 0 else 0.0,
            "avg_mae_10": total_mae / sample_size if sample_size > 0 else 0.0,
            "band_pct_used": band_pct
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
            
        print("\n" + "="*50)
        print("STRATEGY ANALYSIS REPORT")
        print("="*50)
        
        for hyp in self.hypotheses:
            print(f"\nTesting Hypothesis: {hyp.name}")
            print(f"Description: {hyp.description}")
            print(f"Parameters: {hyp.parameters}")
            
            try:
                results = hyp.evaluate(self.df)
                print("-" * 30)
                print(f"Sample Size : {results.get('sample_size', 0)}")
                print(f"Win Rate    : {results.get('win_rate', 0.0):.2%}")
                print(f"Avg MFE (10): {results.get('avg_mfe_10', 0.0):.2f}")
                print(f"Avg MAE (10): {results.get('avg_mae_10', 0.0):.2f}")
                if 'total_hits' in results:
                    print(f"Target Hits : {results['total_hits']}")
                    print(f"Target Fails: {results['total_fails']}")
                        
            except Exception as e:
                print(f"Error evaluating hypothesis: {e}")
                
        print("\n" + "="*50)

if __name__ == "__main__":
    # Path to the generated CSV
    csv_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "simulation_events.csv")
    
    analyzer = StrategyAnalyzer(csv_file)
    
    # Add our hypotheses
    analyzer.add_hypothesis(ConfluenceBounceHypothesis())
    analyzer.add_hypothesis(StrongSRHypothesis())
    analyzer.add_hypothesis(TargetProgressionHypothesis())
    analyzer.add_hypothesis(QuarterReversalAnomalyHypothesis())
    
    # Run the analysis
    if os.path.exists(csv_file):
        analyzer.run_analysis()
    else:
        print(f"Please run the simulation first to generate {csv_file}")
