from __future__ import annotations

import multiprocessing as mp
from dataclasses import dataclass
from typing import Iterable

from config.config_schema import AppConfig
from data.schemas import Candle
from signals.signal import Signal


class Strategy:
    name: str = "base"
    config_key: str = "base"

    def __init__(self, config: AppConfig, params: dict[str, str]) -> None:
        self.config = config
        self.params = params

    def on_candle(self, candle: Candle) -> Iterable[Signal]:
        raise NotImplementedError


class NoOpStrategy(Strategy):
    name = "noop"
    config_key = "noop"

    def on_candle(self, candle: Candle) -> Iterable[Signal]:
        return []


@dataclass
class StrategyProcess:
    name: str
    process: mp.Process
    input_queue: mp.Queue[Candle]
    output_queue: mp.Queue[Signal]


def strategy_worker(
    strategy: Strategy,
    input_queue: mp.Queue[Candle],
    output_queue: mp.Queue[Signal],
) -> None:
    try:
        while True:
            candle = input_queue.get()
            if candle is None:
                break
            for signal in strategy.on_candle(candle):
                output_queue.put(signal)
    except KeyboardInterrupt:
        return
