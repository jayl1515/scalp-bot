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

## Web control panel

A lightweight, mobile-friendly control panel lets you monitor and manage the bot from your phone or browser.

### Required environment variables

| Variable | Required | Description |
|---|---|---|
| `CONTROL_PANEL_TOKEN` | Recommended | ****** protecting all control endpoints. Omit only for local dev. |
| `CONTROL_PANEL_HOST` | Optional | Server bind address (default `0.0.0.0`) |
| `CONTROL_PANEL_PORT` | Optional | Server port (default `5000`) |
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

Open http://localhost:5000 in your browser.

### Open from your phone (same Wi-Fi network)

1. Find your computer's local IP address:
   - **macOS / Linux**: `ip route get 1 | awk '{print $7}'` or `ifconfig | grep "inet "`
   - **Windows**: `ipconfig` → look for "IPv4 Address"
2. Make sure the control panel is running with `CONTROL_PANEL_HOST=0.0.0.0` (the default).
3. On your phone, open: `http://<your-computer-ip>:5000`
   - Example: `http://192.168.1.42:5000`
4. Tap **Set Token** in the top-right corner and enter your `CONTROL_PANEL_TOKEN`.

### Add to Home Screen

**iOS (Safari)**
1. Open the URL in Safari.
2. Tap the Share icon → **Add to Home Screen**.
3. Tap **Add**. The panel opens like a native app.

**Android (Chrome)**
1. Open the URL in Chrome.
2. Tap the three-dot menu → **Add to Home screen**.
3. Tap **Add**.

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
  app.py          — Flask app factory and all API routes
  state.py        — Thread-safe in-memory bot state
  auth.py         — Bearer-token auth decorator
  audit.py        — Audit/action log (in-memory, newest-first)
  validation.py   — Server-side settings validation
  templates/
    index.html    — Mobile-first single-page UI
  static/
    panel.css     — Responsive dark-theme stylesheet
    panel.js      — Vanilla JS: status polling, actions, settings form
tests/
  test_control_panel.py — 45 tests covering all endpoints, auth, validation
```
