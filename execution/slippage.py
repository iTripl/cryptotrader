from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlippageResult:
    expected_price: float
    executed_price: float
    slippage_bps: float


def calculate_slippage(expected_price: float, executed_price: float) -> SlippageResult:
    if expected_price == 0:
        return SlippageResult(expected_price, executed_price, 0.0)
    slippage = (executed_price - expected_price) / expected_price * 10000
    return SlippageResult(expected_price, executed_price, slippage)
