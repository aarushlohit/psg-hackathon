"""CLARA server — voice signaling (WebRTC relay + voice rooms)."""

import logging
from dataclasses import dataclass, field
from typing import Optional

from clara.database.db import ClaraDB
from clara.server.protocol import Action, Packet

logger = logging.getLogger("clara.voice")


@dataclass
class VoiceCall:
    session_id: int = 0
    caller: str = ""
    callee: str = ""
    accepted: bool = False


@dataclass
class VoiceRoom:
    room: str = ""
    members: set[str] = field(default_factory=set)


class VoiceService:
    """Manages P2P calls, voice rooms, and WebRTC signaling relay."""

    def __init__(self, db: ClaraDB) -> None:
        self.db = db
        self._calls: dict[str, VoiceCall] = {}
        self._voice_rooms: dict[str, VoiceRoom] = {}

    # ── P2P calls ──

    def initiate_call(self, caller: str, callee: str, session_id: int) -> VoiceCall:
        call = VoiceCall(session_id=session_id, caller=caller, callee=callee)
        self._calls[caller] = call
        return call

    def accept_call(self, caller: str) -> Optional[VoiceCall]:
        call = self._calls.get(caller)
        if call:
            call.accepted = True
        return call

    def reject_call(self, caller: str) -> Optional[VoiceCall]:
        return self._calls.pop(caller, None)

    def end_call(self, username: str) -> Optional[VoiceCall]:
        call = self._calls.pop(username, None)
        if call is None:
            for k, v in list(self._calls.items()):
                if v.callee == username:
                    return self._calls.pop(k, None)
        return call

    # ── voice rooms ──

    def join_voice_room(self, room: str, username: str) -> VoiceRoom:
        if room not in self._voice_rooms:
            self._voice_rooms[room] = VoiceRoom(room=room)
        vr = self._voice_rooms[room]
        vr.members.add(username)
        return vr

    def leave_voice_room(self, room: str, username: str) -> Optional[VoiceRoom]:
        vr = self._voice_rooms.get(room)
        if vr:
            vr.members.discard(username)
            if not vr.members:
                del self._voice_rooms[room]
                return None
        return vr

    def get_user_voice_rooms(self, username: str) -> list[str]:
        return [r for r, vr in self._voice_rooms.items() if username in vr.members]

    def remove_user(self, username: str) -> None:
        self._calls.pop(username, None)
        for k, v in list(self._calls.items()):
            if v.callee == username:
                del self._calls[k]
        for room in list(self._voice_rooms):
            self.leave_voice_room(room, username)

    # ── handlers ──

    async def handle_call(self, client, pkt: Packet, get_client_fn) -> None:
        callee = pkt.target.strip()
        if not callee:
            await client.send(Packet.error("Usage: call <user>"))
            return
        target = get_client_fn(callee)
        if not target:
            await client.send(Packet.error(f"{callee} is not online."))
            return
        sid = self.db.create_voice_session(client.username, callee)
        self.initiate_call(client.username, callee, sid)
        await target.send(Packet(action=Action.CALL, sender=client.username,
                                  target=callee, data={"session_id": sid}))
        await client.send(Packet.ok(f"Calling {callee}..."))
        logger.info("%s calling %s (session=%d)", client.username, callee, sid)

    async def handle_call_accept(self, client, pkt: Packet, get_client_fn) -> None:
        caller = pkt.target.strip()
        call = self.accept_call(caller)
        if not call:
            await client.send(Packet.error("No pending call."))
            return
        caller_client = get_client_fn(caller)
        if caller_client:
            await caller_client.send(Packet(action=Action.CALL_ACCEPT, sender=client.username))
        await client.send(Packet.ok(f"Call with {caller} accepted."))
        logger.info("%s accepted call from %s", client.username, caller)

    async def handle_call_reject(self, client, pkt: Packet, get_client_fn) -> None:
        caller = pkt.target.strip()
        call = self.reject_call(caller)
        if call:
            caller_client = get_client_fn(caller)
            if caller_client:
                await caller_client.send(Packet(action=Action.CALL_REJECT,
                                                 sender=client.username, content="Call rejected."))
            self.db.end_voice_session(call.session_id)
        await client.send(Packet.ok("Call rejected."))

    async def handle_call_end(self, client, pkt: Packet, get_client_fn) -> None:
        call = self.end_call(client.username)
        if call:
            other = call.callee if call.caller == client.username else call.caller
            other_client = get_client_fn(other)
            if other_client:
                await other_client.send(Packet(action=Action.CALL_END,
                                                sender=client.username, content="Call ended."))
            self.db.end_voice_session(call.session_id)
        await client.send(Packet.ok("Call ended."))

    async def handle_voice_join(self, client, pkt: Packet, broadcast_fn) -> None:
        room = pkt.room or client.room
        if not room:
            await client.send(Packet.error("Specify a room."))
            return
        vr = self.join_voice_room(room, client.username)
        await broadcast_fn(room, Packet.system(f"{client.username} joined voice in #{room}.", room=room))
        await client.send(Packet.ok(f"Joined voice in #{room}. Members: {', '.join(vr.members)}"))
        logger.info("%s joined voice room %s", client.username, room)

    async def handle_voice_leave(self, client, pkt: Packet, broadcast_fn) -> None:
        room = pkt.room or client.room
        if not room:
            await client.send(Packet.error("Not in a voice room."))
            return
        self.leave_voice_room(room, client.username)
        await broadcast_fn(room, Packet.system(f"{client.username} left voice.", room=room))
        await client.send(Packet.ok("Left voice channel."))

    async def handle_voice_signal(self, client, pkt: Packet, get_client_fn) -> None:
        target = get_client_fn(pkt.target.strip())
        if target:
            pkt.sender = client.username
            await target.send(pkt)
        else:
            await client.send(Packet.error(f"{pkt.target} not found."))

    async def handle_mute(self, client, pkt: Packet, broadcast_fn) -> None:
        for room in self.get_user_voice_rooms(client.username):
            await broadcast_fn(room, Packet.system(f"{client.username} muted.", room=room))
        await client.send(Packet.ok("Muted."))

    async def handle_unmute(self, client, pkt: Packet, broadcast_fn) -> None:
        for room in self.get_user_voice_rooms(client.username):
            await broadcast_fn(room, Packet.system(f"{client.username} unmuted.", room=room))
        await client.send(Packet.ok("Unmuted."))
