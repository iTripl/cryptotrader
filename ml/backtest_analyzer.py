from __future__ import annotations

import json
import time
from dataclasses import dataclass
from uuid import uuid4

from config.config_schema import AppConfig
from state.models import MlRecommendation, Trade


@dataclass(frozen=True)
class RecommendationResult:
    stop_loss_pct: float
    take_profit_pct: float
    strategy_confidence: dict[str, float]
    notes: list[str]


class BacktestAnalyzer:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def analyze(self, trades: list[Trade], initial_equity: float, final_equity: float) -> RecommendationResult:
        notes: list[str] = []
        if len(trades) < self.config.ml.min_trades:
            notes.append("insufficient trades for ML moderation")
            return RecommendationResult(
                stop_loss_pct=self.config.risk.stop_loss_pct,
                take_profit_pct=self.config.risk.take_profit_pct,
                strategy_confidence=self._current_strategy_confidence(),
                notes=notes,
            )

        pnls = [t.pnl for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [abs(p) for p in pnls if p < 0]
        win_rate = len(wins) / len(pnls) if pnls else 0.0
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        payoff = (avg_win / avg_loss) if avg_loss else 0.0

        stop_loss = self.config.risk.stop_loss_pct
        take_profit = self.config.risk.take_profit_pct
        adj = self.config.ml.max_adjustment_pct

        if payoff < 1.0:
            stop_loss = stop_loss * (1 - adj / 2)
            take_profit = take_profit * (1 + adj)
            notes.append("low payoff ratio: tightening SL, widening TP")
        elif win_rate < self.config.ml.target_win_rate:
            stop_loss = stop_loss * (1 + adj / 2)
            take_profit = take_profit * (1 - adj / 2)
            notes.append("win rate below target: loosening SL, tightening TP")
        else:
            notes.append("performance within target bands")

        stop_loss = _clamp(stop_loss, 0.001, 0.5)
        take_profit = _clamp(take_profit, 0.001, 1.0)

        strategy_conf = self._moderate_strategy_confidence(trades)
        return RecommendationResult(
            stop_loss_pct=stop_loss,
            take_profit_pct=take_profit,
            strategy_confidence=strategy_conf,
            notes=notes,
        )

    def to_recommendation(self, result: RecommendationResult) -> MlRecommendation:
        payload = {
            "stop_loss_pct": result.stop_loss_pct,
            "take_profit_pct": result.take_profit_pct,
            "strategy_confidence": result.strategy_confidence,
            "notes": result.notes,
        }
        return MlRecommendation(
            run_id=str(uuid4()),
            created_at=int(time.time()),
            payload_json=json.dumps(payload),
        )

    def _current_strategy_confidence(self) -> dict[str, float]:
        confidences: dict[str, float] = {}
        for key, params in self.config.strategy_params.items():
            if "confidence" in params:
                try:
                    confidences[key] = float(params["confidence"])
                except ValueError:
                    continue
        return confidences

    def _moderate_strategy_confidence(self, trades: list[Trade]) -> dict[str, float]:
        grouped: dict[str, list[Trade]] = {}
        for trade in trades:
            if not trade.strategy:
                continue
            if trade.strategy not in self.config.strategy_params:
                continue
            grouped.setdefault(trade.strategy, []).append(trade)

        current = self._current_strategy_confidence()
        adjusted: dict[str, float] = {}
        for strategy, strat_trades in grouped.items():
            wins = len([t for t in strat_trades if t.pnl > 0])
            total = len(strat_trades)
            win_rate = wins / total if total else 0.0
            confidence = current.get(strategy, 0.5)
            if win_rate < self.config.ml.target_win_rate - 0.05:
                confidence *= 0.9
            elif win_rate > self.config.ml.target_win_rate + 0.05:
                confidence *= 1.05
            adjusted[strategy] = _clamp(confidence, 0.1, 0.95)
        return adjusted


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
