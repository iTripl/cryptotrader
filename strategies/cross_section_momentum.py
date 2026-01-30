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
        self._bar_counter: dict[str, int] = {}
        self._last_selected: dict[str, set[str]] = {}

    def on_candle(self, candle: Candle) -> Iterable[Signal]:
        key = f"{candle.symbol}:{candle.timeframe}"
        state = self._state.get(key)
        if state is None:
            state = MomentumState(series=deque(maxlen=self.lookback_bars + 1))
            self._state[key] = state

        state.series.append(candle.close)
        timeframe = candle.timeframe
        self._bar_counter[timeframe] = self._bar_counter.get(timeframe, 0) + 1

        states = self._states_for_timeframe(timeframe)
        if not states:
            return []
        expected_symbols = set(self.config.symbols.symbols)
        if expected_symbols and set(states.keys()) != expected_symbols:
            return []
        if not self._ready(states):
            return []

        if self._bar_counter[timeframe] % self.hold_bars != 0:
            return []

        momentums = self._compute_momentum(states)
        if not momentums:
            return []

        ranked = sorted(momentums.items(), key=lambda item: item[1][0], reverse=True)
        winners = {symbol for symbol, _ in ranked[: self.top_n]}
        losers = {symbol for symbol, _ in ranked[-self.top_n :]} if self.allow_short else set()

        signals: list[Signal] = []
        exit_symbols = self._last_selected.get(timeframe, set()) - winners - losers
        for symbol, (momentum, last_price) in ranked:
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
                        "price": last_price,
                        "momentum": momentum,
                        "winners": list(winners),
                    },
                )
            )
        self._last_selected[timeframe] = winners | losers
        return signals

    def _states_for_timeframe(self, timeframe: str) -> dict[str, MomentumState]:
        states: dict[str, MomentumState] = {}
        for key, state in self._state.items():
            symbol, state_tf = key.split(":")
            if state_tf == timeframe:
                states[symbol] = state
        return states

    def _ready(self, states: dict[str, MomentumState]) -> bool:
        for state in states.values():
            if len(state.series) < self.lookback_bars + 1:
                return False
        return True

    def _compute_momentum(self, states: dict[str, MomentumState]) -> dict[str, tuple[float, float]]:
        momentums: dict[str, tuple[float, float]] = {}
        for symbol, state in states.items():
            values = list(state.series)
            if len(values) < self.lookback_bars + 1:
                continue
            start = values[-self.lookback_bars - 1]
            end = values[-1]
            if start == 0:
                continue
            momentums[symbol] = ((end / start) - 1.0, end)
        return momentums
