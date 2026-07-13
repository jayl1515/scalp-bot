# scalp-bot

A Python crypto scalping framework with a **phone-installable control panel app**. Run the server on your computer and control the bot from your phone like a native app — no app store required.

> ⚠️ **Risk notice:** This project does not promise profits or guaranteed returns. Crypto trading is risky, backtests can be misleading, and live performance can be worse than historical results.

---

## Get the app on your phone in 5 minutes

### Step 1 — Prerequisites

- Python 3.11 or newer installed on your computer
- Your phone and computer on the **same Wi-Fi network**

### Step 2 — Install

```bash
# Clone the repo (skip if you already have it)
git clone https://github.com/jayl1515/scalp-bot.git
cd scalp-bot

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt
```

### Step 3 — Start the server

Pick a token (any secret string you choose) and start the control panel:

```bash
CONTROL_PANEL_TOKEN=my-secret python -m scalp_bot.control_panel
```

You should see:

```
 * Running on http://0.0.0.0:5000
```

Keep this terminal open. The server must stay running while you use the app.

### Step 4 — Find your computer's IP address

You need this so your phone can reach the server over Wi-Fi.

| OS | Command |
|---|---|
| macOS / Linux | `ip route get 1 \| awk '{print $7}'` |
| Windows | `ipconfig` → look for **IPv4 Address** |

The IP looks like `192.168.1.42`. Write it down.

### Step 5 — Open the app on your phone

1. Make sure your phone is on the same Wi-Fi network as your computer.
2. Open your phone's browser and go to:

   ```
   http://<your-computer-ip>:5000
   ```

   Example: `http://192.168.1.42:5000`

3. The control panel loads. Tap **Set Token** (top-right corner) and enter the token you chose in Step 3 (`my-secret` in the example).

### Step 6 — Install it as an app

**iPhone / iPad (Safari)**

1. Open the URL in **Safari** (not Chrome — Safari is required for iOS install).
2. Tap the **Share** button (box with an arrow pointing up).
3. Scroll down and tap **Add to Home Screen**.
4. Tap **Add**.

The app now appears on your home screen with its own icon and opens in fullscreen, just like a native app.

**Android (Chrome)**

1. Open the URL in **Chrome**.
2. Tap the **three-dot menu** (top-right).
3. Tap **Add to Home screen**.
4. Tap **Add**.

---

## Using the app

### First steps

| What to do | Where |
|---|---|
| Start or stop the bot | **Home** screen → **Start / Stop** buttons |
| Check current mode (paper vs live) | Status bar at the top of the Home screen |
| Run a backtest | **Backtests** tab → fill in date range → **Run** |
| View past runs | **History** tab |
| Edit strategy settings | **Settings** tab |
| Emergency stop | **Kill Switch** button — immediately halts the bot |

### Paper mode vs live mode

The bot **always starts in paper mode** — no real orders are placed.

To switch to live mode:
1. Tap the **Live ⚠** button.
2. Type `LIVE` in the confirmation prompt and confirm.
3. The server validates the confirmation before switching.

To switch back to paper mode, tap **Paper** on the mode bar.

### Kill Switch

Tapping **Kill Switch** immediately stops the bot and **blocks it from restarting** until you manually reset it. Use this if something goes wrong. To re-enable, tap **Reset Kill Switch**.

---

## Configuration

The bot reads its base settings from `config/sample_config.json`. Copy and edit this file to adjust strategy parameters:

```json
{
  "base_capital": 20.0,
  "strategy": {
    "ema_fast_period": 8,
    "ema_slow_period": 21,
    "stop_atr_multiple": 1.2,
    "reward_to_risk": 1.4
  }
}
```

Point the server at your config file:

```bash
CONTROL_PANEL_TOKEN=my-secret \
SCALP_BOT_CONFIG_PATH=config/my_config.json \
python -m scalp_bot.control_panel
```

You can also override individual settings live from the **Settings** tab in the app without restarting the server.

---

## CLI commands (optional, for power users)

All of these can also be done from the app, but the CLI is available if you prefer it.

```bash
# Run a backtest
python -m scalp_bot.cli backtest \
  --config config/sample_config.json \
  --data data/sample_ohlcv.csv \
  --report reports/backtest_report.json

# Run the parameter optimizer
python -m scalp_bot.cli optimize \
  --config config/sample_config.json \
  --data data/sample_ohlcv.csv \
  --report reports/optimization_results.json

# Print a saved backtest summary
python -m scalp_bot.cli summary --report reports/backtest_report.json
```

---

## Run tests

```bash
python -m pytest
```

---

## Security checklist

- [ ] Set `CONTROL_PANEL_TOKEN` to a strong, unique secret — never leave it blank in a real setup.
- [ ] Store the token in a `.env` file and add `.env` to `.gitignore` so it is never committed.
- [ ] Set `FLASK_SECRET_KEY` to a random string in production.
- [ ] Never enable `FLASK_DEBUG=1` outside of local development.
- [ ] All control actions (start, stop, mode change, settings update, kill switch) are logged in the audit trail with timestamp and IP address.

---

## Environment variables reference

| Variable | Default | Description |
|---|---|---|
| `CONTROL_PANEL_TOKEN` | *(none)* | Token required to call all control endpoints. **Always set this.** |
| `CONTROL_PANEL_HOST` | `0.0.0.0` | Server bind address |
| `CONTROL_PANEL_PORT` | `5000` | Server port |
| `CONTROL_PANEL_DB_PATH` | `instance/scalp_bot.db` | SQLite database for persistent state and run history |
| `SCALP_BOT_CONFIG_PATH` | `config/sample_config.json` | Config JSON for backtests and paper sessions |
| `SCALP_BOT_DATA_PATH` | `data/sample_ohlcv.csv` | OHLCV CSV for the in-app backtest runner |
| `FLASK_SECRET_KEY` | `dev-secret-change-me` | Flask session secret — set a random value in production |
| `FLASK_DEBUG` | `0` | Set to `1` for debug mode (never in production) |

---

## What is saved

Everything is stored in a local SQLite database (`instance/scalp_bot.db`):

- Bot mode and kill-switch state across restarts
- Settings overrides you apply from the app
- Every backtest — its own ID, date range, config snapshot, metrics, and trade list
- Every paper session — its own ID, event log, and trade journal
- Full audit log of every control action

Running the same backtest multiple times is safe — each run is stored as a separate record.

---

## Project layout

```
scalp_bot/
  cli.py                        — backtest, optimize, summary commands
  backtester.py / strategy.py   — core bot logic
  control_panel/
    app.py                      — Flask app and all API routes
    services.py                 — backtest and paper session logic
    storage.py                  — SQLite persistence
    state.py                    — thread-safe runtime state
    auth.py                     — token authentication
    audit.py                    — audit log
    validation.py               — settings validation
    templates/index.html        — app UI shell
    static/panel.css            — mobile app styling
    static/panel.js             — app navigation and API calls
    static/sw.js                — service worker (enables install)
    static/icon.svg             — app icon
config/sample_config.json       — sample strategy settings
data/sample_ohlcv.csv           — sample OHLCV data
reports/                        — generated backtest outputs
tests/                          — unit and integration tests
```
