from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class RuntimeConfig:
    mode: str
    exchange: str
    strategy_modules: tuple[str, ...]
    risk_profile: str
    dry_run: bool


@dataclass(frozen=True)
class ExchangeConfig:
    api_key: str
    api_secret: str
    api_passphrase: str | None
    rest_url: str
    ws_url: str
    timeout_seconds: float
    rate_limit_per_min: int
    category: str
    use_demo: bool
    demo_rest_url: str
    market_rest_url: str
    public_ws_url: str
    private_ws_url: str
    recv_window: int
    order_poll_interval_seconds: int
    demo_handshake: bool
    handshake_symbol: str
    handshake_quantity: float
    ws_open_timeout_seconds: int
    ws_ping_interval_seconds: int
    ws_retry_seconds: int
    ws_message_timeout_seconds: int


@dataclass(frozen=True)
class SymbolConfig:
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]


@dataclass(frozen=True)
class RiskConfig:
    initial_equity: float
    risk_per_trade: float
    max_daily_drawdown: float
    max_consecutive_losses: int
    min_expectancy: float
    correlation_limit: float
    exposure_limit: float
    volatility_adjustment_high: float
    volatility_adjustment_normal: float
    volatility_adjustment_low: float
    stop_loss_pct: float
    take_profit_pct: float
    trailing_take_profit_pct: float
    atr_period: int
    atr_sl_mult: float
    atr_tp_mult: float
    atr_trailing_mult: float


@dataclass(frozen=True)
class StrategyConfig:
    confidence_floor: float
    signal_horizon: str
    signal_timeout_seconds: float


@dataclass(frozen=True)
class PathsConfig:
    data_dir: Path
    state_dir: Path
    state_db: Path
    logs_dir: Path


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    json: bool
    console: bool


@dataclass(frozen=True)
class BacktestConfig:
    start_ts: int
    end_ts: int
    days_back: int
    fast_local: bool
    max_candles_per_series: int
    fee_bps: float
    slippage_bps: float
    latency_ms: int
    auto_download: bool
    download_limit: int
    loader_timeout_seconds: int
    max_empty_batches: int


@dataclass(frozen=True)
class ForwardConfig:
    paper_trading: bool


@dataclass(frozen=True)
class LiveConfig:
    paper_trading: bool


@dataclass(frozen=True)
class AppConfig:
    config_path: Path
    runtime: RuntimeConfig
    exchange: ExchangeConfig
    symbols: SymbolConfig
    risk: RiskConfig
    strategy: StrategyConfig
    strategy_params: dict[str, dict[str, str]]
    paths: PathsConfig
    logging: LoggingConfig
    backtest: BacktestConfig
    forward: ForwardConfig
    live: LiveConfig

    def paper_trading_enabled(self) -> bool:
        if self.runtime.mode == "forward":
            return self.forward.paper_trading
        if self.runtime.mode == "live":
            return self.live.paper_trading
        return False

    def demo_trading_enabled(self) -> bool:
        return self.paper_trading_enabled() and self.exchange.use_demo

    def validate(self) -> None:
        if self.runtime.mode not in {"backtest", "forward", "live"}:
            raise ValueError(f"Unsupported mode: {self.runtime.mode}")
        if self.paper_trading_enabled() and not self.exchange.use_demo:
            raise ValueError("paper_trading requires exchange.use_demo=true for demo trading")
        if not self.symbols.symbols:
            raise ValueError("At least one symbol is required")
        if not self.symbols.timeframes:
            raise ValueError("At least one timeframe is required")
        if self.risk.risk_per_trade <= 0 or self.risk.risk_per_trade > 1:
            raise ValueError("risk_per_trade must be within (0, 1]")
        if self.risk.max_daily_drawdown <= 0 or self.risk.max_daily_drawdown > 1:
            raise ValueError("max_daily_drawdown must be within (0, 1]")
        if self.logging.level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"Invalid logging level: {self.logging.level}")
        if self.risk.initial_equity <= 0:
            raise ValueError("initial_equity must be greater than 0")
        if self.backtest.download_limit <= 0:
            raise ValueError("backtest.download_limit must be greater than 0")
        if self.risk.stop_loss_pct < 0 or self.risk.take_profit_pct < 0:
            raise ValueError("stop_loss_pct/take_profit_pct must be >= 0")
        if self.risk.trailing_take_profit_pct < 0:
            raise ValueError("trailing_take_profit_pct must be >= 0")
        if self.risk.atr_period < 0:
            raise ValueError("atr_period must be >= 0")
        if self.risk.atr_sl_mult < 0 or self.risk.atr_tp_mult < 0 or self.risk.atr_trailing_mult < 0:
            raise ValueError("atr_*_mult must be >= 0")
        if self.strategy.signal_timeout_seconds <= 0:
            raise ValueError("strategy.signal_timeout_seconds must be > 0")
        if self.backtest.days_back < 0:
            raise ValueError("backtest.days_back must be >= 0")
        if self.backtest.loader_timeout_seconds <= 0:
            raise ValueError("backtest.loader_timeout_seconds must be > 0")
        if self.backtest.max_empty_batches <= 0:
            raise ValueError("backtest.max_empty_batches must be > 0")
        if self.backtest.max_candles_per_series < 0:
            raise ValueError("backtest.max_candles_per_series must be >= 0")
        if self.exchange.order_poll_interval_seconds <= 0:
            raise ValueError("exchange.order_poll_interval_seconds must be > 0")
        if self.exchange.handshake_quantity < 0:
            raise ValueError("exchange.handshake_quantity must be >= 0")
        if self.exchange.ws_open_timeout_seconds <= 0:
            raise ValueError("exchange.ws_open_timeout_seconds must be > 0")
        if self.exchange.ws_ping_interval_seconds <= 0:
            raise ValueError("exchange.ws_ping_interval_seconds must be > 0")
        if self.exchange.ws_retry_seconds <= 0:
            raise ValueError("exchange.ws_retry_seconds must be > 0")
        if self.exchange.ws_message_timeout_seconds <= 0:
            raise ValueError("exchange.ws_message_timeout_seconds must be > 0")
    def with_mode(self, mode: str) -> "AppConfig":
        updated = replace(self, runtime=replace(self.runtime, mode=mode))
        updated.validate()
        return updated

    def with_dry_run(self, dry_run: bool) -> "AppConfig":
        updated = replace(self, runtime=replace(self.runtime, dry_run=dry_run))
        updated.validate()
        return updated

    def strategy_params_for(self, key: str) -> dict[str, str]:
        return self.strategy_params.get(key, {})


def parse_runtime(section: dict[str, str]) -> RuntimeConfig:
    return RuntimeConfig(
        mode=section["mode"],
        exchange=section["exchange"],
        strategy_modules=tuple(_split_csv(section["strategy_modules"])),
        risk_profile=section.get("risk_profile", "balanced"),
        dry_run=_as_bool(section.get("dry_run", "false")),
    )


def parse_exchange(section: dict[str, str]) -> ExchangeConfig:
    return ExchangeConfig(
        api_key=section.get("api_key", ""),
        api_secret=section.get("api_secret", ""),
        api_passphrase=section.get("api_passphrase") or None,
        rest_url=section["rest_url"],
        ws_url=section["ws_url"],
        timeout_seconds=float(section.get("timeout_seconds", "10")),
        rate_limit_per_min=int(section.get("rate_limit_per_min", "120")),
        category=section.get("category", "linear"),
        use_demo=_as_bool(section.get("use_demo", "false")),
        demo_rest_url=section.get("demo_rest_url", "https://api-demo.bybit.com"),
        market_rest_url=section.get("market_rest_url", section.get("rest_url", "")),
        public_ws_url=section.get("public_ws_url", section.get("ws_url", "")),
        private_ws_url=section.get("private_ws_url", "wss://stream.bybit.com/v5/private"),
        recv_window=int(section.get("recv_window", "5000")),
        order_poll_interval_seconds=int(section.get("order_poll_interval_seconds", "5")),
        demo_handshake=_as_bool(section["demo_handshake"]),
        handshake_symbol=section["handshake_symbol"],
        handshake_quantity=float(section["handshake_quantity"]),
        ws_open_timeout_seconds=int(section.get("ws_open_timeout_seconds", "10")),
        ws_ping_interval_seconds=int(section.get("ws_ping_interval_seconds", "20")),
        ws_retry_seconds=int(section.get("ws_retry_seconds", "5")),
        ws_message_timeout_seconds=int(section.get("ws_message_timeout_seconds", "30")),
    )


def parse_symbols(section: dict[str, str]) -> SymbolConfig:
    return SymbolConfig(
        symbols=tuple(_split_csv(section["symbols"])),
        timeframes=tuple(_split_csv(section["timeframes"])),
    )


def parse_risk(section: dict[str, str]) -> RiskConfig:
    return RiskConfig(
        initial_equity=float(section.get("initial_equity", "0")),
        risk_per_trade=float(section["risk_per_trade"]),
        max_daily_drawdown=float(section["max_daily_drawdown"]),
        max_consecutive_losses=int(section["max_consecutive_losses"]),
        min_expectancy=float(section.get("min_expectancy", "0")),
        correlation_limit=float(section.get("correlation_limit", "0.7")),
        exposure_limit=float(section.get("exposure_limit", "0.25")),
        volatility_adjustment_high=float(section.get("volatility_adjustment_high", "0.6")),
        volatility_adjustment_normal=float(section.get("volatility_adjustment_normal", "1.0")),
        volatility_adjustment_low=float(section.get("volatility_adjustment_low", "1.2")),
        stop_loss_pct=float(section.get("stop_loss_pct", "0.0")),
        take_profit_pct=float(section.get("take_profit_pct", "0.0")),
        trailing_take_profit_pct=float(section.get("trailing_take_profit_pct", "0.0")),
        atr_period=int(section.get("atr_period", "0")),
        atr_sl_mult=float(section.get("atr_sl_mult", "0.0")),
        atr_tp_mult=float(section.get("atr_tp_mult", "0.0")),
        atr_trailing_mult=float(section.get("atr_trailing_mult", "0.0")),
    )


def parse_strategy(section: dict[str, str]) -> StrategyConfig:
    return StrategyConfig(
        confidence_floor=float(section.get("confidence_floor", "0.55")),
        signal_horizon=section.get("signal_horizon", "5m"),
        signal_timeout_seconds=float(section.get("signal_timeout_seconds", "0.25")),
    )


def parse_paths(section: dict[str, str]) -> PathsConfig:
    return PathsConfig(
        data_dir=Path(section.get("data_dir", "runtime/data")),
        state_dir=Path(section.get("state_dir", "runtime/state")),
        state_db=Path(section.get("state_db", "runtime/state/trading.db")),
        logs_dir=Path(section.get("logs_dir", "runtime/logs")),
    )


def parse_logging(section: dict[str, str]) -> LoggingConfig:
    return LoggingConfig(
        level=section.get("level", "INFO").upper(),
        json=_as_bool(section.get("json", "true")),
        console=_as_bool(section.get("console", "true")),
    )


def parse_backtest(section: dict[str, str]) -> BacktestConfig:
    return BacktestConfig(
        start_ts=int(section.get("start_ts", "0")),
        end_ts=int(section.get("end_ts", "0")),
        days_back=int(section.get("days_back", "0")),
        fast_local=_as_bool(section.get("fast_local", "false")),
        max_candles_per_series=int(section.get("max_candles_per_series", "0")),
        fee_bps=float(section.get("fee_bps", "0")),
        slippage_bps=float(section.get("slippage_bps", "0")),
        latency_ms=int(section.get("latency_ms", "0")),
        auto_download=_as_bool(section.get("auto_download", "true")),
        download_limit=int(section.get("download_limit", "1000")),
        loader_timeout_seconds=int(section.get("loader_timeout_seconds", "120")),
        max_empty_batches=int(section.get("max_empty_batches", "2")),
    )


def parse_forward(section: dict[str, str]) -> ForwardConfig:
    return ForwardConfig(
        paper_trading=_as_bool(section.get("paper_trading", "true")),
    )


def parse_live(section: dict[str, str]) -> LiveConfig:
    return LiveConfig(
        paper_trading=_as_bool(section.get("paper_trading", "false")),
    )


def ensure_sections(config: dict[str, dict[str, str]], required: Iterable[str]) -> None:
    missing = [section for section in required if section not in config]
    if missing:
        raise ValueError(f"Missing config sections: {', '.join(missing)}")
