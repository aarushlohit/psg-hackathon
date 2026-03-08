"""CLARA module — full-featured terminal communication platform.

Supports: global chat, rooms, DMs, voice calls, file sharing, AI integration,
and moderation. Connects to a CLARA server via WebSocket.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from devhub.modules.base import BaseModule
from devhub.modules.clara.client.ws_client import ClaraWSClient
from devhub.modules.clara.protocol import Action, Packet
from devhub.storage.config import DevHubConfig

logger = logging.getLogger(__name__)
console = Console()


def _ts(ts: float) -> str:
    """Format unix timestamp as HH:MM."""
    return datetime.fromtimestamp(ts).strftime("%H:%M")


class ClaraModule(BaseModule):
    """Interactive CLARA CLI — IRC/Discord in your terminal."""

    name = "clara"
    prompt_label = "[clara]"

    def __init__(self) -> None:
        self._client: Optional[ClaraWSClient] = None
        self._server_thread: Optional[threading.Thread] = None
        self._config = DevHubConfig.load()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._incoming_call_from: str = ""

    # ──────────── lifecycle ────────────

    def enter(self) -> None:
        super().enter()
        console.print(Panel(
            "[bold cyan]CLARA[/bold cyan] — Terminal Communication Platform\n"
            "[dim]Chat · Rooms · DMs · Voice · Files · AI[/dim]\n"
            "Type [bold]help[/bold] for commands.",
            title="CLARA CLI", border_style="cyan",
        ))

    def exit(self) -> None:
        super().exit()
        if self._client and self._client.connected:
            self._run(self._client.close())
            self._client = None

    # ──────────── command dispatch ────────────

    def help(self) -> None:
        sections = [
            ("Server", [
                ("server start", "Start CLARA server on this machine"),
                ("server stop", "Stop the local CLARA server"),
                ("server status", "Show server status"),
            ]),
            ("Connection", [
                ("connect <host> <user>", "Connect and register/login"),
                ("disconnect", "Disconnect from server"),
                ("whoami", "Show current identity"),
            ]),
            ("Rooms", [
                ("create-room <name>", "Create a new room"),
                ("join <room>", "Join a chat room"),
                ("leave", "Leave current room"),
                ("rooms", "List all rooms"),
                ("list", "List users in current room"),
            ]),
            ("Messaging", [
                ("send <message>", "Send message to room"),
                ("msg <user> <message>", "Private message"),
                ("edit <msg_id> <text>", "Edit a message"),
                ("delete <msg_id>", "Delete a message"),
                ("search <text>", "Search messages in room"),
            ]),
            ("Voice", [
                ("call <user>", "Call a user"),
                ("voice join [room]", "Join voice channel"),
                ("voice leave", "Leave voice channel"),
                ("mute", "Mute yourself"),
                ("unmute", "Unmute yourself"),
                ("hangup", "End current call"),
            ]),
            ("File Transfer", [
                ("file send <path>", "Upload a file"),
                ("file receive <id>", "Download a file"),
                ("file list", "List shared files"),
            ]),
            ("AI", [
                ("ai enable [provider]", "Enable AI (openai/claude/openrouter)"),
                ("ai ask <question>", "Ask AI a question"),
                ("ai summarize", "Summarize recent chat"),
                ("ai usage", "Show AI usage stats"),
                ("ai budget <$>", "Set spending limit"),
                ("ai limit <n>", "Set token limit"),
            ]),
            ("Moderation", [
                ("kick <user>", "Kick user from room"),
                ("ban <user>", "Ban user from server"),
                ("mute <user>", "Mute a user"),
                ("admin <user>", "Promote to admin"),
            ]),
        ]
        for title, cmds in sections:
            table = Table(title=title, show_header=True, header_style="bold cyan",
                          title_style="bold white", expand=False)
            table.add_column("Command", style="green", min_width=25)
            table.add_column("Description")
            for cmd, desc in cmds:
                table.add_row(cmd, desc)
            console.print(table)

    def handle(self, command: str) -> None:
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        try:
            match cmd:
                # server
                case "server":
                    self._handle_server(args)
                # connection
                case "connect":
                    self._handle_connect(args)
                case "disconnect":
                    self._handle_disconnect()
                case "whoami":
                    self._cmd_whoami()
                # rooms
                case "create-room":
                    self._cmd_create_room(args)
                case "join":
                    self._cmd_join(args)
                case "leave":
                    self._cmd_leave()
                case "rooms":
                    self._cmd_list_rooms()
                case "list":
                    self._cmd_list_users()
                # messaging
                case "send":
                    self._cmd_send(args)
                case "msg":
                    self._cmd_dm(args)
                case "edit":
                    self._cmd_edit(args)
                case "delete":
                    self._cmd_delete(args)
                case "search":
                    self._cmd_search(args)
                # voice
                case "call":
                    self._cmd_call(args)
                case "voice":
                    self._cmd_voice(args)
                case "mute":
                    if args.strip():
                        self._cmd_mute_user(args)
                    else:
                        self._cmd_mute_self()
                case "unmute":
                    if args.strip():
                        self._cmd_unmute_user(args)
                    else:
                        self._cmd_unmute_self()
                case "hangup":
                    self._cmd_hangup()
                case "accept":
                    self._cmd_accept_call(args)
                case "reject":
                    self._cmd_reject_call(args)
                # files
                case "file":
                    self._cmd_file(args)
                # AI
                case "ai":
                    self._cmd_ai(args)
                # moderation
                case "kick":
                    self._cmd_kick(args)
                case "ban":
                    self._cmd_ban(args)
                case "unban":
                    self._cmd_unban(args)
                case "admin":
                    self._cmd_admin(args)
                # help
                case "help":
                    self.help()
                case "":
                    pass
                case _:
                    # If in a room, treat anything else as a message
                    if self._client and self._client.connected and self._client.room:
                        self._cmd_send(command)
                    else:
                        console.print(f"[yellow]Unknown: {cmd}. Type 'help'.[/yellow]")
        except Exception as exc:
            logger.exception("CLARA error")
            console.print(f"[red]✗ Error:[/red] {exc}")

    # ──────────── helpers ────────────

    def _ensure_connected(self) -> bool:
        if not self._client or not self._client.connected:
            console.print("[red]Not connected. Use: connect <host> <user>[/red]")
            return False
        return True

    def _run(self, coro):
        """Run an async coroutine from sync context."""
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return future.result(timeout=30)
        return asyncio.get_event_loop().run_until_complete(coro)

    # ──────────── server management ────────────

    def _handle_server(self, args: str) -> None:
        sub = args.strip().split()[0].lower() if args.strip() else ""
        if sub == "start":
            if self._server_thread and self._server_thread.is_alive():
                console.print("[yellow]Server is already running.[/yellow]")
                return
            port = self._config.clara_port
            self._server_thread = threading.Thread(
                target=self._run_server_thread, args=(port,), daemon=True,
            )
            self._server_thread.start()
            time.sleep(1)  # Let uvicorn boot
            console.print(f"[green]✓[/green] CLARA server started on 0.0.0.0:{port}")
        elif sub == "stop":
            console.print("[yellow]Server runs in background — will stop with DevHub exit.[/yellow]")
        elif sub == "status":
            if self._server_thread and self._server_thread.is_alive():
                console.print(f"[green]● Server running[/green] on port {self._config.clara_port}")
            else:
                console.print("[dim]● Server not running[/dim]")
        else:
            console.print("[yellow]Usage: server start | stop | status[/yellow]")

    def _run_server_thread(self, port: int) -> None:
        from devhub.modules.clara.server.app import run_server_async
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_server_async("0.0.0.0", port))
        except Exception as exc:
            logger.error("Server error: %s", exc)
        finally:
            loop.close()

    # ──────────── connection ────────────

    def _handle_connect(self, args: str) -> None:
        parts = args.strip().split()
        if len(parts) < 2:
            console.print("[yellow]Usage: connect <host> <username>[/yellow]")
            return
        host, username = parts[0], parts[1]
        password = parts[2] if len(parts) > 2 else ""
        port = self._config.clara_port

        # Guard: prevent double-connect which would leak the old session
        if self._client and self._client.connected:
            console.print(
                f"[yellow]Already connected as [bold]{self._client.username}[/bold]. "
                "Run [bold]disconnect[/bold] first.[/yellow]"
            )
            return

        if not password:
            try:
                password = console.input("[dim]Password: [/dim]", password=True)
            except (EOFError, KeyboardInterrupt):
                return

        self._loop = asyncio.new_event_loop()
        self._client = ClaraWSClient(host, port)

        # Signal auth completion to the main thread
        auth_event = threading.Event()
        auth_result: dict = {"ok": False, "error": ""}

        def _connect_and_listen() -> None:
            asyncio.set_event_loop(self._loop)
            try:
                # Step 1: open WebSocket
                self._loop.run_until_complete(self._client.connect())

                # Step 2: try login; if it fails for any reason, auto-register
                resp = self._loop.run_until_complete(self._client.login(username, password))
                if resp.action != Action.AUTH_OK:
                    resp = self._loop.run_until_complete(
                        self._client.register(username, password)
                    )

                if resp.action == Action.AUTH_OK:
                    auth_result["ok"] = True
                    auth_event.set()  # Unblock main thread before run_forever
                    # Schedule listener + heartbeat then keep loop alive
                    self._client.start_listener(self._on_packet, self._loop)
                    self._loop.run_forever()
                else:
                    auth_result["error"] = resp.content or "Authentication failed"
                    self._loop.run_until_complete(self._client.close())
                    auth_event.set()
            except Exception as exc:
                logger.exception("CLARA connect error")
                auth_result["error"] = str(exc)
                try:
                    self._loop.run_until_complete(self._client.close())
                except Exception:
                    pass
                auth_event.set()
            finally:
                # Loop has stopped (disconnect) or auth failed — clean up
                if not self._loop.is_closed():
                    self._loop.close()

        t = threading.Thread(target=_connect_and_listen, daemon=True)
        t.start()

        # Block until auth resolves (up to 10 s) rather than sleeping blindly
        if not auth_event.wait(timeout=10):
            console.print("[red]✗ Connection timed out.[/red]")
            self._client = None
            self._loop = None
            return

        if auth_result["ok"]:
            console.print(
                f"[green]✓[/green] Connected as [bold]{username}[/bold] to {host}:{port}"
                f"  [dim](role: {self._client.role})[/dim]"
            )
        else:
            console.print(f"[red]✗ Connection failed:[/red] {auth_result['error']}")
            self._client = None
            self._loop = None

    def _handle_disconnect(self) -> None:
        if not self._client or not self._client.connected:
            console.print("[yellow]Not connected.[/yellow]")
            return
        if self._loop and self._loop.is_running():
            # Wait for clean close before stopping the loop
            future = asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
            try:
                future.result(timeout=5)
            except Exception:
                pass
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._client = None
        self._loop = None
        console.print("[green]\u2713[/green] Disconnected.")

    def _cmd_whoami(self) -> None:
        if not self._ensure_connected():
            return
        asyncio.run_coroutine_threadsafe(self._client.whoami(), self._loop)

    # ──────────── rooms ────────────

    def _cmd_create_room(self, args: str) -> None:
        if not self._ensure_connected():
            return
        name = args.strip()
        if not name:
            console.print("[yellow]Usage: create-room <name>[/yellow]")
            return
        asyncio.run_coroutine_threadsafe(self._client.create_room(name), self._loop)

    def _cmd_join(self, args: str) -> None:
        if not self._ensure_connected():
            return
        room = args.strip() or "general"
        asyncio.run_coroutine_threadsafe(self._client.join_room(room), self._loop)
        self._client.room = room

    def _cmd_leave(self) -> None:
        if not self._ensure_connected():
            return
        asyncio.run_coroutine_threadsafe(self._client.leave_room(), self._loop)
        self._client.room = ""

    def _cmd_list_rooms(self) -> None:
        if not self._ensure_connected():
            return
        asyncio.run_coroutine_threadsafe(self._client.list_rooms(), self._loop)

    def _cmd_list_users(self) -> None:
        if not self._ensure_connected():
            return
        asyncio.run_coroutine_threadsafe(self._client.list_users(), self._loop)

    # ──────────── messaging ────────────

    def _cmd_send(self, args: str) -> None:
        if not self._ensure_connected():
            return
        text = args.strip()
        if not text:
            console.print("[yellow]Usage: send <message>[/yellow]")
            return
        if not self._client.room:
            console.print("[red]Join a room first: join <room>[/red]")
            return
        asyncio.run_coroutine_threadsafe(self._client.send_message(text), self._loop)

    def _cmd_dm(self, args: str) -> None:
        if not self._ensure_connected():
            return
        parts = args.strip().split(maxsplit=1)
        if len(parts) < 2:
            console.print("[yellow]Usage: msg <user> <message>[/yellow]")
            return
        target, text = parts[0], parts[1]
        asyncio.run_coroutine_threadsafe(self._client.send_dm(target, text), self._loop)

    def _cmd_edit(self, args: str) -> None:
        if not self._ensure_connected():
            return
        parts = args.strip().split(maxsplit=1)
        if len(parts) < 2:
            console.print("[yellow]Usage: edit <msg_id> <new_text>[/yellow]")
            return
        try:
            msg_id = int(parts[0])
        except ValueError:
            console.print("[red]Invalid message ID.[/red]")
            return
        asyncio.run_coroutine_threadsafe(
            self._client.edit_message(msg_id, parts[1]),
            self._loop,
        )

    def _cmd_delete(self, args: str) -> None:
        if not self._ensure_connected():
            return
        try:
            msg_id = int(args.strip())
        except ValueError:
            console.print("[red]Invalid message ID.[/red]")
            return
        asyncio.run_coroutine_threadsafe(self._client.delete_message(msg_id), self._loop)

    def _cmd_search(self, args: str) -> None:
        if not self._ensure_connected():
            return
        query = args.strip()
        if not query:
            console.print("[yellow]Usage: search <text>[/yellow]")
            return
        asyncio.run_coroutine_threadsafe(self._client.search(query), self._loop)

    # ──────────── voice ────────────

    def _cmd_call(self, args: str) -> None:
        if not self._ensure_connected():
            return
        target = args.strip()
        if not target:
            console.print("[yellow]Usage: call <user>[/yellow]")
            return
        asyncio.run_coroutine_threadsafe(self._client.call_user(target), self._loop)

    def _cmd_accept_call(self, args: str) -> None:
        if not self._ensure_connected():
            return
        caller = args.strip() or self._incoming_call_from
        if not caller:
            console.print("[yellow]No pending call to accept.[/yellow]")
            return
        asyncio.run_coroutine_threadsafe(self._client.accept_call(caller), self._loop)
        self._incoming_call_from = ""

    def _cmd_reject_call(self, args: str) -> None:
        if not self._ensure_connected():
            return
        caller = args.strip() or self._incoming_call_from
        if not caller:
            console.print("[yellow]No pending call to reject.[/yellow]")
            return
        asyncio.run_coroutine_threadsafe(self._client.reject_call(caller), self._loop)
        self._incoming_call_from = ""

    def _cmd_voice(self, args: str) -> None:
        if not self._ensure_connected():
            return
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else ""
        if sub == "join":
            room = parts[1] if len(parts) > 1 else ""
            asyncio.run_coroutine_threadsafe(self._client.voice_join(room), self._loop)
        elif sub == "leave":
            asyncio.run_coroutine_threadsafe(self._client.voice_leave(), self._loop)
        else:
            console.print("[yellow]Usage: voice join [room] | voice leave[/yellow]")

    def _cmd_mute_self(self) -> None:
        if not self._ensure_connected():
            return
        asyncio.run_coroutine_threadsafe(self._client.mute(), self._loop)

    def _cmd_unmute_self(self) -> None:
        if not self._ensure_connected():
            return
        asyncio.run_coroutine_threadsafe(self._client.unmute(), self._loop)

    def _cmd_hangup(self) -> None:
        if not self._ensure_connected():
            return
        asyncio.run_coroutine_threadsafe(self._client.hangup(), self._loop)

    # ──────────── files ────────────

    def _cmd_file(self, args: str) -> None:
        if not self._ensure_connected():
            return
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else ""
        farg = parts[1].strip() if len(parts) > 1 else ""

        if sub == "send":
            if not farg:
                console.print("[yellow]Usage: file send <filepath>[/yellow]")
                return
            try:
                asyncio.run_coroutine_threadsafe(
                    self._client.upload_file(farg), self._loop
                ).result(timeout=30)
            except FileNotFoundError as exc:
                console.print(f"[red]{exc}[/red]")
            except Exception as exc:
                console.print(f"[red]Upload failed: {exc}[/red]")
        elif sub == "receive":
            if not farg:
                console.print("[yellow]Usage: file receive <file_id>[/yellow]")
                return
            asyncio.run_coroutine_threadsafe(self._client.download_file(farg), self._loop)
        elif sub == "list":
            asyncio.run_coroutine_threadsafe(self._client.list_files(), self._loop)
        else:
            console.print("[yellow]Usage: file send|receive|list[/yellow]")

    # ──────────── AI ────────────

    def _cmd_ai(self, args: str) -> None:
        if not self._ensure_connected():
            return
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else ""
        aarg = parts[1].strip() if len(parts) > 1 else ""

        match sub:
            case "enable":
                provider = aarg or "openai"
                asyncio.run_coroutine_threadsafe(self._client.ai_enable(provider), self._loop)
            case "ask":
                if not aarg:
                    console.print("[yellow]Usage: ai ask <question>[/yellow]")
                    return
                asyncio.run_coroutine_threadsafe(self._client.ai_ask(aarg), self._loop)
            case "summarize":
                asyncio.run_coroutine_threadsafe(self._client.ai_summarize(), self._loop)
            case "usage":
                asyncio.run_coroutine_threadsafe(self._client.ai_usage(), self._loop)
            case "budget":
                try:
                    amount = float(aarg.replace("$", ""))
                except ValueError:
                    console.print("[yellow]Usage: ai budget <amount>[/yellow]")
                    return
                asyncio.run_coroutine_threadsafe(self._client.ai_budget(amount), self._loop)
            case "limit":
                try:
                    limit = int(aarg)
                except ValueError:
                    console.print("[yellow]Usage: ai limit <number>[/yellow]")
                    return
                asyncio.run_coroutine_threadsafe(self._client.ai_limit(limit), self._loop)
            case _:
                console.print("[yellow]Usage: ai enable|ask|summarize|usage|budget|limit[/yellow]")

    # ──────────── moderation ────────────

    def _cmd_kick(self, args: str) -> None:
        if not self._ensure_connected():
            return
        target = args.strip()
        if not target:
            console.print("[yellow]Usage: kick <user>[/yellow]")
            return
        asyncio.run_coroutine_threadsafe(self._client.kick(target), self._loop)

    def _cmd_ban(self, args: str) -> None:
        if not self._ensure_connected():
            return
        target = args.strip()
        asyncio.run_coroutine_threadsafe(self._client.ban(target), self._loop)

    def _cmd_unban(self, args: str) -> None:
        if not self._ensure_connected():
            return
        target = args.strip()
        asyncio.run_coroutine_threadsafe(self._client.unban(target), self._loop)

    def _cmd_mute_user(self, args: str) -> None:
        if not self._ensure_connected():
            return
        target = args.strip()
        asyncio.run_coroutine_threadsafe(self._client.mute_user(target), self._loop)

    def _cmd_unmute_user(self, args: str) -> None:
        if not self._ensure_connected():
            return
        target = args.strip()
        asyncio.run_coroutine_threadsafe(self._client.unmute_user(target), self._loop)

    def _cmd_admin(self, args: str) -> None:
        if not self._ensure_connected():
            return
        target = args.strip()
        asyncio.run_coroutine_threadsafe(self._client.promote_admin(target), self._loop)

    # ──────────── incoming packet renderer ────────────

    def _on_packet(self, pkt: Packet) -> None:
        """Display incoming packets with Rich formatting."""
        match pkt.action:
            case Action.MESSAGE:
                ts = _ts(pkt.timestamp)
                console.print(f"  [dim]{ts}[/dim] [bold]{pkt.sender}[/bold]: {pkt.content}"
                              + (f"  [dim](#{pkt.msg_id})[/dim]" if pkt.msg_id else ""))

            case Action.DM:
                ts = _ts(pkt.timestamp)
                direction = "→" if pkt.sender == (self._client.username if self._client else "") else "←"
                other = pkt.target if pkt.sender == (self._client.username if self._client else "") else pkt.sender
                console.print(f"  [dim]{ts}[/dim] [magenta]DM {direction} {other}:[/magenta] {pkt.content}")

            case Action.EDIT:
                console.print(f"  [dim]✎ {pkt.sender} edited msg #{pkt.msg_id}:[/dim] {pkt.content}")

            case Action.DELETE:
                console.print(f"  [dim]🗑 {pkt.sender} deleted msg #{pkt.msg_id}[/dim]")

            case Action.SYSTEM:
                console.print(f"  [dim cyan]» {pkt.content}[/dim cyan]")

            case Action.OK:
                console.print(f"  [green]✓[/green] {pkt.content}")

            case Action.ERROR:
                console.print(f"  [red]✗[/red] {pkt.content}")

            case Action.AUTH_OK:
                console.print(f"  [green]✓ Authenticated:[/green] {pkt.content}")

            case Action.AUTH_FAIL:
                console.print(f"  [red]✗ Auth failed:[/red] {pkt.content}")

            case Action.ROOM_LIST:
                rooms = pkt.data.get("rooms", [])
                if not rooms:
                    console.print("  [dim]No rooms found.[/dim]")
                else:
                    table = Table(title="Rooms", show_header=True, header_style="bold cyan")
                    table.add_column("Name", style="green")
                    table.add_column("Created By")
                    for r in rooms:
                        table.add_row(f"#{r['name']}", r.get("created_by", ""))
                    console.print(table)

            case Action.USER_LIST:
                users = pkt.data.get("users", [])
                room = pkt.room or "online"
                console.print(f"  [cyan]Users in {room}:[/cyan] {', '.join(users) if users else '(none)'}")

            case Action.MSG_LIST:
                msgs = pkt.data.get("messages", [])
                query = pkt.data.get("query", "")
                if query:
                    console.print(f"  [cyan]Search results for '{query}':[/cyan]")
                for m in msgs:
                    ts = _ts(m.get("timestamp", 0))
                    console.print(f"  [dim]{ts}[/dim] [{m.get('id', '?')}] {m.get('sender', '?')}: {m.get('content', '')}")

            case Action.CALL:
                caller = pkt.sender
                self._incoming_call_from = caller
                console.print(
                    f"\n  [bold yellow]📞 Incoming call from {caller}![/bold yellow]\n"
                    f"  Type [bold]accept[/bold] or [bold]reject[/bold]"
                )

            case Action.CALL_ACCEPT:
                console.print(f"  [green]📞 {pkt.sender} accepted your call.[/green]")

            case Action.CALL_REJECT:
                console.print(f"  [red]📞 {pkt.sender} rejected your call.[/red]")

            case Action.CALL_END:
                console.print(f"  [dim]📞 Call ended by {pkt.sender}.[/dim]")

            case Action.AI_RESPONSE:
                console.print(Panel(
                    pkt.content,
                    title=f"AI ({pkt.data.get('provider', 'unknown')})",
                    border_style="blue",
                    subtitle=f"tokens: {pkt.data.get('tokens', '?')} | cost: {pkt.data.get('cost', '?')}",
                ))

            case Action.FILE_DATA:
                filename = pkt.data.get("filename", "file")
                data_b64 = pkt.data.get("data", "")
                size = pkt.data.get("size", 0)
                if data_b64:
                    dest = Path.cwd() / filename
                    dest.write_bytes(base64.b64decode(data_b64))
                    console.print(f"  [green]✓[/green] Downloaded: {dest} ({size} bytes)")

            case Action.FILE_RECORD_LIST:
                files = pkt.data.get("files", [])
                if not files:
                    console.print("  [dim]No files.[/dim]")
                else:
                    table = Table(title="Files", show_header=True, header_style="bold cyan")
                    table.add_column("ID", style="green")
                    table.add_column("Name")
                    table.add_column("Sender")
                    table.add_column("Size")
                    for f in files:
                        table.add_row(f.get("file_id", ""), f.get("filename", ""),
                                      f.get("sender", ""), str(f.get("size", 0)))
                    console.print(table)

            case _:
                if pkt.content:
                    console.print(f"  [dim]{pkt.action.value}: {pkt.content}[/dim]")
