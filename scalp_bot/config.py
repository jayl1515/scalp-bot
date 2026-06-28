from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RiskConfig:
    max_daily_loss_pct: float = 0.05
    max_consecutive_losses: int = 3
    cooldown_bars: int = 5


@dataclass(slots=True)
class StrategyConfig:
    ema_fast_period: int = 8
    ema_slow_period: int = 21
    atr_period: int = 14
    min_atr_pct: float = 0.0015
    max_atr_pct: float = 0.02
    volume_lookback: int = 20
    volume_multiplier: float = 1.05
    risk_per_trade_pct: float = 0.01
    max_position_pct: float = 1.0
    stop_atr_multiple: float = 1.2
    reward_to_risk: float = 1.4
    max_hold_bars: int = 10
    min_trade_notional: float = 5.0


@dataclass(slots=True)
class OptimizationConfig:
    top_n: int = 5
    grid: dict[str, list[Any]] = field(
        default_factory=lambda: {
            "ema_fast_period": [6, 8, 10],
            "ema_slow_period": [18, 21, 24],
            "volume_multiplier": [1.0, 1.05, 1.1],
            "stop_atr_multiple": [1.0, 1.2, 1.4],
            "reward_to_risk": [1.2, 1.4, 1.6],
            "max_hold_bars": [8, 10, 12],
        }
    )


@dataclass(slots=True)
class BotConfig:
    base_capital: float = 20.0
    fee_rate: float = 0.001
    slippage_bps: float = 5.0
    risk: RiskConfig = field(default_factory=RiskConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    optimization: OptimizationConfig = field(default_factory=OptimizationConfig)


def _merge_dataclass(cls: type, data: dict[str, Any] | None):
    if not data:
        return cls()
    defaults = cls()
    for key, value in data.items():
        setattr(defaults, key, value)
    return defaults


def load_config(path: str | Path) -> BotConfig:
    raw = json.loads(Path(path).read_text())
    return BotConfig(
        base_capital=float(raw.get("base_capital", 20.0)),
        fee_rate=float(raw.get("fee_rate", 0.001)),
        slippage_bps=float(raw.get("slippage_bps", 5.0)),
        risk=_merge_dataclass(RiskConfig, raw.get("risk")),
        strategy=_merge_dataclass(StrategyConfig, raw.get("strategy")),
        optimization=OptimizationConfig(
            top_n=int(raw.get("optimization", {}).get("top_n", 5)),
            grid=raw.get("optimization", {}).get("grid", OptimizationConfig().grid),
        ),
    )
