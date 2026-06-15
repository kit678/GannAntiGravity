"""
Pattern Miner — Brute-force tests patterns against enriched event data.

Usage:
    from analysis.pattern_miner import run_tier1, run_tier2
    tier1_results = run_tier1(events_df)
    tier2_results = run_tier2(events_df, tier1_results.head(20), fan_line_catalog)
"""
import numpy as np
import pandas as pd


def compute_pattern_stats(events_df: pd.DataFrame, mask: pd.Series) -> dict:
    """
    Compute statistics for events matching a boolean mask.

    Returns dict with: sample_count, mean_mfe_10, mean_mae_10, win_rate, composite,
                       p25_mfe_10, p50_mfe_10, p75_mfe_10
    """
    subset = events_df[mask].dropna(subset=["fwd_mfe_10", "fwd_mae_10"])
    n = len(subset)
    if n < 1:
        return {
            "sample_count": 0, "mean_mfe_10": 0, "mean_mae_10": 0,
            "win_rate": 0, "composite": 0,
            "p25_mfe_10": 0, "p50_mfe_10": 0, "p75_mfe_10": 0,
        }

    mean_mfe = subset["fwd_mfe_10"].mean()
    mean_mae = subset["fwd_mae_10"].mean()
    win_rate = subset["fwd_win_10"].astype(bool).mean() if "fwd_win_10" in subset.columns else 0

    composite = mean_mfe * np.sqrt(n) if mean_mfe > 0 else 0

    mfe_vals = subset["fwd_mfe_10"].values
    p25 = np.percentile(mfe_vals, 25)
    p50 = np.percentile(mfe_vals, 50)
    p75 = np.percentile(mfe_vals, 75)

    return {
        "sample_count": n,
        "mean_mfe_10": round(mean_mfe, 4),
        "mean_mae_10": round(mean_mae, 4),
        "win_rate": round(win_rate, 4),
        "composite": round(composite, 4),
        "p25_mfe_10": round(p25, 4),
        "p50_mfe_10": round(p50, 4),
        "p75_mfe_10": round(p75, 4),
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


def compute_line_reach(events_df: pd.DataFrame, mask: pd.Series, fan_line_catalog: dict) -> dict:
    """
    For events matching mask, compute how often price reaches the next angle line.

    Uses fan_line_catalog dict from trace_miner to find next line in event's direction.
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

        # Look up fan lines at this bar
        fan_lines = fan_line_catalog.get(fan_id, {}).get(bar_idx, [])

        next_line_price = None
        for frac_val, price in fan_lines:
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


def run_tier2(events_df: pd.DataFrame, tier1_candidates: pd.DataFrame, fan_line_catalog: dict) -> pd.DataFrame:
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

        reach = compute_line_reach(non_retro, mask, fan_line_catalog)

        row = candidate.to_dict()
        row.update(reach)
        results.append(row)

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values("composite", ascending=False).head(20)
    return results_df


def grade_patterns(tier1_df: pd.DataFrame, tier2_df: pd.DataFrame) -> pd.DataFrame:
    """
    Grade Tier 1 candidates into A/B/C tiers using H1 stats + H2 line-reach.

    Grading rules:
      A: H1 passes, H2 line_reach_rate_10 > 50%  -> Best: MFE edge + hits the line
      B: H1 passes, H2 line_reach_rate_10 <= 50% -> Good MFE, don't target the line
      C: H1 passes weakly (win_rate 50-55%)       -> Marginal, needs more data
      Discard: H1 fails (excluded from output)

    Args:
        tier1_df: DataFrame from run_tier1() with columns: pattern, win_rate, mean_mfe_10, composite
        tier2_df: DataFrame from run_tier2() with columns: pattern, line_reach_rate_10, line_reach_rate_20

    Returns:
        DataFrame with grade column added, sorted by grade (A first) then composite desc.
        Only includes graded (non-discard) patterns.
    """
    # Merge Tier 1 and Tier 2 on pattern name
    merged = tier1_df.copy()

    if not tier2_df.empty:
        t2_cols = ["pattern", "line_reach_rate_10", "line_reach_rate_20"]
        existing = [c for c in t2_cols if c in tier2_df.columns]
        merged = merged.merge(tier2_df[existing], on="pattern", how="left")

    if "line_reach_rate_10" not in merged.columns:
        merged["line_reach_rate_10"] = 0.0

    merged["line_reach_rate_10"] = merged["line_reach_rate_10"].fillna(0.0)

    def assign_grade(row):
        win_rate = row.get("win_rate", 0)
        reach = row.get("line_reach_rate_10", 0)

        # H1 must pass: win_rate > 50% (already filtered by run_tier1, but guard anyway)
        if win_rate <= 0.50:
            return "DISCARD"

        if win_rate > 0.55 and reach > 0.50:
            return "A"
        elif win_rate > 0.55 and reach <= 0.50:
            return "B"
        else:
            return "C"

    merged["grade"] = merged.apply(assign_grade, axis=1)

    # Filter discards
    merged = merged[merged["grade"] != "DISCARD"].copy()

    # Sort: A first, then B, then C; within each grade, composite desc
    grade_order = {"A": 0, "B": 1, "C": 2}
    merged["_grade_sort"] = merged["grade"].map(grade_order)
    merged = merged.sort_values(["_grade_sort", "composite"], ascending=[True, False])
    merged = merged.drop(columns=["_grade_sort"]).reset_index(drop=True)

    return merged
