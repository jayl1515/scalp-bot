from pathlib import Path

from scalp_bot.backtest import Backtester
from scalp_bot.config import load_config
from scalp_bot.data import load_candles


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_backtest_runs_on_sample_data():
    config = load_config(REPO_ROOT / "config" / "sample_config.json")
    candles = load_candles(REPO_ROOT / "data" / "sample_ohlcv.csv")

    result = Backtester(config).run(candles)

    assert result.metrics.total_trades > 0
    assert result.metrics.total_equity > 0
    assert len(result.trades) == result.metrics.total_trades
