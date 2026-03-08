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

from rich import box
from rich.align import Align
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.rule import Rule
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
        console.print()
        console.print(Panel(
            Align.center(
                "[bold bright_cyan]C L A R A[/bold bright_cyan]\n"
                "[dim]Terminal Communication Platform[/dim]\n\n"
                "[dim]Chat  ·  Rooms  ·  DMs  ·  Voice  ·  Files  ·  AI[/dim]"
            ),
            border_style="cyan",
            padding=(1, 4),
            subtitle="[dim]type [bold green]help[/bold green] for commands  ·  "
                     "[bold green]connect <host> <user>[/bold green] to start[/dim]",
        ))
        console.print()

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
                ("server status", "Check server health"),
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
                ("msg <user> <message>", "Send a private message"),
                ("edit <msg_id> <text>", "Edit one of your messages"),
                ("delete <msg_id>", "Delete a message"),
                ("search <text>", "Search messages in room"),
            ]),
            ("Voice", [
                ("call <user>", "Start a voice call"),
                ("accept", "Accept an incoming call"),
                ("reject", "Reject an incoming call"),
                ("hangup", "End the current call"),
                ("voice join [room]", "Join a voice channel"),
                ("voice leave", "Leave the voice channel"),
                ("mute", "Mute yourself"),
                ("unmute", "Unmute yourself"),
            ]),
            ("Files", [
                ("file send <path>", "Upload a file to the room"),
                ("file receive <id>", "Download a shared file"),
                ("file list", "List files shared in room"),
            ]),
            ("AI", [
                ("ai enable [provider]", "Enable AI  (openai / claude / openrouter)"),
                ("ai ask <question>", "Ask the AI assistant anything"),
                ("ai summarize", "Summarise recent chat history"),
                ("ai usage", "Show token usage and cost"),
                ("ai budget <amount>", "Set a spending cap  e.g. ai budget 5"),
                ("ai limit <n>", "Set max tokens per response"),
            ]),
            ("Moderation", [
                ("kick <user>", "Kick a user from the room"),
                ("ban <user>", "Ban a user from the server"),
                ("mute <user>", "Mute a user in the room"),
                ("admin <user>", "Promote a user to admin"),
            ]),
        ]
        console.print()
        console.rule("[bold cyan]CLARA  —  Commands[/bold cyan]", style="cyan")
        table = Table(
            show_header=True,
            header_style="bold dim",
            border_style="bright_black",
            box=box.SIMPLE,
            padding=(0, 1),
            expand=False,
        )
        table.add_column("Category",  style="dim cyan",   width=12, no_wrap=True)
        table.add_column("Command",   style="bold green", width=28, no_wrap=True)
        table.add_column("Description")
        for i, (title, cmds) in enumerate(sections):
            if i > 0:
                table.add_row("", "", "")   # blank separator row
            for j, (cmd, desc) in enumerate(cmds):
                table.add_row(title if j == 0 else "", cmd, desc)
        console.print(table)
        console.rule(style="bright_black")
        console.print()

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

        # Guard: block if already live-connected
        if self._client and self._client.connected:
            console.print(
                f"[yellow]Already connected as [bold]{self._client.username}[/bold]. "
                "Run [bold]disconnect[/bold] first.[/yellow]"
            )
            return

        # Tear down any previous client that is dead/reconnecting but not yet cleaned up.
        # This stops orphaned reconnect loops from continuing in the background.
        if self._client is not None:
            self._client._shutdown = True   # stops _reconnect_loop immediately
            if self._loop and self._loop.is_running():
                try:
                    asyncio.run_coroutine_threadsafe(
                        self._client.close(), self._loop
                    ).result(timeout=2)
                except Exception:
                    pass
                self._loop.call_soon_threadsafe(self._loop.stop)
            self._client = None
            self._loop = None

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
        if not self._client:
            console.print("[yellow]Not connected.[/yellow]")
            return
        if self._loop and self._loop.is_running():
            self._client._shutdown = True   # stop any reconnect loop first
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

    def _on_packet(self, pkt: Packet) -> None:  # noqa: C901
        """Render incoming packets with Claude Code-style Rich formatting."""
        match pkt.action:

            # ── chat messages ──────────────────────────────────────────────
            case Action.MESSAGE:
                ts = _ts(pkt.timestamp)
                room_tag = f"  [dim bright_black]#{pkt.room}[/dim bright_black]" if pkt.room else ""
                id_tag   = f"  [dim]·{pkt.msg_id}[/dim]" if pkt.msg_id else ""
                console.print(
                    f" [dim]{ts}[/dim]  [bold cyan]{escape(pkt.sender)}[/bold cyan]  "
                    f"{escape(pkt.content)}{id_tag}{room_tag}"
                )

            case Action.DM:
                ts  = _ts(pkt.timestamp)
                me  = self._client.username if self._client else ""
                out = pkt.sender == me
                other  = pkt.target if out else pkt.sender
                arrow  = "[bold magenta]→[/bold magenta]" if out else "[bold magenta]←[/bold magenta]"
                console.print(
                    f" [dim]{ts}[/dim]  {arrow}  [bold magenta]{escape(other)}[/bold magenta]  "
                    f"[dim magenta]dm[/dim magenta]  {escape(pkt.content)}"
                )

            # ── message mutations ──────────────────────────────────────────
            case Action.EDIT:
                console.print(
                    f" [dim]  ✎  {escape(pkt.sender)} edited "
                    f"[bold]#{pkt.msg_id}[/bold]:[/dim]  {escape(pkt.content)}"
                )

            case Action.DELETE:
                console.print(
                    f" [dim]  ✗  {escape(pkt.sender)} deleted msg #{pkt.msg_id}[/dim]"
                )

            # ── system / status ────────────────────────────────────────────
            case Action.SYSTEM:
                console.rule(f"[dim]{escape(pkt.content)}[/dim]", style="bright_black")

            case Action.OK:
                console.print(f"  [bold green]✓[/bold green]  {escape(pkt.content)}")

            case Action.ERROR:
                console.print(f"  [bold red]✗[/bold red]  {escape(pkt.content)}")

            case Action.AUTH_OK:
                console.print(f"  [bold green]✓[/bold green]  [dim]auth:[/dim]  {escape(pkt.content)}")

            case Action.AUTH_FAIL:
                console.print(f"  [bold red]✗[/bold red]  [dim]auth:[/dim]  {escape(pkt.content)}")

            # ── room / user lists ──────────────────────────────────────────
            case Action.ROOM_LIST:
                rooms = pkt.data.get("rooms", [])
                if not rooms:
                    console.print("  [dim]No rooms yet  —  create one with [bold]create-room <name>[/bold][/dim]")
                else:
                    table = Table(
                        show_header=True,
                        header_style="bold dim",
                        border_style="bright_black",
                        box=box.SIMPLE,
                        padding=(0, 1),
                    )
                    table.add_column("#",          style="dim",       width=4)
                    table.add_column("Room",       style="bold cyan")
                    table.add_column("Created by", style="dim")
                    for i, r in enumerate(rooms, 1):
                        table.add_row(str(i), r["name"], r.get("created_by", ""))
                    console.print(table)

            case Action.USER_LIST:
                users = pkt.data.get("users", [])
                room  = pkt.room or "server"
                if not users:
                    console.print(f"  [dim]No users in [bold]{room}[/bold][/dim]")
                else:
                    pills = "  ".join(f"[cyan]{escape(u)}[/cyan]" for u in users)
                    console.print(f"  [dim]in [bold]{room}[/bold][/dim]  {pills}")

            # ── search results ─────────────────────────────────────────────
            case Action.MSG_LIST:
                msgs  = pkt.data.get("messages", [])
                query = pkt.data.get("query", "")
                if query:
                    console.rule(
                        f"[dim]search results for[/dim] [bold]{escape(query)!r}[/bold]",
                        style="bright_black",
                    )
                if not msgs:
                    console.print("  [dim]No messages found.[/dim]")
                for m in msgs:
                    ts = _ts(m.get("timestamp", 0))
                    console.print(
                        f" [dim]{ts}[/dim]  [dim]#{m.get('id','?')}[/dim]  "
                        f"[bold]{escape(m.get('sender','?'))}[/bold]  "
                        f"{escape(m.get('content',''))}"
                    )
                if query and msgs:
                    console.rule(style="bright_black")

            # ── voice / calls ──────────────────────────────────────────────
            case Action.CALL:
                caller = pkt.sender
                self._incoming_call_from = caller
                console.print()
                console.print(Panel(
                    f"[bold yellow]  📞  Incoming call from "
                    f"[bold white]{escape(caller)}[/bold white][/bold yellow]\n\n"
                    "[dim]  Type [bold]accept[/bold] to answer  ·  "
                    "[bold]reject[/bold] to decline[/dim]",
                    border_style="yellow",
                    padding=(0, 2),
                ))

            case Action.CALL_ACCEPT:
                console.print(Panel(
                    f"[bold green]  📞  Connected with "
                    f"[bold white]{escape(pkt.sender)}[/bold white][/bold green]",
                    border_style="green",
                    padding=(0, 2),
                ))

            case Action.CALL_REJECT:
                console.print(
                    f"  [dim]📞  {escape(pkt.sender)} declined.[/dim]"
                )

            case Action.CALL_END:
                console.print(
                    f"  [dim]📞  Call ended by {escape(pkt.sender)}.[/dim]"
                )

            # ── AI ─────────────────────────────────────────────────────────
            case Action.AI_RESPONSE:
                provider = pkt.data.get("provider", "AI")
                tokens   = pkt.data.get("tokens", "?")
                cost     = pkt.data.get("cost", "?")
                console.print(Panel(
                    pkt.content,
                    title=f"[bold cyan]{escape(provider)}[/bold cyan]",
                    subtitle=f"[dim]{tokens} tokens  ·  ${cost}[/dim]",
                    border_style="blue",
                    padding=(1, 2),
                ))

            # ── files ──────────────────────────────────────────────────────
            case Action.FILE_DATA:
                filename = pkt.data.get("filename", "file")
                data_b64 = pkt.data.get("data", "")
                size     = pkt.data.get("size", 0)
                if data_b64:
                    dest = Path.cwd() / filename
                    dest.write_bytes(base64.b64decode(data_b64))
                    console.print(
                        f"  [bold green]↓[/bold green]  [bold]{escape(filename)}[/bold]  "
                        f"[dim]{size:,} bytes  →  {dest}[/dim]"
                    )

            case Action.FILE_RECORD_LIST:
                files = pkt.data.get("files", [])
                if not files:
                    console.print("  [dim]No files shared in this room.[/dim]")
                else:
                    table = Table(
                        show_header=True,
                        header_style="bold dim",
                        border_style="bright_black",
                        box=box.SIMPLE,
                        padding=(0, 1),
                    )
                    table.add_column("ID",          style="dim",  width=10, no_wrap=True)
                    table.add_column("Filename",    style="bold")
                    table.add_column("Size",        justify="right", style="dim")
                    table.add_column("Uploaded by", style="dim")
                    for f in files:
                        table.add_row(
                            str(f.get("file_id", ""))[:8],
                            f.get("filename", ""),
                            f"{f.get('size', 0):,}",
                            f.get("sender", ""),
                        )
                    console.print(table)

            case _:
                if pkt.content:
                    console.print(f"  [dim]{escape(pkt.action.value)}  {escape(pkt.content)}[/dim]")
