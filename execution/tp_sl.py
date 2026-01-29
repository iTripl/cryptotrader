from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TakeProfitStopLossPlan:
    fixed_tp: float
    fixed_sl: float
    trailing_tp: float
    trailing_sl: float


def build_tp_sl(
    entry_price: float,
    tp_pct: float,
    sl_pct: float,
    trailing_tp_pct: float,
    trailing_sl_pct: float,
) -> TakeProfitStopLossPlan:
    fixed_tp = entry_price * (1 + tp_pct)
    fixed_sl = entry_price * (1 - sl_pct)
    trailing_tp = entry_price * (1 + trailing_tp_pct)
    trailing_sl = entry_price * (1 - trailing_sl_pct)
    return TakeProfitStopLossPlan(fixed_tp, fixed_sl, trailing_tp, trailing_sl)
