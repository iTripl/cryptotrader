# Debugging & Validation

## Local debug run
```bash
bash scripts/setup_venv.sh
cp .env.example .env
python main.py --config config/config.ini --dry-run
```

## Interactive menu
```bash
python main.py --config config/config.ini --interactive
```

## Increase logging verbosity
Set in `config/config.ini`:
```
[logging]
level = DEBUG
json = true
console = true
```

## Noise strategy (debug)
Use a low-confidence noise strategy to exercise the pipeline with minimal sizing.
Add to `config.ini`:
```
[strategy.noise]
order_notional = 5
confidence = 0.02
signal_probability = 0.25
horizon = 1m
volatility_regime = low
cooldown_seconds = 0
min_quantity = 0
max_quantity = 0
min_notional = 0
max_notional = 0
symbols = BTCUSDT
```
Then include `strategies.noise:NoiseStrategy` in `[runtime] strategy_modules`.
If you want sizing driven purely by risk settings, set `min_quantity=0`.

## Synthetic data
When no Parquet data is available, backtest uses a synthetic stream.
Use `--dry-run` in any mode to force synthetic data and bypass execution.

## Backtest auto-download
Backtest mode will auto-download missing Parquet data by symbol/timeframe
unless `backtest.auto_download=false` in config.
Set `backtest.days_back` to load data from today backwards by N days.

## Trailing take profit
Trailing TP is simulated on candles using high/low in all modes.
Configure in `[risk]` with `trailing_take_profit_pct`.

## Run tests
```bash
pytest
```

## Backtest outputs
- Summary stats and final equity are stored in the SQLite state DB:
  `runtime/state/trading.db` (table: `backtest_runs`)