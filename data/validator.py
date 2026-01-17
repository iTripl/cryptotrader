# data/validator.py
import pandas as pd
from dataclasses import dataclass
from typing import List


@dataclass
class DataIntegrityReport:
    total_rows: int
    duplicates: int
    gaps: int
    first_ts: pd.Timestamp
    last_ts: pd.Timestamp
    gap_timestamps: List[pd.Timestamp]


class OHLCVValidator:
    """
    Production-grade OHLCV validator.
    НЕ чинит данные молча.
    """

    def __init__(self, interval_min: int, strict: bool = False):
        self.interval_ms = interval_min * 60 * 1000
        self.strict = strict

    def validate(self, df: pd.DataFrame) -> DataIntegrityReport:
        if df.empty:
            raise ValueError("OHLCV DataFrame is empty")

        if df["timestamp"].dt.tz is None:
            raise ValueError("timestamp must be timezone-aware (UTC)")

        df = df.sort_values("timestamp")

        # duplicates
        duplicates = df.duplicated("timestamp").sum()

        # gaps
        ts = df["timestamp"].astype("int64") // 10**6
        diffs = ts.diff().dropna()
        gaps_mask = diffs != self.interval_ms
        gaps = gaps_mask.sum()

        gap_timestamps = df["timestamp"].iloc[1:][gaps_mask].tolist()

        report = DataIntegrityReport(
            total_rows=len(df),
            duplicates=int(duplicates),
            gaps=int(gaps),
            first_ts=df["timestamp"].iloc[0],
            last_ts=df["timestamp"].iloc[-1],
            gap_timestamps=gap_timestamps,
        )

        if self.strict and (duplicates > 0 or gaps > 0):
            raise ValueError(
                f"Data integrity violation: {duplicates} duplicates, {gaps} gaps"
            )

        return report
