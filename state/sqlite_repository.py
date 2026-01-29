from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from state.models import BacktestSummary, Fill, MlRecommendation, Order, Trade
from state.repository import StateRepository


class SqliteStateRepository(StateRepository):
    def __init__(self, path: Path) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                client_order_id TEXT,
                symbol TEXT,
                side TEXT,
                quantity REAL,
                status TEXT,
                signal_id TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT PRIMARY KEY,
                order_id TEXT,
                symbol TEXT,
                entry_price REAL,
                exit_price REAL,
                quantity REAL,
                pnl REAL,
                fees REAL,
                slippage_bps REAL,
                strategy TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fills (
                fill_id TEXT PRIMARY KEY,
                order_id TEXT,
                price REAL,
                quantity REAL,
                fee REAL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS backtest_runs (
                run_id TEXT PRIMARY KEY,
                started_at INTEGER,
                finished_at INTEGER,
                exchange TEXT,
                symbols TEXT,
                timeframes TEXT,
                total_signals INTEGER,
                total_orders INTEGER,
                total_trades INTEGER,
                final_equity REAL,
                stats_json TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ml_recommendations (
                run_id TEXT PRIMARY KEY,
                created_at INTEGER,
                payload_json TEXT
            )
            """
        )
        self._ensure_trade_columns()
        self._conn.commit()

    def save_order(self, order: Order) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO orders (
                order_id, client_order_id, symbol, side, quantity, status, signal_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order.order_id,
                order.client_order_id,
                order.symbol,
                order.side,
                order.quantity,
                order.status.value,
                order.signal_id,
            ),
        )
        self._conn.commit()

    def save_trade(self, trade: Trade) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO trades (
                trade_id, order_id, symbol, entry_price, exit_price, quantity, pnl, fees, slippage_bps, strategy
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade.trade_id,
                trade.order_id,
                trade.symbol,
                trade.entry_price,
                trade.exit_price,
                trade.quantity,
                trade.pnl,
                trade.fees,
                trade.slippage_bps,
                trade.strategy,
            ),
        )
        self._conn.commit()

    def save_fill(self, fill: Fill) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO fills (
                fill_id, order_id, price, quantity, fee
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                fill.fill_id,
                fill.order_id,
                fill.price,
                fill.quantity,
                fill.fee,
            ),
        )
        self._conn.commit()

    def save_backtest_summary(self, summary: BacktestSummary) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO backtest_runs (
                run_id,
                started_at,
                finished_at,
                exchange,
                symbols,
                timeframes,
                total_signals,
                total_orders,
                total_trades,
                final_equity,
                stats_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary.run_id,
                summary.started_at,
                summary.finished_at,
                summary.exchange,
                json.dumps(summary.symbols),
                json.dumps(summary.timeframes),
                summary.total_signals,
                summary.total_orders,
                summary.total_trades,
                summary.final_equity,
                summary.stats_json,
            ),
        )
        self._conn.commit()

    def save_ml_recommendation(self, recommendation: MlRecommendation) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO ml_recommendations (
                run_id, created_at, payload_json
            ) VALUES (?, ?, ?)
            """,
            (recommendation.run_id, recommendation.created_at, recommendation.payload_json),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _ensure_trade_columns(self) -> None:
        columns = [row[1] for row in self._conn.execute("PRAGMA table_info(trades)").fetchall()]
        if "strategy" not in columns:
            self._conn.execute("ALTER TABLE trades ADD COLUMN strategy TEXT")
