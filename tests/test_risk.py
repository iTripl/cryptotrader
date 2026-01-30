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
        atr_period=14,
        atr_sl_mult=1.5,
        atr_tp_mult=3.0,
        atr_trailing_mult=1.0,
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


def test_risk_manager_caps_by_exposure() -> None:
    risk = RiskConfig(
        initial_equity=10000,
        risk_per_trade=0.2,
        max_daily_drawdown=0.2,
        max_consecutive_losses=10,
        min_expectancy=0.0,
        correlation_limit=0.7,
        exposure_limit=0.25,
        volatility_adjustment_high=1.0,
        volatility_adjustment_normal=1.0,
        volatility_adjustment_low=1.0,
        stop_loss_pct=0.0,
        take_profit_pct=0.0,
        trailing_take_profit_pct=0.0,
        atr_period=0,
        atr_sl_mult=0.0,
        atr_tp_mult=0.0,
        atr_trailing_mult=0.0,
    )
    manager = DefaultRiskManager(risk)
    portfolio = PortfolioState(
        equity=1000,
        daily_drawdown=0.0,
        consecutive_losses=0,
        gross_exposure=0.2,
        expectancy=1.0,
    )
    signal = Signal(
        symbol="BTCUSDT",
        direction="LONG",
        confidence=1.0,
        horizon="5m",
        volatility_regime="normal",
        metadata={},
    )
    decision = manager.approve(signal, portfolio)
    assert decision.approved
    assert decision.size == 50.0


def test_risk_manager_rejects_no_equity() -> None:
    risk = RiskConfig(
        initial_equity=10000,
        risk_per_trade=0.01,
        max_daily_drawdown=0.1,
        max_consecutive_losses=3,
        min_expectancy=0.0,
        correlation_limit=0.7,
        exposure_limit=0.25,
        volatility_adjustment_high=1.0,
        volatility_adjustment_normal=1.0,
        volatility_adjustment_low=1.0,
        stop_loss_pct=0.0,
        take_profit_pct=0.0,
        trailing_take_profit_pct=0.0,
        atr_period=0,
        atr_sl_mult=0.0,
        atr_tp_mult=0.0,
        atr_trailing_mult=0.0,
    )
    manager = DefaultRiskManager(risk)
    portfolio = PortfolioState(equity=0.0, daily_drawdown=0.0, consecutive_losses=0)
    signal = Signal(
        symbol="BTCUSDT",
        direction="LONG",
        confidence=0.5,
        horizon="5m",
        volatility_regime="normal",
        metadata={},
    )
    decision = manager.approve(signal, portfolio)
    assert not decision.approved
    assert decision.reason == "no_equity"
