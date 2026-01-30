from __future__ import annotations

import configparser
from pathlib import Path

from config.config_schema import (
    AppConfig,
    PathsConfig,
    ensure_sections,
    parse_backtest,
    parse_exchange,
    parse_forward,
    parse_live,
    parse_logging,
    parse_paths,
    parse_risk,
    parse_runtime,
    parse_strategy,
    parse_symbols,
)
from config.secrets import load_env_file, resolve_mapping


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    parser = configparser.ConfigParser()
    strategy_path = path.parent / "strategies.ini"
    parser.read([str(path), str(strategy_path)])

    if "secrets" in parser and "env_file" in parser["secrets"]:
        env_path = Path(parser["secrets"]["env_file"]).expanduser()
        if not env_path.is_absolute():
            env_path = (path.parent / env_path).resolve()
        load_env_file(env_path)

    required = [
        "runtime",
        "exchange",
        "symbols",
        "risk",
        "strategy",
        "paths",
        "logging",
        "backtest",
        "forward",
        "live",
    ]
    ensure_sections(parser, required)

    runtime = parse_runtime(resolve_mapping(dict(parser["runtime"])))
    exchange = parse_exchange(resolve_mapping(dict(parser["exchange"])))
    symbols = parse_symbols(resolve_mapping(dict(parser["symbols"])))
    risk = parse_risk(resolve_mapping(dict(parser["risk"])))
    strategy = parse_strategy(resolve_mapping(dict(parser["strategy"])))
    paths = parse_paths(resolve_mapping(dict(parser["paths"])))
    logging_cfg = parse_logging(resolve_mapping(dict(parser["logging"])))
    backtest = parse_backtest(resolve_mapping(dict(parser["backtest"])))
    forward = parse_forward(resolve_mapping(dict(parser["forward"])))
    live = parse_live(resolve_mapping(dict(parser["live"])))

    base_dir = _resolve_base_dir(path)
    paths = PathsConfig(
        data_dir=_resolve_path(base_dir, paths.data_dir),
        state_dir=_resolve_path(base_dir, paths.state_dir),
        state_db=_resolve_path(base_dir, paths.state_db),
        logs_dir=_resolve_path(base_dir, paths.logs_dir),
    )

    strategy_params = _parse_strategy_params(parser)

    config = AppConfig(
        config_path=path.resolve(),
        runtime=runtime,
        exchange=exchange,
        symbols=symbols,
        risk=risk,
        strategy=strategy,
        strategy_params=strategy_params,
        paths=paths,
        logging=logging_cfg,
        backtest=backtest,
        forward=forward,
        live=live,
    )
    config.validate()
    return config


def _resolve_path(base_dir: Path, target: Path) -> Path:
    if target.is_absolute():
        return target
    return (base_dir / target).resolve()


def _resolve_base_dir(path: Path) -> Path:
    base = path.parent
    if base.name == "config":
        return base.parent
    return base


def _parse_strategy_params(parser: configparser.ConfigParser) -> dict[str, dict[str, str]]:
    params: dict[str, dict[str, str]] = {}
    for section in parser.sections():
        if section.startswith("strategy.") and section != "strategy":
            key = section.split(".", 1)[1]
            params[key] = resolve_mapping(dict(parser[section]))
    return params
