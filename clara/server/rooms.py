"""CLARA server — room management."""

import logging

from clara.database.db import ClaraDB
from clara.server.protocol import Action, Packet

logger = logging.getLogger("clara.messages")


class RoomManager:
    """Handles room creation, joins, leaves, and listing."""

    def __init__(self, db: ClaraDB) -> None:
        self.db = db

    async def handle_create(self, client: "ConnectedClient", pkt: Packet) -> None:
        name = pkt.content.strip()
        if not name:
            await client.send(Packet.error("Room name required."))
            return
        if self.db.get_room(name):
            await client.send(Packet.error(f"Room '{name}' already exists."))
            return
        self.db.create_room(name, client.username)
        await client.send(Packet.ok(f"Room '{name}' created."))

    async def handle_join(self, client: "ConnectedClient", pkt: Packet,
                          broadcast_fn: callable) -> None:
        room = pkt.room.strip() or pkt.content.strip() or "general"
        if client.room and client.room != room:
            self.db.leave_room(client.room, client.username)
            await broadcast_fn(
                client.room,
                Packet.system(f"{client.username} left.", room=client.room),
                exclude=client.username,
            )
        if not self.db.get_room(room):
            self.db.create_room(room, client.username)
        client.room = room
        self.db.join_room(room, client.username)
        await client.send(Packet.ok(f"Joined #{room}.", room=room))
        await broadcast_fn(
            room,
            Packet.system(f"{client.username} joined #{room}.", room=room),
            exclude=client.username,
        )

    async def handle_leave(self, client: "ConnectedClient", pkt: Packet,
                           broadcast_fn: callable) -> None:
        if not client.room:
            await client.send(Packet.error("Not in a room."))
            return
        room = client.room
        self.db.leave_room(room, client.username)
        await broadcast_fn(
            room,
            Packet.system(f"{client.username} left #{room}.", room=room),
            exclude=client.username,
        )
        client.room = ""
        await client.send(Packet.ok(f"Left #{room}."))

    async def handle_list_rooms(self, client: "ConnectedClient", pkt: Packet) -> None:
        rooms = self.db.list_rooms()
        room_data = [{"name": r.name, "created_by": r.created_by} for r in rooms]
        await client.send(Packet(action=Action.ROOM_LIST, data={"rooms": room_data}))

    async def handle_list_users(self, client: "ConnectedClient", pkt: Packet,
                                online_users: list[str]) -> None:
        room = pkt.room or client.room
        if room:
            users = self.db.get_room_members(room)
        else:
            users = online_users
        await client.send(Packet(action=Action.USER_LIST, room=room, data={"users": users}))


# Forward ref resolved at runtime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from clara.server.websocket import ConnectedClient
