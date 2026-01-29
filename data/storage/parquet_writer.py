from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from data.schemas import Candle
from utils.logger import get_logger


logger = get_logger("data.parquet")


def _require_pandas() -> None:
    try:
        import pandas  # noqa: F401
        import pyarrow  # noqa: F401
    except ImportError as exc:
        raise ImportError("pandas and pyarrow are required for Parquet I/O") from exc


def _filename(symbol: str, timeframe: str, year: int) -> str:
    return f"{symbol}_{timeframe}_{year}.parquet"


class ParquetWriter:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def write(self, candles: Iterable[Candle], namespace: str) -> Path:
        _require_pandas()
        import pandas as pd

        candle_list = list(candles)
        if not candle_list:
            raise ValueError("No candles to write")

        symbol = candle_list[0].symbol
        timeframe = candle_list[0].timeframe
        year = datetime.fromtimestamp(candle_list[0].timestamp, tz=timezone.utc).year

        target_dir = self.base_dir / namespace
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / _filename(symbol, timeframe, year)

        df = pd.DataFrame([asdict(candle) for candle in candle_list])
        df.to_parquet(path, index=False)
        logger.info("wrote parquet %s", path)
        return path

    def write_partitioned(self, candles: Iterable[Candle], namespace: str) -> list[Path]:
        _require_pandas()
        import pandas as pd

        candle_iter = iter(candles)
        bucket: list[Candle] = []
        written: list[Path] = []
        current_year: int | None = None
        symbol = None
        timeframe = None

        for candle in candle_iter:
            candle_year = datetime.fromtimestamp(candle.timestamp, tz=timezone.utc).year
            if current_year is None:
                current_year = candle_year
                symbol = candle.symbol
                timeframe = candle.timeframe
            if candle_year != current_year and bucket:
                path = self._write_bucket(bucket, namespace, symbol, timeframe, current_year)
                written.append(path)
                bucket = []
                current_year = candle_year
            bucket.append(candle)

        if bucket and current_year is not None and symbol and timeframe:
            path = self._write_bucket(bucket, namespace, symbol, timeframe, current_year)
            written.append(path)
        return written

    def _write_bucket(
        self,
        bucket: list[Candle],
        namespace: str,
        symbol: str,
        timeframe: str,
        year: int,
    ) -> Path:
        import pandas as pd

        target_dir = self.base_dir / namespace
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / _filename(symbol, timeframe, year)
        df = pd.DataFrame([asdict(candle) for candle in bucket])
        df.to_parquet(path, index=False)
        logger.info("wrote parquet %s", path)
        return path
