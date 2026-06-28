from __future__ import annotations

from dataclasses import replace

from .config import BotConfig
from .models import BacktestMetrics, BacktestResult, Position, Trade
from .risk import ProfitLedger, RiskManager
from .strategy import ScalpingStrategy

FLOATING_POINT_TOLERANCE = 1e-9
MIN_DRAWDOWN_FLOOR = 0.05
MAX_PROFIT_FACTOR_FOR_SCORING = 5.0
TRADE_QUALITY_SMOOTHING_FACTOR = 5


class Backtester:
    def __init__(self, config: BotConfig):
        self.config = config
        self.strategy = ScalpingStrategy(config.strategy)

    def calculate_position_size(self, entry_price: float, stop_price: float, trading_balance: float) -> float:
        risk_per_unit = max(entry_price - stop_price, 0.0)
        if risk_per_unit <= 0:
            return 0.0
        risk_budget = self.config.base_capital * self.config.strategy.risk_per_trade_pct
        quantity_by_risk = risk_budget / risk_per_unit
        notional_cap = min(
            self.config.base_capital * self.config.strategy.max_position_pct,
            trading_balance,
        )
        quantity_by_notional = notional_cap / entry_price if entry_price else 0.0
        quantity = min(quantity_by_risk, quantity_by_notional)
        if quantity * entry_price < self.config.strategy.min_trade_notional:
            return 0.0
        return max(quantity, 0.0)

    def run(self, candles) -> BacktestResult:
        if not candles:
            raise ValueError("No candles were provided for backtesting.")

        state = self.strategy.prepare(candles)
        ledger = ProfitLedger.from_base_capital(self.config.base_capital)
        risk_manager = RiskManager(self.config)
        trades: list[Trade] = []
        equity_curve = [ledger.total_equity]
        stop_reasons: list[str] = []
        position: Position | None = None
        warmup = self.strategy.warmup_bars()

        for index in range(warmup, len(candles)):
            candle = candles[index]
            risk_manager.on_new_bar(candle.timestamp.date())

            if position:
                position.bars_held += 1
                exit_price: float | None = None
                exit_reason: str | None = None
                stop_hit = candle.low <= position.stop_price
                target_hit = candle.high >= position.take_profit_price
                if stop_hit and target_hit:
                    exit_price = position.stop_price
                    exit_reason = "stop_loss"
                elif stop_hit:
                    exit_price = position.stop_price
                    exit_reason = "stop_loss"
                elif target_hit:
                    exit_price = position.take_profit_price
                    exit_reason = "take_profit"
                elif position.bars_held >= self.config.strategy.max_hold_bars:
                    exit_price = candle.close * (1 - self.config.slippage_bps / 10000)
                    exit_reason = "time_exit"
                elif self.strategy.should_exit_on_close(index, candles, state):
                    exit_price = candle.close * (1 - self.config.slippage_bps / 10000)
                    exit_reason = "signal_exit"

                if exit_price is not None and exit_reason is not None:
                    exit_fee = exit_price * position.quantity * self.config.fee_rate
                    gross_pnl = (exit_price - position.entry_price) * position.quantity
                    net_pnl = gross_pnl - position.entry_fee - exit_fee
                    trades.append(
                        Trade(
                            entry_time=position.entry_time,
                            exit_time=candle.timestamp,
                            entry_price=position.entry_price,
                            exit_price=exit_price,
                            quantity=position.quantity,
                            gross_pnl=gross_pnl,
                            net_pnl=net_pnl,
                            exit_reason=exit_reason,
                            bars_held=position.bars_held,
                            stop_price=position.stop_price,
                            take_profit_price=position.take_profit_price,
                        )
                    )
                    ledger.apply_closed_trade(net_pnl)
                    equity_curve.append(ledger.total_equity)
                    stop_reason = risk_manager.register_closed_trade(index, net_pnl)
                    if stop_reason:
                        stop_reasons.append(f"{candle.timestamp.date().isoformat()}: {stop_reason}")
                    position = None
                continue

            if not risk_manager.can_open_trade(index):
                continue
            if not self.strategy.should_enter(index, candles, state):
                continue

            entry_price = candle.close * (1 + self.config.slippage_bps / 10000)
            atr = state.atr[index]
            stop_price = entry_price - atr * self.config.strategy.stop_atr_multiple
            if stop_price <= 0:
                continue
            quantity = self.calculate_position_size(entry_price, stop_price, ledger.trading_balance)
            if quantity <= 0:
                continue
            notional = entry_price * quantity
            if notional > ledger.trading_balance + FLOATING_POINT_TOLERANCE:
                continue
            take_profit_price = entry_price + (entry_price - stop_price) * self.config.strategy.reward_to_risk
            position = Position(
                entry_index=index,
                entry_time=candle.timestamp,
                entry_price=entry_price,
                stop_price=stop_price,
                take_profit_price=take_profit_price,
                quantity=quantity,
                entry_fee=notional * self.config.fee_rate,
            )

        if position is not None:
            final_candle = candles[-1]
            exit_price = final_candle.close * (1 - self.config.slippage_bps / 10000)
            exit_fee = exit_price * position.quantity * self.config.fee_rate
            gross_pnl = (exit_price - position.entry_price) * position.quantity
            net_pnl = gross_pnl - position.entry_fee - exit_fee
            trades.append(
                Trade(
                    entry_time=position.entry_time,
                    exit_time=final_candle.timestamp,
                    entry_price=position.entry_price,
                    exit_price=exit_price,
                    quantity=position.quantity,
                    gross_pnl=gross_pnl,
                    net_pnl=net_pnl,
                    exit_reason="end_of_data",
                    bars_held=position.bars_held,
                    stop_price=position.stop_price,
                    take_profit_price=position.take_profit_price,
                )
            )
            ledger.apply_closed_trade(net_pnl)
            equity_curve.append(ledger.total_equity)
            stop_reason = risk_manager.register_closed_trade(len(candles) - 1, net_pnl)
            if stop_reason:
                stop_reasons.append(f"{final_candle.timestamp.date().isoformat()}: {stop_reason}")

        metrics = build_metrics(trades, equity_curve, ledger, len(stop_reasons))
        return BacktestResult(metrics=metrics, trades=trades, equity_curve=equity_curve, daily_stop_reasons=stop_reasons)


def build_metrics(trades: list[Trade], equity_curve: list[float], ledger: ProfitLedger, stopped_days: int) -> BacktestMetrics:
    wins = [trade.net_pnl for trade in trades if trade.net_pnl > 0]
    losses = [trade.net_pnl for trade in trades if trade.net_pnl < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    max_drawdown = calculate_max_drawdown(equity_curve)
    total_trades = len(trades)
    win_rate = (len(wins) / total_trades * 100) if total_trades else 0.0
    average_win = gross_profit / len(wins) if wins else 0.0
    average_loss = sum(losses) / len(losses) if losses else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit > 0 else 0.0)
    metrics = BacktestMetrics(
        win_rate=win_rate,
        net_pnl=ledger.realized_net_profit,
        profit_factor=profit_factor,
        max_drawdown=max_drawdown,
        total_trades=total_trades,
        average_win=average_win,
        average_loss=average_loss,
        ending_trading_balance=ledger.trading_balance,
        profit_wallet_balance=ledger.profit_wallet_balance,
        total_equity=ledger.total_equity,
        stopped_days=stopped_days,
    )
    return replace(metrics, risk_adjusted_score=risk_adjusted_score(metrics))


def calculate_max_drawdown(equity_curve: list[float]) -> float:
    peak = equity_curve[0] if equity_curve else 0.0
    max_drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return max_drawdown


def risk_adjusted_score(metrics: BacktestMetrics) -> float:
    if metrics.total_trades == 0:
        return float("-inf")
    drawdown_floor = max(metrics.max_drawdown, MIN_DRAWDOWN_FLOOR)
    capped_profit_factor = 0.0 if metrics.profit_factor == float("inf") else min(
        metrics.profit_factor,
        MAX_PROFIT_FACTOR_FOR_SCORING,
    )
    trade_quality = metrics.total_trades / (
        metrics.total_trades + TRADE_QUALITY_SMOOTHING_FACTOR
    )
    return (metrics.net_pnl / drawdown_floor) * max(capped_profit_factor, 0.5) * trade_quality
