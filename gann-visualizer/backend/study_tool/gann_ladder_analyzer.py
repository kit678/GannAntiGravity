"""
Gann Ladder Analyzer - records price/level interactions bar by bar.

Shaped like BreachAnalyzer: built from a config dict, fed one bar at a time,
holding explicit serialisable state so a long walk can be checkpointed.

This module records. It does not predict. The held/failed classification it
applies is a DEFAULT sitting on top of raw measurements that are all retained,
so Phase 3 can recompute the outcome under any other threshold.
"""

from typing import Any, Dict, List, Optional, Tuple

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

        # level key ("source|square") -> pending cross state
        self.pending: Dict[str, Dict[str, Any]] = {}
        # breach_id -> open breach state
        self.open_breaches: Dict[str, Dict[str, Any]] = {}
        # level key -> breach_id of its currently open breach, if any. Lets a
        # level with an unresolved breach be skipped in the main loop instead
        # of starting a second, independent cycle on top of the one already
        # being tracked via open_breaches.
        self.open_by_level: Dict[str, str] = {}

        # Bars must be fed in strictly increasing bar_index order. -1 means
        # none processed yet.
        self._last_bar_index = -1

    # -- helpers ---------------------------------------------------------

    def _level_key(self, level: Dict) -> str:
        """
        Stable identity for a level.

        Price alone is not enough: two different crosses (e.g. Sun and Moon)
        can land on the same price, most notably at a conjunction, and must
        not be tracked as the same pending cross.
        """
        return f"{level.get('source')}|{level.get('square')}"

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

    def _crossed(self, price: float, open_price: Optional[float],
                 high: float, low: float, close: float,
                 direction_hint: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Whether this bar counts as crossing the level, and in which direction.

        In 'close' mode a cross requires the bar to have travelled through the
        level - opened on one side, closed on the other - not merely rested
        on one side, or wicked it without closing past it.

        In 'wick' mode any bar whose range clears the level counts, even if
        it closes back on the side it came from.

        direction_hint, when given, checks only whether the bar still counts
        as crossed in that specific direction - used once a cross is already
        pending, so a bar wicking or resting the wrong way doesn't reset or
        confuse the count.
        """
        if self.breach_mode == "wick":
            wicked_up = high > price
            wicked_down = low < price
            if direction_hint == "up":
                return wicked_up, "up"
            if direction_hint == "down":
                return wicked_down, "down"
            if wicked_up:
                return True, "up"
            if wicked_down:
                return True, "down"
            return False, None

        beyond_up = close > price
        beyond_down = close < price
        if direction_hint == "up":
            return beyond_up, "up"
        if direction_hint == "down":
            return beyond_down, "down"
        straddled_up = open_price is not None and open_price <= price and beyond_up
        straddled_down = open_price is not None and open_price >= price and beyond_down
        if straddled_up:
            return True, "up"
        if straddled_down:
            return True, "down"
        return False, None

    # -- main loop -------------------------------------------------------

    def process_bar(self, bar: Dict, bar_index: int,
                    levels: List[Dict]) -> List[Event]:
        """
        Feed one bar. Returns the events it produced.

        Pure with respect to its inputs: the same bar plus the same state in
        gives the same events out. bar_index must be strictly increasing
        across calls (including after restore_state) - a long walk that
        replays or skips backward would silently corrupt the close/retest
        counters, so this is enforced rather than left to the caller.
        """
        if bar_index <= self._last_bar_index:
            raise ValueError(
                f"process_bar called with bar_index={bar_index}, which is "
                f"not after the last processed bar_index={self._last_bar_index}. "
                "Bars must be fed in strictly increasing order."
            )
        self._last_bar_index = bar_index

        events: List[Event] = []
        high, low, close = bar["high"], bar["low"], bar["close"]
        open_price = bar.get("open")

        current_keys = {self._level_key(level) for level in levels}
        events.extend(self._expire_pending_not_in(current_keys, bar, bar_index))

        for level in levels:
            key = self._level_key(level)

            # An already-open, unresolved breach on this exact level is
            # tracked purely via _track_open_breaches (retest/resolution).
            # Starting a new touch/cross cycle for it here would double-count
            # the same price action as both a retest of the open breach and
            # the trigger of a second, independent one.
            if key in self.open_by_level:
                continue

            price = level["price"]
            gap = self._sub_gap(level)
            tolerance = gap * self.touch_tolerance
            reached = (low - tolerance) <= price <= (high + tolerance)

            state = self.pending.get(key)

            if state is None:
                if not reached:
                    continue
                crossed_now, direction = self._crossed(price, open_price, high, low, close)
                if not crossed_now:
                    events.append(self._make_event(
                        EventType.LADDER_TOUCH, bar, bar_index, level,
                    ))
                    continue
                self.pending[key] = {
                    "direction": direction,
                    "closes": 1,
                    "first_bar": bar_index,
                    "level": level,
                }
                events.append(self._make_event(
                    EventType.LADDER_CROSS, bar, bar_index, level,
                    direction=direction,
                ))
                if self.confirmation_closes <= 1:
                    events.append(self._confirm(bar, bar_index, level, direction, key))
                    self.pending.pop(key, None)
                continue

            # A cross is pending on this level - still crossed the same way?
            direction = state["direction"]
            still_crossed, _ = self._crossed(
                price, open_price, high, low, close, direction_hint=direction,
            )
            if still_crossed:
                state["closes"] += 1
                if state["closes"] >= self.confirmation_closes:
                    events.append(self._confirm(bar, bar_index, level, direction, key))
                    self.pending.pop(key, None)
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
                self.pending.pop(key, None)

        events.extend(self._track_open_breaches(bar, bar_index))
        return events

    def _expire_pending_not_in(self, current_keys, bar: Dict,
                                bar_index: int) -> List[Event]:
        """
        Resolve any pending cross whose level has dropped out of the current
        ladder (e.g. the Moon moved to a different square, so its old level
        no longer appears in `levels`).

        Without this, a stale pending entry sits forgotten under its
        (source, square) key until - possibly much later - an unrelated
        level happens to reuse that same key, and would wrongly inherit its
        accumulated close count. Expiring it here instead gives it a
        terminal event immediately and guarantees a fresh start for any
        future reuse of the key.
        """
        events: List[Event] = []
        for key in list(self.pending):
            if key in current_keys:
                continue
            state = self.pending.pop(key)
            level = state.get("level", {})
            events.append(self._make_event(
                EventType.LADDER_BREACH_RESOLVED, bar, bar_index, level,
                direction=state.get("direction"),
                details={
                    "outcome": None,
                    "truncated": True,
                    "reason": "level_left_ladder",
                },
            ))
        return events

    def _confirm(self, bar, bar_index, level, direction, key) -> Event:
        breach_id = self._breach_id(level, bar_index)
        self.open_breaches[breach_id] = {
            "level": level,
            "direction": direction,
            "bar": bar_index,
            "extreme": bar["high"] if direction == "up" else bar["low"],
            "retested": False,
            "closes_back": 0,
        }
        self.open_by_level[key] = breach_id
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
        key = self._level_key(level)
        if self.open_by_level.get(key) == breach_id:
            del self.open_by_level[key]

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
        Close out breaches and pending crosses still open at the end of the
        data.

        Emitted with outcome None rather than dropped: truncation is a fact
        about the dataset, not a reason to discard a sample. Routed through
        _make_event (with an empty stand-in bar) so the resolved event
        carries the same full level identity - including sub-level index,
        halfway flag, and segment bounds - as every other event in that
        breach's lineage, for consistent joining by breach_id.
        """
        events: List[Event] = []
        for breach_id in list(self.open_breaches):
            state = self.open_breaches.pop(breach_id)
            level = state["level"]
            key = self._level_key(level)
            if self.open_by_level.get(key) == breach_id:
                del self.open_by_level[key]
            events.append(self._make_event(
                EventType.LADDER_BREACH_RESOLVED, {}, state["bar"], level,
                direction=state["direction"],
                parent_breach_id=breach_id,
                details={
                    "outcome": None,
                    "truncated": True,
                    "retested": state["retested"],
                },
            ))
        for key in list(self.pending):
            state = self.pending.pop(key)
            level = state.get("level", {})
            events.append(self._make_event(
                EventType.LADDER_BREACH_RESOLVED, {}, state.get("first_bar", -1), level,
                direction=state.get("direction"),
                details={
                    "outcome": None,
                    "truncated": True,
                    "reason": "end_of_data",
                },
            ))
        return events

    # -- checkpointing ---------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        return {
            "pending": self.pending,
            "open_breaches": self.open_breaches,
            "open_by_level": self.open_by_level,
            "last_bar_index": self._last_bar_index,
        }

    def restore_state(self, state: Dict[str, Any]) -> None:
        self.pending = state.get("pending", {})
        self.open_breaches = state.get("open_breaches", {})
        self.open_by_level = state.get("open_by_level", {})
        self._last_bar_index = state.get("last_bar_index", -1)
