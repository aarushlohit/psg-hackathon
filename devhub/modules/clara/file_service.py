"""CLARA file transfer — server-side upload / download via chunked base64 over WS."""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
from pathlib import Path

from devhub.storage.paths import ensure_home_dir

logger = logging.getLogger(__name__)

UPLOAD_DIR: Path = ensure_home_dir() / "clara_files"
MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50 MB


def ensure_upload_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


def generate_file_id() -> str:
    return secrets.token_hex(8)


def save_uploaded_file(file_id: str, filename: str, data_b64: str) -> tuple[int, str]:
    """Decode base64 data and write to disk. Returns (size, sha256)."""
    dest = ensure_upload_dir() / file_id
    raw = base64.b64decode(data_b64)
    if len(raw) > MAX_FILE_SIZE:
        raise ValueError(f"File too large ({len(raw)} bytes, max {MAX_FILE_SIZE})")
    dest.write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    return len(raw), sha


def read_file_b64(file_id: str) -> tuple[bytes, str]:
    """Read a stored file and return (base64_encoded, sha256)."""
    path = ensure_upload_dir() / file_id
    if not path.exists():
        raise FileNotFoundError(f"File {file_id} not found")
    raw = path.read_bytes()
    return base64.b64encode(raw), hashlib.sha256(raw).hexdigest()


def delete_stored_file(file_id: str) -> bool:
    path = ensure_upload_dir() / file_id
    if path.exists():
        path.unlink()
        return True
    return False
