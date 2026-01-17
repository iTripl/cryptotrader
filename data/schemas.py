# data/schemas.py
import pandas as pd

OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]

def validate_ohlcv_schema(df: pd.DataFrame) -> pd.DataFrame:
    missing = set(OHLCV_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns: {missing}")

    df = df[OHLCV_COLUMNS].copy()

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna().sort_values("timestamp").drop_duplicates("timestamp")
    return df
