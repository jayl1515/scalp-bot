from __future__ import annotations

from dataclasses import dataclass

from .config import StrategyConfig
from .models import Candle

@dataclass(slots=True)
class StrategyState:
    ema_fast: list[float]
    ema_slow: list[float]
    atr: list[float]
    volume_sma: list[float]


class ScalpingStrategy:
    def __init__(self, config: StrategyConfig):
        self.config = config

    def prepare(self, candles: list[Candle]) -> StrategyState:
        closes = [candle.close for candle in candles]
        volumes = [candle.volume for candle in candles]
        return StrategyState(
            ema_fast=ema(closes, self.config.ema_fast_period),
            ema_slow=ema(closes, self.config.ema_slow_period),
            atr=average_true_range(candles, self.config.atr_period),
            volume_sma=sma(volumes, self.config.volume_lookback),
        )

    def warmup_bars(self) -> int:
        return max(
            self.config.ema_slow_period,
            self.config.atr_period,
            self.config.volume_lookback,
        )

    def should_enter(self, index: int, candles: list[Candle], state: StrategyState) -> bool:
        if index <= 0:
            return False
        candle = candles[index]
        if candle.close == 0:
            return False
        prev = candles[index - 1]
        fast = state.ema_fast[index]
        slow = state.ema_slow[index]
        atr_value = state.atr[index]
        atr_pct = atr_value / candle.close
        avg_volume = state.volume_sma[index]
        trend_ok = candle.close > fast > slow
        volatility_ok = self.config.min_atr_pct <= atr_pct <= self.config.max_atr_pct
        volume_ok = candle.volume >= avg_volume * self.config.volume_multiplier if avg_volume > 0 else False
        breakout_ok = candle.close > prev.high and candle.close > candle.open
        return trend_ok and volatility_ok and volume_ok and breakout_ok

    def should_exit_on_close(self, index: int, candles: list[Candle], state: StrategyState) -> bool:
        candle = candles[index]
        fast = state.ema_fast[index]
        return candle.close < fast or candle.close < candle.open


def ema(values: list[float], period: int) -> list[float]:
    results: list[float] = []
    multiplier = 2 / (period + 1)
    running = values[0] if values else 0.0
    for value in values:
        running = (value - running) * multiplier + running
        results.append(running)
    return results


def sma(values: list[float], period: int) -> list[float]:
    results: list[float] = []
    total = 0.0
    for index, value in enumerate(values):
        total += value
        if index >= period:
            total -= values[index - period]
        length = min(index + 1, period)
        results.append(total / length if length else 0.0)
    return results


def average_true_range(candles: list[Candle], period: int) -> list[float]:
    if not candles:
        return []
    true_ranges: list[float] = [candles[0].high - candles[0].low]
    for index in range(1, len(candles)):
        candle = candles[index]
        prev_close = candles[index - 1].close
        true_ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - prev_close),
                abs(candle.low - prev_close),
            )
        )
    return ema(true_ranges, period)
