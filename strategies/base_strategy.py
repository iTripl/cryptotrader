from __future__ import annotations

import multiprocessing as mp
from dataclasses import dataclass
from typing import Iterable

from config.config_schema import AppConfig
from data.schemas import Candle
from signals.signal import Signal


class Strategy:
    name: str = "base"
    auto_load_data: bool = True
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
    auto_load: bool


def strategy_worker(
    strategy: Strategy,
    input_queue: mp.Queue[Candle],
    output_queue: mp.Queue[Signal],
    config: "AppConfig | None",
    auto_load: bool,
) -> None:
    if auto_load:
        if config is None:
            raise ValueError("Config required for auto-load strategies")
        from app.container import Container
        from app.mode_runner import ModeRunner
        from data.storage.parquet_reader import ParquetReader
        from utils.logger import get_logger

        logger = get_logger(f"strategies.{strategy.name}")
        container = Container(config)
        runner = ModeRunner(config, ParquetReader(config.paths.data_dir), container.data_auto_loader())
        for candle in runner.stream():
            for signal in strategy.on_candle(candle):
                output_queue.put(signal)
        logger.info("strategy data stream completed")
        return

    while True:
        candle = input_queue.get()
        if candle is None:
            break
        for signal in strategy.on_candle(candle):
            output_queue.put(signal)
