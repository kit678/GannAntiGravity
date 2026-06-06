"""
Pattern Miner — Brute-force tests patterns against enriched event data.

Usage:
    from analysis.pattern_miner import run_tier1, run_tier2
    tier1_results = run_tier1(events_df)
    tier2_results = run_tier2(events_df, tier1_results.head(20), line_prices)
"""
import numpy as np
import pandas as pd


def compute_pattern_stats(events_df: pd.DataFrame, mask: pd.Series) -> dict:
    """
    Compute statistics for events matching a boolean mask.

    Returns dict with: sample_count, mean_mfe_10, mean_mae_10, win_rate, composite
    """
    subset = events_df[mask].dropna(subset=["fwd_mfe_10", "fwd_mae_10"])
    n = len(subset)
    if n < 1:
        return {"sample_count": 0, "mean_mfe_10": 0, "mean_mae_10": 0, "win_rate": 0, "composite": 0}

    mean_mfe = subset["fwd_mfe_10"].mean()
    mean_mae = subset["fwd_mae_10"].mean()
    win_rate = subset["fwd_win_10"].astype(bool).mean() if "fwd_win_10" in subset.columns else 0

    composite = mean_mfe * np.sqrt(n) if mean_mfe > 0 else 0

    return {
        "sample_count": n,
        "mean_mfe_10": round(mean_mfe, 4),
        "mean_mae_10": round(mean_mae, 4),
        "win_rate": round(win_rate, 4),
        "composite": round(composite, 4),
    }


TIER1_THRESHOLDS = {
    "min_sample": 20,
    "min_win_rate": 0.50,
}


def run_tier1(events_df: pd.DataFrame) -> pd.DataFrame:
    """
    Test single-event patterns against Tier 1 thresholds.

    Tests every combination of: event_type x line_fraction x candle_pattern.
    Returns DataFrame sorted by composite score.
    """
    results = []

    event_types = sorted(events_df["event_type"].unique())
    line_fractions = sorted(events_df["line_fraction"].unique())
    candle_patterns = sorted(events_df["candle_pattern"].dropna().unique())
    candle_patterns = [p for p in candle_patterns if p]

    non_retro = events_df[~events_df["is_retro"]]

    for et in event_types:
        for frac in line_fractions:
            # Without candle pattern filter
            mask = (non_retro["event_type"] == et) & (non_retro["line_fraction"] == str(frac))
            stats = compute_pattern_stats(non_retro, mask)
            pattern_name = f"{et} on {frac} line"
            if stats["sample_count"] >= TIER1_THRESHOLDS["min_sample"] and stats["win_rate"] >= TIER1_THRESHOLDS["min_win_rate"]:
                results.append({
                    "pattern": pattern_name,
                    "event_type": et,
                    "line_fraction": str(frac),
                    "candle_pattern": "any",
                    "sequence_type": "single",
                    **stats,
                })

            # With candle pattern filter
            for cp in candle_patterns:
                mask_cp = mask & (non_retro["candle_pattern"] == cp)
                stats_cp = compute_pattern_stats(non_retro, mask_cp)
                pattern_name_cp = f"{et} on {frac} line [{cp}]"
                if stats_cp["sample_count"] >= TIER1_THRESHOLDS["min_sample"] and stats_cp["win_rate"] >= TIER1_THRESHOLDS["min_win_rate"]:
                    results.append({
                        "pattern": pattern_name_cp,
                        "event_type": et,
                        "line_fraction": str(frac),
                        "candle_pattern": cp,
                        "sequence_type": "single",
                        **stats_cp,
                    })

    if not results:
        return pd.DataFrame()

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values("composite", ascending=False).reset_index(drop=True)
    return results_df


def compute_line_reach(events_df: pd.DataFrame, mask: pd.Series, line_prices: dict) -> dict:
    """
    For events matching mask, compute how often price reaches the next angle line.

    Uses line_prices dict from trace_miner to find next line in event's direction.
    """
    from analysis.trace_miner import get_event_direction

    subset = events_df[mask].copy()
    n = len(subset)
    if n == 0:
        return {"line_reach_rate_10": 0, "line_reach_rate_20": 0}

    reaches_10 = 0
    reaches_20 = 0

    for idx, row in subset.iterrows():
        bar_idx = row["bar_index"]
        direction = get_event_direction(row)
        if direction == "NEUTRAL":
            continue

        fan_id = row["fan_id"]
        current_frac = row["line_fraction"]

        # Look up line prices at this bar for this fan
        key = (bar_idx, fan_id)
        fan_lines = line_prices.get(key, [])

        next_line_price = None
        for frac_str, price, dist in fan_lines:
            try:
                frac_val = float(frac_str) if frac_str != "horizontal" else 0.0
            except (ValueError, TypeError):
                continue
            try:
                current_frac_val = float(current_frac) if current_frac != "horizontal" else 0.0
            except (ValueError, TypeError):
                continue

            if direction == "UP" and frac_val > current_frac_val:
                if next_line_price is None or frac_val < next_line_price[0]:
                    next_line_price = (frac_val, price)
            elif direction == "DOWN" and frac_val < current_frac_val:
                if next_line_price is None or frac_val > next_line_price[0]:
                    next_line_price = (frac_val, price)

        if next_line_price is None:
            continue

        target_price = next_line_price[1]
        entry_close = row["close"]
        distance_to_line = abs(target_price - entry_close) / entry_close * 100

        mfe_10 = row.get("fwd_mfe_10", np.nan)
        mfe_20 = row.get("fwd_mfe_20", np.nan)

        if not np.isnan(mfe_10) and mfe_10 >= distance_to_line * 0.95:
            reaches_10 += 1
        if not np.isnan(mfe_20) and mfe_20 >= distance_to_line * 0.95:
            reaches_20 += 1

    return {
        "line_reach_rate_10": round(reaches_10 / n, 4) if n > 0 else 0,
        "line_reach_rate_20": round(reaches_20 / n, 4) if n > 0 else 0,
    }


def run_tier2(events_df: pd.DataFrame, tier1_candidates: pd.DataFrame, line_prices: dict) -> pd.DataFrame:
    """
    Run Tier 2 line-reach validation on Tier 1 survivors.

    Returns candidates with line_reach_rate columns appended, limit top 20.
    """
    if tier1_candidates.empty:
        return pd.DataFrame()

    results = []
    non_retro = events_df[~events_df["is_retro"]]

    for _, candidate in tier1_candidates.iterrows():
        et = candidate["event_type"]
        frac = candidate["line_fraction"]
        cp = candidate.get("candle_pattern", "any")

        mask = (non_retro["event_type"] == et) & (non_retro["line_fraction"] == str(frac))
        if cp and cp != "any":
            mask = mask & (non_retro["candle_pattern"] == cp)

        reach = compute_line_reach(non_retro, mask, line_prices)

        row = candidate.to_dict()
        row.update(reach)
        results.append(row)

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values("composite", ascending=False).head(20)
    return results_df
