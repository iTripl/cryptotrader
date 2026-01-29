from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass
class Metric:
    name: str
    value: float


class MetricsCollector:
    def __init__(self) -> None:
        self._metrics: dict[str, float] = defaultdict(float)

    def inc(self, name: str, value: float = 1.0) -> None:
        self._metrics[name] += value

    def set(self, name: str, value: float) -> None:
        self._metrics[name] = value

    def snapshot(self) -> list[Metric]:
        return [Metric(name, value) for name, value in self._metrics.items()]
