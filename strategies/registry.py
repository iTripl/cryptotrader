from __future__ import annotations

import importlib
import inspect
import pkgutil
from dataclasses import dataclass
from typing import Iterable

from config.config_schema import AppConfig
from strategies.base_strategy import Strategy


@dataclass(frozen=True)
class StrategySpec:
    module: str
    class_name: str


def parse_spec(spec: str) -> StrategySpec:
    module, class_name = spec.split(":")
    return StrategySpec(module=module, class_name=class_name)


def load_strategy(spec: StrategySpec, config: AppConfig) -> Strategy:
    module = importlib.import_module(spec.module)
    cls = getattr(module, spec.class_name)
    config_key = getattr(cls, "config_key", getattr(cls, "name", cls.__name__.lower()))
    params = config.strategy_params_for(config_key)
    return cls(config, params)


def load_strategies(specs: Iterable[str], config: AppConfig) -> list[Strategy]:
    return [load_strategy(parse_spec(spec), config) for spec in specs]


def discover_strategy_specs() -> list[str]:
    specs: list[str] = []
    package = importlib.import_module("strategies")
    for module_info in pkgutil.iter_modules(package.__path__, package.__name__ + "."):
        module_name = module_info.name
        if module_name.endswith(".base_strategy") or module_name.endswith(".manager") or module_name.endswith(".registry") or module_name.endswith(".params"):
            continue
        module = importlib.import_module(module_name)
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls is Strategy:
                continue
            if not issubclass(cls, Strategy):
                continue
            if cls.__module__ != module.__name__:
                continue
            specs.append(f"{module.__name__}:{cls.__name__}")
    return sorted(set(specs))
