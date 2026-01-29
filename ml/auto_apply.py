from __future__ import annotations

import configparser
from pathlib import Path

from ml.backtest_analyzer import RecommendationResult


def apply_recommendation(config_path: Path, result: RecommendationResult) -> None:
    parser = configparser.ConfigParser()
    parser.read(config_path)

    if "risk" not in parser:
        parser["risk"] = {}
    parser["risk"]["stop_loss_pct"] = f"{result.stop_loss_pct:.6f}"
    parser["risk"]["take_profit_pct"] = f"{result.take_profit_pct:.6f}"

    for strategy, confidence in result.strategy_confidence.items():
        section = f"strategy.{strategy}"
        if section not in parser:
            continue
        parser[section]["confidence"] = f"{confidence:.4f}"

    with config_path.open("w", encoding="utf-8") as handle:
        parser.write(handle)
