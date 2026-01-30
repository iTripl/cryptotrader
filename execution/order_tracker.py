from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass
from typing import Iterable

from utils.logger import get_logger


logger = get_logger("execution.order_tracker")


@dataclass(frozen=True)
class FillEvent:
    exec_id: str
    order_id: str
    symbol: str
    side: str
    price: float
    quantity: float
    fee: float
    timestamp: int


class OrderTracker:
    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def register_order(self, order_id: str, symbol: str) -> None:
        raise NotImplementedError

    def drain_fills(self) -> list[FillEvent]:
        raise NotImplementedError

    def open_orders(self) -> dict[str, str]:
        raise NotImplementedError


class BybitOrderTracker(OrderTracker):
    def __init__(
        self,
        rest_client,
        private_ws_url: str,
        api_key: str,
        api_secret: str,
        recv_window: int,
        poll_interval_seconds: int,
        open_timeout: int,
        ping_interval: int,
        retry_seconds: int,
    ) -> None:
        self._rest = rest_client
        self._private_ws_url = private_ws_url
        self._api_key = api_key
        self._api_secret = api_secret
        self._recv_window = recv_window
        self._poll_interval = poll_interval_seconds
        self._open_timeout = open_timeout
        self._ping_interval = ping_interval
        self._retry_seconds = retry_seconds
        self._fills: queue.Queue[FillEvent] = queue.Queue()
        self._open_orders: dict[str, str] = {}
        self._seen_exec_ids: set[str] = set()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._orders_lock = threading.Lock()
        self._seen_lock = threading.Lock()

    def start(self) -> None:
        if not self._api_key or not self._api_secret:
            logger.warning("Bybit order tracker disabled: missing API key/secret")
            return
        ws_thread = threading.Thread(target=self._run_private_ws, daemon=True)
        poll_thread = threading.Thread(target=self._run_polling, daemon=True)
        self._threads = [ws_thread, poll_thread]
        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=2)

    def register_order(self, order_id: str, symbol: str) -> None:
        if not order_id:
            return
        with self._orders_lock:
            self._open_orders[order_id] = symbol
        logger.info("tracking order %s (%s)", order_id, symbol)

    def drain_fills(self) -> list[FillEvent]:
        fills: list[FillEvent] = []
        while True:
            try:
                fills.append(self._fills.get_nowait())
            except queue.Empty:
                break
        return fills

    def open_orders(self) -> dict[str, str]:
        with self._orders_lock:
            return dict(self._open_orders)

    def _run_polling(self) -> None:
        while not self._stop.is_set():
            with self._orders_lock:
                open_orders = list(self._open_orders.items())
            for order_id, symbol in open_orders:
                try:
                    status = self._rest.get_order_status(order_id, symbol)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("order status poll failed: %s", exc)
                    continue
                state = status.get("orderStatus") or status.get("order_status")
                if state:
                    logger.info("order %s status=%s", order_id, state)
                self._collect_executions(order_id, symbol)
                if state in {"Filled", "Cancelled", "Rejected"}:
                    with self._orders_lock:
                        self._open_orders.pop(order_id, None)
            time.sleep(self._poll_interval)

    def _run_private_ws(self) -> None:
        import asyncio
        import websockets

        async def _listen() -> None:
            while not self._stop.is_set():
                try:
                    async with websockets.connect(
                        self._private_ws_url,
                        ping_interval=self._ping_interval,
                        open_timeout=self._open_timeout,
                    ) as ws:
                        expires = self._rest.ws_expires()
                        signature = self._rest.sign_ws(expires)
                        await ws.send(json.dumps({"op": "auth", "args": [self._api_key, expires, signature]}))
                        await ws.send(json.dumps({"op": "subscribe", "args": ["execution"]}))

                        while not self._stop.is_set():
                            msg = await ws.recv()
                            payload = json.loads(msg)
                            if payload.get("topic") != "execution":
                                continue
                            data = payload.get("data") or []
                            if isinstance(data, dict):
                                data = [data]
                            for item in data:
                                exec_id = str(item.get("execId") or item.get("execID") or "")
                                if exec_id:
                                    with self._seen_lock:
                                        if exec_id in self._seen_exec_ids:
                                            continue
                                        self._seen_exec_ids.add(exec_id)
                                fill = FillEvent(
                                    exec_id=exec_id,
                                    order_id=str(item.get("orderId") or ""),
                                    symbol=str(item.get("symbol") or ""),
                                    side=str(item.get("side") or ""),
                                    price=float(item.get("execPrice") or item.get("price") or 0),
                                    quantity=float(item.get("execQty") or item.get("qty") or 0),
                                    fee=float(item.get("execFee") or item.get("fee") or 0),
                                    timestamp=int(item.get("execTime") or item.get("ts") or 0) // 1000,
                                )
                                self._fills.put(fill)
                                if fill.order_id:
                                    with self._orders_lock:
                                        self._open_orders.pop(fill.order_id, None)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("private WS reconnect: %s", exc)
                    await asyncio.sleep(self._retry_seconds)

        try:
            asyncio.run(_listen())
        except Exception as exc:  # noqa: BLE001
            logger.error("private WS stopped: %s", exc)

    def _collect_executions(self, order_id: str, symbol: str) -> None:
        try:
            executions = self._rest.get_executions(order_id, symbol)
        except Exception as exc:  # noqa: BLE001
            logger.warning("execution list fetch failed: %s", exc)
            return
        for item in executions:
            exec_id = str(item.get("execId") or item.get("execID") or "")
            if not exec_id:
                continue
            with self._seen_lock:
                if exec_id in self._seen_exec_ids:
                    continue
                self._seen_exec_ids.add(exec_id)
            fill = FillEvent(
                exec_id=exec_id,
                order_id=str(item.get("orderId") or ""),
                symbol=str(item.get("symbol") or symbol),
                side=str(item.get("side") or ""),
                price=float(item.get("execPrice") or item.get("price") or 0),
                quantity=float(item.get("execQty") or item.get("qty") or 0),
                fee=float(item.get("execFee") or item.get("fee") or 0),
                timestamp=int(item.get("execTime") or item.get("ts") or 0) // 1000,
            )
            self._fills.put(fill)
