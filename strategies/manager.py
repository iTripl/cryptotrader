from __future__ import annotations

import multiprocessing as mp
import time
from queue import Empty
from typing import Iterable

from data.schemas import Candle
from signals.signal import Signal
from strategies.base_strategy import Strategy, StrategyProcess, strategy_worker
from utils.logger import get_logger


logger = get_logger("strategies.manager")


class StrategyManager:
    def __init__(self, strategies: Iterable[Strategy], timeout_seconds: float = 0.25) -> None:
        self._strategies = list(strategies)
        self._strategy_by_name = {strategy.name: strategy for strategy in self._strategies}
        self._processes: list[StrategyProcess] = []
        self._timeout_seconds = timeout_seconds

    def start(self) -> None:
        for strategy in self._strategies:
            self._processes.append(self._spawn(strategy))

    def _spawn(self, strategy: Strategy) -> StrategyProcess:
        input_queue: mp.Queue[Candle] = mp.Queue()
        output_queue: mp.Queue = mp.Queue()
        process = mp.Process(
            target=strategy_worker,
            args=(strategy, input_queue, output_queue),
            name=f"strategy-{strategy.name}",
            daemon=True,
        )
        process.start()
        logger.info("started strategy %s", strategy.name)
        return StrategyProcess(
            name=strategy.name,
            process=process,
            input_queue=input_queue,
            output_queue=output_queue,
        )

    def stop(self) -> None:
        for proc in self._processes:
            proc.input_queue.put(None)
            proc.process.join(timeout=3)
            if proc.process.is_alive():
                proc.process.terminate()
            logger.info("stopped strategy %s", proc.name)
        self._processes.clear()

    def broadcast_candle(self, candle: Candle) -> None:
        logger.debug(
            "broadcast candle %s %s ts=%s",
            candle.symbol,
            candle.timeframe,
            candle.timestamp,
        )
        for proc in self._processes:
            proc.input_queue.put(candle)

    def collect_signals(self) -> list:
        signals = []
        for proc in self._processes:
            while True:
                try:
                    signals.append(proc.output_queue.get_nowait())
                except Empty:
                    break
        return signals

    def local_signals(self, candle: Candle) -> list[Signal]:
        signals: list[Signal] = []
        for strategy in self._strategies:
            batch = list(strategy.on_candle(candle))
            logger.debug(
                "strategy %s processed candle %s %s signals=%d",
                strategy.name,
                candle.symbol,
                candle.timeframe,
                len(batch),
            )
            if batch:
                logger.info("strategy %s produced %d signals", strategy.name, len(batch))
            signals.extend(batch)
        return signals

    def healthcheck(self) -> dict[str, bool]:
        return {proc.name: proc.process.is_alive() for proc in self._processes}

    def restart_failed(self) -> None:
        failed = [proc for proc in self._processes if not proc.process.is_alive()]
        if not failed:
            return
        logger.warning("restarting failed strategies: %s", [p.name for p in failed])
        for proc in failed:
            if proc in self._processes:
                self._processes.remove(proc)
            proc.process.terminate()
        time.sleep(0.5)
        for proc in failed:
            strategy = self._strategy_by_name.get(proc.name)
            if strategy:
                self._processes.append(self._spawn(strategy))

    def on_candle(self, candle: Candle, timeout_seconds: float | None = None) -> list[Signal]:
        timeout_seconds = self._timeout_seconds if timeout_seconds is None else timeout_seconds
        self.broadcast_candle(candle)
        signals: list[Signal] = []
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            batch = self.collect_signals()
            if batch:
                signals.extend(batch)
            else:
                time.sleep(0.001)
        logger.debug(
            "signals collected for candle %s %s count=%d",
            candle.symbol,
            candle.timeframe,
            len(signals),
        )
        if signals:
            logger.info("strategies produced %d signals", len(signals))
        return signals
