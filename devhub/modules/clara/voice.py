"""CLARA voice signaling — WebRTC negotiation relay over WebSocket.

This module handles the signaling layer (offer/answer/ICE) so that
two peers can establish a direct WebRTC audio stream.
Actual media transport happens peer-to-peer via aiortc on the client side.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class VoiceCall:
    """Active voice call or room session."""
    session_id: int = 0
    caller: str = ""
    callee: str = ""
    room: str = ""
    accepted: bool = False
    session_type: str = "p2p"  # p2p | room


@dataclass
class VoiceRoom:
    """A voice channel inside a room."""
    room: str = ""
    members: set[str] = field(default_factory=set)


class VoiceSignaling:
    """Manages active calls and voice room membership."""

    def __init__(self) -> None:
        self._calls: dict[str, VoiceCall] = {}      # caller -> VoiceCall
        self._voice_rooms: dict[str, VoiceRoom] = {}  # room -> VoiceRoom

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
        """End a call by either party."""
        call = self._calls.pop(username, None)
        if call is None:
            # Check if user is the callee
            for k, v in list(self._calls.items()):
                if v.callee == username:
                    return self._calls.pop(k, None)
        return call

    def get_call(self, username: str) -> Optional[VoiceCall]:
        call = self._calls.get(username)
        if call:
            return call
        for v in self._calls.values():
            if v.callee == username:
                return v
        return None

    # ── Voice rooms ──

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

    def get_voice_room(self, room: str) -> Optional[VoiceRoom]:
        return self._voice_rooms.get(room)

    def get_user_voice_rooms(self, username: str) -> list[str]:
        return [r for r, vr in self._voice_rooms.items() if username in vr.members]

    # ── cleanup ──

    def remove_user(self, username: str) -> None:
        """Remove user from all calls and voice rooms."""
        self._calls.pop(username, None)
        for k, v in list(self._calls.items()):
            if v.callee == username:
                del self._calls[k]
        for room in list(self._voice_rooms):
            self.leave_voice_room(room, username)
