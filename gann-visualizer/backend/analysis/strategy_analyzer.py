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
        self.detailed_log = []
        
    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        self.detailed_log = []
        tests = df[df['Type'].isin(['SUPPORT_TEST', 'RESISTANCE_TEST'])].copy()
        if tests.empty:
            return {"sample_size": 0, "win_rate": 0.0, "live_sample_size": 0, "live_win_rate": 0.0, "retro_sample_size": 0, "retro_win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0, "detailed_log": []}
            
        wins = 0
        live_wins = 0
        live_total = 0
        retro_wins = 0
        retro_total = 0
        
        total_mfe = 0.0
        total_mae = 0.0
        
        ratio = self.parameters['min_mfe_reward_ratio']
        
        for _, row in tests.iterrows():
            mfe = row.get('MFE_10', np.nan)
            mae = row.get('MAE_10', np.nan)
            
            if pd.isna(mfe) or pd.isna(mae):
                continue
                
            safe_mae = max(mae, 0.1)
            is_win = mfe > safe_mae * ratio
            
            details = str(row.get("Details", ""))
            is_retro = "[Retro]" in details
            
            record = {
                "time": row.get("Time", ""),
                "fan": row.get("Fan", ""),
                "fraction": row.get("Fraction", ""),
                "type": row.get("Type", ""),
                "price": row.get("Price", 0.0),
                "is_retro": is_retro,
                "outcome": "WIN" if is_win else "LOSS",
                "mfe": mfe,
                "mae": mae
            }
            self.detailed_log.append(record)
            
            if is_win:
                wins += 1
            total_mfe += mfe
            total_mae += mae
            
            if is_retro:
                retro_total += 1
                if is_win:
                    retro_wins += 1
            else:
                live_total += 1
                if is_win:
                    live_wins += 1
            
        n = len(self.detailed_log)
        return {
            "sample_size": n,
            "win_rate": wins / n if n > 0 else 0.0,
            "live_sample_size": live_total,
            "live_win_rate": live_wins / live_total if live_total > 0 else 0.0,
            "retro_sample_size": retro_total,
            "retro_win_rate": retro_wins / retro_total if retro_total > 0 else 0.0,
            "avg_mfe_10": total_mfe / n if n > 0 else 0.0,
            "avg_mae_10": total_mae / n if n > 0 else 0.0,
            "detailed_log": self.detailed_log
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
            
        hits = 0
        live_hits = 0
        live_total = 0
        retro_hits = 0
        retro_total = 0
        
        for record in self.detailed_log:
            is_win = record["outcome"] == "WIN"
            if is_win:
                hits += 1
                
            if record.get("is_retro", False):
                retro_total += 1
                if is_win:
                    retro_hits += 1
            else:
                live_total += 1
                if is_win:
                    live_hits += 1
        
        n = len(self.detailed_log)
        
        return {
            "sample_size": n,
            "win_rate": hits / n if n > 0 else 0.0,
            "live_sample_size": live_total,
            "live_win_rate": live_hits / live_total if live_total > 0 else 0.0,
            "retro_sample_size": retro_total,
            "retro_win_rate": retro_hits / retro_total if retro_total > 0 else 0.0,
            "avg_mfe_10": 0.0,
            "avg_mae_10": 0.0,
            "total_hits": hits,
            "total_fails": n - hits,
            "detailed_log": self.detailed_log
        }
    
    def _find_preceding_breach(self, target_row: pd.Series, breaches_df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        fan = target_row.get('Fan', '')
        # Use strictly chronological bar_index instead of string-based Time
        target_bar_index = target_row.get('bar_index', 0)
        target_fraction = str(target_row.get('Fraction', ''))
        
        # Define origin angle mapping based on target progression sequence
        origin_angle_map = {
            '0.75': '0.875',
            '0.5': '0.75',
            '0.25': '0.5',
            'horizontal': '0.5',
            'full_coverage': ['0.25', 'horizontal'] # full_coverage can originate from either
        }
        
        # Determine the expected origin angle(s) for this hit
        expected_origins = []
        if target_row.get('Type') == 'TARGET_FAILED':
            # TARGET_FAILED explicitly logs its origin angle in the Fraction field
            expected_origins = [target_fraction]
        else:
            # TARGET_HIT
            mapped = origin_angle_map.get(target_fraction)
            if isinstance(mapped, list):
                expected_origins = mapped
            elif mapped:
                expected_origins = [mapped]
                
        if not expected_origins:
            return None
            
        # Determine expected breach direction based on fan polarity
        # High-anchored fans (e.g. P2 (H195-L191)) progress down
        # Low-anchored fans (e.g. P1 (L190-H195)) progress up
        expected_direction = None
        if '(' in fan:
            anchor_part = fan.split('(')[1].strip()
            if anchor_part.startswith('H'):
                expected_direction = 'down'
            elif anchor_part.startswith('L'):
                expected_direction = 'up'

        # Filter for the specific fan, strictly BEFORE OR EQUAL TO the target hit/miss bar,
        # AND matching the exact expected origin angle.
        # We use <= because a breach can be confirmed on the exact same bar that hits the target,
        # provided the breach physically occurs before the target is reached intra-bar.
        preceding_breaches = breaches_df[
            (breaches_df['Fan'] == fan) & 
            (breaches_df['bar_index'] <= target_bar_index) &
            (breaches_df['Fraction'].astype(str).isin(expected_origins))
        ]
        
        # Enforce directional monotonicity
        if expected_direction and not preceding_breaches.empty:
            if 'Direction' in preceding_breaches.columns:
                preceding_breaches = preceding_breaches[preceding_breaches['Direction'].astype(str).str.lower() == expected_direction]
            else:
                # Fallback to parsing from Details if Direction column is somehow missing
                preceding_breaches = preceding_breaches[preceding_breaches['Details'].astype(str).str.lower().str.contains(expected_direction)]
        
        if preceding_breaches.empty:
            return None
            
        # Sort by bar_index ascending just to be absolutely sure, then take the last one
        preceding_breaches = preceding_breaches.sort_values(by='bar_index')
        last_breach = preceding_breaches.iloc[-1]
        
        breach_dir = last_breach.get('Direction', '')
        if pd.isna(breach_dir) or not breach_dir:
            breach_dir = last_breach.get('Details', '').split()[0] if last_breach.get('Details', '') else ''
            
        return {
            "breach_time": last_breach.get('Time', ''),
            "breach_fraction": last_breach.get('Fraction', ''),
            "breach_price": last_breach.get('Price', 0.0),
            "breach_direction": str(breach_dir).replace('[Retro]', '').strip()
        }
    
    def _log_target_event(self, row: pd.Series, outcome: str, breaches_df: pd.DataFrame):
        time_val = row.get('Time', 'Unknown')
        fan_val = row.get('Fan', 'Unknown')
        fraction = row.get('Fraction', 'Unknown')
        price = row.get('Price', 0.0)
        next_angle = row.get('Next_Angle_Line', None)
        
        preceding_breach = self._find_preceding_breach(row, breaches_df)
        
        # CRITICAL FILTER: If there is no confirmed breach preceding this target hit/miss,
        # it is an invalid attempt (e.g. instant hit NO_ALPHA, or failed breakout).
        # We only log and evaluate progressions that actually had a valid setup.
        if not preceding_breach:
            return

        details = str(row.get("Details", ""))
        is_retro = "[Retro]" in details
        
        log_entry = {
            "outcome": outcome,
            "time": time_val,
            "fan": fan_val,
            "fraction": fraction,
            "target_price": round(price, 2),
            "next_angle": next_angle,
            "is_retro": is_retro,
            "O": row.get('Open', 0.0),
            "H": row.get('High', 0.0),
            "L": row.get('Low', 0.0),
            "C": row.get('Close', 0.0),
        }
        
        if preceding_breach:
            log_entry["breach_time"] = preceding_breach["breach_time"]
            log_entry["breach_fraction"] = preceding_breach["breach_fraction"]
            log_entry["breach_price"] = preceding_breach["breach_price"]
            log_entry["breach_direction"] = preceding_breach.get("breach_direction", "")
        
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
        self.detailed_log = []
        
    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        self.detailed_log = []
        # Interactions specifically on the 0.25 fraction
        interactions = df[(df['Fraction'] == '0.25') & (df['Type'].isin(['TOUCH', 'SUPPORT_TEST', 'RESISTANCE_TEST']))].copy()
        
        if interactions.empty:
            return {"sample_size": 0, "win_rate": 0.0, "live_sample_size": 0, "live_win_rate": 0.0, "retro_sample_size": 0, "retro_win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0, "detailed_log": []}
            
        wins = 0
        live_wins = 0
        live_total = 0
        retro_wins = 0
        retro_total = 0
        
        total_mfe = 0.0
        total_mae = 0.0
        ratio = self.parameters['min_mfe_reward_ratio']
        
        for _, row in interactions.iterrows():
            mfe = row.get('MFE_10', np.nan)
            mae = row.get('MAE_10', np.nan)
            
            if pd.isna(mfe) or pd.isna(mae):
                continue
                
            safe_mae = max(mae, 0.1)
            is_win = mfe > safe_mae * ratio
            
            details = str(row.get("Details", ""))
            is_retro = "[Retro]" in details
            
            record = {
                "time": row.get("Time", ""),
                "fan": row.get("Fan", ""),
                "fraction": row.get("Fraction", ""),
                "type": row.get("Type", ""),
                "price": row.get("Price", 0.0),
                "is_retro": is_retro,
                "outcome": "WIN" if is_win else "LOSS",
                "mfe": mfe,
                "mae": mae
            }
            self.detailed_log.append(record)
            
            if is_win:
                wins += 1
            total_mfe += mfe
            total_mae += mae
            
            if is_retro:
                retro_total += 1
                if is_win:
                    retro_wins += 1
            else:
                live_total += 1
                if is_win:
                    live_wins += 1
            
        n = len(self.detailed_log)
        return {
            "sample_size": n,
            "win_rate": wins / n if n > 0 else 0.0,
            "live_sample_size": live_total,
            "live_win_rate": live_wins / live_total if live_total > 0 else 0.0,
            "retro_sample_size": retro_total,
            "retro_win_rate": retro_wins / retro_total if retro_total > 0 else 0.0,
            "avg_mfe_10": total_mfe / n if n > 0 else 0.0,
            "avg_mae_10": total_mae / n if n > 0 else 0.0,
            "detailed_log": self.detailed_log
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
            return {"sample_size": 0, "win_rate": 0.0, "live_sample_size": 0, "live_win_rate": 0.0, "retro_sample_size": 0, "retro_win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0, "detailed_log": []}
            
        band_pct = self.parameters['price_band_pct']
        
        wins = 0
        live_wins = 0
        live_total = 0
        retro_wins = 0
        retro_total = 0
        
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
                
                details = str(row.get("Details", ""))
                is_retro = "[Retro]" in details
                
                record = {
                    "time": row.get("Time", ""),
                    "fan": row.get("Fan", ""),
                    "fraction": row.get("Fraction", ""),
                    "type": row.get("Type", ""),
                    "price": row.get("Price", 0.0),
                    "is_retro": is_retro,
                    "outcome": "WIN" if is_win else "LOSS",
                    "mfe": mfe,
                    "mae": mae,
                    "confluence_lines": confluence_lines
                }
                self.detailed_log.append(record)
                
                if is_win:
                    wins += 1
                total_mfe += mfe
                total_mae += mae
                
                if is_retro:
                    retro_total += 1
                    if is_win:
                        retro_wins += 1
                else:
                    live_total += 1
                    if is_win:
                        live_wins += 1
                
        n = len(self.detailed_log)
        return {
            "sample_size": n,
            "win_rate": wins / n if n > 0 else 0.0,
            "live_sample_size": live_total,
            "live_win_rate": live_wins / live_total if live_total > 0 else 0.0,
            "retro_sample_size": retro_total,
            "retro_win_rate": retro_wins / retro_total if retro_total > 0 else 0.0,
            "avg_mfe_10": total_mfe / n if n > 0 else 0.0,
            "avg_mae_10": total_mae / n if n > 0 else 0.0,
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
        self.detailed_log = []

    def evaluate(self, df: pd.DataFrame) -> Dict[str, Any]:
        self.detailed_log = []
        if df.empty:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0, "detailed_log": []}

        breaches = df[df["Type"] == "BREACH_CONFIRMED"].copy()
        if breaches.empty:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0, "detailed_log": []}

        tests = df[df["Type"].isin(["SUPPORT_TEST", "RESISTANCE_TEST"])].copy()

        N = int(self.parameters["pullback_window_bars"])
        ratio = float(self.parameters["min_mfe_reward_ratio"])
        qualifying_entries = []

        for _, brc in breaches.iterrows():
            direction = str(brc.get("Direction", "")).lower()
            breach_time = brc.get("Time", "")
            fan = brc["Fan"]
            fraction = brc["Fraction"]
            b_idx = brc["bar_index"]

            details = str(brc.get("Details", ""))
            is_retro = "[Retro]" in details

            # Log the breach event being evaluated
            breach_record = {
                "breach_time": breach_time,
                "fan": fan,
                "fraction": fraction,
                "direction": direction,
                "is_retro": is_retro,
                "status": "NO_PULLBACK_FOUND", # Default status
                "pullback_time": None,
                "pullback_type": None,
                "mfe": 0.0,
                "mae": 0.0,
                "outcome": None,
                "reason": "No subsequent test within window"
            }

            # Find ALL tests on this line after the breach (even beyond N bars, to see why they might be rejected)
            future_tests = tests[
                (tests["Fan"] == fan) & 
                (tests["Fraction"] == fraction) & 
                (tests["bar_index"] > b_idx)
            ].sort_values("bar_index")

            if future_tests.empty:
                # Find what DID happen within N bars for this fan to provide context
                future_events = df[
                    (df["Fan"] == fan) & 
                    (df["bar_index"] > b_idx) & 
                    (df["bar_index"] <= b_idx + N)
                ].sort_values("bar_index")
                
                if not future_events.empty:
                    # Summarize what happened instead
                    unique_summary = []
                    for _, ev in future_events.iterrows():
                        summary_str = f"{ev['Type']} on {ev['Fraction']}"
                        if summary_str not in unique_summary:
                            unique_summary.append(summary_str)
                    
                    breach_record["reason"] = f"No test on this line. Within {N} bars saw: {', '.join(unique_summary[:3])}"
                else:
                    breach_record["reason"] = f"No test on this line. No events at all for this fan within {N} bars (possibly invalidated or price drifted)."
                
                self.detailed_log.append(breach_record)
                continue
            
            # Look for the first test
            first_test = future_tests.iloc[0]
            test_idx = first_test["bar_index"]
            test_type = first_test["Type"]
            test_time = first_test.get("Time", "")

            breach_record["pullback_time"] = test_time
            breach_record["pullback_type"] = test_type
            breach_record["bars_elapsed"] = test_idx - b_idx
            breach_record["pullback_price"] = float(first_test.get("Price", 0.0) or 0.0)
            breach_record["breach_price"] = float(brc.get("Price", 0.0) or 0.0)

            if test_idx > b_idx + N:
                breach_record["status"] = "REJECTED"
                breach_record["reason"] = f"Test occurred outside {N}-bar window (happened {test_idx - b_idx} bars later)"
                self.detailed_log.append(breach_record)
                continue

            # It is within window. Check direction
            if direction == "up" and test_type != "SUPPORT_TEST":
                breach_record["status"] = "REJECTED"
                breach_record["reason"] = f"Breach UP requires SUPPORT_TEST, but got {test_type} ({test_idx - b_idx} bars later)"
                self.detailed_log.append(breach_record)
                continue
            elif direction == "down" and test_type != "RESISTANCE_TEST":
                breach_record["status"] = "REJECTED"
                breach_record["reason"] = f"Breach DOWN requires RESISTANCE_TEST, but got {test_type} ({test_idx - b_idx} bars later)"
                self.detailed_log.append(breach_record)
                continue

            # Valid qualifying pullback
            # ONLY grab the first test if there are multiple tests for the SAME breach
            qualifying_entries.append(first_test)
            mfe = float(first_test.get("MFE_10", 0.0) or 0.0)
            mae = float(first_test.get("MAE_10", 0.0) or 0.0)
            safe_mae = max(mae, 0.1)
            is_win = mfe > safe_mae * ratio

            breach_record["status"] = "ACCEPTED"
            breach_record["reason"] = "Valid Post-Breach Pullback"
            breach_record["mfe"] = mfe
            breach_record["mae"] = mae
            breach_record["outcome"] = "WIN" if is_win else "LOSS"
            self.detailed_log.append(breach_record)

        if not qualifying_entries:
            return {"sample_size": 0, "win_rate": 0.0, "live_sample_size": 0, "live_win_rate": 0.0, "retro_sample_size": 0, "retro_win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0, "detailed_log": self.detailed_log}

        wins = 0
        live_wins = 0
        live_total = 0
        retro_wins = 0
        retro_total = 0
        
        total_mfe = 0.0
        total_mae = 0.0
        
        # Track statistics directly from the detailed_log for Accepted trades
        for record in self.detailed_log:
            if record["status"] == "ACCEPTED":
                if record["outcome"] == "WIN":
                    wins += 1
                total_mfe += record["mfe"]
                total_mae += record["mae"]
                
                if record.get("is_retro", False):
                    retro_total += 1
                    if record["outcome"] == "WIN":
                        retro_wins += 1
                else:
                    live_total += 1
                    if record["outcome"] == "WIN":
                        live_wins += 1

        n = live_total + retro_total
        return {
            "sample_size": n,
            "win_rate": wins / n if n > 0 else 0.0,
            "live_sample_size": live_total,
            "live_win_rate": live_wins / live_total if live_total > 0 else 0.0,
            "retro_sample_size": retro_total,
            "retro_win_rate": retro_wins / retro_total if retro_total > 0 else 0.0,
            "avg_mfe_10": total_mfe / n if n > 0 else 0.0,
            "avg_mae_10": total_mae / n if n > 0 else 0.0,
            "detailed_log": self.detailed_log
        }


class MultiTFReversalHypothesis(Hypothesis):
    """HTF respect of a major angle line triggers LTF reversal entry.

    Trigger sequence:
      1. HTF event ∈ {SUPPORT_TEST, RESISTANCE_TEST} on a fan line whose
         fraction matches `line_filter` (default "0.5").
      2. Within `entry_window_htf_bars` HTF-bar durations after the HTF
         close, an LTF bar that:
           - closes in the trigger direction (long if HTF SUPPORT_TEST,
             short if HTF RESISTANCE_TEST), AND
           - has body/range ratio ≥ `body_ratio_min`.

    See spec §3.2.1 priority #1 for the full hypothesis specification.

    Note: this class takes TWO DataFrames (LTF events, HTF events) — unlike
    the single-DataFrame hypotheses. The base Hypothesis.evaluate(df) signature
    is preserved for compatibility but here `df` is the LTF DataFrame and
    HTF events are passed as a second positional argument.
    """
    def __init__(self):
        super().__init__(
            name="Multi-TF Reversal",
            description="HTF respect of a major angle line triggers LTF reversal entry.",
        )
        self.set_parameters(
            htf="60",
            ltf="5",
            line_filter="0.5",
            entry_window_htf_bars=1,
            body_ratio_min=0.5,
            min_mfe_reward_ratio=2.0,
        )

    def evaluate(self, ltf: pd.DataFrame, htf: pd.DataFrame = None) -> Dict[str, Any]:
        from analysis.multi_tf_helper import compute_bar_close_time, merge_asof_htf_to_ltf, timeframe_seconds

        if htf is None or ltf.empty or htf.empty:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0}

        line_filter = str(self.parameters["line_filter"])
        body_ratio_min = float(self.parameters["body_ratio_min"])
        entry_window_htf_bars = int(self.parameters["entry_window_htf_bars"])
        ratio = float(self.parameters["min_mfe_reward_ratio"])
        htf_tf = str(self.parameters["htf"])
        htf_bar_seconds = timeframe_seconds(htf_tf)

        # Filter HTF to qualifying triggers only (right line + right event type)
        htf_filtered = htf[
            (htf["Type"].isin(["SUPPORT_TEST", "RESISTANCE_TEST"]))
            & (htf["Fraction"].astype(str) == line_filter)
        ].copy()
        if htf_filtered.empty:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0}

        # Compute bar_close_time on both
        ltf_bc = compute_bar_close_time(ltf)
        htf_bc = compute_bar_close_time(htf_filtered)

        # Multi-instrument 'by' parameter if column present in both
        join_by = "Instrument" if ("Instrument" in ltf.columns and "Instrument" in htf.columns) else None

        merged = merge_asof_htf_to_ltf(ltf_bc, htf_bc, by=join_by)

        # Apply window: LTF bar_close_time must be within entry_window_htf_bars
        # of the HTF event's bar_close_time. Note: the merged index is
        # bar_close_time (LTF close); htf_bar_close_time is a column.
        if "htf_bar_close_time" in merged.columns:
            window_seconds = entry_window_htf_bars * htf_bar_seconds
            # LTF bar_close_time is the index; htf_bar_close_time is a column.
            time_gap = merged.index - merged["htf_bar_close_time"]
            in_window = (time_gap >= 0) & (time_gap <= window_seconds)
        else:
            in_window = pd.Series([False] * len(merged), index=merged.index)

        # Body ratio filter
        rng = (merged["High"] - merged["Low"]).replace(0, 1e-9)
        body = (merged["Close"] - merged["Open"]).abs()
        body_ok = (body / rng) >= body_ratio_min

        # Direction filter: HTF SUPPORT_TEST → look long → LTF must close > open
        # HTF RESISTANCE_TEST → look short → LTF must close < open
        htf_type = merged["htf_event_type"] if "htf_event_type" in merged.columns else pd.Series([None] * len(merged), index=merged.index)
        long_signal = (htf_type == "SUPPORT_TEST") & (merged["Close"] > merged["Open"])
        short_signal = (htf_type == "RESISTANCE_TEST") & (merged["Close"] < merged["Open"])
        direction_ok = long_signal | short_signal

        qualifying = merged[in_window & body_ok & direction_ok]

        if qualifying.empty:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0, "avg_mae_10": 0.0}

        wins = 0
        total_mfe = 0.0
        total_mae = 0.0
        for _, row in qualifying.iterrows():
            mfe = float(row.get("MFE_10", 0.0) or 0.0)
            mae = float(row.get("MAE_10", 0.0) or 0.0)
            safe_mae = max(mae, 0.1)
            if mfe > safe_mae * ratio:
                wins += 1
            total_mfe += mfe
            total_mae += mae

        n = len(qualifying)
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
