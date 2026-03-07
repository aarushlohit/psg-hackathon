"""CLARA messaging protocol — JSON-based, version-tagged, transport-agnostic."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
MESSAGE_DELIMITER = b"\n"


class MessageType(str, Enum):
    """All recognized message types."""

    MESSAGE = "message"
    JOIN = "join"
    LEAVE = "leave"
    LIST = "list"
    LIST_RESPONSE = "list_response"
    ERROR = "error"
    ACK = "ack"


@dataclass
class ClaraMessage:
    """A single protocol message exchanged between client ↔ server."""

    type: MessageType
    room: str = ""
    user: str = ""
    content: str = ""
    timestamp: float = field(default_factory=time.time)
    version: int = PROTOCOL_VERSION
    extra: dict[str, str] = field(default_factory=dict)

    # ---- serialization ----

    def to_bytes(self) -> bytes:
        """Serialize to newline-delimited JSON bytes."""
        payload = asdict(self)
        payload["type"] = self.type.value
        return json.dumps(payload, separators=(",", ":")).encode("utf-8") + MESSAGE_DELIMITER

    @classmethod
    def from_bytes(cls, data: bytes) -> ClaraMessage:
        """Deserialize from JSON bytes (one line)."""
        raw = json.loads(data.strip())
        raw["type"] = MessageType(raw["type"])
        raw.pop("version", None)
        return cls(**raw)


def encode_message(msg: ClaraMessage) -> bytes:
    """Convenience wrapper for ClaraMessage.to_bytes."""
    return msg.to_bytes()


def decode_message(data: bytes) -> Optional[ClaraMessage]:
    """Attempt to decode bytes into a ClaraMessage; returns None on failure."""
    try:
        return ClaraMessage.from_bytes(data)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        logger.warning("Failed to decode message: %s", exc)
        return None
