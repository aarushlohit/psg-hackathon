"""CLARA server — FastAPI + WebSocket hub.

Handles auth, chat, rooms, DMs, voice signaling, file transfer, AI, and moderation.
Run with:  python -m devhub.modules.clara.server.app
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from pathlib import Path
from typing import Optional

from devhub.modules.clara.ai_gateway import AIGateway
from devhub.modules.clara.database import ClaraDatabase
from devhub.modules.clara.file_service import (
    generate_file_id,
    read_file_b64,
    save_uploaded_file,
)
from devhub.modules.clara.protocol import Action, Packet
from devhub.modules.clara.voice import VoiceSignaling

logger = logging.getLogger(__name__)


class ConnectedClient:
    """Represents one WebSocket client."""

    def __init__(self, websocket: object, username: str = "", room: str = "") -> None:
        self.ws = websocket
        self.username = username
        self.room = room
        self.authenticated = False
        self.role = "user"
        self.muted = False

    async def send(self, pkt: Packet) -> None:
        try:
            await self.ws.send_text(pkt.to_json())  # type: ignore[union-attr]
        except Exception:
            pass


class ClaraHub:
    """Core server logic — protocol-level message routing."""

    def __init__(self, db: ClaraDatabase) -> None:
        self.db = db
        self.clients: dict[str, ConnectedClient] = {}  # username -> client
        self.voice = VoiceSignaling()
        self.ai = AIGateway()
        self._rate_limits: dict[str, list[float]] = {}

    # ── connection lifecycle ──

    async def on_connect(self, ws: object) -> ConnectedClient:
        client = ConnectedClient(ws)
        return client

    async def on_disconnect(self, client: ConnectedClient) -> None:
        if client.username:
            # Notify rooms
            if client.room:
                await self._broadcast_to_room(
                    client.room,
                    Packet.system(f"{client.username} disconnected.", room=client.room),
                    exclude=client.username,
                )
                self.db.leave_room(client.room, client.username)
            self.voice.remove_user(client.username)
            self.clients.pop(client.username, None)

    # ── rate limiting ──

    def _check_rate_limit(self, username: str, max_per_sec: int = 10) -> bool:
        now = time.time()
        timestamps = self._rate_limits.setdefault(username, [])
        timestamps[:] = [t for t in timestamps if now - t < 1.0]
        if len(timestamps) >= max_per_sec:
            return False
        timestamps.append(now)
        return True

    # ── main dispatch ──

    async def handle_packet(self, client: ConnectedClient, pkt: Packet) -> None:
        action = pkt.action

        # Auth actions don't require authentication
        if action in (Action.REGISTER, Action.LOGIN):
            await self._handle_auth(client, pkt)
            return

        if not client.authenticated:
            await client.send(Packet.error("Not authenticated. Login first."))
            return

        if not self._check_rate_limit(client.username):
            await client.send(Packet.error("Rate limited. Slow down."))
            return

        handlers = {
            Action.WHOAMI: self._handle_whoami,
            Action.DISCONNECT: self._handle_disconnect_cmd,
            Action.CREATE_ROOM: self._handle_create_room,
            Action.JOIN: self._handle_join,
            Action.LEAVE: self._handle_leave,
            Action.LIST_ROOMS: self._handle_list_rooms,
            Action.LIST_USERS: self._handle_list_users,
            Action.MESSAGE: self._handle_message,
            Action.DM: self._handle_dm,
            Action.EDIT: self._handle_edit,
            Action.DELETE: self._handle_delete,
            Action.SEARCH: self._handle_search,
            Action.HISTORY: self._handle_history,
            Action.CALL: self._handle_call,
            Action.CALL_ACCEPT: self._handle_call_accept,
            Action.CALL_REJECT: self._handle_call_reject,
            Action.CALL_END: self._handle_call_end,
            Action.VOICE_JOIN: self._handle_voice_join,
            Action.VOICE_LEAVE: self._handle_voice_leave,
            Action.VOICE_SIGNAL: self._handle_voice_signal,
            Action.MUTE: self._handle_mute,
            Action.UNMUTE: self._handle_unmute,
            Action.FILE_UPLOAD: self._handle_file_upload,
            Action.FILE_DOWNLOAD: self._handle_file_download,
            Action.FILE_LIST: self._handle_file_list,
            Action.AI_ENABLE: self._handle_ai_enable,
            Action.AI_ASK: self._handle_ai_ask,
            Action.AI_SUMMARIZE: self._handle_ai_summarize,
            Action.AI_USAGE: self._handle_ai_usage,
            Action.AI_BUDGET: self._handle_ai_budget,
            Action.AI_LIMIT: self._handle_ai_limit,
            Action.KICK: self._handle_kick,
            Action.BAN: self._handle_ban,
            Action.UNBAN: self._handle_unban,
            Action.MUTE_USER: self._handle_mute_user,
            Action.UNMUTE_USER: self._handle_unmute_user,
            Action.ADMIN: self._handle_admin,
        }

        handler = handlers.get(action)
        if handler:
            await handler(client, pkt)
        else:
            await client.send(Packet.error(f"Unknown action: {action.value}"))

    # ═══════════════  AUTH  ═══════════════

    async def _handle_auth(self, client: ConnectedClient, pkt: Packet) -> None:
        username = pkt.sender.strip()
        password = pkt.data.get("password", "")

        if not username or not password:
            await client.send(Packet(action=Action.AUTH_FAIL, content="Username and password required."))
            return

        if pkt.action == Action.REGISTER:
            existing = self.db.get_user(username)
            if existing:
                await client.send(Packet(action=Action.AUTH_FAIL, content="Username taken."))
                return
            user = self.db.create_user(username, password)
            client.username = username
            client.authenticated = True
            client.role = user.role
            self.clients[username] = client
            await client.send(Packet(action=Action.AUTH_OK, sender=username,
                                      content=f"Registered as {username}.", data={"role": user.role}))

        elif pkt.action == Action.LOGIN:
            user = self.db.authenticate(username, password)
            if not user:
                await client.send(Packet(action=Action.AUTH_FAIL, content="Invalid credentials or banned."))
                return
            # Kick old session if exists
            old = self.clients.pop(username, None)
            if old:
                await old.send(Packet.system("Session replaced by new login."))
            client.username = username
            client.authenticated = True
            client.role = user.role
            self.clients[username] = client
            await client.send(Packet(action=Action.AUTH_OK, sender=username,
                                      content=f"Welcome back, {username}.", data={"role": user.role}))

    # ═══════════════  CONNECTION  ═══════════════

    async def _handle_whoami(self, client: ConnectedClient, pkt: Packet) -> None:
        await client.send(Packet.ok(
            content=client.username,
            role=client.role,
            room=client.room,
        ))

    async def _handle_disconnect_cmd(self, client: ConnectedClient, pkt: Packet) -> None:
        await client.send(Packet.ok("Disconnected."))

    # ═══════════════  ROOMS  ═══════════════

    async def _handle_create_room(self, client: ConnectedClient, pkt: Packet) -> None:
        name = pkt.content.strip()
        if not name:
            await client.send(Packet.error("Room name required."))
            return
        existing = self.db.get_room(name)
        if existing:
            await client.send(Packet.error(f"Room '{name}' already exists."))
            return
        self.db.create_room(name, client.username)
        await client.send(Packet.ok(f"Room '{name}' created."))

    async def _handle_join(self, client: ConnectedClient, pkt: Packet) -> None:
        room = pkt.room.strip() or pkt.content.strip() or "general"
        # Leave current room silently
        if client.room and client.room != room:
            self.db.leave_room(client.room, client.username)
            await self._broadcast_to_room(
                client.room,
                Packet.system(f"{client.username} left.", room=client.room),
                exclude=client.username,
            )

        db_room = self.db.get_room(room)
        if not db_room:
            # Auto-create room
            self.db.create_room(room, client.username)

        client.room = room
        self.db.join_room(room, client.username)
        await client.send(Packet.ok(f"Joined #{room}.", room=room))
        await self._broadcast_to_room(
            room,
            Packet.system(f"{client.username} joined #{room}.", room=room),
            exclude=client.username,
        )

    async def _handle_leave(self, client: ConnectedClient, pkt: Packet) -> None:
        if not client.room:
            await client.send(Packet.error("Not in a room."))
            return
        room = client.room
        self.db.leave_room(room, client.username)
        await self._broadcast_to_room(
            room,
            Packet.system(f"{client.username} left #{room}.", room=room),
            exclude=client.username,
        )
        client.room = ""
        await client.send(Packet.ok(f"Left #{room}."))

    async def _handle_list_rooms(self, client: ConnectedClient, pkt: Packet) -> None:
        rooms = self.db.list_rooms()
        room_data = [{"name": r.name, "created_by": r.created_by} for r in rooms]
        await client.send(Packet(action=Action.ROOM_LIST, data={"rooms": room_data}))

    async def _handle_list_users(self, client: ConnectedClient, pkt: Packet) -> None:
        room = pkt.room or client.room
        if not room:
            # List all connected users
            users = list(self.clients.keys())
        else:
            users = self.db.get_room_members(room)
        await client.send(Packet(action=Action.USER_LIST, room=room,
                                  data={"users": users}))

    # ═══════════════  MESSAGING  ═══════════════

    async def _handle_message(self, client: ConnectedClient, pkt: Packet) -> None:
        if client.muted:
            await client.send(Packet.error("You are muted."))
            return
        if not client.room:
            await client.send(Packet.error("Join a room first."))
            return
        content = pkt.content.strip()
        if not content:
            return
        msg = self.db.store_message(client.username, client.room, content)
        broadcast = Packet(
            action=Action.MESSAGE,
            sender=client.username,
            room=client.room,
            content=content,
            msg_id=msg.id,
            timestamp=msg.timestamp,
        )
        await self._broadcast_to_room(client.room, broadcast)

    async def _handle_dm(self, client: ConnectedClient, pkt: Packet) -> None:
        target = pkt.target.strip()
        content = pkt.content.strip()
        if not target or not content:
            await client.send(Packet.error("Usage: msg <user> <message>"))
            return
        msg = self.db.store_message(client.username, "", content, recipient=target)
        dm_pkt = Packet(
            action=Action.DM,
            sender=client.username,
            target=target,
            content=content,
            msg_id=msg.id,
            timestamp=msg.timestamp,
        )
        # Send to recipient if online
        recipient = self.clients.get(target)
        if recipient:
            await recipient.send(dm_pkt)
        # Echo back to sender
        await client.send(dm_pkt)

    async def _handle_edit(self, client: ConnectedClient, pkt: Packet) -> None:
        msg_id = pkt.msg_id
        new_content = pkt.content.strip()
        if not msg_id or not new_content:
            await client.send(Packet.error("Usage: edit <msg_id> <new_content>"))
            return
        ok = self.db.edit_message(msg_id, client.username, new_content)
        if ok:
            edit_pkt = Packet(
                action=Action.EDIT,
                sender=client.username,
                room=client.room,
                msg_id=msg_id,
                content=new_content,
            )
            if client.room:
                await self._broadcast_to_room(client.room, edit_pkt)
            else:
                await client.send(Packet.ok("Message edited."))
        else:
            await client.send(Packet.error("Cannot edit that message."))

    async def _handle_delete(self, client: ConnectedClient, pkt: Packet) -> None:
        msg_id = pkt.msg_id
        if not msg_id:
            await client.send(Packet.error("Usage: delete <msg_id>"))
            return
        ok = self.db.delete_message(msg_id, client.username)
        if ok:
            del_pkt = Packet(action=Action.DELETE, sender=client.username,
                              room=client.room, msg_id=msg_id)
            if client.room:
                await self._broadcast_to_room(client.room, del_pkt)
            else:
                await client.send(Packet.ok("Message deleted."))
        else:
            await client.send(Packet.error("Cannot delete that message."))

    async def _handle_search(self, client: ConnectedClient, pkt: Packet) -> None:
        query = pkt.content.strip()
        room = client.room
        if not room:
            await client.send(Packet.error("Join a room to search."))
            return
        msgs = self.db.search_messages(room, query)
        msg_data = [{"id": m.id, "sender": m.sender, "content": m.content,
                      "timestamp": m.timestamp} for m in msgs]
        await client.send(Packet(action=Action.MSG_LIST, room=room,
                                  data={"messages": msg_data, "query": query}))

    async def _handle_history(self, client: ConnectedClient, pkt: Packet) -> None:
        room = pkt.room or client.room
        if not room:
            await client.send(Packet.error("Specify a room."))
            return
        msgs = self.db.get_recent_messages(room)
        msg_data = [{"id": m.id, "sender": m.sender, "content": m.content,
                      "timestamp": m.timestamp} for m in msgs]
        await client.send(Packet(action=Action.MSG_LIST, room=room,
                                  data={"messages": msg_data}))

    # ═══════════════  VOICE  ═══════════════

    async def _handle_call(self, client: ConnectedClient, pkt: Packet) -> None:
        callee = pkt.target.strip()
        if not callee:
            await client.send(Packet.error("Usage: call <user>"))
            return
        target = self.clients.get(callee)
        if not target:
            await client.send(Packet.error(f"{callee} is not online."))
            return
        sid = self.db.create_voice_session(client.username, callee)
        self.voice.initiate_call(client.username, callee, sid)
        await target.send(Packet(action=Action.CALL, sender=client.username,
                                  target=callee, data={"session_id": sid}))
        await client.send(Packet.ok(f"Calling {callee}..."))

    async def _handle_call_accept(self, client: ConnectedClient, pkt: Packet) -> None:
        caller = pkt.target.strip()
        call = self.voice.accept_call(caller)
        if not call:
            await client.send(Packet.error("No pending call."))
            return
        caller_client = self.clients.get(caller)
        if caller_client:
            await caller_client.send(Packet(action=Action.CALL_ACCEPT, sender=client.username))
        await client.send(Packet.ok(f"Call with {caller} accepted."))

    async def _handle_call_reject(self, client: ConnectedClient, pkt: Packet) -> None:
        caller = pkt.target.strip()
        call = self.voice.reject_call(caller)
        if call:
            caller_client = self.clients.get(caller)
            if caller_client:
                await caller_client.send(Packet(action=Action.CALL_REJECT, sender=client.username,
                                                  content="Call rejected."))
            self.db.end_voice_session(call.session_id)
        await client.send(Packet.ok("Call rejected."))

    async def _handle_call_end(self, client: ConnectedClient, pkt: Packet) -> None:
        call = self.voice.end_call(client.username)
        if call:
            other = call.callee if call.caller == client.username else call.caller
            other_client = self.clients.get(other)
            if other_client:
                await other_client.send(Packet(action=Action.CALL_END, sender=client.username,
                                                content="Call ended."))
            self.db.end_voice_session(call.session_id)
        await client.send(Packet.ok("Call ended."))

    async def _handle_voice_join(self, client: ConnectedClient, pkt: Packet) -> None:
        room = pkt.room or client.room
        if not room:
            await client.send(Packet.error("Specify a room."))
            return
        vr = self.voice.join_voice_room(room, client.username)
        await self._broadcast_to_room(
            room,
            Packet.system(f"{client.username} joined voice in #{room}.", room=room),
        )
        await client.send(Packet.ok(f"Joined voice in #{room}. Members: {', '.join(vr.members)}"))

    async def _handle_voice_leave(self, client: ConnectedClient, pkt: Packet) -> None:
        room = pkt.room or client.room
        if not room:
            await client.send(Packet.error("Not in a voice room."))
            return
        self.voice.leave_voice_room(room, client.username)
        await self._broadcast_to_room(
            room,
            Packet.system(f"{client.username} left voice.", room=room),
        )
        await client.send(Packet.ok("Left voice channel."))

    async def _handle_voice_signal(self, client: ConnectedClient, pkt: Packet) -> None:
        """Relay WebRTC signaling data (offer/answer/ICE) to the target peer."""
        target_name = pkt.target.strip()
        target = self.clients.get(target_name)
        if target:
            pkt.sender = client.username
            await target.send(pkt)
        else:
            await client.send(Packet.error(f"{target_name} not found."))

    async def _handle_mute(self, client: ConnectedClient, pkt: Packet) -> None:
        rooms = self.voice.get_user_voice_rooms(client.username)
        for room in rooms:
            await self._broadcast_to_room(
                room, Packet.system(f"{client.username} muted.", room=room),
            )
        await client.send(Packet.ok("Muted."))

    async def _handle_unmute(self, client: ConnectedClient, pkt: Packet) -> None:
        rooms = self.voice.get_user_voice_rooms(client.username)
        for room in rooms:
            await self._broadcast_to_room(
                room, Packet.system(f"{client.username} unmuted.", room=room),
            )
        await client.send(Packet.ok("Unmuted."))

    # ═══════════════  FILE TRANSFER  ═══════════════

    async def _handle_file_upload(self, client: ConnectedClient, pkt: Packet) -> None:
        filename = pkt.data.get("filename", "")
        data_b64 = pkt.data.get("data", "")
        if not filename or not data_b64:
            await client.send(Packet.error("Filename and data required."))
            return
        file_id = generate_file_id()
        try:
            size, sha = save_uploaded_file(file_id, filename, data_b64)
        except (ValueError, Exception) as exc:
            await client.send(Packet.error(str(exc)))
            return
        room = client.room or ""
        self.db.store_file(file_id, filename, client.username, room, size)
        await client.send(Packet.ok(
            f"File uploaded: {filename} ({size} bytes)",
            file_id=file_id,
            sha256=sha,
        ))
        if room:
            await self._broadcast_to_room(
                room,
                Packet.system(f"{client.username} shared file: {filename} (ID: {file_id})", room=room),
                exclude=client.username,
            )

    async def _handle_file_download(self, client: ConnectedClient, pkt: Packet) -> None:
        file_id = pkt.content.strip() or pkt.data.get("file_id", "")
        if not file_id:
            await client.send(Packet.error("File ID required."))
            return
        rec = self.db.get_file(file_id)
        if not rec:
            await client.send(Packet.error("File not found."))
            return
        try:
            data_b64, sha = read_file_b64(file_id)
        except FileNotFoundError:
            await client.send(Packet.error("File data missing."))
            return
        await client.send(Packet(
            action=Action.FILE_DATA,
            data={"file_id": file_id, "filename": rec.filename,
                   "data": data_b64.decode(), "sha256": sha, "size": rec.size},
        ))

    async def _handle_file_list(self, client: ConnectedClient, pkt: Packet) -> None:
        room = pkt.room or client.room or ""
        files = self.db.list_files(room)
        file_data = [{"file_id": f.file_id, "filename": f.filename,
                       "sender": f.sender, "size": f.size} for f in files]
        await client.send(Packet(action=Action.FILE_RECORD_LIST, data={"files": file_data}))

    # ═══════════════  AI  ═══════════════

    async def _handle_ai_enable(self, client: ConnectedClient, pkt: Packet) -> None:
        provider = pkt.content.strip() or "openai"
        result = self.ai.enable(client.username, provider)
        # 2-second billing disclaimer
        await client.send(Packet.system(
            "⚠ AI queries may incur API costs. You control your budget with 'ai budget' and 'ai limit'."
        ))
        await asyncio.sleep(2)
        await client.send(Packet.ok(result))

    async def _handle_ai_ask(self, client: ConnectedClient, pkt: Packet) -> None:
        question = pkt.content.strip()
        if not question:
            await client.send(Packet.error("Usage: ai ask <question>"))
            return
        resp = await self.ai.ask(client.username, question)
        if resp.error:
            await client.send(Packet.error(resp.error))
        else:
            self.db.log_ai_usage(client.username, resp.provider, resp.tokens_used, resp.cost)
            await client.send(Packet(
                action=Action.AI_RESPONSE,
                content=resp.content,
                data={"tokens": resp.tokens_used, "cost": f"${resp.cost:.6f}",
                       "provider": resp.provider},
            ))

    async def _handle_ai_summarize(self, client: ConnectedClient, pkt: Packet) -> None:
        if not client.room:
            await client.send(Packet.error("Join a room first."))
            return
        msgs = self.db.get_recent_messages(client.room, limit=50)
        texts = [f"{m.sender}: {m.content}" for m in msgs]
        resp = await self.ai.summarize(client.username, texts)
        if resp.error:
            await client.send(Packet.error(resp.error))
        else:
            self.db.log_ai_usage(client.username, resp.provider, resp.tokens_used, resp.cost)
            await client.send(Packet(action=Action.AI_RESPONSE, content=resp.content))

    async def _handle_ai_usage(self, client: ConnectedClient, pkt: Packet) -> None:
        usage = self.ai.get_usage(client.username)
        await client.send(Packet.ok(json.dumps(usage), **usage))

    async def _handle_ai_budget(self, client: ConnectedClient, pkt: Packet) -> None:
        try:
            amount = float(pkt.content.strip().replace("$", ""))
        except (ValueError, TypeError):
            await client.send(Packet.error("Usage: ai budget <amount>"))
            return
        result = self.ai.set_budget(client.username, amount)
        await client.send(Packet.ok(result))

    async def _handle_ai_limit(self, client: ConnectedClient, pkt: Packet) -> None:
        try:
            limit = int(pkt.content.strip())
        except (ValueError, TypeError):
            await client.send(Packet.error("Usage: ai limit <number>"))
            return
        result = self.ai.set_limit(client.username, limit)
        await client.send(Packet.ok(result))

    # ═══════════════  MODERATION  ═══════════════

    def _require_mod(self, client: ConnectedClient) -> bool:
        return client.role in ("admin", "moderator")

    async def _handle_kick(self, client: ConnectedClient, pkt: Packet) -> None:
        if not self._require_mod(client):
            await client.send(Packet.error("Permission denied."))
            return
        target_name = pkt.target.strip()
        target = self.clients.get(target_name)
        if target:
            await target.send(Packet.system("You have been kicked."))
            if target.room:
                self.db.leave_room(target.room, target.username)
                await self._broadcast_to_room(
                    target.room,
                    Packet.system(f"{target_name} was kicked by {client.username}.", room=target.room),
                )
            target.room = ""
            await client.send(Packet.ok(f"Kicked {target_name}."))
        else:
            await client.send(Packet.error(f"{target_name} not found."))

    async def _handle_ban(self, client: ConnectedClient, pkt: Packet) -> None:
        if not self._require_mod(client):
            await client.send(Packet.error("Permission denied."))
            return
        target_name = pkt.target.strip()
        self.db.ban_user(target_name)
        target = self.clients.get(target_name)
        if target:
            await target.send(Packet.system("You have been banned."))
        await client.send(Packet.ok(f"Banned {target_name}."))

    async def _handle_unban(self, client: ConnectedClient, pkt: Packet) -> None:
        if not self._require_mod(client):
            await client.send(Packet.error("Permission denied."))
            return
        target_name = pkt.target.strip()
        self.db.unban_user(target_name)
        await client.send(Packet.ok(f"Unbanned {target_name}."))

    async def _handle_mute_user(self, client: ConnectedClient, pkt: Packet) -> None:
        if not self._require_mod(client):
            await client.send(Packet.error("Permission denied."))
            return
        target_name = pkt.target.strip()
        target = self.clients.get(target_name)
        if target:
            target.muted = True
            await target.send(Packet.system("You have been muted by a moderator."))
            await client.send(Packet.ok(f"Muted {target_name}."))
        else:
            await client.send(Packet.error(f"{target_name} not found."))

    async def _handle_unmute_user(self, client: ConnectedClient, pkt: Packet) -> None:
        if not self._require_mod(client):
            await client.send(Packet.error("Permission denied."))
            return
        target_name = pkt.target.strip()
        target = self.clients.get(target_name)
        if target:
            target.muted = False
            await target.send(Packet.system("You have been unmuted."))
            await client.send(Packet.ok(f"Unmuted {target_name}."))
        else:
            await client.send(Packet.error(f"{target_name} not found."))

    async def _handle_admin(self, client: ConnectedClient, pkt: Packet) -> None:
        if client.role != "admin":
            await client.send(Packet.error("Only admins can promote."))
            return
        target_name = pkt.target.strip()
        self.db.set_role(target_name, "admin")
        await client.send(Packet.ok(f"{target_name} promoted to admin."))
        target = self.clients.get(target_name)
        if target:
            target.role = "admin"
            await target.send(Packet.system("You have been promoted to admin."))

    # ═══════════════  BROADCAST HELPER  ═══════════════

    async def _broadcast_to_room(self, room: str, pkt: Packet, exclude: str = "") -> None:
        """Send packet to all clients currently in the given room."""
        for c in list(self.clients.values()):
            if c.room == room and c.username != exclude:
                await c.send(pkt)
