# CryptoTrader Infrastructure (Scaffold)

Production-grade, modular architecture for a crypto trading system with
clean separation between strategy, risk, execution, and data layers.

## Quick start (debug/dev)
- Edit `config/config.ini`
- Create venv: `bash scripts/setup_venv.sh`
- Run: `python main.py --config config/config.ini --interactive`
- Debug with synthetic stream: `python main.py --config config/config.ini --dry-run`
- Run tests: `pytest`
 - Preflight checks: `python scripts/preflight.py --config config/config.ini`

## Modes
- `backtest`  : uses historical Parquet data and simulated execution
- `forward`   : uses live data, paper execution
- `live`      : uses live data + exchange execution

Backtest auto-downloads missing data for the configured symbols/timeframes.

Backtest summaries (stats + final equity) are stored in `State/trading.db`.
ML recommendations (TP/SL + confidence) are stored in `State/trading.db` table `ml_recommendations`.
Latest recommendations are also written to `State/ml_recommendations.json`.

## Design highlights
- One strategy per OS process
- Each strategy auto-loads data by default
- Unified exchange interface (REST + WS)
- Strict signal contract with traceability
- Parquet data pipeline with validation
- Structured JSON logging

## Notes
- This is infrastructure scaffolding; production strategy logic is not included.
- Two basic test strategies are included (MA cross + RSI mean reversion).
- Configuration is required for all runtime parameters; nothing is hardcoded.

## Deployment
- Guide: `docs/deployment.md`
- Debugging: `docs/debugging.md`
- Research notes: `docs/research.md`
