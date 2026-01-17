# data/storage.py
import os
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from .storage import MarketDataStorage
from .schemas import validate_ohlcv_schema


class ParquetStorageBackend(MarketDataStorage):

    def __init__(self, root: str = "data/ohlcv"):
        self.root = root

    def _path(self, symbol: str, interval_min: int, year: int) -> str:
        return os.path.join(
            self.root,
            symbol,
            f"{interval_min}m",
            f"{year}.parquet"
        )

    def load(self, symbol, interval_min, start_ts, end_ts):
        dfs = []
        start_year = pd.to_datetime(start_ts, unit="ms", utc=True).year
        end_year = pd.to_datetime(end_ts, unit="ms", utc=True).year

        for year in range(start_year, end_year + 1):
            path = self._path(symbol, interval_min, year)
            if os.path.exists(path):
                table = pq.read_table(path)
                df = table.to_pandas()
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                dfs.append(validate_ohlcv_schema(df))

        if not dfs:
            return None

        df = pd.concat(dfs).drop_duplicates("timestamp").sort_values("timestamp")

        ts_ms = df["timestamp"].astype("int64") // 10**6
        mask = (ts_ms >= start_ts) & (ts_ms <= end_ts)
        return df.loc[mask]

    def save(self, symbol, interval_min, df):
        df = validate_ohlcv_schema(df)

        for year, part in df.groupby(df["timestamp"].dt.year):
            path = self._path(symbol, interval_min, year)
            os.makedirs(os.path.dirname(path), exist_ok=True)

            if os.path.exists(path):
                old = pq.read_table(path).to_pandas()
                old["timestamp"] = pd.to_datetime(old["timestamp"], utc=True)
                merged = (
                    pd.concat([old, part])
                    .drop_duplicates("timestamp")
                    .sort_values("timestamp")
                )
            else:
                merged = part

            table = pa.Table.from_pandas(merged)
            pq.write_table(
                table,
                path,
                compression="zstd",
                compression_level=3
            )
