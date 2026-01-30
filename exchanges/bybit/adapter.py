from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import asyncio
import hashlib
import hmac
import json
import queue
import threading
import time

import requests

from data.schemas import Candle
from utils.logger import get_logger
from exchanges.base_exchange import ExchangeAdapter, RateLimiter, RestClient, WsClient
from utils.time import timeframe_to_seconds
from utils.retry import RetryPolicy


logger = get_logger("exchange.bybit")


class BybitRestClient(RestClient):
    def __init__(
        self,
        rate_limiter: RateLimiter,
        retry_policy: RetryPolicy,
        base_url: str,
        market_base_url: str,
        timeout: float,
        category: str,
        api_key: str,
        api_secret: str,
        recv_window: int,
    ) -> None:
        super().__init__(rate_limiter, retry_policy)
        self.base_url = base_url.rstrip("/")
        self.market_base_url = market_base_url.rstrip("/") if market_base_url else self.base_url
        self.timeout = timeout
        self.category = category
        self.api_key = api_key
        self.api_secret = api_secret
        self.recv_window = recv_window
        self._time_offset_ms = 0
        self._last_time_sync = 0.0
        self._sync_stop = threading.Event()
        self._sync_thread: threading.Thread | None = None
        self._instrument_cache: dict[str, tuple[float, dict[str, float]]] = {}
        self._instrument_cache_ttl = 300.0

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
        payload = self.request({"path": "/v5/market/kline", "params": params, "method": "GET", "market": True})
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

    def get_order_status(self, order_id: str, symbol: str) -> dict[str, Any]:
        params = {"category": self.category, "orderId": order_id, "symbol": symbol}
        payload = self.request({"path": "/v5/order/realtime", "params": params, "method": "GET", "auth": True})
        items = payload.get("result", {}).get("list", []) or []
        return items[0] if items else {}

    def get_executions(self, order_id: str, symbol: str) -> list[dict[str, Any]]:
        params = {"category": self.category, "orderId": order_id, "symbol": symbol}
        payload = self.request({"path": "/v5/execution/list", "params": params, "method": "GET", "auth": True})
        return payload.get("result", {}).get("list", []) or []

    def get_instrument_constraints(self, symbol: str) -> dict[str, float]:
        now = time.time()
        cached = self._instrument_cache.get(symbol)
        if cached and now - cached[0] < self._instrument_cache_ttl:
            return cached[1]
        params = {"category": self.category, "symbol": symbol}
        payload = self.request({"path": "/v5/market/instruments-info", "params": params, "method": "GET", "market": True})
        items = payload.get("result", {}).get("list", []) or []
        if not items:
            return {}
        item = items[0] or {}
        lot = item.get("lotSizeFilter") or {}
        min_qty = _parse_float(lot.get("minOrderQty"))
        min_notional = _parse_float(
            lot.get("minOrderAmt")
            or lot.get("minOrderValue")
            or lot.get("minNotional")
            or lot.get("minNotionalValue")
        )
        constraints = {
            "min_qty": min_qty,
            "min_notional": min_notional,
        }
        self._instrument_cache[symbol] = (now, constraints)
        return constraints

    def place_order(self, order) -> Any:
        body = {
            "category": self.category,
            "symbol": order.symbol,
            "side": "Buy" if order.side.upper() == "BUY" else "Sell",
            "orderType": "Market",
            "qty": str(order.quantity),
            "orderLinkId": order.client_order_id,
        }
        return self.request({"path": "/v5/order/create", "params": body, "method": "POST", "auth": True})

    def cancel_order(self, order_id: str, symbol: str) -> Any:
        body = {
            "category": self.category,
            "symbol": symbol,
            "orderId": order_id,
        }
        return self.request({"path": "/v5/order/cancel", "params": body, "method": "POST", "auth": True})

    def sign_ws(self, expires: str) -> str:
        message = f"GET/realtime{expires}"
        return _sign(self.api_secret, message)

    def ws_expires(self) -> str:
        return str(self._timestamp_ms() + 10_000)

    def start_time_sync(self) -> None:
        if self._sync_thread and self._sync_thread.is_alive():
            return

        def _runner() -> None:
            while not self._sync_stop.is_set():
                now = time.time()
                base = int(now // 60) * 60
                target = base + 1
                if now >= target:
                    target = base + 60 + 1
                sleep_seconds = max(0.0, target - now)
                self._sync_stop.wait(timeout=sleep_seconds)
                if self._sync_stop.is_set():
                    break
                self._ensure_time_sync(force=True)

        self._sync_thread = threading.Thread(target=_runner, daemon=True, name="bybit-time-sync")
        self._sync_thread.start()

    def stop_time_sync(self) -> None:
        self._sync_stop.set()

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        base_url = self.market_base_url if payload.get("market") else self.base_url
        url = f"{base_url}{payload['path']}"
        params = payload.get("params", {})
        method = payload.get("method", "GET").upper()
        auth = payload.get("auth", False)
        headers = {"Content-Type": "application/json"}
        payload_str = _payload_string(method, params)
        if auth:
            self._ensure_time_sync()
            timestamp = str(self._timestamp_ms())
            recv_window = str(self.recv_window)
            sign = _sign(self.api_secret, f"{timestamp}{self.api_key}{recv_window}{payload_str}")
            headers = {
                "X-BAPI-API-KEY": self.api_key,
                "X-BAPI-TIMESTAMP": timestamp,
                "X-BAPI-RECV-WINDOW": recv_window,
                "X-BAPI-SIGN": sign,
                "Content-Type": "application/json",
            }
        if method == "POST":
            response = requests.post(url, data=payload_str, headers=headers, timeout=self.timeout)
        else:
            response = requests.get(url, params=params, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        if data.get("retCode") not in (0, "0"):
            raise RuntimeError(f"Bybit error: {data.get('retMsg')}")
        return data

    def _timestamp_ms(self) -> int:
        return int(time.time() * 1000) + int(self._time_offset_ms)

    def _ensure_time_sync(self, force: bool = False) -> None:
        if not force and time.time() - self._last_time_sync < 60:
            return
        try:
            response = requests.get(f"{self.market_base_url}/v5/market/time", timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            result = data.get("result", {}) if isinstance(data, dict) else {}
            server_ms = 0
            if "timeSecond" in result:
                server_ms = int(result["timeSecond"]) * 1000
            elif "timeNano" in result:
                server_ms = int(int(result["timeNano"]) / 1_000_000)
            if server_ms:
                local_ms = int(time.time() * 1000)
                self._time_offset_ms = server_ms - local_ms
                self._last_time_sync = time.time()
                return
        except Exception as exc:  # noqa: BLE001
            logger.warning("bybit time sync failed: %s", exc)


class BybitWsClient(WsClient):
    def __init__(
        self,
        ws_url: str,
        exchange_name: str,
        open_timeout: int,
        ping_interval: int,
        retry_seconds: int,
        message_timeout: int,
    ) -> None:
        self.ws_url = ws_url
        self.exchange_name = exchange_name
        self.open_timeout = open_timeout
        self.ping_interval = ping_interval
        self.retry_seconds = retry_seconds
        self.message_timeout = message_timeout

    def connect(self) -> None:
        raise NotImplementedError("Direct connect not supported; use stream_ohlcv")

    def subscribe(self, channel: str) -> None:
        raise NotImplementedError("Direct subscribe not supported; use stream_ohlcv")

    def stream_ohlcv(self, symbols: list[str], timeframes: list[str]) -> Iterable[Candle | None]:
        topics = []
        for symbol in symbols:
            for timeframe in timeframes:
                interval = _map_timeframe(timeframe)
                topics.append(f"kline.{interval}.{symbol}")

        output: queue.Queue[Candle] = queue.Queue()
        stop_event = threading.Event()

        async def _listen() -> None:
            import websockets

            while not stop_event.is_set():
                try:
                    async with websockets.connect(
                        self.ws_url,
                        ping_interval=self.ping_interval,
                        open_timeout=self.open_timeout,
                    ) as ws:
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
                except Exception as exc:  # noqa: BLE001
                    logger.warning("public WS reconnect: %s", exc)
                    await asyncio.sleep(self.retry_seconds)

        def _run() -> None:
            asyncio.run(_listen())

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        while True:
            try:
                yield output.get(timeout=self.message_timeout)
            except queue.Empty:
                logger.warning("no WS candles received in %ss", self.message_timeout)
                yield None


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


def _parse_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _payload_string(method: str, params: dict[str, Any]) -> str:
    if method == "GET":
        if not params:
            return ""
        parts = [f"{key}={params[key]}" for key in sorted(params.keys())]
        return "&".join(parts)
    return json.dumps(params, separators=(",", ":"), ensure_ascii=False, sort_keys=True)


def _sign(secret: str, message: str) -> str:
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
