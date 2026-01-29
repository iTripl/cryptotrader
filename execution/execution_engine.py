from __future__ import annotations

from dataclasses import dataclass

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


class LiveExecutionEngine(ExecutionEngine):
    def __init__(self, adapter: ExchangeAdapter, order_manager: OrderManager) -> None:
        self.adapter = adapter
        self.order_manager = order_manager

    def execute(self, signal: Signal, decision_size: float, portfolio: PortfolioState) -> ExecutionResult:
        order = self.order_manager.build_order(signal, decision_size)
        logger.info("submitting order %s", order.client_order_id)
        response = self.adapter.rest.place_order(order)
        return ExecutionResult(order=order, response=response)


class PaperExecutionEngine(ExecutionEngine):
    def __init__(self, order_manager: OrderManager) -> None:
        self.order_manager = order_manager

    def execute(self, signal: Signal, decision_size: float, portfolio: PortfolioState) -> ExecutionResult:
        order = self.order_manager.build_order(signal, decision_size)
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
