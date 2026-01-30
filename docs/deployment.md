# Deployment Guide

## Prerequisites
- Python 3.11+
- Linux VDS (systemd recommended)
- Writable paths for `Data/`, `State/`, `Logs/`

## Install
```bash
bash scripts/setup_venv.sh
```

## Configure
1. Edit `config/config.ini`
2. Copy `.env.example` to `.env` and fill credentials
3. Export API keys (optional override):
```bash
export BYBIT_API_KEY="..."
export BYBIT_API_SECRET="..."
```

## Preflight checks
```bash
python scripts/preflight.py --config config/config.ini
```

## Run
```bash
python main.py --config config/config.ini
```

## Logs
- `Logs/system.log`
- `Logs/execution.log`
- `Logs/strategies.log`
- `Logs/errors.log`

## systemd example
```
[Unit]
Description=CryptoTrader
After=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/cryptotrader
Environment=PYTHONUNBUFFERED=1
Environment=BYBIT_API_KEY=...
Environment=BYBIT_API_SECRET=...
ExecStart=/opt/cryptotrader/.venv/bin/python main.py --config config/config.ini
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
