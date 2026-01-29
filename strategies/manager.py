from __future__ import annotations

import multiprocessing as mp
import time
from queue import Empty
from typing import Iterable

from config.config_schema import AppConfig
from data.schemas import Candle
from signals.signal import Signal
from strategies.base_strategy import Strategy, StrategyProcess, strategy_worker
from utils.logger import get_logger


logger = get_logger("strategies.manager")


class StrategyManager:
    def __init__(self, strategies: Iterable[Strategy]) -> None:
        self._strategies = list(strategies)
        self._strategy_by_name = {strategy.name: strategy for strategy in self._strategies}
        self._processes: list[StrategyProcess] = []
        self._completed: set[str] = set()
        self._auto_load_enabled = any(s.auto_load_data for s in self._strategies)

    def start(self, config: AppConfig | None = None, force_auto_load: bool | None = None) -> None:
        self._auto_load_enabled = False
        for strategy in self._strategies:
            auto_load = strategy.auto_load_data if force_auto_load is None else force_auto_load
            self._processes.append(self._spawn(strategy, config, auto_load))
            if auto_load:
                self._auto_load_enabled = True

    def _spawn(self, strategy: Strategy, config: AppConfig | None, auto_load: bool) -> StrategyProcess:
        input_queue: mp.Queue[Candle] = mp.Queue()
        output_queue: mp.Queue = mp.Queue()
        process = mp.Process(
            target=strategy_worker,
            args=(strategy, input_queue, output_queue, config, auto_load),
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
            auto_load=auto_load,
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
            if batch:
                logger.info("strategy %s produced %d signals", strategy.name, len(batch))
            signals.extend(batch)
        return signals

    def healthcheck(self) -> dict[str, bool]:
        return {proc.name: proc.process.is_alive() for proc in self._processes}

    def restart_failed(self, config: AppConfig | None = None) -> None:
        failed = [
            proc
            for proc in self._processes
            if not proc.process.is_alive() and proc.name not in self._completed
        ]
        if not failed:
            return
        restart: list[StrategyProcess] = []
        for proc in failed:
            if proc.process.exitcode == 0 and proc.auto_load:
                self._completed.add(proc.name)
                continue
            restart.append(proc)
        if restart:
            logger.warning("restarting failed strategies: %s", [p.name for p in restart])
            for proc in restart:
                if proc in self._processes:
                    self._processes.remove(proc)
                proc.process.terminate()
            time.sleep(0.5)
            for proc in restart:
                strategy = self._strategy_by_name.get(proc.name)
                if strategy:
                    self._processes.append(self._spawn(strategy, config))

    def auto_load_enabled(self) -> bool:
        return self._auto_load_enabled

    def all_completed(self) -> bool:
        auto_load_names = {proc.name for proc in self._processes if proc.auto_load}
        if not auto_load_names:
            return False
        return auto_load_names.issubset(self._completed)
