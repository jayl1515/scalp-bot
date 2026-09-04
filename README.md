# scalp-bot

`scalp-bot` is a Python framework and installable web control panel for researching fixed-capital crypto scalping strategies. It currently supports offline CSV backtests, exchange-backed historical OHLCV downloads, local caching, paper-session logging, saved run history, and strategy optimization.

This project is being built in stages. The current exchange-data milestone supports **spot historical data**. Futures execution, exchange API-key management, and automatic live orders are not implemented yet.

## Risk warning

This software does not promise profits or guaranteed returns. Crypto trading is risky, backtests can be misleading, and live results can be worse than historical results. Keep the app in paper mode until the strategy, data, and risk controls have been thoroughly validated.

## Current capabilities

- Fixed base-capital position sizing
- Separate profit-wallet ledger for realized gains above the trading bankroll
- Daily loss, consecutive-loss, cooldown, and kill-switch controls
- Long-only configurable scalping strategy
- CSV-based offline backtesting
- Grid-search optimization from the command line
- Exchange-backed historical OHLCV downloads through `ccxt`
- Paginated downloads and local CSV caching
- Binance and Kraken provider options in the control panel
- Spot market selection with common candle intervals
- Custom backtest dates and quick date presets, including a six-year window
- Persistent SQLite history for backtests, paper sessions, trades, events, and audit entries
- Installable mobile-friendly control panel

## Requirements

- Python 3.11 or newer
- Network access is needed for exchange-backed data
- No exchange API key is needed for public historical OHLCV downloads

## Installation

From the repository root:

```bash
cd /workspaces/scalp-bot
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

## Start the web UI

### Local development without authentication

This is the simplest way to view the UI and use the bundled sample data:

```bash
cd /workspaces/scalp-bot
SCALP_BOT_DATA_PATH=data/sample_ohlcv.csv python -m scalp_bot.control_panel
```

Open <http://localhost:5000> in a browser.

The server binds to `0.0.0.0` on port `5000` by default. In a VS Code dev container, open port `5000` from the Ports panel if `localhost` is not available directly.

### One-command startup after installation

Install the project into the active virtual environment once:

```bash
python -m pip install -e .
```

Then start the UI with:

```bash
scalp-bot-panel
```

This starts the same local web UI at <http://localhost:5000>. The browser remains the interface, while the command runs the local server in the terminal.

### Local development with a control token

Use a token when accessing the UI from another device or network:

```bash
cd /workspaces/scalp-bot
CONTROL_PANEL_TOKEN=change-this-token \
SCALP_BOT_DATA_PATH=data/sample_ohlcv.csv \
python -m scalp_bot.control_panel
```

In the UI, choose **Token** and enter the same value. The token is stored in the browser's local storage for that browser only.

Do not commit real tokens, exchange credentials, or `.env` files.

### Server options

```bash
CONTROL_PANEL_HOST=0.0.0.0 \
CONTROL_PANEL_PORT=5000 \
CONTROL_PANEL_TOKEN=change-this-token \
python -m scalp_bot.control_panel
```

Available environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `CONTROL_PANEL_HOST` | `0.0.0.0` | Server bind address |
| `CONTROL_PANEL_PORT` | `5000` | Server port |
| `CONTROL_PANEL_TOKEN` | unset | Bearer token for protected control endpoints |
| `CONTROL_PANEL_DB_PATH` | `instance/scalp_bot.db` | SQLite database location |
| `SCALP_BOT_CONFIG_PATH` | `config/sample_config.json` | Base strategy configuration |
| `SCALP_BOT_DATA_PATH` | `data/btcusdt_1h.csv`, then bundled sample fallback | Offline CSV dataset |
| `FLASK_SECRET_KEY` | development value | Flask secret; set a random value outside local development |
| `FLASK_DEBUG` | `0` | Flask debug mode; keep disabled outside development |

## Using the control panel

1. Start the server using one of the commands above.
2. Open `http://localhost:5000`.
3. Leave the app in **Paper** mode while testing.
4. Open **Backtests**.
5. Choose an exchange, market type, symbol, and timeframe.
6. Choose dates manually or use a date preset.
7. Run the backtest and inspect the saved results in **History**.
8. Change one setting at a time so the effect is understandable.

### Offline sample mode

Use:

- Market: `sample`
- Timeframe: `csv`

This mode does not need network access and uses `data/sample_ohlcv.csv`.

### Exchange-backed spot mode

Use an exchange symbol such as:

- Binance: `BTC/USDT`, `ETH/USDT`, or `SOL/USDT`
- Kraken: `BTC/USD` or `ETH/USD`

Use a timeframe such as `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, or `1w`, subject to the selected exchange's availability. The first request downloads the requested range and caches it under `data/market_cache/`. Later requests can reuse the cache.

Six years of one-minute candles can be a very large download. Start with a recent week or month, confirm the workflow, and then increase the range. A coin cannot have candles from before it was listed.

Some exchanges may restrict access based on the server's location. If Binance returns an HTTP 451 restriction, try Kraken or another supported provider rather than treating it as a strategy or application failure.

## Command-line workflows

### Build a desktop executable

The repository includes `ScalpBot.spec` for PyInstaller. Build it on the operating system where you intend to use it. A Windows build must be created on Windows and produces `dist\\ScalpBot.exe`; a Linux build produces `dist/ScalpBot`.

Install PyInstaller in the virtual environment:

```bash
python -m pip install pyinstaller
```

Build the executable:

```bash
pyinstaller --clean --noconfirm ScalpBot.spec
```

Start the built program:

```bash
dist/ScalpBot
```

On Windows, double-click `dist\\ScalpBot.exe` or run it from PowerShell. The program starts the local web server; open <http://localhost:5000> in your browser. Keep the terminal window open while using the app.

The executable includes the UI assets and bundled sample data. Exchange-backed downloads still require network access.

Run tests:

```bash
python -m pytest -q
```

Run an offline backtest:

```bash
python -m scalp_bot.cli backtest \
  --config config/sample_config.json \
  --data data/sample_ohlcv.csv \
  --report reports/backtest_report.json
```

Run optimization:

```bash
python -m scalp_bot.cli optimize \
  --config config/sample_config.json \
  --data data/sample_ohlcv.csv \
  --report reports/optimization_results.json
```

Print a saved report summary:

```bash
python -m scalp_bot.cli summary \
  --report reports/backtest_report.json
```

## Strategy and backtest notes

The current strategy is a configurable long-only template using:

- Fast and slow EMA trend filters
- ATR volatility bounds
- Rolling volume confirmation
- Breakout-style entries
- Stop loss and take profit
- Cooldowns and time-based exits

Settings can be changed in `config/sample_config.json` or through the control panel. The optimizer currently performs grid search over configured strategy values.

The engine uses OHLCV candles rather than tick-by-tick data. If one candle touches both the stop loss and take profit, the backtest uses a conservative stop-first assumption.

## Safety and live-trading status

- The server starts in paper mode.
- The current live-mode button is a guarded state transition, not a complete exchange execution system.
- Real exchange order placement is not implemented.
- Futures are not implemented. Futures require separate treatment for leverage, margin, funding, liquidation, contract size, and mark price.
- Never put exchange API keys in source code or browser storage.
- Keep the kill switch available and test paper behavior before considering any live integration.

## Project layout

```text
scalp_bot/
  backtest.py                 Backtest engine
  cli.py                      Command-line backtest and optimization commands
  config.py                   Configuration loading and defaults
  data.py                     CSV loading and date filtering
  market_data.py              Exchange OHLCV fetching and local caching
  models.py                   Candle, trade, wallet, and result models
  optimization.py             Grid-search optimization
  risk.py                     Fixed-capital and profit-wallet logic
  strategy.py                 Signal and strategy rules
  control_panel/
    app.py                    Flask application factory and API routes
    services.py               Backtest, paper-session, and metadata service layer
    storage.py                SQLite persistence
    state.py                  Runtime bot state
    auth.py                   Optional bearer-token authentication
    audit.py                  Audit-log abstraction
    validation.py             Server-side settings validation
    templates/index.html      Web app shell
    static/panel.js           UI behavior and API calls
    static/panel.css          UI styling
tests/
  test_backtest_smoke.py      Backtest smoke coverage
  test_control_panel.py       Control panel and persistence coverage
  test_market_data.py         Exchange adapter pagination and cache coverage
  test_position_sizing.py     Position-sizing coverage
  test_wallet.py              Profit-wallet coverage
data/
  sample_ohlcv.csv            Bundled offline dataset
  market_cache/               Downloaded exchange data, created as needed
```

## Roadmap

The next planned stages are:

1. Improve data status and cache controls in the UI.
2. Add more exchange adapters and provider-specific validation.
3. Add richer charts, drawdown analysis, export, and run comparison.
4. Add robust walk-forward optimization and regime analysis.
5. Add paper trading from live market streams.
6. Add carefully isolated live spot execution.
7. Add futures only after leverage, funding, margin, and liquidation behavior are modeled and tested.
