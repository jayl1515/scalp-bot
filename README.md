# scalp-bot

A small Python framework for testing fixed-capital crypto scalping ideas on historical data.

## What this project does

- Uses **Python** only.
- Keeps the trading base capital fixed at **$20.00**.
- Sizes trades from the fixed base-capital rules instead of compounding from profits.
- Sweeps realized gains above the $20.00 trading bankroll into a separate **profit wallet** ledger.
- Stops trading for the day when configured risk limits are hit.
- Includes backtesting, grid-search optimization, tests, and CLI commands.

## Important risk note

This project does **not** promise profits or guaranteed returns. Crypto trading is risky, backtests can be misleading, and live performance can be worse than historical results.

## Project layout

- `scalp_bot/` - bot logic, strategy, backtester, optimizer, CLI
- `config/sample_config.json` - sample settings
- `data/sample_ohlcv.csv` - sample OHLCV data
- `tests/` - unit and smoke tests
- `reports/` - generated backtest and optimization outputs

## Setup

1. Make sure Python 3.11+ is installed.
2. Create a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## Run tests

```bash
python -m pytest
```

## Run a backtest

```bash
python -m scalp_bot.cli backtest \
  --config config/sample_config.json \
  --data data/sample_ohlcv.csv \
  --report reports/backtest_report.json
```

## Run the optimizer

```bash
python -m scalp_bot.cli optimize \
  --config config/sample_config.json \
  --data data/sample_ohlcv.csv \
  --report reports/optimization_results.json
```

## Print a saved performance summary

```bash
python -m scalp_bot.cli summary --report reports/backtest_report.json
```

## Strategy template summary

The sample strategy is a configurable long-only scalping template that uses:

- trend filter with fast and slow EMAs
- volatility filter with ATR percentage bounds
- volume filter with a rolling volume average
- breakout-style entries
- stop loss, take profit, cooldowns, and time-based exits

You can change the parameters in `config/sample_config.json` and rerun backtests or optimization.

## Backtest limitation to understand

This framework uses OHLCV candles, not tick-by-tick data. If a candle touches both the stop loss and take profit in the same bar, the backtest uses a **conservative stop-first assumption**.
