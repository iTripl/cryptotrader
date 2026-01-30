from __future__ import annotations

from dataclasses import dataclass, field

from state.models import BacktestMetrics, BacktestSummary, Fill, Order, Trade, TradeMetrics


class StateRepository:
    def save_order(self, order: Order) -> None:
        raise NotImplementedError

    def save_trade(self, trade: Trade) -> None:
        raise NotImplementedError

    def save_fill(self, fill: Fill) -> None:
        raise NotImplementedError

    def save_trade_metrics(self, metrics: TradeMetrics) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def save_backtest_summary(self, summary: BacktestSummary) -> None:
        raise NotImplementedError

    def save_backtest_metrics(self, metrics: BacktestMetrics) -> None:
        raise NotImplementedError

@dataclass
class InMemoryStateRepository(StateRepository):
    orders: list[Order] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    backtest_summaries: list[BacktestSummary] = field(default_factory=list)
    trade_metrics: list[TradeMetrics] = field(default_factory=list)
    backtest_metrics: list[BacktestMetrics] = field(default_factory=list)

    def save_order(self, order: Order) -> None:
        self.orders.append(order)

    def save_trade(self, trade: Trade) -> None:
        self.trades.append(trade)

    def save_fill(self, fill: Fill) -> None:
        self.fills.append(fill)

    def save_trade_metrics(self, metrics: TradeMetrics) -> None:
        self.trade_metrics.append(metrics)

    def close(self) -> None:
        return None

    def save_backtest_summary(self, summary: BacktestSummary) -> None:
        self.backtest_summaries.append(summary)

    def save_backtest_metrics(self, metrics: BacktestMetrics) -> None:
        self.backtest_metrics.append(metrics)

