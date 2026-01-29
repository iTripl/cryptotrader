from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from data.schemas import Candle


@dataclass(frozen=True)
class FeatureVector:
    timestamp: int
    symbol: str
    timeframe: str
    exchange: str
    features: dict


class FeaturePipeline:
    def transform(self, candle: Candle) -> FeatureVector:
        return FeatureVector(
            timestamp=candle.timestamp,
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            exchange=candle.exchange,
            features={},
        )
