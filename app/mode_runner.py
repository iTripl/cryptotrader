from __future__ import annotations

from pathlib import Path
from typing import Iterable

from config.config_schema import AppConfig
from data.schemas import Candle
from data.normalization import normalize_ohlcv
from exchanges.base_exchange import ExchangeAdapter
from data.simulated import SyntheticDataSource
from data.auto_loader import DataAutoLoader
from data.storage.parquet_reader import ParquetReader
from utils.logger import get_logger
from utils.time import timeframe_to_seconds, utc_now_ts


logger = get_logger("app.mode")


class ModeRunner:
    def __init__(
        self,
        config: AppConfig,
        reader: ParquetReader,
        auto_loader: DataAutoLoader | None = None,
        exchange_adapter: ExchangeAdapter | None = None,
    ) -> None:
        self.config = config
        self.reader = reader
        self.auto_loader = auto_loader
        self.exchange_adapter = exchange_adapter
        self._last_polled_ts: dict[tuple[str, str], int] = {}
        self._last_stream_ts: dict[tuple[str, str], int] = {}

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
        if self.config.backtest.max_candles_per_series > 0:
            candles = self._cap_per_series(candles, self.config.backtest.max_candles_per_series)
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
        return self._live_stream()

    def _live_stream(self) -> Iterable[Candle]:
        if self.config.runtime.dry_run:
            return self._synthetic_stream()
        if not self.exchange_adapter:
            raise RuntimeError("Exchange adapter required for live stream")
        logger.info("starting live stream via exchange WS")
        stream = self.exchange_adapter.stream_ohlcv(
            list(self.config.symbols.symbols),
            list(self.config.symbols.timeframes),
        )
        logger.debug(
            "live stream subscribed symbols=%s timeframes=%s",
            self.config.symbols.symbols,
            self.config.symbols.timeframes,
        )
        for candle in stream:
            if candle is None:
                logger.debug("live stream heartbeat missed; polling REST for latest candles")
                for symbol in self.config.symbols.symbols:
                    for timeframe in self.config.symbols.timeframes:
                        polled = self._poll_latest_candle(symbol, timeframe)
                        if polled and self._dedupe_candle(polled):
                            yield polled
                continue
            logger.debug(
                "live candle %s %s ts=%s close=%s",
                candle.symbol,
                candle.timeframe,
                candle.timestamp,
                candle.close,
            )
            if self._dedupe_candle(candle):
                yield candle

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

    @staticmethod
    def _cap_per_series(candles: list[Candle], max_per_series: int) -> list[Candle]:
        if max_per_series <= 0:
            return candles
        buckets: dict[tuple[str, str], list[Candle]] = {}
        for candle in candles:
            key = (candle.symbol, candle.timeframe)
            buckets.setdefault(key, []).append(candle)
        capped: list[Candle] = []
        for series in buckets.values():
            series.sort(key=lambda c: c.timestamp)
            capped.extend(series[-max_per_series:])
        return capped

    def _poll_latest_candle(self, symbol: str, timeframe: str) -> Candle | None:
        if not self.exchange_adapter:
            return None
        end_ts = utc_now_ts()
        try:
            step = timeframe_to_seconds(timeframe)
        except ValueError:
            return None
        start_ts = end_ts - step * 2
        try:
            rows = self.exchange_adapter.rest.get_ohlcv(symbol, timeframe, start_ts, end_ts, 2)
        except Exception as exc:  # noqa: BLE001
            logger.warning("REST poll failed for %s %s: %s", symbol, timeframe, exc)
            return None
        if isinstance(rows, tuple):
            rows = rows[0]
        if not rows:
            return None
        last = rows[-1]
        key = (symbol, timeframe)
        last_seen = self._last_polled_ts.get(key, 0)
        if last["timestamp"] <= last_seen:
            logger.debug(
                "rest candle skipped %s %s ts=%s last_seen=%s",
                symbol,
                timeframe,
                last.get("timestamp"),
                last_seen,
            )
            return None
        self._last_polled_ts[key] = last["timestamp"]
        logger.debug(
            "rest candle %s %s ts=%s close=%s",
            symbol,
            timeframe,
            last.get("timestamp"),
            last.get("close"),
        )
        return normalize_ohlcv([last], symbol, timeframe, self.exchange_adapter.name)[0]

    def _dedupe_candle(self, candle: Candle) -> bool:
        key = (candle.symbol, candle.timeframe)
        last_seen = self._last_stream_ts.get(key, 0)
        if candle.timestamp <= last_seen:
            logger.debug(
                "duplicate candle skipped %s %s ts=%s last_seen=%s",
                candle.symbol,
                candle.timeframe,
                candle.timestamp,
                last_seen,
            )
            return False
        self._last_stream_ts[key] = candle.timestamp
        return True
