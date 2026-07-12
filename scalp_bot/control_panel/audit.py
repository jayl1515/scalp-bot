"""Audit logging for control panel actions."""
from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any


_lock = threading.Lock()
_audit_log: deque[dict[str, Any]] = deque(maxlen=500)


def record(action: str, actor: str, result: str, detail: str | None = None) -> None:
    """Append an audit entry (thread-safe)."""
    entry: dict[str, Any] = {
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "result": result,
    }
    if detail:
        entry["detail"] = detail
    with _lock:
        _audit_log.appendleft(entry)


def get_recent(n: int = 50) -> list[dict[str, Any]]:
    """Return the *n* most recent audit entries (newest first)."""
    with _lock:
        return list(_audit_log)[:n]


def clear() -> None:
    """Clear all audit log entries (useful in tests)."""
    with _lock:
        _audit_log.clear()


def to_json(n: int = 50) -> str:
    return json.dumps(get_recent(n))
