from __future__ import annotations

from dataclasses import dataclass, replace

from execution.order_manager import OrderManager, OrderRequest, OrderResponse
from exchanges.base_exchange import ExchangeAdapter
from signals.signal import Signal
from state.models import PortfolioState
from utils.logger import get_logger


logger = get_logger("execution.engine")


@dataclass(frozen=True)
class ExecutionResult:
    order: OrderRequest
    response: OrderResponse


class ExecutionEngine:
    def execute(self, signal: Signal, decision_size: float, portfolio: PortfolioState) -> ExecutionResult:
        raise NotImplementedError

    def handshake(self, symbol: str, quantity: float) -> None:
        return None

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        return False


class LiveExecutionEngine(ExecutionEngine):
    def __init__(self, adapter: ExchangeAdapter, order_manager: OrderManager) -> None:
        self.adapter = adapter
        self.order_manager = order_manager

    def execute(self, signal: Signal, decision_size: float, portfolio: PortfolioState) -> ExecutionResult:
        order = self.order_manager.build_order(signal, decision_size)
        constraints = {}
        if hasattr(self.adapter.rest, "get_instrument_constraints"):
            try:
                constraints = self.adapter.rest.get_instrument_constraints(order.symbol)
            except Exception as exc:  # noqa: BLE001
                logger.debug("instrument constraints unavailable: %s", exc)
                constraints = {}
        min_qty = constraints.get("min_qty") if isinstance(constraints, dict) else None
        min_notional = constraints.get("min_notional") if isinstance(constraints, dict) else None
        price = signal.metadata.get("price")
        required_qty = order.quantity
        if min_notional and price:
            try:
                required_qty = max(required_qty, float(min_notional) / float(price))
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        if min_qty:
            try:
                required_qty = max(required_qty, float(min_qty))
            except (TypeError, ValueError):
                pass
        if required_qty > order.quantity:
            logger.warning(
                "order rejected by constraints symbol=%s qty=%s min_qty=%s min_notional=%s price=%s",
                order.symbol,
                order.quantity,
                min_qty,
                min_notional,
                price,
            )
            response = OrderResponse(
                order_id=order.client_order_id,
                status="rejected",
                client_order_id=order.client_order_id,
            )
            return ExecutionResult(order=order, response=response)
        logger.debug(
            "live order prepared symbol=%s side=%s qty=%s type=%s",
            order.symbol,
            order.side,
            order.quantity,
            order.order_type,
        )
        logger.info("submitting order %s", order.client_order_id)
        try:
            response = self.adapter.rest.place_order(order)
        except Exception as exc:  # noqa: BLE001
            logger.warning("order submission failed: %s", exc)
            response = OrderResponse(
                order_id=order.client_order_id,
                status="rejected",
                client_order_id=order.client_order_id,
            )
            return ExecutionResult(order=order, response=response)
        order_id = response.get("result", {}).get("orderId") if isinstance(response, dict) else None
        client_order_id = response.get("result", {}).get("orderLinkId") if isinstance(response, dict) else None
        if order_id:
            response = OrderResponse(
                order_id=order_id,
                status="submitted",
                client_order_id=client_order_id or order.client_order_id,
            )
        return ExecutionResult(order=order, response=response)

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        if not order_id:
            return False
        if not hasattr(self.adapter.rest, "cancel_order"):
            return False
        try:
            self.adapter.rest.cancel_order(order_id, symbol)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cancel order failed %s (%s): %s", order_id, symbol, exc)
            return False
        return True

    def handshake(self, symbol: str, quantity: float) -> None:
        if quantity <= 0:
            return
        buy_order = OrderRequest(
            symbol=symbol,
            side="BUY",
            quantity=quantity,
            order_type="MARKET",
            price=None,
            signal_id="demo_handshake_buy",
        )
        sell_order = OrderRequest(
            symbol=symbol,
            side="SELL",
            quantity=quantity,
            order_type="MARKET",
            price=None,
            signal_id="demo_handshake_sell",
        )
        self.adapter.rest.place_order(buy_order)
        self.adapter.rest.place_order(sell_order)


class PaperExecutionEngine(ExecutionEngine):
    def __init__(self, order_manager: OrderManager) -> None:
        self.order_manager = order_manager

    def execute(self, signal: Signal, decision_size: float, portfolio: PortfolioState) -> ExecutionResult:
        order = self.order_manager.build_order(signal, decision_size)
        logger.debug(
            "paper order filled symbol=%s side=%s qty=%s type=%s",
            order.symbol,
            order.side,
            order.quantity,
            order.order_type,
        )
        response = OrderResponse(order_id=order.client_order_id, status="filled", client_order_id=order.client_order_id)
        return ExecutionResult(order=order, response=response)


class BacktestExecutionEngine(ExecutionEngine):
    def __init__(self, order_manager: OrderManager, fee_bps: float, slippage_bps: float) -> None:
        self.order_manager = order_manager
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps

    def execute(self, signal: Signal, decision_size: float, portfolio: PortfolioState) -> ExecutionResult:
        order = self.order_manager.build_order(signal, decision_size)
        response = OrderResponse(order_id=order.client_order_id, status="filled", client_order_id=order.client_order_id)
        return ExecutionResult(order=order, response=response)
