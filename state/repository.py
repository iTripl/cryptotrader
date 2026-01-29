from __future__ import annotations

from dataclasses import dataclass, field

from state.models import BacktestSummary, Fill, MlRecommendation, Order, Trade


class StateRepository:
    def save_order(self, order: Order) -> None:
        raise NotImplementedError

    def save_trade(self, trade: Trade) -> None:
        raise NotImplementedError

    def save_fill(self, fill: Fill) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def save_backtest_summary(self, summary: BacktestSummary) -> None:
        raise NotImplementedError

    def save_ml_recommendation(self, recommendation: MlRecommendation) -> None:
        raise NotImplementedError


@dataclass
class InMemoryStateRepository(StateRepository):
    orders: list[Order] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    backtest_summaries: list[BacktestSummary] = field(default_factory=list)
    ml_recommendations: list[MlRecommendation] = field(default_factory=list)

    def save_order(self, order: Order) -> None:
        self.orders.append(order)

    def save_trade(self, trade: Trade) -> None:
        self.trades.append(trade)

    def save_fill(self, fill: Fill) -> None:
        self.fills.append(fill)

    def close(self) -> None:
        return None

    def save_backtest_summary(self, summary: BacktestSummary) -> None:
        self.backtest_summaries.append(summary)

    def save_ml_recommendation(self, recommendation: MlRecommendation) -> None:
        self.ml_recommendations.append(recommendation)
