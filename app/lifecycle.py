from __future__ import annotations

import time
from dataclasses import dataclass

from analytics.collector import StatisticsCollector
from app.mode_runner import ModeRunner
from config.config_schema import AppConfig
from execution.execution_engine import ExecutionEngine
from features.feature_pipeline import FeaturePipeline
from ml.auto_apply import apply_recommendation
from ml.backtest_analyzer import BacktestAnalyzer
from monitoring.killswitch import KillSwitch
from risk.risk_manager import RiskManager
from signals.signal import Signal
import json
from uuid import uuid4

from state.models import BacktestSummary, Order, PortfolioState, Position, Trade, order_state_from_status
from state.repository import StateRepository
from strategies.manager import StrategyManager
from utils.logger import get_logger, log_extra


logger = get_logger("app.lifecycle")


@dataclass
class TradingApplication:
    config: AppConfig
    mode_runner: ModeRunner
    strategy_manager: StrategyManager
    risk_manager: RiskManager
    execution_engine: ExecutionEngine
    feature_pipeline: FeaturePipeline
    state_repo: StateRepository
    stats: StatisticsCollector
    killswitch: KillSwitch

    def run(self) -> None:
        started_at = int(time.time())
        portfolio = PortfolioState(
            equity=self.config.risk.initial_equity,
            daily_drawdown=0.0,
            consecutive_losses=0,
        )
        logger.info("starting trading application")
        use_local = self.config.runtime.mode == "backtest"
        if not use_local:
            self.strategy_manager.start(self.config)
        heartbeat = 0
        total_signals = 0
        self._order_count = 0
        last_prices: dict[str, float] = {}
        candle_count = 0

        try:
            if self.config.runtime.mode != "backtest" and self.strategy_manager.auto_load_enabled():
                while True:
                    if self.killswitch.triggered:
                        logger.error("killswitch triggered: %s", self.killswitch.reason)
                        break
                    signals = self.strategy_manager.collect_signals()
                    for signal in signals:
                        self._handle_signal(signal, portfolio)
                        total_signals += 1
                    heartbeat += 1
                    if heartbeat % 50 == 0:
                        self.strategy_manager.restart_failed(self.config)
                    if self.strategy_manager.all_completed():
                        logger.info("all strategy data streams completed")
                        break
                    time.sleep(0.05)
            else:
                for candle in self.mode_runner.stream():
                    if self.killswitch.triggered:
                        logger.error("killswitch triggered: %s", self.killswitch.reason)
                        break
                    if self.config.runtime.mode == "backtest":
                        self._apply_backtest_stops(candle, portfolio)
                    _ = self.feature_pipeline.transform(candle)
                    last_prices[candle.symbol] = candle.close
                    candle_count += 1
                    if use_local:
                        signals = self.strategy_manager.local_signals(candle)
                    else:
                        self.strategy_manager.broadcast_candle(candle)
                        signals = self.strategy_manager.collect_signals()
                    for signal in signals:
                        self._handle_signal(signal, portfolio)
                        total_signals += 1
                    heartbeat += 1
                    if candle_count % 500 == 0:
                        logger.info(
                            "backtest progress candles=%d signals=%d open_positions=%d",
                            candle_count,
                            total_signals,
                            len(portfolio.open_positions),
                        )
                    if heartbeat % 50 == 0:
                        if not use_local:
                            self.strategy_manager.restart_failed(self.config)
        finally:
            if not use_local:
                self.strategy_manager.stop()
            finished_at = int(time.time())
            if self.config.runtime.mode == "backtest":
                self._liquidate_positions(last_prices, portfolio)
                simulated_days = self._simulated_days()
                logger.info(
                    "backtest finished candles=%d signals=%d trades=%d",
                    candle_count,
                    total_signals,
                    self.stats.total_trades(),
                )
                stats = self.stats.snapshot(self.config.risk.initial_equity)
                report = self.stats.backtest_report(self.config.risk.initial_equity, portfolio.equity)
                stats_payload = stats.__dict__ | report.__dict__ | {"simulated_days": simulated_days}
                summary = BacktestSummary(
                    run_id=str(uuid4()),
                    started_at=started_at,
                    finished_at=finished_at,
                    exchange=self.config.runtime.exchange,
                    symbols=self.config.symbols.symbols,
                    timeframes=self.config.symbols.timeframes,
                    total_signals=total_signals,
                    total_orders=self._order_count,
                    total_trades=stats.total_trades,
                    final_equity=portfolio.equity,
                    stats_json=json.dumps(stats_payload),
                )
                self.state_repo.save_backtest_summary(summary)
                self._print_backtest_report(report, portfolio.equity, simulated_days)
                if self.config.ml.enabled:
                    analyzer = BacktestAnalyzer(self.config)
                    result = analyzer.analyze(self.stats.trades(), self.config.risk.initial_equity, portfolio.equity)
                    recommendation = analyzer.to_recommendation(result)
                    self.state_repo.save_ml_recommendation(recommendation)
                    self._print_ml_recommendation(result)
                    self._write_ml_recommendation(result)
                    self._prompt_apply_ml(result)
            self.state_repo.close()

    def _handle_signal(self, signal: Signal, portfolio: PortfolioState) -> None:
        trace_id = signal.signal_id
        decision = self.risk_manager.approve(signal, portfolio)
        log_extra(
            logger,
            "risk decision",
            trace_id=trace_id,
            signal_id=signal.signal_id,
            approved=decision.approved,
            reason=decision.reason,
            size=decision.size,
        )
        if not decision.approved:
            if decision.reason in {"max_consecutive_losses", "max_daily_drawdown"}:
                self.killswitch.trigger(decision.reason or "risk_limit")
            return

        execution_size = decision.size
        price = signal.metadata.get("price")
        if price is not None and price > 0:
            execution_size = decision.size / float(price)

        result = self.execution_engine.execute(signal, execution_size, portfolio)
        log_extra(
            logger,
            "execution result",
            trace_id=trace_id,
            signal_id=signal.signal_id,
            order_id=result.response.order_id,
            status=result.response.status,
        )
        self._increment_order()

        order = Order(
            order_id=result.response.order_id,
            client_order_id=result.response.client_order_id,
            symbol=result.order.symbol,
            side=result.order.side,
            quantity=result.order.quantity,
            status=order_state_from_status(result.response.status),
            signal_id=signal.signal_id,
        )
        self.state_repo.save_order(order)

        if self.config.runtime.mode == "backtest":
            self._apply_backtest_accounting(signal, execution_size, portfolio, order.order_id)

    def _apply_backtest_accounting(
        self,
        signal: Signal,
        size: float,
        portfolio: PortfolioState,
        order_id: str,
    ) -> None:
        price = signal.metadata.get("price")
        if price is None:
            return
        price = float(price)
        side = signal.direction
        position = portfolio.open_positions.get(signal.symbol)
        if position is None and side in {"LONG", "SHORT"}:
            portfolio.open_positions[signal.symbol] = Position(
                symbol=signal.symbol,
                quantity=size,
                entry_price=price,
                side=side,
                max_price=price,
                min_price=price,
            )
            return

        if position is None:
            return

        if side == position.side:
            return

        entry_price = position.entry_price
        close_price = price
        slip = self.config.backtest.slippage_bps / 10000.0
        fee = self.config.backtest.fee_bps / 10000.0

        if position.side == "LONG":
            exec_entry = entry_price * (1 + slip)
            exec_exit = close_price * (1 - slip)
            pnl = (exec_exit - exec_entry) * position.quantity
        else:
            exec_entry = entry_price * (1 - slip)
            exec_exit = close_price * (1 + slip)
            pnl = (exec_entry - exec_exit) * position.quantity

        fees = (exec_entry + exec_exit) * position.quantity * fee
        pnl -= fees
        portfolio.equity += pnl
        trade = Trade(
            trade_id=str(uuid4()),
            order_id=order_id,
            symbol=signal.symbol,
            entry_price=exec_entry,
            exit_price=exec_exit,
            quantity=position.quantity,
            pnl=pnl,
            fees=fees,
            slippage_bps=self.config.backtest.slippage_bps,
            strategy=signal.metadata.get("strategy"),
        )
        self.state_repo.save_trade(trade)
        self.stats.add_trade(trade)
        portfolio.open_positions.pop(signal.symbol, None)

        if pnl < 0:
            portfolio.consecutive_losses += 1
        else:
            portfolio.consecutive_losses = 0

    @staticmethod
    def _print_backtest_report(report, final_equity: float, simulated_days: int) -> None:
        print("=== Backtest Summary ===")
        if simulated_days:
            print(f"Simulated days: {simulated_days}")
        print(f"Total trades: {report.total_trades}")
        print(f"Wins / Losses: {report.wins} / {report.losses}")
        print(f"Win rate: {report.win_rate:.2%}")
        print(f"Max drawdown: {report.max_drawdown:.2%}")
        print(f"PnL value: {report.pnl_value:.2f}")
        print(f"PnL %: {report.pnl_pct:.2%}")
        print(f"Final equity: {final_equity:.2f}")

    @staticmethod
    def _print_ml_recommendation(result) -> None:
        print("=== ML Recommendation ===")
        print(f"Stop loss pct: {result.stop_loss_pct:.4f}")
        print(f"Take profit pct: {result.take_profit_pct:.4f}")
        if result.strategy_confidence:
            for strategy, confidence in result.strategy_confidence.items():
                print(f"{strategy} confidence: {confidence:.2f}")
        if result.notes:
            print("Notes: " + "; ".join(result.notes))

    def _write_ml_recommendation(self, result) -> None:
        payload = {
            "stop_loss_pct": result.stop_loss_pct,
            "take_profit_pct": result.take_profit_pct,
            "strategy_confidence": result.strategy_confidence,
            "notes": result.notes,
        }
        path = self.config.paths.state_dir / "ml_recommendations.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _prompt_apply_ml(self, result) -> None:
        try:
            answer = input("Apply ML recommendations to config.ini? [y/N]: ").strip().lower()
        except EOFError:
            return
        if answer in {"y", "yes"}:
            apply_recommendation(self.config.config_path, result)
            print(f"Updated config: {self.config.config_path}")

    def _apply_backtest_stops(self, candle, portfolio: PortfolioState) -> None:
        if not portfolio.open_positions:
            return
        stop_pct = self.config.risk.stop_loss_pct
        tp_pct = self.config.risk.take_profit_pct
        trailing_pct = self.config.risk.trailing_take_profit_pct
        if stop_pct <= 0 and tp_pct <= 0 and trailing_pct <= 0:
            return

        for symbol, position in list(portfolio.open_positions.items()):
            if symbol != candle.symbol:
                continue
            if position.side == "LONG":
                position.max_price = max(position.max_price, candle.high)
                position.min_price = min(position.min_price, candle.low)
            else:
                position.min_price = min(position.min_price, candle.low)
                position.max_price = max(position.max_price, candle.high)
            stop_price = None
            take_price = None
            trailing_price = None
            if position.side == "LONG":
                if stop_pct > 0:
                    stop_price = position.entry_price * (1 - stop_pct)
                if tp_pct > 0:
                    take_price = position.entry_price * (1 + tp_pct)
                if trailing_pct > 0:
                    activation = position.entry_price * (1 + (tp_pct if tp_pct > 0 else trailing_pct))
                    if position.max_price >= activation:
                        trailing_price = position.max_price * (1 - trailing_pct)
                stop_hit = stop_price is not None and candle.low <= stop_price
                take_hit = take_price is not None and candle.high >= take_price
                trailing_hit = trailing_price is not None and candle.low <= trailing_price
            else:
                if stop_pct > 0:
                    stop_price = position.entry_price * (1 + stop_pct)
                if tp_pct > 0:
                    take_price = position.entry_price * (1 - tp_pct)
                if trailing_pct > 0:
                    activation = position.entry_price * (1 - (tp_pct if tp_pct > 0 else trailing_pct))
                    if position.min_price <= activation:
                        trailing_price = position.min_price * (1 + trailing_pct)
                stop_hit = stop_price is not None and candle.high >= stop_price
                take_hit = take_price is not None and candle.low <= take_price
                trailing_hit = trailing_price is not None and candle.high >= trailing_price

            if not stop_hit and not take_hit and not trailing_hit:
                continue

            if stop_hit:
                exit_price = stop_price
                exit_reason = "stop_loss"
            elif trailing_hit:
                exit_price = trailing_price
                exit_reason = "trailing_take_profit"
            else:
                exit_price = take_price
                exit_reason = "take_profit"

            slip = self.config.backtest.slippage_bps / 10000.0
            fee = self.config.backtest.fee_bps / 10000.0

            if position.side == "LONG":
                exec_entry = position.entry_price * (1 + slip)
                exec_exit = exit_price * (1 - slip)
                pnl = (exec_exit - exec_entry) * position.quantity
            else:
                exec_entry = position.entry_price * (1 - slip)
                exec_exit = exit_price * (1 + slip)
                pnl = (exec_entry - exec_exit) * position.quantity

            fees = (exec_entry + exec_exit) * position.quantity * fee
            pnl -= fees
            portfolio.equity += pnl
            trade = Trade(
                trade_id=str(uuid4()),
                order_id=f"{exit_reason}_{uuid4()}",
                symbol=symbol,
                entry_price=exec_entry,
                exit_price=exec_exit,
                quantity=position.quantity,
                pnl=pnl,
                fees=fees,
                slippage_bps=self.config.backtest.slippage_bps,
                strategy="stop_exit",
            )
            self.state_repo.save_trade(trade)
            self.stats.add_trade(trade)
            portfolio.open_positions.pop(symbol, None)
            if pnl < 0:
                portfolio.consecutive_losses += 1
            else:
                portfolio.consecutive_losses = 0

    def _liquidate_positions(self, last_prices: dict[str, float], portfolio: PortfolioState) -> None:
        if not portfolio.open_positions:
            return
        for symbol, position in list(portfolio.open_positions.items()):
            price = last_prices.get(symbol)
            if price is None:
                continue
            slip = self.config.backtest.slippage_bps / 10000.0
            fee = self.config.backtest.fee_bps / 10000.0
            if position.side == "LONG":
                exec_entry = position.entry_price * (1 + slip)
                exec_exit = price * (1 - slip)
                pnl = (exec_exit - exec_entry) * position.quantity
            else:
                exec_entry = position.entry_price * (1 - slip)
                exec_exit = price * (1 + slip)
                pnl = (exec_entry - exec_exit) * position.quantity
            fees = (exec_entry + exec_exit) * position.quantity * fee
            pnl -= fees
            portfolio.equity += pnl
            trade = Trade(
                trade_id=str(uuid4()),
                order_id=f"forced_exit_{uuid4()}",
                symbol=symbol,
                entry_price=exec_entry,
                exit_price=exec_exit,
                quantity=position.quantity,
                pnl=pnl,
                fees=fees,
                slippage_bps=self.config.backtest.slippage_bps,
                strategy="forced_exit",
            )
            self.state_repo.save_trade(trade)
            self.stats.add_trade(trade)
            portfolio.open_positions.pop(symbol, None)

    def _simulated_days(self) -> int:
        if self.config.backtest.days_back > 0:
            return self.config.backtest.days_back
        if self.config.backtest.start_ts > 0 and self.config.backtest.end_ts > 0:
            seconds = self.config.backtest.end_ts - self.config.backtest.start_ts
            return max(1, int(seconds / 86400))
        return 0

    def _increment_order(self) -> None:
        if not hasattr(self, "_order_count"):
            self._order_count = 0
        self._order_count += 1
