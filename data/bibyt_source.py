# data/bybit_source.py
import time
import requests
import pandas as pd
from .datasource import MarketDataSource
from .intervals import BYBIT_INTERVAL_MAP
from .schemas import validate_ohlcv_schema

class BybitDataSource(MarketDataSource):

    BASE_URL = "https://api.bybit.com/v5/market/kline"

    def __init__(self, category: str = "linear", retries: int = 5, backoff: float = 2.0):
        self.category = category
        self.retries = retries
        self.backoff = backoff

    def fetch_ohlcv(self, symbol, interval_min, start_ts, end_ts, limit=1000) -> pd.DataFrame:
        interval = BYBIT_INTERVAL_MAP.get(interval_min)
        if interval is None:
            raise ValueError(f"Unsupported interval: {interval_min}m")

        params = {
            "category": self.category,
            "symbol": symbol,
            "interval": interval,
            "start": start_ts,
            "end": end_ts,
            "limit": limit,
        }

        for attempt in range(1, self.retries + 1):
            try:
                r = requests.get(self.BASE_URL, params=params, timeout=10)
                data = r.json()
                if data.get("retCode") != 0:
                    time.sleep(self.backoff * attempt)
                    continue

                rows = data["result"].get("list", [])
                if not rows:
                    return pd.DataFrame(columns=["timestamp","open","high","low","close","volume"])

                df = pd.DataFrame(
                    rows,
                    columns=["timestamp","open","high","low","close","volume","turnover"]
                )
                df = df[["timestamp","open","high","low","close","volume"]]
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                return validate_ohlcv_schema(df)

            except Exception:
                time.sleep(self.backoff * attempt)

        return pd.DataFrame(columns=["timestamp","open","high","low","close","volume"])
