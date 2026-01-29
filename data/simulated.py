from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable

from data.schemas import Candle
from utils.time import timeframe_to_seconds, utc_now_ts


@dataclass
class SyntheticDataSource:
    symbol: str
    timeframe: str
    exchange: str
    start_price: float = 30000.0
    steps: int = 100

    def stream(self) -> Iterable[Candle]:
        ts = utc_now_ts()
        price = self.start_price
        step = timeframe_to_seconds(self.timeframe)
        for _ in range(self.steps):
            drift = random.uniform(-0.001, 0.001)
            price = price * (1 + drift)
            candle = Candle(
                timestamp=ts,
                open=price * 0.999,
                high=price * 1.002,
                low=price * 0.998,
                close=price,
                volume=random.uniform(1, 10),
                symbol=self.symbol,
                timeframe=self.timeframe,
                exchange=self.exchange,
            )
            yield candle
            ts += step
