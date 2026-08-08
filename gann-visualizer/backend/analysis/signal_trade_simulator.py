from dataclasses import asdict, dataclass
import math
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd


@dataclass(frozen=True)
class CandleSignal:
    bar_index: int
    side: str
    entry_price: float
    stop_price: float
    signal_time: Any
    max_hold_bars: Optional[int] = None


def simulate_trade_grid(
    candles: pd.DataFrame,
    signals: Iterable[CandleSignal],
    r_values: Iterable[float],
    max_hold_bars: int,
    fee_rate: float = 0.0,
    slippage_per_side: float = 0.0,
) -> Dict[str, Any]:
    signal_list = _normalize_signals(signals)
    r_grid = [_validate_r_value(r_value) for r_value in _normalize_r_values(r_values)]
    max_hold_bars = _coerce_integer_value("max_hold_bars", max_hold_bars)
    fee_rate = _validate_execution_cost_input("fee_rate", fee_rate)
    slippage_per_side = _validate_execution_cost_input(
        "slippage_per_side", slippage_per_side
    )
    candles_by_bar = _prepare_candles(candles)
    _validate_inputs(
        candles_by_bar=candles_by_bar,
        signals=signal_list,
        r_grid=r_grid,
        max_hold_bars=max_hold_bars,
    )

    all_r_results = [
        _simulate_for_r(
            candles_by_bar=candles_by_bar,
            signals=signal_list,
            r_value=r_value,
            max_hold_bars=max_hold_bars,
            fee_rate=fee_rate,
            slippage_per_side=slippage_per_side,
        )
        for r_value in r_grid
    ]

    best = _choose_best_result(all_r_results)
    per_signal = best["per_signal"] if best else {}

    return {
        "best": best,
        "all_r_results": all_r_results,
        "per_signal": per_signal,
    }


def _prepare_candles(candles: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(candles, pd.DataFrame):
        raise ValueError("candles must be a pandas DataFrame")

    required_columns = {"bar_index", "high", "low", "close"}
    missing = required_columns.difference(candles.columns)
    if missing:
        raise ValueError(f"candles missing required columns: {sorted(missing)}")

    prepared = candles.copy()
    prepared["bar_index"] = [
        _coerce_integer_value("candle bar_index", bar_index)
        for bar_index in prepared["bar_index"].tolist()
    ]

    if prepared["bar_index"].duplicated().any():
        raise ValueError("candles contain duplicate bar_index values")

    prepared = prepared.sort_values("bar_index")
    _validate_candle_prices(prepared)
    return prepared.set_index("bar_index")


def _validate_inputs(
    candles_by_bar: pd.DataFrame,
    signals: List[CandleSignal],
    r_grid: List[float],
    max_hold_bars: int,
) -> None:
    if max_hold_bars <= 0:
        raise ValueError("max_hold_bars must be positive")
    if not r_grid:
        raise ValueError("r_values must not be empty")
    if any(not math.isfinite(r_value) or r_value <= 0 for r_value in r_grid):
        raise ValueError("r_values must be finite and strictly positive")
    if candles_by_bar.empty:
        raise ValueError("candles must not be empty")

    min_bar_index = int(candles_by_bar.index.min())
    max_bar_index = int(candles_by_bar.index.max())

    for signal in signals:
        _validate_signal(
            candles_by_bar=candles_by_bar,
            signal=signal,
            min_bar_index=min_bar_index,
            max_bar_index=max_bar_index,
            max_hold_bars=max_hold_bars,
        )


def _validate_signal(
    candles_by_bar: pd.DataFrame,
    signal: CandleSignal,
    min_bar_index: int,
    max_bar_index: int,
    max_hold_bars: int,
) -> None:
    side = _normalize_side(signal.side)
    if side not in {"LONG", "SHORT"}:
        raise ValueError(f"unsupported side: {signal.side}")

    signal_bar_index = _coerce_integer_value("bar_index", signal.bar_index)
    entry_price = _validate_positive_price("entry_price", signal.entry_price)
    stop_price = _validate_positive_price("stop_price", signal.stop_price)

    if entry_price == stop_price:
        raise ValueError(f"signal at bar {signal_bar_index} has non-positive risk")
    if side == "LONG" and stop_price >= entry_price:
        raise ValueError(
            f"signal at bar {signal_bar_index} has invalid stop orientation for LONG"
        )
    if side == "SHORT" and stop_price <= entry_price:
        raise ValueError(
            f"signal at bar {signal_bar_index} has invalid stop orientation for SHORT"
        )

    if signal_bar_index < min_bar_index or signal_bar_index > max_bar_index:
        raise ValueError(
            f"signal bar_index {signal_bar_index} outside candle range "
            f"[{min_bar_index}, {max_bar_index}]"
        )
    if signal_bar_index not in candles_by_bar.index:
        raise ValueError(f"signal at bar {signal_bar_index} is not simulatable")

    simulation_window = _future_bar_window(
        candles_by_bar=candles_by_bar,
        signal_bar_index=signal_bar_index,
        max_hold_bars=_effective_max_hold(signal, max_hold_bars),
    )
    if simulation_window.empty:
        raise ValueError(f"signal at bar {signal_bar_index} is not simulatable")


def _simulate_for_r(
    candles_by_bar: pd.DataFrame,
    signals: List[CandleSignal],
    r_value: float,
    max_hold_bars: int,
    fee_rate: float,
    slippage_per_side: float,
) -> Dict[str, Any]:
    trades = [
        _simulate_single_trade(
            candles_by_bar=candles_by_bar,
            signal=signal,
            signal_index=signal_index,
            r_value=r_value,
            max_hold_bars=max_hold_bars,
            fee_rate=fee_rate,
            slippage_per_side=slippage_per_side,
        )
        for signal_index, signal in enumerate(signals)
    ]

    wins = sum(1 for trade in trades if trade["outcome"] == "WIN")
    losses = sum(1 for trade in trades if trade["outcome"] == "LOSS")
    breakevens = sum(1 for trade in trades if trade["outcome"] == "BREAKEVEN")
    net_pnl_total = round(sum(trade["net_pnl"] for trade in trades), 6)
    gross_profit = round(sum(max(trade["net_pnl"], 0.0) for trade in trades), 6)
    gross_loss = round(sum(-min(trade["net_pnl"], 0.0) for trade in trades), 6)
    n = len(trades)

    return {
        "r_value": r_value,
        "n": n,
        "wins": wins,
        "losses": losses,
        "breakevens": breakevens,
        "win_rate": round(wins / n, 4) if n else 0.0,
        "net_pnl_total": net_pnl_total,
        "avg_net_pnl": round(net_pnl_total / n, 6) if n else 0.0,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "per_signal": {trade["signal_key"]: trade for trade in trades},
    }


def _simulate_single_trade(
    candles_by_bar: pd.DataFrame,
    signal: CandleSignal,
    signal_index: int,
    r_value: float,
    max_hold_bars: int,
    fee_rate: float,
    slippage_per_side: float,
) -> Dict[str, Any]:
    side = _normalize_side(signal.side)
    if side not in {"LONG", "SHORT"}:
        raise ValueError(f"unsupported side: {signal.side}")

    risk = abs(signal.entry_price - signal.stop_price)
    if risk <= 0:
        raise ValueError(f"signal at bar {signal.bar_index} has non-positive risk")

    target_price = _target_price(signal.entry_price, signal.stop_price, side, r_value)
    signal_key = _signal_key(signal.bar_index, signal_index)
    exit_bar_index = signal.bar_index
    exit_price = signal.entry_price
    exit_reason = "end_of_data"
    exit_time = None
    last_observed_bar_index = None
    last_observed_close = None
    last_observed_time = None

    effective_max_hold = _effective_max_hold(signal, max_hold_bars)
    future_bars = _future_bar_window(
        candles_by_bar=candles_by_bar,
        signal_bar_index=signal.bar_index,
        max_hold_bars=effective_max_hold,
    )
    for lookup_bar in future_bars:
        candle = candles_by_bar.loc[lookup_bar]
        bar_high = float(candle["high"])
        bar_low = float(candle["low"])
        bar_close = float(candle["close"])
        exit_time = candle["time"] if "time" in candle.index else None
        last_observed_bar_index = lookup_bar
        last_observed_close = bar_close
        last_observed_time = exit_time

        stop_hit = _stop_hit(side, signal.stop_price, bar_high, bar_low)
        target_hit = _target_hit(side, target_price, bar_high, bar_low)

        exit_bar_index = lookup_bar

        if stop_hit:
            exit_price = signal.stop_price
            exit_reason = "stop_loss"
            break
        if target_hit:
            exit_price = target_price
            exit_reason = "target"
            break

    if exit_reason == "end_of_data" and last_observed_close is not None:
        exit_bar_index = last_observed_bar_index
        exit_price = last_observed_close
        exit_time = last_observed_time
        if len(future_bars) == effective_max_hold:
            exit_reason = "max_hold"

    gross_pnl = _gross_pnl(side, signal.entry_price, exit_price)
    cost = _trade_cost(
        entry_price=signal.entry_price,
        exit_price=exit_price,
        fee_rate=fee_rate,
        slippage_per_side=slippage_per_side,
    )
    net_pnl = round(gross_pnl - cost, 6)

    if net_pnl > 0:
        outcome = "WIN"
    elif net_pnl < 0:
        outcome = "LOSS"
    else:
        outcome = "BREAKEVEN"

    return {
        "signal_key": signal_key,
        "signal_index": signal_index,
        "bar_index": signal.bar_index,
        "signal_time": signal.signal_time,
        "side": side,
        "entry_price": float(signal.entry_price),
        "stop_price": float(signal.stop_price),
        "target_price": round(target_price, 6),
        "r_value": r_value,
        "risk_per_unit": round(risk, 6),
        "exit_bar_index": exit_bar_index,
        "exit_time": exit_time,
        "exit_price": round(exit_price, 6),
        "exit_reason": exit_reason,
        "gross_pnl": round(gross_pnl, 6),
        "fees": round(cost, 6),
        "net_pnl": net_pnl,
        "outcome": outcome,
        "signal": asdict(signal),
    }


def _signal_key(bar_index: int, signal_index: int) -> str:
    return f"{bar_index}:{signal_index}"


def _effective_max_hold(signal: CandleSignal, max_hold_bars: int) -> int:
    """Per-signal cap overrides the global one when present."""
    if signal.max_hold_bars is None:
        return max_hold_bars
    return signal.max_hold_bars


def _future_bar_window(
    candles_by_bar: pd.DataFrame,
    signal_bar_index: int,
    max_hold_bars: int,
) -> pd.Index:
    future_bars = candles_by_bar.index[candles_by_bar.index > signal_bar_index]
    return future_bars[:max_hold_bars]


def _target_price(entry_price: float, stop_price: float, side: str, r_value: float) -> float:
    risk = abs(entry_price - stop_price)
    if side == "LONG":
        return entry_price + (risk * r_value)
    return entry_price - (risk * r_value)


def _stop_hit(side: str, stop_price: float, bar_high: float, bar_low: float) -> bool:
    if side == "LONG":
        return bar_low <= stop_price
    return bar_high >= stop_price


def _target_hit(side: str, target_price: float, bar_high: float, bar_low: float) -> bool:
    if side == "LONG":
        return bar_high >= target_price
    return bar_low <= target_price


def _gross_pnl(side: str, entry_price: float, exit_price: float) -> float:
    if side == "LONG":
        return exit_price - entry_price
    return entry_price - exit_price


def _validate_candle_prices(candles: pd.DataFrame) -> None:
    validated_columns = {}
    for column_name in ("high", "low", "close"):
        validated_columns[column_name] = pd.Series(
            [
                _validate_positive_price(f"candle {column_name}", value)
                for value in candles[column_name].tolist()
            ],
            index=candles.index,
            dtype="float64",
        )

    high_values = validated_columns["high"]
    low_values = validated_columns["low"]
    close_values = validated_columns["close"]

    if (high_values < low_values).any():
        raise ValueError("candle high must be greater than or equal to candle low")
    if ((close_values < low_values) | (close_values > high_values)).any():
        raise ValueError("candle close must be between candle low and candle high")


def _normalize_signal(signal: CandleSignal) -> CandleSignal:
    if not isinstance(signal, CandleSignal):
        raise ValueError("signals must contain CandleSignal instances")

    max_hold = signal.max_hold_bars
    if max_hold is not None:
        max_hold = _coerce_integer_value("max_hold_bars", max_hold)
        if max_hold <= 0:
            raise ValueError("max_hold_bars must be positive when set")

    return CandleSignal(
        bar_index=_coerce_integer_value("bar_index", signal.bar_index),
        side=signal.side,
        entry_price=_validate_positive_price("entry_price", signal.entry_price),
        stop_price=_validate_positive_price("stop_price", signal.stop_price),
        signal_time=signal.signal_time,
        max_hold_bars=max_hold,
    )


def _normalize_signals(signals: Iterable[CandleSignal]) -> List[CandleSignal]:
    try:
        return [_normalize_signal(signal) for signal in signals]
    except TypeError as exc:
        if "not iterable" not in str(exc):
            raise
        raise ValueError("signals must contain CandleSignal instances") from None


def _normalize_r_values(r_values: Iterable[float]) -> List[float]:
    if r_values is None or isinstance(r_values, (str, bytes, bytearray, memoryview)):
        raise ValueError("r_values must be an iterable of numeric values")

    try:
        return list(r_values)
    except TypeError:
        raise ValueError("r_values must be an iterable of numeric values") from None


def _normalize_side(side: Any) -> str:
    if not isinstance(side, str):
        raise ValueError("side must be a string")
    return side.upper()


def _coerce_numeric_value(
    field_name: str,
    value: Any,
    error_message: Optional[str] = None,
) -> float:
    resolved_error_message = error_message or f"{field_name} must be finite"
    if isinstance(value, bool):
        raise ValueError(resolved_error_message)
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        raise ValueError(resolved_error_message) from None

    if not math.isfinite(numeric_value):
        raise ValueError(resolved_error_message)

    return numeric_value


def _coerce_integer_value(field_name: str, value: Any) -> int:
    numeric_value = _coerce_numeric_value(
        field_name,
        value,
        error_message=f"{field_name} must be an integer",
    )
    if not numeric_value.is_integer():
        raise ValueError(f"{field_name} must be an integer")

    return int(numeric_value)


def _validate_positive_price(field_name: str, value: Any) -> float:
    numeric_value = _coerce_numeric_value(field_name, value)
    if numeric_value <= 0:
        raise ValueError(f"{field_name} must be positive")
    return numeric_value


def _validate_execution_cost_input(field_name: str, value: Any) -> float:
    numeric_value = _coerce_numeric_value(
        field_name,
        value,
        error_message=f"{field_name} must be finite and non-negative",
    )
    if numeric_value < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return numeric_value


def _validate_r_value(value: Any) -> float:
    numeric_value = _coerce_numeric_value(
        "r_values",
        value,
        error_message="r_values must be finite and strictly positive",
    )
    if numeric_value <= 0:
        raise ValueError("r_values must be finite and strictly positive")
    return numeric_value


def _trade_cost(
    entry_price: float,
    exit_price: float,
    fee_rate: float,
    slippage_per_side: float,
) -> float:
    notional_fees = (entry_price + exit_price) * fee_rate
    slippage = slippage_per_side * 2.0
    return notional_fees + slippage


def _choose_best_result(all_r_results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not all_r_results:
        return None

    return max(
        all_r_results,
        key=lambda result: (result["net_pnl_total"], -result["r_value"]),
    )
