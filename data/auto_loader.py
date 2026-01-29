from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
import time
from pathlib import Path

from config.config_schema import AppConfig
from data.loaders.base_loader import HistoricalLoader
from data.loaders.binance_loader import BinanceHistoricalLoader
from data.loaders.bybit_loader import BybitHistoricalLoader
from data.loaders.okx_loader import OkxHistoricalLoader
from data.storage.parquet_writer import ParquetWriter
from exchanges.base_exchange import ExchangeAdapter
from utils.logger import get_logger
from utils.time import utc_now_ts


logger = get_logger("data.auto_loader")


@dataclass
class DataAutoLoader:
    config: AppConfig
    adapter: ExchangeAdapter
    writer: ParquetWriter

    def ensure_backtest_data(self) -> None:
        if not self.config.backtest.auto_download:
            return

        start_ts, end_ts = self._resolve_backtest_range()

        if start_ts <= 0 or end_ts <= 0 or end_ts <= start_ts:
            raise ValueError("Invalid backtest start_ts/end_ts")
        logger.info("backtest range: %d -> %d", start_ts, end_ts)

        for symbol in self.config.symbols.symbols:
            for timeframe in self.config.symbols.timeframes:
                self._download_range(symbol, timeframe, start_ts, end_ts)

    def _resolve_backtest_range(self) -> tuple[int, int]:
        if self.config.backtest.days_back > 0:
            end_ts = utc_now_ts()
            start_ts = end_ts - self.config.backtest.days_back * 86400
            return start_ts, end_ts
        start_ts = self.config.backtest.start_ts
        end_ts = self.config.backtest.end_ts or utc_now_ts()
        return start_ts, end_ts

    def _download_range(self, symbol: str, timeframe: str, start_ts: int, end_ts: int) -> None:
        lock_path = (self.config.paths.data_dir / "norm" / f"{symbol}_{timeframe}.lock")
        if not self._acquire_lock(lock_path):
            raise RuntimeError(f"lock timeout for {symbol} {timeframe}")
        try:
            logger.info("downloading %s %s range", symbol, timeframe)
            loader = self._loader(symbol, timeframe)
            loader.checkpoint.clear()
            candles = loader.load_range(
                symbol=symbol,
                timeframe=timeframe,
                start_ts=start_ts,
                end_ts=end_ts,
                limit=self.config.backtest.download_limit,
                timeout_seconds=self.config.backtest.loader_timeout_seconds,
                max_empty_batches=self.config.backtest.max_empty_batches,
            )
            written = self.writer.write_partitioned(candles, namespace="norm")
            if not written:
                raise RuntimeError(f"no data downloaded for {symbol} {timeframe}")
            logger.info("downloaded %s %s (%d files)", symbol, timeframe, len(written))
        finally:
            if lock_path.exists():
                lock_path.unlink(missing_ok=True)

    def _loader(self, symbol: str, timeframe: str) -> HistoricalLoader:
        exchange = self.adapter.name
        checkpoint_name = f"{exchange}_{symbol}_{timeframe}"
        if exchange == "bybit":
            return BybitHistoricalLoader(self.adapter, checkpoint_name)
        if exchange == "binance":
            return BinanceHistoricalLoader(self.adapter, checkpoint_name)
        if exchange == "okx":
            return OkxHistoricalLoader(self.adapter, checkpoint_name)
        raise ValueError(f"Unsupported exchange for auto-download: {exchange}")

    @staticmethod
    def _acquire_lock(lock_path: Path) -> bool:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(30):
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return True
            except FileExistsError:
                time.sleep(1)
        return False
