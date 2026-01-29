from __future__ import annotations

import argparse
import importlib
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from config.loader import load_config
from strategies.registry import load_strategies


@dataclass
class PreflightReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    def ok(self) -> bool:
        return not self.errors

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_info(self, message: str) -> None:
        self.info.append(message)

    def render(self) -> str:
        lines: list[str] = []
        if self.errors:
            lines.append("Errors:")
            lines.extend([f"  - {msg}" for msg in self.errors])
        if self.warnings:
            lines.append("Warnings:")
            lines.extend([f"  - {msg}" for msg in self.warnings])
        if self.info:
            lines.append("Info:")
            lines.extend([f"  - {msg}" for msg in self.info])
        return "\n".join(lines) if lines else "Preflight OK"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CryptoTrader preflight checks")
    parser.add_argument("--config", default="config/config.ini", help="Path to config.ini")
    return parser.parse_args()


def _check_python(report: PreflightReport) -> None:
    if sys.version_info < (3, 11):
        report.add_error("Python 3.11+ is required")
    else:
        report.add_info(f"Python version OK: {sys.version_info.major}.{sys.version_info.minor}")


def _check_timezone(report: PreflightReport) -> None:
    offset = -time_offset_seconds()
    if offset != 0:
        report.add_warning("System timezone is not UTC; use UTC for production")


def time_offset_seconds() -> int:
    if hasattr(time, "altzone"):
        return time.altzone if time.localtime().tm_isdst else time.timezone
    return 0


def _check_dependencies(report: PreflightReport, mode: str) -> None:
    required = ["pandas", "pyarrow"]
    optional = ["rich"]
    if mode in {"forward", "live"}:
        required = []
        optional = ["rich", "requests", "websockets"]
    for pkg in required:
        if importlib.util.find_spec(pkg) is None:
            report.add_error(f"Missing dependency: {pkg}")
    for pkg in optional:
        if importlib.util.find_spec(pkg) is None:
            report.add_warning(f"Optional dependency not installed: {pkg}")


def _check_paths(report: PreflightReport, paths: list[Path]) -> None:
    for path in paths:
        try:
            path.mkdir(parents=True, exist_ok=True)
            test_file = path / ".write_check"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
        except OSError:
            report.add_error(f"Path not writable: {path}")


def _check_exchange_credentials(report: PreflightReport, mode: str, api_key: str, api_secret: str) -> None:
    if mode == "live":
        if not api_key or not api_secret:
            report.add_error("Live mode requires API key/secret")
    if mode != "live" and (not api_key or not api_secret):
        report.add_warning("API keys missing; live mode will fail")


def _check_strategies(report: PreflightReport, strategy_specs: tuple[str, ...]) -> None:
    try:
        load_strategies(strategy_specs)
    except Exception as exc:  # noqa: BLE001
        report.add_error(f"Strategy load failed: {exc}")


def _check_exchange_impl(report: PreflightReport, exchange: str, mode: str) -> None:
    if mode == "live":
        report.add_warning(f"Exchange adapter implementations for {exchange} must be completed")


def main() -> int:
    args = parse_args()
    report = PreflightReport()
    _check_python(report)

    config_path = Path(args.config).expanduser().resolve()
    try:
        config = load_config(config_path)
    except Exception as exc:  # noqa: BLE001
        report.add_error(f"Config load failed: {exc}")
        print(report.render())
        return 1

    _check_timezone(report)
    _check_dependencies(report, config.runtime.mode)
    _check_paths(report, [config.paths.data_dir, config.paths.state_dir, config.paths.logs_dir])
    _check_exchange_credentials(report, config.runtime.mode, config.exchange.api_key, config.exchange.api_secret)
    _check_strategies(report, config.runtime.strategy_modules)
    _check_exchange_impl(report, config.runtime.exchange, config.runtime.mode)

    print(report.render())
    return 0 if report.ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
