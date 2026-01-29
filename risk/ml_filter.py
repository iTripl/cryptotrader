from __future__ import annotations

from dataclasses import dataclass

from signals.signal import Signal


@dataclass(frozen=True)
class MlFilterDecision:
    approved: bool
    score: float


class MlRiskFilter:
    def approve(self, signal: Signal) -> MlFilterDecision:
        raise NotImplementedError("Implement ML risk filter")
