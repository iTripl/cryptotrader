from __future__ import annotations

from typing import Iterable

from data.schemas import Candle


def normalize_ohlcv(
    rows: Iterable[dict],
    symbol: str,
    timeframe: str,
    exchange: str,
) -> list[Candle]:
    normalized: list[Candle] = []
    for row in rows:
        normalized.append(
            Candle(
                timestamp=int(row["timestamp"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                symbol=symbol,
                timeframe=timeframe,
                exchange=exchange,
            )
        )
    return normalized
