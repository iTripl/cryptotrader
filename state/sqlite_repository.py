from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from state.models import BacktestMetrics, BacktestSummary, Fill, Order, Trade, TradeMetrics
from state.repository import StateRepository


class SqliteStateRepository(StateRepository):
    def __init__(self, path: Path) -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        with self._lock:
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
                symbol TEXT,
                side TEXT,
                price REAL,
                quantity REAL,
                fee REAL,
                timestamp INTEGER
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
            CREATE TABLE IF NOT EXISTS trade_metrics (
                trade_id TEXT PRIMARY KEY,
                symbol TEXT,
                strategy TEXT,
                notional REAL,
                gross_pnl REAL,
                net_pnl REAL,
                return_pct REAL,
                fee_pct REAL,
                slippage_bps REAL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS backtest_metrics (
                run_id TEXT PRIMARY KEY,
                total_trades INTEGER,
                win_rate REAL,
                avg_win REAL,
                avg_loss REAL,
                profit_factor REAL,
                payoff_ratio REAL,
                expectancy REAL,
                max_drawdown REAL,
                pnl_value REAL,
                pnl_pct REAL,
                cagr REAL,
                calmar_ratio REAL,
                sharpe REAL,
                sortino REAL
            )
            """
        )
        self._ensure_trade_columns()
        self._ensure_fill_columns()
        self._conn.commit()

    def save_order(self, order: Order) -> None:
        with self._lock:
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
        with self._lock:
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
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO fills (
                    fill_id, order_id, symbol, side, price, quantity, fee, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fill.fill_id,
                    fill.order_id,
                    fill.symbol,
                    fill.side,
                    fill.price,
                    fill.quantity,
                    fill.fee,
                    fill.timestamp,
                ),
            )
            self._conn.commit()

    def save_trade_metrics(self, metrics: TradeMetrics) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO trade_metrics (
                    trade_id,
                    symbol,
                    strategy,
                    notional,
                    gross_pnl,
                    net_pnl,
                    return_pct,
                    fee_pct,
                    slippage_bps
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metrics.trade_id,
                    metrics.symbol,
                    metrics.strategy,
                    metrics.notional,
                    metrics.gross_pnl,
                    metrics.net_pnl,
                    metrics.return_pct,
                    metrics.fee_pct,
                    metrics.slippage_bps,
                ),
            )
            self._conn.commit()

    def save_backtest_summary(self, summary: BacktestSummary) -> None:
        with self._lock:
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

    def save_backtest_metrics(self, metrics: BacktestMetrics) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO backtest_metrics (
                    run_id,
                    total_trades,
                    win_rate,
                    avg_win,
                    avg_loss,
                    profit_factor,
                    payoff_ratio,
                    expectancy,
                    max_drawdown,
                    pnl_value,
                    pnl_pct,
                    cagr,
                    calmar_ratio,
                    sharpe,
                    sortino
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metrics.run_id,
                    metrics.total_trades,
                    metrics.win_rate,
                    metrics.avg_win,
                    metrics.avg_loss,
                    metrics.profit_factor,
                    metrics.payoff_ratio,
                    metrics.expectancy,
                    metrics.max_drawdown,
                    metrics.pnl_value,
                    metrics.pnl_pct,
                    metrics.cagr,
                    metrics.calmar_ratio,
                    metrics.sharpe,
                    metrics.sortino,
                ),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _ensure_trade_columns(self) -> None:
        columns = [row[1] for row in self._conn.execute("PRAGMA table_info(trades)").fetchall()]
        if "strategy" not in columns:
            self._conn.execute("ALTER TABLE trades ADD COLUMN strategy TEXT")

    def _ensure_fill_columns(self) -> None:
        columns = [row[1] for row in self._conn.execute("PRAGMA table_info(fills)").fetchall()]
        if "symbol" not in columns:
            self._conn.execute("ALTER TABLE fills ADD COLUMN symbol TEXT")
        if "side" not in columns:
            self._conn.execute("ALTER TABLE fills ADD COLUMN side TEXT")
        if "timestamp" not in columns:
            self._conn.execute("ALTER TABLE fills ADD COLUMN timestamp INTEGER")
