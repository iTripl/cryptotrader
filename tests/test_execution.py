from execution.execution_engine import LiveExecutionEngine
from execution.order_manager import OrderManager
from signals.signal import Signal
from state.models import PortfolioState


class DummyRest:
    def __init__(self, min_qty=None, min_notional=None) -> None:
        self._constraints = {"min_qty": min_qty, "min_notional": min_notional}
        self.place_order_called = False

    def get_instrument_constraints(self, symbol: str):
        return self._constraints

    def place_order(self, order):
        self.place_order_called = True
        return {"result": {"orderId": "123", "orderLinkId": order.client_order_id}}


class DummyAdapter:
    def __init__(self, rest) -> None:
        self.rest = rest


def test_live_execution_rejects_below_min_notional() -> None:
    rest = DummyRest(min_notional=100.0)
    engine = LiveExecutionEngine(DummyAdapter(rest), OrderManager())
    signal = Signal(
        symbol="BTCUSDT",
        direction="LONG",
        confidence=0.9,
        horizon="5m",
        volatility_regime="normal",
        metadata={"price": 50.0},
    )
    portfolio = PortfolioState(equity=1000.0, daily_drawdown=0.0, consecutive_losses=0)
    result = engine.execute(signal, decision_size=1.0, portfolio=portfolio)
    assert result.response.status == "rejected"
    assert not rest.place_order_called


def test_live_execution_submits_when_constraints_ok() -> None:
    rest = DummyRest(min_notional=10.0)
    engine = LiveExecutionEngine(DummyAdapter(rest), OrderManager())
    signal = Signal(
        symbol="BTCUSDT",
        direction="LONG",
        confidence=0.9,
        horizon="5m",
        volatility_regime="normal",
        metadata={"price": 50.0},
    )
    portfolio = PortfolioState(equity=1000.0, daily_drawdown=0.0, consecutive_losses=0)
    result = engine.execute(signal, decision_size=1.0, portfolio=portfolio)
    assert result.response.status == "submitted"
    assert rest.place_order_called
