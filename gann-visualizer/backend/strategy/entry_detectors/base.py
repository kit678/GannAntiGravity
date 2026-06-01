from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from study_tool.event_pipeline import PriceInteractionEvent
from analysis.target_progression import TargetProgression


@dataclass
class MomentumContext:
    state: str
    adx: float
    rsi: float
    rsi_divergence: Optional[str] = None
    macd_histogram_slope: float = 0.0


@dataclass
class BarContext:
    candles: List[Dict[str, Any]]
    bar_index: int
    atr: float
    momentum: MomentumContext
    progression: TargetProgression
    breached_setups: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class EntrySignal:
    detector_name: str
    fan_id: str
    fan_identity: str
    priority_label: str
    side: str
    entry_price: float
    stop_price: float
    target: str
    entry_path: str
    fraction: str
    momentum: Optional[MomentumContext] = None
    anchor_type: str = ""


class EntryDetector(ABC):
    @abstractmethod
    def detect(
        self,
        event: PriceInteractionEvent,
        context: BarContext,
    ) -> Optional[EntrySignal]:
        ...
