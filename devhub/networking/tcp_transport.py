"""Async TCP transport layer for CLARA chat — designed for future WebSocket upgrade."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Awaitable, Optional

from devhub.networking.protocol import (
    ClaraMessage,
    MessageType,
    MESSAGE_DELIMITER,
    decode_message,
    encode_message,
)

logger = logging.getLogger(__name__)

# Type alias for the handler callback the server uses per-message.
MessageHandler = Callable[[ClaraMessage, "ClientConnection"], Awaitable[None]]


class ClientConnection:
    """Wraps a single connected client's reader/writer pair."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        username: str = "",
        room: str = "",
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.username = username
        self.room = room
        addr = writer.get_extra_info("peername")
        self.address: str = f"{addr[0]}:{addr[1]}" if addr else "unknown"

    async def send(self, msg: ClaraMessage) -> None:
        """Send a protocol message to this client."""
        try:
            self.writer.write(encode_message(msg))
            await self.writer.drain()
        except (ConnectionError, OSError) as exc:
            logger.warning("Send failed to %s: %s", self.address, exc)

    async def read_messages(self) -> asyncio.AsyncIterator:
        """Yield ClaraMessage objects until the connection drops."""
        buffer = b""
        try:
            while True:
                chunk = await self.reader.read(4096)
                if not chunk:
                    break
                buffer += chunk
                while MESSAGE_DELIMITER in buffer:
                    line, buffer = buffer.split(MESSAGE_DELIMITER, 1)
                    if not line:
                        continue
                    msg = decode_message(line)
                    if msg is not None:
                        yield msg
        except (ConnectionError, asyncio.CancelledError):
            pass

    def close(self) -> None:
        """Close the underlying writer."""
        try:
            self.writer.close()
        except Exception:
            pass


class TCPServer:
    """Async TCP server managing multiple client connections."""

    def __init__(self, host: str, port: int, handler: MessageHandler) -> None:
        self.host = host
        self.port = port
        self._handler = handler
        self._clients: dict[str, ClientConnection] = {}
        self._server: Optional[asyncio.AbstractServer] = None

    async def start(self) -> None:
        """Start listening for connections."""
        self._server = await asyncio.start_server(self._on_connect, self.host, self.port)
        logger.info("CLARA TCP server listening on %s:%s", self.host, self.port)

    async def stop(self) -> None:
        """Shut down server and all client connections."""
        for client in list(self._clients.values()):
            client.close()
        self._clients.clear()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        logger.info("CLARA TCP server stopped")

    async def broadcast(self, msg: ClaraMessage, room: str, exclude: str = "") -> None:
        """Send *msg* to all clients in *room*, optionally excluding one address."""
        for client in list(self._clients.values()):
            if client.room == room and client.address != exclude:
                await client.send(msg)

    def get_users_in_room(self, room: str) -> list[str]:
        """Return usernames currently in *room*."""
        return [c.username for c in self._clients.values() if c.room == room and c.username]

    # ---- private ----

    async def _on_connect(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        client = ClientConnection(reader, writer)
        self._clients[client.address] = client
        logger.info("Client connected: %s", client.address)
        try:
            async for msg in client.read_messages():
                # Track user/room on join.
                if msg.type == MessageType.JOIN:
                    client.username = msg.user
                    client.room = msg.room
                await self._handler(msg, client)
        finally:
            self._clients.pop(client.address, None)
            client.close()
            logger.info("Client disconnected: %s", client.address)


class TCPClient:
    """Async TCP client for connecting to a CLARA server."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._conn: Optional[ClientConnection] = None

    @property
    def connected(self) -> bool:
        return self._conn is not None

    async def connect(self) -> None:
        """Open connection to the CLARA server."""
        reader, writer = await asyncio.open_connection(self.host, self.port)
        self._conn = ClientConnection(reader, writer)
        logger.info("Connected to CLARA server at %s:%s", self.host, self.port)

    async def send(self, msg: ClaraMessage) -> None:
        """Send a message to the server."""
        if self._conn is None:
            raise ConnectionError("Not connected to server")
        await self._conn.send(msg)

    async def receive(self) -> ClaraMessage | None:
        """Read the next message from the server. Returns None on disconnect."""
        if self._conn is None:
            return None
        buffer = b""
        try:
            while True:
                chunk = await self._conn.reader.read(4096)
                if not chunk:
                    return None
                buffer += chunk
                if MESSAGE_DELIMITER in buffer:
                    line, _ = buffer.split(MESSAGE_DELIMITER, 1)
                    return decode_message(line)
        except (ConnectionError, asyncio.CancelledError):
            return None

    def close(self) -> None:
        """Disconnect from the server."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
