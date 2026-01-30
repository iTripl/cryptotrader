from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable

from data.schemas import Candle
from signals.signal import Signal
from strategies.base_strategy import Strategy
from strategies.params import require_float, require_int, require_str


@dataclass
class LiquidityReversalState:
    closes: Deque[float]
    volumes: Deque[float]
    bar_index: int = 0
    last_signal_index: int | None = None


class LiquidityReversalStrategy(Strategy):
    name = "liquidity_reversal"
    config_key = "liquidity_reversal"

    def __init__(self, config, params: dict[str, str]) -> None:
        super().__init__(config, params)
        self.return_lookback = require_int(params, "return_lookback")
        self.volume_lookback = require_int(params, "volume_lookback")
        self.return_threshold = require_float(params, "return_threshold")
        self.volume_spike_ratio = require_float(params, "volume_spike_ratio")
        self.cooldown_bars = require_int(params, "cooldown_bars")
        self.allow_short = params.get("allow_short", "true").lower() in {"1", "true", "yes", "y"}
        self.confidence = require_float(params, "confidence")
        self.horizon = require_str(params, "horizon")
        self.volatility_regime = require_str(params, "volatility_regime")
        if self.return_lookback <= 0:
            raise ValueError("return_lookback must be > 0")
        if self.volume_lookback <= 0:
            raise ValueError("volume_lookback must be > 0")
        if self.return_threshold <= 0:
            raise ValueError("return_threshold must be > 0")
        if self.volume_spike_ratio <= 0:
            raise ValueError("volume_spike_ratio must be > 0")
        if self.cooldown_bars < 0:
            raise ValueError("cooldown_bars must be >= 0")
        self._state: dict[str, LiquidityReversalState] = {}

    def on_candle(self, candle: Candle) -> Iterable[Signal]:
        key = f"{candle.symbol}:{candle.timeframe}"
        state = self._state.get(key)
        if state is None:
            state = LiquidityReversalState(
                closes=deque(maxlen=max(self.return_lookback + 1, self.volume_lookback)),
                volumes=deque(maxlen=self.volume_lookback),
            )
            self._state[key] = state

        state.bar_index += 1
        state.closes.append(candle.close)
        state.volumes.append(candle.volume)
        if len(state.closes) < self.return_lookback + 1:
            return []
        if len(state.volumes) < self.volume_lookback:
            return []
        if state.last_signal_index is not None and state.bar_index - state.last_signal_index <= self.cooldown_bars:
            return []

        past_close = list(state.closes)[-self.return_lookback - 1]
        if past_close == 0:
            return []
        return_pct = (candle.close / past_close) - 1.0
        avg_volume = sum(state.volumes) / self.volume_lookback
        if avg_volume <= 0:
            return []
        volume_ratio = candle.volume / avg_volume

        if abs(return_pct) < self.return_threshold or volume_ratio < self.volume_spike_ratio:
            return []

        if return_pct > 0:
            if not self.allow_short:
                return []
            direction = "SHORT"
        else:
            direction = "LONG"

        state.last_signal_index = state.bar_index
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
                    "return_lookback": self.return_lookback,
                    "volume_lookback": self.volume_lookback,
                    "return_threshold": self.return_threshold,
                    "volume_spike_ratio": self.volume_spike_ratio,
                    "return_pct": return_pct,
                    "volume_ratio": volume_ratio,
                },
            )
        ]
