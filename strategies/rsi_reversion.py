from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable

from data.schemas import Candle
from signals.signal import Signal
from strategies.base_strategy import Strategy
from strategies.params import require_float, require_int, require_str


@dataclass
class RsiState:
    series: Deque[float]
    last_band: str | None = None


class RsiMeanReversionStrategy(Strategy):
    name = "rsi_reversion"
    config_key = "rsi_reversion"

    def __init__(self, config, params: dict[str, str]) -> None:
        super().__init__(config, params)
        self.period = require_int(params, "rsi_period")
        self.overbought = require_float(params, "overbought")
        self.oversold = require_float(params, "oversold")
        self.confidence = require_float(params, "confidence")
        self.horizon = require_str(params, "horizon")
        self.volatility_regime = require_str(params, "volatility_regime")
        self._state: dict[str, RsiState] = {}

    def on_candle(self, candle: Candle) -> Iterable[Signal]:
        key = f"{candle.symbol}:{candle.timeframe}"
        state = self._state.get(key)
        if state is None:
            state = RsiState(series=deque(maxlen=self.period + 1))
            self._state[key] = state

        state.series.append(candle.close)
        if len(state.series) < self.period + 1:
            return []

        rsi = self._rsi(state.series, self.period)
        if rsi is None:
            return []

        if rsi > self.overbought:
            band = "overbought"
        elif rsi < self.oversold:
            band = "oversold"
        else:
            band = "neutral"

        if state.last_band == band:
            return []
        state.last_band = band

        if band == "neutral":
            return []

        direction = "SHORT" if band == "overbought" else "LONG"
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
                    "rsi": rsi,
                    "overbought": self.overbought,
                    "oversold": self.oversold,
                },
            )
        ]

    @staticmethod
    def _rsi(series: Deque[float], period: int) -> float | None:
        if len(series) < period + 1:
            return None
        values = list(series)[-period - 1 :]
        gains = []
        losses = []
        for prev, curr in zip(values, values[1:]):
            diff = curr - prev
            if diff >= 0:
                gains.append(diff)
            else:
                losses.append(abs(diff))
        avg_gain = sum(gains) / period if gains else 0.0
        avg_loss = sum(losses) / period if losses else 0.0
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
