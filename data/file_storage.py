# data/file_storage.py
import os
import pandas as pd
from .storage import MarketDataStorage
from .schemas import validate_ohlcv_schema

class FileStorageBackend(MarketDataStorage):

    def __init__(self, root: str = "data/ohlcv"):
        self.root = root

    def _path(self, symbol, interval_min, year):
        return os.path.join(
            self.root,
            symbol,
            f"{interval_min}m",
            f"{year}.csv"
        )

    def load(self, symbol, interval_min, start_ts, end_ts):
        dfs = []
        start_year = pd.to_datetime(start_ts, unit="ms", utc=True).year
        end_year = pd.to_datetime(end_ts, unit="ms", utc=True).year

        for year in range(start_year, end_year + 1):
            path = self._path(symbol, interval_min, year)
            if os.path.exists(path):
                df = pd.read_csv(path)
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                dfs.append(validate_ohlcv_schema(df))

        if not dfs:
            return None

        df = pd.concat(dfs).drop_duplicates("timestamp").sort_values("timestamp")
        mask = (df["timestamp"].astype("int64") // 10**6 >= start_ts) & \
               (df["timestamp"].astype("int64") // 10**6 <= end_ts)
        return df.loc[mask]

    def save(self, symbol, interval_min, df):
        os.makedirs(self.root, exist_ok=True)
        df = validate_ohlcv_schema(df)

        for year, part in df.groupby(df["timestamp"].dt.year):
            path = self._path(symbol, interval_min, year)
            os.makedirs(os.path.dirname(path), exist_ok=True)

            if os.path.exists(path):
                old = pd.read_csv(path)
                old["timestamp"] = pd.to_datetime(old["timestamp"], utc=True)
                merged = pd.concat([old, part]).drop_duplicates("timestamp").sort_values("timestamp")
            else:
                merged = part

            merged.to_csv(path, index=False)
