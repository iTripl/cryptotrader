# CryptoTrader Infrastructure

Production-grade, modular architecture for a crypto trading system with
clean separation between strategy, risk, execution, and data layers.

## Quick start (debug/dev)
- Edit `config/config.ini`
- Create venv: `bash scripts/setup_venv.sh`
- Copy secrets template: `cp .env.example .env`
- Run: `python main.py --config config/config.ini --interactive`
- Debug with synthetic stream: `python main.py --config config/config.ini --dry-run`
- Run tests: `pytest`
- Preflight checks: `python scripts/preflight.py --config config/config.ini`

## Modes
- `backtest`  : uses historical Parquet data and simulated execution
- `forward`   : uses live data + demo execution when `paper_trading=true`
- `live`      : uses live data + exchange execution (demo when `paper_trading=true`)

Backtest auto-downloads missing data for the configured symbols/timeframes.
Backtest summaries (stats + final equity) are stored in `State/trading.db`.
ML recommendations (TP/SL + confidence) are stored in `State/trading.db` table `ml_recommendations`.
Latest recommendations are also written to `State/ml_recommendations.json`.

## How It Works
1) **Config load**: `config.ini` is parsed and validated (no hardcoded params).
2) **Data source**:
   - Backtest: loads Parquet, auto-downloads missing data, filters by `days_back`.
   - Forward/Live: consumes exchange WS stream (Bybit implemented).
3) **Candle loop**: all modes use the same candle loop and strategy execution path.
4) **Strategies**: each strategy runs in its own OS process (backtest can use `fast_local` to run in-process).
5) **Signals → Risk → Execution**:
   - Strategy emits immutable `Signal`.
   - Risk checks position/exposure/expectancy and sizes orders.
   - Execution engine routes orders (paper/live/backtest).
6) **Accounting**: positions, trades, PnL, and equity are updated for all modes.
7) **Outputs**: structured logs + backtest summaries + ML recommendations.

## Design highlights
- One strategy per OS process (optional single-process for fast backtests)
- Unified exchange interface (REST + WS)
- Strict signal contract with traceability
- Parquet data pipeline with validation and resume
- Structured JSON logging and run summaries

## Included strategies
- `simple_ma` (moving average cross)
- `rsi_reversion` (RSI mean reversion)
- `donchian_trend` (Donchian ensemble trend)
- `cross_section_momentum` (cross-sectional momentum)

## Notes
- This is infrastructure scaffolding; production strategies and live WS connectors for Binance/OKX are not included yet.
- Configuration is required for all runtime parameters; nothing is hardcoded.
- Use the console menu to select strategies by number.
- Secrets are loaded from `.env` (see `[secrets]` in `config.ini`) and must never be committed.

## Deployment
- Guide: `docs/deployment.md`
- Debugging: `docs/debugging.md`
- Research notes: `docs/research.md`
- Demo trading: `docs/demo_trading.md`