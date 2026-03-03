from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class SchedulerRepository:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS constraints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS operations (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    effective_timestamp TEXT NOT NULL,
                    dispatch_mode TEXT NOT NULL,
                    dispatched INTEGER NOT NULL DEFAULT 0,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    dispatched_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON decisions(timestamp);
                CREATE INDEX IF NOT EXISTS idx_commands_dispatched ON commands(dispatched, id);
                """
            )
            self._conn.commit()

    def save_cycle(
        self,
        decision: dict[str, Any],
        summary: dict[str, Any],
        constraints: dict[str, Any],
        operations: dict[str, Any],
    ) -> None:
        created_at = _now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO decisions(timestamp, payload, created_at) VALUES(?,?,?)",
                (decision["timestamp"], json.dumps(decision), created_at),
            )
            self._conn.execute(
                "INSERT INTO summaries(payload, created_at) VALUES(?,?)",
                (json.dumps(summary), created_at),
            )
            self._conn.execute(
                "INSERT INTO constraints(payload, created_at) VALUES(?,?)",
                (json.dumps(constraints), created_at),
            )
            self._conn.execute(
                """
                INSERT INTO operations(id, payload, updated_at) VALUES(1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at
                """,
                (json.dumps(operations), created_at),
            )
            self._conn.commit()

    def enqueue_command(self, payload: dict[str, Any], dispatch_mode: str, dispatched: bool) -> int:
        created_at = _now_iso()
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO commands(effective_timestamp, dispatch_mode, dispatched, payload, created_at, dispatched_at)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    payload["effective_timestamp"],
                    dispatch_mode,
                    1 if dispatched else 0,
                    json.dumps(payload),
                    created_at,
                    created_at if dispatched else None,
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def mark_command_dispatched(self, command_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE commands SET dispatched=1, dispatched_at=? WHERE id=?",
                (_now_iso(), command_id),
            )
            self._conn.commit()

    def get_latest(self, table: str) -> dict[str, Any] | None:
        allowed = {"decisions", "summaries", "constraints"}
        if table not in allowed:
            raise ValueError("Invalid table")
        with self._lock:
            row = self._conn.execute(
                f"SELECT payload FROM {table} ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def get_operations(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM operations WHERE id=1").fetchone()
        return json.loads(row["payload"]) if row else None

    def list_recent_decisions(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM decisions ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    def list_decisions_since(self, since_timestamp: str, limit: int = 2000) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT payload
                FROM decisions
                WHERE timestamp >= ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (since_timestamp, limit),
            ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    def count_pending_commands(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM commands WHERE dispatched=0").fetchone()
        return int(row["c"]) if row else 0

    def fetch_pending_commands(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, dispatch_mode, dispatched, created_at, dispatched_at, payload FROM commands WHERE dispatched=0 ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "dispatch_mode": r["dispatch_mode"],
                    "dispatched": bool(r["dispatched"]),
                    "created_at": r["created_at"],
                    "dispatched_at": r["dispatched_at"],
                    "payload": json.loads(r["payload"]),
                }
            )
        return out

    def list_commands(self, limit: int = 50, only_pending: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT id, dispatch_mode, dispatched, created_at, dispatched_at, payload FROM commands"
        params: tuple[Any, ...]
        if only_pending:
            sql += " WHERE dispatched=0"
            params = ()
        else:
            params = ()
        sql += " ORDER BY id DESC LIMIT ?"
        params += (limit,)

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()

        out = []
        for r in rows:
            out.append(
                {
                    "id": r["id"],
                    "dispatch_mode": r["dispatch_mode"],
                    "dispatched": bool(r["dispatched"]),
                    "created_at": r["created_at"],
                    "dispatched_at": r["dispatched_at"],
                    "payload": json.loads(r["payload"]),
                }
            )
        return out
