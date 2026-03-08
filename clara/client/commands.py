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


# Each entry: (command, syntax, example, description)
HELP_ENTRIES: list[tuple[str, str, str, str]] = [
    # ── Connection ──────────────────────────────────────────────────────────
    ("Connection", "/whoami",                  "/whoami",                           "Show your logged-in username"),
    ("Connection", "/quit",                    "/quit",                             "Disconnect and exit CLARA"),

    # ── Rooms ───────────────────────────────────────────────────────────────
    ("Rooms",      "/create <room>",           "/create dev",                       "Create a new room named <room>"),
    ("Rooms",      "/join <room>",             "/join dev",                         "Join an existing room"),
    ("Rooms",      "/leave",                   "/leave",                            "Leave the current room"),
    ("Rooms",      "/rooms",                   "/rooms",                            "List all available rooms"),
    ("Rooms",      "/users",                   "/users",                            "List users in the current room"),
    ("Rooms",      "/who",                     "/who",                              "Show all online users + their status"),

    # ── Chat ────────────────────────────────────────────────────────────────
    ("Chat",       "<message>",               "hello everyone!",                   "Send a message to the current room (no slash needed)"),
    ("Chat",       "/msg <user> <text>",       "/msg alice hey, are you there?",     "Send a private direct message"),
    ("Chat",       "/reply <id> <text>",       "/reply 42 yes, I agree!",           "Reply to a specific message by ID"),
    ("Chat",       "/edit <id> <text>",        "/edit 42 corrected message",        "Edit one of your own messages"),
    ("Chat",       "/delete <id>",             "/delete 42",                        "Delete one of your own messages"),
    ("Chat",       "/history [room]",          "/history dev",                      "Show recent message history for a room"),
    ("Chat",       "/search <query>",          "/search launch codes",              "Search messages across the current room"),

    # ── Voice ───────────────────────────────────────────────────────────────
    ("Voice",      "/call <user>",             "/call alice",                       "Start a P2P voice call with a user"),
    ("Voice",      "/accept <user>",           "/accept spider",                    "Accept an incoming call"),
    ("Voice",      "/reject <user>",           "/reject spider",                    "Reject an incoming call"),
    ("Voice",      "/hangup",                  "/hangup",                           "End the current active call"),
    ("Voice",      "/voicejoin [room]",        "/voicejoin dev",                    "Join a voice room (multi-user)"),
    ("Voice",      "/voiceleave",             "/voiceleave",                       "Leave the current voice room"),
    ("Voice",      "/mute",                   "/mute",                             "Mute your microphone in a voice room"),
    ("Voice",      "/unmute",                 "/unmute",                           "Unmute your microphone"),

    # ── Files ───────────────────────────────────────────────────────────────
    ("Files",      "/upload <path>",           "/upload /tmp/report.pdf",           "Upload a local file to the current room (max 50 MB)"),
    ("Files",      "/files",                   "/files",                            "List files shared in the current room"),
    ("Files",      "/download <id>",           "/download a3f9c2",                  "Download a shared file by its ID"),

    # ── AI Gateway ──────────────────────────────────────────────────────────
    ("AI",         "/ai enable [provider]",    "/ai enable openai",                 "Enable the AI gateway (providers: openai · claude · openrouter)"),
    ("AI",         "/ai ask <question>",       "/ai ask what is quantum computing?", "Ask the AI a question"),
    ("AI",         "/ai summarize",            "/ai summarize",                     "Summarise recent room messages with AI"),
    ("AI",         "/ai usage",                "/ai usage",                         "Show your AI token + cost usage"),
    ("AI",         "/ai budget <amount>",      "/ai budget 5.00",                   "Set your AI spend budget in USD"),
    ("AI",         "/ai limit <n>",            "/ai limit 200",                     "Set your max token limit per request"),

    # ── Moderation ──────────────────────────────────────────────────────────
    ("Moderation", "/kick <user>",             "/kick bob",                         "Remove a user from the current room (not banned)"),
    ("Moderation", "/ban <user>",              "/ban bob",                          "Permanently ban a user from the server"),
    ("Moderation", "/unban <user>",            "/unban bob",                        "Lift a ban from a user"),
    ("Moderation", "/muteuser <user> [min]",   "/muteuser alice 10",                "Silence a user in the room (optional: duration in minutes)"),
    ("Moderation", "/unmuteuser <user>",       "/unmuteuser alice",                 "Remove a mute from a user"),
    ("Moderation", "/role <user> <role>",      "/role alice admin",                 "Set a user's role (owner › admin › moderator › member)"),

    # ── Presence / Status ────────────────────────────────────────────────────
    ("Status",     "/status <text>",           "/status coding away",               "Set your presence status message"),
]

# Legacy flat string kept for any fallback rendering
HELP_TEXT = "\n".join(
    f"  {syntax:<35} {example:<40} # {desc}"
    for _, syntax, example, desc in HELP_ENTRIES
)
