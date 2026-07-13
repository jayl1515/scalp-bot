"""Service layer for the installable control panel app."""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..backtest import Backtester
from ..config import build_config, load_config_data
from ..data import candle_time_range, filter_candles, load_candles
from .state import BotState
from .storage import AppDatabase, utc_now_iso


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _serialize_state(state: BotState) -> dict[str, Any]:
    return {
        "running": state.running,
        "mode": state.mode,
        "started_at": state.started_at.isoformat() if state.started_at else None,
        "stopped_at": state.stopped_at.isoformat() if state.stopped_at else None,
        "kill_switch_active": state.kill_switch_active,
        "last_signal": state.last_signal,
        "last_trade": state.last_trade,
        "settings_override": state.settings_override,
        "active_paper_run_id": state.active_paper_run_id,
    }


def _load_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _hydrate_state(state: BotState, payload: dict[str, Any]) -> None:
    if not payload:
        return
    state.running = bool(payload.get("running", state.running))
    state.mode = payload.get("mode", state.mode)
    state.started_at = _load_datetime(payload.get("started_at"))
    state.stopped_at = _load_datetime(payload.get("stopped_at"))
    state.kill_switch_active = bool(payload.get("kill_switch_active", state.kill_switch_active))
    state.last_signal = payload.get("last_signal")
    state.last_trade = payload.get("last_trade")
    state.settings_override = payload.get("settings_override", {})
    state.active_paper_run_id = payload.get("active_paper_run_id")


class ControlPanelService:
    def __init__(
        self,
        *,
        state: BotState,
        database: AppDatabase,
        config_path: str | Path,
        data_path: str | Path,
    ) -> None:
        self.state = state
        self.database = database
        self.config_path = Path(config_path)
        self.data_path = Path(data_path)
        self._candles_cache = None
        self._dataset_cache = None
        _hydrate_state(self.state, self.database.load_bot_snapshot())

    def persist_state(self) -> None:
        self.database.save_bot_snapshot(_serialize_state(self.state))

    def _load_base_config(self) -> dict[str, Any]:
        return load_config_data(self.config_path)

    def effective_config_payload(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = _deep_merge(self._load_base_config(), self.state.settings_override)
        if overrides:
            payload = _deep_merge(payload, overrides)
        return payload

    def _load_dataset(self):
        if self._candles_cache is None:
            self._candles_cache = load_candles(self.data_path)
        return self._candles_cache

    def dataset_summary(self) -> dict[str, Any]:
        if self._dataset_cache is None:
            candles = self._load_dataset()
            start_at, end_at = candle_time_range(candles)
            self._dataset_cache = {
                "path": str(self.data_path.resolve()),
                "total_candles": len(candles),
                "start_at": start_at,
                "end_at": end_at,
            }
        return self._dataset_cache

    def app_metadata(self) -> dict[str, Any]:
        runs = self.database.list_runs(limit=8)
        return {
            "state": self.state.to_dict() | {"active_paper_run_id": self.state.active_paper_run_id},
            "dataset": self.dataset_summary(),
            "recent_runs": runs,
            "current_settings": self.state.settings_override,
            "available_sections": [
                "dashboard",
                "backtests",
                "paper",
                "history",
                "settings",
            ],
        }

    def run_backtest(self, payload: dict[str, Any]) -> dict[str, Any]:
        overrides = payload.get("config_overrides") or {}
        candles = filter_candles(
            self._load_dataset(),
            start=payload.get("start_date"),
            end=payload.get("end_date"),
        )
        if not candles:
            raise ValueError("No candles matched the selected date range.")
        merged_config = self.effective_config_payload(overrides)
        title = payload.get("title") or f"Backtest {payload.get('start_date') or 'full'} → {payload.get('end_date') or 'latest'}"
        run_id = self.database.create_run(
            run_type="backtest",
            status="running",
            title=title,
            dataset_path=str(self.data_path.resolve()),
            start_date=payload.get("start_date"),
            end_date=payload.get("end_date"),
            config=merged_config,
            summary={
                "requested_at": utc_now_iso(),
                "total_candles": len(candles),
                "dataset_path": str(self.data_path.resolve()),
            },
            notes=payload.get("notes"),
        )
        self.database.add_event(
            run_id,
            "requested",
            {
                "timestamp": utc_now_iso(),
                "start_date": payload.get("start_date"),
                "end_date": payload.get("end_date"),
                "config_overrides": overrides,
            },
        )
        try:
            result = Backtester(build_config(merged_config)).run(candles)
        except Exception as exc:
            completed_at = utc_now_iso()
            self.database.add_event(run_id, "failed", {"timestamp": completed_at, "error": str(exc)})
            self.database.update_run(
                run_id,
                status="failed",
                summary={"error": str(exc), "total_candles": len(candles)},
                completed_at=completed_at,
            )
            raise

        for trade in result.trades:
            self.database.add_trade(run_id, trade.to_dict())
        for reason in result.daily_stop_reasons:
            self.database.add_event(run_id, "daily_stop", {"timestamp": utc_now_iso(), "reason": reason})

        completed_at = utc_now_iso()
        summary = {
            "completed_at": completed_at,
            "total_candles": len(candles),
            "total_trades": result.metrics.total_trades,
            "net_pnl": result.metrics.net_pnl,
            "start_at": candles[0].timestamp.isoformat(),
            "end_at": candles[-1].timestamp.isoformat(),
        }
        self.database.add_event(run_id, "completed", {"timestamp": completed_at, **summary})
        self.database.update_run(
            run_id,
            status="completed",
            summary=summary,
            metrics=result.metrics.to_dict(),
            completed_at=completed_at,
        )
        return self.database.get_run(run_id) or {}

    def start_paper_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.state.active_paper_run_id:
            raise ValueError("A paper session is already active.")
        merged_config = self.effective_config_payload(payload.get("config_overrides") or {})
        title = payload.get("title") or f"Paper session {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        run_id = self.database.create_run(
            run_type="paper",
            status="running",
            title=title,
            dataset_path=str(self.data_path.resolve()),
            start_date=None,
            end_date=None,
            config=merged_config,
            summary={"started_at": utc_now_iso()},
            notes=payload.get("notes"),
        )
        event_payload = {
            "timestamp": utc_now_iso(),
            "notes": payload.get("notes"),
            "mode": self.state.mode,
        }
        self.database.add_event(run_id, "session_started", event_payload)
        self.state.active_paper_run_id = run_id
        self.persist_state()
        return self.database.get_run(run_id) or {}

    def get_active_paper_session(self) -> dict[str, Any] | None:
        if not self.state.active_paper_run_id:
            return None
        return self.database.get_run(self.state.active_paper_run_id)

    def stop_paper_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = self.state.active_paper_run_id
        if not run_id:
            raise ValueError("No active paper session to stop.")
        stopped_at = utc_now_iso()
        self.database.add_event(
            run_id,
            "session_stopped",
            {
                "timestamp": stopped_at,
                "notes": payload.get("notes"),
                "last_signal": self.state.last_signal,
                "last_trade": self.state.last_trade,
            },
        )
        existing = self.database.get_run(run_id) or {}
        summary = existing.get("summary", {}) | {
            "stopped_at": stopped_at,
            "event_count": existing.get("event_count", 0) + 1,
            "trade_count": existing.get("trade_count", 0),
        }
        self.database.update_run(
            run_id,
            status="stopped",
            summary=summary,
            completed_at=stopped_at,
            notes=payload.get("notes") or existing.get("notes"),
        )
        self.state.active_paper_run_id = None
        self.persist_state()
        return self.database.get_run(run_id) or {}

    def log_paper_signal(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = self.state.active_paper_run_id
        if not run_id:
            raise ValueError("Start a paper session before logging signals.")
        signal = {
            "timestamp": utc_now_iso(),
            "symbol": payload.get("symbol"),
            "bias": payload.get("bias"),
            "price": payload.get("price"),
            "note": payload.get("note"),
        }
        self.database.add_event(run_id, "signal", signal)
        self.state.last_signal = signal
        self.persist_state()
        return signal

    def log_paper_trade(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = self.state.active_paper_run_id
        if not run_id:
            raise ValueError("Start a paper session before logging trades.")
        entry_price = payload.get("entry_price")
        exit_price = payload.get("exit_price")
        quantity = payload.get("quantity")
        side = payload.get("side", "long")
        gross_pnl = payload.get("gross_pnl")
        if gross_pnl is None and None not in (entry_price, exit_price, quantity):
            direction = 1 if side != "short" else -1
            gross_pnl = (float(exit_price) - float(entry_price)) * float(quantity) * direction
        net_pnl = payload.get("net_pnl", gross_pnl)
        trade = {
            "timestamp": utc_now_iso(),
            "symbol": payload.get("symbol"),
            "side": side,
            "entry_time": payload.get("entry_time"),
            "exit_time": payload.get("exit_time"),
            "entry_price": entry_price,
            "exit_price": exit_price,
            "quantity": quantity,
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
            "exit_reason": payload.get("exit_reason") or payload.get("note"),
            "note": payload.get("note"),
        }
        self.database.add_trade(run_id, trade)
        self.database.add_event(run_id, "trade", trade)
        self.state.last_trade = trade
        self.persist_state()
        return trade

    def list_runs(self, *, run_type: str | None, status: str | None, limit: int) -> list[dict[str, Any]]:
        return self.database.list_runs(run_type=run_type, status=status, limit=limit)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self.database.get_run(run_id)

    def compare_runs(self, run_ids: list[str]) -> dict[str, Any]:
        runs = [self.database.get_run(run_id) for run_id in run_ids]
        resolved = [run for run in runs if run is not None]
        if len(resolved) < 2:
            raise ValueError("Choose at least two valid runs to compare.")
        metric_keys = [
            "net_pnl",
            "win_rate",
            "profit_factor",
            "max_drawdown",
            "total_trades",
            "risk_adjusted_score",
        ]
        comparisons: dict[str, list[dict[str, Any]]] = {}
        for key in metric_keys:
            comparisons[key] = []
            baseline = resolved[0].get("metrics", {}) or {}
            baseline_value = baseline.get(key)
            for run in resolved:
                value = (run.get("metrics") or {}).get(key)
                delta = None
                if isinstance(value, (int, float)) and isinstance(baseline_value, (int, float)):
                    delta = value - baseline_value
                comparisons[key].append(
                    {
                        "run_id": run["id"],
                        "title": run["title"],
                        "value": value,
                        "delta_vs_first": delta,
                    }
                )
        return {
            "runs": [
                {
                    "id": run["id"],
                    "title": run["title"],
                    "run_type": run["run_type"],
                    "status": run["status"],
                    "summary": run.get("summary", {}),
                }
                for run in resolved
            ],
            "metrics": comparisons,
        }
