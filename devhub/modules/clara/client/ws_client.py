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
        # reconnect state
        self._password: str = ""
        self._shutdown: bool = False
        self._reconnecting: bool = False
        self._max_retries: int = 3   # 3 attempts: 2 s, 4 s, 8 s  (~14 s total)
        self._heartbeat_task: Optional[asyncio.Task] = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def ws_url(self) -> str:
        return f"http://{self.host}:{self.port}/ws"

    # ── connection ──

    async def connect(self) -> None:
        if self._connected:
            return  # Already connected — no-op to prevent session leak
        self._shutdown = False  # fresh connect clears any prior shutdown
        await self._close_transport()  # clean up any stale socket
        self._session = aiohttp.ClientSession()
        try:
            self._ws = await self._session.ws_connect(self.ws_url)
        except Exception:
            await self._session.close()
            self._session = None
            raise
        self._connected = True
        logger.info("Connected to CLARA server at %s", self.ws_url)

    async def close(self) -> None:
        self._shutdown = True  # prevent auto-reconnect on intentional close
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
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

    async def _close_transport(self) -> None:
        """Close only the WS socket and HTTP session (not the listener task)."""
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
            if msg.type in (
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.CLOSING,
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.ERROR,
            ):
                self._connected = False
                return None
        except Exception:
            self._connected = False
        return None

    # ── listener ──

    def start_listener(
        self,
        callback: Callable[[Packet], None],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Schedule the listener and heartbeat tasks on *loop*.

        Must be called before ``loop.run_forever()`` so the tasks are queued
        and start running as soon as the loop begins.
        """
        self._on_packet = callback
        self._listener_task = loop.create_task(self._listen())
        self._heartbeat_task = loop.create_task(self._heartbeat())

    async def _listen(self) -> None:
        """Persistent receive loop — auto-reconnects when the connection drops."""
        _rapid_failures = 0          # consecutive drops within grace period
        _MAX_RAPID = 3               # give up after this many instant drops
        _GRACE_SECS = 5.0            # must survive this long to reset counter

        while True:
            _connected_at = asyncio.get_event_loop().time()

            # ── inner receive loop ──
            try:
                while self._connected and self._ws:
                    pkt = await self.recv_packet()
                    if pkt is None:
                        break
                    if self._on_packet:
                        self._on_packet(pkt)
            except asyncio.CancelledError:
                self._connected = False
                raise  # close() cancelled us — exit cleanly
            finally:
                self._connected = False

            # ── reconnect? ──
            # Only reconnect if we have stored credentials and weren't shut down
            if self._shutdown or not self.username or not self._password:
                break

            # Detect rapid connect-then-drop cycles
            alive = asyncio.get_event_loop().time() - _connected_at
            if alive < _GRACE_SECS:
                _rapid_failures += 1
            else:
                _rapid_failures = 0

            if _rapid_failures >= _MAX_RAPID:
                if self._on_packet:
                    self._on_packet(Packet(
                        action=Action.SYSTEM,
                        content="Connection keeps dropping immediately — giving up. "
                                "Use [bold]connect[/bold] to retry manually.",
                    ))
                break

            reconnected = await self._reconnect_loop()
            if not reconnected:
                break
            # Reconnect succeeded — outer loop resumes listening

    async def _reconnect_loop(self) -> bool:
        """Try to reconnect with exponential back-off. Returns True on success."""
        if self._reconnecting:
            return False
        self._reconnecting = True
        delay = 2  # start at 2 s; doubles each attempt (2 → 4 → 8)
        try:
            for attempt in range(1, self._max_retries + 1):
                if self._shutdown:
                    return False

                if self._on_packet:
                    self._on_packet(Packet(
                        action=Action.SYSTEM,
                        content=f"Connection lost — reconnecting "
                                f"({attempt}/{self._max_retries})…",
                    ))

                try:
                    await self._close_transport()
                    self._session = aiohttp.ClientSession()
                    self._ws = await self._session.ws_connect(self.ws_url)
                    self._connected = True

                    # Re-authenticate with stored credentials
                    resp = await self.login(self.username, self._password)
                    if resp.action != Action.AUTH_OK:
                        resp = await self.register(self.username, self._password)

                    if resp.action == Action.AUTH_OK:
                        # Re-join previous room if any
                        if self.room:
                            await self.join_room(self.room)
                        # Stabilise the WS before restarting listener/heartbeat
                        await asyncio.sleep(0.5)
                        # Cancel stale heartbeat and start a fresh one
                        if self._heartbeat_task and not self._heartbeat_task.done():
                            self._heartbeat_task.cancel()
                        self._heartbeat_task = asyncio.ensure_future(self._heartbeat())
                        if self._on_packet:
                            room_tag = f"  ·  #{self.room}" if self.room else ""
                            self._on_packet(Packet(
                                action=Action.SYSTEM,
                                content=f"Reconnected as {self.username}{room_tag}",
                            ))
                        logger.info("Reconnected to %s as %s", self.ws_url, self.username)
                        return True
                    else:
                        self._connected = False
                        await self._close_transport()
                        raise ConnectionError(f"Re-auth failed: {resp.content}")

                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "Reconnect attempt %d/%d failed: %s",
                        attempt, self._max_retries, exc,
                    )
                    self._connected = False
                    await self._close_transport()

                    if attempt < self._max_retries and not self._shutdown:
                        if self._on_packet:
                            self._on_packet(Packet(
                                action=Action.SYSTEM,
                                content=f"Reconnect failed — retrying in {delay}s…",
                            ))
                        await asyncio.sleep(delay)
                        delay = min(delay * 2, 30)  # cap at 30 s

            # All retries exhausted
            if self._on_packet:
                self._on_packet(Packet(
                    action=Action.SYSTEM,
                    content=f"Could not reconnect after {self._max_retries} attempts. "
                            "Use [bold]connect[/bold] to retry manually.",
                ))
            return False
        finally:
            self._reconnecting = False

    async def _heartbeat(self, interval: int = 20) -> None:
        """Send periodic WebSocket pings to prevent server-side timeouts."""
        while self._connected and self._ws and not self._ws.closed:
            await asyncio.sleep(interval)
            if self._connected and self._ws and not self._ws.closed:
                try:
                    await self._ws.ping()
                except Exception:
                    self._connected = False
                    break

    # ── auth convenience ──

    async def register(self, username: str, password: str) -> Packet:
        pkt = Packet(action=Action.REGISTER, sender=username, data={"password": password})
        await self.send_packet(pkt)
        resp = await self.recv_packet()
        if resp and resp.action == Action.AUTH_OK:
            self.username = username
            self._password = password  # store for auto-reconnect
            self.role = resp.data.get("role", "user")
        return resp or Packet.error("No response")

    async def login(self, username: str, password: str) -> Packet:
        pkt = Packet(action=Action.LOGIN, sender=username, data={"password": password})
        await self.send_packet(pkt)
        resp = await self.recv_packet()
        if resp and resp.action == Action.AUTH_OK:
            self.username = username
            self._password = password  # store for auto-reconnect
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
