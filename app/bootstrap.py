from __future__ import annotations

from analytics.collector import StatisticsCollector
from app.container import Container
from app.lifecycle import TradingApplication
from app.mode_runner import ModeRunner
from config.config_schema import AppConfig
from monitoring.killswitch import KillSwitch


class Bootstrap:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def build(self) -> TradingApplication:
        self.config.paths.data_dir.mkdir(parents=True, exist_ok=True)
        (self.config.paths.data_dir / "raw").mkdir(parents=True, exist_ok=True)
        (self.config.paths.data_dir / "norm").mkdir(parents=True, exist_ok=True)
        (self.config.paths.data_dir / "features").mkdir(parents=True, exist_ok=True)
        self.config.paths.state_dir.mkdir(parents=True, exist_ok=True)
        self.config.paths.state_db.parent.mkdir(parents=True, exist_ok=True)
        self.config.paths.logs_dir.mkdir(parents=True, exist_ok=True)
        container = Container(self.config)
        return TradingApplication(
            config=self.config,
            mode_runner=ModeRunner(self.config, container.parquet_reader(), container.data_auto_loader()),
            strategy_manager=container.strategy_manager(),
            risk_manager=container.risk_manager(),
            execution_engine=container.execution_engine(),
            feature_pipeline=container.feature_pipeline(),
            state_repo=container.state_repository(),
            stats=StatisticsCollector(),
            killswitch=KillSwitch(),
        )
