from __future__ import annotations

from dataclasses import asdict, dataclass
from math import sqrt

from state.models import Trade


@dataclass(frozen=True)
class StatisticsSnapshot:
    total_trades: int
    win_rate: float
    expectancy: float
    max_drawdown: float
    sharpe: float
    sortino: float
    consecutive_losses: int
    slippage_impact: float
    fees_impact: float


@dataclass(frozen=True)
class BacktestReport:
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    max_drawdown: float
    pnl_value: float
    pnl_pct: float


class StatisticsCollector:
    def __init__(self) -> None:
        self._trades: list[Trade] = []
        self._consecutive_losses = 0

    def add_trade(self, trade: Trade) -> None:
        self._trades.append(trade)
        if trade.pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

    def snapshot(self, initial_equity: float | None = None) -> StatisticsSnapshot:
        if not self._trades:
            return StatisticsSnapshot(0, 0.0, 0.0, 0.0, 0.0, 0.0, self._consecutive_losses, 0.0, 0.0)

        pnls = [t.pnl for t in self._trades]
        wins = [p for p in pnls if p > 0]
        win_rate = len(wins) / len(pnls)
        expectancy = sum(pnls) / len(pnls)
        slippage = sum(t.slippage_bps for t in self._trades) / len(self._trades)
        fees = sum(t.fees for t in self._trades)

        mean = expectancy
        variance = sum((p - mean) ** 2 for p in pnls) / max(len(pnls), 1)
        std = sqrt(variance) if variance > 0 else 0.0
        sharpe = mean / std if std else 0.0

        downside = [p for p in pnls if p < 0]
        downside_var = sum((p - mean) ** 2 for p in downside) / max(len(downside), 1) if downside else 0.0
        downside_std = sqrt(downside_var) if downside_var > 0 else 0.0
        sortino = mean / downside_std if downside_std else 0.0

        max_drawdown = 0.0
        if initial_equity is not None:
            max_drawdown = self._max_drawdown(initial_equity)

        return StatisticsSnapshot(
            total_trades=len(pnls),
            win_rate=win_rate,
            expectancy=expectancy,
            max_drawdown=max_drawdown,
            sharpe=sharpe,
            sortino=sortino,
            consecutive_losses=self._consecutive_losses,
            slippage_impact=slippage,
            fees_impact=fees,
        )

    def total_trades(self) -> int:
        return len(self._trades)

    def trades(self) -> list[Trade]:
        return list(self._trades)

    def backtest_report(self, initial_equity: float, final_equity: float) -> BacktestReport:
        total = len(self._trades)
        wins = len([t for t in self._trades if t.pnl > 0])
        losses = len([t for t in self._trades if t.pnl < 0])
        win_rate = wins / total if total else 0.0
        max_dd = self._max_drawdown(initial_equity)
        pnl_value = final_equity - initial_equity
        pnl_pct = (pnl_value / initial_equity) if initial_equity else 0.0
        return BacktestReport(
            total_trades=total,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            max_drawdown=max_dd,
            pnl_value=pnl_value,
            pnl_pct=pnl_pct,
        )

    def _max_drawdown(self, initial_equity: float) -> float:
        equity = initial_equity
        peak = initial_equity
        max_dd = 0.0
        for trade in self._trades:
            equity += trade.pnl
            peak = max(peak, equity)
            if peak > 0:
                dd = (peak - equity) / peak
                max_dd = max(max_dd, dd)
        return max_dd

    def to_dict(self, stats: StatisticsSnapshot) -> dict:
        return asdict(stats)
