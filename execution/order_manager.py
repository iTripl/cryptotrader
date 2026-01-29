from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from signals.signal import Signal


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: str
    quantity: float
    order_type: str
    price: float | None
    signal_id: str
    client_order_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True)
class OrderResponse:
    order_id: str
    status: str
    client_order_id: str
    filled_qty: float = 0.0


class OrderManager:
    def build_order(self, signal: Signal, size: float) -> OrderRequest:
        side = "BUY" if signal.direction == "LONG" else "SELL"
        return OrderRequest(
            symbol=signal.symbol,
            side=side,
            quantity=size,
            order_type="MARKET",
            price=None,
            signal_id=signal.signal_id,
        )
