from datetime import datetime

import pytest

from scalp_bot.market_data import cache_summary, fetch_historical_candles


class FakeExchange:
    timeframes = {"1m": "1m"}

    def __init__(self):
        self.calls = []
        self.batches = [
            [[0, 100, 101, 99, 100.5, 10], [60_000, 100.5, 102, 100, 101.5, 12]],
            [[120_000, 101.5, 103, 101, 102.5, 14]],
        ]

    def load_markets(self):
        return {"BTC/USDT": {"spot": True}}

    def parse_timeframe(self, timeframe):
        return 60

    def fetch_ohlcv(self, symbol, *, timeframe, since, limit):
        self.calls.append((symbol, timeframe, since, limit))
        return self.batches.pop(0) if self.batches else []


def test_fetches_paged_candles_and_caches_them(tmp_path):
    exchange = FakeExchange()
    candles = fetch_historical_candles(
        exchange_id="fake",
        symbol="BTC/USDT",
        timeframe="1m",
        start="1970-01-01T00:00:00",
        end="1970-01-01T00:02:00",
        cache_dir=tmp_path,
        exchange=exchange,
    )

    assert [candle.close for candle in candles] == [100.5, 101.5, 102.5]
    assert len(exchange.calls) == 2

    cached_exchange = FakeExchange()
    cached = fetch_historical_candles(
        exchange_id="fake",
        symbol="BTC/USDT",
        timeframe="1m",
        start="1970-01-01T00:00:00",
        end="1970-01-01T00:02:00",
        cache_dir=tmp_path,
        exchange=cached_exchange,
    )

    assert len(cached) == 3
    assert cached_exchange.calls == []


def test_rejects_unknown_symbol(tmp_path):
    exchange = FakeExchange()
    with pytest.raises(ValueError, match="not available"):
        fetch_historical_candles(
            exchange_id="fake",
            symbol="ETH/USDT",
            timeframe="1m",
            start="1970-01-01",
            end="1970-01-02",
            cache_dir=tmp_path,
            exchange=exchange,
        )


def test_cache_summary_reports_missing_cache(tmp_path):
    summary = cache_summary(
        exchange_id="fake",
        symbol="BTC/USDT",
        timeframe="1h",
        cache_dir=tmp_path,
    )

    assert summary["exists"] is False
    assert summary["total_candles"] == 0
    assert summary["start_at"] is None
