from __future__ import annotations

import random
from typing import Iterable

from data.schemas import Candle
from signals.signal import Signal
from strategies.base_strategy import Strategy
from strategies.params import require_float


def _float_param(params: dict[str, str], key: str, default: float) -> float:
    value = params.get(key)
    if value is None or value == "":
        return default
    return float(value)


def _int_param(params: dict[str, str], key: str, default: int) -> int:
    value = params.get(key)
    if value is None or value == "":
        return default
    return int(value)


def _str_param(params: dict[str, str], key: str, default: str) -> str:
    value = params.get(key)
    return value if value else default


def _split_symbols(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


class NoiseStrategy(Strategy):
    name = "noise"
    config_key = "noise"

    def __init__(self, config, params: dict[str, str]) -> None:
        super().__init__(config, params)
        self.signal_probability = max(0.0, min(1.0, _float_param(params, "signal_probability", 0.25)))
        raw_confidence = _float_param(params, "confidence", 0.02)
        self.confidence = max(0.01, min(1.0, raw_confidence))
        self.horizon = _str_param(params, "horizon", "1m")
        self.volatility_regime = _str_param(params, "volatility_regime", "low")
        self.cooldown_seconds = max(0, _int_param(params, "cooldown_seconds", 0))
        self.order_notional = require_float(params, "order_notional")
        self.min_quantity = _float_param(params, "min_quantity", 0.0)
        self.max_quantity = _float_param(params, "max_quantity", 0.0)
        self.min_notional = _float_param(params, "min_notional", 0.0)
        self.max_notional = _float_param(params, "max_notional", 0.0)
        raw_symbols = params.get("symbols")
        if raw_symbols:
            self.symbols = _split_symbols(raw_symbols)
        else:
            self.symbols = set(self.config.symbols.symbols)
        seed = params.get("seed")
        self._rng = random.Random(int(seed)) if seed is not None and seed != "" else random.Random()
        self._last_signal_ts: dict[str, int] = {}

    def on_candle(self, candle: Candle) -> Iterable[Signal]:
        if self.symbols and candle.symbol not in self.symbols:
            return []
        if candle.close <= 0:
            return []
        key = f"{candle.symbol}:{candle.timeframe}"
        last_ts = self._last_signal_ts.get(key, 0)
        if self.cooldown_seconds and candle.timestamp - last_ts < self.cooldown_seconds:
            return []
        if self._rng.random() >= self.signal_probability:
            return []
        direction = "LONG" if self._rng.random() < 0.5 else "SHORT"
        self._last_signal_ts[key] = candle.timestamp
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
                    "reason": "noise",
                    "force_execute": True,
                    "order_notional": self.order_notional,
                    "min_quantity": self.min_quantity,
                    "min_notional": self.min_notional or self.order_notional,
                    "max_notional": self.max_notional or self.order_notional,
                    "max_quantity": self.max_quantity,
                },
            )
        ]
