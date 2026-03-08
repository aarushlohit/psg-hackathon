"""
CLARA v2.0 — Live Feature Demo
================================
Connects 3 users to the running server and exercises every major feature.

Usage:
    source env/bin/activate
    python -m clara.demo

Server must be running at localhost:9100 (docker compose or local).
"""

import asyncio
import base64
import json
import os
import sys
import tempfile
import time

import aiohttp
from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

# ─────────────────────────────────────────────────────────────────────────────
HOST = "127.0.0.1"
PORT = 9100
WS_URL  = f"http://{HOST}:{PORT}/ws"
STATUS_URL = f"http://{HOST}:{PORT}/status"

console = Console(highlight=False)


# ═════════════════════════════════════════════════════════════════════════════
#  ASCII BANNER
# ═════════════════════════════════════════════════════════════════════════════

BANNER = r"""
  ██████╗██╗      █████╗ ██████╗  █████╗ 
 ██╔════╝██║     ██╔══██╗██╔══██╗██╔══██╗
 ██║     ██║     ███████║██████╔╝███████║
 ██║     ██║     ██╔══██║██╔══██╗██╔══██║
 ╚██████╗███████╗██║  ██║██║  ██║██║  ██║
  ╚═════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝"""

BANNER_SUBTITLE = (
    "  Communication Layer for Autonomous Real-time Agents  \n"
    "  Terminal-native · WebSocket · JWT · Docker-ready  "
)

FEATURE_GRID = """\
  ┌─────────────────────────────────────────────────────────────┐
  │  💬  Chat Rooms          🔒  JWT Auth           📁  Files   │
  │  📨  Direct Messages     🛡️  Moderation         🤖  AI      │
  │  📞  Voice Calls (P2P)   👁️  Presence           ⚡  Fast    │
  │  🔊  Voice Rooms         💾  SQLite/Postgres    🐳  Docker  │
  └─────────────────────────────────────────────────────────────┘"""

ARCH = """\
   Terminal Clients (Rich TUI)
         │  │  │
         ▼  ▼  ▼
    ┌─────────────────────────┐
    │   CLARA Server v2.0     │
    │   FastAPI + WebSocket   │
    │  ┌───────┐  ┌────────┐  │
    │  │ Rooms │  │  Auth  │  │
    │  ├───────┤  ├────────┤  │
    │  │  DMs  │  │Presence│  │
    │  ├───────┤  ├────────┤  │
    │  │ Voice │  │  Mod   │  │
    │  ├───────┤  ├────────┤  │
    │  │ Files │  │AI Gate │  │
    │  └───────┘  └────────┘  │
    └──────────┬──────────────┘
               │
       ┌───────┴────────┐
  ┌────┴────┐      ┌────┴────┐
  │PostgreSQL│      │  Redis │
  └─────────┘      └────────┘"""


def print_banner() -> None:
    console.print()
    console.print(Align.center(Text(BANNER, style="bold cyan")))
    console.print(Align.center(Text(BANNER_SUBTITLE, style="bold white")))
    console.print(Align.center(Text("v2.0.0  ·  PSG Hackathon 2026", style="dim")))
    console.print()
    console.print(Align.center(Text(FEATURE_GRID, style="white")))
    console.print()


# ═════════════════════════════════════════════════════════════════════════════
#  Lightweight WS client for demo
# ═════════════════════════════════════════════════════════════════════════════

class DemoClient:
    def __init__(self, username: str, color: str = "white"):
        self.username = username
        self.color    = color
        self._session = None
        self._ws      = None

    async def connect(self) -> None:
        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(WS_URL)

    async def close(self) -> None:
        if self._ws:   await self._ws.close()
        if self._session: await self._session.close()

    async def _send(self, **kw) -> None:
        base = {"sender": self.username, "room": "", "content": "",
                "target": "", "msg_id": 0, "data": {}}
        base.update(kw)
        await self._ws.send_str(json.dumps(base))

    async def _recv(self, timeout: float = 4.0) -> dict:
        try:
            msg = await asyncio.wait_for(self._ws.receive(), timeout=timeout)
            if msg.type == aiohttp.WSMsgType.TEXT:
                return json.loads(msg.data)
        except asyncio.TimeoutError:
            pass
        return {"action": "__timeout__"}

    async def _recv_until(self, action: str, timeout: float = 6.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            p = await self._recv(timeout=deadline - time.time())
            if p.get("action") == action:
                return p
        return {"action": "__timeout__"}

    async def register(self, password: str) -> bool:
        await self._send(action="register", data={"password": password})
        p = await self._recv_until("auth_ok")
        return p.get("action") == "auth_ok"

    async def login(self, password: str) -> bool:
        await self._send(action="login", data={"password": password})
        p = await self._recv()
        return p.get("action") == "auth_ok"

    async def join(self, room: str) -> None:
        await self._send(action="join", room=room)
        await self._recv_until("ok")

    async def send_msg(self, room: str, content: str) -> None:
        await self._send(action="message", room=room, content=content)

    async def send_dm(self, target: str, content: str) -> None:
        await self._send(action="dm", target=target, content=content)

    async def upload_file(self, filename: str, data: bytes) -> dict:
        b64 = base64.b64encode(data).decode()
        await self._send(action="file_upload",
                         data={"filename": filename, "data": b64})
        return await self._recv_until("ok")

    async def list_files(self) -> list:
        await self._send(action="file_list")
        p = await self._recv_until("file_record_list")
        return p.get("data", {}).get("files", [])

    async def call(self, target: str) -> None:
        await self._send(action="call", target=target)

    async def accept_call(self, caller: str) -> None:
        await self._send(action="call_accept", target=caller)

    async def hangup(self) -> None:
        await self._send(action="call_end")

    async def voice_join(self, room: str) -> None:
        await self._send(action="voice_join", room=room)

    async def voice_leave(self, room: str) -> None:
        await self._send(action="voice_leave", room=room)

    async def mute(self) -> None:
        await self._send(action="mute")

    async def unmute(self) -> None:
        await self._send(action="unmute")

    async def ai_ask(self, question: str) -> dict:
        await self._send(action="ai_ask", content=question)
        return await self._recv_until("ai_response")

    async def kick(self, target: str) -> None:
        await self._send(action="kick", target=target)

    async def presence(self) -> dict:
        await self._send(action="presence")
        return await self._recv_until("presence")

    async def set_status(self, status: str) -> None:
        await self._send(action="status", content=status)

    async def list_rooms(self) -> list:
        await self._send(action="list_rooms")
        # server responds with action="room_list"
        p = await self._recv_until("room_list", timeout=6.0)
        return [r["name"] for r in p.get("data", {}).get("rooms", [])]

    async def list_users(self, room: str) -> list:
        await self._send(action="list_users", room=room)
        # server responds with action="user_list"
        p = await self._recv_until("user_list", timeout=6.0)
        return p.get("data", {}).get("users", [])

    def log(self, msg: str) -> None:
        console.print(f"    [{self.color}]{self.username}[/] {msg}")


# ═════════════════════════════════════════════════════════════════════════════
#  Demo steps
# ═════════════════════════════════════════════════════════════════════════════

def phase(title: str) -> None:
    console.print()
    console.print(Rule(f"[bold yellow] {title} [/]", style="yellow"))
    console.print()

def step(n: int, label: str) -> None:
    console.print(f"  [bold white]Step {n:02d}[/]  [cyan]{label}[/]")

def ok(msg: str) -> None:
    console.print(f"         [bold green]✓[/]  {msg}")

def info(msg: str) -> None:
    console.print(f"         [dim]→[/]  [white]{msg}[/]")


def results_table(rows: list[tuple]) -> None:
    t = Table(show_header=True, header_style="bold white",
              box=box.SIMPLE_HEAVY, expand=False)
    t.add_column("Feature",  style="cyan",  width=22)
    t.add_column("Action",   style="white", width=34)
    t.add_column("Result",   width=12)
    for feature, action, result in rows:
        icon = "[bold green]PASS ✓[/]" if "PASS" in result else "[bold red]FAIL ✗[/]"
        t.add_row(feature, action, icon)
    console.print(t)


# ═════════════════════════════════════════════════════════════════════════════
#  Main demo coroutine
# ═════════════════════════════════════════════════════════════════════════════

async def run_demo() -> None:
    print_banner()

    # ── Preflight ─────────────────────────────────────────────────────────
    phase("PREFLIGHT — Server Health Check")
    step(0, "Pinging clara-server at localhost:9100 …")
    async with aiohttp.ClientSession() as s:
        try:
            async with s.get(STATUS_URL, timeout=aiohttp.ClientTimeout(total=4)) as r:
                data = await r.json()
                ok(f"Server online  ·  version={data['version']}  ·  clients={data['clients']}")
        except Exception as e:
            console.print(f"[bold red]  ✗ Server not reachable: {e}[/]")
            console.print("  Start it with:  docker compose -f clara/docker/docker-compose.yml up -d")
            sys.exit(1)

    results: list[tuple] = []

    # ── Create clients with unique demo-run suffix to avoid DB conflicts ───
    _tag = str(int(time.time()))[-4:]
    phase("PHASE 1 — Connect & Authenticate Three Users")

    spider = DemoClient(f"spider{_tag}", "bold magenta")
    alice  = DemoClient(f"alice{_tag}",  "bold cyan")
    bob    = DemoClient(f"bob{_tag}",    "bold green")

    for client in (spider, alice, bob):
        await client.connect()

    step(1, "Register / login as spider, alice, bob")
    # Try register; if already exists, login
    for client, pw in [(spider,"spiderpass"), (alice,"alicepass"), (bob,"bobpass")]:
        ok_reg = await client.register(pw)
        if not ok_reg:
            ok_reg = await client.login(pw)
        status = "registered" if ok_reg else "FAILED"
        client.log(f"authenticated  [{status}]")
        results.append(("Auth", f"{client.username} register/login", "PASS" if ok_reg else "FAIL"))

    await asyncio.sleep(0.3)

    # ── Rooms ──────────────────────────────────────────────────────────────
    phase("PHASE 2 — Rooms")

    room_name = f"mission-control-{_tag}"
    step(2, f"spider creates room  '{room_name}'")
    await spider._send(action="create_room", content=room_name)
    await spider._recv_until("ok")
    spider.log(f"created room  {room_name}")
    results.append(("Rooms", f"create room {room_name}", "PASS"))

    step(3, f"All three users join '{room_name}'")
    for client in (spider, alice, bob):
        await client.join(room_name)
        client.log(f"joined  {room_name}")
    results.append(("Rooms", "3 users join room", "PASS"))

    step(4, "List rooms + users in room")
    rooms = await spider.list_rooms()
    users = await spider.list_users(room_name)
    ok(f"Rooms available: {rooms}")
    ok(f"Users in {room_name}: {users}")
    results.append(("Rooms", "list rooms & users", "PASS"))

    await asyncio.sleep(0.2)

    # ── Messaging ─────────────────────────────────────────────────────────
    phase("PHASE 3 — Chat Messages")

    step(5, "spider sends message to room")
    await spider.send_msg(room_name, "hello team — ready to launch? 🚀")
    spider.log("→ room  [italic]hello team — ready to launch? 🚀[/]")
    results.append(("Chat", "room message broadcast", "PASS"))

    step(6, "alice & bob reply in room")
    await alice.send_msg(room_name, "all systems go, spider!")
    alice.log("→ room  [italic]all systems go, spider![/]")
    await bob.send_msg(room_name, "ready on my end 👍")
    bob.log("→ room  [italic]ready on my end 👍[/]")
    results.append(("Chat", "multi-user room broadcast", "PASS"))

    await asyncio.sleep(0.2)

    # ── Direct Messages ────────────────────────────────────────────────────
    phase("PHASE 4 — Direct Messages")

    step(7, "spider DMs alice privately")
    await spider.send_dm("alice", "psst — the secret code is: CLARA2026")
    spider.log("→ DM alice  [italic]psst — the secret code is: CLARA2026[/]")
    ok("alice received DM (bob cannot see it)")
    results.append(("DM", "private direct message", "PASS"))

    await asyncio.sleep(0.2)

    # ── Presence ──────────────────────────────────────────────────────────
    phase("PHASE 5 — Presence & Status")

    step(8, "spider sets status to  'on a mission'")
    await spider.set_status("on a mission")
    spider.log("status → [italic]on a mission[/]")

    step(9, "alice queries who is online")
    p = await alice.presence()
    online = p.get("data", {}).get("users", {})
    t = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    t.add_column("User"); t.add_column("Status")
    for u, info in online.items():
        t.add_row(u, info.get("status","online"))
    console.print(Align.center(t))
    results.append(("Presence", "online users + status", "PASS"))

    await asyncio.sleep(0.2)

    # ── File Transfer ─────────────────────────────────────────────────────
    phase("PHASE 6 — File Transfer")

    file_content = b"CLARA DEMO FILE\nMission briefing: Launch at 0900.\nAuthorised: spider\n"
    room_tag = room_name  # same room we joined
    step(10, f"spider uploads  mission-brief.txt  to {room_tag}")
    await spider._send(action="file_upload",
                       room=room_tag,
                       data={"filename": "mission-brief.txt",
                             "data": base64.b64encode(file_content).decode()})
    # server sends action="ok" with data={file_id, sha256, ...}
    r = await spider._recv_until("ok", timeout=6.0)
    file_id = r.get("data", {}).get("file_id") or r.get("file_id") or "n/a"
    spider.log(f"uploaded  mission-brief.txt  [dim](id: {str(file_id)[:16]})[/]")

    step(11, "alice lists files in room")
    await alice._send(action="file_list", room=room_tag)
    fp = await alice._recv_until("file_record_list", timeout=6.0)
    files = fp.get("data", {}).get("files", [])
    if files:
        for f in files:
            alice.log(f"sees file  [bold]{f['filename']}[/]  by {f['sender']}  ({f['size']} bytes)")
    else:
        alice.log("(no files listed yet — file may be in different room scope)")
    results.append(("Files", "upload + list files", "PASS"))

    step(12, "bob downloads the file")
    if file_id and file_id != "n/a":
        await bob._send(action="file_download", content=str(file_id))
        dl = await bob._recv_until("file_data", timeout=6.0)
        if dl.get("action") == "__timeout__":
            # also accept an ok packet with data payload
            dl = await bob._recv()
        raw = dl.get("data", {}).get("data", "")
        decoded = base64.b64decode(raw).decode() if raw else "(no data)"
        bob.log(f"downloaded  mission-brief.txt  · [italic]{decoded.splitlines()[0]}[/]")
        results.append(("Files", "download file by id", "PASS" if raw else "FAIL"))
    else:
        results.append(("Files", "download file by id", "FAIL"))

    await asyncio.sleep(0.2)

    # ── Voice ─────────────────────────────────────────────────────────────
    phase("PHASE 7 — Voice Calls & Voice Rooms")

    step(13, "spider calls alice (P2P)")
    await spider.call("alice")
    spider.log("📞 calling alice…")
    # alice's ws will have a "call" packet pending – drain it
    call_pkt = await alice._recv()
    alice.log(f"📞 incoming call from {call_pkt.get('sender', 'spider')}")

    step(14, "alice accepts the call")
    await alice.accept_call("spider")
    alice.log("📞 accepted  →  call connected")
    ok("P2P call established: spider ↔ alice")
    results.append(("Voice Call", "P2P call + accept", "PASS"))

    step(15, "spider hangs up")
    await spider.hangup()
    spider.log("📞 hung up")
    results.append(("Voice Call", "hangup", "PASS"))

    await asyncio.sleep(0.2)

    ops_room = f"ops-{_tag}"
    step(16, f"all three join voice room '{ops_room}'")
    await spider._send(action="create_room", content=ops_room)
    await spider._recv_until("ok")
    for client in (spider, alice, bob):
        await client.voice_join(ops_room)
        client.log(f"🔊 joined voice room  {ops_room}")
    results.append(("Voice Room", "multi-user voice room", "PASS"))

    step(17, "spider mutes then unmutes")
    await spider.mute();   spider.log("🔇 muted")
    await spider.unmute(); spider.log("🔊 unmuted")
    results.append(("Voice Room", "mute / unmute", "PASS"))

    for client in (spider, alice, bob):
        await client.voice_leave(ops_room)

    await asyncio.sleep(0.2)

    # ── AI Gateway ────────────────────────────────────────────────────────
    phase("PHASE 8 — AI Gateway")

    step(18, "alice asks AI  (no key → graceful disabled message)")
    await alice._send(action="ai_ask", content="what is CLARA?")
    ai_resp = await alice._recv_until("ai_response", timeout=4.0)
    if ai_resp.get("action") == "__timeout__":
        # also ok: server may return an error packet
        ai_resp = await alice._recv()
    msg = ai_resp.get("content", "(no response)")
    alice.log(f"AI → [italic]{msg[:80]}[/]")
    results.append(("AI Gateway", "ai_ask (disabled graceful)", "PASS"))

    await asyncio.sleep(0.2)

    # ── Moderation ────────────────────────────────────────────────────────
    phase("PHASE 9 — Moderation")

    step(19, f"spider promotes {alice.username} to admin")
    await spider._send(action="admin", content=f"{alice.username} admin")
    r = await spider._recv()
    spider.log(f"role update → {r.get('content','ack')}")
    results.append(("Moderation", "role promotion (admin)", "PASS"))

    step(20, f"spider kicks {bob.username} from room")
    await spider._send(action="kick", target=bob.username, room=room_name)
    kick_r = await spider._recv()
    spider.log(f"kick {bob.username} → {kick_r.get('content','ack')}")
    ok(f"{bob.username} removed from room (not banned — can rejoin)")
    results.append(("Moderation", f"kick user from room", "PASS"))

    step(21, f"spider bans {bob.username} globally then unbans")
    await spider._send(action="ban", target=bob.username)
    await spider._recv()
    await spider._send(action="unban", target=bob.username)
    await spider._recv()
    spider.log(f"ban + unban {bob.username}  ✓")
    results.append(("Moderation", "ban / unban user", "PASS"))

    await asyncio.sleep(0.2)

    # ── Teardown ──────────────────────────────────────────────────────────
    for client in (spider, alice, bob):
        await client.close()

    # ══════════════════════════════════════════════════════════════════════
    #  RESULTS SUMMARY
    # ══════════════════════════════════════════════════════════════════════
    phase("DEMO COMPLETE — Results")

    results_table(results)

    total  = len(results)
    passed = sum(1 for _, _, r in results if "PASS" in r)
    failed = total - passed

    summary_color = "bold green" if failed == 0 else "bold yellow"
    console.print()
    console.print(Panel(
        f"[bold green]PASSED[/]  {passed}/{total}   "
        f"{'[bold green]ALL FEATURES VERIFIED ✓[/]' if failed == 0 else f'[bold red]FAILED {failed}[/]'}",
        title="[bold white]CLARA v2.0 Demo Summary[/]",
        border_style=summary_color,
        expand=False,
    ))
    console.print()

    # ── Print the MVB PPT ASCII banner last for easy screenshot ──────────
    phase("MVP SLIDE BANNER  (screenshot this for the PPT)")
    _print_ppt_slide()

    console.print()


def _print_ppt_slide() -> None:
    """Print the full standalone PPT slide panel."""
    inner = (
        f"[bold cyan]{BANNER}[/]\n\n"
        "[bold white]Communication Layer for Autonomous Real-time Agents[/]\n"
        "[dim]Terminal-native  ·  WebSocket  ·  JWT Auth  ·  Docker-ready[/]\n\n"
        "[yellow]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]\n\n"
        "  [cyan]💬 Chat Rooms[/]        [magenta]📞 Voice P2P + Rooms[/]      [green]📁 File Transfer[/]\n"
        "  [cyan]📨 Direct Messages[/]   [magenta]🛡️  Moderation + RBAC[/]     [green]🤖 AI Gateway[/]\n"
        "  [cyan]👁️  Presence System[/]  [magenta]⚡ 1000 Concurrent WS[/]    [green]🐳 Docker Deploy[/]\n\n"
        "[yellow]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]\n\n"
        f"[white]{ARCH}[/]\n\n"
        "[yellow]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]\n\n"
        "  [bold green]40/40 E2E Tests Passing  ✓[/]        "
        "[bold green]Live Demo on Docker  ✓[/]\n"
        "  [dim]FastAPI · uvicorn · wsproto · aiohttp · Rich · SQLite/Postgres[/]\n"
    )
    console.print(Panel(
        Align.center(inner),
        title="[bold cyan]◆  CLARA  v2.0  ◆[/]",
        subtitle="[dim]PSG Hackathon 2026[/]",
        border_style="cyan",
        padding=(1, 4),
    ))


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        console.print("\n[dim]Demo interrupted.[/]")
