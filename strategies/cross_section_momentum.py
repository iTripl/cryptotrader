from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable

from data.schemas import Candle
from signals.signal import Signal
from strategies.base_strategy import Strategy
from strategies.params import require_float, require_int, require_str


@dataclass
class MomentumState:
    series: Deque[float]


class CrossSectionMomentumStrategy(Strategy):
    name = "cross_section_momentum"
    config_key = "cross_section_momentum"

    def __init__(self, config, params: dict[str, str]) -> None:
        super().__init__(config, params)
        self.lookback_bars = require_int(params, "lookback_bars")
        self.hold_bars = require_int(params, "hold_bars")
        self.top_n = require_int(params, "top_n")
        self.allow_short = params.get("allow_short", "false").lower() in {"1", "true", "yes", "y"}
        self.confidence = require_float(params, "confidence")
        self.horizon = require_str(params, "horizon")
        self.volatility_regime = require_str(params, "volatility_regime")
        self._state: dict[str, MomentumState] = {}
        self._bar_counter = 0
        self._last_selected: set[str] = set()

    def on_candle(self, candle: Candle) -> Iterable[Signal]:
        key = f"{candle.symbol}:{candle.timeframe}"
        state = self._state.get(key)
        if state is None:
            state = MomentumState(series=deque(maxlen=self.lookback_bars + 1))
            self._state[key] = state

        state.series.append(candle.close)
        self._bar_counter += 1

        if not self._ready():
            return []

        if self._bar_counter % self.hold_bars != 0:
            return []

        momentums = self._compute_momentum()
        if not momentums:
            return []

        ranked = sorted(momentums.items(), key=lambda item: item[1], reverse=True)
        winners = {symbol for symbol, _ in ranked[: self.top_n]}
        losers = {symbol for symbol, _ in ranked[-self.top_n :]} if self.allow_short else set()

        signals: list[Signal] = []
        exit_symbols = self._last_selected - winners - losers
        for symbol, momentum in ranked:
            if symbol in winners:
                direction = "LONG"
            elif symbol in losers:
                direction = "SHORT"
            elif symbol in exit_symbols:
                direction = "FLAT"
            else:
                continue
            signals.append(
                Signal(
                    symbol=symbol,
                    direction=direction,
                    confidence=self.confidence,
                    horizon=self.horizon,
                    volatility_regime=self.volatility_regime,
                    metadata={
                        "strategy": self.name,
                        "timestamp": candle.timestamp,
                        "price": candle.close,
                        "momentum": momentum,
                        "winners": list(winners),
                    },
                )
            )
        self._last_selected = winners | losers
        return signals

    def _ready(self) -> bool:
        for state in self._state.values():
            if len(state.series) < self.lookback_bars + 1:
                return False
        return True

    def _compute_momentum(self) -> dict[str, float]:
        momentums: dict[str, float] = {}
        for key, state in self._state.items():
            symbol = key.split(":")[0]
            values = list(state.series)
            if len(values) < self.lookback_bars + 1:
                continue
            start = values[-self.lookback_bars - 1]
            end = values[-1]
            if start == 0:
                continue
            momentums[symbol] = (end / start) - 1.0
        return momentums
