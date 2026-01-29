from __future__ import annotations

from dataclasses import dataclass

from config.config_schema import RiskConfig
from risk.sizing import position_size
from signals.signal import Signal
from state.models import PortfolioState


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str | None
    size: float


class RiskManager:
    def approve(self, signal: Signal, portfolio: PortfolioState) -> RiskDecision:
        raise NotImplementedError


class DefaultRiskManager(RiskManager):
    def __init__(self, config: RiskConfig) -> None:
        self.config = config

    def approve(self, signal: Signal, portfolio: PortfolioState) -> RiskDecision:
        if portfolio.consecutive_losses >= self.config.max_consecutive_losses:
            return RiskDecision(False, "max_consecutive_losses", 0.0)
        if portfolio.daily_drawdown >= self.config.max_daily_drawdown:
            return RiskDecision(False, "max_daily_drawdown", 0.0)
        existing = portfolio.open_positions.get(signal.symbol)
        if existing:
            if signal.direction == "FLAT" or signal.direction != existing.side:
                return RiskDecision(True, "exit_position", existing.quantity)
            return RiskDecision(False, "existing_position", 0.0)
        if portfolio.gross_exposure >= self.config.exposure_limit:
            return RiskDecision(False, "exposure_limit", 0.0)
        if portfolio.correlation >= self.config.correlation_limit:
            return RiskDecision(False, "correlation_limit", 0.0)
        if portfolio.expectancy < self.config.min_expectancy:
            return RiskDecision(False, "min_expectancy", 0.0)
        if signal.confidence < 0.01:
            return RiskDecision(False, "low_confidence", 0.0)

        volatility_adjustment = self._volatility_adjustment(signal.volatility_regime)
        size = position_size(
            equity=portfolio.equity,
            risk_per_trade=self.config.risk_per_trade,
            confidence=signal.confidence,
            volatility_adjustment=volatility_adjustment,
        )
        return RiskDecision(True, None, size)

    def _volatility_adjustment(self, regime: str) -> float:
        if regime == "high":
            return self.config.volatility_adjustment_high
        if regime == "low":
            return self.config.volatility_adjustment_low
        return self.config.volatility_adjustment_normal
