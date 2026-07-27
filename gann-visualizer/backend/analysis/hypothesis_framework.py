"""
Unified Hypothesis Framework — runs all hypotheses + walk-forward validation.

Architecture:
  Layer 1: Metrics (event_logger.py) — computed during simulation
  Layer 2: Hypotheses (strategy_analyzer.py + this file) — post-simulation
  Layer 3: Walk-forward validation (this file) — wraps every hypothesis

Output: <run_dir>/analysis/hypotheses/ with per-hypothesis JSON + run_summary
"""
import os
import json
import math
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional

from .strategy_analyzer import (
    Hypothesis,
    StrongSRHypothesis,
    QuarterReversalAnomalyHypothesis,
    ConfluenceBounceHypothesis,
    TargetProgressionHypothesis,
    PostBreachPullbackHypothesis,
)
from .rsi_trendline_hypothesis import RSITrendlineBreakHypothesis

from .exit_optimizer import ExitOptimizer, filter_bounce_events


class ReversalByAngleLineHypothesis(Hypothesis):
    """Tests reversal win rate broken down by angle line (0.25, 0.5, 0.75, 0.875, horizontal)."""

    def __init__(self):
        super().__init__(
            name="Reversal by Angle Line",
            description="Which angle division lines produce the best reversals? "
                        "Tests SUPPORT_TEST and RESISTANCE_TEST events using Reversal_Outcome."
        )
        self.detailed_log = []

    def evaluate(self, df: pd.DataFrame, candles_df=None, fan_catalog=None) -> Dict[str, Any]:
        self.detailed_log = []
        tests = df[df['Type'].isin(['SUPPORT_TEST', 'RESISTANCE_TEST'])].copy()

        if tests.empty:
            return self._empty_result()

        wins = 0
        live_wins = 0
        live_total = 0
        retro_wins = 0
        retro_total = 0
        total_mfe = 0.0
        total_mae = 0.0

        # Per-fraction accumulators
        frac_stats = {}

        for _, row in tests.iterrows():
            outcome = row.get('Reversal_Outcome', None)
            if pd.isna(outcome) or str(outcome).strip() == '':
                continue

            is_win = str(outcome).strip() == 'WIN'
            mfe = row.get('MFE_10', 0.0)
            mae = row.get('MAE_10', 0.0)
            if pd.isna(mfe):
                mfe = 0.0
            if pd.isna(mae):
                mae = 0.0

            details = str(row.get("Details", ""))
            is_retro = "[Retro]" in details
            fraction = str(row.get("Fraction", ""))

            record = {
                "time": row.get("Time", ""),
                "fan": row.get("Fan", ""),
                "fraction": fraction,
                "type": row.get("Type", ""),
                "price": row.get("Price", 0.0),
                "is_retro": is_retro,
                "outcome": "WIN" if is_win else "LOSS",
                "mfe": mfe,
                "mae": mae,
                "anchor_bar_index": row.get("anchor_bar_index", 0),
                "scale_ratio": row.get("scale_ratio", 1.0),
                "anchor_price": row.get("anchor_price", 0.0),
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

            # Accumulate per-fraction
            if fraction not in frac_stats:
                frac_stats[fraction] = {"wins": 0, "total": 0, "mfe": 0.0, "mae": 0.0}
            frac_stats[fraction]["total"] += 1
            frac_stats[fraction]["mfe"] += mfe
            frac_stats[fraction]["mae"] += mae
            if is_win:
                frac_stats[fraction]["wins"] += 1

        n = len(self.detailed_log)
        if n == 0:
            return self._empty_result()

        # Build groups dict
        groups = {}
        for frac, s in sorted(frac_stats.items()):
            t = s["total"]
            groups[frac] = {
                "sample_size": t,
                "win_rate": s["wins"] / t if t > 0 else 0.0,
                "avg_mfe_10": s["mfe"] / t if t > 0 else 0.0,
                "avg_mae_10": s["mae"] / t if t > 0 else 0.0,
            }

        return {
            "sample_size": n,
            "win_rate": wins / n if n > 0 else 0.0,
            "live_sample_size": live_total,
            "live_win_rate": live_wins / live_total if live_total > 0 else 0.0,
            "retro_sample_size": retro_total,
            "retro_win_rate": retro_wins / retro_total if retro_total > 0 else 0.0,
            "avg_mfe_10": total_mfe / n if n > 0 else 0.0,
            "avg_mae_10": total_mae / n if n > 0 else 0.0,
            "composite": (total_mfe / n) * math.sqrt(n) if n > 0 else 0.0,
            "groups": groups,
            "detailed_log": self.detailed_log,
        }

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "sample_size": 0, "win_rate": 0.0, "live_sample_size": 0, "live_win_rate": 0.0,
            "retro_sample_size": 0, "retro_win_rate": 0.0,
            "avg_mfe_10": 0.0, "avg_mae_10": 0.0, "composite": 0.0,
            "groups": {}, "detailed_log": [],
        }


class BounceFollowThroughV2Hypothesis(Hypothesis):
    """Bounce Follow-Through V2 — stricter confirmation rules.

    V2 enhancements over V1:
      - No T+0 (test and confirmation on same bar) — minimum 1 bar delay
      - Confirmation bar body check (close > open for bounce, close < open for rejection)
      - Follow-through: confirmation bar close must be beyond test bar's close in the expected direction
      - 3-bar lookback window (vs 5 in V1)
    """

    def __init__(self):
        super().__init__(
            name="Bounce Follow-Through V2",
            description="Stricter bounce/rejection with no T+0, body confirmation, "
                        "and follow-through close check. Win = MFE_10 > MAE_10 * 1.5."
        )
        self.set_parameters(min_mfe_reward_ratio=1.5, max_lookback_bars=3)
        self.detailed_log = []

    def evaluate(self, df: pd.DataFrame, candles_df=None, fan_catalog=None) -> Dict[str, Any]:
        self.detailed_log = []
        bounces = df[df['Type'].isin(['SUPPORT_BOUNCE', 'RESISTANCE_REJECTION'])].copy()

        if bounces.empty:
            return self._empty_result()

        # Pre-index candles if available
        candles_indexed = None
        if candles_df is not None and len(candles_df) > 0:
            candles_indexed = candles_df.copy()
            # Ensure bar_index exists
            if 'bar_index' not in candles_indexed.columns and 'Bar_Index' not in candles_indexed.columns:
                candles_indexed = candles_indexed.reset_index()
            bar_col = 'bar_index' if 'bar_index' in candles_indexed.columns else 'Bar_Index'

        ratio = self.parameters['min_mfe_reward_ratio']
        max_lookback = self.parameters['max_lookback_bars']
        wins = 0
        live_wins = 0
        live_total = 0
        retro_wins = 0
        retro_total = 0
        total_mfe = 0.0
        total_mae = 0.0
        type_stats = {}
        frac_stats = {}
        rejected_count = 0  # T+0 and other rejections

        for _, row in bounces.iterrows():
            mfe = row.get('MFE_10', np.nan)
            mae = row.get('MAE_10', np.nan)
            if pd.isna(mfe) or pd.isna(mae):
                continue

            details = str(row.get("Details", ""))
            etype = row.get("Type", "")
            conf_bar_idx = row.get('bar_index', row.get('Bar_Index', 0))

            # V2 Rule 1: Parse T+N delay, reject T+0
            t_delay = self._parse_t_delay(details)
            if t_delay == 0:
                rejected_count += 1
                continue  # T+0: same-bar test and confirmation — skip

            # V2 Rule 2: Lookback window check
            if t_delay > max_lookback:
                rejected_count += 1
                continue

            # V2 Rules 3+4: Body check and follow-through (requires candles)
            if candles_indexed is not None and t_delay > 0:
                conf_candle = candles_indexed[candles_indexed[bar_col] == conf_bar_idx]
                if conf_candle.empty:
                    rejected_count += 1
                    continue
                conf_close = conf_candle.iloc[0].get('Close', conf_candle.iloc[0].get('close', 0))
                conf_open = conf_candle.iloc[0].get('Open', conf_candle.iloc[0].get('open', 0))

                # Look up test bar
                test_bar_idx = conf_bar_idx - t_delay
                test_candle = candles_indexed[candles_indexed[bar_col] == test_bar_idx]
                if test_candle.empty:
                    rejected_count += 1
                    continue
                test_close = test_candle.iloc[0].get('Close', test_candle.iloc[0].get('close', 0))

                if etype == 'SUPPORT_BOUNCE':
                    # Body: confirmation bar must be bullish (close > open)
                    if conf_close <= conf_open:
                        rejected_count += 1
                        continue
                    # Follow-through: confirmation close must be above test bar's close
                    if conf_close <= test_close:
                        rejected_count += 1
                        continue
                elif etype == 'RESISTANCE_REJECTION':
                    # Body: confirmation bar must be bearish (close < open)
                    if conf_close >= conf_open:
                        rejected_count += 1
                        continue
                    # Follow-through: confirmation close must be below test bar's close
                    if conf_close >= test_close:
                        rejected_count += 1
                        continue

            is_retro = "[Retro]" in details
            safe_mae = max(mae, 0.1)
            is_win = mfe > safe_mae * ratio

            record = {
                "time": row.get("Time", ""),
                "fan": row.get("Fan", ""),
                "fraction": row.get("Fraction", ""),
                "type": etype,
                "price": row.get("Price", 0.0),
                "is_retro": is_retro,
                "outcome": "WIN" if is_win else "LOSS",
                "mfe": mfe,
                "mae": mae,
                "anchor_bar_index": row.get("anchor_bar_index", 0),
                "scale_ratio": row.get("scale_ratio", 1.0),
                "anchor_price": row.get("anchor_price", 0.0),
                "details": f"{'[Retro] ' if is_retro else ''}{details}",
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

            # Per-type stats
            if etype not in type_stats:
                type_stats[etype] = {"wins": 0, "total": 0, "mfe": 0.0, "mae": 0.0}
            type_stats[etype]["total"] += 1
            type_stats[etype]["mfe"] += mfe
            type_stats[etype]["mae"] += mae
            if is_win:
                type_stats[etype]["wins"] += 1

            # Per-angle (fraction) stats
            fraction = str(row.get("Fraction", ""))
            if fraction not in frac_stats:
                frac_stats[fraction] = {"wins": 0, "total": 0, "mfe": 0.0, "mae": 0.0}
            frac_stats[fraction]["total"] += 1
            frac_stats[fraction]["mfe"] += mfe
            frac_stats[fraction]["mae"] += mae
            if is_win:
                frac_stats[fraction]["wins"] += 1

        n = len(self.detailed_log)
        if n == 0:
            return self._empty_result()

        groups = {}
        for etype_key, s in sorted(type_stats.items()):
            t = s["total"]
            groups[etype_key] = {
                "sample_size": t,
                "win_rate": s["wins"] / t if t > 0 else 0.0,
                "avg_mfe_10": s["mfe"] / t if t > 0 else 0.0,
                "avg_mae_10": s["mae"] / t if t > 0 else 0.0,
            }
        for frac, s in sorted(frac_stats.items()):
            t = s["total"]
            groups[f"angle:{frac}"] = {
                "sample_size": t,
                "win_rate": s["wins"] / t if t > 0 else 0.0,
                "avg_mfe_10": s["mfe"] / t if t > 0 else 0.0,
                "avg_mae_10": s["mae"] / t if t > 0 else 0.0,
            }

        return {
            "sample_size": n,
            "win_rate": wins / n if n > 0 else 0.0,
            "live_sample_size": live_total,
            "live_win_rate": live_wins / live_total if live_total > 0 else 0.0,
            "retro_sample_size": retro_total,
            "retro_win_rate": retro_wins / retro_total if retro_total > 0 else 0.0,
            "avg_mfe_10": total_mfe / n if n > 0 else 0.0,
            "avg_mae_10": total_mae / n if n > 0 else 0.0,
            "composite": (total_mfe / n) * math.sqrt(n) if n > 0 else 0.0,
            "groups": groups,
            "detailed_log": self.detailed_log,
            "rejected_by_v2": rejected_count,
        }

    def _parse_t_delay(self, details: str) -> int:
        """Parse 'Bounced (T+2 bars)' or 'Rejected (T+1 bars)' -> 2 or 1."""
        import re
        m = re.search(r'T\+(\d+)', str(details))
        return int(m.group(1)) if m else 0

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "sample_size": 0, "win_rate": 0.0, "live_sample_size": 0, "live_win_rate": 0.0,
            "retro_sample_size": 0, "retro_win_rate": 0.0,
            "avg_mfe_10": 0.0, "avg_mae_10": 0.0, "composite": 0.0,
            "groups": {}, "detailed_log": [], "rejected_by_v2": 0,
        }


class BounceFollowThroughHypothesis(Hypothesis):
    """Tests whether confirmed bounces/rejections have sustained follow-through."""

    def __init__(self):
        super().__init__(
            name="Bounce Follow-Through",
            description="After SUPPORT_BOUNCE/RESISTANCE_REJECTION confirms, does momentum sustain? "
                        "Win = MFE_10 > MAE_10 * 1.5 (lower bar — bounce already confirmed)."
        )
        self.set_parameters(min_mfe_reward_ratio=1.5)
        self.detailed_log = []

    def evaluate(self, df: pd.DataFrame, candles_df=None, fan_catalog=None) -> Dict[str, Any]:
        self.detailed_log = []
        bounces = df[df['Type'].isin(['SUPPORT_BOUNCE', 'RESISTANCE_REJECTION'])].copy()

        if bounces.empty:
            return self._empty_result()

        ratio = self.parameters['min_mfe_reward_ratio']
        wins = 0
        live_wins = 0
        live_total = 0
        retro_wins = 0
        retro_total = 0
        total_mfe = 0.0
        total_mae = 0.0
        type_stats = {}
        frac_stats = {}

        for _, row in bounces.iterrows():
            mfe = row.get('MFE_10', np.nan)
            mae = row.get('MAE_10', np.nan)
            if pd.isna(mfe) or pd.isna(mae):
                continue

            safe_mae = max(mae, 0.1)
            is_win = mfe > safe_mae * ratio
            details = str(row.get("Details", ""))
            is_retro = "[Retro]" in details
            etype = row.get("Type", "")

            record = {
                "time": row.get("Time", ""),
                "fan": row.get("Fan", ""),
                "fraction": row.get("Fraction", ""),
                "type": etype,
                "price": row.get("Price", 0.0),
                "is_retro": is_retro,
                "outcome": "WIN" if is_win else "LOSS",
                "mfe": mfe,
                "mae": mae,
                "anchor_bar_index": row.get("anchor_bar_index", 0),
                "scale_ratio": row.get("scale_ratio", 1.0),
                "anchor_price": row.get("anchor_price", 0.0),
                "details": details,  # e.g., "Bounced (T+2 bars)" / "Rejected (T+3 bars)"
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

            # Per-type stats
            if etype not in type_stats:
                type_stats[etype] = {"wins": 0, "total": 0, "mfe": 0.0, "mae": 0.0}
            type_stats[etype]["total"] += 1
            type_stats[etype]["mfe"] += mfe
            type_stats[etype]["mae"] += mae
            if is_win:
                type_stats[etype]["wins"] += 1

            # Per-angle (fraction) stats
            fraction = str(row.get("Fraction", ""))
            if fraction not in frac_stats:
                frac_stats[fraction] = {"wins": 0, "total": 0, "mfe": 0.0, "mae": 0.0}
            frac_stats[fraction]["total"] += 1
            frac_stats[fraction]["mfe"] += mfe
            frac_stats[fraction]["mae"] += mae
            if is_win:
                frac_stats[fraction]["wins"] += 1

        n = len(self.detailed_log)
        if n == 0:
            return self._empty_result()

        groups = {}
        for etype, s in sorted(type_stats.items()):
            t = s["total"]
            groups[etype] = {
                "sample_size": t,
                "win_rate": s["wins"] / t if t > 0 else 0.0,
                "avg_mfe_10": s["mfe"] / t if t > 0 else 0.0,
                "avg_mae_10": s["mae"] / t if t > 0 else 0.0,
            }
        for frac, s in sorted(frac_stats.items()):
            t = s["total"]
            groups[f"angle:{frac}"] = {
                "sample_size": t,
                "win_rate": s["wins"] / t if t > 0 else 0.0,
                "avg_mfe_10": s["mfe"] / t if t > 0 else 0.0,
                "avg_mae_10": s["mae"] / t if t > 0 else 0.0,
            }

        return {
            "sample_size": n,
            "win_rate": wins / n if n > 0 else 0.0,
            "live_sample_size": live_total,
            "live_win_rate": live_wins / live_total if live_total > 0 else 0.0,
            "retro_sample_size": retro_total,
            "retro_win_rate": retro_wins / retro_total if retro_total > 0 else 0.0,
            "avg_mfe_10": total_mfe / n if n > 0 else 0.0,
            "avg_mae_10": total_mae / n if n > 0 else 0.0,
            "composite": (total_mfe / n) * math.sqrt(n) if n > 0 else 0.0,
            "groups": groups,
            "detailed_log": self.detailed_log,
        }

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "sample_size": 0, "win_rate": 0.0, "live_sample_size": 0, "live_win_rate": 0.0,
            "retro_sample_size": 0, "retro_win_rate": 0.0,
            "avg_mfe_10": 0.0, "avg_mae_10": 0.0, "composite": 0.0,
            "groups": {}, "detailed_log": [],
        }


class BounceFollowThroughV3Hypothesis(Hypothesis):
    """Bounce Follow-Through V3 — stricter than V2.

    V3 additions over V2:
      - Minimum 2-bar delay: reject T+0 and T+1 (only T+2/T+3 qualify)
      - MFE:MAE reward ratio raised to 2.0 (from 1.5 in V2)
      - Same body check and follow-through close rules as V2
    """

    def __init__(self):
        super().__init__(
            name="Bounce Follow-Through V3",
            description="V3: min 2-bar delay, MFE:MAE >= 2.0, body confirmation, "
                        "follow-through close check. Win = MFE_10 > MAE_10 * 2.0."
        )
        self.set_parameters(min_mfe_reward_ratio=2.0, max_lookback_bars=3, min_confirm_bars=2)
        self.detailed_log = []

    def evaluate(self, df: pd.DataFrame, candles_df=None, fan_catalog=None) -> Dict[str, Any]:
        self.detailed_log = []
        bounces = df[df['Type'].isin(['SUPPORT_BOUNCE', 'RESISTANCE_REJECTION'])].copy()

        if bounces.empty:
            return self._empty_result()

        candles_indexed = None
        if candles_df is not None and len(candles_df) > 0:
            candles_indexed = candles_df.copy()
            if 'bar_index' not in candles_indexed.columns and 'Bar_Index' not in candles_indexed.columns:
                candles_indexed = candles_indexed.reset_index()
            bar_col = 'bar_index' if 'bar_index' in candles_indexed.columns else 'Bar_Index'

        ratio = self.parameters['min_mfe_reward_ratio']
        max_lookback = self.parameters['max_lookback_bars']
        min_bars = self.parameters['min_confirm_bars']
        wins = 0
        live_wins = 0
        live_total = 0
        retro_wins = 0
        retro_total = 0
        total_mfe = 0.0
        total_mae = 0.0
        type_stats = {}
        frac_stats = {}
        rejected_count = 0

        for _, row in bounces.iterrows():
            mfe = row.get('MFE_10', np.nan)
            mae = row.get('MAE_10', np.nan)
            if pd.isna(mfe) or pd.isna(mae):
                continue

            details = str(row.get("Details", ""))
            etype = row.get("Type", "")
            conf_bar_idx = row.get('bar_index', row.get('Bar_Index', 0))

            # V3 Rule 1: Parse T+N delay, reject T+0 and T+1 (min_confirm_bars=2)
            t_delay = self._parse_t_delay(details)
            if t_delay < min_bars:
                rejected_count += 1
                continue

            # V3 Rule 2: Lookback window check
            if t_delay > max_lookback:
                rejected_count += 1
                continue

            # V3 Rules 3+4: Body check and follow-through (same as V2)
            if candles_indexed is not None and t_delay > 0:
                conf_candle = candles_indexed[candles_indexed[bar_col] == conf_bar_idx]
                if conf_candle.empty:
                    rejected_count += 1
                    continue
                conf_close = conf_candle.iloc[0].get('Close', conf_candle.iloc[0].get('close', 0))
                conf_open = conf_candle.iloc[0].get('Open', conf_candle.iloc[0].get('open', 0))

                test_bar_idx = conf_bar_idx - t_delay
                test_candle = candles_indexed[candles_indexed[bar_col] == test_bar_idx]
                if test_candle.empty:
                    rejected_count += 1
                    continue
                test_close = test_candle.iloc[0].get('Close', test_candle.iloc[0].get('close', 0))

                if etype == 'SUPPORT_BOUNCE':
                    if conf_close <= conf_open:
                        rejected_count += 1
                        continue
                    if conf_close <= test_close:
                        rejected_count += 1
                        continue
                elif etype == 'RESISTANCE_REJECTION':
                    if conf_close >= conf_open:
                        rejected_count += 1
                        continue
                    if conf_close >= test_close:
                        rejected_count += 1
                        continue

            is_retro = "[Retro]" in details
            # V3: raised ratio to 2.0
            safe_mae = max(mae, 0.1)
            is_win = mfe > safe_mae * ratio

            record = {
                "time": row.get("Time", ""),
                "fan": row.get("Fan", ""),
                "fraction": row.get("Fraction", ""),
                "type": etype,
                "price": row.get("Price", 0.0),
                "is_retro": is_retro,
                "outcome": "WIN" if is_win else "LOSS",
                "mfe": mfe,
                "mae": mae,
                "anchor_bar_index": row.get("anchor_bar_index", 0),
                "scale_ratio": row.get("scale_ratio", 1.0),
                "anchor_price": row.get("anchor_price", 0.0),
                "details": f"{'[Retro] ' if is_retro else ''}{details}",
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

            if etype not in type_stats:
                type_stats[etype] = {"wins": 0, "total": 0, "mfe": 0.0, "mae": 0.0}
            type_stats[etype]["total"] += 1
            type_stats[etype]["mfe"] += mfe
            type_stats[etype]["mae"] += mae
            if is_win:
                type_stats[etype]["wins"] += 1

            fraction = str(row.get("Fraction", ""))
            if fraction not in frac_stats:
                frac_stats[fraction] = {"wins": 0, "total": 0, "mfe": 0.0, "mae": 0.0}
            frac_stats[fraction]["total"] += 1
            frac_stats[fraction]["mfe"] += mfe
            frac_stats[fraction]["mae"] += mae
            if is_win:
                frac_stats[fraction]["wins"] += 1

        n = len(self.detailed_log)
        if n == 0:
            return self._empty_result()

        groups = {}
        for etype_key, s in sorted(type_stats.items()):
            t = s["total"]
            groups[etype_key] = {
                "sample_size": t,
                "win_rate": s["wins"] / t if t > 0 else 0.0,
                "avg_mfe_10": s["mfe"] / t if t > 0 else 0.0,
                "avg_mae_10": s["mae"] / t if t > 0 else 0.0,
            }
        for frac, s in sorted(frac_stats.items()):
            t = s["total"]
            groups[f"angle:{frac}"] = {
                "sample_size": t,
                "win_rate": s["wins"] / t if t > 0 else 0.0,
                "avg_mfe_10": s["mfe"] / t if t > 0 else 0.0,
                "avg_mae_10": s["mae"] / t if t > 0 else 0.0,
            }

        return {
            "sample_size": n,
            "win_rate": wins / n if n > 0 else 0.0,
            "live_sample_size": live_total,
            "live_win_rate": live_wins / live_total if live_total > 0 else 0.0,
            "retro_sample_size": retro_total,
            "retro_win_rate": retro_wins / retro_total if retro_total > 0 else 0.0,
            "avg_mfe_10": total_mfe / n if n > 0 else 0.0,
            "avg_mae_10": total_mae / n if n > 0 else 0.0,
            "composite": (total_mfe / n) * math.sqrt(n) if n > 0 else 0.0,
            "groups": groups,
            "detailed_log": self.detailed_log,
            "rejected_by_v3": rejected_count,
        }

    def _parse_t_delay(self, details: str) -> int:
        """Parse 'Bounced (T+2 bars)' or 'Rejected (T+1 bars)' -> 2 or 1."""
        import re
        m = re.search(r'T\+(\d+)', str(details))
        return int(m.group(1)) if m else 0

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "sample_size": 0, "win_rate": 0.0, "live_sample_size": 0, "live_win_rate": 0.0,
            "retro_sample_size": 0, "retro_win_rate": 0.0,
            "avg_mfe_10": 0.0, "avg_mae_10": 0.0, "composite": 0.0,
            "groups": {}, "detailed_log": [], "rejected_by_v3": 0,
        }


# ---- Parametric Bounce Follow-Through engine for V4-V9 ----

class _BounceFollowThroughParam(Hypothesis):
    """Parametric bounce follow-through — configurable delay, lookback, and ratio."""

    def __init__(self, name, description, min_bars, max_lookback, mfe_ratio, trend_aligned_only=False, counter_trend_only=False):
        super().__init__(name=name, description=description)
        self.set_parameters(
            min_confirm_bars=min_bars,
            max_lookback_bars=max_lookback,
            min_mfe_reward_ratio=mfe_ratio,
            trend_aligned_only=trend_aligned_only,
            counter_trend_only=counter_trend_only,
        )
        self.detailed_log = []

    def evaluate(self, df: pd.DataFrame, candles_df=None, fan_catalog=None) -> Dict[str, Any]:
        self.detailed_log = []
        bounces = df[df['Type'].isin(['SUPPORT_BOUNCE', 'RESISTANCE_REJECTION'])].copy()

        if bounces.empty:
            return self._empty_result()

        # Build timestamp-based candle lookup (matches filter_bounce_events pattern)
        candle_lookup = {}      # sequential index -> {open, close, timestamp}
        ts_to_candle_idx = {}   # timestamp -> sequential index
        if candles_df is not None and len(candles_df) > 0:
            for c_idx, c in candles_df.iterrows():
                candle_data = {
                    'open': float(c.get('open', c.get('Open', 0))),
                    'close': float(c.get('close', c.get('Close', 0))),
                    'timestamp': c.get('timestamp', c.get('time', None)),
                }
                candle_lookup[c_idx] = candle_data
                ts = c.get('timestamp', c.get('time', None))
                if ts is not None:
                    ts_to_candle_idx[int(float(ts))] = c_idx

        ratio = self.parameters['min_mfe_reward_ratio']
        max_lookback = self.parameters['max_lookback_bars']
        min_bars = self.parameters['min_confirm_bars']
        wins = 0
        live_wins = 0; live_total = 0
        retro_wins = 0; retro_total = 0
        total_mfe = 0.0; total_mae = 0.0
        type_stats = {}; frac_stats = {}
        rejected_count = 0

        for _, row in bounces.iterrows():
            mfe = row.get('MFE_10', np.nan)
            mae = row.get('MAE_10', np.nan)
            if pd.isna(mfe) or pd.isna(mae):
                continue

            details = str(row.get("Details", ""))
            etype = row.get("Type", "")

            t_delay = self._parse_t_delay(details)
            if t_delay < min_bars:
                rejected_count += 1; continue
            if t_delay > max_lookback:
                rejected_count += 1; continue

            # Trend-aligned check: Low-anchored (L*) -> SUPPORT_BOUNCE only. High-anchored (H*) -> RESISTANCE_REJECTION only.
            if self.parameters.get('trend_aligned_only', False):
                fan_label = row.get("Fan", "")
                if "(L" in fan_label and etype != 'SUPPORT_BOUNCE':
                    rejected_count += 1; continue
                if "(H" in fan_label and etype != 'RESISTANCE_REJECTION':
                    rejected_count += 1; continue

            # Counter-trend check: Low-anchored (L*) -> RESISTANCE_REJECTION only. High-anchored (H*) -> SUPPORT_BOUNCE only.
            if self.parameters.get('counter_trend_only', False):
                fan_label = row.get("Fan", "")
                if "(L" in fan_label and etype != 'RESISTANCE_REJECTION':
                    rejected_count += 1; continue
                if "(H" in fan_label and etype != 'SUPPORT_BOUNCE':
                    rejected_count += 1; continue

            if candle_lookup and ts_to_candle_idx:
                # Use timestamp-based lookup to find confirmation candle
                raw_ts = int(float(row.get('Raw_Timestamp', row.get('Timestamp', 0))))
                conf_idx = ts_to_candle_idx.get(raw_ts)
                if conf_idx is None:
                    rejected_count += 1; continue

                conf = candle_lookup.get(conf_idx)
                test_idx = conf_idx - t_delay
                test = candle_lookup.get(test_idx)
                if conf is None or test is None:
                    rejected_count += 1; continue

                conf_close = conf['close']
                conf_open = conf['open']
                test_close = test['close']

                if etype == 'SUPPORT_BOUNCE':
                    if conf_close <= conf_open:
                        rejected_count += 1; continue
                    if conf_close <= test_close:
                        rejected_count += 1; continue
                elif etype == 'RESISTANCE_REJECTION':
                    if conf_close >= conf_open:
                        rejected_count += 1; continue
                    if conf_close >= test_close:
                        rejected_count += 1; continue

            is_retro = "[Retro]" in details
            safe_mae = max(mae, 0.1)
            is_win = mfe > safe_mae * ratio

            # Get test event time from the test candle (t_delay bars before confirmation)
            test_time = row.get("Time", "")
            if candle_lookup and ts_to_candle_idx:
                raw_ts = int(float(row.get('Raw_Timestamp', row.get('Timestamp', 0))))
                conf_idx = ts_to_candle_idx.get(raw_ts)
                if conf_idx is not None:
                    test_idx = conf_idx - t_delay
                    test_candle = candle_lookup.get(test_idx)
                    if test_candle is not None:
                        ts = test_candle.get('timestamp')
                        if ts is not None:
                            from datetime import datetime, timezone
                            test_time = datetime.fromtimestamp(int(float(ts)) / 1000.0 if float(ts) > 1e10 else float(ts),
                                                               tz=timezone.utc).strftime("%m/%d/%Y, %I:%M:%S %p")

            record = {
                "time": row.get("Time", ""),
                "test_time": test_time,
                "fan": row.get("Fan", ""),
                "fraction": row.get("Fraction", ""),
                "type": etype,
                "price": row.get("Price", 0.0),
                "is_retro": is_retro,
                "outcome": "WIN" if is_win else "LOSS",
                "mfe": mfe, "mae": mae,
                "anchor_bar_index": row.get("anchor_bar_index", 0),
                "scale_ratio": row.get("scale_ratio", 1.0),
                "anchor_price": row.get("anchor_price", 0.0),
                "details": f"{'[Retro] ' if is_retro else ''}{details}",
                "confirmation_details": details if details else None,
                "raw_timestamp": int(float(row.get("Raw_Timestamp", row.get("Timestamp", 0)))),
            }
            self.detailed_log.append(record)

            if is_win: wins += 1
            total_mfe += mfe; total_mae += mae

            if is_retro:
                retro_total += 1
                if is_win: retro_wins += 1
            else:
                live_total += 1
                if is_win: live_wins += 1

            if etype not in type_stats:
                type_stats[etype] = {"wins": 0, "total": 0, "mfe": 0.0, "mae": 0.0}
            type_stats[etype]["total"] += 1
            type_stats[etype]["mfe"] += mfe; type_stats[etype]["mae"] += mae
            if is_win: type_stats[etype]["wins"] += 1

            fraction = str(row.get("Fraction", ""))
            if fraction not in frac_stats:
                frac_stats[fraction] = {"wins": 0, "total": 0, "mfe": 0.0, "mae": 0.0}
            frac_stats[fraction]["total"] += 1
            frac_stats[fraction]["mfe"] += mfe; frac_stats[fraction]["mae"] += mae
            if is_win: frac_stats[fraction]["wins"] += 1

        n = len(self.detailed_log)
        if n == 0:
            return self._empty_result()

        groups = {}
        for etype_key, s in sorted(type_stats.items()):
            t = s["total"]
            groups[etype_key] = {"sample_size": t, "win_rate": s["wins"] / t if t > 0 else 0.0,
                                 "avg_mfe_10": s["mfe"] / t if t > 0 else 0.0,
                                 "avg_mae_10": s["mae"] / t if t > 0 else 0.0}
        for frac, s in sorted(frac_stats.items()):
            t = s["total"]
            groups[f"angle:{frac}"] = {"sample_size": t, "win_rate": s["wins"] / t if t > 0 else 0.0,
                                       "avg_mfe_10": s["mfe"] / t if t > 0 else 0.0,
                                       "avg_mae_10": s["mae"] / t if t > 0 else 0.0}

        return {
            "sample_size": n, "win_rate": wins / n if n > 0 else 0.0,
            "live_sample_size": live_total, "live_win_rate": live_wins / live_total if live_total > 0 else 0.0,
            "retro_sample_size": retro_total, "retro_win_rate": retro_wins / retro_total if retro_total > 0 else 0.0,
            "avg_mfe_10": total_mfe / n if n > 0 else 0.0,
            "avg_mae_10": total_mae / n if n > 0 else 0.0,
            "composite": (total_mfe / n) * math.sqrt(n) if n > 0 else 0.0,
            "groups": groups, "detailed_log": self.detailed_log,
            "rejected_by_vx": rejected_count,
        }

    def _parse_t_delay(self, details: str) -> int:
        import re
        m = re.search(r'T\+(\d+)', str(details))
        return int(m.group(1)) if m else 0

    def _empty_result(self) -> Dict[str, Any]:
        return {"sample_size": 0, "win_rate": 0.0, "live_sample_size": 0, "live_win_rate": 0.0,
                "retro_sample_size": 0, "retro_win_rate": 0.0,
                "avg_mfe_10": 0.0, "avg_mae_10": 0.0, "composite": 0.0,
                "groups": {}, "detailed_log": [], "rejected_by_vx": 0}


class BounceFollowThroughV4Hypothesis(_BounceFollowThroughParam):
    """V4: min 2-bar delay, keep 1.5 ratio, 3-bar lookback (Scenario A solo)."""
    def __init__(self):
        super().__init__(
            name="Bounce Follow-Through V4",
            description="V4: min 2-bar, 1.5 ratio, 3-bar lookback",
            min_bars=2, max_lookback=3, mfe_ratio=1.5)


class BounceFollowThroughV5Hypothesis(_BounceFollowThroughParam):
    """V5: V2 settings but 1.0 ratio (lenient — classify all events)."""
    def __init__(self):
        super().__init__(
            name="Bounce Follow-Through V5",
            description="V5: min 1-bar, 1.0 ratio, 3-bar lookback (all pass)",
            min_bars=1, max_lookback=3, mfe_ratio=1.0)


class BounceFollowThroughV6Hypothesis(_BounceFollowThroughParam):
    """V6: min 2-bar delay, 1.5 ratio, but tighter 2-bar lookback."""
    def __init__(self):
        super().__init__(
            name="Bounce Follow-Through V6",
            description="V6: min 2-bar, 1.5 ratio, 2-bar lookback (T+2 only)",
            min_bars=2, max_lookback=2, mfe_ratio=1.5)


class BounceFollowThroughV7Hypothesis(_BounceFollowThroughParam):
    """V7: V2 settings but 1.75 ratio (between V2 1.5 and V3 2.0)."""
    def __init__(self):
        super().__init__(
            name="Bounce Follow-Through V7",
            description="V7: min 1-bar, 1.75 ratio, 3-bar lookback",
            min_bars=1, max_lookback=3, mfe_ratio=1.75)


class BounceFollowThroughV8Hypothesis(_BounceFollowThroughParam):
    """V8: V2 settings but 2.0 ratio (Scenario D solo)."""
    def __init__(self):
        super().__init__(
            name="Bounce Follow-Through V8",
            description="V8: min 1-bar, 2.0 ratio, 3-bar lookback (Scenario D solo)",
            min_bars=1, max_lookback=3, mfe_ratio=2.0)


class BounceFollowThroughV9Hypothesis(_BounceFollowThroughParam):
    """V9: min 3-bar delay, 1.5 ratio (T+3 only, strictest delay)."""
    def __init__(self):
        super().__init__(
            name="Bounce Follow-Through V9",
            description="V9: min 3-bar, 1.5 ratio, 3-bar lookback (T+3 only)",
            min_bars=3, max_lookback=3, mfe_ratio=1.5)


class BounceFollowThroughV10Hypothesis(_BounceFollowThroughParam):
    """V10: V5+V4 hybrid — lenient 1.0 ratio + T+2 minimum delay (recommended)."""
    def __init__(self):
        super().__init__(
            name="Bounce Follow-Through V10",
            description="V10: min 2-bar, 1.0 ratio, 3-bar lookback (V5+V4 hybrid — recommended)",
            min_bars=2, max_lookback=3, mfe_ratio=1.0)


class BounceFollowThroughV11Hypothesis(_BounceFollowThroughParam):
    """V11: Trend-Aligned Only (Low-anchored = Support Bounces, High-anchored = Resistance Rejections).
    Uses V7 parameters (1-bar min delay, 3-bar lookback, 1.75 MFE ratio)."""
    def __init__(self):
        super().__init__(
            name="Bounce Follow-Through V11",
            description="V11: Trend-Aligned Only (L=Support, H=Resistance). V7 settings: min 1-bar, 1.75 ratio, 3-bar lookback.",
            min_bars=1, max_lookback=3, mfe_ratio=1.75, trend_aligned_only=True)


class BounceFollowThroughV12Hypothesis(_BounceFollowThroughParam):
    """V12: Counter-Trend Only (Low-anchored = Resistance Rejections, High-anchored = Support Bounces).
    Uses V7 parameters (1-bar min delay, 3-bar lookback, 1.75 MFE ratio)."""
    def __init__(self):
        super().__init__(
            name="Bounce Follow-Through V12",
            description="V12: Counter-Trend Only (L=Resistance, H=Support). V7 settings: min 1-bar, 1.75 ratio, 3-bar lookback.",
            min_bars=1, max_lookback=3, mfe_ratio=1.75, counter_trend_only=True)


class WalkForwardValidator:
    """Validates hypotheses via 70/30 chronological train/test split."""

    def __init__(self, train_pct: float = 0.7):
        self.train_pct = train_pct

    def validate(self, hypothesis: Hypothesis, df: pd.DataFrame,
                 candles_df: pd.DataFrame = None) -> Dict[str, Any]:
        """
        Validate via chronological 70/30 train/test split.

        Strategy: Run hypothesis.evaluate() on the FULL df to get detailed_log.
        Then split log entries chronologically (not the raw df) to preserve
        cross-event hypotheses like PostBreachPullback that pair events across
        bars. If detailed_log is empty/absent, fall back to split-before-evaluate.
        """
        # Determine bar_index column
        bar_col = 'bar_index' if 'bar_index' in df.columns else 'Bar_Index'

        # First, try selection-before-split: evaluate on full df, split the log
        full_result = self._safe_evaluate(hypothesis, df, candles_df)
        log = full_result.get("detailed_log", [])

        if log and len(log) >= 10:
            # Extract bar_index/timestamp from each log entry for chronological ordering
            indexed_log = []
            for entry in log:
                # Try multiple sources for chronological ordering
                bar_idx = self._extract_bar_index(entry, df, bar_col)
                indexed_log.append((bar_idx, entry))

            # Sort by bar_index
            indexed_log.sort(key=lambda x: x[0])
            n = len(indexed_log)
            split_idx = int(n * self.train_pct)

            if split_idx >= 5 and n - split_idx >= 5:
                train_log = [e for _, e in indexed_log[:split_idx]]
                test_log = [e for _, e in indexed_log[split_idx:]]

                train_result = self._compute_log_stats(hypothesis, train_log)
                test_result = self._compute_log_stats(hypothesis, test_log)

                return self._build_result(train_result, test_result)

        # Fallback: split raw df first (works for single-event hypotheses)
        if bar_col not in df.columns:
            return self._empty_wf()

        df_sorted = df.sort_values(bar_col).reset_index(drop=True)
        n = len(df_sorted)
        split_idx = int(n * self.train_pct)

        if split_idx < 10 or n - split_idx < 10:
            return self._empty_wf()

        train_df = df_sorted.iloc[:split_idx].copy()
        test_df = df_sorted.iloc[split_idx:].copy()

        train_result = self._safe_evaluate(hypothesis, train_df, candles_df)
        test_result = self._safe_evaluate(hypothesis, test_df, candles_df)

        return self._build_result(train_result, test_result)

    def _extract_bar_index(self, entry: dict, df: pd.DataFrame, bar_col: str):
        """Extract a chronological order key from a log entry."""
        # Direct bar_index (from event row or log entry)
        if 'bar_index' in entry and entry['bar_index'] is not None:
            return int(entry['bar_index'])
        if 'bar_idx' in entry and entry['bar_idx'] is not None:
            return int(entry['bar_idx'])
        # anchor_bar_index (stored by H1, H6, H7) — better than time strings
        if 'anchor_bar_index' in entry and entry['anchor_bar_index'] is not None:
            return int(entry['anchor_bar_index'])
        # Try parsing time as pandas Timestamp for proper chronological ordering
        if 'time' in entry and entry['time']:
            try:
                return pd.Timestamp(entry['time']).value
            except Exception:
                return str(entry['time'])
        # Last resort: just use index
        return 0

    def _compute_log_stats(self, hypothesis, log: list) -> dict:
        """Compute basic stats from a subset of detailed_log entries."""
        if not log:
            return {"sample_size": 0, "win_rate": 0.0, "avg_mfe_10": 0.0,
                    "avg_mae_10": 0.0, "composite": 0.0}

        wins = sum(1 for e in log if e.get('outcome') == 'WIN' or e.get('hypothesis_win') == True)
        n = len(log)

        # Extract MFE/MAE - try multiple field names
        mfe_sum = 0.0
        mae_sum = 0.0
        mfe_count = 0
        mae_count = 0

        for e in log:
            mfe = e.get('mfe') or e.get('mfe_10')
            if mfe is None:
                mfe = e.get('MFE_10')
            if mfe is not None and not (isinstance(mfe, float) and math.isnan(mfe)):
                mfe_sum += float(mfe)
                mfe_count += 1

            mae = e.get('mae') or e.get('mae_10')
            if mae is None:
                mae = e.get('MAE_10')
            if mae is not None and not (isinstance(mae, float) and math.isnan(mae)):
                mae_sum += float(mae)
                mae_count += 1

        avg_mfe = mfe_sum / mfe_count if mfe_count > 0 else 0.0
        avg_mae = mae_sum / mae_count if mae_count > 0 else 0.0

        return {
            "sample_size": n,
            "win_rate": wins / n if n > 0 else 0.0,
            "avg_mfe_10": avg_mfe,
            "avg_mae_10": avg_mae,
            "composite": avg_mfe * math.sqrt(n) if n > 0 else 0.0,
        }

    def _build_result(self, train_result: dict, test_result: dict) -> Dict[str, Any]:
        """Build walk-forward result dict from train/test stats."""
        train_n = train_result.get("sample_size", 0)
        test_n = test_result.get("sample_size", 0)
        train_wr = train_result.get("win_rate", 0.0)
        test_wr = test_result.get("win_rate", 0.0)
        train_comp = train_result.get("composite", 0.0)
        test_comp = test_result.get("composite", 0.0)

        if "composite" not in train_result and train_n > 0:
            train_comp = train_result.get("avg_mfe_10", 0.0) * math.sqrt(train_n)
        if "composite" not in test_result and test_n > 0:
            test_comp = test_result.get("avg_mfe_10", 0.0) * math.sqrt(test_n)

        persistent = (
            test_n >= 5
            and test_wr >= train_wr * 0.8
            and test_comp >= train_comp * 0.8
        )

        return {
            "train_sample_size": train_n,
            "train_win_rate": train_wr,
            "train_composite": train_comp,
            "test_sample_size": test_n,
            "test_win_rate": test_wr,
            "test_composite": test_comp,
            "persistent": persistent,
        }

    def _empty_wf(self) -> Dict[str, Any]:
        return {"train_sample_size": 0, "train_win_rate": 0.0, "train_composite": 0.0,
                "test_sample_size": 0, "test_win_rate": 0.0, "test_composite": 0.0,
                "persistent": False}

    def _safe_evaluate(self, hypothesis, df, candles_df):
        """Call evaluate with the right signature for each hypothesis."""
        try:
            return hypothesis.evaluate(df, candles_df=candles_df)
        except TypeError:
            return hypothesis.evaluate(df)


def _sanitize_json(obj):
    """Convert numpy types to native Python for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_json(v) for v in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif pd.isna(obj) if not isinstance(obj, (dict, list, str)) else False:
        return None
    return obj


def rescore_from_realized_trades(result: dict) -> dict:
    """Replace MFE/MAE headline metrics with realized futures-trade results.

    18 of 19 hypotheses originally reported win rates from MFE/MAE labels --
    "did price move favourably at some point within the horizon" -- which never
    has to survive a stop. Bounce Follow-Through V5 reported 0.721 that way
    while its realized trades won 0.176 and lost ~30,000.

    ExitOptimizer already simulates the real trades and writes entry/exit/net_pnl
    into detailed_log; only the headline numbers still came from MFE. This folds
    those realized results into in_sample and walk_forward, and demotes the MFE
    figures to clearly-named diagnostics (``label_win_rate``, ``avg_mfe_10``).

    Only entries carrying ``trade_matched`` are counted. Entries the optimizer
    could not match to a candle keep an MFE-derived outcome, and counting those
    would silently re-mix the two scoring bases.

    Idempotent: safe to call on a hypothesis that already scores on trades.
    """
    in_sample = result.get("in_sample") or {}
    log = result.get("detailed_log") or []

    trades = [e for e in log if e.get("trade_matched") and e.get("outcome") in ("WIN", "LOSS", "BREAKEVEN")]
    if not trades:
        result.setdefault("scoring_basis", "mfe_label")
        return result

    def _wr(entries):
        if not entries:
            return 0.0
        return round(sum(1 for e in entries if e.get("outcome") == "WIN") / len(entries), 4)

    def _net(entries):
        return round(sum(float(e.get("net_pnl") or 0.0) for e in entries), 6)

    # Preserve the MFE numbers once, before the first overwrite.
    if "label_win_rate" not in in_sample:
        in_sample["label_win_rate"] = in_sample.get("win_rate", 0.0)
        in_sample["label_sample_size"] = in_sample.get("sample_size", 0)

    live = [e for e in trades if not e.get("is_retro")]
    retro = [e for e in trades if e.get("is_retro")]
    total_net = _net(trades)

    in_sample["sample_size"] = len(trades)
    in_sample["win_rate"] = _wr(trades)
    in_sample["live_sample_size"] = len(live)
    in_sample["live_win_rate"] = _wr(live)
    in_sample["retro_sample_size"] = len(retro)
    in_sample["retro_win_rate"] = _wr(retro)
    in_sample["net_pnl_total"] = total_net
    in_sample["avg_net_pnl"] = round(total_net / len(trades), 6)

    # Walk-forward on the same chronological 70/30 split, realized outcomes.
    ordered = sorted(trades, key=lambda e: str(e.get("time", "")))
    split = int(len(ordered) * 0.7)
    train, test = ordered[:split], ordered[split:]
    train_wr, test_wr = _wr(train), _wr(test)
    result["walk_forward"] = {
        "train_sample_size": len(train),
        "train_win_rate": train_wr,
        "train_net_pnl": _net(train),
        "test_sample_size": len(test),
        "test_win_rate": test_wr,
        "test_net_pnl": _net(test),
        # Persistent only if the edge survives out of sample AND is above a
        # coin flip. An MFE-based "persistent" flag meant neither.
        "persistent": bool(test and test_wr >= 0.5 and test_wr >= train_wr * 0.9),
        "basis": "realized_trades",
    }

    result["in_sample"] = in_sample
    result["trade_scored"] = True
    result["scoring_basis"] = "realized_trades"
    return result


class HypothesisRunner:
    """Runs all 16 hypotheses + walk-forward validation. Writes unified output."""

    # Map hypothesis classes to output filenames
    HYPOTHESIS_CONFIG = [
        ("strong_sr_rule", StrongSRHypothesis, False),
        ("quarter_reversal_anomaly", QuarterReversalAnomalyHypothesis, False),
        ("confluence_bounce", ConfluenceBounceHypothesis, False),
        ("target_progression", TargetProgressionHypothesis, True),
        ("post_breach_pullback", PostBreachPullbackHypothesis, False),
        ("reversal_by_angle_line", ReversalByAngleLineHypothesis, False),
        ("bounce_follow_through", BounceFollowThroughHypothesis, False),
        ("bounce_follow_through_v2", BounceFollowThroughV2Hypothesis, False),
        ("bounce_follow_through_v3", BounceFollowThroughV3Hypothesis, False),
        ("bounce_follow_through_v4", BounceFollowThroughV4Hypothesis, True),
        ("bounce_follow_through_v5", BounceFollowThroughV5Hypothesis, True),
        ("bounce_follow_through_v6", BounceFollowThroughV6Hypothesis, True),
        ("bounce_follow_through_v7", BounceFollowThroughV7Hypothesis, True),
        ("bounce_follow_through_v8", BounceFollowThroughV8Hypothesis, True),
        ("bounce_follow_through_v9", BounceFollowThroughV9Hypothesis, True),
        ("bounce_follow_through_v10", BounceFollowThroughV10Hypothesis, True),
        ("bounce_follow_through_v11", BounceFollowThroughV11Hypothesis, True),
        ("bounce_follow_through_v12", BounceFollowThroughV12Hypothesis, True),
        ("rsi_trendline_break_strategy", RSITrendlineBreakHypothesis, True),
    ]

    def __init__(self, run_dir: str):
        self.run_dir = run_dir
        self.output_dir = os.path.join(run_dir, "analysis", "hypotheses")

    @staticmethod
    def _parse_time_to_ts(time_str: str) -> int:
        """Parse detailed_log time string (e.g. '4/1/2025, 12:12:00 AM') to epoch seconds."""
        if not time_str:
            return 0
        try:
            from datetime import datetime, timezone
            clean = str(time_str).replace(',', '')
            dt = datetime.strptime(clean, '%m/%d/%Y %I:%M:%S %p')
            dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except (ValueError, OSError):
            return 0

    def run_all(self) -> Dict[str, Any]:
        """Run all hypotheses + walk-forward. Write output files. Return results dict."""
        csv_path = os.path.join(self.run_dir, "events.csv")
        if not os.path.exists(csv_path):
            print(f"[HypothesisFramework] events.csv not found at {csv_path}")
            return {}

        # Load events
        df = pd.read_csv(csv_path)
        # Convert empty strings to NaN for numeric columns
        numeric_cols = ['MFE_5', 'MAE_5', 'MFE_10', 'MAE_10', 'MFE_20', 'MAE_20',
                        'MFE_50', 'MAE_50', 'Price', 'Open', 'High', 'Low', 'Close',
                        'Exc_Up_10', 'Exc_Down_10', 'Raw_Timestamp', 'scale_ratio',
                        'anchor_price', 'origin_price', 'Bar_Index', 'anchor_bar_index',
                        'origin_bar_index', 'Bars_In_Zone']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        # Also handle bar_index lowercase variant
        if 'bar_index' in df.columns:
            df['bar_index'] = pd.to_numeric(df['bar_index'], errors='coerce')

        # Load candles if available
        candles_df = None
        candles_path = os.path.join(self.run_dir, "candles.csv")
        if os.path.exists(candles_path):
            candles_df = pd.read_csv(candles_path)

        os.makedirs(self.output_dir, exist_ok=True)

        results = {}
        wf_validator = WalkForwardValidator(train_pct=0.7)

        for filename, hyp_class, needs_candles in self.HYPOTHESIS_CONFIG:
            hypothesis = hyp_class()
            print(f"[HypothesisFramework] Running {hypothesis.name}...")

            # Evaluate in-sample
            try:
                if needs_candles and candles_df is not None:
                    in_sample = hypothesis.evaluate(df, candles_df=candles_df)
                else:
                    in_sample = self._safe_evaluate(hypothesis, df, candles_df if needs_candles else None)
            except Exception as e:
                print(f"  ERROR: {e}")
                import traceback; traceback.print_exc()
                in_sample = {"sample_size": 0, "win_rate": 0.0, "live_sample_size": 0,
                             "live_win_rate": 0.0, "retro_sample_size": 0, "retro_win_rate": 0.0,
                             "avg_mfe_10": 0.0, "avg_mae_10": 0.0, "composite": 0.0,
                             "detailed_log": [], "error": str(e)}

            # Walk-forward validation
            try:
                wf = wf_validator.validate(hypothesis, df, candles_df if needs_candles else None)
            except Exception as e:
                print(f"  Walk-forward ERROR: {e}")
                wf = {"train_sample_size": 0, "train_win_rate": 0.0, "train_composite": 0.0,
                      "test_sample_size": 0, "test_win_rate": 0.0, "test_composite": 0.0,
                      "persistent": False, "error": str(e)}

            # Compute composite if not present
            n = in_sample.get("sample_size", 0)
            if "composite" not in in_sample and n > 0:
                in_sample["composite"] = in_sample.get("avg_mfe_10", 0.0) * math.sqrt(n)

            result = {
                "hypothesis_name": hypothesis.name,
                "description": hypothesis.description,
                "in_sample": {
                    "sample_size": in_sample.get("sample_size", 0),
                    "win_rate": in_sample.get("win_rate", 0.0),
                    "live_sample_size": in_sample.get("live_sample_size", 0),
                    "live_win_rate": in_sample.get("live_win_rate", 0.0),
                    "retro_sample_size": in_sample.get("retro_sample_size", 0),
                    "retro_win_rate": in_sample.get("retro_win_rate", 0.0),
                    "avg_mfe_10": in_sample.get("avg_mfe_10", 0.0),
                    "avg_mae_10": in_sample.get("avg_mae_10", 0.0),
                    "composite": in_sample.get("composite", 0.0),
                },
                "walk_forward": wf,
                "groups": in_sample.get("groups", {}),
                "detailed_log": in_sample.get("detailed_log", []),
                "rsi_series": in_sample.get("rsi_series", []),
                "line_timeline": in_sample.get("line_timeline", []),
                "skipped": in_sample.get("skipped", {}),
            }
            # net_pnl_total is what trade-scored hypotheses are judged on, so it
            # must survive into the persisted report rather than being recomputed
            # from detailed_log by every consumer.
            if in_sample.get("trade_scored"):
                result["trade_scored"] = True
                result["in_sample"]["net_pnl_total"] = in_sample.get("net_pnl_total", 0.0)
                result["in_sample"]["avg_net_pnl"] = in_sample.get("avg_net_pnl", 0.0)
                # The runner skips its own ExitOptimizer for trade-scored
                # hypotheses (below), so the hypothesis's own per-R grid is the
                # only one there is. Spec section 13 requires preserving it.
                if "exit_optimization" in in_sample:
                    result["exit_optimization"] = in_sample["exit_optimization"]

            # Auto-compute per-angle breakdown from detailed_log if not already present
            self._add_angle_breakdown(result)

            # Run exit optimization for ALL hypotheses that have events and candles
            try:
                if candles_df is not None and result["detailed_log"] and not result.get("trade_scored"):
                    qualified = None
                    is_bft = isinstance(hypothesis, _BounceFollowThroughParam)

                    if is_bft:
                        # BFT: use filter_bounce_events for test-candle-based SL
                        min_bars = hypothesis.parameters.get('min_confirm_bars', 1)
                        max_lb = hypothesis.parameters.get('max_lookback_bars', 3)
                        qualified = filter_bounce_events(df, min_bars, max_lb, candles_df)
                    else:
                        # Non-BFT: use all tradeable events from df, match later by time
                        tradeable = df[df['Type'].apply(
                            lambda t: t in {'SUPPORT_BOUNCE', 'RESISTANCE_REJECTION',
                                           'CROSS_UP', 'CROSS_DOWN', 'GAP_CROSS_UP', 'GAP_CROSS_DOWN',
                                           'target_hit', 'target_failed', 'breach_confirmed',
                                           'BREACH_CONFIRMED_NO_ALPHA'}
                        )]
                        if len(tradeable) > 0:
                            qualified = tradeable

                    if qualified is not None and len(qualified) >= 10:
                        optimizer = ExitOptimizer(
                            events_df=qualified,
                            candles_df=candles_df,
                            train_pct=0.7,
                        )
                        result["exit_optimization"] = optimizer.optimize()
                        # Merge per-event trade results into detailed_log
                        exit_opt = result["exit_optimization"]
                        if "best" in exit_opt:
                            best_r = exit_opt["best"].get("r_value", 1.5)
                            per_event = optimizer.get_per_event_trades(best_r)
                            for evt in result["detailed_log"]:
                                rt = evt.get("raw_timestamp", 0)
                                if rt <= 0:
                                    ts = self._parse_time_to_ts(evt.get("time", ""))
                                    rt = int(ts) if ts else 0
                                trade = per_event.get(int(rt)) if rt > 0 else None
                                if not trade and rt > 0:
                                    trade = per_event.get(int(rt * 1000))
                                if trade:
                                    evt["entry_price"] = trade["entry_price"]
                                    evt["entry_time"] = trade.get("entry_time", "")
                                    evt["exit_price"] = trade["exit_price"]
                                    evt["exit_time"] = trade.get("exit_time", "")
                                    evt["exit_reason"] = trade["exit_reason"]
                                    evt["exit_label"] = trade.get("exit_label", "")
                                    evt["net_pnl"] = trade["net_pnl"]
                                    evt["pnl_pct"] = trade["pnl_pct"]
                                    evt["bars_held"] = trade["bars_held"]
                                    evt["entry_side"] = trade.get("entry_side", "")
                                    evt["outcome"] = "WIN" if trade["net_pnl"] > 0 else "LOSS"
                                    evt["trade_matched"] = True
                        rescore_from_realized_trades(result)
                        print(f"  [ExitOptimizer] Optimization complete for {hypothesis.name} "
                              f"(realized WR={result['in_sample'].get('win_rate')}, "
                              f"net={result['in_sample'].get('net_pnl_total')})")
                    else:
                        n = len(qualified) if qualified is not None else 0
                        result["exit_optimization"] = {"error": f"Insufficient qualified events ({n})"}
            except Exception as e:
                print(f"  [ExitOptimizer] ERROR for {hypothesis.name}: {e}")
                import traceback; traceback.print_exc()
                result["exit_optimization"] = {"error": str(e)}

            # Every hypothesis is scored on realized futures trades, including
            # those that scored themselves -- this makes walk_forward realized
            # too, which the generic label-based path did not. Idempotent.
            rescore_from_realized_trades(result)

            # Exclude stats for QuarterReversal
            if "excluded_stats" in in_sample:
                result["excluded_stats"] = in_sample["excluded_stats"]

            results[filename] = result

            # Write per-hypothesis JSON
            json_path = os.path.join(self.output_dir, f"{filename}.json")
            with open(json_path, 'w') as f:
                json.dump(_sanitize_json(result), f, indent=2, default=str)

            print(f"  n={result['in_sample']['sample_size']} WR={result['in_sample']['win_rate']:.0%} "
                  f"persistent={wf.get('persistent', False)}")

        # Write run summary
        self._write_summary(results, df)

        return results

    def _safe_evaluate(self, hypothesis, df, candles_df):
        """Call evaluate with the right signature for each hypothesis."""
        import inspect
        sig = inspect.signature(hypothesis.evaluate)
        params = sig.parameters
        # Check if it accepts candles_df keyword
        accepts_candles = 'candles_df' in params
        # Check if it accepts variable keyword arguments
        has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())

        if candles_df is not None and (accepts_candles or has_kwargs):
            try:
                return hypothesis.evaluate(df, candles_df=candles_df)
            except TypeError:
                pass
        # Fallback: just pass df
        return hypothesis.evaluate(df)

    def _add_angle_breakdown(self, result: dict):
        """
        Auto-compute per-angle breakdown from detailed_log if it contains
        'fraction' fields and no angle breakdown already exists.
        Adds angle groups like 'angle:0.25' to the result's groups dict.
        """
        log = result.get("detailed_log", [])
        if not log:
            return

        # Check if fractions exist and angle breakdown not already present
        has_fraction = any(e.get("fraction") for e in log)
        existing_groups = result.get("groups", {})
        # Check if groups already contain per-angle statistics (via "angle:" prefix
        # or raw fraction names like "0.25", "horizontal")
        standard_fractions = {"0.25", "0.5", "0.75", "0.875", "horizontal"}
        has_angles = any(k.startswith("angle:") for k in existing_groups)
        has_frac_keys = bool(standard_fractions & set(existing_groups.keys()))
        if not has_fraction or has_angles or has_frac_keys:
            return

        frac_stats = {}
        for entry in log:
            outcome = entry.get("outcome")
            if not outcome:
                continue
            frac = str(entry.get("fraction", ""))
            if not frac:
                continue
            is_win = outcome == "WIN"
            mfe = entry.get("mfe") or entry.get("mfe_10") or entry.get("MFE_10") or 0.0
            mae = entry.get("mae") or entry.get("mae_10") or entry.get("MAE_10") or 0.0
            try:
                mfe = float(mfe) if mfe else 0.0
                mae = float(mae) if mae else 0.0
            except (ValueError, TypeError):
                mfe, mae = 0.0, 0.0
            # Guard against NaN values (NaN is truthy so survives the `or` chain above)
            if math.isnan(mfe):
                mfe = 0.0
            if math.isnan(mae):
                mae = 0.0

            if frac not in frac_stats:
                frac_stats[frac] = {"wins": 0, "total": 0, "mfe": 0.0, "mae": 0.0}
            frac_stats[frac]["total"] += 1
            frac_stats[frac]["mfe"] += mfe
            frac_stats[frac]["mae"] += mae
            if is_win:
                frac_stats[frac]["wins"] += 1

        for frac, s in sorted(frac_stats.items()):
            t = s["total"]
            result["groups"][f"angle:{frac}"] = {
                "sample_size": t,
                "win_rate": s["wins"] / t if t > 0 else 0.0,
                "avg_mfe_10": s["mfe"] / t if t > 0 else 0.0,
                "avg_mae_10": s["mae"] / t if t > 0 else 0.0,
            }

    def _write_summary(self, results: Dict, df: pd.DataFrame):
        """Write run_summary.json and run_summary.txt"""
        # JSON summary
        summary = {
            "total_events": len(df),
            "hypotheses": []
        }
        for filename, result in results.items():
            h = {
                "name": result["hypothesis_name"],
                "filename": filename,
                "sample_size": result["in_sample"]["sample_size"],
                "win_rate": result["in_sample"]["win_rate"],
                "walk_forward_persistent": result["walk_forward"].get("persistent", False),
                "train_win_rate": result["walk_forward"].get("train_win_rate", 0.0),
                "test_win_rate": result["walk_forward"].get("test_win_rate", 0.0),
            }
            if result.get("groups"):
                h["groups"] = {
                    k: {"sample_size": v["sample_size"], "win_rate": v["win_rate"]}
                    for k, v in result["groups"].items()
                }
            summary["hypotheses"].append(h)

        summary["persistent_count"] = sum(1 for h in summary["hypotheses"] if h["walk_forward_persistent"])
        summary["total_hypotheses"] = len(summary["hypotheses"])

        json_path = os.path.join(self.output_dir, "run_summary.json")
        with open(json_path, 'w') as f:
            json.dump(_sanitize_json(summary), f, indent=2, default=str)

        # Text summary
        lines = []

        # Parse run metadata from run_dir path and dataframe
        run_dir_parts = os.path.normpath(self.run_dir).split(os.sep)
        # Path is like: .../runs/BTCUSDT/60/2026-06-23_9198fc
        tf = ""
        symbol = ""
        from_date = ""
        to_date = ""
        for i, part in enumerate(run_dir_parts):
            if part == "runs" and i + 2 < len(run_dir_parts):
                symbol = run_dir_parts[i + 1]
                tf = run_dir_parts[i + 2]

        # Get date range from Time column
        if 'Time' in df.columns:
            times = pd.to_datetime(df['Time'], errors='coerce')
            if not times.empty and times.notna().any():
                from_date = times.min().strftime('%Y-%m-%d')
                to_date = times.max().strftime('%Y-%m-%d')

        # Count unique bars for candle count approximation
        bar_col = 'bar_index' if 'bar_index' in df.columns else 'Bar_Index'
        n_candles = df[bar_col].nunique() if bar_col in df.columns else len(df)

        tf_display = f"{tf}m" if tf.isdigit() else tf

        lines.append("=" * 70)
        lines.append(f"=== RUN SUMMARY: {symbol} {tf_display}, {from_date} to {to_date} ===")
        lines.append(f"Events: {len(df)} | Candles: {n_candles}")
        lines.append("")
        lines.append("HYPOTHESIS RESULTS (in-sample | walk-forward)")
        lines.append("-" * 70)
        lines.append(f"{'Hypothesis':<30s} {'n':>5s} {'WR':>5s} {'WF:train':>8s} {'WF:test':>8s} {'Persistent':>10s}")
        lines.append("-" * 70)

        for h in summary["hypotheses"]:
            lines.append(
                f"{h['name']:<30s} {h['sample_size']:>5d} {h['win_rate']:>4.0%} "
                f"{h['train_win_rate']:>7.0%} {h['test_win_rate']:>7.0%} "
                f"{'YES' if h['walk_forward_persistent'] else 'NO':>10s}"
            )
            # Print subgroups if present
            if h.get("groups"):
                # Split groups: event-type groups vs angle-line groups
                type_groups = {}
                angle_groups = {}
                for gname, gstats in h["groups"].items():
                    if gname.startswith("angle:"):
                        angle_groups[gname.replace("angle:", "")] = gstats
                    else:
                        type_groups[gname] = gstats

                for gname, gstats in sorted(type_groups.items()):
                    lines.append(f"  {gname:>28s} {gstats['sample_size']:>5d} {gstats['win_rate']:>4.0%}")
                if angle_groups:
                    lines.append("    by angle line:")
                    for gname, gstats in sorted(angle_groups.items()):
                        lines.append(f"    {gname:>26s} {gstats['sample_size']:>5d} {gstats['win_rate']:>4.0%}")

        lines.append("-" * 70)
        lines.append(f"PERSISTENT: {summary['persistent_count']}/{summary['total_hypotheses']}")
        lines.append("=" * 70)

        txt_path = os.path.join(self.output_dir, "run_summary.txt")
        with open(txt_path, 'w') as f:
            f.write("\n".join(lines) + "\n")

        print(f"\n[HypothesisFramework] Summary written to {self.output_dir}")
        print("\n".join(lines))
