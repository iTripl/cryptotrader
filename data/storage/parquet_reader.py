from __future__ import annotations

from pathlib import Path

from data.schemas import Candle
from data.storage.parquet_writer import _require_pandas


class ParquetReader:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def read(self, path: Path) -> list[Candle]:
        _require_pandas()
        import pandas as pd

        df = pd.read_parquet(path)
        records = df.to_dict(orient="records")
        return [Candle(**record) for record in records]
