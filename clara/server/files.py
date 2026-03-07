"""CLARA server — file transfer service (base64 over WebSocket)."""

import base64
import hashlib
import logging
import secrets
from pathlib import Path
from typing import Optional

from clara.config.settings import settings
from clara.database.db import ClaraDB
from clara.server.protocol import Action, Packet

logger = logging.getLogger("clara.messages")

UPLOAD_DIR = settings.storage.upload_dir
MAX_FILE_SIZE = settings.security.max_file_size


def _ensure_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


class FileService:
    """Handles file upload, download, and listing."""

    def __init__(self, db: ClaraDB) -> None:
        self.db = db

    async def handle_upload(self, client, pkt: Packet, broadcast_fn) -> None:
        filename = pkt.data.get("filename", "")
        data_b64 = pkt.data.get("data", "")
        if not filename or not data_b64:
            await client.send(Packet.error("Filename and data required."))
            return
        file_id = secrets.token_hex(8)
        try:
            raw = base64.b64decode(data_b64)
        except Exception:
            await client.send(Packet.error("Invalid base64 data."))
            return
        if len(raw) > MAX_FILE_SIZE:
            await client.send(Packet.error(f"File too large ({len(raw)} bytes, max {MAX_FILE_SIZE})."))
            return

        dest = _ensure_dir() / file_id
        dest.write_bytes(raw)
        sha = hashlib.sha256(raw).hexdigest()
        room = client.room or ""
        self.db.store_file(file_id, filename, client.username, room, len(raw))

        await client.send(Packet.ok(
            f"File uploaded: {filename} ({len(raw)} bytes)",
            file_id=file_id, sha256=sha,
        ))
        if room:
            await broadcast_fn(
                room,
                Packet.system(f"{client.username} shared file: {filename} (ID: {file_id})", room=room),
                exclude=client.username,
            )
        logger.info("File uploaded: %s by %s (%d bytes)", filename, client.username, len(raw))

    async def handle_download(self, client, pkt: Packet) -> None:
        file_id = pkt.content.strip() or pkt.data.get("file_id", "")
        if not file_id:
            await client.send(Packet.error("File ID required."))
            return
        rec = self.db.get_file(file_id)
        if not rec:
            await client.send(Packet.error("File not found."))
            return
        path = _ensure_dir() / file_id
        if not path.exists():
            await client.send(Packet.error("File data missing."))
            return
        raw = path.read_bytes()
        data_b64 = base64.b64encode(raw).decode()
        sha = hashlib.sha256(raw).hexdigest()
        await client.send(Packet(
            action=Action.FILE_DATA,
            data={"file_id": file_id, "filename": rec.filename,
                   "data": data_b64, "sha256": sha, "size": rec.size},
        ))

    async def handle_list(self, client, pkt: Packet) -> None:
        room = pkt.room or client.room or ""
        files = self.db.list_files(room)
        file_data = [{"file_id": f.file_id, "filename": f.filename,
                       "sender": f.sender, "size": f.size} for f in files]
        await client.send(Packet(action=Action.FILE_RECORD_LIST, data={"files": file_data}))
