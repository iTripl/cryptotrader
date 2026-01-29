from __future__ import annotations


def position_size(
    equity: float,
    risk_per_trade: float,
    confidence: float,
    volatility_adjustment: float,
) -> float:
    return equity * risk_per_trade * confidence * volatility_adjustment
