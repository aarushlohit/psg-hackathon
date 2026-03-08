"""CLARA server — WebSocket hub.  Central dispatcher wiring all services.

NOTE: Do NOT add ``from __future__ import annotations`` to this file or any
file that defines FastAPI route handlers — it breaks WebSocket parameter
injection in FastAPI + uvicorn, causing 403 errors.
"""

import asyncio
import json
import logging
import time
from typing import Optional

from clara.config.settings import settings
from clara.database.db import ClaraDB
from clara.server.ai_gateway import AIGateway
from clara.server.auth import create_token, verify_token
from clara.server.files import FileService
from clara.server.messaging import MessagingService
from clara.server.moderation import ModerationService
from clara.server.presence import PresenceService
from clara.server.protocol import Action, Packet
from clara.server.rooms import RoomManager
from clara.server.voice import VoiceService

logger = logging.getLogger("clara.connections")


class ConnectedClient:
    """Represents a single WebSocket connection."""

    __slots__ = ("ws", "username", "room", "authenticated", "role", "token")

    def __init__(self, websocket: object) -> None:
        self.ws = websocket
        self.username: str = ""
        self.room: str = ""
        self.authenticated: bool = False
        self.role: str = "member"
        self.token: str = ""

    async def send(self, pkt: Packet) -> None:
        try:
            await self.ws.send_text(pkt.to_json())  # type: ignore[union-attr]
        except Exception:
            pass


class ClaraHub:
    """Core server logic — routes packets to service modules."""

    def __init__(self, db: ClaraDB) -> None:
        self.db = db
        self.clients: dict[str, ConnectedClient] = {}

        # Services
        self.rooms = RoomManager(db)
        self.messaging = MessagingService(db)
        self.voice = VoiceService(db)
        self.files = FileService(db)
        self.ai = AIGateway(db)
        self.moderation = ModerationService(db)
        self.presence = PresenceService()

        # Rate limiting
        self._rate_limits: dict[str, list[float]] = {}

    def start(self) -> None:
        self.presence.start()

    def stop(self) -> None:
        self.presence.stop()

    # ── connection lifecycle ──

    async def on_connect(self, ws: object) -> ConnectedClient:
        return ConnectedClient(ws)

    async def on_disconnect(self, client: ConnectedClient) -> None:
        if not client.username:
            return
        # Only clean up if this client is still the active session for the user.
        # A reconnect may have already replaced the entry with a new client;
        # tearing down the old session must not sabotage the new one.
        is_current = self.clients.get(client.username) is client
        if client.room and is_current:
            await self._broadcast_to_room(
                client.room,
                Packet.system(f"{client.username} disconnected.", room=client.room),
                exclude=client.username,
            )
            self.db.leave_room(client.room, client.username)
        self.voice.remove_user(client.username)
        if is_current:
            await self.presence.user_disconnected(client.username, self.clients)
            self.clients.pop(client.username, None)

    # ── rate limiting ──

    def _check_rate(self, username: str, max_per_sec: int = 10) -> bool:
        now = time.time()
        ts = self._rate_limits.setdefault(username, [])
        ts[:] = [t for t in ts if now - t < 1.0]
        if len(ts) >= max_per_sec:
            return False
        ts.append(now)
        return True

    # ── main dispatcher ──

    async def handle_packet(self, client: ConnectedClient, pkt: Packet) -> None:
        action = pkt.action

        # Pre-auth actions
        if action in (Action.REGISTER, Action.LOGIN):
            await self._handle_auth(client, pkt)
            return

        if not client.authenticated:
            await client.send(Packet.error("Not authenticated. Login first."))
            return

        if not self._check_rate(client.username):
            await client.send(Packet.error("Rate limited. Slow down."))
            return

        _D = self._dispatch_table()
        handler = _D.get(action)
        if handler:
            await handler(client, pkt)
        else:
            await client.send(Packet.error(f"Unknown action: {action.value}"))

    def _dispatch_table(self) -> dict:
        return {
            # Connection
            Action.WHOAMI: self._handle_whoami,
            Action.DISCONNECT: self._handle_disconnect_cmd,
            Action.HEARTBEAT: self._handle_heartbeat,
            Action.PRESENCE: self._handle_who,
            Action.TYPING: self._handle_typing,
            Action.STATUS: self._handle_status,
            # Rooms
            Action.CREATE_ROOM: self._handle_create_room,
            Action.JOIN: self._handle_join,
            Action.LEAVE: self._handle_leave,
            Action.LIST_ROOMS: self._handle_list_rooms,
            Action.LIST_USERS: self._handle_list_users,
            # Messaging
            Action.MESSAGE: self._handle_message,
            Action.DM: self._handle_dm,
            Action.REPLY: self._handle_reply,
            Action.EDIT: self._handle_edit,
            Action.DELETE: self._handle_delete,
            Action.SEARCH: self._handle_search,
            Action.HISTORY: self._handle_history,
            # Voice
            Action.CALL: self._handle_voice_cmd,
            Action.CALL_ACCEPT: self._handle_voice_cmd,
            Action.CALL_REJECT: self._handle_voice_cmd,
            Action.CALL_END: self._handle_voice_cmd,
            Action.VOICE_JOIN: self._handle_voice_cmd,
            Action.VOICE_LEAVE: self._handle_voice_cmd,
            Action.VOICE_SIGNAL: self._handle_voice_signal,
            Action.MUTE: self._handle_voice_mute,
            Action.UNMUTE: self._handle_voice_unmute,
            # Files
            Action.FILE_UPLOAD: self._handle_file_upload,
            Action.FILE_DOWNLOAD: self._handle_file_download,
            Action.FILE_LIST: self._handle_file_list,
            # AI
            Action.AI_ENABLE: self._handle_ai_enable,
            Action.AI_ASK: self._handle_ai_ask,
            Action.AI_SUMMARIZE: self._handle_ai_summarize,
            Action.AI_USAGE: self._handle_ai_usage,
            Action.AI_BUDGET: self._handle_ai_budget,
            Action.AI_LIMIT: self._handle_ai_limit,
            # Moderation
            Action.KICK: self._handle_kick,
            Action.BAN: self._handle_ban,
            Action.UNBAN: self._handle_unban,
            Action.MUTE_USER: self._handle_mute_user,
            Action.UNMUTE_USER: self._handle_unmute_user,
            Action.ADMIN: self._handle_role,
        }

    # ═══════════════  AUTH  ═══════════════

    async def _handle_auth(self, client: ConnectedClient, pkt: Packet) -> None:
        username = (pkt.sender or "").strip()
        password = pkt.data.get("password", "")
        if not username or not password:
            await client.send(Packet(action=Action.AUTH_FAIL,
                                      content="Username and password required."))
            return

        if pkt.action == Action.REGISTER:
            if self.db.get_user(username):
                await client.send(Packet(action=Action.AUTH_FAIL,
                                          content="Username taken."))
                return
            user = self.db.create_user(username, password)
            token = create_token(username, user.role)
            client.username = username
            client.authenticated = True
            client.role = user.role
            client.token = token
            self.clients[username] = client
            await self.presence.user_connected(username, self.clients)
            await client.send(Packet(action=Action.AUTH_OK, sender=username,
                                      content=f"Registered as {username}.",
                                      data={"role": user.role, "token": token}))
        elif pkt.action == Action.LOGIN:
            user = self.db.authenticate(username, password)
            if not user:
                await client.send(Packet(action=Action.AUTH_FAIL,
                                          content="Invalid credentials or banned."))
                return
            # Kick old session
            old = self.clients.pop(username, None)
            if old:
                await old.send(Packet.system("Session replaced by new login."))
            token = create_token(username, user.role)
            client.username = username
            client.authenticated = True
            client.role = user.role
            client.token = token
            self.clients[username] = client
            await self.presence.user_connected(username, self.clients)
            await client.send(Packet(action=Action.AUTH_OK, sender=username,
                                      content=f"Welcome back, {username}.",
                                      data={"role": user.role, "token": token}))

    # ═══════════════  CONNECTION  ═══════════════

    async def _handle_whoami(self, client: ConnectedClient, pkt: Packet) -> None:
        await client.send(Packet.ok(
            content=client.username, role=client.role, room=client.room,
        ))

    async def _handle_disconnect_cmd(self, client: ConnectedClient, pkt: Packet) -> None:
        await client.send(Packet.ok("Disconnected."))

    async def _handle_heartbeat(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.presence.handle_heartbeat(client, pkt)

    async def _handle_who(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.presence.handle_who(client, pkt)

    async def _handle_typing(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.presence.handle_typing(client, pkt, self.clients)

    async def _handle_status(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.presence.handle_status(client, pkt, self.clients)

    # ═══════════════  ROOMS  ═══════════════

    async def _handle_create_room(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.rooms.handle_create(client, pkt)

    async def _handle_join(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.rooms.handle_join(client, pkt, self._broadcast_to_room)

    async def _handle_leave(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.rooms.handle_leave(client, pkt, self._broadcast_to_room)

    async def _handle_list_rooms(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.rooms.handle_list_rooms(client, pkt)

    async def _handle_list_users(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.rooms.handle_list_users(client, pkt, list(self.clients.keys()))

    # ═══════════════  MESSAGING  ═══════════════

    async def _handle_message(self, client: ConnectedClient, pkt: Packet) -> None:
        if self.moderation.is_muted(client.username, client.room or ""):
            await client.send(Packet.error("You are muted."))
            return
        await self.messaging.handle_message(client, pkt, self._broadcast_to_room)

    async def _handle_dm(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.messaging.handle_dm(client, pkt, self._get_client)

    async def _handle_reply(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.messaging.handle_reply(client, pkt, self._broadcast_to_room)

    async def _handle_edit(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.messaging.handle_edit(client, pkt, self._broadcast_to_room)

    async def _handle_delete(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.messaging.handle_delete(client, pkt, self._broadcast_to_room)

    async def _handle_search(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.messaging.handle_search(client, pkt)

    async def _handle_history(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.messaging.handle_history(client, pkt)

    # ═══════════════  VOICE  ═══════════════

    async def _handle_voice_cmd(self, client: ConnectedClient, pkt: Packet) -> None:
        a = pkt.action
        if a == Action.CALL:
            await self.voice.handle_call(client, pkt, self._get_client)
        elif a == Action.CALL_ACCEPT:
            await self.voice.handle_call_accept(client, pkt, self._get_client)
        elif a == Action.CALL_REJECT:
            await self.voice.handle_call_reject(client, pkt, self._get_client)
        elif a == Action.CALL_END:
            await self.voice.handle_call_end(client, pkt, self._get_client)
        elif a == Action.VOICE_JOIN:
            await self.voice.handle_voice_join(client, pkt, self._broadcast_to_room)
        elif a == Action.VOICE_LEAVE:
            await self.voice.handle_voice_leave(client, pkt, self._broadcast_to_room)

    async def _handle_voice_signal(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.voice.handle_voice_signal(client, pkt, self._get_client)

    async def _handle_voice_mute(self, client: ConnectedClient, pkt: Packet) -> None:
        if client.room:
            await self._broadcast_to_room(
                client.room, Packet.system(f"{client.username} muted.", room=client.room))
        await client.send(Packet.ok("Muted."))

    async def _handle_voice_unmute(self, client: ConnectedClient, pkt: Packet) -> None:
        if client.room:
            await self._broadcast_to_room(
                client.room, Packet.system(f"{client.username} unmuted.", room=client.room))
        await client.send(Packet.ok("Unmuted."))

    # ═══════════════  FILES  ═══════════════

    async def _handle_file_upload(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.files.handle_upload(client, pkt, self._broadcast_to_room)

    async def _handle_file_download(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.files.handle_download(client, pkt)

    async def _handle_file_list(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.files.handle_list(client, pkt)

    # ═══════════════  AI  ═══════════════

    async def _handle_ai_enable(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.ai.handle_enable(client, pkt)

    async def _handle_ai_ask(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.ai.handle_ask(client, pkt)

    async def _handle_ai_summarize(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.ai.handle_summarize(client, pkt)

    async def _handle_ai_usage(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.ai.handle_usage(client, pkt)

    async def _handle_ai_budget(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.ai.handle_budget(client, pkt)

    async def _handle_ai_limit(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.ai.handle_limit(client, pkt)

    # ═══════════════  MODERATION  ═══════════════

    async def _handle_kick(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.moderation.handle_kick(client, pkt, self.clients)

    async def _handle_ban(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.moderation.handle_ban(client, pkt, self.clients)

    async def _handle_unban(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.moderation.handle_unban(client, pkt)

    async def _handle_mute_user(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.moderation.handle_mute(client, pkt)

    async def _handle_unmute_user(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.moderation.handle_unmute(client, pkt)

    async def _handle_role(self, client: ConnectedClient, pkt: Packet) -> None:
        await self.moderation.handle_role(client, pkt)

    # ═══════════════  HELPERS  ═══════════════

    def _get_client(self, username: str) -> Optional[ConnectedClient]:
        return self.clients.get(username)

    async def _broadcast_to_room(self, room: str, pkt: Packet, exclude: str = "") -> None:
        for c in list(self.clients.values()):
            if c.room == room and c.username != exclude:
                await c.send(pkt)
