"""MEMO repository — SQLite CRUD for tasks and notes."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from devhub.storage.paths import get_memo_db_path

logger = logging.getLogger(__name__)


# ---- data models ----


@dataclass
class Task:
    id: int
    title: str
    status: str  # "open" | "done"
    priority: str  # "low" | "medium" | "high"
    created_at: str

    @property
    def is_done(self) -> bool:
        return self.status == "done"


@dataclass
class Note:
    id: int
    title: str
    content: str
    created_at: str


# ---- repository ----


class MemoRepository:
    """SQLite-backed storage for tasks and notes."""

    def __init__(self) -> None:
        self._db_path = get_memo_db_path()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    # ---- connection ----

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                status      TEXT    NOT NULL DEFAULT 'open',
                priority    TEXT    NOT NULL DEFAULT 'medium',
                created_at  TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                content     TEXT    NOT NULL DEFAULT '',
                created_at  TEXT    NOT NULL
            );
            """
        )
        conn.commit()
        logger.debug("MEMO database initialized at %s", self._db_path)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ---- tasks ----

    def add_task(self, title: str, priority: str = "medium") -> Task:
        """Insert a new task and return it."""
        now = datetime.now().isoformat(timespec="seconds")
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO tasks (title, priority, created_at) VALUES (?, ?, ?)",
            (title, priority, now),
        )
        conn.commit()
        return Task(
            id=cursor.lastrowid or 0,
            title=title,
            status="open",
            priority=priority,
            created_at=now,
        )

    def list_tasks(self, status: Optional[str] = None) -> list[Task]:
        """Return tasks, optionally filtered by status."""
        conn = self._get_conn()
        if status:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY id", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
        return [Task(**dict(r)) for r in rows]

    def complete_task(self, task_id: int) -> bool:
        """Mark a task as done. Returns True if the task existed."""
        conn = self._get_conn()
        cursor = conn.execute(
            "UPDATE tasks SET status = 'done' WHERE id = ? AND status = 'open'",
            (task_id,),
        )
        conn.commit()
        return cursor.rowcount > 0

    # ---- notes ----

    def add_note(self, title: str, content: str = "") -> Note:
        """Insert a new note and return it."""
        now = datetime.now().isoformat(timespec="seconds")
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO notes (title, content, created_at) VALUES (?, ?, ?)",
            (title, content, now),
        )
        conn.commit()
        return Note(
            id=cursor.lastrowid or 0,
            title=title,
            content=content,
            created_at=now,
        )

    def list_notes(self, query: Optional[str] = None) -> list[Note]:
        """Return notes, optionally filtered by a search query on title."""
        conn = self._get_conn()
        if query:
            rows = conn.execute(
                "SELECT * FROM notes WHERE title LIKE ? ORDER BY id",
                (f"%{query}%",),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM notes ORDER BY id").fetchall()
        return [Note(**dict(r)) for r in rows]
