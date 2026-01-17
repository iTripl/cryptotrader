# data/storage.py
import pandas as pd
from abc import ABC, abstractmethod

class MarketDataStorage(ABC):

    @abstractmethod
    def load(
        self,
        symbol: str,
        interval_min: int,
        start_ts: int,
        end_ts: int
    ) -> pd.DataFrame | None:
        pass

    @abstractmethod
    def save(
        self,
        symbol: str,
        interval_min: int,
        df: pd.DataFrame
    ) -> None:
        pass
