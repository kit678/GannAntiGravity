from dataclasses import asdict, dataclass
import math
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CandleSignal:
    bar_index: int
    side: str
    entry_price: float
    stop_price: float
    signal_time: Any
    max_hold_bars: Optional[int] = None
    entry_bar_index: Optional[int] = None
    """Bar the position actually opens on.

    ``None`` (or equal to ``bar_index``) means the legacy behaviour: filled at
    the signal bar's close, so exposure starts on the next bar. A later bar
    means filled at that bar's OPEN, so that bar's own high/low can already
    stop you out -- which is the only executable reading of a signal that is
    not knowable until its bar has closed.
    """


def simulate_trade_grid(
    candles: pd.DataFrame,
    signals: Iterable[CandleSignal],
    r_values: Iterable[float],
    max_hold_bars: int,
    fee_rate: float = 0.0,
    slippage_per_side: float = 0.0,
    maker_fee_rate: Optional[float] = None,
    select_r: Optional[float] = None,
) -> Dict[str, Any]:
    """Run every R in the grid; report one of them as the headline.

    ``maker_fee_rate`` applies to target exits only -- a target is a resting
    limit order, a stop and a max-hold exit are market orders. Left unset it
    falls back to ``fee_rate``, preserving the all-taker behaviour.

    ``select_r`` pins ``best`` to a declared R. Without it, ``best`` is the R
    that happened to win, which is a choice you cannot make in advance; the
    hindsight winner is always reported separately as ``hindsight_best``.
    """
    signal_list = _normalize_signals(signals)
    r_grid = [_validate_r_value(r_value) for r_value in _normalize_r_values(r_values)]
    max_hold_bars = _coerce_integer_value("max_hold_bars", max_hold_bars)
    fee_rate = _validate_execution_cost_input("fee_rate", fee_rate)
    slippage_per_side = _validate_execution_cost_input(
        "slippage_per_side", slippage_per_side
    )
    if maker_fee_rate is None:
        maker_fee_rate = fee_rate
    else:
        maker_fee_rate = _validate_execution_cost_input("maker_fee_rate", maker_fee_rate)
    if select_r is not None:
        select_r = _validate_r_value(select_r)

    candles_by_bar = _prepare_candles(candles)
    _validate_inputs(
        candles_by_bar=candles_by_bar,
        signals=signal_list,
        r_grid=r_grid,
        max_hold_bars=max_hold_bars,
    )

    bars = _BarArrays(candles_by_bar)
    all_r_results = [
        _simulate_for_r(
            bars=bars,
            signals=signal_list,
            r_value=r_value,
            max_hold_bars=max_hold_bars,
            fee_rate=fee_rate,
            slippage_per_side=slippage_per_side,
            maker_fee_rate=maker_fee_rate,
        )
        for r_value in r_grid
    ]

    hindsight_best = _choose_best_result(all_r_results)
    best = hindsight_best
    if select_r is not None:
        selected = next(
            (r for r in all_r_results if r["r_value"] == select_r), None
        )
        if selected is None:
            raise ValueError(f"select_r {select_r} is not in r_values")
        best = selected
    per_signal = best["per_signal"] if best else {}

    return {
        "best": best,
        "hindsight_best": hindsight_best,
        "selected_r": select_r,
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
    prepared["bar_index"] = _coerce_integer_column("candle bar_index", prepared["bar_index"])

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

    simulation_window = _exposure_window(
        candles_by_bar=candles_by_bar,
        signal=signal,
        max_hold_bars=_effective_max_hold(signal, max_hold_bars),
    )
    if simulation_window.empty:
        raise ValueError(f"signal at bar {signal_bar_index} is not simulatable")


class _BarArrays:
    """Candle columns as plain arrays, built once per grid.

    ``candles_by_bar.loc[bar]`` costs ~10us. A 40-bar hold over 16k signals
    across a 7-value R grid is 4.5M of those lookups -- minutes per file. The
    arrays make the same walk a plain integer loop.
    """

    __slots__ = ("bar_index", "high", "low", "close", "time", "count")

    def __init__(self, candles_by_bar: pd.DataFrame) -> None:
        self.bar_index = candles_by_bar.index.to_numpy()
        self.high = candles_by_bar["high"].to_numpy(dtype=float)
        self.low = candles_by_bar["low"].to_numpy(dtype=float)
        self.close = candles_by_bar["close"].to_numpy(dtype=float)
        self.time = (
            candles_by_bar["time"].tolist() if "time" in candles_by_bar.columns else None
        )
        self.count = len(self.bar_index)

    def exposure_positions(self, signal: CandleSignal, max_hold_bars: int):
        """Row positions the position is exposed on, as a half-open range.

        ``_prepare_candles`` sorts by bar_index, so the exposed bars are always
        a contiguous slice and searchsorted can find its start.
        """
        entry_bar = _entry_bar_index(signal)
        if entry_bar > signal.bar_index:
            start = int(np.searchsorted(self.bar_index, entry_bar, side="left"))
        else:
            start = int(np.searchsorted(self.bar_index, signal.bar_index, side="right"))
        return start, min(start + max_hold_bars, self.count)


def _simulate_for_r(
    bars: "_BarArrays",
    signals: List[CandleSignal],
    r_value: float,
    max_hold_bars: int,
    fee_rate: float,
    slippage_per_side: float,
    maker_fee_rate: float,
) -> Dict[str, Any]:
    trades = [
        _simulate_single_trade(
            bars=bars,
            signal=signal,
            signal_index=signal_index,
            r_value=r_value,
            max_hold_bars=max_hold_bars,
            fee_rate=fee_rate,
            slippage_per_side=slippage_per_side,
            maker_fee_rate=maker_fee_rate,
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

    result = {
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
    result.update(_r_multiple_summary(trades))
    return result


def _r_multiple_summary(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Expectancy in R, not in price units.

    Summing price deltas pools a 60,000-dollar BTC trade with a 24,000-point
    index trade and calls the total performance. R-multiples are the only
    figure that survives being pooled across symbols, timeframes and eras.
    """
    n = len(trades)
    if not n:
        return {
            "expectancy_r": 0.0, "total_r": 0.0, "profit_factor": 0.0,
            "avg_win_r": 0.0, "avg_loss_r": 0.0,
        }

    r_values = [trade["net_r"] for trade in trades]
    wins = [r for r in r_values if r > 0]
    losses = [-r for r in r_values if r < 0]
    gross_win = sum(wins)
    gross_loss = sum(losses)

    return {
        "expectancy_r": round(sum(r_values) / n, 6),
        "total_r": round(sum(r_values), 6),
        "profit_factor": (
            round(gross_win / gross_loss, 6) if gross_loss else float("inf")
        ),
        "avg_win_r": round(gross_win / len(wins), 6) if wins else 0.0,
        "avg_loss_r": round(gross_loss / len(losses), 6) if losses else 0.0,
    }


def _simulate_single_trade(
    bars: "_BarArrays",
    signal: CandleSignal,
    signal_index: int,
    r_value: float,
    max_hold_bars: int,
    fee_rate: float,
    slippage_per_side: float,
    maker_fee_rate: float,
) -> Dict[str, Any]:
    side = _normalize_side(signal.side)
    if side not in {"LONG", "SHORT"}:
        raise ValueError(f"unsupported side: {signal.side}")

    risk = abs(signal.entry_price - signal.stop_price)
    if risk <= 0:
        raise ValueError(f"signal at bar {signal.bar_index} has non-positive risk")

    target_price = _target_price(signal.entry_price, signal.stop_price, side, r_value)
    signal_key = _signal_key(signal.bar_index, signal_index)
    entry_bar_index = _entry_bar_index(signal)
    exit_bar_index = entry_bar_index
    exit_price = signal.entry_price
    exit_reason = "end_of_data"
    exit_time = None
    last_observed_bar_index = None
    last_observed_close = None
    last_observed_time = None

    effective_max_hold = _effective_max_hold(signal, max_hold_bars)
    start_position, end_position = bars.exposure_positions(signal, effective_max_hold)
    is_long = side == "LONG"
    stop_price = signal.stop_price

    for position in range(start_position, end_position):
        bar_high = bars.high[position]
        bar_low = bars.low[position]
        bar_close = bars.close[position]
        exit_time = bars.time[position] if bars.time is not None else None
        last_observed_bar_index = int(bars.bar_index[position])
        last_observed_close = float(bar_close)
        last_observed_time = exit_time

        exit_bar_index = last_observed_bar_index

        if is_long:
            stop_hit = bar_low <= stop_price
            target_hit = bar_high >= target_price
        else:
            stop_hit = bar_high >= stop_price
            target_hit = bar_low <= target_price

        if stop_hit:
            exit_price = stop_price
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
        if (end_position - start_position) == effective_max_hold:
            exit_reason = "max_hold"

    # A target is a resting limit order and rebates the maker rate; a stop or a
    # max-hold exit is a market order and pays taker.
    exit_is_maker = exit_reason == "target"
    gross_pnl = _gross_pnl(side, signal.entry_price, exit_price)
    cost = _trade_cost(
        entry_price=signal.entry_price,
        exit_price=exit_price,
        fee_rate=fee_rate,
        slippage_per_side=slippage_per_side,
        exit_fee_rate=maker_fee_rate if exit_is_maker else fee_rate,
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
        "entry_bar_index": entry_bar_index,
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
        "exit_is_maker": exit_is_maker,
        "gross_pnl": round(gross_pnl, 6),
        "fees": round(cost, 6),
        "net_pnl": net_pnl,
        "net_r": round(net_pnl / risk, 6),
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


def _entry_bar_index(signal: CandleSignal) -> int:
    if signal.entry_bar_index is None:
        return signal.bar_index
    return signal.entry_bar_index


def _exposure_window(
    candles_by_bar: pd.DataFrame,
    signal: CandleSignal,
    max_hold_bars: int,
) -> pd.Index:
    """Bars on which the position can be stopped, targeted, or timed out.

    A close fill on the signal bar is not exposed to that bar -- the bar is
    already over. An open fill on a later bar IS exposed to it, and a gap
    through the stop on that very bar is the single most common way this
    kind of entry actually loses.
    """
    entry_bar = _entry_bar_index(signal)
    if entry_bar > signal.bar_index:
        window = candles_by_bar.index[candles_by_bar.index >= entry_bar]
    else:
        window = candles_by_bar.index[candles_by_bar.index > signal.bar_index]
    return window[:max_hold_bars]


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


def _plain_numeric_array(series: pd.Series) -> Optional["np.ndarray"]:
    """Float view of an already-numeric column, or ``None`` to take the slow path.

    Booleans are excluded deliberately: ``_coerce_numeric_value`` rejects them,
    and ``np.issubdtype(bool, np.integer)`` would happily let them through.
    """
    dtype = series.dtype
    if dtype == bool or not (
        np.issubdtype(dtype, np.integer) or np.issubdtype(dtype, np.floating)
    ):
        return None
    return series.to_numpy(dtype=float)


def _coerce_integer_column(field_name: str, series: pd.Series) -> List[int]:
    values = _plain_numeric_array(series)
    if values is None:
        return [_coerce_integer_value(field_name, value) for value in series.tolist()]
    if not np.isfinite(values).all() or not np.equal(np.mod(values, 1), 0).all():
        raise ValueError(f"{field_name} must be an integer")
    return values.astype(np.int64).tolist()


def _validate_positive_price_column(field_name: str, series: pd.Series) -> "np.ndarray":
    values = _plain_numeric_array(series)
    if values is None:
        return np.array(
            [_validate_positive_price(field_name, value) for value in series.tolist()],
            dtype=float,
        )
    if not np.isfinite(values).all():
        raise ValueError(f"{field_name} must be finite")
    if (values <= 0).any():
        raise ValueError(f"{field_name} must be positive")
    return values


def _validate_candle_prices(candles: pd.DataFrame) -> None:
    validated_columns = {}
    for column_name in ("high", "low", "close"):
        validated_columns[column_name] = pd.Series(
            _validate_positive_price_column(f"candle {column_name}", candles[column_name]),
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

    bar_index = _coerce_integer_value("bar_index", signal.bar_index)
    entry_bar = signal.entry_bar_index
    if entry_bar is not None:
        entry_bar = _coerce_integer_value("entry_bar_index", entry_bar)
        if entry_bar < bar_index:
            raise ValueError("entry_bar_index must not precede bar_index")

    return CandleSignal(
        bar_index=bar_index,
        side=signal.side,
        entry_price=_validate_positive_price("entry_price", signal.entry_price),
        stop_price=_validate_positive_price("stop_price", signal.stop_price),
        signal_time=signal.signal_time,
        max_hold_bars=max_hold,
        entry_bar_index=entry_bar,
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
    exit_fee_rate: Optional[float] = None,
) -> float:
    if exit_fee_rate is None:
        exit_fee_rate = fee_rate
    notional_fees = (entry_price * fee_rate) + (exit_price * exit_fee_rate)
    slippage = slippage_per_side * 2.0
    return notional_fees + slippage


def _choose_best_result(all_r_results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not all_r_results:
        return None

    return max(
        all_r_results,
        key=lambda result: (result["net_pnl_total"], -result["r_value"]),
    )
