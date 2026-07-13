"""Persistent SQLite storage for the control panel app."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class AppDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = threading.Lock()
        if self.path != ":memory:":
            Path(self.path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS kv_store (
            namespace TEXT NOT NULL,
            key TEXT NOT NULL,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (namespace, key)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            result TEXT NOT NULL,
            detail TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp DESC);

        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            run_type TEXT NOT NULL,
            status TEXT NOT NULL,
            title TEXT NOT NULL,
            dataset_path TEXT,
            start_date TEXT,
            end_date TEXT,
            config_json TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            metrics_json TEXT,
            notes TEXT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_runs_listing
            ON runs(run_type, status, started_at DESC, created_at DESC);

        CREATE TABLE IF NOT EXISTS run_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_run_events_lookup
            ON run_events(run_id, timestamp DESC);

        CREATE TABLE IF NOT EXISTS run_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            sequence_no INTEGER NOT NULL,
            entry_time TEXT,
            exit_time TEXT,
            entry_price REAL,
            exit_price REAL,
            quantity REAL,
            gross_pnl REAL,
            net_pnl REAL,
            exit_reason TEXT,
            bars_held INTEGER,
            stop_price REAL,
            take_profit_price REAL,
            payload_json TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_run_trades_sequence
            ON run_trades(run_id, sequence_no);
        """
        with self._lock, self._connect() as connection:
            connection.executescript(schema)

    @staticmethod
    def _encode(payload: Any) -> str:
        return json.dumps(payload, sort_keys=True)

    @staticmethod
    def _decode(payload: str | None, default: Any) -> Any:
        if payload is None:
            return default
        return json.loads(payload)

    def save_bot_snapshot(self, payload: dict[str, Any]) -> None:
        now = utc_now_iso()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO kv_store(namespace, key, value_json, updated_at)
                VALUES ('app_state', 'bot_snapshot', ?, ?)
                ON CONFLICT(namespace, key)
                DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at
                """,
                (self._encode(payload), now),
            )

    def load_bot_snapshot(self) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT value_json FROM kv_store WHERE namespace = 'app_state' AND key = 'bot_snapshot'"
            ).fetchone()
        return self._decode(row["value_json"], {}) if row else {}

    def record(self, action: str, actor: str, result: str, detail: str | None = None) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO audit_log(timestamp, actor, action, result, detail)
                VALUES (?, ?, ?, ?, ?)
                """,
                (utc_now_iso(), actor, action, result, detail),
            )

    def get_recent(self, n: int = 50) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT timestamp, actor, action, result, detail
                FROM audit_log
                ORDER BY id DESC
                LIMIT ?
                """,
                (n,),
            ).fetchall()
        return [dict(row) for row in rows]

    def clear(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM audit_log")

    def create_run(
        self,
        *,
        run_type: str,
        status: str,
        title: str,
        dataset_path: str | None,
        start_date: str | None,
        end_date: str | None,
        config: dict[str, Any],
        summary: dict[str, Any] | None = None,
        notes: str | None = None,
    ) -> str:
        run_id = uuid.uuid4().hex
        now = utc_now_iso()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs(
                    id, run_type, status, title, dataset_path, start_date, end_date,
                    config_json, summary_json, metrics_json, notes,
                    started_at, completed_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    run_type,
                    status,
                    title,
                    dataset_path,
                    start_date,
                    end_date,
                    self._encode(config),
                    self._encode(summary or {}),
                    None,
                    notes,
                    now,
                    None,
                    now,
                    now,
                ),
            )
        return run_id

    def update_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        summary: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        completed_at: str | None = None,
        notes: str | None = None,
    ) -> None:
        fields: list[str] = ["updated_at = ?"]
        values: list[Any] = [utc_now_iso()]
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if summary is not None:
            fields.append("summary_json = ?")
            values.append(self._encode(summary))
        if metrics is not None:
            fields.append("metrics_json = ?")
            values.append(self._encode(metrics))
        if completed_at is not None:
            fields.append("completed_at = ?")
            values.append(completed_at)
        if notes is not None:
            fields.append("notes = ?")
            values.append(notes)
        values.append(run_id)
        with self._lock, self._connect() as connection:
            connection.execute(
                f"UPDATE runs SET {', '.join(fields)} WHERE id = ?",
                values,
            )

    def add_event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        timestamp = payload.get("timestamp") or utc_now_iso()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO run_events(run_id, timestamp, event_type, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, timestamp, event_type, self._encode(payload)),
            )

    def add_trade(self, run_id: str, payload: dict[str, Any]) -> int:
        with self._lock, self._connect() as connection:
            next_sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence_no), 0) + 1 FROM run_trades WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
            cursor = connection.execute(
                """
                INSERT INTO run_trades(
                    run_id, sequence_no, entry_time, exit_time, entry_price, exit_price,
                    quantity, gross_pnl, net_pnl, exit_reason, bars_held,
                    stop_price, take_profit_price, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    next_sequence,
                    payload.get("entry_time"),
                    payload.get("exit_time"),
                    payload.get("entry_price"),
                    payload.get("exit_price"),
                    payload.get("quantity"),
                    payload.get("gross_pnl"),
                    payload.get("net_pnl"),
                    payload.get("exit_reason"),
                    payload.get("bars_held"),
                    payload.get("stop_price"),
                    payload.get("take_profit_price"),
                    self._encode(payload),
                ),
            )
        return int(cursor.lastrowid)

    def list_runs(
        self,
        *,
        run_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if run_type:
            clauses.append("run_type = ?")
            values.append(run_type)
        if status:
            clauses.append("status = ?")
            values.append(status)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT
                id,
                run_type,
                status,
                title,
                dataset_path,
                start_date,
                end_date,
                summary_json,
                metrics_json,
                notes,
                started_at,
                completed_at,
                created_at,
                updated_at,
                (
                    SELECT COUNT(*)
                    FROM run_trades
                    WHERE run_id = runs.id
                ) AS trade_count,
                (
                    SELECT COUNT(*)
                    FROM run_events
                    WHERE run_id = runs.id
                ) AS event_count
            FROM runs
            {where_clause}
            ORDER BY started_at DESC, created_at DESC
            LIMIT ?
        """
        values.append(limit)
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, values).fetchall()
        return [self._row_to_run_summary(row) for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            run_row = connection.execute(
                """
                SELECT *
                FROM runs
                WHERE id = ?
                """,
                (run_id,),
            ).fetchone()
            if run_row is None:
                return None
            trade_rows = connection.execute(
                """
                SELECT sequence_no, payload_json
                FROM run_trades
                WHERE run_id = ?
                ORDER BY sequence_no ASC
                """,
                (run_id,),
            ).fetchall()
            event_rows = connection.execute(
                """
                SELECT timestamp, event_type, payload_json
                FROM run_events
                WHERE run_id = ?
                ORDER BY id ASC
                """,
                (run_id,),
            ).fetchall()
        payload = dict(run_row)
        payload["config"] = self._decode(payload.pop("config_json"), {})
        payload["summary"] = self._decode(payload.pop("summary_json"), {})
        payload["metrics"] = self._decode(payload.pop("metrics_json"), None)
        payload["trades"] = [
            {
                "sequence_no": row["sequence_no"],
                **self._decode(row["payload_json"], {}),
            }
            for row in trade_rows
        ]
        payload["events"] = [
            {
                "timestamp": row["timestamp"],
                "event_type": row["event_type"],
                "payload": self._decode(row["payload_json"], {}),
            }
            for row in event_rows
        ]
        payload["trade_count"] = len(payload["trades"])
        payload["event_count"] = len(payload["events"])
        return payload

    def _row_to_run_summary(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["summary"] = self._decode(payload.pop("summary_json"), {})
        payload["metrics"] = self._decode(payload.pop("metrics_json"), None)
        return payload
