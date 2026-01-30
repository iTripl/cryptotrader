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
        symbols = self._prompt("Symbols (comma-separated)", ",".join(self.config.symbols.symbols))
        timeframes = self._prompt("Timeframes (comma-separated)", ",".join(self.config.symbols.timeframes))
        available = discover_strategy_specs() or list(self.config.runtime.strategy_modules)
        strategies = self._select_strategies(tuple(available), self.config.runtime.strategy_modules)

        updated_symbols = SymbolConfig(
            symbols=tuple(s.strip() for s in symbols.split(",") if s.strip()),
            timeframes=tuple(t.strip() for t in timeframes.split(",") if t.strip()),
        )

        runtime = replace(
            self.config.runtime,
            mode=mode,
            strategy_modules=strategies,
        )
        updated = replace(self.config, runtime=runtime, symbols=updated_symbols)
        updated.validate()
        self._persist_config(updated)
        return updated

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

    @staticmethod
    def _persist_config(config: AppConfig) -> None:
        path = config.config_path
        updates = {
            "runtime": {
                "mode": config.runtime.mode,
                "strategy_modules": ",".join(config.runtime.strategy_modules),
            },
            "symbols": {
                "symbols": ",".join(config.symbols.symbols),
                "timeframes": ",".join(config.symbols.timeframes),
            },
        }
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        section = None
        out: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                section = stripped[1:-1].lower()
                out.append(line)
                continue
            if section in updates and "=" in line:
                key = line.split("=", 1)[0].strip()
                if key in updates[section]:
                    out.append(f"{key} = {updates[section][key]}\n")
                    continue
            out.append(line)
        path.write_text("".join(out), encoding="utf-8")
