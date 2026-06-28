from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class Position:
    entry_index: int
    entry_time: datetime
    entry_price: float
    stop_price: float
    take_profit_price: float
    quantity: float
    entry_fee: float
    bars_held: int = 0


@dataclass(slots=True)
class Trade:
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    net_pnl: float
    exit_reason: str
    bars_held: int
    stop_price: float
    take_profit_price: float

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["entry_time"] = self.entry_time.isoformat()
        payload["exit_time"] = self.exit_time.isoformat()
        return payload


@dataclass(slots=True)
class WalletSnapshot:
    trading_balance: float
    profit_wallet_balance: float
    total_equity: float


@dataclass(slots=True)
class BacktestMetrics:
    win_rate: float
    net_pnl: float
    profit_factor: float
    max_drawdown: float
    total_trades: int
    average_win: float
    average_loss: float
    ending_trading_balance: float
    profit_wallet_balance: float
    total_equity: float
    stopped_days: int
    risk_adjusted_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BacktestResult:
    metrics: BacktestMetrics
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    daily_stop_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics.to_dict(),
            "trades": [trade.to_dict() for trade in self.trades],
            "equity_curve": self.equity_curve,
            "daily_stop_reasons": self.daily_stop_reasons,
        }
