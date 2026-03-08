"""CLARA client — Rich terminal UI for formatting messages."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from clara.server.protocol import Action, Packet

console = Console()


def render_packet(pkt: Packet) -> None:
    """Render a received packet using Rich."""
    a = pkt.action

    if a == Action.AUTH_OK:
        console.print(f"[bold green]✓[/] {pkt.content}")
    elif a == Action.AUTH_FAIL:
        console.print(f"[bold red]✗[/] {pkt.content}")
    elif a == Action.OK:
        console.print(f"[green]→[/] {pkt.content}")
    elif a == Action.ERROR:
        console.print(f"[bold red]✗ Error:[/] {pkt.content}")
    elif a == Action.SYSTEM:
        if pkt.content == "__HELP__":
            _render_help()
        else:
            console.print(f"[dim cyan]ℹ {pkt.content}[/]")
    elif a == Action.MESSAGE:
        ts = pkt.timestamp[:19] if pkt.timestamp else ""
        reply = pkt.data.get("reply_to", "")
        prefix = f"[dim](↩ {reply})[/] " if reply else ""
        console.print(
            f"[dim]{ts}[/] [bold]{pkt.sender}[/] [dim]#{pkt.room}[/]: {prefix}{pkt.content}"
        )
    elif a == Action.DM:
        console.print(f"[magenta]DM[/] [bold]{pkt.sender}[/] → [bold]{pkt.target}[/]: {pkt.content}")
    elif a == Action.EDIT:
        console.print(f"[yellow]✎ {pkt.sender} edited msg {pkt.msg_id}:[/] {pkt.content}")
    elif a == Action.DELETE:
        console.print(f"[red]✕ {pkt.sender} deleted msg {pkt.msg_id}[/]")
    elif a == Action.ROOM_LIST:
        _render_rooms(pkt)
    elif a == Action.USER_LIST:
        _render_users(pkt)
    elif a == Action.MSG_LIST:
        _render_messages(pkt)
    elif a == Action.CALL:
        console.print(f"[bold yellow]📞 Incoming call from {pkt.sender}[/] — /accept {pkt.sender} or /reject {pkt.sender}")
    elif a == Action.CALL_ACCEPT:
        console.print(f"[bold green]📞 {pkt.sender} accepted the call[/]")
    elif a == Action.CALL_REJECT:
        console.print(f"[red]📞 {pkt.sender} rejected the call[/]")
    elif a == Action.CALL_END:
        console.print(f"[dim]📞 Call ended by {pkt.sender}[/]")
    elif a == Action.FILE_DATA:
        d = pkt.data
        console.print(f"[green]📎 File: {d.get('filename', '?')}[/] ({d.get('size', 0)} bytes, SHA: {d.get('sha256', '?')[:12]}...)")
    elif a == Action.FILE_RECORD_LIST:
        _render_files(pkt)
    elif a == Action.AI_RESPONSE:
        _render_ai(pkt)
    elif a == Action.PRESENCE:
        _render_presence(pkt)
    elif a == Action.TYPING:
        console.print(f"[dim]{pkt.sender} is typing...[/]")
    elif a == Action.HEARTBEAT:
        pass  # silent
    else:
        console.print(f"[dim][{a.value}][/] {pkt.content}")


def _render_rooms(pkt: Packet) -> None:
    rooms = pkt.data.get("rooms", [])
    table = Table(title="Rooms", show_lines=False)
    table.add_column("Name", style="cyan")
    table.add_column("Created by", style="green")
    for r in rooms:
        table.add_row(r["name"], r.get("created_by", ""))
    console.print(table)


def _render_users(pkt: Packet) -> None:
    users = pkt.data.get("users", [])
    room = pkt.room or "all"
    console.print(Panel(", ".join(users) if users else "(none)",
                        title=f"Users in #{room}", border_style="cyan"))


def _render_messages(pkt: Packet) -> None:
    msgs = pkt.data.get("messages", [])
    query = pkt.data.get("query", "")
    title = f"Search: '{query}'" if query else f"History #{pkt.room}"
    table = Table(title=title, show_lines=False)
    table.add_column("ID", style="dim", width=6)
    table.add_column("Sender", style="bold")
    table.add_column("Message")
    table.add_column("Time", style="dim")
    for m in msgs:
        table.add_row(str(m["id"]), m["sender"], m["content"], m.get("timestamp", "")[:19])
    console.print(table)


def _render_files(pkt: Packet) -> None:
    files = pkt.data.get("files", [])
    table = Table(title="Files", show_lines=False)
    table.add_column("ID", style="cyan")
    table.add_column("Filename")
    table.add_column("Sender", style="green")
    table.add_column("Size", justify="right")
    for f in files:
        table.add_row(f["file_id"], f["filename"], f["sender"], str(f.get("size", 0)))
    console.print(table)


def _render_ai(pkt: Packet) -> None:
    console.print(Panel(pkt.content, title="AI Response", border_style="magenta"))
    d = pkt.data
    if d.get("tokens"):
        console.print(f"[dim]Tokens: {d['tokens']}  Cost: {d.get('cost', 'N/A')}  Provider: {d.get('provider', '-')}[/]")


def _render_presence(pkt: Packet) -> None:
    users = pkt.data.get("users")
    if users:
        table = Table(title="Online Users", show_lines=False)
        table.add_column("User", style="bold")
        table.add_column("Status")
        table.add_column("Typing in")
        for name, info in users.items():
            table.add_row(name, info.get("status", "?"), info.get("typing") or "")
        console.print(table)
    else:
        user = pkt.data.get("user", pkt.sender)
        status = pkt.data.get("status", "?")
        console.print(f"[dim]{user} is now {status}[/]")


def _render_help() -> None:
    from clara.client.commands import HELP_ENTRIES
    CATEGORY_COLORS = {
        "Connection": "bright_white",
        "Rooms":      "cyan",
        "Chat":       "green",
        "Voice":      "yellow",
        "Files":      "blue",
        "AI":         "magenta",
        "Moderation": "red",
        "Status":     "bright_cyan",
    }
    table = Table(
        show_header=True, header_style="bold white",
        box=box.SIMPLE_HEAVY, show_lines=False, expand=False,
        title="[bold cyan]CLARA — Command Reference[/]",
    )
    table.add_column("Category",    style="dim",          width=12, no_wrap=True)
    table.add_column("Syntax",                            width=32, no_wrap=True)
    table.add_column("Example",     style="bold green",   width=40, no_wrap=True)
    table.add_column("Description", style="dim white",    min_width=30)

    last_cat = ""
    for category, syntax, example, desc in HELP_ENTRIES:
        color = CATEGORY_COLORS.get(category, "white")
        cat_cell = f"[{color}]{category}[/]" if category != last_cat else ""
        last_cat = category
        table.add_row(cat_cell, f"[bold]{syntax}[/]", example, desc)

    console.print()
    console.print(table)
    console.print("[dim]  Tip: type any text without a / to send a chat message to the current room.[/]\n")


def show_welcome() -> None:
    console.print(Panel(
        "[bold cyan]CLARA[/] — Communication Layer for Autonomous Real-time Agents\n"
        "Type [bold]/help[/] for commands, or just type to chat.",
        title="Welcome", border_style="cyan",
    ))
