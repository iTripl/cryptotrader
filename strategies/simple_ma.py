from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable

from data.schemas import Candle
from signals.signal import Signal
from strategies.base_strategy import Strategy
from strategies.params import require_float, require_int, require_str


@dataclass
class MaState:
    series: Deque[float]
    last_state: str | None = None


class SimpleMovingAverageCrossStrategy(Strategy):
    name = "simple_ma"
    config_key = "simple_ma"

    def __init__(self, config, params: dict[str, str]) -> None:
        super().__init__(config, params)
        self.fast_window = require_int(params, "fast_window")
        self.slow_window = require_int(params, "slow_window")
        if self.fast_window <= 0 or self.slow_window <= 0:
            raise ValueError("MA windows must be > 0")
        if self.fast_window >= self.slow_window:
            raise ValueError("fast_window must be < slow_window")
        self.confidence = require_float(params, "confidence")
        self.horizon = require_str(params, "horizon")
        self.volatility_regime = require_str(params, "volatility_regime")
        self._state: dict[str, MaState] = {}

    def on_candle(self, candle: Candle) -> Iterable[Signal]:
        key = f"{candle.symbol}:{candle.timeframe}"
        state = self._state.get(key)
        if state is None:
            state = MaState(series=deque(maxlen=self.slow_window))
            self._state[key] = state

        state.series.append(candle.close)
        if len(state.series) < self.slow_window:
            return []

        fast = sum(list(state.series)[-self.fast_window :]) / self.fast_window
        slow = sum(state.series) / self.slow_window
        if fast > slow:
            current = "above"
        elif fast < slow:
            current = "below"
        else:
            current = "flat"

        if state.last_state is None:
            state.last_state = current
            return []

        if current == state.last_state:
            return []

        state.last_state = current
        if current == "flat":
            return []

        direction = "LONG" if current == "above" else "SHORT"
        return [
            Signal(
                symbol=candle.symbol,
                direction=direction,
                confidence=self.confidence,
                horizon=self.horizon,
                volatility_regime=self.volatility_regime,
                metadata={
                    "strategy": self.name,
                    "timestamp": candle.timestamp,
                    "price": candle.close,
                    "fast_window": self.fast_window,
                    "slow_window": self.slow_window,
                    "fast_ma": fast,
                    "slow_ma": slow,
                },
            )
        ]
