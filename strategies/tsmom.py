from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable

from data.schemas import Candle
from signals.signal import Signal
from strategies.base_strategy import Strategy
from strategies.params import require_float, require_int, require_str


@dataclass
class TsmomState:
    closes: Deque[float]
    volumes: Deque[float]
    last_state: str | None = None


class TimeSeriesMomentumStrategy(Strategy):
    name = "tsmom"
    config_key = "tsmom"

    def __init__(self, config, params: dict[str, str]) -> None:
        super().__init__(config, params)
        self.lookback_bars = require_int(params, "lookback_bars")
        self.min_momentum = require_float(params, "min_momentum")
        self.allow_short = params.get("allow_short", "false").lower() in {"1", "true", "yes", "y"}
        self.confidence = require_float(params, "confidence")
        self.horizon = require_str(params, "horizon")
        self.volatility_regime = require_str(params, "volatility_regime")
        if self.lookback_bars <= 0:
            raise ValueError("lookback_bars must be > 0")
        if self.min_momentum < 0:
            raise ValueError("min_momentum must be >= 0")
        self._state: dict[str, TsmomState] = {}

    def on_candle(self, candle: Candle) -> Iterable[Signal]:
        key = f"{candle.symbol}:{candle.timeframe}"
        state = self._state.get(key)
        if state is None:
            state = TsmomState(
                closes=deque(maxlen=self.lookback_bars + 1),
                volumes=deque(maxlen=self.lookback_bars + 1),
            )
            self._state[key] = state

        state.closes.append(candle.close)
        state.volumes.append(candle.volume)
        if len(state.closes) < self.lookback_bars + 1:
            return []

        window_closes = list(state.closes)[-self.lookback_bars - 1 :]
        window_volumes = list(state.volumes)[-self.lookback_bars :]
        avg_volume = sum(window_volumes) / self.lookback_bars if window_volumes else 0.0
        if avg_volume <= 0:
            return []

        weighted_return = 0.0
        for prev, curr, volume in zip(window_closes, window_closes[1:], window_volumes):
            if prev == 0:
                continue
            weighted_return += ((curr / prev) - 1.0) * (volume / avg_volume)
        momentum = weighted_return / self.lookback_bars

        if momentum >= self.min_momentum:
            current = "long"
        elif momentum <= -self.min_momentum and self.allow_short:
            current = "short"
        else:
            current = "flat"

        if state.last_state == current:
            return []
        state.last_state = current
        if current == "flat":
            return []

        direction = "LONG" if current == "long" else "SHORT"
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
                    "timeframe": candle.timeframe,
                    "lookback_bars": self.lookback_bars,
                    "min_momentum": self.min_momentum,
                    "momentum": momentum,
                    "avg_volume": avg_volume,
                },
            )
        ]
