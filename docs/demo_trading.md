# Demo Trading (Bybit)

This guide shows how to run **paper trading** using Bybit’s demo trading account.
Bybit demo uses a **separate REST domain** and **private WS domain**, while public
market data remains on mainnet. See: [Bybit Demo Trading Service](https://bybit-exchange.github.io/docs/v5/demo).

## 1) Create demo API keys
1. Log in to Bybit.
2. Switch to **Demo Trading** (separate demo account).
3. Create an API key for the demo account.

## 2) Store secrets (never commit)
```bash
cp .env.example .env
```
Fill `.env` with:
```
BYBIT_API_KEY=...
BYBIT_API_SECRET=...
```

## 3) Configure `config/config.ini`
```
[runtime]
mode = forward
exchange = bybit

[exchange]
use_demo = true
demo_rest_url = https://api-demo.bybit.com
public_ws_url = wss://stream.bybit.com/v5/public/linear
private_ws_url = wss://stream-demo.bybit.com/v5/private
recv_window = 5000
demo_handshake = true
handshake_symbol = BTCUSDT
handshake_quantity = 0.001
ws_open_timeout_seconds = 10
ws_ping_interval_seconds = 20
ws_retry_seconds = 5
ws_message_timeout_seconds = 30

[forward]
paper_trading = true
```
Paper trading now requires `use_demo=true` and will route orders to the demo account.
Set `demo_handshake=false` or `handshake_quantity=0` to bypass the handshake trade.

## 4) Run
```bash
python main.py --config config/config.ini --interactive
```

## 5) What you get
- **Order status polling** via `/v5/order/realtime`
- **Execution fills** from demo private WS
- **PnL from actual fill prices** (not signal price)
- Trades and fills stored in `runtime/state/trading.db`
- A one-time demo **handshake trade** (buy+sell) to verify connectivity

## Troubleshooting
- Ensure `use_demo=true` and demo REST/WS URLs match the demo environment.
- Public market data always uses mainnet WS.
- If you see "apiKey is missing", check `.env` is loaded and keys are set.
- If orders are not filling, check Bybit demo balance and symbol availability.
- If private WS is blocked, order polling will still fetch executions via REST.
