from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable

from data.schemas import Candle
from signals.signal import Signal
from strategies.base_strategy import Strategy
from strategies.params import require_float, require_int, require_str


@dataclass
class DonchianState:
    highs: Deque[float]
    lows: Deque[float]
    closes: Deque[float]
    last_state: str | None = None


class DonchianEnsembleTrendStrategy(Strategy):
    name = "donchian_trend"
    config_key = "donchian_trend"

    def __init__(self, config, params: dict[str, str]) -> None:
        super().__init__(config, params)
        lookbacks = params.get("lookbacks", "20,50,100")
        self.lookbacks = sorted({int(x.strip()) for x in lookbacks.split(",") if x.strip()})
        if not self.lookbacks:
            raise ValueError("lookbacks must contain at least one window")
        self.min_votes = require_int(params, "min_votes")
        self.confidence = require_float(params, "confidence")
        self.horizon = require_str(params, "horizon")
        self.volatility_regime = require_str(params, "volatility_regime")
        self._state: dict[str, DonchianState] = {}

    def on_candle(self, candle: Candle) -> Iterable[Signal]:
        key = f"{candle.symbol}:{candle.timeframe}"
        state = self._state.get(key)
        max_lookback = max(self.lookbacks)
        if state is None:
            state = DonchianState(
                highs=deque(maxlen=max_lookback),
                lows=deque(maxlen=max_lookback),
                closes=deque(maxlen=max_lookback),
            )
            self._state[key] = state

        state.highs.append(candle.high)
        state.lows.append(candle.low)
        state.closes.append(candle.close)
        if len(state.closes) < max_lookback:
            return []

        close = candle.close
        votes = 0
        for window in self.lookbacks:
            highs = list(state.highs)[-window:]
            lows = list(state.lows)[-window:]
            if close >= max(highs):
                votes += 1
            elif close <= min(lows):
                votes -= 1

        if votes >= self.min_votes:
            current = "long"
        elif votes <= -self.min_votes:
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
                    "lookbacks": self.lookbacks,
                    "votes": votes,
                },
            )
        ]
