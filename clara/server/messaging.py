"""CLARA server — messaging (rooms, DMs, edit, delete, search, history)."""

import logging

from clara.database.db import ClaraDB
from clara.server.protocol import Action, Packet

logger = logging.getLogger("clara.messages")


class MessagingService:
    """Handles message send / DM / edit / delete / search / history."""

    def __init__(self, db: ClaraDB) -> None:
        self.db = db

    async def handle_message(self, client, pkt: Packet, broadcast_fn) -> None:
        if not client.room:
            await client.send(Packet.error("Join a room first."))
            return
        content = pkt.content.strip()
        if not content:
            return
        msg = self.db.store_message(client.username, client.room, content)
        broadcast = Packet(
            action=Action.MESSAGE, sender=client.username, room=client.room,
            content=content, msg_id=msg.id, timestamp=msg.timestamp,
        )
        await broadcast_fn(client.room, broadcast)

    async def handle_dm(self, client, pkt: Packet, get_client_fn) -> None:
        target = pkt.target.strip()
        content = pkt.content.strip()
        if not target or not content:
            await client.send(Packet.error("Usage: msg <user> <message>"))
            return
        msg = self.db.store_message(client.username, "", content, recipient=target)
        dm_pkt = Packet(
            action=Action.DM, sender=client.username, target=target,
            content=content, msg_id=msg.id, timestamp=msg.timestamp,
        )
        recipient = get_client_fn(target)
        if recipient:
            await recipient.send(dm_pkt)
        await client.send(dm_pkt)

    async def handle_reply(self, client, pkt: Packet, broadcast_fn) -> None:
        """Reply to a message — stores as a regular message with reply context."""
        reply_to = pkt.msg_id
        content = pkt.content.strip()
        if not reply_to or not content:
            await client.send(Packet.error("Usage: reply <msg_id> <message>"))
            return
        if not client.room:
            await client.send(Packet.error("Join a room first."))
            return
        msg = self.db.store_message(client.username, client.room, content)
        broadcast = Packet(
            action=Action.MESSAGE, sender=client.username, room=client.room,
            content=content, msg_id=msg.id, timestamp=msg.timestamp,
            data={"reply_to": reply_to},
        )
        await broadcast_fn(client.room, broadcast)

    async def handle_edit(self, client, pkt: Packet, broadcast_fn) -> None:
        msg_id = pkt.msg_id
        new_content = pkt.content.strip()
        if not msg_id or not new_content:
            await client.send(Packet.error("Usage: edit <msg_id> <new_content>"))
            return
        if self.db.edit_message(msg_id, client.username, new_content):
            edit_pkt = Packet(
                action=Action.EDIT, sender=client.username, room=client.room,
                msg_id=msg_id, content=new_content,
            )
            if client.room:
                await broadcast_fn(client.room, edit_pkt)
            else:
                await client.send(Packet.ok("Message edited."))
        else:
            await client.send(Packet.error("Cannot edit that message."))

    async def handle_delete(self, client, pkt: Packet, broadcast_fn) -> None:
        msg_id = pkt.msg_id
        if not msg_id:
            await client.send(Packet.error("Usage: delete <msg_id>"))
            return
        if self.db.delete_message(msg_id, client.username):
            del_pkt = Packet(action=Action.DELETE, sender=client.username,
                              room=client.room, msg_id=msg_id)
            if client.room:
                await broadcast_fn(client.room, del_pkt)
            else:
                await client.send(Packet.ok("Message deleted."))
        else:
            await client.send(Packet.error("Cannot delete that message."))

    async def handle_search(self, client, pkt: Packet) -> None:
        query = pkt.content.strip()
        if not client.room:
            await client.send(Packet.error("Join a room to search."))
            return
        msgs = self.db.search_messages(client.room, query)
        msg_data = [{"id": m.id, "sender": m.sender, "content": m.content,
                      "timestamp": m.timestamp} for m in msgs]
        await client.send(Packet(action=Action.MSG_LIST, room=client.room,
                                  data={"messages": msg_data, "query": query}))

    async def handle_history(self, client, pkt: Packet) -> None:
        room = pkt.room or client.room
        if not room:
            await client.send(Packet.error("Specify a room."))
            return
        msgs = self.db.get_recent_messages(room)
        msg_data = [{"id": m.id, "sender": m.sender, "content": m.content,
                      "timestamp": m.timestamp} for m in msgs]
        await client.send(Packet(action=Action.MSG_LIST, room=room, data={"messages": msg_data}))
