from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from exchanges.base_exchange import ExchangeAdapter, RateLimiter, RestClient, WsClient
from utils.retry import RetryPolicy


class BinanceRestClient(RestClient):
    def __init__(
        self,
        rate_limiter: RateLimiter,
        retry_policy: RetryPolicy,
        base_url: str,
        timeout: float,
    ) -> None:
        super().__init__(rate_limiter, retry_policy)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_ohlcv(self, symbol: str, timeframe: str, since: int, end_ts: int, limit: int) -> list[dict]:
        interval = _map_timeframe(timeframe)
        start_ms = since * 1000
        end_ms = end_ts * 1000
        params = {"symbol": symbol, "interval": interval, "startTime": start_ms, "endTime": end_ms, "limit": limit}
        payload = self.request({"path": "/api/v3/klines", "params": params})
        rows = []
        for item in payload:
            open_time, open_p, high, low, close, volume = item[:6]
            rows.append(
                {
                    "timestamp": int(open_time) // 1000,
                    "open": float(open_p),
                    "high": float(high),
                    "low": float(low),
                    "close": float(close),
                    "volume": float(volume),
                }
            )
        rows.sort(key=lambda r: r["timestamp"])
        return rows

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{payload['path']}"
        params = payload.get("params", {})
        response = requests.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()


class BinanceWsClient(WsClient):
    def connect(self) -> None:
        raise NotImplementedError("Implement Binance WS connect")

    def subscribe(self, channel: str) -> None:
        raise NotImplementedError("Implement Binance WS subscribe")

    def stream_ohlcv(self, symbols: list[str], timeframes: list[str]):
        raise NotImplementedError("Implement Binance WS stream")


class BinanceAdapter(ExchangeAdapter):
    name = "binance"

    def __init__(self, rest: BinanceRestClient, ws: BinanceWsClient, checkpoint_dir: Path) -> None:
        super().__init__(rest, ws, checkpoint_dir)


def _map_timeframe(timeframe: str) -> str:
    mapping = {
        "1m": "1m",
        "3m": "3m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "6h": "6h",
        "8h": "8h",
        "12h": "12h",
        "1d": "1d",
        "1w": "1w",
    }
    if timeframe not in mapping:
        raise ValueError(f"Unsupported timeframe for Binance: {timeframe}")
    return mapping[timeframe]
