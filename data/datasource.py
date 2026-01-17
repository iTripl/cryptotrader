# data/datasource.py
import pandas as pd
from abc import ABC, abstractmethod

class MarketDataSource(ABC):

    @abstractmethod
    def fetch_ohlcv(
        self,
        symbol: str,
        interval_min: int,
        start_ts: int,
        end_ts: int,
        limit: int
    ) -> pd.DataFrame:
        pass
