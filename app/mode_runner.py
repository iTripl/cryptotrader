from __future__ import annotations

from pathlib import Path
from typing import Iterable

from config.config_schema import AppConfig
from data.schemas import Candle
from data.simulated import SyntheticDataSource
from data.auto_loader import DataAutoLoader
from data.storage.parquet_reader import ParquetReader
from utils.logger import get_logger
from utils.time import timeframe_to_seconds, utc_now_ts


logger = get_logger("app.mode")


class ModeRunner:
    def __init__(self, config: AppConfig, reader: ParquetReader, auto_loader: DataAutoLoader | None = None) -> None:
        self.config = config
        self.reader = reader
        self.auto_loader = auto_loader

    def stream(self) -> Iterable[Candle]:
        if self.config.runtime.mode == "backtest":
            return self._backtest_stream()
        if self.config.runtime.mode == "forward":
            return self._forward_stream()
        if self.config.runtime.mode == "live":
            return self._live_stream()
        raise ValueError(f"Unsupported mode: {self.config.runtime.mode}")

    def _backtest_stream(self) -> Iterable[Candle]:
        if self.auto_loader:
            self.auto_loader.ensure_backtest_data()
        data_dir = Path(self.config.paths.data_dir) / "norm"
        parquet_files = []
        for symbol in self.config.symbols.symbols:
            for timeframe in self.config.symbols.timeframes:
                parquet_files.extend(list(data_dir.glob(f"{symbol}_{timeframe}_*.parquet")))
        if not parquet_files:
            logger.warning("no parquet data found, using synthetic stream")
            return self._synthetic_stream()
        logger.info("loading %d parquet files for backtest", len(parquet_files))
        candles: list[Candle] = []
        for path in parquet_files:
            candles.extend(self.reader.read(path))
        start_ts, end_ts = self._resolve_backtest_range()
        logger.info("backtest range filter %s -> %s", start_ts, end_ts)
        if start_ts or end_ts:
            candles = [
                candle
                for candle in candles
                if candle.timestamp >= start_ts and (end_ts is None or candle.timestamp <= end_ts)
            ]
        logger.info("backtest candles loaded: %d", len(candles))
        if not candles:
            raise RuntimeError("no backtest candles available after filtering")
        return sorted(candles, key=lambda c: c.timestamp)

    def _resolve_backtest_range(self) -> tuple[int, int | None]:
        if self.config.backtest.days_back > 0:
            end_ts = utc_now_ts()
            start_ts = end_ts - self.config.backtest.days_back * 86400
            return start_ts, end_ts
        start_ts = self.config.backtest.start_ts
        end_ts = self.config.backtest.end_ts or None
        return start_ts, end_ts

    def _forward_stream(self) -> Iterable[Candle]:
        if self.config.runtime.dry_run:
            return self._synthetic_stream()
        logger.warning("forward mode requires live data connector")
        return self._synthetic_stream()

    def _live_stream(self) -> Iterable[Candle]:
        if self.config.runtime.dry_run:
            return self._synthetic_stream()
        logger.warning("live mode requires exchange WS connector")
        return self._synthetic_stream()

    def _synthetic_stream(self) -> Iterable[Candle]:
        streams = []
        for symbol in self.config.symbols.symbols:
            for timeframe in self.config.symbols.timeframes:
                steps = self._synthetic_steps(timeframe)
                logger.info("synthetic stream %s %s steps=%d", symbol, timeframe, steps)
                streams.append(
                    SyntheticDataSource(
                        symbol=symbol,
                        timeframe=timeframe,
                        exchange=self.config.runtime.exchange,
                        steps=steps,
                    ).stream()
                )
        for stream in streams:
            for candle in stream:
                yield candle

    def _synthetic_steps(self, timeframe: str) -> int:
        if self.config.backtest.days_back > 0:
            try:
                step = timeframe_to_seconds(timeframe)
            except ValueError:
                return 200
            steps = int(self.config.backtest.days_back * 86400 / step)
            return max(50, min(steps, 5000))
        return 200
