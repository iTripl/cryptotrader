from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from uuid import uuid4


class OrderState(str, Enum):
    CREATED = "created"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CLOSED = "closed"
    CANCELED = "canceled"
    REJECTED = "rejected"


def order_state_from_status(status: str) -> OrderState:
    status_lower = status.lower()
    mapping = {
        "created": OrderState.CREATED,
        "submitted": OrderState.SUBMITTED,
        "partially_filled": OrderState.PARTIALLY_FILLED,
        "partial": OrderState.PARTIALLY_FILLED,
        "filled": OrderState.FILLED,
        "closed": OrderState.CLOSED,
        "canceled": OrderState.CANCELED,
        "cancelled": OrderState.CANCELED,
        "rejected": OrderState.REJECTED,
        "error": OrderState.REJECTED,
        "failed": OrderState.REJECTED,
    }
    return mapping.get(status_lower, OrderState.SUBMITTED)


@dataclass(frozen=True)
class Order:
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    quantity: float
    status: OrderState
    signal_id: str


@dataclass(frozen=True)
class Fill:
    fill_id: str
    order_id: str
    symbol: str
    side: str
    price: float
    quantity: float
    fee: float
    timestamp: int


@dataclass(frozen=True)
class Trade:
    trade_id: str
    order_id: str
    symbol: str
    entry_price: float
    exit_price: float | None
    quantity: float
    pnl: float
    fees: float
    slippage_bps: float
    strategy: str | None = None


@dataclass(frozen=True)
class TradeMetrics:
    trade_id: str
    symbol: str
    strategy: str | None
    notional: float
    gross_pnl: float
    net_pnl: float
    return_pct: float
    fee_pct: float
    slippage_bps: float


@dataclass
class Position:
    symbol: str
    quantity: float
    entry_price: float
    side: str
    max_price: float
    min_price: float


@dataclass
class PortfolioState:
    equity: float
    daily_drawdown: float
    consecutive_losses: int
    open_positions: dict[str, Position] = field(default_factory=dict)
    gross_exposure: float = 0.0
    correlation: float = 0.0
    expectancy: float = 0.0
    daily_start_equity: float = 0.0
    daily_peak_equity: float = 0.0
    daily_day: int = 0
    trace_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True)
class BacktestSummary:
    run_id: str
    started_at: int
    finished_at: int
    exchange: str
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    total_signals: int
    total_orders: int
    total_trades: int
    final_equity: float
    stats_json: str


@dataclass(frozen=True)
class BacktestMetrics:
    run_id: str
    total_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    payoff_ratio: float
    expectancy: float
    max_drawdown: float
    pnl_value: float
    pnl_pct: float
    cagr: float
    calmar_ratio: float
    sharpe: float
    sortino: float


@dataclass(frozen=True)
class MlRecommendation:
    run_id: str
    created_at: int
    payload_json: str
