"""CLARA protocol — JSON WebSocket messages.

Every action the protocol understands, plus the Packet dataclass for
serialisation / deserialisation.
"""

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


PROTOCOL_VERSION = 2


class Action(str, Enum):
    # auth
    REGISTER = "register"
    LOGIN = "login"
    AUTH_OK = "auth_ok"
    AUTH_FAIL = "auth_fail"

    # connection / presence
    WHOAMI = "whoami"
    DISCONNECT = "disconnect"
    HEARTBEAT = "heartbeat"
    PRESENCE = "presence"
    TYPING = "typing"
    STATUS = "status"

    # rooms
    CREATE_ROOM = "create_room"
    JOIN = "join"
    LEAVE = "leave"
    LIST_ROOMS = "list_rooms"
    LIST_USERS = "list_users"

    # messaging
    MESSAGE = "message"
    DM = "dm"
    REPLY = "reply"
    EDIT = "edit"
    DELETE = "delete"
    SEARCH = "search"
    HISTORY = "history"

    # voice
    CALL = "call"
    CALL_ACCEPT = "call_accept"
    CALL_REJECT = "call_reject"
    CALL_END = "call_end"
    VOICE_JOIN = "voice_join"
    VOICE_LEAVE = "voice_leave"
    VOICE_SIGNAL = "voice_signal"
    MUTE = "mute"
    UNMUTE = "unmute"

    # files
    FILE_UPLOAD = "file_upload"
    FILE_DOWNLOAD = "file_download"
    FILE_LIST = "file_list"

    # AI
    AI_ENABLE = "ai_enable"
    AI_ASK = "ai_ask"
    AI_SUMMARIZE = "ai_summarize"
    AI_USAGE = "ai_usage"
    AI_BUDGET = "ai_budget"
    AI_LIMIT = "ai_limit"
    AI_RESPONSE = "ai_response"

    # moderation
    KICK = "kick"
    BAN = "ban"
    UNBAN = "unban"
    MUTE_USER = "mute_user"
    UNMUTE_USER = "unmute_user"
    ADMIN = "admin"

    # server responses
    OK = "ok"
    ERROR = "error"
    SYSTEM = "system"
    ROOM_LIST = "room_list"
    USER_LIST = "user_list"
    MSG_LIST = "msg_list"
    FILE_DATA = "file_data"
    FILE_RECORD_LIST = "file_record_list"
    SERVER_STATUS = "server_status"


@dataclass
class Packet:
    """A single protocol packet exchanged over WebSocket."""

    action: Action
    sender: str = ""
    room: str = ""
    content: str = ""
    target: str = ""
    msg_id: int = 0
    timestamp: float = field(default_factory=time.time)
    version: int = PROTOCOL_VERSION
    data: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        payload = asdict(self)
        payload["action"] = self.action.value
        return json.dumps(payload, separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> "Packet":
        obj = json.loads(raw)
        obj["action"] = Action(obj["action"])
        obj.pop("version", None)
        return cls(**obj)

    @classmethod
    def ok(cls, content: str = "", **data: Any) -> "Packet":
        return cls(action=Action.OK, content=content, data=data)

    @classmethod
    def error(cls, content: str) -> "Packet":
        return cls(action=Action.ERROR, content=content)

    @classmethod
    def system(cls, content: str, room: str = "") -> "Packet":
        return cls(action=Action.SYSTEM, sender="system", room=room, content=content)
