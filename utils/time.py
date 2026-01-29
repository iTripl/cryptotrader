from __future__ import annotations

from datetime import datetime, timezone


TIMEFRAME_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "1d": 86400,
}


def utc_now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def timeframe_to_seconds(timeframe: str) -> int:
    if timeframe not in TIMEFRAME_SECONDS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return TIMEFRAME_SECONDS[timeframe]
