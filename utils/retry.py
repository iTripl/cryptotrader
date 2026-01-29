from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    base_delay: float
    max_delay: float
    jitter: float


DEFAULT_RETRY_POLICY = RetryPolicy(
    max_attempts=5,
    base_delay=0.5,
    max_delay=5.0,
    jitter=0.3,
)


def retry(policy: RetryPolicy = DEFAULT_RETRY_POLICY) -> Callable[[Callable[..., T]], Callable[..., T]]:
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args, **kwargs) -> T:
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception:
                    attempt += 1
                    if attempt >= policy.max_attempts:
                        raise
                    delay = min(policy.base_delay * (2 ** (attempt - 1)), policy.max_delay)
                    delay += random.random() * policy.jitter
                    time.sleep(delay)

        return wrapper

    return decorator
