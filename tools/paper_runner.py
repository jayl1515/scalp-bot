"""tools/paper_runner.py

Simulate a live paper trading runner from OHLCV candle data and log signals/trades
to the control panel API so they appear exactly like real paper sessions.

Usage (Termux):

CONTROL_PANEL_TOKEN=1234 python tools/paper_runner.py --data data/sample_ohlcv.csv --host http://127.0.0.1:5000 --speed 0.5

This script:
- Verifies the control panel is running and in PAPER mode
- Starts a paper session (via POST /api/paper/start) if none is active
- Streams candles at the requested speed and uses the strategy.should_enter / should_exit_on_close
  logic to trigger entries/exits
- Posts signals (POST /api/paper/signal) and trades (POST /api/paper/trade) so they are persisted
  and visible in the UI and DB.

Notes:
- This is intentionally simple and deterministic (no real exchange calls).
- Position sizing is a conservative attempt using config rules; adapt as needed.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime

import requests

from scalp_bot.config import load_config
from scalp_bot.data import load_candles
from scalp_bot.strategy import ScalpingStrategy


def iso(ts):
    if isinstance(ts, datetime):
        return ts.isoformat()
    return str(ts)


def headers(token: str) -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    return h


def start_paper_session(base_url: str, token: str, title: str = "Paper run") -> dict:
    url = f"{base_url.rstrip('/')}/api/paper/start"
    payload = {"title": title}
    r = requests.post(url, headers=headers(token), json=payload, timeout=10)
    r.raise_for_status()
    return r.json()


def post_signal(base_url: str, token: str, payload: dict) -> dict:
    url = f"{base_url.rstrip('/')}/api/paper/signal"
    r = requests.post(url, headers=headers(token), json=payload, timeout=10)
    r.raise_for_status()
    return r.json()


def post_trade(base_url: str, token: str, payload: dict) -> dict:
    url = f"{base_url.rstrip('/')}/api/paper/trade"
    r = requests.post(url, headers=headers(token), json=payload, timeout=10)
    r.raise_for_status()
    return r.json()


def get_status(base_url: str, token: str) -> dict:
    url = f"{base_url.rstrip('/')}/api/status"
    r = requests.get(url, headers=headers(token), timeout=5)
    r.raise_for_status()
    return r.json()


def make_quantity(cfg, entry_price: float, stop_price: float) -> float:
    # conservative position sizing roughly matching backtest logic
    risk_per_trade = cfg.strategy.risk_per_trade_pct * cfg.base_capital
    risk_per_unit = max(abs(entry_price - stop_price), 1e-9)
    qty_by_risk = risk_per_trade / risk_per_unit
    notional_cap = min(cfg.base_capital * cfg.strategy.max_position_pct, cfg.base_capital)
    qty_by_notional = notional_cap / (entry_price if entry_price else 1)
    qty = min(qty_by_risk, qty_by_notional)
    # enforce min trade notional
    if qty * entry_price < cfg.strategy.min_trade_notional:
        return 0.0
    return float(max(qty, 0.0))


def run(args):
    cfg = load_config(args.config) if args.config else load_config("config/sample_config.json")
    candles = load_candles(args.data)
    strategy = ScalpingStrategy(cfg.strategy)
    warmup = strategy.warmup_bars()
    base_url = args.host.rstrip("/")
    token = args.token or ""

    # sanity check control panel
    try:
        status = get_status(base_url, token)
    except Exception as exc:
        print("ERROR: Unable to reach control panel /api/status:", exc)
        return

    if status.get("mode") != "paper":
        print("ERROR: Control panel is not in PAPER mode. Switch to paper mode before running this tool.")
        return

    # start paper session if none active
    if not status.get("active_paper_run_id"):
        print("Starting new paper session via control panel...")
        try:
            session = start_paper_session(base_url, token, title=args.title or "Paper run from runner")
            run_id = session.get("id")
            print("Started run", run_id)
        except Exception as exc:
            print("ERROR: Failed to start paper session:", exc)
            return
    else:
        run_id = status.get("active_paper_run_id")
        print("Using existing paper run", run_id)

    position = None

    for index in range(warmup, len(candles)):
        candle = candles[index]
        now = iso(candle.timestamp)

        # If we have a position, check exit condition
        if position:
            if strategy.should_exit_on_close(index, candles, strategy.prepare(candles)):
                exit_price = candle.close
                quantity = position["quantity"]
                side = position["side"]
                direction = 1 if side != "short" else -1
                gross_pnl = (exit_price - position["entry_price"]) * quantity * direction
                net_pnl = gross_pnl  # fee/slippage omitted here; extend if needed
                trade_payload = {
                    "entry_price": position["entry_price"],
                    "exit_price": exit_price,
                    "quantity": quantity,
                    "side": side,
                    "entry_time": position["entry_time"],
                    "exit_time": now,
                    "gross_pnl": gross_pnl,
                    "net_pnl": net_pnl,
                    "note": "auto-exit",
                }
                try:
                    posted = post_trade(base_url, token, trade_payload)
                    print(f"TRADE EXIT logged: {posted.get('symbol','') or ''} {trade_payload}")
                except Exception as exc:
                    print("ERROR posting trade:", exc)
                position = None

        # If no position, check entry
        if not position and strategy.should_enter(index, candles, strategy.prepare(candles)):
            entry_price = candle.close
            atr = strategy.prepare(candles).atr[index]
            stop_price = entry_price - (cfg.strategy.stop_atr_multiple * atr)
            quantity = make_quantity(cfg, entry_price, stop_price)
            if quantity <= 0:
                print("Calculated quantity too small, skipping entry")
            else:
                side = "long"
                signal_payload = {
                    "symbol": args.symbol or "SYMBOL",
                    "bias": side,
                    "price": entry_price,
                    "note": "auto-signal",
                }
                try:
                    posted = post_signal(base_url, token, signal_payload)
                    print("SIGNAL logged:", posted)
                except Exception as exc:
                    print("ERROR posting signal:", exc)

                position = {
                    "entry_time": now,
                    "entry_price": entry_price,
                    "quantity": quantity,
                    "side": side,
                    "stop_price": stop_price,
                }
                print("ENTER position:", position)

        time.sleep(args.speed)

    print("Reached end of candle stream")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True, help="Path to OHLCV CSV (same format as data/sample_ohlcv.csv)")
    p.add_argument("--host", default="http://127.0.0.1:5000", help="Control panel base URL")
    p.add_argument("--token", default="", help="CONTROL_PANEL_TOKEN value for Authorization Bearer header")
    p.add_argument("--speed", type=float, default=0.5, help="Seconds between candles (stream speed)")
    p.add_argument("--config", default=None, help="Path to config JSON (optional)")
    p.add_argument("--title", default=None, help="Paper session title")
    p.add_argument("--symbol", default="BTCUSDT", help="Symbol label used for signals/trades")
    args = p.parse_args()
    run(args)


if __name__ == "__main__":
    main()
