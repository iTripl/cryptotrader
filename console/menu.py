from __future__ import annotations

from dataclasses import replace

from config.config_schema import AppConfig, SymbolConfig
from strategies.registry import discover_strategy_specs


class ConsoleMenu:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def run(self) -> AppConfig:
        print("=== CryptoTrader Console ===")
        mode = self._prompt("Mode (backtest/forward/live)", self.config.runtime.mode)
        exchange = self._prompt("Exchange (bybit/binance/okx)", self.config.runtime.exchange)
        symbols = self._prompt("Symbols (comma-separated)", ",".join(self.config.symbols.symbols))
        timeframes = self._prompt("Timeframes (comma-separated)", ",".join(self.config.symbols.timeframes))
        available = discover_strategy_specs() or list(self.config.runtime.strategy_modules)
        strategies = self._select_strategies(tuple(available), self.config.runtime.strategy_modules)
        risk_profile = self._prompt("Risk profile", self.config.runtime.risk_profile)

        updated_symbols = SymbolConfig(
            symbols=tuple(s.strip() for s in symbols.split(",") if s.strip()),
            timeframes=tuple(t.strip() for t in timeframes.split(",") if t.strip()),
        )

        runtime = replace(
            self.config.runtime,
            mode=mode,
            exchange=exchange,
            strategy_modules=strategies,
            risk_profile=risk_profile,
        )
        return replace(self.config, runtime=runtime, symbols=updated_symbols)

    @staticmethod
    def _prompt(label: str, default: str) -> str:
        value = input(f"{label} [{default}]: ").strip()
        return value or default

    @staticmethod
    def _select_strategies(available: tuple[str, ...], selected: tuple[str, ...]) -> tuple[str, ...]:
        if not available:
            return selected
        print("Select strategies (comma-separated numbers).")
        for idx, spec in enumerate(available, start=1):
            mark = "*" if spec in selected else " "
            print(f"  {idx}) [{mark}] {spec}")
        raw = input("Strategies [default=current]: ").strip().lower()
        if not raw or raw == "current":
            return selected
        if raw == "all":
            return available
        try:
            indices = {int(item.strip()) for item in raw.split(",") if item.strip()}
        except ValueError:
            print("Invalid selection, using default.")
            return selected
        selected = [spec for idx, spec in enumerate(available, start=1) if idx in indices]
        return tuple(selected) if selected else selected
