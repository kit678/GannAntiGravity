"""
Target Progression Strategy — Replay & Live Paper Trading on Binance Testnet.

Modes:
  replay: python run_binance_live.py BTCUSDT 1h 500
  live:   python run_binance_live.py BTCUSDT 1h --live --qty 0.01
"""

import argparse
import json
import math
import os
import statistics
import sys
import time
from datetime import datetime, timedelta

backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, backend_dir)

from binance_client import BinanceClient
from study_tool.angular_coverage_study import AngularPriceCoverageStudy
from study_tool.pivot_detector import PivotDetector
from analysis.momentum_indicators import classify_momentum, compute_atr
from analysis.target_progression import TargetProgression
from study_tool.bounce_rejection_tracker import BounceRejectionTracker


BASE_DIGITS = {
    "240": 22.0, "4h": 22.0,
    "60": 5.5, "1h": 5.5,
    "15": 13.73,
    "5": 1.0,
    "1": 1.0,
}

INTERVAL_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
    "30m": 1_800_000, "1h": 3_600_000, "2h": 7_200_000,
    "4h": 14_400_000, "6h": 21_600_000, "8h": 28_800_000,
    "12h": 43_200_000, "1d": 86_400_000,
}


def _load_ticker_scale_ratio(symbol, interval):
    """Read ticker_config.json for the exact scale_ratio, or None if not found."""
    try:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ticker_config.json")
        with open(config_path, 'r') as f:
            cfg = json.load(f)
    except Exception:
        return None
    sym = symbol.upper()
    res_map = {"1": "1-Minute", "4": "4-Minute", "15": "15-Minute",
               "60": "60-Minute", "1H": "60-Minute", "1h": "60-Minute",
               "240": "240-Minute", "4H": "240-Minute", "4h": "240-Minute",
               "D": "Daily", "W": "Weekly", "1d": "Daily", "1w": "Weekly"}
    mapped_res = res_map.get(interval)
    if not mapped_res:
        return None
    try:
        return cfg[sym]["24_hour"]["standard"][mapped_res]
    except (KeyError, TypeError):
        try:
            return cfg[sym]["trading_day"]["390_minute"][mapped_res]
        except (KeyError, TypeError):
            return None


def compute_scale_ratio(candles, interval):
    base_val = BASE_DIGITS.get(interval.lower(), 1.0)
    detector = PivotDetector(left_bars=5, right_bars=5)
    for i in range(len(candles)):
        detector.detect_pivots(candles, i)
    pivots = detector.confirmed_pivots
    if len(pivots) < 2:
        print(f"Warning: only {len(pivots)} pivots detected, using base={base_val}")
        return base_val
    pivots.sort(key=lambda p: p.bar_index)
    slopes = []
    for i in range(1, len(pivots)):
        dp = abs(pivots[i].price - pivots[i - 1].price)
        dt = abs(pivots[i].bar_index - pivots[i - 1].bar_index)
        if dt > 0:
            slopes.append(dp / dt)
    if not slopes:
        return base_val
    ideal = statistics.median(slopes)
    shift = math.log10(ideal / base_val) if base_val > 0 else 0
    exponent = round(shift)
    final_ratio = base_val * (10 ** exponent)
    print(f"Computed scale_ratio: {final_ratio:.4f} (ideal={ideal:.4f}, base={base_val}, shift={shift:.2f})")
    return final_ratio


def _candle_to_dict(c):
    return {
        "time": c["time"] // 1000,
        "open": c["open"],
        "high": c["high"],
        "low": c["low"],
        "close": c["close"],
        "volume": c["volume"],
    }


def _anchor_type_from_fan(fan):
    if fan and "(" in fan:
        first_char = fan.split("(")[1][0] if len(fan.split("(")[1]) > 0 else ""
        if first_char == "H":
            return "high"
        elif first_char == "L":
            return "low"
    return ""


def _side_from_event(event, fan=None):
    """Derive LONG/SHORT from fan anchor polarity or event direction."""
    fan_name = fan or event.get('fan', '')
    direction = event.get('direction', event.get('details', '')).lower()
    if fan_name and '(' in fan_name:
        first_char = fan_name.split('(')[1][0] if len(fan_name.split('(')[1]) > 0 else ''
        if first_char == 'H':
            return 'SHORT'
        elif first_char == 'L':
            return 'LONG'
    if 'up' in direction or 'bullish' in direction:
        return 'LONG'
    if 'down' in direction or 'bearish' in direction:
        return 'SHORT'
    return 'LONG'


def _capture_fan_geometry(study, fan_id):
    if not study:
        return None
    try:
        scale_ratio = study.config.get('scale_ratio', 0) if hasattr(study, 'config') else 0

        candidates = [fan_id]
        if not fan_id.startswith('Fan_'):
            candidates.append(f'Fan_{fan_id}')
        if '-' in fan_id:
            candidates.append(fan_id.replace('-', '_'))
            if not fan_id.startswith('Fan_'):
                candidates.append(f'Fan_{fan_id.replace("-", "_")}')

        fan_obj = None
        fan_data = None

        if hasattr(study, 'angle_engine') and hasattr(study.angle_engine, '_fans'):
            for cid in candidates:
                fan_obj = study.angle_engine._fans.get(cid)
                if fan_obj is not None:
                    break

        if fan_obj is None and hasattr(study, '_persisted_fans'):
            for cid in candidates:
                fan_data = study._persisted_fans.get(cid)
                if fan_data is not None:
                    break
            if fan_data is None:
                for cid in candidates:
                    for k, v in study._persisted_fans.items():
                        if cid in k or k.endswith(cid):
                            fan_data = v
                            break
                    if fan_data is not None:
                        break

        if fan_obj is not None:
            return {
                'origin': {
                    'bar_index': int(fan_obj.from_pivot.get('bar_index', 0)),
                    'time': int(fan_obj.from_pivot.get('time', 0)),
                    'price': float(fan_obj.from_pivot.get('price', 0.0)),
                    'label': str(fan_obj.from_pivot.get('type', '')),
                },
                'anchor': {
                    'bar_index': int(fan_obj.to_pivot.get('bar_index', 0)),
                    'time': int(fan_obj.to_pivot.get('time', 0)),
                    'price': float(fan_obj.to_pivot.get('price', 0.0)),
                    'label': str(fan_obj.to_pivot.get('type', '')),
                },
                'rays': [
                    {
                        'id': line.id,
                        'fraction': line.fraction,
                        'points': [
                            {'time': line.start_time, 'price': line.start_price},
                            {'time': line.end_time, 'price': line.end_price},
                        ],
                        'color': line.color or '#2196F3',
                        'width': line.width or 2,
                    }
                    for line in fan_obj.lines
                ],
            }

        if fan_data:
            anchor = fan_data.get('anchor', {})
            target = fan_data.get('target', {})
            rays = _build_rays_from_pivots(target, anchor, scale_ratio)
            return {
                'origin': {
                    'bar_index': target.get('bar_index'),
                    'time': target.get('time'),
                    'price': target.get('price'),
                    'label': target.get('type', ''),
                },
                'anchor': {
                    'bar_index': anchor.get('bar_index'),
                    'time': anchor.get('time'),
                    'price': anchor.get('price'),
                    'label': anchor.get('type', ''),
                },
                'rays': rays,
            }
        return None
    except Exception:
        return None


def _build_rays_from_pivots(origin_pivot, anchor_pivot, scale_ratio):
    """Build ray dicts from persisted anchor/target pivot data.
    Reconstructs the 6 Gann angle lines: main, 0.875, 0.75, 0.5, 0.25, horizontal.

    Uses the same trig-based Gann angle math as angle_engine.py:
      theta = atan2(price_delta / scale_ratio, bars_delta)
      fractional theta = theta * fraction
      end_price = origin_price + tan(frac_theta) * bars * scale_ratio

    This is NOT simple linear interpolation — tan(theta * frac) != tan(theta) * frac.
    """
    import math
    o_time = origin_pivot.get('time', 0)
    o_price = float(origin_pivot.get('price', 0))
    a_time = anchor_pivot.get('time', 0)
    a_price = float(anchor_pivot.get('price', 0))
    o_bar = origin_pivot.get('bar_index', 0)
    a_bar = anchor_pivot.get('bar_index', 0)

    if not o_time or not a_time or o_time == a_time:
        return []
    if not scale_ratio or scale_ratio <= 0:
        return []

    price_delta = a_price - o_price
    dy_visual = price_delta / scale_ratio
    dx_bars = a_bar - o_bar
    if dx_bars <= 0:
        return []

    theta = math.atan2(dy_visual, dx_bars)

    fan_id = f"Fan_{origin_pivot.get('label','')}_{anchor_pivot.get('label','')}"

    rays = []

    rays.append({
        'id': f'{fan_id}_main',
        'fraction': 1.0,
        'points': [
            {'time': o_time, 'price': o_price},
            {'time': a_time, 'price': a_price},
        ],
        'color': '#808080',
        'width': 2,
    })

    fractions = [
        (0.875, '#2196F3', 2),
        (0.75, '#4CAF50', 2),
        (0.5, '#FF9800', 4),
        (0.25, '#F44336', 2),
    ]

    for frac, color, width in fractions:
        frac_theta = theta * frac
        dy_frac_visual = dx_bars * math.tan(frac_theta)
        end_price = o_price + dy_frac_visual * scale_ratio
        rays.append({
            'id': f'{fan_id}_{frac}',
            'fraction': frac,
            'points': [
                {'time': o_time, 'price': o_price},
                {'time': a_time, 'price': end_price},
            ],
            'color': color,
            'width': width,
        })

    frac_theta_half = theta * 0.5
    y_visual_intercept = dx_bars * math.tan(frac_theta_half)
    intercept_price = o_price + y_visual_intercept * scale_ratio
    horiz_end_time = a_time + (a_time - o_time)

    rays.append({
        'id': f'{fan_id}_horizontal',
        'fraction': None,
        'points': [
            {'time': a_time, 'price': intercept_price},
            {'time': horiz_end_time, 'price': intercept_price},
        ],
        'color': '#FFFFFF',
        'width': 1,
    })

    return rays


_RETEST_EVENTS = {"REST", "SUPPORT_TEST", "RESISTANCE_TEST"}
_BREACH_EVENTS = {"BREACH_CONFIRMED", "BREACH_CONFIRMED_NO_ALPHA"}
_CLOSE_EVENTS = {"TARGET_HIT", "TARGET_FAILED"}
_FAN_LIFECYCLE_EVENTS = {"FAN_VALIDATED", "FAN_DEACTIVATED"}


def _make_setup_key(fan_id, fraction):
    return f"{fan_id}|{fraction}"


def _place_entry_order(client, symbol, side, qty, trade):
    try:
        binance_side = 'BUY' if side == 'LONG' else 'SELL'
        order = client.place_market_order(symbol, binance_side, qty)
        trade['order_id'] = order.get('orderId', '')
        trade['fill_price'] = float(order.get('avgPrice', 0) or order.get('price', 0))
        print(f"  [ORDER] ENTRY {binance_side} {qty} {symbol} | id={order.get('orderId')}")
    except Exception as e:
        print(f"  [ORDER ERROR] ENTRY failed: {e}")


def _apply_close_event(event, trade, candles, bar_index, price, fraction, live_mode, client, symbol, qty):
    evt_type = event.get("type", "")
    fan = event.get("fan", "")
    evt_time = event.get("time", candles[bar_index]["time"])

    if evt_type == "TARGET_HIT" and trade["side"] == "LONG":
        pnl = price - trade["entry_price"]
    elif evt_type == "TARGET_HIT" and trade["side"] == "SHORT":
        pnl = trade["entry_price"] - price
    else:
        exit_price = candles[bar_index]["close"]
        if trade["side"] == "LONG":
            pnl = exit_price - trade["entry_price"]
        else:
            pnl = trade["entry_price"] - exit_price
        trade["exit_price"] = exit_price

    if live_mode and evt_type == "TARGET_HIT" and "order_id" in trade:
        try:
            binance_side = "SELL" if trade["side"] == "LONG" else "BUY"
            qty_close = float(trade.get("fill_qty", qty))
            order = client.place_market_order(symbol, binance_side, qty_close, reduce_only=True)
            print(f"  [ORDER] CLOSE {binance_side} {qty_close} {symbol} | id={order.get('orderId')}")
        except Exception as e:
            print(f"  [ORDER ERROR] CLOSE failed: {e}")

    if evt_type == "TARGET_HIT":
        trade["exit_price"] = price
        trade["pnl"] = pnl
        trade["target_fraction"] = fraction
        trade["exit_time"] = evt_time
        trade["exit_bar"] = bar_index
        if abs(pnl) < 1e-8:
            trade["outcome"] = "BREAK_EVEN"
            label = "BREAK_EVEN"
        else:
            trade["outcome"] = "WIN" if pnl > 0 else "LOSS"
            label = "WIN" if pnl > 0 else "LOSS"
        print(f"  [EXIT {label}] {fan} hit {fraction} @ {price:.2f} | PnL: {pnl:+.2f}")
    else:
        trade["exit_time"] = evt_time
        trade["exit_bar"] = bar_index
        trade["pnl"] = pnl
        if abs(pnl) < 1e-8:
            trade["outcome"] = "BREAK_EVEN"
            label = "BREAK_EVEN"
        else:
            trade["outcome"] = "LOSS"
            label = "LOSS"
        print(f"  [EXIT {label}] {fan} TARGET_FAILED @ {trade['exit_price']:.2f} | PnL: {pnl:+.2f}")


def _process_bar_events(bar_events, candles, bar_index, breached_setups, active_trades, trades, live_mode, client, symbol, qty,
                        momentum_filter=False, unfiltered_trades=None, unfiltered_active_trades=None,
                        study=None, entry_mode='retest_baseline', tracker_results=None):
    """
    Strategy state machine — sequence-aware target progression.

    Uses study.target_progression as the single source of truth for
    progression state (origin_angle, current_target, is_active).

    Phases:
      1. Fan lifecycle (FAN_VALIDATED → register, FAN_DEACTIVATED → cleanup)
      2. Breach (BREACH_CONFIRMED) — record setup, classify momentum
         Post-breach immediate entry if entry_mode='breach_immediate' and momentum.
      3. Retest (REST/SUPPORT_TEST/RESISTANCE_TEST on origin_angle) — enter.
         Post-retest momentum gating if entry_mode='retest_momentum'.
      4. Close (TARGET_HIT/TARGET_FAILED) — exit position, advance progression.
      5. Entry-line re-cross stop (CROSS_UP/CROSS_DOWN on entry fraction).
    """
    if unfiltered_trades is None:
        unfiltered_trades = []
    if unfiltered_active_trades is None:
        unfiltered_active_trades = {}

    close_applied = set()
    unfiltered_close_applied = set()
    current_candle = candles[bar_index]
    bar_time = current_candle['time']

    prog = study.target_progression if study else None

    for event in bar_events:
        evt_type = event.get("type", "")
        fan = event.get("fan", "")
        fan_id = event.get("fanIdentity", "")
        fraction = str(event.get("fraction", ""))
        price = event.get("price", 0)
        evt_time = event.get("time", bar_time)

        if evt_type == 'FAN_VALIDATED' and prog and not prog.get_fan_state(fan_id):
            horizontal_price = event.get('horizontalTargetPrice', None)
            full_coverage_price = event.get('fullCoverageTargetPrice', None)
            prog.register_fan(fan_id, horizontal_price, full_coverage_price)
            prog.activate_fan(fan_id)
            print(f"  [PROGRESSION] Registered fan {fan_id}")
            continue

        if evt_type == 'FAN_DEACTIVATED':
            print(f"  [DEBUG] FAN_DEACTIVATED received for {fan_id}")
            if prog:
                prog.on_fan_deactivated(fan_id)
                prog.remove_fan(fan_id)
            if fan_id in active_trades:
                print(f"  [DEBUG] Closing active trade for {fan_id} due to FAN_DEACTIVATED")
                trade = active_trades.pop(fan_id)
                _apply_close_event(
                    {'type': 'TARGET_FAILED', 'fan': fan, 'time': bar_time},
                    trade, candles, bar_index, current_candle['close'], '', live_mode, client, symbol, qty
                )
                trade['outcome'] = 'ABORTED'
                trade['abort_reason'] = 'FAN_INVALIDATED'
                trades.append(trade)
            
            # Find and remove any breached setups associated with this fan
            keys_to_remove = [k for k, v in breached_setups.items() if v.get('fan_id') == fan_id]
            for k in keys_to_remove:
                del breached_setups[k]
                
            continue

        if evt_type in _BREACH_EVENTS:
            if not fan_id or not fraction:
                continue

            # 0.25 is an observation zone only — not a progression gate.
            # Do not record it as a breach setup.
            if fraction == '0.25':
                continue

            side = _side_from_event(event, fan)
            direction = 'up' if side == 'LONG' else 'down'
            try:
                mom = classify_momentum(candles, bar_index, direction)
            except Exception:
                mom = {'state': 'neutral', 'adx': 0, 'rsi': 0, 'rsi_divergence': 'none', 'macd_histogram_slope': 0}
            mom_state = mom.get("state", "neutral")

            if prog:
                is_prog_active = prog.is_progression_active(fan_id)
                origin_angle = prog.get_origin_angle(fan_id)
                current_target = prog.get_current_target(fan_id)

                if not is_prog_active and origin_angle is None:
                    prog.on_breach_confirmed(fan_id, fraction, bar_time)
                    origin_angle = prog.get_origin_angle(fan_id)
                    current_target = prog.get_current_target(fan_id)

                if current_target and current_target == fraction:
                    prog.on_angle_contact(fan_id, fraction, bar_index, price)
                    current_target = prog.get_current_target(fan_id)
                elif current_target is None:
                    fs = prog.get_fan_state(fan_id)
                    if fs and fraction in fs.targets_remaining:
                        prog.on_angle_contact(fan_id, fraction, bar_index, price)
                        current_target = prog.get_current_target(fan_id)
                    elif fs and fs.horizontal_breach_pending and fraction == 'horizontal':
                        prog.on_angle_contact(fan_id, fraction, bar_index, price)
                        current_target = prog.get_current_target(fan_id)

                concurrent_targets = []
                if current_target is None:
                    fs = prog.get_fan_state(fan_id)
                    if fs:
                        concurrent_targets = list(fs.targets_remaining)
            else:
                is_prog_active = False
                origin_angle = None
                current_target = None
                concurrent_targets = []

            setup_key = _make_setup_key(fan_id, fraction)
            should_record = True

            if should_record:
                setup = {
                    "fan": fan,
                    "fan_id": fan_id,
                    "anchor_type": _anchor_type_from_fan(fan),
                    "breach_fraction": fraction,
                    "fraction": fraction,
                    "breach_price": price,
                    "breach_time": evt_time,
                    "breach_bar": bar_index,
                    "side": side,
                    "current_target": current_target,
                    "momentum_state": mom_state,
                    "momentum_adx": mom.get("adx", 0),
                    "momentum_rsi": mom.get("rsi", 0),
                    "momentum_rsi_divergence": mom.get("rsi_divergence", "none"),
                    "momentum_macd_slope": mom.get("macd_histogram_slope", 0),
                    "breach_momentum": mom,
                }
                setup["targets_remaining"] = concurrent_targets if current_target is None else None
                # Capture the step NOW — state may change by the time we enter
                fs = prog.get_fan_state(fan_id) if prog else None
                setup["progression_step"] = _build_step(fraction, _next_step_from_state(fs))
                breached_setups[setup_key] = setup

                if entry_mode == 'breach_immediate' and mom_state == 'momentum':
                    if fan_id not in active_trades:
                        trade = dict(setup)
                        step = setup.get('progression_step', _build_step(fraction, current_target))
                        trade.update({
                            'entry_price': price, 'entry_time': evt_time,
                            'entry_bar': bar_index, 'retest_type': 'breach_immediate',
                            'entry_path': 'breach_immediate', 'stop_price': price,
                            'retest_count': 0, 'progression_step': step,
                        })
                        active_trades[fan_id] = trade
                        if study:
                            trade['fan_geometry'] = _capture_fan_geometry(study, fan_id)
                        if live_mode:
                            _place_entry_order(client, symbol, side, qty, trade)
                        del breached_setups[setup_key]
                        mom_tag = f" | ADX={mom['adx']:.1f} RSI={mom['rsi']:.1f} [{mom_state}]"
                        print(f"  [ENTRY-BREACH] [{side}] {fan} breach_immediate on {fraction} @ {price:.2f}, step={step}{mom_tag}")
                        continue

            mom_tag = f" | ADX={mom['adx']:.1f} RSI={mom['rsi']:.1f} [{mom_state}]"
            print(f"  [BREACH] [{side}] {fan} breached {fraction} @ {price:.2f}{mom_tag}")
            continue

        if evt_type in ("TOUCH", "SUPPORT_TEST", "RESISTANCE_TEST", "REST"):
            if not fan_id or not fraction:
                continue
            setup_key = _make_setup_key(fan_id, fraction)
            setup = breached_setups.get(setup_key)
            if not setup:
                continue

            side = setup.get("side", _side_from_event(event, fan))
            setup["retest_pending"] = True
            if side == "SHORT":
                setup["pullback_trigger"] = current_candle["low"]
            else:
                setup["pullback_trigger"] = current_candle["high"]
            setup["pullback_bar"] = bar_index
            print(f"  [RETEST PENDING] [{side}] {fan} touched {fraction}. Trigger extreme: {setup['pullback_trigger']:.2f}")
            continue

        if evt_type == 'TARGET_HIT':
            target_fan_id = fan_id
            trade = active_trades.get(target_fan_id)
            if trade and target_fan_id not in close_applied:
                close_applied.add(target_fan_id)
                _apply_close_event(event, trade, candles, bar_index, price, fraction, live_mode, client, symbol, qty)
                trade['target_fraction'] = fraction
                trades.append(trade)
                del active_trades[target_fan_id]
                if prog and fraction != 'horizontal':
                    prog.on_target_hit(target_fan_id, fraction)

            if momentum_filter:
                unfiltered_trade = unfiltered_active_trades.get(target_fan_id)
                if unfiltered_trade and target_fan_id not in unfiltered_close_applied:
                    unfiltered_close_applied.add(target_fan_id)
                    unfiltered_entry = dict(unfiltered_trade)
                    _apply_close_event(event, unfiltered_entry, candles, bar_index, price, fraction, False, None, '', 0)
                    unfiltered_trades.append(unfiltered_entry)
                    del unfiltered_active_trades[target_fan_id]
            continue

        if evt_type == 'TARGET_FAILED':
            target_fan_id = fan_id
            trade = active_trades.get(target_fan_id)
            if trade and target_fan_id not in close_applied:
                close_applied.add(target_fan_id)
                _apply_close_event(event, trade, candles, bar_index, current_candle['close'], '', live_mode, client, symbol, qty)
                trades.append(trade)
                del active_trades[target_fan_id]
                if prog:
                    prog.on_fan_deactivated(target_fan_id)

            if momentum_filter:
                unfiltered_trade = unfiltered_active_trades.get(target_fan_id)
                if unfiltered_trade and target_fan_id not in unfiltered_close_applied:
                    unfiltered_close_applied.add(target_fan_id)
                    unfiltered_entry = dict(unfiltered_trade)
                    _apply_close_event(event, unfiltered_entry, candles, bar_index, current_candle['close'], '', False, None, '', 0)
                    unfiltered_trades.append(unfiltered_entry)
                    del unfiltered_active_trades[target_fan_id]
            continue

        if evt_type in ("CROSS_UP", "CROSS_DOWN"):
            if not fan_id or not fraction:
                continue
            setup_key = _make_setup_key(fan_id, fraction)
            setup = breached_setups.get(setup_key)
            if setup and setup.get("retest_pending"):
                side = setup.get("side", _side_from_event(event, fan))
                if (side == "SHORT" and evt_type == "CROSS_UP") or (side == "LONG" and evt_type == "CROSS_DOWN"):
                    setup["outcome"] = "ABORTED"
                    setup["abort_reason"] = "FAKEOUT_CLOSE"
                    trades.append(dict(setup))
                    del breached_setups[setup_key]
                    print(f"  [ABORTED] [{side}] {fan} fakeout close on {fraction}")
            continue


    # PER-BAR EVALUATION: Check Pending Retests
    for setup_key in list(breached_setups.keys()):
        setup = breached_setups[setup_key]
        if not setup.get("retest_pending"):
            continue

        fan_id = setup["fan_id"]
        fraction = setup["fraction"]
        side = setup["side"]

        # 1. Check Invalidation from Tracker
        is_invalid = False
        abort_reason = ""

        if tracker_results:
            if side == "SHORT":
                for bounce in tracker_results.get("bounces", []):
                    if bounce.fan_id == fan_id and bounce.angle_name == str(fraction):
                        is_invalid = True
                        abort_reason = "SUPPORT_BOUNCE"
                        break
            elif side == "LONG":
                for rej in tracker_results.get("rejections", []):
                    if rej.fan_id == fan_id and rej.angle_name == str(fraction):
                        is_invalid = True
                        abort_reason = "RESISTANCE_REJECTION"
                        break

        if is_invalid:
            setup["outcome"] = "ABORTED"
            setup["abort_reason"] = abort_reason
            trades.append(dict(setup))
            del breached_setups[setup_key]
            print(f"  [ABORTED] [{side}] {fan_id} {abort_reason} on {fraction}")
            continue

        # 2. Check Entry Trigger
        trigger_price = setup.get("pullback_trigger")
        if not trigger_price:
            continue

        triggered = False
        if side == "SHORT" and current_candle["low"] < trigger_price:
            triggered = True
        elif side == "LONG" and current_candle["high"] > trigger_price:
            triggered = True

        if triggered:
            trade = dict(setup)
            entry_price = trigger_price

            # Calculate ATR Stop Loss
            atr_vals = compute_atr(candles[:bar_index+1])
            atr = atr_vals[-1] if atr_vals else (current_candle["high"] - current_candle["low"])

            if side == "SHORT":
                stop_loss = entry_price + (1.5 * atr)
            else:
                stop_loss = entry_price - (1.5 * atr)

            trade.update({
                'entry_price': entry_price, 'entry_time': bar_time,
                'entry_bar': bar_index, 'retest_type': 'pullback_breakout',
                'entry_path': entry_mode, 'stop_price': stop_loss,
                'retest_count': 1, 'progression_step': setup.get('progression_step', fraction)
            })

            active_trades[fan_id] = trade
            if study:
                trade['fan_geometry'] = _capture_fan_geometry(study, fan_id)
            if live_mode:
                _place_entry_order(client, symbol, side, qty, trade)

            del breached_setups[setup_key]
            print(f"  [ENTRY] [{side}] {fan_id} triggered at {entry_price:.2f} (Stop: {stop_loss:.2f})")

    # PER-BAR EVALUATION: Check Active Trades for Stop Loss
    for fan_id in list(active_trades.keys()):
        trade = active_trades[fan_id]
        stop_price = trade.get("stop_price")
        if not stop_price:
            continue

        side = trade["side"]
        hit_stop = False

        if side == "SHORT" and current_candle["high"] >= stop_price:
            hit_stop = True
        elif side == "LONG" and current_candle["low"] <= stop_price:
            hit_stop = True

        if hit_stop:
            trade['exit_price'] = stop_price
            trade['exit_time'] = bar_time
            trade['exit_bar'] = bar_index

            if side == 'LONG':
                pnl = stop_price - trade['entry_price']
            else:
                pnl = trade['entry_price'] - stop_price

            trade['pnl'] = pnl
            trade['stop_triggered'] = True

            if abs(pnl) < 1e-8:
                trade['outcome'] = 'BREAK_EVEN'
            else:
                trade['outcome'] = 'WIN' if pnl > 0 else 'LOSS'

            trades.append(dict(trade))
            del active_trades[fan_id]
            print(f"  [EXIT {trade['outcome']}] {fan_id} STOP HIT @ {stop_price:.2f} | PnL: {pnl:+.2f}")


def _next_step_from_state(fan_state):
    """Get the logical next step name from the target progression state.
    
    This looks past internal state-machine details (like horizontal_breach_pending)
    to produce a human-readable target name for display in the step column.
    """
    if not fan_state:
        return None
    if fan_state.targets_remaining:
        return fan_state.targets_remaining[0]
    if fan_state.horizontal_breach_pending:
        return 'horizontal'
    return None


def _build_step(origin, target, fallback_origin=None, concurrent_targets=None):
    """Build a readable progression step string like '0.875->0.75'.

    For concurrent state (target is None), shows remaining targets in braces.
    Example: '0.5->horizontal' or 'horizontal->full_coverage'
    """
    o = origin or fallback_origin
    t = target
    if concurrent_targets is None:
        concurrent_targets = []

    if o and t and o != t:
        return f"{o}->{t}"
    if t:
        return f"->{t}"
    if o and concurrent_targets:
        remaining = '|'.join(concurrent_targets) if concurrent_targets else '?'
        return f"{o}->{{{remaining}}}"
    if o and not concurrent_targets:
        return f"{o}->..."
    if concurrent_targets:
        remaining = '|'.join(concurrent_targets)
        return f"->{{{remaining}}}"
    return "->..."


def _process_bar_events_model_a(bar_events, candles, bar_index, breached_setups, active_trades, trades,
                                live_mode=False, client=None, symbol=None, qty=None):
    """
    Model A (old): Generic breach+retest on any fraction. No sequence awareness.
    Enters on first retest of any breached line. Exits on TARGET_HIT/TARGET_FAILED.
    """
    close_applied = set()
    current_candle = candles[bar_index]

    for event in bar_events:
        evt_type = event.get("type", "")
        fan = event.get("fan", "")
        fan_id = event.get("fanIdentity", "")
        fraction = event.get("fraction", "")
        price = event.get("price", 0)
        evt_time = event.get("time", current_candle["time"])
        setup_key = f"{fan_id}|{fraction}"

        if evt_type in _BREACH_EVENTS:
            anchor_type = _anchor_type_from_fan(fan)
            if anchor_type == "high":
                side = "SHORT"
            elif anchor_type == "low":
                side = "LONG"
            else:
                continue
            if not fan_id or not fraction:
                continue
            breached_setups[setup_key] = {
                "fan": fan, "fan_id": fan_id, "anchor_type": anchor_type,
                "breach_fraction": fraction, "breach_price": price,
                "breach_time": evt_time, "breach_bar": bar_index,
                "side": side, "fraction": fraction,
            }

        elif evt_type in _RETEST_EVENTS:
            setup = breached_setups.get(setup_key)
            if not setup:
                continue
            if setup["fan_id"] in active_trades:
                continue
            side = setup["side"]
            entry = dict(setup)
            entry["entry_price"] = price
            entry["entry_time"] = evt_time
            entry["entry_bar"] = bar_index
            entry["retest_type"] = evt_type
            if live_mode:
                try:
                    binance_side = "BUY" if side == "LONG" else "SELL"
                    order = client.place_market_order(symbol, binance_side, qty)
                    entry["order_id"] = order.get("orderId")
                    entry["fill_price"] = float(order.get("avgPrice", price))
                    print(f"  [ORDER-MODEL_A] {binance_side} {qty} {symbol} @ {entry['fill_price']:.2f} | id={order.get('orderId')}")
                except Exception as e:
                    print(f"  [ORDER ERROR] {binance_side} failed: {e}")
                    continue
            active_trades[setup["fan_id"]] = entry
            del breached_setups[setup_key]
            print(f"  [ENTRY-MODEL_A] [{side}] {fan} retest ({evt_type}) on {fraction} @ {price:.2f}")

        elif evt_type == 'FAN_DEACTIVATED':
            target_fan_id = fan_id
            trade = active_trades.get(target_fan_id)
            if trade and target_fan_id not in close_applied:
                close_applied.add(target_fan_id)
                trade = active_trades.pop(target_fan_id)
                _apply_close_event(
                    {'type': 'TARGET_FAILED', 'fan': fan, 'time': evt_time},
                    trade, candles, bar_index, current_candle['close'], '', live_mode, client, symbol, qty
                )
                trade['outcome'] = 'ABORTED'
                trade['abort_reason'] = 'FAN_INVALIDATED'
                trades.append(trade)
                
            # Find and remove any breached setups associated with this fan
            keys_to_remove = [k for k, v in breached_setups.items() if v.get('fan_id') == target_fan_id]
            for k in keys_to_remove:
                del breached_setups[k]

        elif evt_type in _CLOSE_EVENTS:
            target_fan_id = fan_id
            trade = active_trades.get(target_fan_id)
            if trade and target_fan_id not in close_applied:
                close_applied.add(target_fan_id)
                _apply_close_event(event, trade, candles, bar_index, price, fraction, live_mode, client, symbol, qty)
                trades.append(trade)
                del active_trades[target_fan_id]


def _print_summary(symbol, interval, candles, scale_ratio, all_events, trades, momentum_filter=False, unfiltered_trades=None):
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Symbol:           {symbol}")
    print(f"Interval:         {interval}")
    print(f"Candles:          {len(candles)}")
    print(f"Scale Ratio:      {scale_ratio:.4f}")
    print(f"Total Events:     {len(all_events)}")
    print()
    breach_events = sum(1 for e in all_events if e.get("type") == "BREACH_CONFIRMED")
    target_hits = sum(1 for e in all_events if e.get("type") == "TARGET_HIT")
    target_fails = sum(1 for e in all_events if e.get("type") == "TARGET_FAILED")
    print(f"BREACH_CONFIRMED: {breach_events}")
    print(f"TARGET_HIT:       {target_hits}")
    print(f"TARGET_FAILED:    {target_fails}")
    print()
    print(f"Total Trades:     {len(trades)}")
    wins = [t for t in trades if t["outcome"] == "WIN"]
    losses = [t for t in trades if t["outcome"] == "LOSS"]
    open_trades = [t for t in trades if t["outcome"] == "OPEN"]
    if wins or losses:
        closed = wins + losses
        win_rate = len(wins) / len(closed) * 100 if closed else 0
        print(f"Closed Trades:    {len(closed)} (WIN: {len(wins)}, LOSS: {len(losses)})")
        print(f"Win Rate:         {win_rate:.1f}%")
        print(f"Open Trades:      {len(open_trades)}")
        if wins:
            print(f"Avg Win PnL:      {sum(t['pnl'] for t in wins) / len(wins):+.4f}")
        if losses:
            print(f"Avg Loss PnL:     {sum(t['pnl'] for t in losses) / len(losses):+.4f}")
        if wins and losses:
            pf = abs(sum(t["pnl"] for t in wins) / sum(t["pnl"] for t in losses)) if sum(t["pnl"] for t in losses) != 0 else float("inf")
            print(f"Profit Factor:    {pf:.2f}")
            print(f"Total PnL:        {sum(t['pnl'] for t in closed):+.4f}")

    if momentum_filter and unfiltered_trades:
        print()
        print("-" * 40)
        print("MOMENTUM FILTER COMPARISON")
        print("-" * 40)
        all_closed = [t for t in trades if t.get("outcome") != "OPEN"] + [t for t in unfiltered_trades if t.get("outcome") != "OPEN"]
        all_wins = [t for t in all_closed if t.get("outcome") == "WIN"]
        all_losses = [t for t in all_closed if t.get("outcome") == "LOSS"]
        all_rate = len(all_wins) / len(all_closed) * 100 if all_closed else 0

        filt_wins = [t for t in trades if t.get("outcome") == "WIN"]
        filt_losses = [t for t in trades if t.get("outcome") == "LOSS"]
        filt_closed = filt_wins + filt_losses
        filt_rate = len(filt_wins) / len(filt_closed) * 100 if filt_closed else 0

        filtered_out_closed = [t for t in unfiltered_trades if t.get("outcome") != "OPEN"]
        filtered_out_wins = [t for t in filtered_out_closed if t.get("outcome") == "WIN"]
        filtered_out_losses = [t for t in filtered_out_closed if t.get("outcome") == "LOSS"]
        filtered_out_rate = len(filtered_out_wins) / len(filtered_out_closed) * 100 if filtered_out_closed else 0

        print(f"  ALL POTENTIAL (unfiltered): {len(all_closed):>3} trades | WR: {all_rate:>5.1f}% | PnL: {sum(t.get('pnl', 0) for t in all_closed):>+8.4f}")
        print(f"  Momentum-filtered (entered): {len(filt_closed):>3} trades | WR: {filt_rate:>5.1f}% | PnL: {sum(t.get('pnl', 0) for t in filt_closed):>+8.4f}")
        print(f"  Filtered OUT (skipped):      {len(filtered_out_closed):>3} trades | WR: {filtered_out_rate:>5.1f}% | PnL: {sum(t.get('pnl', 0) for t in filtered_out_closed):>+8.4f}")
        breach_mom_counts = {"momentum": 0, "exhaustion": 0, "neutral": 0}
        for t in all_closed:
            st = t.get("momentum_state", "neutral")
            breach_mom_counts[st] = breach_mom_counts.get(st, 0) + 1
        print(f"  Breach Momentum: M={breach_mom_counts['momentum']} E={breach_mom_counts['exhaustion']} N={breach_mom_counts['neutral']}")

    print()
    print("=" * 60)


def _print_mode_summary(mode_label, trades):
    """Print summary for a single mode."""
    closed = [t for t in trades if 'outcome' in t and t.get('outcome') != 'OPEN']
    wins = [t for t in closed if t.get('outcome') == 'WIN']
    losses = [t for t in closed if t.get('outcome') == 'LOSS']
    total_pnl = sum(t.get('pnl', 0) for t in closed)
    wr = (len(wins) / len(closed) * 100) if closed else 0
    avg_win = statistics.mean([t['pnl'] for t in wins]) if wins else 0
    avg_loss = statistics.mean([t['pnl'] for t in losses]) if losses else 0
    gross_profit = sum(t['pnl'] for t in wins) if wins else 0
    gross_loss = abs(sum(t['pnl'] for t in losses)) if losses else 0
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    print(f"\n=== {mode_label} ===")
    print(f"Trades: {len(closed)} | WR: {wr:.1f}% | PF: {pf:.2f} | Total PnL: {total_pnl:+.2f}")
    print(f"Avg Win: {avg_win:+.2f} | Avg Loss: {avg_loss:+.2f}")

    steps = {}
    for t in closed:
        step = t.get('progression_step', 'generic')
        if step not in steps:
            steps[step] = {'trades': 0, 'wins': 0, 'pnl': 0.0}
        steps[step]['trades'] += 1
        if t.get('outcome') == 'WIN':
            steps[step]['wins'] += 1
        steps[step]['pnl'] += t.get('pnl', 0)
    for step, stats in sorted(steps.items()):
        swr = (stats['wins'] / stats['trades'] * 100) if stats['trades'] > 0 else 0
        print(f"  {step}: {stats['trades']} trades, {swr:.1f}% WR, {stats['pnl']:+.2f}")

    return {'trades': len(closed), 'wr': wr, 'pf': pf, 'total_pnl': total_pnl}


def run_replay(symbol, interval, from_date, to_date, warmup_days, client, momentum_filter=False):
    print(f"=== Target Progression Replay ===")
    print(f"Symbol: {symbol}  Interval: {interval}  From: {from_date} To: {to_date} Warmup: {warmup_days} days")
    if momentum_filter:
        print(f"Momentum Filter:  ENABLED (only enter if breach momentum == 'momentum')")
    print()

    from datetime import timezone
    from_dt = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    to_dt = datetime.strptime(to_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    
    warmup_from_dt = from_dt - timedelta(days=warmup_days)
    
    start_ms = int(warmup_from_dt.timestamp() * 1000)
    end_ms = int(to_dt.timestamp() * 1000)
    execution_start_ts = int(from_dt.timestamp())

    print(f"Fetching candles from {warmup_from_dt.strftime('%Y-%m-%d')} to {to_dt.strftime('%Y-%m-%d')}...")
    raw_candles = client.fetch_klines_range(symbol, interval, start_ms, end_ms)
    if not raw_candles:
        print("ERROR: No candles returned.")
        return
    print(f"Fetched {len(raw_candles)} candles.")

    candles = [_candle_to_dict(c) for c in raw_candles]

    start_ts = datetime.fromtimestamp(candles[0]["time"])
    end_ts = datetime.fromtimestamp(candles[-1]["time"])
    print(f"Range: {start_ts} --> {end_ts}")

    scale_ratio = _load_ticker_scale_ratio(symbol, interval) or compute_scale_ratio(candles, interval)
    print(f"Scale ratio: {scale_ratio:.4f}")

    study = AngularPriceCoverageStudy(config={
        "scale_ratio": scale_ratio, "left_bars": 5, "right_bars": 5,
        "symbol": symbol, "resolution": interval,
    })

    min_warmup = study.config["left_bars"] + study.config["right_bars"] + 1
    
    start_index = 0
    for i, c in enumerate(candles):
        if int(c['time']) >= execution_start_ts:
            start_index = i
            break
            
    warmup_end = max(min_warmup, start_index)
    print(f"Warmup: {warmup_end} bars (min required: {min_warmup})")
    study.initialize_history(candles[:warmup_end])
    study._initialized = True
    print(f"Initialized. Pivots: {len(study.pivot_detector.confirmed_pivots)}")

    all_events = []

    tracker = BounceRejectionTracker({
        'bounce_threshold_percent': 0.3,
        'rejection_lookback_bars': 5,
        'rest_tolerance_percent': 0.15,
        'rest_required_bars': 3
    })

    entry_modes = ['retest_baseline', 'breach_immediate', 'retest_momentum']
    mode_trades = {mode: [] for mode in entry_modes}
    mode_active = {mode: {} for mode in entry_modes}
    mode_breached = {mode: {} for mode in entry_modes}
    mode_skipped_retests = {mode: [] for mode in entry_modes}

    model_a_active = {}
    model_a_breached = {}
    model_a_trades = []

    for i in range(warmup_end, len(candles)):
        result = study.process_bar(candles, i, state=None)
        bar_events = result.get("intersection_events", []) if result else []
        for e in bar_events:
            all_events.append(e)

        tracker_results = tracker.process_bar(
            candles[i], i, bar_events, study.angle_engine.active_fans if study else {}
        )

        for mode in entry_modes:
            _process_bar_events(bar_events, candles, i, mode_breached[mode], mode_active[mode], mode_trades[mode],
                                live_mode=False, client=None, symbol=symbol, qty=0,
                                momentum_filter=False, unfiltered_trades=None,
                                unfiltered_active_trades=None,
                                study=study, entry_mode=mode, tracker_results=tracker_results)

        _process_bar_events_model_a(bar_events, candles, i, model_a_breached, model_a_active, model_a_trades,
                                    live_mode=False, client=None, symbol=symbol, qty=None)

        for mode in entry_modes:
            for fan_id, trade in mode_active[mode].items():
                if 'fan_geometry' not in trade:
                    trade['fan_geometry'] = _capture_fan_geometry(study, fan_id)

    for mode in entry_modes:
        for trade in mode_active[mode].values():
            trade["outcome"] = "OPEN"
            trade["exit_price"] = candles[-1]["close"]
            trade["exit_time"] = candles[-1]["time"]
            trade["exit_bar"] = len(candles) - 1
            trade["pnl"] = trade["exit_price"] - trade["entry_price"] if trade["side"] == "LONG" else trade["entry_price"] - trade["exit_price"]
            mode_trades[mode].append(trade)

    for trade in model_a_active.values():
        trade["outcome"] = "OPEN"
        trade["exit_price"] = candles[-1]["close"]
        trade["exit_time"] = candles[-1]["time"]
        trade["exit_bar"] = len(candles) - 1
        trade["pnl"] = trade["exit_price"] - trade["entry_price"] if trade["side"] == "LONG" else trade["entry_price"] - trade["exit_price"]
        model_a_trades.append(trade)

    for mode in entry_modes:
        for trade in mode_trades[mode]:
            if 'fan_geometry' not in trade and trade.get('fan_id'):
                trade['fan_geometry'] = _capture_fan_geometry(study, trade['fan_id'])

    for trade in model_a_trades:
        if 'fan_geometry' not in trade and trade.get('fan_id'):
            trade['fan_geometry'] = _capture_fan_geometry(study, trade['fan_id'])

    print("\n" + "=" * 60)
    print("ALL-MODE COMPARISON")
    print("=" * 60)

    _print_mode_summary("Model A (Generic Breach+Retest)", model_a_trades)

    mode_labels = {
        'retest_baseline': 'Model B / Mode 1: Retest-only baseline',
        'breach_immediate': 'Model B / Mode 2: Post-breach immediate + retest',
        'retest_momentum': 'Model B / Mode 3: Post-breach immediate + momentum-gated retest',
    }
    for mode in entry_modes:
        _print_mode_summary(mode_labels[mode], mode_trades[mode])

    print()
    print("=" * 60)

    output = {
        'symbol': symbol,
        'interval': interval,
        'bars': len(candles),
        'modes': {
            mode: [t for t in mode_trades[mode] if 'outcome' in t]
            for mode in entry_modes
        },
        'model_a': [t for t in model_a_trades if 'outcome' in t],
    }
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(base_dir, f'strategy_trades_{symbol}_{interval}.json')
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nTrades written to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Target Progression Strategy on Binance Testnet")
    parser.add_argument("symbol", default="BTCUSDT", nargs="?", help="Trading pair (default: BTCUSDT)")
    parser.add_argument("interval", default="1h", nargs="?", help="Kline interval (default: 1h)")
    parser.add_argument("--from-date", type=str, required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to-date", type=str, required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--warmup-days", type=int, default=0, help="Days of history to fetch before from-date (default: 0)")
    parser.add_argument("--momentum-filter", action="store_true", dest="momentum_filter",
                        help="Only enter on retest if breach momentum was 'momentum' (not exhaustion/neutral)")
    parser.add_argument('--target-progression', action='store_true',
                        help='Run Model B (target progression sequential) alongside Model A for comparison')
    args = parser.parse_args()

    client = BinanceClient(use_testnet=True)

    run_replay(args.symbol.upper(), args.interval, args.from_date, args.to_date, args.warmup_days, client, momentum_filter=args.momentum_filter)


if __name__ == "__main__":
    main()
