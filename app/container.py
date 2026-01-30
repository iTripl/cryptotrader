from __future__ import annotations

from pathlib import Path

from config.config_schema import AppConfig
from data.auto_loader import DataAutoLoader
from data.storage.parquet_reader import ParquetReader
from data.storage.parquet_writer import ParquetWriter
from exchanges.base_exchange import RateLimiter
from exchanges.binance.adapter import BinanceAdapter, BinanceRestClient, BinanceWsClient
from exchanges.bybit.adapter import BybitAdapter, BybitRestClient, BybitWsClient
from exchanges.okx.adapter import OkxAdapter, OkxRestClient, OkxWsClient
from execution.execution_engine import BacktestExecutionEngine, LiveExecutionEngine, PaperExecutionEngine
from execution.order_manager import OrderManager
from execution.order_tracker import BybitOrderTracker, OrderTracker
from features.feature_pipeline import FeaturePipeline
from risk.risk_manager import DefaultRiskManager
from state.repository import InMemoryStateRepository
from state.sqlite_repository import SqliteStateRepository
from strategies.registry import load_strategies
from utils.retry import RetryPolicy
from utils.logger import get_logger


class Container:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._logger = get_logger("app.container")

    def exchange_adapter(self):
        rate_limiter = RateLimiter(self.config.exchange.rate_limit_per_min)
        retry_policy = RetryPolicy(max_attempts=5, base_delay=0.5, max_delay=5.0, jitter=0.3)
        checkpoint_dir = Path(self.config.paths.state_dir) / "checkpoints"

        if self.config.runtime.exchange == "bybit":
            rest_url = self.config.exchange.demo_rest_url if self.config.exchange.use_demo else self.config.exchange.rest_url
            ws_url = self.config.exchange.public_ws_url or self.config.exchange.ws_url
            rest = BybitRestClient(
                rate_limiter,
                retry_policy,
                base_url=rest_url,
                market_base_url=self.config.exchange.market_rest_url or self.config.exchange.rest_url,
                timeout=self.config.exchange.timeout_seconds,
                category=self.config.exchange.category,
                api_key=self.config.exchange.api_key,
                api_secret=self.config.exchange.api_secret,
                recv_window=self.config.exchange.recv_window,
            )
            rest.start_time_sync()
            ws = BybitWsClient(
                ws_url,
                self.config.runtime.exchange,
                open_timeout=self.config.exchange.ws_open_timeout_seconds,
                ping_interval=self.config.exchange.ws_ping_interval_seconds,
                retry_seconds=self.config.exchange.ws_retry_seconds,
                message_timeout=self.config.exchange.ws_message_timeout_seconds,
            )
            return BybitAdapter(rest, ws, checkpoint_dir)
        if self.config.runtime.exchange == "binance":
            rest = BinanceRestClient(
                rate_limiter,
                retry_policy,
                base_url=self.config.exchange.rest_url,
                timeout=self.config.exchange.timeout_seconds,
            )
            ws = BinanceWsClient()
            return BinanceAdapter(rest, ws, checkpoint_dir)
        if self.config.runtime.exchange == "okx":
            rest = OkxRestClient(
                rate_limiter,
                retry_policy,
                base_url=self.config.exchange.rest_url,
                timeout=self.config.exchange.timeout_seconds,
            )
            ws = OkxWsClient()
            return OkxAdapter(rest, ws, checkpoint_dir)

        raise ValueError(f"Unsupported exchange: {self.config.runtime.exchange}")

    def strategy_manager(self):
        strategies = load_strategies(self.config.runtime.strategy_modules, self.config)
        from strategies.manager import StrategyManager

        return StrategyManager(strategies, timeout_seconds=self.config.strategy.signal_timeout_seconds)

    def risk_manager(self):
        return DefaultRiskManager(self.config.risk)

    def order_manager(self):
        return OrderManager()

    def execution_engine(self):
        if self.config.runtime.mode == "backtest":
            return BacktestExecutionEngine(
                self.order_manager(),
                fee_bps=self.config.backtest.fee_bps,
                slippage_bps=self.config.backtest.slippage_bps,
            )
        if self.config.paper_trading_enabled():
            if not self.config.exchange.use_demo:
                raise ValueError("paper_trading requires exchange.use_demo=true for demo trading")
            return LiveExecutionEngine(self.exchange_adapter(), self.order_manager())
        return LiveExecutionEngine(self.exchange_adapter(), self.order_manager())

    def feature_pipeline(self):
        return FeaturePipeline()

    def state_repository(self):
        try:
            return SqliteStateRepository(self.config.paths.state_db)
        except Exception as exc:
            self._logger.warning("sqlite repository unavailable: %s", exc)
            return InMemoryStateRepository()

    def parquet_writer(self):
        return ParquetWriter(Path(self.config.paths.data_dir))

    def parquet_reader(self):
        return ParquetReader(Path(self.config.paths.data_dir))

    def data_auto_loader(self):
        return DataAutoLoader(self.config, self.exchange_adapter(), self.parquet_writer())

    def order_tracker(self) -> OrderTracker | None:
        if self.config.runtime.exchange != "bybit":
            return None
        if not self.config.exchange.api_key or not self.config.exchange.api_secret:
            return None
        return BybitOrderTracker(
            self.exchange_adapter().rest,
            private_ws_url=self.config.exchange.private_ws_url,
            api_key=self.config.exchange.api_key,
            api_secret=self.config.exchange.api_secret,
            recv_window=self.config.exchange.recv_window,
            poll_interval_seconds=self.config.exchange.order_poll_interval_seconds,
            open_timeout=self.config.exchange.ws_open_timeout_seconds,
            ping_interval=self.config.exchange.ws_ping_interval_seconds,
            retry_seconds=self.config.exchange.ws_retry_seconds,
        )

