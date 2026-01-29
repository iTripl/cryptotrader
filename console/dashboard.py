from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class DashboardState:
    strategies: dict[str, bool]
    pnl: float
    drawdown: float
    status: str


class Dashboard:
    def __init__(self, state_provider: Callable[[], DashboardState]) -> None:
        self.state_provider = state_provider

    def run(self) -> None:
        try:
            from rich.live import Live
            from rich.table import Table
        except ImportError:
            self._run_fallback()
            return

        with Live(auto_refresh=False) as live:
            while True:
                state = self.state_provider()
                table = Table(title="Runtime Dashboard")
                table.add_column("Metric")
                table.add_column("Value")
                table.add_row("Status", state.status)
                table.add_row("PnL", f"{state.pnl:.2f}")
                table.add_row("Drawdown", f"{state.drawdown:.2%}")
                table.add_row("Strategies", ", ".join([f"{k}:{'up' if v else 'down'}" for k, v in state.strategies.items()]))
                live.update(table, refresh=True)
                time.sleep(1)

    def _run_fallback(self) -> None:
        while True:
            state = self.state_provider()
            print(f"Status={state.status} PnL={state.pnl:.2f} DD={state.drawdown:.2%} Strategies={state.strategies}")
            time.sleep(2)
