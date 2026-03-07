"""CLARA WebSocket client — connects to a CLARA server and manages communication."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from pathlib import Path
from typing import Callable, Optional

import aiohttp

from devhub.modules.clara.protocol import Action, Packet

logger = logging.getLogger(__name__)


class ClaraWSClient:
    """WebSocket client for CLARA — handles auth, messaging, and async listening."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9100) -> None:
        self.host = host
        self.port = port
        self.username: str = ""
        self.room: str = ""
        self.role: str = "user"
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._on_packet: Optional[Callable[[Packet], None]] = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def ws_url(self) -> str:
        return f"http://{self.host}:{self.port}/ws"

    # ── connection ──

    async def connect(self) -> None:
        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(self.ws_url)
        self._connected = True
        logger.info("Connected to CLARA server at %s", self.ws_url)

    async def close(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            self._listener_task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._session:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None
        self._connected = False

    # ── send / receive ──

    async def send_packet(self, pkt: Packet) -> None:
        if not self._ws:
            raise ConnectionError("Not connected")
        await self._ws.send_str(pkt.to_json())

    async def recv_packet(self) -> Optional[Packet]:
        if not self._ws:
            return None
        try:
            msg = await self._ws.receive()
            if msg.type == aiohttp.WSMsgType.TEXT:
                return Packet.from_json(msg.data)
            if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                self._connected = False
                return None
        except Exception:
            self._connected = False
        return None

    # ── listener ──

    def start_listener(self, callback: Callable[[Packet], None]) -> None:
        self._on_packet = callback
        loop = asyncio.get_event_loop()
        self._listener_task = loop.create_task(self._listen())

    async def _listen(self) -> None:
        while self._connected and self._ws:
            pkt = await self.recv_packet()
            if pkt is None:
                break
            if self._on_packet:
                self._on_packet(pkt)

    # ── auth convenience ──

    async def register(self, username: str, password: str) -> Packet:
        pkt = Packet(action=Action.REGISTER, sender=username, data={"password": password})
        await self.send_packet(pkt)
        resp = await self.recv_packet()
        if resp and resp.action == Action.AUTH_OK:
            self.username = username
            self.role = resp.data.get("role", "user")
        return resp or Packet.error("No response")

    async def login(self, username: str, password: str) -> Packet:
        pkt = Packet(action=Action.LOGIN, sender=username, data={"password": password})
        await self.send_packet(pkt)
        resp = await self.recv_packet()
        if resp and resp.action == Action.AUTH_OK:
            self.username = username
            self.role = resp.data.get("role", "user")
        return resp or Packet.error("No response")

    # ── room convenience ──

    async def join_room(self, room: str) -> None:
        await self.send_packet(Packet(action=Action.JOIN, room=room))
        self.room = room

    async def leave_room(self) -> None:
        await self.send_packet(Packet(action=Action.LEAVE))
        self.room = ""

    async def create_room(self, name: str) -> None:
        await self.send_packet(Packet(action=Action.CREATE_ROOM, content=name))

    async def list_rooms(self) -> None:
        await self.send_packet(Packet(action=Action.LIST_ROOMS))

    async def list_users(self) -> None:
        await self.send_packet(Packet(action=Action.LIST_USERS, room=self.room))

    # ── messaging ──

    async def send_message(self, text: str) -> None:
        await self.send_packet(Packet(action=Action.MESSAGE, content=text, room=self.room))

    async def send_dm(self, target: str, text: str) -> None:
        await self.send_packet(Packet(action=Action.DM, target=target, content=text))

    async def edit_message(self, msg_id: int, new_content: str) -> None:
        await self.send_packet(Packet(action=Action.EDIT, msg_id=msg_id, content=new_content))

    async def delete_message(self, msg_id: int) -> None:
        await self.send_packet(Packet(action=Action.DELETE, msg_id=msg_id))

    async def search(self, query: str) -> None:
        await self.send_packet(Packet(action=Action.SEARCH, content=query))

    # ── voice ──

    async def call_user(self, target: str) -> None:
        await self.send_packet(Packet(action=Action.CALL, target=target))

    async def accept_call(self, caller: str) -> None:
        await self.send_packet(Packet(action=Action.CALL_ACCEPT, target=caller))

    async def reject_call(self, caller: str) -> None:
        await self.send_packet(Packet(action=Action.CALL_REJECT, target=caller))

    async def hangup(self) -> None:
        await self.send_packet(Packet(action=Action.CALL_END))

    async def voice_join(self, room: str = "") -> None:
        await self.send_packet(Packet(action=Action.VOICE_JOIN, room=room or self.room))

    async def voice_leave(self) -> None:
        await self.send_packet(Packet(action=Action.VOICE_LEAVE, room=self.room))

    async def mute(self) -> None:
        await self.send_packet(Packet(action=Action.MUTE))

    async def unmute(self) -> None:
        await self.send_packet(Packet(action=Action.UNMUTE))

    # ── files ──

    async def upload_file(self, filepath: str) -> None:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        data = base64.b64encode(path.read_bytes()).decode()
        await self.send_packet(Packet(
            action=Action.FILE_UPLOAD,
            data={"filename": path.name, "data": data},
        ))

    async def download_file(self, file_id: str) -> None:
        await self.send_packet(Packet(action=Action.FILE_DOWNLOAD, content=file_id))

    async def list_files(self) -> None:
        await self.send_packet(Packet(action=Action.FILE_LIST, room=self.room))

    # ── AI ──

    async def ai_enable(self, provider: str = "openai") -> None:
        await self.send_packet(Packet(action=Action.AI_ENABLE, content=provider))

    async def ai_ask(self, question: str) -> None:
        await self.send_packet(Packet(action=Action.AI_ASK, content=question))

    async def ai_summarize(self) -> None:
        await self.send_packet(Packet(action=Action.AI_SUMMARIZE))

    async def ai_usage(self) -> None:
        await self.send_packet(Packet(action=Action.AI_USAGE))

    async def ai_budget(self, amount: float) -> None:
        await self.send_packet(Packet(action=Action.AI_BUDGET, content=str(amount)))

    async def ai_limit(self, limit: int) -> None:
        await self.send_packet(Packet(action=Action.AI_LIMIT, content=str(limit)))

    # ── moderation ──

    async def kick(self, target: str) -> None:
        await self.send_packet(Packet(action=Action.KICK, target=target))

    async def ban(self, target: str) -> None:
        await self.send_packet(Packet(action=Action.BAN, target=target))

    async def unban(self, target: str) -> None:
        await self.send_packet(Packet(action=Action.UNBAN, target=target))

    async def mute_user(self, target: str) -> None:
        await self.send_packet(Packet(action=Action.MUTE_USER, target=target))

    async def unmute_user(self, target: str) -> None:
        await self.send_packet(Packet(action=Action.UNMUTE_USER, target=target))

    async def promote_admin(self, target: str) -> None:
        await self.send_packet(Packet(action=Action.ADMIN, target=target))

    # ── whoami ──

    async def whoami(self) -> None:
        await self.send_packet(Packet(action=Action.WHOAMI))
