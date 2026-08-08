"""Per-session result object shared by both ORB variants."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Optional

from analysis.signal_trade_simulator import CandleSignal


@dataclass(frozen=True)
class OrbSignal:
    """Outcome of evaluating one trading session.

    Exactly one of ``signal`` or ``reason`` is set. A session that produced no
    trade always carries a reason, so the report can account for every session
    instead of quietly losing it.
    """

    session_date: date
    signal: Optional[CandleSignal] = None
    reason: Optional[str] = None
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (self.signal is not None) == bool(self.reason):
            raise ValueError(
                "OrbSignal must set exactly one of signal or reason, got "
                f"signal={self.signal!r} reason={self.reason!r}"
            )

    @property
    def triggered(self) -> bool:
        return self.signal is not None

    @classmethod
    def skipped(cls, session_date: date, reason: str, **diagnostics: Any) -> "OrbSignal":
        if not reason:
            raise ValueError("a skipped session must carry a reason")
        return cls(session_date=session_date, signal=None, reason=reason, diagnostics=diagnostics)

    @classmethod
    def fired(
        cls,
        session_date: date,
        signal: Optional[CandleSignal],
        **diagnostics: Any,
    ) -> "OrbSignal":
        if signal is None:
            raise ValueError("a fired session must carry a signal")
        return cls(session_date=session_date, signal=signal, reason=None, diagnostics=diagnostics)
