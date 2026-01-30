from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

from analytics.collector import StatisticsCollector
from app.mode_runner import ModeRunner
from config.config_schema import AppConfig
from execution.execution_engine import ExecutionEngine
from execution.order_tracker import FillEvent, OrderTracker
from features.feature_pipeline import FeaturePipeline
from monitoring.killswitch import KillSwitch
from risk.metrics import compute_exposure, update_daily_drawdown
from risk.risk_manager import RiskManager
from signals.signal import Signal
import json
from uuid import uuid4

from state.models import (
    BacktestSummary,
    Fill,
    Order,
    OrderState,
    PortfolioState,
    Position,
    Trade,
    TradeMetrics,
    order_state_from_status,
)
from state.state_machine import OrderStateMachine
from state.repository import StateRepository
from strategies.manager import StrategyManager
from utils.logger import get_logger, log_extra
from utils.time import timeframe_to_seconds


logger = get_logger("app.lifecycle")


@dataclass
class AtrState:
    trs: deque[float]
    prev_close: float | None = None
    atr: float = 0.0


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
    order_tracker: OrderTracker | None = None

    def run(self) -> None:
        started_at = int(time.time())
        portfolio = PortfolioState(
            equity=self.config.risk.initial_equity,
            daily_drawdown=0.0,
            consecutive_losses=0,
            daily_start_equity=self.config.risk.initial_equity,
            daily_peak_equity=self.config.risk.initial_equity,
            daily_day=started_at // 86400,
        )
        logger.info("starting trading application")
        use_local = self.config.runtime.mode == "backtest" and self.config.backtest.fast_local
        if not use_local:
            self.strategy_manager.start()
        else:
            logger.info("backtest fast_local enabled (single-process strategies)")
        if self.order_tracker and self.config.runtime.mode != "backtest":
            self.order_tracker.start()
        self._maybe_run_handshake()
        heartbeat = 0
        total_signals = 0
        self._order_count = 0
        last_prices: dict[str, float] = {}
        last_timestamp = 0
        self._last_prices = last_prices
        self._atr_state: dict[tuple[str, str], AtrState] = {}
        candle_count = 0

        try:
            for candle in self.mode_runner.stream():
                if self.killswitch.triggered:
                    logger.error("killswitch triggered: %s", self.killswitch.reason)
                    self._handle_killswitch()
                    break
                self._update_atr(candle)
                self._apply_candle_stops(candle, portfolio)
                self._apply_time_exits(candle, portfolio)
                _ = self.feature_pipeline.transform(candle)
                last_prices[candle.symbol] = candle.close
                last_timestamp = candle.timestamp
                self._last_prices = last_prices
                self._refresh_portfolio_metrics(portfolio, candle.timestamp)
                candle_count += 1
                if use_local:
                    signals = self.strategy_manager.local_signals(candle)
                else:
                    signals = self.strategy_manager.on_candle(candle)
                for signal in signals:
                    self._handle_signal(signal, portfolio, candle.timestamp)
                    total_signals += 1
                if self.order_tracker and self.config.runtime.mode != "backtest":
                    self._process_fill_events(portfolio)
                heartbeat += 1
                if candle_count % 500 == 0:
                    logger.info(
                        "backtest progress candles=%d signals=%d open_positions=%d",
                        candle_count,
                        total_signals,
                        len(portfolio.open_positions),
                    )
                if heartbeat % 50 == 0 and not use_local:
                    self.strategy_manager.restart_failed()
        except KeyboardInterrupt:
            logger.info("shutdown requested by user")
        finally:
            if not use_local:
                self.strategy_manager.stop()
            if self.order_tracker and self.config.runtime.mode != "backtest":
                self._process_fill_events(portfolio)
                self.order_tracker.stop()
            finished_at = int(time.time())
            if self.config.runtime.mode == "backtest":
                self._liquidate_positions(last_prices, portfolio, last_timestamp)
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
                run_id = str(uuid4())
                summary = BacktestSummary(
                    run_id=run_id,
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
                metrics = self.stats.backtest_metrics(
                    run_id=run_id,
                    initial_equity=self.config.risk.initial_equity,
                    final_equity=portfolio.equity,
                    simulated_days=simulated_days,
                )
                self.state_repo.save_backtest_metrics(metrics)
                self._print_backtest_report(report, portfolio.equity, simulated_days)
            self.state_repo.close()

    def _handle_signal(self, signal: Signal, portfolio: PortfolioState, timestamp: int) -> None:
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
                self._handle_killswitch()
            return

        decision_size = decision.size
        metadata = signal.metadata if isinstance(signal.metadata, dict) else {}
        price = self._parse_float(metadata.get("price"))
        min_notional_value = self._parse_float(metadata.get("min_notional"))
        if min_notional_value > 0 and decision_size < min_notional_value:
            logger.warning(
                "min notional exceeds risk size size=%s min=%s",
                decision_size,
                min_notional_value,
            )
            return
        max_notional_value = self._parse_float(metadata.get("max_notional"))
        if max_notional_value > 0 and decision_size > max_notional_value:
            logger.debug("max notional override size=%s max=%s", decision_size, max_notional_value)
            decision_size = max_notional_value

        if price > 0:
            execution_size = decision_size / price
        else:
            execution_size = decision_size

        min_quantity_value = self._parse_float(metadata.get("min_quantity"))
        if min_quantity_value > 0 and execution_size < min_quantity_value:
            logger.warning(
                "min quantity exceeds risk size qty=%s min=%s",
                execution_size,
                min_quantity_value,
            )
            return

        max_quantity_value = self._parse_float(metadata.get("max_quantity"))
        if max_quantity_value > 0 and execution_size > max_quantity_value:
            logger.debug("max quantity override qty=%s max=%s", execution_size, max_quantity_value)
            execution_size = max_quantity_value
            if price > 0:
                decision_size = execution_size * price

        if execution_size <= 0:
            logger.warning("execution size invalid size=%s", execution_size)
            return

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
            status=OrderState.CREATED,
            signal_id=signal.signal_id,
        )
        target_state = order_state_from_status(result.response.status)
        order = self._transition_order(order, target_state)
        self.state_repo.save_order(order)
        log_extra(
            logger,
            "order recorded",
            trace_id=signal.signal_id,
            order_id=order.order_id,
            status=order.status.value,
            symbol=order.symbol,
            quantity=order.quantity,
        )

        if result.response.status.lower() in {"rejected", "error", "failed"}:
            logger.warning("order rejected: %s", result.response.status)
            return

        if self.order_tracker and self.config.runtime.mode in {"forward", "live"}:
            self.order_tracker.register_order(order.order_id, order.symbol)
        else:
            self._apply_accounting(signal, execution_size, portfolio, order.order_id, timestamp)

    def _apply_accounting(
        self,
        signal: Signal,
        size: float,
        portfolio: PortfolioState,
        order_id: str,
        timestamp: int,
    ) -> None:
        metadata = signal.metadata if isinstance(signal.metadata, dict) else {}
        price = self._parse_float(metadata.get("price"))
        if price <= 0:
            return
        timeframe = metadata.get("timeframe")
        atr_value = self._atr_value(signal.symbol, timeframe) if timeframe else 0.0
        side = signal.direction
        if side not in {"LONG", "SHORT"}:
            return
        self._apply_execution(
            symbol=signal.symbol,
            side=side,
            quantity=size,
            price=price,
            portfolio=portfolio,
            timestamp=timestamp,
            order_id=order_id,
            strategy=metadata.get("strategy"),
            allow_add=False,
            max_hold_seconds=self._parse_hold_seconds(signal.horizon),
            entry_atr=atr_value,
        )

    def _process_fill_events(self, portfolio: PortfolioState) -> None:
        if not self.order_tracker:
            return
        fills = self.order_tracker.drain_fills()
        for fill in fills:
            self._apply_fill_accounting(fill, portfolio)

    def _apply_fill_accounting(self, fill: FillEvent, portfolio: PortfolioState) -> None:
        side = "LONG" if fill.side.lower() == "buy" else "SHORT"
        symbol = fill.symbol
        qty = fill.quantity
        price = fill.price
        if qty <= 0 or price <= 0:
            return

        self.state_repo.save_fill(
            Fill(
                fill_id=fill.exec_id or f"exec_{fill.order_id}_{fill.timestamp}",
                order_id=fill.order_id,
                symbol=symbol,
                side=fill.side,
                price=price,
                quantity=qty,
                fee=fill.fee,
                timestamp=fill.timestamp,
            )
        )
        log_extra(
            logger,
            "fill received",
            order_id=fill.order_id,
            symbol=fill.symbol,
            price=fill.price,
            quantity=fill.quantity,
            fee=fill.fee,
        )

        self._apply_execution(
            symbol=symbol,
            side=side,
            quantity=qty,
            price=price,
            portfolio=portfolio,
            timestamp=fill.timestamp,
            order_id=fill.order_id,
            strategy="fill_execution",
            fee_override=fill.fee,
            slippage_override=0.0,
            allow_add=True,
            max_hold_seconds=0,
            entry_atr=0.0,
        )

    def _apply_execution(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        portfolio: PortfolioState,
        timestamp: int,
        order_id: str,
        strategy: str | None,
        allow_add: bool,
        max_hold_seconds: int,
        entry_atr: float,
        fee_override: float | None = None,
        slippage_override: float | None = None,
    ) -> None:
        if quantity <= 0 or price <= 0:
            return
        position = portfolio.open_positions.get(symbol)
        slippage_rate = self._slippage_rate(slippage_override)
        entry_fee = self._fee_for_qty(price, quantity, fee_override)

        if position is None:
            portfolio.open_positions[symbol] = Position(
                symbol=symbol,
                quantity=quantity,
                entry_price=price,
                side=side,
                max_price=price,
                min_price=price,
                entry_ts=timestamp,
                max_hold_seconds=max_hold_seconds,
                entry_atr=entry_atr if entry_atr > 0 else 0.0,
                fees_paid=entry_fee,
            )
            self._refresh_portfolio_metrics(portfolio, timestamp)
            return

        if position.side == side:
            if not allow_add:
                return
            new_qty = position.quantity + quantity
            position.entry_price = (position.entry_price * position.quantity + price * quantity) / new_qty
            position.quantity = new_qty
            position.max_price = max(position.max_price, price)
            position.min_price = min(position.min_price, price)
            position.fees_paid += entry_fee
            if position.entry_atr <= 0 and entry_atr > 0:
                position.entry_atr = entry_atr
            self._refresh_portfolio_metrics(portfolio, timestamp)
            return

        exit_qty = min(position.quantity, quantity)
        exit_fee_override = self._allocate_fee_override(fee_override, exit_qty, quantity)
        exit_fee = self._fee_for_qty(price, exit_qty, exit_fee_override)
        entry_fee_share = 0.0
        if position.quantity > 0:
            entry_fee_share = position.fees_paid * (exit_qty / position.quantity)
        pnl = self._close_position(
            position=position,
            exit_price=price,
            exit_qty=exit_qty,
            portfolio=portfolio,
            timestamp=timestamp,
            order_id=order_id,
            strategy=strategy,
            slippage_rate=slippage_rate,
            exit_fee=exit_fee,
            entry_fee_share=entry_fee_share,
        )

        position.quantity -= exit_qty
        position.fees_paid = max(0.0, position.fees_paid - entry_fee_share)
        if position.quantity <= 0:
            portfolio.open_positions.pop(symbol, None)
        if quantity > exit_qty:
            remaining_qty = quantity - exit_qty
            remaining_fee = max(0.0, entry_fee - exit_fee)
            portfolio.open_positions[symbol] = Position(
                symbol=symbol,
                quantity=remaining_qty,
                entry_price=price,
                side=side,
                max_price=price,
                min_price=price,
                entry_ts=timestamp,
                max_hold_seconds=max_hold_seconds,
                entry_atr=entry_atr if entry_atr > 0 else 0.0,
                fees_paid=remaining_fee,
            )
        self._refresh_portfolio_metrics(portfolio, timestamp)

        if pnl < 0:
            portfolio.consecutive_losses += 1
        else:
            portfolio.consecutive_losses = 0

    def _close_position(
        self,
        position: Position,
        exit_price: float,
        exit_qty: float,
        portfolio: PortfolioState,
        timestamp: int,
        order_id: str,
        strategy: str | None,
        slippage_rate: float,
        exit_fee: float,
        entry_fee_share: float,
    ) -> float:
        if exit_qty <= 0:
            return 0.0
        if position.side == "LONG":
            exec_entry = position.entry_price * (1 + slippage_rate)
            exec_exit = exit_price * (1 - slippage_rate)
            pnl = (exec_exit - exec_entry) * exit_qty
        else:
            exec_entry = position.entry_price * (1 - slippage_rate)
            exec_exit = exit_price * (1 + slippage_rate)
            pnl = (exec_entry - exec_exit) * exit_qty

        fees = entry_fee_share + exit_fee
        pnl -= fees
        portfolio.equity += pnl
        trade = Trade(
            trade_id=str(uuid4()),
            order_id=order_id,
            symbol=position.symbol,
            entry_price=exec_entry,
            exit_price=exec_exit,
            quantity=exit_qty,
            pnl=pnl,
            fees=fees,
            slippage_bps=slippage_rate * 10000.0,
            strategy=strategy,
        )
        logger.debug(
            "trade closed symbol=%s entry=%s exit=%s qty=%s pnl=%s fees=%s",
            trade.symbol,
            trade.entry_price,
            trade.exit_price,
            trade.quantity,
            trade.pnl,
            trade.fees,
        )
        self.state_repo.save_trade(trade)
        self.stats.add_trade(trade)
        self.state_repo.save_trade_metrics(self._trade_metrics(trade))
        log_extra(
            logger,
            "trade closed",
            symbol=trade.symbol,
            pnl=trade.pnl,
            fees=trade.fees,
            quantity=trade.quantity,
        )
        return pnl

    def _slippage_rate(self, override: float | None = None) -> float:
        if override is not None:
            return override
        if self.config.runtime.mode == "live":
            return 0.0
        return self.config.backtest.slippage_bps / 10000.0

    def _fee_rate(self) -> float:
        if self.config.runtime.mode == "live":
            return 0.0
        return self.config.backtest.fee_bps / 10000.0

    def _fee_for_qty(self, price: float, quantity: float, fee_override: float | None = None) -> float:
        if fee_override is not None:
            return fee_override
        return price * quantity * self._fee_rate()

    @staticmethod
    def _allocate_fee_override(fee_override: float | None, portion_qty: float, total_qty: float) -> float | None:
        if fee_override is None:
            return None
        if total_qty <= 0:
            return 0.0
        return fee_override * (portion_qty / total_qty)

    def _refresh_portfolio_metrics(self, portfolio: PortfolioState, timestamp: int) -> None:
        update_daily_drawdown(portfolio, timestamp)
        prices = getattr(self, "_last_prices", {})
        exposure = compute_exposure(portfolio.open_positions, prices, portfolio.equity)
        portfolio.gross_exposure = exposure.gross_exposure
        portfolio.correlation = exposure.correlation
        portfolio.expectancy = self.stats.snapshot().expectancy

    def _handle_killswitch(self) -> None:
        if getattr(self, "_killswitch_handled", False):
            return
        self._killswitch_handled = True
        self._cancel_open_orders()

    def _cancel_open_orders(self) -> None:
        if not self.order_tracker:
            return
        orders = self.order_tracker.open_orders()
        if not orders:
            return
        for order_id, symbol in orders.items():
            if not self.execution_engine.cancel_order(order_id, symbol):
                logger.warning("failed to cancel order %s (%s)", order_id, symbol)

    @staticmethod
    def _parse_float(value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _parse_hold_seconds(horizon: str) -> int:
        try:
            return timeframe_to_seconds(horizon)
        except (TypeError, ValueError):
            return 0

    def _update_atr(self, candle) -> None:
        period = self.config.risk.atr_period
        if period <= 0:
            return
        key = (candle.symbol, candle.timeframe)
        state = self._atr_state.get(key)
        if state is None:
            state = AtrState(trs=deque(maxlen=period))
            self._atr_state[key] = state
        if state.prev_close is None:
            tr = candle.high - candle.low
        else:
            tr = max(
                candle.high - candle.low,
                abs(candle.high - state.prev_close),
                abs(candle.low - state.prev_close),
            )
        state.trs.append(tr)
        if len(state.trs) >= period:
            state.atr = sum(state.trs) / len(state.trs)
        state.prev_close = candle.close

    def _atr_value(self, symbol: str, timeframe: str) -> float:
        state = self._atr_state.get((symbol, timeframe))
        if not state:
            return 0.0
        return state.atr

    @staticmethod
    def _transition_order(order: Order, target: OrderState) -> Order:
        if order.status == target:
            return order
        machine = OrderStateMachine(order)
        try:
            if target == OrderState.FILLED:
                order = machine.transition(OrderState.SUBMITTED)
                order = machine.transition(OrderState.FILLED)
                return order
            return machine.transition(target)
        except ValueError:
            return Order(
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                status=target,
                signal_id=order.signal_id,
            )

    def _maybe_run_handshake(self) -> None:
        if not self.config.demo_trading_enabled():
            return
        if not self.config.exchange.demo_handshake:
            return
        if not self.config.exchange.api_key or not self.config.exchange.api_secret:
            logger.warning("demo handshake skipped: missing API key/secret")
            return
        symbol = self.config.exchange.handshake_symbol
        qty = self.config.exchange.handshake_quantity
        if qty <= 0:
            logger.debug("demo handshake skipped: handshake_quantity=%s", qty)
            return
        try:
            logger.info("running demo handshake for %s qty=%s", symbol, qty)
            self.execution_engine.handshake(symbol, qty)
        except Exception as exc:  # noqa: BLE001
            logger.warning("demo handshake failed: %s", exc)

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

    def _apply_candle_stops(self, candle, portfolio: PortfolioState) -> None:
        if not portfolio.open_positions:
            return
        stop_pct = self.config.risk.stop_loss_pct
        tp_pct = self.config.risk.take_profit_pct
        trailing_pct = self.config.risk.trailing_take_profit_pct
        atr_enabled = (
            self.config.risk.atr_period > 0
            and (
                self.config.risk.atr_sl_mult > 0
                or self.config.risk.atr_tp_mult > 0
                or self.config.risk.atr_trailing_mult > 0
            )
        )
        if stop_pct <= 0 and tp_pct <= 0 and trailing_pct <= 0 and not atr_enabled:
            return

        updated = False
        slippage_rate = self._slippage_rate()
        atr_value = self._atr_value(candle.symbol, candle.timeframe)
        for symbol, position in list(portfolio.open_positions.items()):
            if symbol != candle.symbol:
                continue
            if position.entry_atr <= 0 and atr_value > 0:
                position.entry_atr = atr_value
            if position.side == "LONG":
                position.max_price = max(position.max_price, candle.high)
                position.min_price = min(position.min_price, candle.low)
            else:
                position.min_price = min(position.min_price, candle.low)
                position.max_price = max(position.max_price, candle.high)
            stop_price = None
            take_price = None
            trailing_price = None
            atr_base = position.entry_atr if position.entry_atr > 0 else atr_value
            if atr_enabled:
                if atr_base <= 0:
                    continue
                sl_dist = self.config.risk.atr_sl_mult * atr_base if self.config.risk.atr_sl_mult > 0 else None
                tp_dist = self.config.risk.atr_tp_mult * atr_base if self.config.risk.atr_tp_mult > 0 else None
                trail_dist = (
                    self.config.risk.atr_trailing_mult * atr_base
                    if self.config.risk.atr_trailing_mult > 0
                    else None
                )
                if position.side == "LONG":
                    if sl_dist:
                        stop_price = position.entry_price - sl_dist
                    if tp_dist:
                        take_price = position.entry_price + tp_dist
                    if trail_dist and position.max_price - position.entry_price >= trail_dist:
                        trailing_price = position.max_price - trail_dist
                    stop_hit = stop_price is not None and candle.low <= stop_price
                    take_hit = take_price is not None and candle.high >= take_price
                    trailing_hit = trailing_price is not None and candle.low <= trailing_price
                else:
                    if sl_dist:
                        stop_price = position.entry_price + sl_dist
                    if tp_dist:
                        take_price = position.entry_price - tp_dist
                    if trail_dist and position.entry_price - position.min_price >= trail_dist:
                        trailing_price = position.min_price + trail_dist
                    stop_hit = stop_price is not None and candle.high >= stop_price
                    take_hit = take_price is not None and candle.low <= take_price
                    trailing_hit = trailing_price is not None and candle.high >= trailing_price
            else:
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

            exit_fee = self._fee_for_qty(exit_price, position.quantity)
            pnl = self._close_position(
                position=position,
                exit_price=exit_price,
                exit_qty=position.quantity,
                portfolio=portfolio,
                timestamp=candle.timestamp,
                order_id=f"{exit_reason}_{uuid4()}",
                strategy="stop_exit",
                slippage_rate=slippage_rate,
                exit_fee=exit_fee,
                entry_fee_share=position.fees_paid,
            )
            portfolio.open_positions.pop(symbol, None)
            updated = True
            if pnl < 0:
                portfolio.consecutive_losses += 1
            else:
                portfolio.consecutive_losses = 0

        if updated:
            self._refresh_portfolio_metrics(portfolio, candle.timestamp)

    def _apply_time_exits(self, candle, portfolio: PortfolioState) -> None:
        if not portfolio.open_positions:
            return
        updated = False
        slippage_rate = self._slippage_rate()
        for symbol, position in list(portfolio.open_positions.items()):
            if symbol != candle.symbol:
                continue
            if position.entry_ts <= 0 or position.max_hold_seconds <= 0:
                continue
            if candle.timestamp - position.entry_ts < position.max_hold_seconds:
                continue
            exit_price = candle.close
            if exit_price <= 0:
                continue
            exit_fee = self._fee_for_qty(exit_price, position.quantity)
            pnl = self._close_position(
                position=position,
                exit_price=exit_price,
                exit_qty=position.quantity,
                portfolio=portfolio,
                timestamp=candle.timestamp,
                order_id=f"time_exit_{uuid4()}",
                strategy="time_exit",
                slippage_rate=slippage_rate,
                exit_fee=exit_fee,
                entry_fee_share=position.fees_paid,
            )
            portfolio.open_positions.pop(symbol, None)
            updated = True
            if pnl < 0:
                portfolio.consecutive_losses += 1
            else:
                portfolio.consecutive_losses = 0

        if updated:
            self._refresh_portfolio_metrics(portfolio, candle.timestamp)

    def _liquidate_positions(
        self,
        last_prices: dict[str, float],
        portfolio: PortfolioState,
        timestamp: int,
    ) -> None:
        if not portfolio.open_positions:
            return
        slippage_rate = self._slippage_rate()
        for symbol, position in list(portfolio.open_positions.items()):
            price = last_prices.get(symbol)
            if price is None:
                continue
            exit_fee = self._fee_for_qty(price, position.quantity)
            self._close_position(
                position=position,
                exit_price=price,
                exit_qty=position.quantity,
                portfolio=portfolio,
                timestamp=timestamp,
                order_id=f"forced_exit_{uuid4()}",
                strategy="forced_exit",
                slippage_rate=slippage_rate,
                exit_fee=exit_fee,
                entry_fee_share=position.fees_paid,
            )
            portfolio.open_positions.pop(symbol, None)
        self._refresh_portfolio_metrics(portfolio, timestamp)

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

    @staticmethod
    def _trade_metrics(trade: Trade) -> TradeMetrics:
        notional = trade.entry_price * trade.quantity
        gross_pnl = trade.pnl + trade.fees
        if notional > 0:
            return_pct = trade.pnl / notional
            fee_pct = trade.fees / notional
        else:
            return_pct = 0.0
            fee_pct = 0.0
        return TradeMetrics(
            trade_id=trade.trade_id,
            symbol=trade.symbol,
            strategy=trade.strategy,
            notional=notional,
            gross_pnl=gross_pnl,
            net_pnl=trade.pnl,
            return_pct=return_pct,
            fee_pct=fee_pct,
            slippage_bps=trade.slippage_bps,
        )
