from __future__ import annotations

import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from data.loaders.base_loader import LoaderCheckpoint
from data.schemas import Candle
from monitoring.health import CircuitBreaker
from utils.retry import RetryPolicy


@dataclass
class RateLimiter:
    max_per_minute: int
    last_reset: float = 0.0
    tokens: int = 0

    def allow(self) -> bool:
        now = time.time()
        if now - self.last_reset > 60:
            self.tokens = self.max_per_minute
            self.last_reset = now
        if self.tokens <= 0:
            return False
        self.tokens -= 1
        return True


class RestClient:
    def __init__(self, rate_limiter: RateLimiter, retry_policy: RetryPolicy) -> None:
        self.rate_limiter = rate_limiter
        self.retry_policy = retry_policy
        self.circuit = CircuitBreaker()

    def request(self, payload: dict[str, Any]) -> Any:
        attempt = 0
        while True:
            try:
                if not self.rate_limiter.allow():
                    raise RuntimeError("Rate limit exceeded")
                if not self.circuit.allow():
                    raise RuntimeError("Circuit breaker open")
                return self._request(payload)
            except Exception as exc:
                if isinstance(exc, (ValueError, TypeError, KeyError)):
                    raise
                attempt += 1
                if attempt >= self.retry_policy.max_attempts:
                    self.circuit.record_failure()
                    raise
                delay = min(
                    self.retry_policy.base_delay * (2 ** (attempt - 1)),
                    self.retry_policy.max_delay,
                )
                delay += random.uniform(0, self.retry_policy.jitter)
                time.sleep(delay)

    def _request(self, payload: dict[str, Any]) -> Any:
        raise NotImplementedError

    def place_order(self, order: Any) -> Any:
        raise NotImplementedError

    def cancel_order(self, order_id: str, symbol: str) -> Any:
        raise NotImplementedError


class WsClient:
    def connect(self) -> None:
        raise NotImplementedError

    def subscribe(self, channel: str) -> None:
        raise NotImplementedError

    def stream_ohlcv(self, symbols: list[str], timeframes: list[str]) -> Iterable[Candle | None]:
        raise NotImplementedError


class ExchangeAdapter:
    name: str

    def __init__(self, rest: RestClient, ws: WsClient, checkpoint_dir: Path) -> None:
        self.rest = rest
        self.ws = ws
        self._checkpoint_dir = checkpoint_dir
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def checkpoint(self, name: str) -> LoaderCheckpoint:
        return LoaderCheckpoint(self._checkpoint_dir / f"{name}.json")

    def stream_ohlcv(self, symbols: list[str], timeframes: list[str]) -> Iterable[Candle]:
        return self.ws.stream_ohlcv(symbols, timeframes)
