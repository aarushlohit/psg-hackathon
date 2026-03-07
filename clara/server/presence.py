"""CLARA server — presence service (online/offline, typing, heartbeat)."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from clara.server.protocol import Action, Packet

if TYPE_CHECKING:
    from clara.server.websocket import ConnectedClient

logger = logging.getLogger("clara.connections")

HEARTBEAT_INTERVAL = 30
HEARTBEAT_TIMEOUT = 90


@dataclass
class UserPresence:
    username: str
    status: str = "online"           # online, away, busy, offline
    last_heartbeat: float = 0.0
    last_activity: float = 0.0
    typing_in: str | None = None
    typing_until: float = 0.0


class PresenceService:
    """Tracks online/offline, typing indicators, heartbeat."""

    def __init__(self) -> None:
        self._presence: dict[str, UserPresence] = {}
        self._monitor_task: asyncio.Task | None = None

    # ── lifecycle ──

    def start(self) -> None:
        if self._monitor_task is None:
            self._monitor_task = asyncio.create_task(self._monitor_loop())

    def stop(self) -> None:
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None

    async def user_connected(self, username: str,
                             clients: dict[str, "ConnectedClient"]) -> None:
        now = time.time()
        self._presence[username] = UserPresence(
            username=username, status="online",
            last_heartbeat=now, last_activity=now,
        )
        await self._broadcast_status(username, "online", clients)

    async def user_disconnected(self, username: str,
                                clients: dict[str, "ConnectedClient"]) -> None:
        self._presence.pop(username, None)
        await self._broadcast_status(username, "offline", clients)

    # ── handlers ──

    async def handle_heartbeat(self, client: "ConnectedClient", pkt: Packet) -> None:
        p = self._presence.get(client.username)
        if p:
            p.last_heartbeat = time.time()
            p.last_activity = time.time()
        await client.send(Packet(action=Action.HEARTBEAT))

    async def handle_typing(self, client: "ConnectedClient", pkt: Packet,
                            clients: dict[str, "ConnectedClient"]) -> None:
        if not client.room:
            return
        p = self._presence.get(client.username)
        if p:
            p.typing_in = client.room
            p.typing_until = time.time() + 5.0
            p.last_activity = time.time()
        for c in clients.values():
            if c.room == client.room and c.username != client.username:
                await c.send(Packet(
                    action=Action.TYPING, sender=client.username,
                    data={"room": client.room},
                ))

    async def handle_status(self, client: "ConnectedClient", pkt: Packet,
                            clients: dict[str, "ConnectedClient"]) -> None:
        new_status = (pkt.content or "").strip().lower()
        valid = {"online", "away", "busy"}
        if new_status not in valid:
            await client.send(Packet.error(f"Valid statuses: {', '.join(valid)}"))
            return
        p = self._presence.get(client.username)
        if p:
            p.status = new_status
        await self._broadcast_status(client.username, new_status, clients)
        await client.send(Packet.ok(f"Status set to {new_status}."))

    async def handle_who(self, client: "ConnectedClient", pkt: Packet) -> None:
        users = {}
        for name, p in self._presence.items():
            users[name] = {
                "status": p.status,
                "typing": p.typing_in if time.time() < p.typing_until else None,
            }
        await client.send(Packet(
            action=Action.PRESENCE, data={"users": users},
        ))

    # ── internal ──

    async def _broadcast_status(self, username: str, status: str,
                                clients: dict[str, "ConnectedClient"]) -> None:
        pkt = Packet(action=Action.PRESENCE, sender=username,
                     data={"user": username, "status": status})
        for c in clients.values():
            if c.username and c.username != username:
                try:
                    await c.send(pkt)
                except Exception:
                    pass

    async def _monitor_loop(self) -> None:
        """Check for stale heartbeats periodically."""
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                now = time.time()
                stale = [
                    name for name, p in self._presence.items()
                    if now - p.last_heartbeat > HEARTBEAT_TIMEOUT
                ]
                for name in stale:
                    logger.info("Heartbeat timeout for %s", name)
                    self._presence.pop(name, None)
        except asyncio.CancelledError:
            pass
