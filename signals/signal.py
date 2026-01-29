from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4


SignalDirection = Literal["LONG", "SHORT", "FLAT"]
VolatilityRegime = Literal["high", "normal", "low"]


@dataclass(frozen=True)
class Signal:
    symbol: str
    direction: SignalDirection
    confidence: float
    horizon: str
    volatility_regime: VolatilityRegime
    metadata: dict
    signal_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")
