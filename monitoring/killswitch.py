from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KillSwitch:
    enabled: bool = True
    triggered: bool = False
    reason: str | None = None

    def trigger(self, reason: str) -> None:
        if not self.enabled:
            return
        self.triggered = True
        self.reason = reason

    def reset(self) -> None:
        self.triggered = False
        self.reason = None
