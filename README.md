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

---

## Installable phone app control panel

The control panel is now an **installable app-style interface** for phones and tablets. It keeps the existing bot controls, adds polished app navigation, and stores backtests, paper sessions, settings, and audit history in a persistent SQLite database.

### Required environment variables

| Variable | Required | Description |
|---|---|---|
| `CONTROL_PANEL_TOKEN` | Recommended | ****** protecting all control endpoints. Omit only for local dev. |
| `CONTROL_PANEL_HOST` | Optional | Server bind address (default `0.0.0.0`) |
| `CONTROL_PANEL_PORT` | Optional | Server port (default `5000`) |
| `CONTROL_PANEL_DB_PATH` | Optional | SQLite database path for persistent app state and run history (default `instance/scalp_bot.db`) |
| `SCALP_BOT_CONFIG_PATH` | Optional | Config JSON used as the base snapshot for backtests and paper sessions |
| `SCALP_BOT_DATA_PATH` | Optional | OHLCV CSV used by the in-app backtest runner |
| `FLASK_SECRET_KEY` | Optional | Secret key for Flask sessions (set to a random string in production) |
| `FLASK_DEBUG` | Optional | Set to `1` to enable Flask debug mode (never in production) |

### Run locally

```bash
# Install dependencies (includes Flask)
pip install -r requirements.txt

# Start the control panel
CONTROL_PANEL_TOKEN=my-secret python -m scalp_bot.control_panel
# → Listening on http://0.0.0.0:5000
```

Open http://localhost:5000 in your browser, then install it to your phone home screen for an app-like experience.

### Open from your phone (same Wi-Fi network)

1. Find your computer's local IP address:
   - **macOS / Linux**: `ip route get 1 | awk '{print $7}'` or `ifconfig | grep "inet "`
   - **Windows**: `ipconfig` → look for "IPv4 Address"
2. Make sure the control panel is running with `CONTROL_PANEL_HOST=0.0.0.0` (the default).
3. On your phone, open: `http://<your-computer-ip>:5000`
   - Example: `http://192.168.1.42:5000`
4. Tap **Set Token** in the top-right corner and enter your `CONTROL_PANEL_TOKEN`.

### Install on your phone

**iOS (Safari)**
1. Open the URL in Safari.
2. Tap the Share icon → **Add to Home Screen**.
3. Tap **Add**. The control panel opens in standalone app mode.

**Android (Chrome)**
1. Open the URL in Chrome.
2. Tap the three-dot menu → **Add to Home screen**.
3. Tap **Add**.

### What is persisted

- Bot mode, kill-switch state, last logged paper signal, and last logged paper trade
- Custom settings overrides saved from the app
- Every backtest run with its own unique ID, date range, config snapshot, metrics, trades, and event trail
- Every paper session with its own unique ID, event log, and trade journal
- Audit history for control actions

Running the same backtest range multiple times is safe because each run is saved as a separate database record.

### App API highlights

- `POST /api/backtests` — run a backtest for a chosen date range and save it
- `GET /api/runs` — list backtests and paper sessions
- `GET /api/runs/<run_id>` — inspect a specific run, including trades and events
- `GET /api/runs/compare?ids=<id1>,<id2>` — compare saved runs
- `POST /api/paper/start`, `/api/paper/signal`, `/api/paper/trade`, `/api/paper/stop` — manage persistent paper sessions
- `GET /api/app` — load app metadata, dataset range, and recent runs

### Safety notes for live mode

- The server defaults to **paper mode**. No real orders are placed unless you explicitly switch to live.
- Switching to **live mode** requires:
  1. Tapping the **Live ⚠** button.
  2. Typing `LIVE` in the confirmation prompt.
  3. The server validates the `{"confirm": "LIVE"}` body server-side before accepting the switch.
- The **Kill Switch** button immediately stops the bot and blocks restarts until manually reset.
- All control actions (start, stop, mode change, settings update, kill switch) are recorded in the audit log with timestamp, IP address, and result.
- Keep `CONTROL_PANEL_TOKEN` out of source code — use environment variables or a `.env` file (add `.env` to `.gitignore`).

### Control panel project layout

```
scalp_bot/control_panel/
  app.py          — Flask app factory and API routes for the installable app
  services.py     — service layer for backtests, paper runs, and run history
  storage.py      — SQLite persistence for app state, runs, trades, and events
  state.py        — thread-safe runtime bot state
  auth.py         — Bearer-token auth decorator
  audit.py        — audit log abstraction backed by SQLite
  validation.py   — server-side settings validation
  templates/
    index.html    — multi-screen app shell
  static/
    panel.css     — polished mobile app styling
    panel.js      — app navigation, history views, and API actions
    sw.js         — service worker for install/caching
    icon.svg      — app icon
tests/
  test_control_panel.py — app, persistence, history, and control API coverage
```
