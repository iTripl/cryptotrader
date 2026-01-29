from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from exchanges.base_exchange import ExchangeAdapter, RateLimiter, RestClient, WsClient
from utils.time import timeframe_to_seconds
from utils.retry import RetryPolicy


class BybitRestClient(RestClient):
    def __init__(
        self,
        rate_limiter: RateLimiter,
        retry_policy: RetryPolicy,
        base_url: str,
        timeout: float,
        category: str,
    ) -> None:
        super().__init__(rate_limiter, retry_policy)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.category = category

    def get_ohlcv(self, symbol: str, timeframe: str, since: int, end_ts: int, limit: int) -> tuple[list[dict], int | None]:
        interval = _map_timeframe(timeframe)
        start_ms = since * 1000
        end_ms = end_ts * 1000
        params = {
            "category": self.category,
            "symbol": symbol,
            "interval": interval,
            "start": start_ms,
            "end": end_ms,
            "limit": limit,
        }
        payload = self.request({"path": "/v5/market/kline", "params": params})
        raw = payload.get("result", {}).get("list", []) or []
        rows = []
        for item in raw:
            ts_ms, open_p, high, low, close, volume = item[:6]
            rows.append(
                {
                    "timestamp": int(ts_ms) // 1000,
                    "open": float(open_p),
                    "high": float(high),
                    "low": float(low),
                    "close": float(close),
                    "volume": float(volume),
                }
            )
        rows.sort(key=lambda r: r["timestamp"])
        next_since = None
        if rows:
            next_since = rows[-1]["timestamp"] + timeframe_to_seconds(timeframe)
        return rows, next_since

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{payload['path']}"
        params = payload.get("params", {})
        response = requests.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        if data.get("retCode") not in (0, "0"):
            raise RuntimeError(f"Bybit error: {data.get('retMsg')}")
        return data


class BybitWsClient(WsClient):
    def connect(self) -> None:
        raise NotImplementedError("Implement Bybit WS connect")

    def subscribe(self, channel: str) -> None:
        raise NotImplementedError("Implement Bybit WS subscribe")


class BybitAdapter(ExchangeAdapter):
    name = "bybit"

    def __init__(self, rest: BybitRestClient, ws: BybitWsClient, checkpoint_dir: Path) -> None:
        super().__init__(rest, ws, checkpoint_dir)


def _map_timeframe(timeframe: str) -> str:
    mapping = {
        "1m": "1",
        "3m": "3",
        "5m": "5",
        "15m": "15",
        "30m": "30",
        "1h": "60",
        "2h": "120",
        "4h": "240",
        "6h": "360",
        "12h": "720",
        "1d": "D",
        "1w": "W",
    }
    if timeframe not in mapping:
        raise ValueError(f"Unsupported timeframe for Bybit: {timeframe}")
    return mapping[timeframe]
