from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .config import BotConfig


@dataclass(slots=True)
class ProfitLedger:
    base_capital: float
    trading_balance: float
    profit_wallet_balance: float = 0.0
    realized_net_profit: float = 0.0

    @classmethod
    def from_base_capital(cls, base_capital: float) -> "ProfitLedger":
        return cls(base_capital=base_capital, trading_balance=base_capital)

    def apply_closed_trade(self, net_pnl: float) -> float:
        self.realized_net_profit += net_pnl
        self.trading_balance += net_pnl
        swept = 0.0
        if self.trading_balance > self.base_capital:
            swept = self.trading_balance - self.base_capital
            self.profit_wallet_balance += swept
            self.trading_balance = self.base_capital
        return swept

    @property
    def total_equity(self) -> float:
        return self.trading_balance + self.profit_wallet_balance


@dataclass(slots=True)
class DailyRiskState:
    day: date | None = None
    consecutive_losses: int = 0
    daily_realized_pnl: float = 0.0
    cooldown_until_index: int = -1
    stopped_for_day: bool = False
    stop_reason: str | None = None

    def reset_for_day(self, day: date) -> None:
        self.day = day
        self.daily_realized_pnl = 0.0
        self.consecutive_losses = 0
        self.stopped_for_day = False
        self.stop_reason = None


class RiskManager:
    def __init__(self, config: BotConfig):
        self.config = config
        self.state = DailyRiskState()

    def on_new_bar(self, bar_day: date) -> None:
        if self.state.day != bar_day:
            self.state.reset_for_day(bar_day)

    def can_open_trade(self, index: int) -> bool:
        return not self.state.stopped_for_day and index > self.state.cooldown_until_index

    def register_closed_trade(self, index: int, net_pnl: float) -> str | None:
        self.state.daily_realized_pnl += net_pnl
        if net_pnl < 0:
            self.state.consecutive_losses += 1
        else:
            self.state.consecutive_losses = 0
        self.state.cooldown_until_index = index + self.config.risk.cooldown_bars
        daily_loss_limit = self.config.base_capital * self.config.risk.max_daily_loss_pct
        if self.state.daily_realized_pnl <= -daily_loss_limit:
            self.state.stopped_for_day = True
            self.state.stop_reason = "max_daily_loss_pct"
        elif self.state.consecutive_losses >= self.config.risk.max_consecutive_losses:
            self.state.stopped_for_day = True
            self.state.stop_reason = "max_consecutive_losses"
        return self.state.stop_reason
