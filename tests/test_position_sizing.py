from scalp_bot.backtest import Backtester
from scalp_bot.config import BotConfig


def test_position_size_uses_fixed_base_capital_not_profit_wallet_growth():
    config = BotConfig(base_capital=20.0)
    backtester = Backtester(config)

    quantity_with_small_balance = backtester.calculate_position_size(100.0, 98.0, trading_balance=20.0)
    quantity_with_large_balance = backtester.calculate_position_size(100.0, 98.0, trading_balance=100.0)

    assert quantity_with_small_balance == quantity_with_large_balance


def test_position_size_respects_available_trading_balance_cap():
    config = BotConfig(base_capital=20.0)
    backtester = Backtester(config)

    quantity = backtester.calculate_position_size(10.0, 9.0, trading_balance=7.0)

    assert quantity == 0.7
