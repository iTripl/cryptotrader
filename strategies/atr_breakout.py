from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable

from data.schemas import Candle
from signals.signal import Signal
from strategies.base_strategy import Strategy
from strategies.params import require_float, require_int, require_str


@dataclass
class AtrBreakoutState:
    highs: Deque[float]
    lows: Deque[float]
    closes: Deque[float]
    tr_values: Deque[float]
    last_state: str | None = None


class AtrBreakoutStrategy(Strategy):
    name = "atr_breakout"
    config_key = "atr_breakout"

    def __init__(self, config, params: dict[str, str]) -> None:
        super().__init__(config, params)
        self.breakout_lookback = require_int(params, "breakout_lookback")
        self.atr_period = require_int(params, "atr_period")
        self.atr_mult = require_float(params, "atr_mult")
        self.allow_short = params.get("allow_short", "false").lower() in {"1", "true", "yes", "y"}
        self.confidence = require_float(params, "confidence")
        self.horizon = require_str(params, "horizon")
        self.volatility_regime = require_str(params, "volatility_regime")
        if self.breakout_lookback <= 0:
            raise ValueError("breakout_lookback must be > 0")
        if self.atr_period <= 0:
            raise ValueError("atr_period must be > 0")
        if self.atr_mult < 0:
            raise ValueError("atr_mult must be >= 0")
        self._state: dict[str, AtrBreakoutState] = {}

    def on_candle(self, candle: Candle) -> Iterable[Signal]:
        key = f"{candle.symbol}:{candle.timeframe}"
        state = self._state.get(key)
        maxlen = max(self.breakout_lookback + 1, self.atr_period + 1)
        if state is None:
            state = AtrBreakoutState(
                highs=deque(maxlen=maxlen),
                lows=deque(maxlen=maxlen),
                closes=deque(maxlen=maxlen),
                tr_values=deque(maxlen=self.atr_period),
            )
            self._state[key] = state

        state.highs.append(candle.high)
        state.lows.append(candle.low)
        state.closes.append(candle.close)
        if len(state.closes) < 2:
            return []

        prev_close = list(state.closes)[-2]
        true_range = max(
            candle.high - candle.low,
            abs(candle.high - prev_close),
            abs(candle.low - prev_close),
        )
        state.tr_values.append(true_range)
        if len(state.tr_values) < self.atr_period:
            return []
        if len(state.highs) < self.breakout_lookback + 1:
            return []

        atr = sum(state.tr_values) / self.atr_period
        window_highs = list(state.highs)[-self.breakout_lookback - 1 : -1]
        window_lows = list(state.lows)[-self.breakout_lookback - 1 : -1]
        if not window_highs or not window_lows:
            return []

        upper = max(window_highs) + self.atr_mult * atr
        lower = min(window_lows) - self.atr_mult * atr

        if candle.close > upper:
            current = "long"
        elif candle.close < lower and self.allow_short:
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
                    "breakout_lookback": self.breakout_lookback,
                    "atr_period": self.atr_period,
                    "atr_mult": self.atr_mult,
                    "atr": atr,
                    "upper": upper,
                    "lower": lower,
                },
            )
        ]
