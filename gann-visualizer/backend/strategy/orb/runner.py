"""
ORB test orchestration.

Takes bars as an argument rather than fetching them, so the whole pipeline is
testable offline. Fetching lives in scripts/run_orb_test.py.
"""

from collections import Counter
from datetime import date, time
from typing import Any, Dict, List, Optional

import pandas as pd

from analysis.signal_trade_simulator import CandleSignal, simulate_trade_grid
from strategy.orb import variant_a_range, variant_b_noise_band
from strategy.orb.costs import (
    BASE_FEE_RATE,
    BASE_SLIPPAGE,
    SLIPPAGE_SWEEP,
    STRESSED_FEE_RATE,
    STRESSED_SLIPPAGE,
    breakeven_slippage,
)
from strategy.orb.placebo import build_placebo_signals, placebo_percentile
from strategy.orb.session import (
    FLAT_BY,
    SESSION_START,
    add_bar_index,
    split_dates_in_half,
    split_sessions,
)
from strategy.orb.types import OrbSignal
from strategy.orb.verdict import CellResult, decide_verdict

# Declared before any code ran. See the spec's "Robustness grid" section.
ROBUSTNESS_GRID: Dict[str, List[Dict[str, Any]]] = {
    "A": [
        {"label": "or=15,r=2.0", "is_headline": True, "params": {"or_minutes": 15}, "r": 2.0},
        {"label": "or=30,r=2.0", "is_headline": False, "params": {"or_minutes": 30}, "r": 2.0},
        {"label": "or=15,r=1.5", "is_headline": False, "params": {"or_minutes": 15}, "r": 1.5},
        {"label": "or=15,r=3.0", "is_headline": False, "params": {"or_minutes": 15}, "r": 3.0},
    ],
    "B": [
        {"label": "k=0.25,r=2.0", "is_headline": True, "params": {"k": 0.25}, "r": 2.0},
        {"label": "k=0.15,r=2.0", "is_headline": False, "params": {"k": 0.15}, "r": 2.0},
        {"label": "k=0.40,r=2.0", "is_headline": False, "params": {"k": 0.40}, "r": 2.0},
        {"label": "k=0.25,r=1.5", "is_headline": False, "params": {"k": 0.25}, "r": 1.5},
        {"label": "k=0.25,r=3.0", "is_headline": False, "params": {"k": 0.25}, "r": 3.0},
    ],
}

INFO_ONLY_R = 1.0


def run_orb(
    symbol: str,
    variant: str,
    bars: pd.DataFrame,
    daily_bars: Optional[pd.DataFrame],
    data_source: str,
    bar_minutes: int = 5,
    session_start: time = SESSION_START,
    flat_by: time = FLAT_BY,
    atr_length: int = 14,
    placebo_seeds: int = 200,
) -> Dict[str, Any]:
    """Run the full pre-registered test and return a report dict."""
    variant = variant.upper()
    if variant not in ROBUSTNESS_GRID:
        raise ValueError(f"unknown variant {variant!r}, expected 'A' or 'B'")
    if bars is None or bars.empty:
        raise ValueError(f"bars for {symbol} are empty — refusing to report zero trades")
    if variant == "B" and (daily_bars is None or daily_bars.empty):
        raise ValueError("variant B needs daily_bars to compute ATR")

    indexed = add_bar_index(bars)
    sessions = split_sessions(indexed)
    session_dates = sorted(sessions)
    if len(session_dates) < 2:
        raise ValueError(f"need at least 2 sessions, got {len(session_dates)}")

    atr_by_date = _atr_by_date(daily_bars, atr_length) if variant == "B" else {}

    train_dates, test_dates = split_dates_in_half(session_dates)
    candles = indexed[["bar_index", "open", "high", "low", "close"]].copy()
    max_session_bars = max(len(session) for session in sessions.values())

    # Built once. A per-lookup scan would be O(sessions) inside a 200-seed
    # placebo loop, which is slow enough to matter on multi-year data.
    bar_to_session_date: Dict[int, date] = {
        int(bar_index): session_date
        for session_date, session in sessions.items()
        for bar_index in session["bar_index"].tolist()
    }

    cells: List[CellResult] = []
    cell_reports: List[Dict[str, Any]] = []
    headline_context: Optional[Dict[str, Any]] = None

    for cell in ROBUSTNESS_GRID[variant]:
        params = {
            **cell["params"],
            "bar_minutes": bar_minutes,
            "session_start": session_start,
            "flat_by": flat_by,
        }
        orb_signals = _generate_all(variant, sessions, params, atr_by_date)
        fired = [s for s in orb_signals if s.triggered]

        base = _simulate(
            candles, fired, cell["r"], max_session_bars, BASE_SLIPPAGE, BASE_FEE_RATE
        )
        stressed = _simulate(
            candles, fired, cell["r"], max_session_bars, STRESSED_SLIPPAGE, STRESSED_FEE_RATE
        )

        result = CellResult(
            label=cell["label"],
            is_headline=cell["is_headline"],
            n_trades_test=_count(base, test_dates),
            avg_net_pnl_test_base=_avg(base, test_dates),
            avg_net_pnl_test_stressed=_avg(stressed, test_dates),
            avg_net_pnl_train_base=_avg(base, train_dates),
        )
        cells.append(result)
        cell_reports.append(
            {
                "label": result.label,
                "is_headline": result.is_headline,
                "n_trades_test": result.n_trades_test,
                "avg_net_pnl_test_base": result.avg_net_pnl_test_base,
                "avg_net_pnl_test_stressed": result.avg_net_pnl_test_stressed,
                "avg_net_pnl_train_base": result.avg_net_pnl_train_base,
            }
        )

        if cell["is_headline"]:
            headline_context = {
                "orb_signals": orb_signals,
                "fired": fired,
                "params": params,
                "r": cell["r"],
            }

    assert headline_context is not None  # grid always declares one headline

    sweep = {
        slippage: _avg(
            _simulate(
                candles,
                headline_context["fired"],
                headline_context["r"],
                max_session_bars,
                slippage,
                BASE_FEE_RATE,
            ),
            test_dates,
        )
        for slippage in SLIPPAGE_SWEEP
    }

    info_grid = _simulate(
        candles, headline_context["fired"], INFO_ONLY_R, max_session_bars,
        BASE_SLIPPAGE, BASE_FEE_RATE,
    )

    percentile = _run_placebo(
        headline_context=headline_context,
        sessions=sessions,
        candles=candles,
        max_session_bars=max_session_bars,
        test_dates=test_dates,
        bar_to_session_date=bar_to_session_date,
        real_avg=_avg_from_cells(cells),
        seeds=placebo_seeds,
    )

    verdict, reasons = decide_verdict(
        cells=cells, placebo_percentile=percentile, data_source=data_source
    )

    skip_reasons = Counter(
        s.reason for s in headline_context["orb_signals"] if not s.triggered
    )

    return {
        "symbol": symbol,
        "variant": variant,
        "data_source": data_source,
        "preliminary": data_source.lower() == "yfinance",
        "sessions": {
            "available": len(session_dates),
            "traded": len(headline_context["fired"]),
            "skipped": len(session_dates) - len(headline_context["fired"]),
            "skip_reasons": dict(skip_reasons),
        },
        "split": {
            "train_dates": [d.isoformat() for d in train_dates],
            "test_dates": [d.isoformat() for d in test_dates],
        },
        "cells": cell_reports,
        "headline_cell": next(c for c in cell_reports if c["is_headline"]),
        "info_only_r1_avg_net_pnl_test": _avg(info_grid, test_dates),
        "slippage_sweep": sweep,
        "breakeven_slippage": breakeven_slippage(sweep),
        "placebo_percentile": percentile,
        "placebo_seeds": placebo_seeds,
        "fee_rate_base": BASE_FEE_RATE,
        "fee_rate_stressed": STRESSED_FEE_RATE,
        "verdict": verdict,
        "verdict_reasons": reasons,
    }


def _generate_all(
    variant: str,
    sessions: Dict[date, pd.DataFrame],
    params: Dict[str, Any],
    atr_by_date: Dict[date, float],
) -> List[OrbSignal]:
    results: List[OrbSignal] = []
    for session_date in sorted(sessions):
        session = sessions[session_date]
        if variant == "A":
            results.append(variant_a_range.generate_signal(session, params))
        else:
            band_params = {**params, "warmup_minutes": params.get("warmup_minutes", 15)}
            results.append(
                variant_b_noise_band.generate_signal(
                    session, band_params, atr=atr_by_date.get(session_date)
                )
            )
    return results


def _atr_by_date(daily_bars: pd.DataFrame, length: int) -> Dict[date, float]:
    """ATR through YESTERDAY's close, keyed by session date."""
    frame = daily_bars.copy()
    frame["session_date"] = (
        pd.to_datetime(frame["timestamp"], unit="s", utc=True)
        .dt.tz_convert("Asia/Kolkata")
        .dt.date
    )
    frame = frame.sort_values("session_date").reset_index(drop=True)
    atr = variant_b_noise_band.daily_atr(frame, length=length).shift(1)
    return {
        row_date: float(value)
        for row_date, value in zip(frame["session_date"], atr)
        if pd.notna(value)
    }


def _simulate(
    candles: pd.DataFrame,
    fired: List[OrbSignal],
    r_value: float,
    max_hold_bars: int,
    slippage: float,
    fee_rate: float,
) -> List[Dict[str, Any]]:
    """Simulate the fired signals and return trades tagged with their session date."""
    if not fired:
        return []
    signals: List[CandleSignal] = [s.signal for s in fired]
    result = simulate_trade_grid(
        candles=candles,
        signals=signals,
        r_values=[r_value],
        max_hold_bars=max_hold_bars,
        fee_rate=fee_rate,
        slippage_per_side=slippage,
    )
    trades = list(result["best"]["per_signal"].values())
    for trade, orb_signal in zip(trades, fired):
        trade["session_date"] = orb_signal.session_date
    return trades


def _in(trades: List[Dict[str, Any]], dates: List[date]) -> List[Dict[str, Any]]:
    wanted = set(dates)
    return [t for t in trades if t["session_date"] in wanted]


def _count(trades: List[Dict[str, Any]], dates: List[date]) -> int:
    return len(_in(trades, dates))


def _avg(trades: List[Dict[str, Any]], dates: List[date]) -> float:
    selected = _in(trades, dates)
    if not selected:
        return 0.0
    return round(sum(t["net_pnl"] for t in selected) / len(selected), 6)


def _avg_from_cells(cells: List[CellResult]) -> float:
    headline = next(cell for cell in cells if cell.is_headline)
    return headline.avg_net_pnl_test_base


def _run_placebo(
    headline_context: Dict[str, Any],
    sessions: Dict[date, pd.DataFrame],
    candles: pd.DataFrame,
    max_session_bars: int,
    test_dates: List[date],
    bar_to_session_date: Dict[int, date],
    real_avg: float,
    seeds: int,
) -> Optional[float]:
    fired = headline_context["fired"]
    if not fired:
        return None

    averages: List[float] = []
    for seed in range(seeds):
        placebo_signals = build_placebo_signals(
            fired, sessions, headline_context["params"], seed=seed
        )
        if not placebo_signals:
            continue
        result = simulate_trade_grid(
            candles=candles,
            signals=placebo_signals,
            r_values=[headline_context["r"]],
            max_hold_bars=max_session_bars,
            fee_rate=BASE_FEE_RATE,
            slippage_per_side=BASE_SLIPPAGE,
        )
        trades = list(result["best"]["per_signal"].values())
        for trade, signal in zip(trades, placebo_signals):
            trade["session_date"] = bar_to_session_date.get(signal.bar_index)
        averages.append(_avg(trades, test_dates))

    if not averages:
        return None
    return placebo_percentile(real_avg, averages)
