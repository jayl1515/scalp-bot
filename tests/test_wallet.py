from scalp_bot.risk import ProfitLedger


def test_profit_sweep_moves_excess_to_profit_wallet():
    ledger = ProfitLedger.from_base_capital(20.0)

    swept = ledger.apply_closed_trade(3.5)

    assert swept == 3.5
    assert ledger.trading_balance == 20.0
    assert ledger.profit_wallet_balance == 3.5
    assert ledger.total_equity == 23.5


def test_loss_does_not_reduce_profit_wallet_balance():
    ledger = ProfitLedger.from_base_capital(20.0)
    ledger.apply_closed_trade(2.0)

    swept = ledger.apply_closed_trade(-1.0)

    assert swept == 0.0
    assert ledger.trading_balance == 19.0
    assert ledger.profit_wallet_balance == 2.0
    assert ledger.total_equity == 21.0
