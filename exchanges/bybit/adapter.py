from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import asyncio
import json
import queue
import threading

import requests

from data.schemas import Candle
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
    def __init__(self, ws_url: str, exchange_name: str) -> None:
        self.ws_url = ws_url
        self.exchange_name = exchange_name

    def connect(self) -> None:
        raise NotImplementedError("Direct connect not supported; use stream_ohlcv")

    def subscribe(self, channel: str) -> None:
        raise NotImplementedError("Direct subscribe not supported; use stream_ohlcv")

    def stream_ohlcv(self, symbols: list[str], timeframes: list[str]) -> Iterable[Candle]:
        topics = []
        for symbol in symbols:
            for timeframe in timeframes:
                interval = _map_timeframe(timeframe)
                topics.append(f"kline.{interval}.{symbol}")

        output: queue.Queue[Candle] = queue.Queue()
        stop_event = threading.Event()

        async def _listen() -> None:
            import websockets

            async with websockets.connect(self.ws_url, ping_interval=20) as ws:
                await ws.send(json.dumps({"op": "subscribe", "args": topics}))
                while not stop_event.is_set():
                    msg = await ws.recv()
                    payload = json.loads(msg)
                    if "topic" not in payload:
                        continue
                    topic = payload.get("topic", "")
                    if not topic.startswith("kline."):
                        continue
                    data = payload.get("data") or []
                    if isinstance(data, dict):
                        data = [data]
                    for item in data:
                        if not item.get("confirm", False):
                            continue
                        ts = _to_seconds(item.get("start"))
                        candle = Candle(
                            timestamp=ts,
                            open=float(item.get("open")),
                            high=float(item.get("high")),
                            low=float(item.get("low")),
                            close=float(item.get("close")),
                            volume=float(item.get("volume")),
                            symbol=item.get("symbol"),
                            timeframe=_timeframe_from_topic(topic),
                            exchange=self.exchange_name,
                        )
                        output.put(candle)

        def _run() -> None:
            asyncio.run(_listen())

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        while True:
            yield output.get()


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


def _timeframe_from_topic(topic: str) -> str:
    parts = topic.split(".")
    if len(parts) < 3:
        return "1m"
    interval = parts[1]
    reverse = {
        "1": "1m",
        "3": "3m",
        "5": "5m",
        "15": "15m",
        "30": "30m",
        "60": "1h",
        "120": "2h",
        "240": "4h",
        "360": "6h",
        "720": "12h",
        "D": "1d",
        "W": "1w",
    }
    return reverse.get(interval, "1m")


def _to_seconds(value: Any) -> int:
    if value is None:
        return 0
    ts = int(value)
    if ts > 10_000_000_000:
        return ts // 1000
    return ts
