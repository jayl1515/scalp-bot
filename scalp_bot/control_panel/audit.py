"""Audit logging for control panel actions."""
from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from typing import Any, Protocol


class AuditBackend(Protocol):
    def record(self, action: str, actor: str, result: str, detail: str | None = None) -> None: ...
    def get_recent(self, n: int = 50) -> list[dict[str, Any]]: ...
    def clear(self) -> None: ...


class MemoryAuditBackend:
    def __init__(self) -> None:
        self._audit_log: deque[dict[str, Any]] = deque(maxlen=500)

    def record(self, action: str, actor: str, result: str, detail: str | None = None) -> None:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "actor": actor,
            "action": action,
            "result": result,
        }
        if detail:
            entry["detail"] = detail
        self._audit_log.appendleft(entry)

    def get_recent(self, n: int = 50) -> list[dict[str, Any]]:
        return list(self._audit_log)[:n]

    def clear(self) -> None:
        self._audit_log.clear()


_backend: AuditBackend = MemoryAuditBackend()


def set_backend(backend: AuditBackend) -> None:
    global _backend
    _backend = backend


def record(action: str, actor: str, result: str, detail: str | None = None) -> None:
    _backend.record(action, actor, result, detail)


def get_recent(n: int = 50) -> list[dict[str, Any]]:
    return _backend.get_recent(n)


def clear() -> None:
    _backend.clear()


def to_json(n: int = 50) -> str:
    return json.dumps(get_recent(n))
