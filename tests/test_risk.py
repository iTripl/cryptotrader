from config.config_schema import RiskConfig
from risk.risk_manager import DefaultRiskManager
from signals.signal import Signal
from state.models import PortfolioState


def test_risk_manager_blocks_consecutive_losses() -> None:
    risk = RiskConfig(
        initial_equity=10000,
        risk_per_trade=0.01,
        max_daily_drawdown=0.05,
        max_consecutive_losses=3,
        min_expectancy=0.0,
        correlation_limit=0.7,
        exposure_limit=0.25,
        volatility_adjustment_high=0.6,
        volatility_adjustment_normal=1.0,
        volatility_adjustment_low=1.2,
        stop_loss_pct=0.02,
        take_profit_pct=0.04,
        trailing_take_profit_pct=0.02,
    )
    manager = DefaultRiskManager(risk)
    portfolio = PortfolioState(equity=10000, daily_drawdown=0.0, consecutive_losses=3)
    signal = Signal(
        symbol="BTCUSDT",
        direction="LONG",
        confidence=0.8,
        horizon="5m",
        volatility_regime="normal",
        metadata={},
    )
    decision = manager.approve(signal, portfolio)
    assert not decision.approved
