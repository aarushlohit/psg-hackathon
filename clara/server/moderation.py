"""CLARA server — moderation service (kick, ban, mute, roles)."""

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from clara.database.db import ClaraDB
from clara.server.protocol import Action, Packet

if TYPE_CHECKING:
    from clara.server.websocket import ConnectedClient

logger = logging.getLogger("clara.connections")

_ROLE_POWER = {"owner": 40, "admin": 30, "moderator": 20, "member": 10}


def _power(role: str) -> int:
    return _ROLE_POWER.get(role, 0)


@dataclass
class MuteRecord:
    username: str
    room: str
    until: float
    by: str


class ModerationService:
    """Handles kick, ban, mute, role management."""

    def __init__(self, db: ClaraDB) -> None:
        self.db = db
        self._mutes: dict[str, MuteRecord] = {}  # "user:room" → record

    def is_muted(self, username: str, room: str) -> bool:
        key = f"{username}:{room}"
        rec = self._mutes.get(key)
        if not rec:
            return False
        if time.time() > rec.until:
            del self._mutes[key]
            return False
        return True

    def mute_remaining(self, username: str, room: str) -> float:
        key = f"{username}:{room}"
        rec = self._mutes.get(key)
        if not rec:
            return 0.0
        remaining = rec.until - time.time()
        return max(0.0, remaining)

    # ── handlers ──

    async def handle_kick(self, client: "ConnectedClient", pkt: Packet,
                          clients: dict[str, "ConnectedClient"]) -> None:
        target = pkt.target
        if not target or not client.room:
            await client.send(Packet.error("Usage: /kick <username>"))
            return
        if _power(client.role) < _power("moderator"):
            await client.send(Packet.error("Insufficient permissions."))
            return

        target_client = clients.get(target)
        if not target_client or target_client.room != client.room:
            await client.send(Packet.error(f"User '{target}' not in this room."))
            return
        if _power(target_client.role) >= _power(client.role):
            await client.send(Packet.error("Cannot kick a user with equal or higher role."))
            return

        room = target_client.room
        target_client.room = None
        await target_client.send(Packet.system(f"You were kicked from #{room} by {client.username}."))
        await client.send(Packet.ok(f"Kicked {target} from #{room}."))
        # Broadcast
        for c in clients.values():
            if c.room == room and c.username != client.username:
                await c.send(Packet.system(f"{target} was kicked by {client.username}."))

    async def handle_ban(self, client: "ConnectedClient", pkt: Packet,
                         clients: dict[str, "ConnectedClient"]) -> None:
        target = pkt.target
        if not target:
            await client.send(Packet.error("Usage: /ban <username>"))
            return
        if _power(client.role) < _power("admin"):
            await client.send(Packet.error("Only admins can ban users."))
            return

        target_user = self.db.get_user(target)
        if not target_user:
            await client.send(Packet.error(f"User '{target}' not found."))
            return
        if _power(target_user.role) >= _power(client.role):
            await client.send(Packet.error("Cannot ban a user with equal or higher role."))
            return

        self.db.ban_user(target, banned=True)
        await client.send(Packet.ok(f"Banned {target}."))
        logger.info("User %s banned by %s", target, client.username)

        tc = clients.get(target)
        if tc:
            await tc.send(Packet.system(f"You have been banned by {client.username}."))
            await tc.ws.close()

    async def handle_unban(self, client: "ConnectedClient", pkt: Packet) -> None:
        target = pkt.target
        if not target:
            await client.send(Packet.error("Usage: /unban <username>"))
            return
        if _power(client.role) < _power("admin"):
            await client.send(Packet.error("Only admins can unban users."))
            return
        self.db.ban_user(target, banned=False)
        await client.send(Packet.ok(f"Unbanned {target}."))

    async def handle_mute(self, client: "ConnectedClient", pkt: Packet) -> None:
        target = pkt.target
        if not target or not client.room:
            await client.send(Packet.error("Usage: /mute <username> [minutes]"))
            return
        if _power(client.role) < _power("moderator"):
            await client.send(Packet.error("Insufficient permissions."))
            return

        duration = 5.0
        if pkt.content:
            try:
                duration = float(pkt.content)
            except ValueError:
                pass

        key = f"{target}:{client.room}"
        self._mutes[key] = MuteRecord(
            username=target, room=client.room,
            until=time.time() + duration * 60, by=client.username,
        )
        await client.send(Packet.ok(f"Muted {target} for {duration} min."))

    async def handle_unmute(self, client: "ConnectedClient", pkt: Packet) -> None:
        target = pkt.target
        if not target or not client.room:
            await client.send(Packet.error("Usage: /unmute <username>"))
            return
        if _power(client.role) < _power("moderator"):
            await client.send(Packet.error("Insufficient permissions."))
            return
        key = f"{target}:{client.room}"
        self._mutes.pop(key, None)
        await client.send(Packet.ok(f"Unmuted {target}."))

    async def handle_role(self, client: "ConnectedClient", pkt: Packet) -> None:
        parts = (pkt.content or "").split()
        if len(parts) < 2:
            await client.send(Packet.error("Usage: /role <username> <role>"))
            return
        target, new_role = parts[0], parts[1].lower()
        if new_role not in _ROLE_POWER:
            await client.send(Packet.error(f"Valid roles: {', '.join(_ROLE_POWER)}"))
            return
        if _power(client.role) < _power("admin"):
            await client.send(Packet.error("Only admins can change roles."))
            return
        if _power(new_role) >= _power(client.role):
            await client.send(Packet.error("Cannot assign role >= your own."))
            return
        self.db.set_role(target, new_role)
        await client.send(Packet.ok(f"Set {target}'s role to {new_role}."))
