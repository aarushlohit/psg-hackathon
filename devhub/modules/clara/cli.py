"""CLARA CLI — standalone Typer entry point.

Usage:
    clara server start
    clara connect <host> <username>
    clara --help
"""

from __future__ import annotations

import asyncio
import sys
import time
import threading

import typer
from rich.console import Console

console = Console()
app = typer.Typer(
    name="clara",
    help="CLARA CLI — Terminal Communication Platform",
    add_completion=False,
    rich_markup_mode="rich",
)
server_app = typer.Typer(help="Server management")
app.add_typer(server_app, name="server")


# ──────────── server commands ────────────


@server_app.command("start")
def server_start(
    host: str = typer.Option("0.0.0.0", "--host", "-H", help="Bind address"),
    port: int = typer.Option(9100, "--port", "-p", help="Port"),
) -> None:
    """Start the CLARA server."""
    from devhub.modules.clara.server.app import run_server
    console.print(f"[bold cyan]CLARA Server[/bold cyan] starting on {host}:{port}")
    run_server(host, port)


@server_app.command("stop")
def server_stop() -> None:
    """Stop the CLARA server (placeholder — server runs until killed)."""
    console.print("[yellow]Send Ctrl+C to the server process to stop it.[/yellow]")


@server_app.command("status")
def server_status(
    host: str = typer.Option("127.0.0.1", "--host", "-H"),
    port: int = typer.Option(9100, "--port", "-p"),
) -> None:
    """Check if CLARA server is running."""
    import urllib.request
    import json
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/status", timeout=3) as resp:
            data = json.loads(resp.read())
            console.print(f"[green]● CLARA Server v{data.get('version', '?')}[/green]"
                          f" — {data.get('clients', 0)} client(s) connected")
    except Exception:
        console.print(f"[red]● Server not reachable at {host}:{port}[/red]")


# ──────────── connect command ────────────


@app.command()
def connect(
    host: str = typer.Argument(..., help="Server IP or hostname"),
    username: str = typer.Argument(..., help="Your username"),
    port: int = typer.Option(9100, "--port", "-p", help="Server port"),
) -> None:
    """Connect to a CLARA server and enter interactive chat."""
    from devhub.modules.clara.client.ws_client import ClaraWSClient
    from devhub.modules.clara.protocol import Action, Packet

    password = console.input("[dim]Password: [/dim]", password=True)

    loop = asyncio.new_event_loop()

    client = ClaraWSClient(host, port)

    def _display(pkt: Packet) -> None:
        """Simple packet display for standalone mode."""
        from devhub.modules.clara.module import ClaraModule
        # Reuse the renderer from the module
        mod = ClaraModule.__new__(ClaraModule)
        mod._client = client
        mod._incoming_call_from = ""
        mod._on_packet(pkt)

    async def _connect() -> bool:
        await client.connect()
        resp = await client.login(username, password)
        if resp.action == Action.AUTH_FAIL:
            resp = await client.register(username, password)
        if resp.action == Action.AUTH_OK:
            console.print(f"[green]✓[/green] {resp.content}")
            client.start_listener(_display)
            return True
        else:
            console.print(f"[red]✗[/red] {resp.content}")
            return False

    # Connect in background event loop
    def _run_loop():
        asyncio.set_event_loop(loop)
        ok = loop.run_until_complete(_connect())
        if ok:
            loop.run_forever()

    t = threading.Thread(target=_run_loop, daemon=True)
    t.start()
    time.sleep(1)

    if not client.connected:
        console.print("[red]Connection failed.[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Connected to {host}:{port} as {username}. Type /help for commands.[/dim]\n")

    # Interactive loop
    try:
        while client.connected:
            try:
                raw = input(f"clara({username})> ")
            except (EOFError, KeyboardInterrupt):
                break

            raw = raw.strip()
            if not raw:
                continue

            if raw in ("/quit", "/exit", "/q"):
                break

            if raw == "/help":
                console.print(
                    "[cyan]Commands:[/cyan]\n"
                    "  join <room>        — Join room\n"
                    "  leave              — Leave room\n"
                    "  rooms              — List rooms\n"
                    "  list               — List users\n"
                    "  msg <user> <text>  — Private message\n"
                    "  file send <path>   — Upload file\n"
                    "  file list          — List files\n"
                    "  call <user>        — Voice call\n"
                    "  ai enable          — Enable AI\n"
                    "  ai ask <q>         — Ask AI\n"
                    "  /quit              — Exit\n"
                    "  [dim]Anything else is sent as a chat message.[/dim]"
                )
                continue

            # Route commands
            parts = raw.split(maxsplit=1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""

            future = None
            if cmd == "join":
                future = asyncio.run_coroutine_threadsafe(client.join_room(args.strip() or "general"), loop)
                client.room = args.strip() or "general"
            elif cmd == "leave":
                future = asyncio.run_coroutine_threadsafe(client.leave_room(), loop)
            elif cmd == "rooms":
                future = asyncio.run_coroutine_threadsafe(client.list_rooms(), loop)
            elif cmd == "list":
                future = asyncio.run_coroutine_threadsafe(client.list_users(), loop)
            elif cmd == "msg":
                p = args.split(maxsplit=1)
                if len(p) >= 2:
                    future = asyncio.run_coroutine_threadsafe(client.send_dm(p[0], p[1]), loop)
            elif cmd == "file":
                fp = args.split(maxsplit=1)
                sub = fp[0].lower() if fp else ""
                if sub == "send" and len(fp) > 1:
                    future = asyncio.run_coroutine_threadsafe(client.upload_file(fp[1]), loop)
                elif sub == "list":
                    future = asyncio.run_coroutine_threadsafe(client.list_files(), loop)
                elif sub == "receive" and len(fp) > 1:
                    future = asyncio.run_coroutine_threadsafe(client.download_file(fp[1]), loop)
            elif cmd == "call":
                future = asyncio.run_coroutine_threadsafe(client.call_user(args.strip()), loop)
            elif cmd == "hangup":
                future = asyncio.run_coroutine_threadsafe(client.hangup(), loop)
            elif cmd == "ai":
                ap = args.split(maxsplit=1)
                sub = ap[0].lower() if ap else ""
                if sub == "enable":
                    provider = ap[1] if len(ap) > 1 else "openai"
                    future = asyncio.run_coroutine_threadsafe(client.ai_enable(provider), loop)
                elif sub == "ask" and len(ap) > 1:
                    future = asyncio.run_coroutine_threadsafe(client.ai_ask(ap[1]), loop)
                elif sub == "summarize":
                    future = asyncio.run_coroutine_threadsafe(client.ai_summarize(), loop)
                elif sub == "usage":
                    future = asyncio.run_coroutine_threadsafe(client.ai_usage(), loop)
                elif sub == "budget" and len(ap) > 1:
                    future = asyncio.run_coroutine_threadsafe(
                        client.ai_budget(float(ap[1].replace("$", ""))), loop)
                elif sub == "limit" and len(ap) > 1:
                    future = asyncio.run_coroutine_threadsafe(client.ai_limit(int(ap[1])), loop)
            elif cmd in ("kick", "ban", "unban"):
                method = getattr(client, cmd)
                future = asyncio.run_coroutine_threadsafe(method(args.strip()), loop)
            else:
                # Default: send as a chat message
                if client.room:
                    future = asyncio.run_coroutine_threadsafe(client.send_message(raw), loop)
                else:
                    console.print("[yellow]Join a room first: join <room>[/yellow]")

            if future:
                try:
                    future.result(timeout=10)
                except Exception as exc:
                    console.print(f"[red]Error: {exc}[/red]")
    finally:
        asyncio.run_coroutine_threadsafe(client.close(), loop)
        loop.call_soon_threadsafe(loop.stop)
        console.print("[dim]Disconnected.[/dim]")


if __name__ == "__main__":
    app()
