from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.config_schema import LoggingConfig


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "trace_id"):
            payload["trace_id"] = getattr(record, "trace_id")
        if hasattr(record, "extra"):
            payload["extra"] = getattr(record, "extra")
        return json.dumps(payload, ensure_ascii=True)


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return f"[{record.levelname}] {record.name}: {record.getMessage()}"


def _ensure_log_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _as_log_dir() -> Path:
    value = os.environ.get("CRYPTOTRADER_LOG_DIR")
    if value:
        return Path(value)
    return Path("Logs")


def configure_logging(config: LoggingConfig, log_dir: Path | None = None) -> None:
    log_dir = log_dir or _as_log_dir()
    _ensure_log_dir(log_dir)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(config.level)

    file_handler = logging.FileHandler(log_dir / "system.log")
    file_handler.setLevel(config.level)
    file_handler.setFormatter(JsonFormatter() if config.json else ConsoleFormatter())
    root.addHandler(file_handler)

    error_handler = logging.FileHandler(log_dir / "errors.log")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JsonFormatter() if config.json else ConsoleFormatter())
    root.addHandler(error_handler)

    execution_logger = logging.getLogger("execution")
    exec_handler = logging.FileHandler(log_dir / "execution.log")
    exec_handler.setLevel(config.level)
    exec_handler.setFormatter(JsonFormatter() if config.json else ConsoleFormatter())
    execution_logger.addHandler(exec_handler)
    execution_logger.propagate = True

    strategy_logger = logging.getLogger("strategies")
    strat_handler = logging.FileHandler(log_dir / "strategies.log")
    strat_handler.setLevel(config.level)
    strat_handler.setFormatter(JsonFormatter() if config.json else ConsoleFormatter())
    strategy_logger.addHandler(strat_handler)
    strategy_logger.propagate = True

    if config.console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(config.level)
        console_handler.setFormatter(ConsoleFormatter())
        root.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_extra(logger: logging.Logger, message: str, trace_id: str | None = None, **extra: Any) -> None:
    safe_extra = {}
    for key, value in extra.items():
        if is_dataclass(value):
            safe_extra[key] = asdict(value)
        else:
            safe_extra[key] = value
    payload = {"extra": safe_extra}
    if trace_id:
        payload["trace_id"] = trace_id
    logger.info(message, extra=payload)
