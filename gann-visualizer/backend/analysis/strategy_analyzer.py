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
        self.detailed_log: List[Dict[str, Any]] = []
        
    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        hits_df = df[df['Type'] == 'TARGET_HIT'].copy()
        fails_df = df[df['Type'] == 'TARGET_FAILED'].copy()
        breaches_df = df[df['Type'] == 'BREACH_CONFIRMED'].copy()
        
        breaches_df['ts_index'] = range(len(breaches_df))
        hits_df['ts_index'] = range(len(hits_df))
        fails_df['ts_index'] = range(len(fails_df))
        
        self.detailed_log = []
        
        for _, row in hits_df.iterrows():
            self._log_target_event(row, "WIN", breaches_df)
            
        for _, row in fails_df.iterrows():
            self._log_target_event(row, "MISS", breaches_df)
            
        hits = len(hits_df)
        fails = len(fails_df)
        
        sample_size = hits + fails
        win_rate = hits / sample_size if sample_size > 0 else 0.0
        
        return {
            "sample_size": sample_size,
            "win_rate": win_rate,
            "avg_mfe_10": 0.0,
            "avg_mae_10": 0.0,
            "total_hits": hits,
            "total_fails": fails,
            "detailed_log": self.detailed_log
        }
    
    def _find_preceding_breach(self, target_row: pd.Series, breaches_df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        fan = target_row.get('Fan', '')
        target_time = target_row.get('Time', '')
        target_fraction = target_row.get('Fraction', '')
        
        preceding_breaches = breaches_df[
            (breaches_df['Fan'] == fan) & 
            (breaches_df['Time'] < target_time)
        ]
        
        if preceding_breaches.empty:
            return None
            
        last_breach = preceding_breaches.iloc[-1]
        
        return {
            "breach_time": last_breach.get('Time', ''),
            "breach_fraction": last_breach.get('Fraction', ''),
            "breach_price": last_breach.get('Price', 0.0),
            "breach_direction": last_breach.get('Details', '').split()[0] if last_breach.get('Details', '') else ''
        }
    
    def _log_target_event(self, row: pd.Series, outcome: str, breaches_df: pd.DataFrame):
        time_val = row.get('Time', 'Unknown')
        fan_val = row.get('Fan', 'Unknown')
        fraction = row.get('Fraction', 'Unknown')
        price = row.get('Price', 0.0)
        next_angle = row.get('Next_Angle_Line', None)
        
        preceding_breach = self._find_preceding_breach(row, breaches_df)
        
        log_entry = {
            "outcome": outcome,
            "time": time_val,
            "fan": fan_val,
            "fraction": fraction,
            "target_price": round(price, 2),
            "next_angle": next_angle,
            "O": row.get('Open', 0.0),
            "H": row.get('High', 0.0),
            "L": row.get('Low', 0.0),
            "C": row.get('Close', 0.0),
        }
        
        if preceding_breach:
            log_entry["breach_time"] = preceding_breach["breach_time"]
            log_entry["breach_fraction"] = preceding_breach["breach_fraction"]
            log_entry["breach_price"] = preceding_breach["breach_price"]
        
        if outcome == "WIN":
            log_entry["mfe_10"] = row.get('MFE_10', 0)
            log_entry["mae_10"] = row.get('MAE_10', 0)
        
        self.detailed_log.append(log_entry)
    
    def get_detailed_log(self) -> List[Dict[str, Any]]:
        return self.detailed_log

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
        self.detailed_log = []
        
    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        self.detailed_log = []
        target_types = ['SUPPORT_TEST', 'RESISTANCE_TEST', 'TOUCH']
        touches = df[df['Type'].isin(target_types)].copy()
        if touches.empty:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0, "detailed_log": []}
            
        band_pct = self.parameters['price_band_pct']
        
        wins = 0
        total_mfe = 0
        total_mae = 0
        valid_confluence_events = 0
        
        for _, row in touches.iterrows():
            price = row['Price']
            active_angles_str = row.get('Active_Angles', '{}')
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
            confluence_lines = []
            current_fan = row['Fan']
            
            for line_key, line_price in active_angles.items():
                # line_key is format "Fan_ID_Fraction"
                if str(current_fan) not in line_key: # Different fan
                    if line_price > 0:
                        diff_pct = abs(price - line_price) / line_price
                        if diff_pct <= band_pct:
                            has_confluence = True
                            confluence_lines.append(f"{line_key}: {line_price:.2f}")
                            
            if has_confluence:
                valid_confluence_events += 1
                safe_mae = max(mae, 0.1)
                is_win = mfe > safe_mae * 2
                if is_win:
                    wins += 1
                total_mfe += mfe
                total_mae += mae
                
                # Log individual event
                self.detailed_log.append({
                    "outcome": "WIN" if is_win else "MISS",
                    "time": row.get('Time', ''),
                    "fan": row['Fan'],
                    "fraction": row.get('Fraction', '-'),
                    "price": price,
                    "type": row['Type'],
                    "confluence_with": confluence_lines,
                    "O": row.get('Open', ''),
                    "H": row.get('High', ''),
                    "L": row.get('Low', ''),
                    "C": row.get('Close', ''),
                    "mfe_10": mfe,
                    "mae_10": mae
                })
                
        sample_size = valid_confluence_events
        win_rate = wins / sample_size if sample_size > 0 else 0.0
        
        return {
            "sample_size": sample_size,
            "win_rate": win_rate,
            "avg_mfe_10": total_mfe / sample_size if sample_size > 0 else 0.0,
            "avg_mae_10": total_mae / sample_size if sample_size > 0 else 0.0,
            "band_pct_used": band_pct,
            "detailed_log": self.detailed_log
        }

class PostBreachPullbackHypothesis(Hypothesis):
    """Continuation entry: enter on the re-test of a breached angle line.

    Trigger sequence (single TF):
      1. BREACH_CONFIRMED on (fan F, line X) in direction D
      2. Within next N bars: SUPPORT_TEST (D=up) or RESISTANCE_TEST (D=down)
         on the same (F, X)

    See spec section 3.2.1 priority #2.
    """
    def __init__(self):
        super().__init__(
            name="Post-Breach Pullback Continuation",
            description="Re-test of a breached line is a continuation entry in the breach direction.",
        )
        self.set_parameters(pullback_window_bars=10, min_mfe_reward_ratio=2.0)

    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        if df.empty:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0}

        breaches = df[df["Type"] == "BREACH_CONFIRMED"].copy()
        if breaches.empty:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0}

        tests = df[df["Type"].isin(["SUPPORT_TEST", "RESISTANCE_TEST"])].copy()

        N = int(self.parameters["pullback_window_bars"])
        ratio = float(self.parameters["min_mfe_reward_ratio"])
        qualifying_entries = []

        for _, brc in breaches.iterrows():
            direction = str(brc.get("Direction", "")).lower()
            same_line_mask = (
                (tests["Fan"] == brc["Fan"])
                & (tests["Fraction"] == brc["Fraction"])
                & (tests["bar_index"] > brc["bar_index"])
                & (tests["bar_index"] <= brc["bar_index"] + N)
            )
            candidates = tests[same_line_mask]

            for _, test in candidates.iterrows():
                if direction == "up" and test["Type"] == "SUPPORT_TEST":
                    qualifying_entries.append(test)
                elif direction == "down" and test["Type"] == "RESISTANCE_TEST":
                    qualifying_entries.append(test)

        if not qualifying_entries:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0}

        wins = 0
        total_mfe = 0.0
        total_mae = 0.0
        for entry in qualifying_entries:
            mfe = float(entry.get("MFE_10", 0.0) or 0.0)
            mae = float(entry.get("MAE_10", 0.0) or 0.0)
            safe_mae = max(mae, 0.1)
            if mfe > safe_mae * ratio:
                wins += 1
            total_mfe += mfe
            total_mae += mae

        n = len(qualifying_entries)
        return {
            "sample_size": n,
            "win_rate": wins / n,
            "avg_mfe_10": total_mfe / n,
            "avg_mae_10": total_mae / n,
        }


class StrategyAnalyzer:
    def __init__(self, csv_path: str, output_dir: str = None):
        self.csv_path = csv_path
        self.output_dir = output_dir or os.path.join(os.path.dirname(csv_path), "analysis")
        self.df = None
        self.hypotheses: List[Hypothesis] = []
        self.all_results: Dict[str, Dict[str, Any]] = {}
        
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
                self.all_results[hyp.name] = results
                print("-" * 30)
                print(f"Sample Size : {results.get('sample_size', 0)}")
                print(f"Win Rate    : {results.get('win_rate', 0.0):.2%}")
                print(f"Avg MFE (10): {results.get('avg_mfe_10', 0.0):.2f}")
                print(f"Avg MAE (10): {results.get('avg_mae_10', 0.0):.2f}")
                if 'total_hits' in results:
                    print(f"Target Hits : {results['total_hits']}")
                    print(f"Target Fails: {results['total_fails']}")
                    
                if 'detailed_log' in results and results['detailed_log']:
                    self._print_detailed_log(results['detailed_log'])
                        
            except Exception as e:
                print(f"Error evaluating hypothesis: {e}")
                
        print("\n" + "="*50)
    
    def _print_detailed_log(self, detailed_log: List[Dict[str, Any]]):
        print("\n" + "-" * 30)
        print("DETAILED EVENT LOG:")
        print("-" * 30)
        for i, entry in enumerate(detailed_log, 1):
            outcome = entry['outcome']
            marker = "[WIN]" if outcome == "WIN" else "[MISS]"
            print(f"\n{i}. {marker} Time: {entry['time']}")
            print(f"   Fan: {entry['fan']}, Fraction: {entry['fraction']}")
            print(f"   Target Price: {entry['target_price']:.2f}, Next Angle: {entry['next_angle']}")
            print(f"   Candle - O:{entry['O']:.2f} H:{entry['H']:.2f} L:{entry['L']:.2f} C:{entry['C']:.2f}")
            if 'breach_time' in entry:
                print(f"   Preceding Breach: {entry['breach_time']} | Fraction: {entry['breach_fraction']} | Price: {entry['breach_price']:.2f}")
            if entry.get('mfe_10'):
                print(f"   MFE_10: {entry['mfe_10']:.2f}, MAE_10: {entry['mae_10']:.2f}")
    
    def export_detailed_logs(self) -> list:
        os.makedirs(self.output_dir, exist_ok=True)
        
        exported_files = []
        
        for hyp_name, results in self.all_results.items():
            safe_name = hyp_name.lower().replace(' ', '_').replace('/', '_').replace('(', '').replace(')', '')
            json_file = os.path.join(self.output_dir, f"{safe_name}.json")
            csv_file = os.path.join(self.output_dir, f"{safe_name}.csv")
            
            if 'detailed_log' in results and results['detailed_log']:
                events = results['detailed_log']
                export_data = {
                    "hypothesis": hyp_name,
                    "description": next((h.description for h in self.hypotheses if h.name == hyp_name), ''),
                    "sample_size": results.get('sample_size', 0),
                    "win_rate": results.get('win_rate', 0.0),
                    "avg_mfe_10": results.get('avg_mfe_10', 0.0),
                    "avg_mae_10": results.get('avg_mae_10', 0.0),
                    "total_hits": results.get('total_hits', 0),
                    "total_fails": results.get('total_fails', 0),
                    "events": events
                }
                
                rows = []
                for event in events:
                    row = {
                        "Outcome": event['outcome'],
                        "Time": event['time'],
                        "Fan": event['fan'],
                        "Fraction": event['fraction'],
                        "Price": event.get('target_price', event.get('price', '')),
                        "Type": event.get('type', ''),
                        "Confluence_With": '; '.join(event.get('confluence_with', [])),
                        "O": event.get('O', ''),
                        "H": event.get('H', ''),
                        "L": event.get('L', ''),
                        "C": event.get('C', ''),
                        "Breach_Time": event.get('breach_time', ''),
                        "Breach_Fraction": event.get('breach_fraction', ''),
                        "Breach_Price": event.get('breach_price', ''),
                        "MFE_10": event.get('mfe_10', event.get('mfe_10', '')),
                        "MAE_10": event.get('mae_10', event.get('mae_10', ''))
                    }
                    rows.append(row)
                
                with open(json_file, 'w') as f:
                    json.dump(export_data, f, indent=2)
                
                csv_df = pd.DataFrame(rows)
                csv_df.to_csv(csv_file, index=False)
                
                print(f"  {hyp_name}:")
                print(f"    JSON: {json_file}")
                print(f"    CSV:  {csv_file}")
                exported_files.append((json_file, csv_file))
            else:
                export_data = {
                    "hypothesis": hyp_name,
                    "description": next((h.description for h in self.hypotheses if h.name == hyp_name), ''),
                    "sample_size": results.get('sample_size', 0),
                    "win_rate": results.get('win_rate', 0.0),
                    "avg_mfe_10": results.get('avg_mfe_10', 0.0),
                    "avg_mae_10": results.get('avg_mae_10', 0.0),
                    "band_pct_used": results.get('band_pct_used', '')
                }
                
                with open(json_file, 'w') as f:
                    json.dump(export_data, f, indent=2)
                
                print(f"  {hyp_name}:")
                print(f"    JSON: {json_file}")
                print(f"    (No detailed events)")
                exported_files.append((json_file, None))
        
        print(f"\nAll hypothesis files exported to: {self.output_dir}")
        return exported_files
    
    def get_results(self) -> Dict[str, Dict[str, Any]]:
        return self.all_results

if __name__ == "__main__":
    csv_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "simulation_events.csv")
    
    analyzer = StrategyAnalyzer(csv_file)
    
    analyzer.add_hypothesis(ConfluenceBounceHypothesis())
    analyzer.add_hypothesis(StrongSRHypothesis())
    analyzer.add_hypothesis(TargetProgressionHypothesis())
    analyzer.add_hypothesis(QuarterReversalAnomalyHypothesis())
    
    if os.path.exists(csv_file):
        analyzer.run_analysis()
        analyzer.export_detailed_logs()
    else:
        print(f"Please run the simulation first to generate {csv_file}")
