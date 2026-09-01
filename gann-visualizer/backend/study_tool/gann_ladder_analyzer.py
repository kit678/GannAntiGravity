"""
Gann Ladder Analyzer - records price/level interactions bar by bar.

Shaped like BreachAnalyzer: built from a config dict, fed one bar at a time,
holding explicit serialisable state so a long walk can be checkpointed.

This module records. It does not predict. The held/failed classification it
applies is a DEFAULT sitting on top of raw measurements that are all retained,
so Phase 3 can recompute the outcome under any other threshold.
"""

from typing import Any, Dict, List, Optional

from study_tool.event_logger import Event, EventType


class GannLadderAnalyzer:
    """Turns bars plus a level ladder into a stream of interaction events."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.breach_mode = config.get("breach_mode", "close")
        self.confirmation_closes = config.get("confirmation_closes", 2)
        self.touch_tolerance = config.get("touch_tolerance_sublevels", 0.1)
        self.resolution_window = config.get("resolution_window_bars", 50)
        self.retest_window = config.get("retest_window_bars", 50)
        self.instrument = config.get("instrument")
        self.timeframe = config.get("timeframe")
        self.price_scale = config.get("price_scale", 1)

        # level_price -> pending cross state
        self.pending: Dict[float, Dict[str, Any]] = {}
        # breach_id -> open breach state
        self.open_breaches: Dict[str, Dict[str, Any]] = {}

    # -- helpers ---------------------------------------------------------

    def _sub_gap(self, level: Dict) -> float:
        """Price distance between adjacent sub-levels of a level's segment."""
        start = level.get("segment_start")
        end = level.get("segment_end")
        if start is None or end is None or end == start:
            return 1.0
        return abs(end - start) / 8.0

    def _make_event(self, event_type, bar, bar_index, level,
                    direction=None, details=None, breach_id=None,
                    parent_breach_id=None) -> Event:
        return Event(
            timestamp=bar.get("timestamp", bar_index),
            event_type=event_type,
            price=bar.get("close"),
            direction=direction,
            details=details or {},
            bar_index=bar_index,
            open_price=bar.get("open"),
            high_price=bar.get("high"),
            low_price=bar.get("low"),
            close_price=bar.get("close"),
            instrument=self.instrument,
            timeframe=self.timeframe,
            level_source=level.get("source"),
            level_price=level.get("price"),
            level_square=level.get("square"),
            level_kind=level.get("kind"),
            level_degree=level.get("degree"),
            level_ring=level.get("ring"),
            level_sub_index=level.get("sub_index"),
            level_is_halfway=level.get("is_halfway"),
            level_segment_start=level.get("segment_start"),
            level_segment_end=level.get("segment_end"),
            price_scale=self.price_scale,
            breach_id=breach_id,
            parent_breach_id=parent_breach_id,
        )

    def _breach_id(self, level: Dict, bar_index: int) -> str:
        return ":".join(str(part) for part in (
            self.instrument, self.timeframe, self.price_scale,
            level.get("source"), level.get("square"), bar_index,
        ))

    # -- main loop -------------------------------------------------------

    def process_bar(self, bar: Dict, bar_index: int,
                    levels: List[Dict]) -> List[Event]:
        """
        Feed one bar. Returns the events it produced.

        Pure with respect to its inputs: the same bar plus the same state in
        gives the same events out.
        """
        events: List[Event] = []
        high, low, close = bar["high"], bar["low"], bar["close"]

        for level in levels:
            price = level["price"]
            gap = self._sub_gap(level)
            tolerance = gap * self.touch_tolerance

            reached = (low - tolerance) <= price <= (high + tolerance)
            beyond_up = close > price
            beyond_down = close < price

            state = self.pending.get(price)

            if state is None:
                if not reached:
                    continue
                # Wick mode confirms as soon as the range clears the level.
                crossed = high > price or low < price
                if self.breach_mode == "wick" and crossed:
                    direction = "up" if high > price else "down"
                    if self.confirmation_closes <= 1:
                        events.append(self._confirm(bar, bar_index, level, direction))
                        continue
                # A genuine cross needs the bar to have travelled through the
                # level (open on one side, close on the other) — not merely
                # closed on the far side of a level it was already past, or
                # rested on one side while a wick tagged it exactly.
                open_price = bar.get("open")
                straddled_up = open_price is not None and open_price <= price and beyond_up
                straddled_down = open_price is not None and open_price >= price and beyond_down
                if (self.breach_mode == "close" and (straddled_up or straddled_down)):
                    direction = "up" if straddled_up else "down"
                    self.pending[price] = {
                        "direction": direction,
                        "closes": 1,
                        "first_bar": bar_index,
                    }
                    events.append(self._make_event(
                        EventType.LADDER_CROSS, bar, bar_index, level,
                        direction=direction,
                    ))
                    if self.confirmation_closes <= 1:
                        events.append(self._confirm(bar, bar_index, level, direction))
                        self.pending.pop(price, None)
                else:
                    events.append(self._make_event(
                        EventType.LADDER_TOUCH, bar, bar_index, level,
                    ))
                continue

            # A cross is pending on this level.
            direction = state["direction"]
            still_beyond = beyond_up if direction == "up" else beyond_down
            if still_beyond:
                state["closes"] += 1
                if state["closes"] >= self.confirmation_closes:
                    events.append(self._confirm(bar, bar_index, level, direction))
                    self.pending.pop(price, None)
            else:
                events.append(self._make_event(
                    EventType.LADDER_BREACH_REJECTED, bar, bar_index, level,
                    direction=direction,
                ))
                events.append(self._make_event(
                    EventType.LADDER_BREACH_RESOLVED, bar, bar_index, level,
                    direction=direction,
                    details={"outcome": "NEVER_CONFIRMED", "truncated": False},
                ))
                self.pending.pop(price, None)

        events.extend(self._track_open_breaches(bar, bar_index))
        return events

    def _confirm(self, bar, bar_index, level, direction) -> Event:
        breach_id = self._breach_id(level, bar_index)
        self.open_breaches[breach_id] = {
            "level": level,
            "direction": direction,
            "bar": bar_index,
            "extreme": bar["high"] if direction == "up" else bar["low"],
            "retested": False,
            "closes_back": 0,
        }
        return self._make_event(
            EventType.LADDER_BREACH_CONFIRMED, bar, bar_index, level,
            direction=direction, breach_id=breach_id,
        )

    def _track_open_breaches(self, bar: Dict, bar_index: int) -> List[Event]:
        """Watch for retests and assign terminal outcomes."""
        events: List[Event] = []
        high, low, close = bar["high"], bar["low"], bar["close"]

        for breach_id in list(self.open_breaches):
            state = self.open_breaches[breach_id]
            if bar_index <= state["bar"]:
                continue

            level = state["level"]
            price = level["price"]
            direction = state["direction"]
            gap = self._sub_gap(level)
            elapsed = bar_index - state["bar"]

            if direction == "up":
                state["extreme"] = max(state["extreme"], high)
                came_back = low <= price + gap
                depth = (price - low) / gap
                crossed_back = close < price
            else:
                state["extreme"] = min(state["extreme"], low)
                came_back = high >= price - gap
                depth = (high - price) / gap
                crossed_back = close > price

            if came_back and not state["retested"]:
                state["retested"] = True
                state["retest_bar"] = bar_index
                if crossed_back:
                    state["closes_back"] += 1
                events.append(self._make_event(
                    EventType.LADDER_RETEST, bar, bar_index, level,
                    direction=direction,
                    parent_breach_id=breach_id,
                    details={
                        "bars_since_breach": elapsed,
                        "retest_extreme": low if direction == "up" else high,
                        "depth_in_sublevels": round(depth, 4),
                        "crossed_back": crossed_back,
                        "closes_beyond": state["closes_back"],
                    },
                ))
            elif state["retested"] and crossed_back:
                state["closes_back"] += 1

            if elapsed >= self.resolution_window:
                events.append(self._resolve(bar, bar_index, breach_id))

        return events

    def _resolve(self, bar, bar_index, breach_id) -> Event:
        state = self.open_breaches.pop(breach_id)
        level = state["level"]

        if not state["retested"]:
            outcome = "NEVER_RETESTED"
        elif state["closes_back"] >= 2:
            outcome = "RETEST_FAILED"
        else:
            outcome = "RETEST_HELD"

        return self._make_event(
            EventType.LADDER_BREACH_RESOLVED, bar, bar_index, level,
            direction=state["direction"],
            parent_breach_id=breach_id,
            details={
                "outcome": outcome,
                "truncated": False,
                "retested": state["retested"],
                "closes_back": state["closes_back"],
            },
        )

    def finalize(self) -> List[Event]:
        """
        Close out breaches still open at the end of the data.

        Emitted with outcome None rather than dropped: truncation is a fact
        about the dataset, not a reason to discard a sample.
        """
        events: List[Event] = []
        for breach_id in list(self.open_breaches):
            state = self.open_breaches.pop(breach_id)
            level = state["level"]
            events.append(Event(
                timestamp=0,
                event_type=EventType.LADDER_BREACH_RESOLVED,
                direction=state["direction"],
                bar_index=state["bar"],
                instrument=self.instrument,
                timeframe=self.timeframe,
                level_source=level.get("source"),
                level_price=level.get("price"),
                level_square=level.get("square"),
                level_kind=level.get("kind"),
                level_degree=level.get("degree"),
                level_ring=level.get("ring"),
                price_scale=self.price_scale,
                parent_breach_id=breach_id,
                details={
                    "outcome": None,
                    "truncated": True,
                    "retested": state["retested"],
                },
            ))
        return events

    # -- checkpointing ---------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        return {
            "pending": {str(k): v for k, v in self.pending.items()},
            "open_breaches": self.open_breaches,
        }

    def restore_state(self, state: Dict[str, Any]) -> None:
        self.pending = {float(k): v for k, v in state.get("pending", {}).items()}
        self.open_breaches = state.get("open_breaches", {})
