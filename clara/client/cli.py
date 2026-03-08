"""CLARA client — CLI entry point (interactive terminal client).

Usage:
    clara-client --host 127.0.0.1 --port 9100
"""

import asyncio
import base64
import sys
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt

from clara.client.commands import parse_command
from clara.client.ui import console, render_packet, show_welcome, _render_help
from clara.client.websocket_client import ClaraWSClient
from clara.server.protocol import Action, Packet


async def _interactive(host: str, port: int) -> None:
    client = ClaraWSClient(host, port)
    try:
        await client.connect()
    except Exception as exc:
        console.print(f"[bold red]Cannot connect to {host}:{port}: {exc}[/]")
        return

    show_welcome()

    # ── auth ──
    mode = Prompt.ask("[bold]Register or Login?[/]", choices=["register", "login"], default="login")
    username = Prompt.ask("[bold]Username[/]")
    password = Prompt.ask("[bold]Password[/]", password=True)

    if mode == "register":
        resp = await client.register(username, password)
    else:
        resp = await client.login(username, password)
    render_packet(resp)

    if resp.action != Action.AUTH_OK:
        await client.close()
        return

    # ── listener task ──
    async def listener() -> None:
        while client.connected:
            pkt = await client.recv_packet()
            if pkt is None:
                break
            render_packet(pkt)

    listen_task = asyncio.create_task(listener())

    # ── heartbeat task ──
    async def heartbeat() -> None:
        while client.connected:
            await asyncio.sleep(25)
            try:
                await client.heartbeat()
            except Exception:
                break

    hb_task = asyncio.create_task(heartbeat())

    # ── input loop ──
    try:
        while client.connected:
            try:
                raw = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input(f"[{client.username}#{client.room or '-'}] > "),
                )
            except (EOFError, KeyboardInterrupt):
                break

            pkt = parse_command(raw, client.room)
            if pkt is None:
                continue

            # Client-side help — rendered locally, no server round-trip
            if pkt.action == Action.SYSTEM and pkt.content == "__HELP__":
                _render_help()
                continue

            # File upload needs local processing
            if pkt.action == Action.FILE_UPLOAD and pkt.data.get("filepath"):
                filepath = pkt.data["filepath"]
                try:
                    path = Path(filepath)
                    data_b64 = base64.b64encode(path.read_bytes()).decode()
                    pkt = Packet(action=Action.FILE_UPLOAD,
                                 data={"filename": path.name, "data": data_b64})
                except FileNotFoundError:
                    console.print(f"[red]File not found: {filepath}[/]")
                    continue
                except Exception as exc:
                    console.print(f"[red]Error reading file: {exc}[/]")
                    continue

            if pkt.action == Action.DISCONNECT:
                break

            try:
                await client.send_packet(pkt)
            except Exception as exc:
                console.print(f"[red]Send error: {exc}[/]")
                break
    finally:
        hb_task.cancel()
        listen_task.cancel()
        await client.close()
        console.print("[dim]Disconnected.[/]")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="CLARA Client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9100)
    args = parser.parse_args()
    try:
        asyncio.run(_interactive(args.host, args.port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
