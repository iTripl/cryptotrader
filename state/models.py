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
    price: float
    quantity: float
    fee: float


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
class MlRecommendation:
    run_id: str
    created_at: int
    payload_json: str
