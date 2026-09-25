"""SQLite task store; each operation owns its connection."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path


def now() -> str:
    return datetime.now(UTC).isoformat()


class TaskStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._connection() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    language TEXT NOT NULL,
                    focus TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress INTEGER NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

    def _connection(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        result = dict(row)
        raw_result = result.pop("result_json")
        result["result"] = json.loads(raw_result) if raw_result else None
        return result

    def create(self, url: str, platform: str, language: str, focus: str) -> dict:
        task_id = uuid.uuid4().hex
        stamp = now()
        with self._connection() as db:
            db.execute(
                "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (task_id, url, platform, language, focus, "queued", "等待处理", 0, None, None,
                 stamp, stamp),
            )
        return self.get(task_id)

    def get(self, task_id: str) -> dict | None:
        with self._connection() as db:
            row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._decode(row)

    def list(self, limit: int = 20) -> list[dict]:
        with self._connection() as db:
            rows = db.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._decode(row) for row in rows]

    def update(self, task_id: str, *, status: str, stage: str, progress: int,
               result: dict | None = None, error: str | None = None) -> None:
        with self._connection() as db:
            db.execute(
                """UPDATE tasks SET status=?, stage=?, progress=?, result_json=?,
                   error=?, updated_at=? WHERE id=?""",
                (status, stage, progress, json.dumps(result, ensure_ascii=False) if result else None,
                 error, now(), task_id),
            )

    def recover_pending(self) -> list[dict]:
        with self._connection() as db:
            db.execute(
                """UPDATE tasks SET status='queued', stage='服务重启后重新排队', progress=0,
                   updated_at=? WHERE status='running'""",
                (now(),),
            )
            rows = db.execute("SELECT * FROM tasks WHERE status='queued'").fetchall()
        return [self._decode(row) for row in rows]
