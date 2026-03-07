"""CLARA database — SQLite persistence for users, rooms, messages, files, AI usage."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from devhub.storage.paths import ensure_home_dir

logger = logging.getLogger(__name__)

DB_PATH: Path = ensure_home_dir() / "clara.db"


# ──────────────────────────── dataclasses ────────────────────────────


@dataclass
class User:
    id: int = 0
    username: str = ""
    password_hash: str = ""
    salt: str = ""
    role: str = "user"  # user | admin | moderator
    created_at: float = 0.0
    banned: bool = False


@dataclass
class Room:
    id: int = 0
    name: str = ""
    created_by: str = ""
    created_at: float = 0.0
    is_private: bool = False


@dataclass
class Message:
    id: int = 0
    sender: str = ""
    room: str = ""
    content: str = ""
    timestamp: float = 0.0
    edited: bool = False
    deleted: bool = False
    recipient: str = ""  # non-empty → DM


@dataclass
class FileRecord:
    id: int = 0
    file_id: str = ""
    filename: str = ""
    sender: str = ""
    room: str = ""
    size: int = 0
    uploaded_at: float = 0.0


@dataclass
class AIUsageRecord:
    id: int = 0
    username: str = ""
    provider: str = ""
    tokens_used: int = 0
    cost: float = 0.0
    timestamp: float = 0.0


# ──────────────────────────── password hashing ────────────────────────────


def _hash_password(password: str, salt: str) -> str:
    """Derive password hash via PBKDF2-HMAC-SHA256 (100k iterations)."""
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100_000
    ).hex()


def create_password_hash(password: str) -> tuple[str, str]:
    """Return (hash, salt) for a new password."""
    salt = secrets.token_hex(16)
    return _hash_password(password, salt), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """Constant-time comparison of password against stored hash."""
    candidate = _hash_password(password, salt)
    return hmac.compare_digest(candidate, stored_hash)


# ──────────────────────────── database manager ────────────────────────────


class ClaraDatabase:
    """Thread-safe SQLite database for CLARA."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = str(path or DB_PATH)
        self._conn: Optional[sqlite3.Connection] = None

    # ── lifecycle ──

    def connect(self) -> None:
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.row_factory = sqlite3.Row
        self._create_tables()
        logger.debug("CLARA database opened at %s", self._path)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        return self._conn  # type: ignore[return-value]

    # ── schema ──

    def _create_tables(self) -> None:
        c = self.conn
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT    UNIQUE NOT NULL,
                password_hash TEXT  NOT NULL,
                salt        TEXT    NOT NULL,
                role        TEXT    DEFAULT 'user',
                created_at  REAL   NOT NULL,
                banned      INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS rooms (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    UNIQUE NOT NULL,
                created_by  TEXT    NOT NULL,
                created_at  REAL   NOT NULL,
                is_private  INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS room_members (
                room_name   TEXT NOT NULL,
                username    TEXT NOT NULL,
                joined_at   REAL NOT NULL,
                PRIMARY KEY (room_name, username)
            );
            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                sender      TEXT    NOT NULL,
                room        TEXT    DEFAULT '',
                content     TEXT    NOT NULL,
                timestamp   REAL   NOT NULL,
                edited      INTEGER DEFAULT 0,
                deleted     INTEGER DEFAULT 0,
                recipient   TEXT    DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS files (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id     TEXT    UNIQUE NOT NULL,
                filename    TEXT    NOT NULL,
                sender      TEXT    NOT NULL,
                room        TEXT    DEFAULT '',
                size        INTEGER DEFAULT 0,
                uploaded_at REAL   NOT NULL
            );
            CREATE TABLE IF NOT EXISTS voice_sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                caller      TEXT NOT NULL,
                callee      TEXT DEFAULT '',
                room        TEXT DEFAULT '',
                started_at  REAL NOT NULL,
                ended_at    REAL DEFAULT 0,
                session_type TEXT DEFAULT 'p2p'
            );
            CREATE TABLE IF NOT EXISTS ai_usage (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT NOT NULL,
                provider    TEXT NOT NULL,
                tokens_used INTEGER DEFAULT 0,
                cost        REAL DEFAULT 0.0,
                timestamp   REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_room ON messages(room);
            CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender);
            CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient);
            CREATE INDEX IF NOT EXISTS idx_files_room ON files(room);
            """
        )
        c.commit()
        # Ensure default #general room
        self._ensure_default_room()

    def _ensure_default_room(self) -> None:
        cur = self.conn.execute("SELECT 1 FROM rooms WHERE name = ?", ("general",))
        if cur.fetchone() is None:
            self.conn.execute(
                "INSERT INTO rooms (name, created_by, created_at) VALUES (?, ?, ?)",
                ("general", "system", time.time()),
            )
            self.conn.commit()

    # ── users ──

    def create_user(self, username: str, password: str, role: str = "user") -> User:
        pw_hash, salt = create_password_hash(password)
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO users (username, password_hash, salt, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, pw_hash, salt, role, now),
        )
        self.conn.commit()
        return User(id=cur.lastrowid or 0, username=username, password_hash=pw_hash,
                     salt=salt, role=role, created_at=now)

    def get_user(self, username: str) -> Optional[User]:
        row = self.conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            return None
        return User(**dict(row))

    def authenticate(self, username: str, password: str) -> Optional[User]:
        user = self.get_user(username)
        if user is None:
            return None
        if not verify_password(password, user.password_hash, user.salt):
            return None
        if user.banned:
            return None
        return user

    def ban_user(self, username: str) -> bool:
        cur = self.conn.execute("UPDATE users SET banned = 1 WHERE username = ?", (username,))
        self.conn.commit()
        return cur.rowcount > 0

    def unban_user(self, username: str) -> bool:
        cur = self.conn.execute("UPDATE users SET banned = 0 WHERE username = ?", (username,))
        self.conn.commit()
        return cur.rowcount > 0

    def set_role(self, username: str, role: str) -> bool:
        cur = self.conn.execute("UPDATE users SET role = ? WHERE username = ?", (role, username))
        self.conn.commit()
        return cur.rowcount > 0

    # ── rooms ──

    def create_room(self, name: str, created_by: str, is_private: bool = False) -> Room:
        now = time.time()
        self.conn.execute(
            "INSERT INTO rooms (name, created_by, created_at, is_private) VALUES (?, ?, ?, ?)",
            (name, created_by, now, int(is_private)),
        )
        self.conn.commit()
        return Room(name=name, created_by=created_by, created_at=now, is_private=is_private)

    def get_room(self, name: str) -> Optional[Room]:
        row = self.conn.execute("SELECT * FROM rooms WHERE name = ?", (name,)).fetchone()
        if row is None:
            return None
        return Room(**dict(row))

    def list_rooms(self) -> list[Room]:
        rows = self.conn.execute("SELECT * FROM rooms WHERE is_private = 0 ORDER BY name").fetchall()
        return [Room(**dict(r)) for r in rows]

    def join_room(self, room_name: str, username: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO room_members (room_name, username, joined_at) VALUES (?, ?, ?)",
            (room_name, username, time.time()),
        )
        self.conn.commit()

    def leave_room(self, room_name: str, username: str) -> None:
        self.conn.execute(
            "DELETE FROM room_members WHERE room_name = ? AND username = ?",
            (room_name, username),
        )
        self.conn.commit()

    def get_room_members(self, room_name: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT username FROM room_members WHERE room_name = ? ORDER BY username",
            (room_name,),
        ).fetchall()
        return [r["username"] for r in rows]

    # ── messages ──

    def store_message(self, sender: str, room: str, content: str, recipient: str = "") -> Message:
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO messages (sender, room, content, timestamp, recipient) VALUES (?, ?, ?, ?, ?)",
            (sender, room, content, now, recipient),
        )
        self.conn.commit()
        return Message(id=cur.lastrowid or 0, sender=sender, room=room,
                       content=content, timestamp=now, recipient=recipient)

    def edit_message(self, msg_id: int, sender: str, new_content: str) -> bool:
        cur = self.conn.execute(
            "UPDATE messages SET content = ?, edited = 1 WHERE id = ? AND sender = ? AND deleted = 0",
            (new_content, msg_id, sender),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def delete_message(self, msg_id: int, sender: str) -> bool:
        cur = self.conn.execute(
            "UPDATE messages SET deleted = 1 WHERE id = ? AND sender = ?",
            (msg_id, sender),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def search_messages(self, room: str, query: str, limit: int = 50) -> list[Message]:
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE room = ? AND content LIKE ? AND deleted = 0 ORDER BY timestamp DESC LIMIT ?",
            (room, f"%{query}%", limit),
        ).fetchall()
        return [Message(**dict(r)) for r in rows]

    def get_recent_messages(self, room: str, limit: int = 50) -> list[Message]:
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE room = ? AND deleted = 0 AND recipient = '' ORDER BY timestamp DESC LIMIT ?",
            (room, limit),
        ).fetchall()
        return [Message(**dict(r)) for r in reversed(rows)]

    def get_dm_history(self, user1: str, user2: str, limit: int = 50) -> list[Message]:
        rows = self.conn.execute(
            """SELECT * FROM messages
               WHERE deleted = 0 AND recipient != ''
                 AND ((sender = ? AND recipient = ?) OR (sender = ? AND recipient = ?))
               ORDER BY timestamp DESC LIMIT ?""",
            (user1, user2, user2, user1, limit),
        ).fetchall()
        return [Message(**dict(r)) for r in reversed(rows)]

    # ── files ──

    def store_file(self, file_id: str, filename: str, sender: str, room: str, size: int) -> FileRecord:
        now = time.time()
        self.conn.execute(
            "INSERT INTO files (file_id, filename, sender, room, size, uploaded_at) VALUES (?, ?, ?, ?, ?, ?)",
            (file_id, filename, sender, room, size, now),
        )
        self.conn.commit()
        return FileRecord(file_id=file_id, filename=filename, sender=sender,
                          room=room, size=size, uploaded_at=now)

    def get_file(self, file_id: str) -> Optional[FileRecord]:
        row = self.conn.execute("SELECT * FROM files WHERE file_id = ?", (file_id,)).fetchone()
        if row is None:
            return None
        return FileRecord(**dict(row))

    def list_files(self, room: str = "") -> list[FileRecord]:
        if room:
            rows = self.conn.execute(
                "SELECT * FROM files WHERE room = ? ORDER BY uploaded_at DESC", (room,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM files ORDER BY uploaded_at DESC").fetchall()
        return [FileRecord(**dict(r)) for r in rows]

    # ── AI usage ──

    def log_ai_usage(self, username: str, provider: str, tokens: int, cost: float) -> None:
        self.conn.execute(
            "INSERT INTO ai_usage (username, provider, tokens_used, cost, timestamp) VALUES (?, ?, ?, ?, ?)",
            (username, provider, tokens, cost, time.time()),
        )
        self.conn.commit()

    def get_ai_usage(self, username: str) -> dict:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(tokens_used), 0) as total_tokens, COALESCE(SUM(cost), 0.0) as total_cost, COUNT(*) as requests FROM ai_usage WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row) if row else {"total_tokens": 0, "total_cost": 0.0, "requests": 0}

    # ── voice sessions ──

    def create_voice_session(self, caller: str, callee: str = "", room: str = "", session_type: str = "p2p") -> int:
        cur = self.conn.execute(
            "INSERT INTO voice_sessions (caller, callee, room, started_at, session_type) VALUES (?, ?, ?, ?, ?)",
            (caller, callee, room, time.time(), session_type),
        )
        self.conn.commit()
        return cur.lastrowid or 0

    def end_voice_session(self, session_id: int) -> None:
        self.conn.execute(
            "UPDATE voice_sessions SET ended_at = ? WHERE id = ?",
            (time.time(), session_id),
        )
        self.conn.commit()
