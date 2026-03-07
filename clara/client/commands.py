"""CLARA client — command parser and router."""

import shlex
from typing import Optional

from clara.server.protocol import Action, Packet


def parse_command(raw: str, current_room: str = "") -> Optional[Packet]:
    """Parse user input into a Packet.  Returns None for empty input."""
    raw = raw.strip()
    if not raw:
        return None

    # Slash commands
    if raw.startswith("/"):
        parts = raw[1:].split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        return _dispatch_slash(cmd, arg, current_room)

    # Default: send as chat message
    return Packet(action=Action.MESSAGE, content=raw, room=current_room)


def _dispatch_slash(cmd: str, arg: str, room: str) -> Packet:
    # ── connection ──
    if cmd == "whoami":
        return Packet(action=Action.WHOAMI)
    if cmd in ("quit", "exit", "disconnect"):
        return Packet(action=Action.DISCONNECT)

    # ── rooms ──
    if cmd == "join":
        return Packet(action=Action.JOIN, room=arg or "general")
    if cmd == "leave":
        return Packet(action=Action.LEAVE)
    if cmd == "create":
        return Packet(action=Action.CREATE_ROOM, content=arg)
    if cmd == "rooms":
        return Packet(action=Action.LIST_ROOMS)
    if cmd == "users":
        return Packet(action=Action.LIST_USERS, room=room)
    if cmd == "who":
        return Packet(action=Action.PRESENCE)

    # ── messaging ──
    if cmd in ("msg", "dm", "w"):
        parts = arg.split(None, 1)
        if len(parts) < 2:
            return Packet.error("Usage: /msg <user> <message>")
        return Packet(action=Action.DM, target=parts[0], content=parts[1])
    if cmd == "reply":
        parts = arg.split(None, 1)
        if len(parts) < 2:
            return Packet.error("Usage: /reply <msg_id> <message>")
        try:
            mid = int(parts[0])
        except ValueError:
            return Packet.error("msg_id must be an integer.")
        return Packet(action=Action.REPLY, msg_id=mid, content=parts[1])
    if cmd == "edit":
        parts = arg.split(None, 1)
        if len(parts) < 2:
            return Packet.error("Usage: /edit <msg_id> <new_content>")
        try:
            mid = int(parts[0])
        except ValueError:
            return Packet.error("msg_id must be an integer.")
        return Packet(action=Action.EDIT, msg_id=mid, content=parts[1])
    if cmd == "delete":
        return Packet(action=Action.DELETE, msg_id=int(arg) if arg.isdigit() else 0)
    if cmd == "search":
        return Packet(action=Action.SEARCH, content=arg)
    if cmd == "history":
        return Packet(action=Action.HISTORY, room=arg or room)

    # ── voice ──
    if cmd == "call":
        return Packet(action=Action.CALL, target=arg)
    if cmd == "accept":
        return Packet(action=Action.CALL_ACCEPT, target=arg)
    if cmd == "reject":
        return Packet(action=Action.CALL_REJECT, target=arg)
    if cmd == "hangup":
        return Packet(action=Action.CALL_END)
    if cmd == "voicejoin":
        return Packet(action=Action.VOICE_JOIN, room=arg or room)
    if cmd == "voiceleave":
        return Packet(action=Action.VOICE_LEAVE, room=room)
    if cmd == "mute":
        return Packet(action=Action.MUTE)
    if cmd == "unmute":
        return Packet(action=Action.UNMUTE)

    # ── files ──
    if cmd == "upload":
        return Packet(action=Action.FILE_UPLOAD, data={"filepath": arg})
    if cmd == "download":
        return Packet(action=Action.FILE_DOWNLOAD, content=arg)
    if cmd == "files":
        return Packet(action=Action.FILE_LIST, room=room)

    # ── AI ──
    if cmd == "ai":
        parts = arg.split(None, 1)
        subcmd = parts[0].lower() if parts else ""
        subarg = parts[1] if len(parts) > 1 else ""
        if subcmd == "enable":
            return Packet(action=Action.AI_ENABLE, content=subarg or "openai")
        if subcmd == "ask":
            return Packet(action=Action.AI_ASK, content=subarg)
        if subcmd == "summarize":
            return Packet(action=Action.AI_SUMMARIZE)
        if subcmd == "usage":
            return Packet(action=Action.AI_USAGE)
        if subcmd == "budget":
            return Packet(action=Action.AI_BUDGET, content=subarg)
        if subcmd == "limit":
            return Packet(action=Action.AI_LIMIT, content=subarg)
        return Packet.error("Usage: /ai <enable|ask|summarize|usage|budget|limit>")

    # ── moderation ──
    if cmd == "kick":
        return Packet(action=Action.KICK, target=arg)
    if cmd == "ban":
        return Packet(action=Action.BAN, target=arg)
    if cmd == "unban":
        return Packet(action=Action.UNBAN, target=arg)
    if cmd == "muteuser":
        parts = arg.split(None, 1)
        return Packet(action=Action.MUTE_USER, target=parts[0] if parts else "",
                      content=parts[1] if len(parts) > 1 else "")
    if cmd == "unmuteuser":
        return Packet(action=Action.UNMUTE_USER, target=arg)
    if cmd == "role":
        return Packet(action=Action.ADMIN, target="", content=arg)

    # ── status ──
    if cmd == "status":
        return Packet(action=Action.STATUS, content=arg)

    # ── help ──
    if cmd == "help":
        return Packet(action=Action.SYSTEM, content="__HELP__")

    return Packet.error(f"Unknown command: /{cmd}. Try /help.")


HELP_TEXT = """
[bold cyan]CLARA Commands[/]

[yellow]Connection:[/]  /whoami  /quit
[yellow]Rooms:[/]       /join <room>  /leave  /create <room>  /rooms  /users  /who
[yellow]Chat:[/]        /msg <user> <text>  /reply <id> <text>  /edit <id> <text>  /delete <id>
                /search <query>  /history [room]
[yellow]Voice:[/]       /call <user>  /accept <user>  /reject <user>  /hangup
                /voicejoin [room]  /voiceleave  /mute  /unmute
[yellow]Files:[/]       /upload <path>  /download <id>  /files
[yellow]AI:[/]          /ai enable [provider]  /ai ask <question>  /ai summarize
                /ai usage  /ai budget <$>  /ai limit <n>
[yellow]Mod:[/]         /kick <user>  /ban <user>  /unban <user>
                /muteuser <user> [min]  /unmuteuser <user>  /role <user> <role>
[yellow]Status:[/]      /status <online|away|busy>

Type text without / to send a chat message.
""".strip()
