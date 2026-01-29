# Debugging & Validation

## Local debug run
```bash
bash scripts/setup_venv.sh
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

## Synthetic data
When no Parquet data is available, backtest uses a synthetic stream.
Use `--dry-run` in any mode to force synthetic data and bypass execution.

## Backtest auto-download
Backtest mode will auto-download missing Parquet data by symbol/timeframe
unless `backtest.auto_download=false` in config.
Set `backtest.days_back` to load data from today backwards by N days.

## Trailing take profit (backtest)
Trailing TP is simulated in backtest using candle high/low.
Configure in `[risk]` with `trailing_take_profit_pct`.

## Run tests
```bash
pytest
```

## Backtest outputs
- Summary stats and final equity are stored in the SQLite state DB:
  `State/trading.db` (table: `backtest_runs`)
- ML recommendations are stored in `State/trading.db` (table: `ml_recommendations`)
- Latest ML recommendation is also written to `State/ml_recommendations.json`
- You can choose to auto-apply ML recommendations after backtest (Y/N prompt)
