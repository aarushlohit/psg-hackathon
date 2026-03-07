"""CLARA database models — pure dataclasses mirroring SQL tables."""

from dataclasses import dataclass


@dataclass
class User:
    id: int = 0
    username: str = ""
    password_hash: str = ""
    salt: str = ""
    role: str = "user"          # user | admin | moderator
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
    recipient: str = ""         # non-empty → DM


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
class VoiceSession:
    id: int = 0
    caller: str = ""
    callee: str = ""
    room: str = ""
    started_at: float = 0.0
    ended_at: float = 0.0
    session_type: str = "p2p"


@dataclass
class AIUsageRecord:
    id: int = 0
    username: str = ""
    provider: str = ""
    tokens_used: int = 0
    cost: float = 0.0
    timestamp: float = 0.0
