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


def grade_sequences(tier1_df: pd.DataFrame, tier2_df: pd.DataFrame) -> pd.DataFrame:
    """
    Grade 2-event sequence patterns into A/B/C tiers.

    Reuses the same grading logic as grade_patterns() for single events.
    See grade_patterns() docstring for grading rules.

    Returns:
        DataFrame with grade column, sorted by grade (A first) then composite desc.
    """
    return grade_patterns(tier1_df, tier2_df)


def walk_forward_validate(events_df: pd.DataFrame, candles_df: pd.DataFrame,
                          fan_line_catalog: dict, train_pct: float = 0.7) -> pd.DataFrame:
    """
    Walk-forward validation: mine patterns on train set, evaluate on test set.

    Splits events_df chronologically by bar_index (earliest bars = train).
    Runs full single-event pipeline on train, then evaluates each pattern
    on the test set using the same mask.

    Args:
        events_df: Enriched events DataFrame
        candles_df: OHLC candles DataFrame (for enrichment, not directly used here)
        fan_line_catalog: Catalog from parse_trace()
        train_pct: Fraction of bars for training (default 0.7)

    Returns:
        DataFrame with columns: pattern, grade, train_composite, test_composite,
        train_win_rate, test_win_rate, train_samples, test_samples, persistent (bool).
        Sorted by train_composite descending.
    """
    non_retro = events_df[~events_df["is_retro"]].copy()
    non_retro = non_retro.sort_values("bar_index").reset_index(drop=True)

    # Chronological split: first train_pct of bars -> train, rest -> test
    n = len(non_retro)
    split_idx = int(n * train_pct)
    if split_idx < 20 or n - split_idx < 20:
        raise ValueError(f"Not enough events for split: train={split_idx}, test={n - split_idx}")

    train_events = non_retro.iloc[:split_idx].copy()
    test_events = non_retro.iloc[split_idx:].copy()

    # Run full pipeline on train
    tier1_train = run_tier1(train_events)
    if tier1_train.empty:
        return pd.DataFrame()

    tier2_train = run_tier2(train_events, tier1_train, fan_line_catalog)
    graded_train = grade_patterns(tier1_train, tier2_train)

    if graded_train.empty:
        return pd.DataFrame()

    # Evaluate each train pattern on test set
    results = []
    for _, pattern_row in graded_train.iterrows():
        et = pattern_row["event_type"]
        frac = pattern_row["line_fraction"]
        cp = pattern_row.get("candle_pattern", "any")

        mask_train = (train_events["event_type"] == et) & (train_events["line_fraction"] == str(frac))
        if cp and cp != "any":
            mask_train = mask_train & (train_events["candle_pattern"] == cp)

        mask_test = (test_events["event_type"] == et) & (test_events["line_fraction"] == str(frac))
        if cp and cp != "any":
            mask_test = mask_test & (test_events["candle_pattern"] == cp)

        train_stats = compute_pattern_stats(train_events, mask_train)
        test_stats = compute_pattern_stats(test_events, mask_test)

        # Persistence: test stats within 80% of train
        persistent = (
            test_stats["sample_count"] >= 5
            and test_stats["win_rate"] >= train_stats["win_rate"] * 0.8
            and test_stats["composite"] >= train_stats["composite"] * 0.8
        )

        results.append({
            "pattern": pattern_row["pattern"],
            "grade": pattern_row.get("grade", "?"),
            "train_composite": train_stats["composite"],
            "test_composite": test_stats["composite"],
            "train_win_rate": train_stats["win_rate"],
            "test_win_rate": test_stats["win_rate"],
            "train_samples": train_stats["sample_count"],
            "test_samples": test_stats["sample_count"],
            "persistent": persistent,
        })

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values("train_composite", ascending=False).reset_index(drop=True)
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


def simulate_trailing_exit(events_df: pd.DataFrame, candles_df: pd.DataFrame,
                           pattern_mask: pd.Series, trail_pct: float = 1.0,
                           max_bars: int = 20) -> dict:
    """
    Simulate trailing-stop exit for events matching a pattern mask.

    Entry:
      - Long at event close for UP-direction events
      - Short at event close for DOWN-direction events

    Exit:
      - Trailing stop from high-water mark (longs) or low-water mark (shorts).
      - Trail amount = entry_price * trail_pct / 100.
      - Each bar after entry (max max_bars): update water mark.
        If price reverses beyond trail, exit at the stop price.
      - If not stopped by max_bars, exit at bar close.

    Args:
        events_df: Enriched events DataFrame
        candles_df: OHLC candles DataFrame
        pattern_mask: Boolean mask selecting events for this pattern
        trail_pct: Trail percentage of entry price (default 1.0)
        max_bars: Maximum bars to hold before forced exit (default 20)

    Returns:
        dict with:
          - trades: int — number of simulated trades
          - win_pct: float — win percentage
          - avg_pnl_pct: float — average PnL per trade (%)
          - avg_mfe_captured_pct: float — avg % of MFE captured
          - max_drawdown_pct: float — max trade drawdown (%)
          - trade_log: list of per-trade dicts (entry_price, mfe_price, mfe_pct,
                        exit_price, exit_bar, pnl_pct, result)
    """
    from analysis.trace_miner import get_event_direction

    subset = events_df[pattern_mask].copy()
    n = len(subset)
    if n == 0:
        return {
            "trades": 0, "win_pct": 0, "avg_pnl_pct": 0,
            "avg_mfe_captured_pct": 0, "max_drawdown_pct": 0, "trade_log": []
        }

    candles = candles_df.set_index("bar_index")
    max_bar_idx = candles.index.max()

    trade_log = []
    wins = 0

    for idx, row in subset.iterrows():
        bar_idx = row["bar_index"]
        direction = get_event_direction(row)
        if direction == "NEUTRAL":
            continue

        entry_price = row["close"]
        trail_amount = entry_price * trail_pct / 100.0

        if direction == "UP":
            is_long = True
            water_mark = entry_price
        else:  # DOWN
            is_long = False
            water_mark = entry_price

        exit_price = None
        exit_bar = None
        mfe_price = entry_price

        for step in range(1, max_bars + 1):
            lookup_bar = bar_idx + step
            if lookup_bar > max_bar_idx:
                # End of data, exit at last available close
                last_rows = candles_df[candles_df["bar_index"] <= max_bar_idx]
                exit_price = last_rows.iloc[-1]["close"] if len(last_rows) > 0 else entry_price
                exit_bar = max_bar_idx
                break

            if lookup_bar not in candles.index:
                continue

            candle = candles.loc[lookup_bar]
            # Handle case where .loc returns a DataFrame for duplicate indices
            if isinstance(candle, pd.DataFrame):
                candle = candle.iloc[0]

            bar_high = candle["high"]
            bar_low = candle["low"]
            bar_close = candle["close"]

            if is_long:
                # Update water mark (highest high seen)
                water_mark = max(water_mark, bar_high)
                stop_price = water_mark - trail_amount
                mfe_price = max(mfe_price, bar_high)

                if bar_low <= stop_price:
                    exit_price = stop_price
                    exit_bar = lookup_bar
                    break
            else:
                # Update water mark (lowest low seen)
                water_mark = min(water_mark, bar_low)
                stop_price = water_mark + trail_amount
                mfe_price = min(mfe_price, bar_low)

                if bar_high >= stop_price:
                    exit_price = stop_price
                    exit_bar = lookup_bar
                    break

            # Check if this is the last bar in the window
            if step == max_bars:
                exit_price = bar_close
                exit_bar = lookup_bar

        if exit_price is None:
            exit_price = entry_price
            exit_bar = bar_idx

        if is_long:
            pnl_pct = (exit_price - entry_price) / entry_price * 100
            mfe_pct = (mfe_price - entry_price) / entry_price * 100
        else:
            pnl_pct = (entry_price - exit_price) / entry_price * 100
            mfe_pct = (entry_price - mfe_price) / entry_price * 100

        result = "WIN" if pnl_pct > 0 else "LOSS"
        if pnl_pct > 0:
            wins += 1

        mfe_captured = (pnl_pct / mfe_pct * 100) if mfe_pct > 0 else 0

        trade_log.append({
            "bar_index": bar_idx,
            "direction": direction,
            "entry_price": round(entry_price, 2),
            "mfe_price": round(mfe_price, 2),
            "mfe_pct": round(mfe_pct, 4),
            "exit_price": round(exit_price, 2),
            "exit_bar": exit_bar,
            "pnl_pct": round(pnl_pct, 4),
            "mfe_captured_pct": round(mfe_captured, 1),
            "result": result,
        })

    n_trades = len(trade_log)
    win_pct = round(wins / n_trades * 100, 1) if n_trades > 0 else 0
    avg_pnl = round(sum(t["pnl_pct"] for t in trade_log) / n_trades, 4) if n_trades > 0 else 0
    avg_mfe_captured = round(sum(t["mfe_captured_pct"] for t in trade_log) / n_trades, 1) if n_trades > 0 else 0

    # Max drawdown: worst cumulative PnL
    cumulative = 0
    max_cumulative = 0
    max_dd = 0
    for t in trade_log:
        cumulative += t["pnl_pct"]
        max_cumulative = max(max_cumulative, cumulative)
        dd = max_cumulative - cumulative
        max_dd = max(max_dd, dd)

    return {
        "trades": n_trades,
        "win_pct": win_pct,
        "avg_pnl_pct": avg_pnl,
        "avg_mfe_captured_pct": avg_mfe_captured,
        "max_drawdown_pct": round(max_dd, 4),
        "trade_log": trade_log,
    }


def extract_sequence_pairs(fan_sequences: dict, max_gap: int = 10) -> pd.DataFrame:
    """
    Extract consecutive 2-event pairs from fan-based sequences.

    For each fan's event sequence, takes every consecutive pair of events,
    filters by bar gap <= max_gap, and returns a DataFrame of unique
    (event_type_1, event_type_2) combos with metadata.

    Args:
        fan_sequences: dict from build_fan_sequences() — {fan_id: [event dicts]}
        max_gap: Max bar_index gap between consecutive events (default 10)

    Returns:
        DataFrame with columns:
          fan_id, event_type_1, event_type_2, line_frac_1, line_frac_2,
          bar_index_1, bar_index_2, bar_gap
    """
    pairs = []
    for fan_id, seq in fan_sequences.items():
        for i in range(len(seq) - 1):
            evt_a = seq[i]
            evt_b = seq[i + 1]
            bar_gap = evt_b["bar_index"] - evt_a["bar_index"]
            if bar_gap < 1 or bar_gap > max_gap:
                continue
            pairs.append({
                "fan_id": fan_id,
                "event_type_1": evt_a["event_type"],
                "event_type_2": evt_b["event_type"],
                "line_frac_1": evt_a["line_fraction"],
                "line_frac_2": evt_b["line_fraction"],
                "bar_index_1": evt_a["bar_index"],
                "bar_index_2": evt_b["bar_index"],
                "bar_gap": bar_gap,
            })

    if not pairs:
        return pd.DataFrame(columns=[
            "fan_id", "event_type_1", "event_type_2", "line_frac_1", "line_frac_2",
            "bar_index_1", "bar_index_2", "bar_gap"
        ])

    return pd.DataFrame(pairs)


def run_sequence_tier1(events_df: pd.DataFrame, pair_df: pd.DataFrame,
                       min_sample: int = 5, min_win_rate: float = 0.50) -> pd.DataFrame:
    """
    Tier 1 screening for 2-event sequence patterns.

    For each unique (event_type_1, event_type_2) combo, compute forward-return
    stats using the 2nd event as the entry point. Reuses compute_pattern_stats().

    Args:
        events_df: Enriched events DataFrame
        pair_df: DataFrame from extract_sequence_pairs()
        min_sample: Minimum occurrences for a combo to be considered
        min_win_rate: Minimum forward win rate

    Returns:
        DataFrame sorted by composite score, columns: pattern, event_type_1,
        event_type_2, sample_count, mean_mfe_10, mean_mae_10, win_rate, composite,
        p25_mfe_10, p50_mfe_10, p75_mfe_10
    """
    if pair_df.empty:
        return pd.DataFrame()

    results = []

    combos = pair_df.groupby(["event_type_1", "event_type_2"])

    for (et1, et2), group in combos:
        # Use bar_index of the 2nd event to look up forward returns
        bar_indices = group["bar_index_2"].tolist()
        mask = events_df["bar_index"].isin(bar_indices) & (~events_df["is_retro"])
        stats = compute_pattern_stats(events_df, mask)

        pattern_name = f"{et1}→{et2}"
        if stats["sample_count"] >= min_sample and stats["win_rate"] >= min_win_rate:
            results.append({
                "pattern": pattern_name,
                "event_type_1": et1,
                "event_type_2": et2,
                "sequence_type": "pair",
                **stats,
            })

    if not results:
        return pd.DataFrame()

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values("composite", ascending=False).reset_index(drop=True)
    return results_df


def run_sequence_tier2(events_df: pd.DataFrame, tier1_df: pd.DataFrame,
                       pair_df: pd.DataFrame, fan_line_catalog: dict) -> pd.DataFrame:
    """
    Tier 2 line-reach validation for 2-event sequence patterns.

    Uses the 2nd event of each pair as the entry point for line-reach computation.

    Args:
        events_df: Enriched events DataFrame
        tier1_df: DataFrame from run_sequence_tier1()
        pair_df: DataFrame from extract_sequence_pairs()
        fan_line_catalog: Catalog from parse_trace()

    Returns:
        tier1_df with line_reach_rate columns appended, sorted by composite, top 20.
    """
    if tier1_df.empty or pair_df.empty:
        return pd.DataFrame()

    results = []

    for _, candidate in tier1_df.iterrows():
        et1 = candidate["event_type_1"]
        et2 = candidate["event_type_2"]

        # Find all 2nd-event bar indices for this combo
        combo_pairs = pair_df[(pair_df["event_type_1"] == et1) & (pair_df["event_type_2"] == et2)]
        bar_indices = combo_pairs["bar_index_2"].tolist()

        mask = events_df["bar_index"].isin(bar_indices) & (~events_df["is_retro"])
        reach = compute_line_reach(events_df, mask, fan_line_catalog)

        row = candidate.to_dict()
        row.update(reach)
        results.append(row)

    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values("composite", ascending=False).head(20)
    return results_df
