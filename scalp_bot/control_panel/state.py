"""Bot runtime state shared across the control panel."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class BotState:
    """Thread-safe in-memory bot state."""

    running: bool = False
    mode: str = "paper"  # "paper" or "live"
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    kill_switch_active: bool = False
    last_signal: dict[str, Any] | None = None
    last_trade: dict[str, Any] | None = None
    settings_override: dict[str, Any] = field(default_factory=dict)
    active_paper_run_id: str | None = None

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "mode": self.mode,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "kill_switch_active": self.kill_switch_active,
            "last_signal": self.last_signal,
            "last_trade": self.last_trade,
        }

    def start(self) -> None:
        with self._lock:
            self.running = True
            self.started_at = datetime.now(tz=timezone.utc)
            self.stopped_at = None

    def stop(self) -> None:
        with self._lock:
            self.running = False
            self.stopped_at = datetime.now(tz=timezone.utc)

    def activate_kill_switch(self) -> None:
        with self._lock:
            self.kill_switch_active = True
            self.running = False
            self.stopped_at = datetime.now(tz=timezone.utc)

    def set_mode(self, mode: str) -> None:
        if mode not in ("paper", "live"):
            raise ValueError(f"Invalid mode: {mode!r}. Must be 'paper' or 'live'.")
        with self._lock:
            self.mode = mode


# Module-level singleton used by the Flask app
bot_state = BotState()
