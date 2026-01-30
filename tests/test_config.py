from pathlib import Path

import pytest

from config.loader import load_config


def test_load_config(tmp_path: Path) -> None:
    config_text = """
[runtime]
mode = backtest
exchange = bybit
strategy_modules = strategies.base_strategy:NoOpStrategy
risk_profile = balanced
dry_run = true

[exchange]
api_key =
api_secret =
api_passphrase =
rest_url = https://api.bybit.com
ws_url = wss://stream.bybit.com
timeout_seconds = 10
rate_limit_per_min = 120
category = linear
use_demo = false
demo_rest_url = https://api-demo.bybit.com
market_rest_url = https://api.bybit.com
public_ws_url = wss://stream.bybit.com
private_ws_url = wss://stream.bybit.com/v5/private
recv_window = 5000
order_poll_interval_seconds = 5
demo_handshake = false
handshake_symbol = BTCUSDT
handshake_quantity = 0.001
ws_open_timeout_seconds = 10
ws_ping_interval_seconds = 20
ws_retry_seconds = 5
ws_message_timeout_seconds = 30

[symbols]
symbols = BTCUSDT
timeframes = 1m

[risk]
initial_equity = 10000
risk_per_trade = 0.01
max_daily_drawdown = 0.05
max_consecutive_losses = 3
min_expectancy = 0
correlation_limit = 0.7
exposure_limit = 0.25
volatility_adjustment_high = 0.6
volatility_adjustment_normal = 1.0
volatility_adjustment_low = 1.2
stop_loss_pct = 0.02
take_profit_pct = 0.04
trailing_take_profit_pct = 0.02
atr_period = 14
atr_sl_mult = 1.5
atr_tp_mult = 3.0
atr_trailing_mult = 1.0

[strategy]
confidence_floor = 0.5
signal_horizon = 5m
signal_timeout_seconds = 0.25

[strategy.simple_ma]
fast_window = 10
slow_window = 20
confidence = 0.6
horizon = 5m
volatility_regime = normal

[strategy.rsi_reversion]
rsi_period = 14
overbought = 70
oversold = 30
confidence = 0.6
horizon = 5m
volatility_regime = normal

[strategy.donchian_trend]
lookbacks = 20,50
min_votes = 1
confidence = 0.6
horizon = 1h
volatility_regime = normal

[strategy.cross_section_momentum]
lookback_bars = 30
hold_bars = 7
top_n = 1
allow_short = false
confidence = 0.6
horizon = 1d
volatility_regime = normal

[paths]
data_dir = runtime/data
state_dir = runtime/state
state_db = runtime/state/trading.db
logs_dir = runtime/logs

[logging]
level = INFO
json = true
console = true

[backtest]
start_ts = 0
end_ts = 0
days_back = 30
fast_local = true
max_candles_per_series = 1000
fee_bps = 0
slippage_bps = 0
latency_ms = 0
auto_download = false
download_limit = 1000
loader_timeout_seconds = 60
max_empty_batches = 2

[forward]
paper_trading = true

[live]
paper_trading = false
""".strip()
    config_path = tmp_path / "config.ini"
    config_path.write_text(config_text, encoding="utf-8")

    config = load_config(config_path)
    assert config.runtime.mode == "backtest"
    assert config.risk.initial_equity == 10000
    assert config.config_path.exists()


def test_paper_trading_requires_demo(tmp_path: Path) -> None:
    config_text = """
[runtime]
mode = forward
exchange = bybit
strategy_modules = strategies.base_strategy:NoOpStrategy
risk_profile = balanced
dry_run = true

[exchange]
api_key =
api_secret =
api_passphrase =
rest_url = https://api.bybit.com
ws_url = wss://stream.bybit.com
timeout_seconds = 10
rate_limit_per_min = 120
category = linear
use_demo = false
demo_rest_url = https://api-demo.bybit.com
market_rest_url = https://api.bybit.com
public_ws_url = wss://stream.bybit.com
private_ws_url = wss://stream.bybit.com/v5/private
recv_window = 5000
order_poll_interval_seconds = 5
demo_handshake = false
handshake_symbol = BTCUSDT
handshake_quantity = 0.001
ws_open_timeout_seconds = 10
ws_ping_interval_seconds = 20
ws_retry_seconds = 5
ws_message_timeout_seconds = 30

[symbols]
symbols = BTCUSDT
timeframes = 1m

[risk]
initial_equity = 10000
risk_per_trade = 0.01
max_daily_drawdown = 0.05
max_consecutive_losses = 3
min_expectancy = 0
correlation_limit = 0.7
exposure_limit = 0.25
volatility_adjustment_high = 0.6
volatility_adjustment_normal = 1.0
volatility_adjustment_low = 1.2
stop_loss_pct = 0.02
take_profit_pct = 0.04
trailing_take_profit_pct = 0.02
atr_period = 14
atr_sl_mult = 1.5
atr_tp_mult = 3.0
atr_trailing_mult = 1.0

[strategy]
confidence_floor = 0.5
signal_horizon = 5m
signal_timeout_seconds = 0.25

[strategy.simple_ma]
fast_window = 10
slow_window = 20
confidence = 0.6
horizon = 5m
volatility_regime = normal

[strategy.rsi_reversion]
rsi_period = 14
overbought = 70
oversold = 30
confidence = 0.6
horizon = 5m
volatility_regime = normal

[strategy.donchian_trend]
lookbacks = 20,50
min_votes = 1
confidence = 0.6
horizon = 1h
volatility_regime = normal

[strategy.cross_section_momentum]
lookback_bars = 30
hold_bars = 7
top_n = 1
allow_short = false
confidence = 0.6
horizon = 1d
volatility_regime = normal

[paths]
data_dir = runtime/data
state_dir = runtime/state
state_db = runtime/state/trading.db
logs_dir = runtime/logs

[logging]
level = INFO
json = true
console = true

[backtest]
start_ts = 0
end_ts = 0
days_back = 30
fast_local = true
max_candles_per_series = 1000
fee_bps = 0
slippage_bps = 0
latency_ms = 0
auto_download = false
download_limit = 1000
loader_timeout_seconds = 60
max_empty_batches = 2

[forward]
paper_trading = true

[live]
paper_trading = false
""".strip()
    config_path = tmp_path / "config.ini"
    config_path.write_text(config_text, encoding="utf-8")

    with pytest.raises(ValueError, match="paper_trading requires exchange.use_demo=true"):
        load_config(config_path)
