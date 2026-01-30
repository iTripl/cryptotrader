from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from state.models import PortfolioState, Position


@dataclass(frozen=True)
class ExposureSnapshot:
    gross_notional: float
    net_notional: float
    gross_exposure: float
    correlation: float


def compute_exposure(
    open_positions: Mapping[str, Position],
    last_prices: Mapping[str, float],
    equity: float,
) -> ExposureSnapshot:
    gross_notional = 0.0
    net_notional = 0.0
    for position in open_positions.values():
        price = last_prices.get(position.symbol, position.entry_price)
        notional = float(price) * float(position.quantity)
        gross_notional += abs(notional)
        if position.side == "LONG":
            net_notional += notional
        else:
            net_notional -= notional

    if equity <= 0:
        gross_exposure = float("inf")
    else:
        gross_exposure = gross_notional / equity

    if gross_notional > 0:
        correlation = abs(net_notional) / gross_notional
    else:
        correlation = 0.0

    return ExposureSnapshot(
        gross_notional=gross_notional,
        net_notional=net_notional,
        gross_exposure=gross_exposure,
        correlation=correlation,
    )


def update_daily_drawdown(portfolio: PortfolioState, timestamp: int) -> None:
    if timestamp <= 0:
        return
    day = int(timestamp // 86400)
    if portfolio.daily_day != day or portfolio.daily_start_equity <= 0:
        portfolio.daily_day = day
        portfolio.daily_start_equity = portfolio.equity
        portfolio.daily_peak_equity = portfolio.equity

    if portfolio.equity > portfolio.daily_peak_equity:
        portfolio.daily_peak_equity = portfolio.equity

    if portfolio.daily_peak_equity > 0:
        portfolio.daily_drawdown = (portfolio.daily_peak_equity - portfolio.equity) / portfolio.daily_peak_equity
    else:
        portfolio.daily_drawdown = 0.0
