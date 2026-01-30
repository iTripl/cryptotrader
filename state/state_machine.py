from __future__ import annotations

from dataclasses import dataclass

from state.models import Order, OrderState


@dataclass
class OrderStateMachine:
    order: Order

    def transition(self, new_state: OrderState) -> Order:
        valid = {
            OrderState.CREATED: {OrderState.SUBMITTED, OrderState.CANCELED, OrderState.REJECTED},
            OrderState.SUBMITTED: {
                OrderState.PARTIALLY_FILLED,
                OrderState.FILLED,
                OrderState.CANCELED,
                OrderState.REJECTED,
            },
            OrderState.PARTIALLY_FILLED: {OrderState.FILLED, OrderState.CANCELED, OrderState.REJECTED},
            OrderState.FILLED: {OrderState.CLOSED},
            OrderState.CLOSED: set(),
            OrderState.CANCELED: set(),
            OrderState.REJECTED: set(),
        }
        if new_state not in valid[self.order.status]:
            raise ValueError(f"Invalid state transition {self.order.status} -> {new_state}")
        self.order = Order(
            order_id=self.order.order_id,
            client_order_id=self.order.client_order_id,
            symbol=self.order.symbol,
            side=self.order.side,
            quantity=self.order.quantity,
            status=new_state,
            signal_id=self.order.signal_id,
        )
        return self.order
