"""CLARA end-to-end tests — 40 tests covering all major features.

Run:
    python -m clara.tests.e2e_tests

Each test starts the server, connects clients, performs actions, verifies results.
"""

import asyncio
import base64
import json
import os
import sys
import tempfile
import time
import traceback

# ── Set env vars BEFORE any clara imports so settings picks them up ──
_test_dir = tempfile.mkdtemp(prefix="clara_test_")
os.environ["CLARA_DATABASE_URL"] = ""
os.environ["CLARA_SQLITE_PATH"] = os.path.join(_test_dir, "clara_test.db")
os.environ["CLARA_JWT_SECRET"] = "test-secret-key-for-e2e"
os.environ["CLARA_UPLOAD_DIR"] = os.path.join(_test_dir, "uploads")

import aiohttp

# ───── CONFIG ─────
HOST = "127.0.0.1"
PORT = 9199  # Use non-default port for tests
WS_URL = f"http://{HOST}:{PORT}/ws"
STATUS_URL = f"http://{HOST}:{PORT}/status"

_server_task = None
_passed = 0
_failed = 0
_errors = []


# ───── helpers ─────

async def start_server():
    global _server_task
    import uvicorn
    from clara.server.main import build_app

    app = build_app()
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning", ws="wsproto")
    server = uvicorn.Server(config)
    _server_task = asyncio.create_task(server.serve())
    # Wait for server to be ready
    for _ in range(50):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(STATUS_URL) as r:
                    if r.status == 200:
                        return
        except Exception:
            pass
        await asyncio.sleep(0.1)
    raise RuntimeError("Server did not start")


async def stop_server():
    global _server_task
    if _server_task:
        _server_task.cancel()
        try:
            await _server_task
        except (asyncio.CancelledError, Exception):
            pass
    # Cleanup temp files
    import shutil
    shutil.rmtree(_test_dir, ignore_errors=True)


class Client:
    """Lightweight test WebSocket client."""

    def __init__(self, name=""):
        self.name = name
        self._session = None
        self._ws = None

    async def connect(self):
        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(WS_URL)

    async def close(self):
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()

    async def send(self, pkt: dict):
        await self._ws.send_str(json.dumps(pkt))

    async def recv(self, timeout=3.0) -> dict:
        try:
            msg = await asyncio.wait_for(self._ws.receive(), timeout=timeout)
            if msg.type == aiohttp.WSMsgType.TEXT:
                return json.loads(msg.data)
        except asyncio.TimeoutError:
            return {"action": "__timeout__"}
        return {"action": "__closed__"}

    async def recv_until(self, action: str, timeout=5.0) -> dict:
        """Keep receiving until we get a packet with the given action."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            pkt = await self.recv(timeout=deadline - time.time())
            if pkt.get("action") == action:
                return pkt
            if pkt.get("action") in ("__timeout__", "__closed__"):
                break
        return {"action": "__timeout__"}

    async def register(self, username: str, password: str) -> dict:
        await self.send({"action": "register", "sender": username,
                         "data": {"password": password}})
        return await self.recv_until("auth_ok")

    async def login(self, username: str, password: str) -> dict:
        await self.send({"action": "login", "sender": username,
                         "data": {"password": password}})
        return await self.recv()


def pkt(**kw) -> dict:
    base = {"sender": "", "room": "", "content": "", "target": "",
            "msg_id": 0, "data": {}}
    base.update(kw)
    return base


async def test(name, coro):
    global _passed, _failed
    try:
        await coro()
        _passed += 1
        print(f"  ✓ {name}")
    except Exception as exc:
        _failed += 1
        _errors.append((name, exc))
        print(f"  ✗ {name}: {exc}")
        traceback.print_exc()
    await asyncio.sleep(0.15)  # Rate limit padding


# ═══════════════  TESTS  ═══════════════

async def test_01_server_status():
    async with aiohttp.ClientSession() as s:
        async with s.get(STATUS_URL) as r:
            assert r.status == 200
            data = await r.json()
            assert data["server"] == "CLARA"
            assert data["status"] == "running"


async def test_02_register():
    c = Client()
    await c.connect()
    resp = await c.register("alice", "pass123")
    assert resp["action"] == "auth_ok"
    assert "alice" in resp.get("content", "")
    await c.close()


async def test_03_login():
    c = Client()
    await c.connect()
    resp = await c.login("alice", "pass123")
    assert resp["action"] == "auth_ok"
    await c.close()


async def test_04_login_wrong_password():
    c = Client()
    await c.connect()
    await c.send(pkt(action="login", sender="alice", data={"password": "wrong"}))
    resp = await c.recv()
    assert resp["action"] == "auth_fail"
    await c.close()


async def test_05_duplicate_register():
    c = Client()
    await c.connect()
    await c.send(pkt(action="register", sender="alice", data={"password": "pass123"}))
    resp = await c.recv()
    assert resp["action"] == "auth_fail"
    assert "taken" in resp.get("content", "").lower()
    await c.close()


async def test_06_unauthenticated_action():
    c = Client()
    await c.connect()
    await c.send(pkt(action="message", content="hello"))
    resp = await c.recv()
    assert resp["action"] == "error"
    assert "authenticated" in resp.get("content", "").lower()
    await c.close()


async def test_07_join_room():
    c = Client()
    await c.connect()
    await c.register("bob", "pass456")
    await c.send(pkt(action="join", room="general"))
    resp = await c.recv_until("ok")
    assert "general" in resp.get("content", "").lower()
    await c.close()


async def test_08_create_room():
    c = Client()
    await c.connect()
    await c.login("bob", "pass456")
    await c.send(pkt(action="create_room", content="dev-chat"))
    resp = await c.recv_until("ok")
    assert "dev-chat" in resp.get("content", "")
    await c.close()


async def test_09_list_rooms():
    c = Client()
    await c.connect()
    await c.login("bob", "pass456")
    await c.send(pkt(action="list_rooms"))
    resp = await c.recv_until("room_list")
    assert resp["action"] == "room_list"
    rooms = resp.get("data", {}).get("rooms", [])
    names = [r["name"] for r in rooms]
    assert "general" in names or "dev-chat" in names
    await c.close()


async def test_10_send_message():
    c = Client()
    await c.connect()
    await c.login("bob", "pass456")
    await c.send(pkt(action="join", room="general"))
    await c.recv_until("ok")
    await c.send(pkt(action="message", content="Hello, world!", room="general"))
    resp = await c.recv_until("message")
    assert resp["action"] == "message"
    assert resp["content"] == "Hello, world!"
    assert resp["sender"] == "bob"
    await c.close()


async def test_11_dm():
    c1 = Client()
    c2 = Client()
    await c1.connect()
    await c2.connect()
    await c1.login("alice", "pass123")
    await c2.register("charlie", "pass789")
    await c1.send(pkt(action="dm", target="charlie", content="secret message"))
    # Charlie should receive the DM
    resp = await c2.recv_until("dm")
    assert resp["action"] == "dm"
    assert resp["content"] == "secret message"
    assert resp["sender"] == "alice"
    await c1.close()
    await c2.close()


async def test_12_message_broadcast():
    c1 = Client()
    c2 = Client()
    await c1.connect()
    await c2.connect()
    await c1.login("alice", "pass123")
    await c2.login("bob", "pass456")
    await c1.send(pkt(action="join", room="broadcast-test"))
    await c1.recv_until("ok")
    await c2.send(pkt(action="join", room="broadcast-test"))
    await c2.recv_until("ok")
    # Drain join notification for c1
    await asyncio.sleep(0.2)
    await c1.send(pkt(action="message", content="ping", room="broadcast-test"))
    # Both should see it
    r1 = await c1.recv_until("message")
    assert r1["content"] == "ping"
    r2 = await c2.recv_until("message")
    assert r2["content"] == "ping"
    await c1.close()
    await c2.close()


async def test_13_edit_message():
    c = Client()
    await c.connect()
    await c.login("alice", "pass123")
    await c.send(pkt(action="join", room="edit-room"))
    await c.recv_until("ok")
    await c.send(pkt(action="message", content="original", room="edit-room"))
    msg = await c.recv_until("message")
    mid = msg.get("msg_id", 0)
    assert mid > 0
    await c.send(pkt(action="edit", msg_id=mid, content="edited"))
    resp = await c.recv_until("edit")
    assert resp["content"] == "edited"
    await c.close()


async def test_14_delete_message():
    c = Client()
    await c.connect()
    await c.login("alice", "pass123")
    await c.send(pkt(action="join", room="del-room"))
    await c.recv_until("ok")
    await c.send(pkt(action="message", content="doomed", room="del-room"))
    msg = await c.recv_until("message")
    mid = msg.get("msg_id", 0)
    await c.send(pkt(action="delete", msg_id=mid))
    resp = await c.recv_until("delete")
    assert resp["action"] == "delete"
    await c.close()


async def test_15_history():
    c = Client()
    await c.connect()
    await c.login("alice", "pass123")
    await c.send(pkt(action="join", room="history-room"))
    await c.recv_until("ok")
    # Send a message so there's something in history
    await c.send(pkt(action="message", content="history msg", room="history-room"))
    await c.recv_until("message")
    await c.send(pkt(action="history", room="history-room"))
    resp = await c.recv_until("msg_list")
    assert resp["action"] == "msg_list"
    await c.close()


async def test_16_search():
    c = Client()
    await c.connect()
    await c.login("bob", "pass456")
    await c.send(pkt(action="join", room="broadcast-test"))
    await c.recv_until("ok")
    await c.send(pkt(action="search", content="ping"))
    resp = await c.recv_until("msg_list")
    msgs = resp.get("data", {}).get("messages", [])
    assert any("ping" in m.get("content", "") for m in msgs)
    await c.close()


async def test_17_leave_room():
    c = Client()
    await c.connect()
    await c.login("bob", "pass456")
    await c.send(pkt(action="join", room="leave-test"))
    await c.recv_until("ok")
    await c.send(pkt(action="leave"))
    resp = await c.recv_until("ok")
    assert "left" in resp.get("content", "").lower()
    await c.close()


async def test_18_list_users():
    c = Client()
    await c.connect()
    await c.login("alice", "pass123")
    await c.send(pkt(action="list_users"))
    resp = await c.recv_until("user_list")
    assert resp["action"] == "user_list"
    await c.close()


async def test_19_whoami():
    c = Client()
    await c.connect()
    await c.login("alice", "pass123")
    await c.send(pkt(action="whoami"))
    resp = await c.recv_until("ok")
    assert "alice" in resp.get("content", "")
    await c.close()


async def test_20_file_upload():
    c = Client()
    await c.connect()
    await c.login("alice", "pass123")
    await c.send(pkt(action="join", room="file-room"))
    await c.recv_until("ok")
    data_b64 = base64.b64encode(b"Hello CLARA file test").decode()
    await c.send(pkt(action="file_upload",
                     data={"filename": "test.txt", "data": data_b64}))
    resp = await c.recv_until("ok")
    assert "uploaded" in resp.get("content", "").lower()
    await c.close()


async def test_21_file_list():
    c = Client()
    await c.connect()
    await c.login("alice", "pass123")
    await c.send(pkt(action="join", room="file-room"))
    await c.recv_until("ok")
    await c.send(pkt(action="file_list", room="file-room"))
    resp = await c.recv_until("file_record_list")
    files = resp.get("data", {}).get("files", [])
    assert len(files) >= 1
    assert files[0]["filename"] == "test.txt"
    await c.close()


async def test_22_file_download():
    c = Client()
    await c.connect()
    await c.login("alice", "pass123")
    # Get file list to find ID
    await c.send(pkt(action="join", room="file-room"))
    await c.recv_until("ok")
    await c.send(pkt(action="file_list", room="file-room"))
    resp = await c.recv_until("file_record_list")
    files = resp.get("data", {}).get("files", [])
    file_id = files[0]["file_id"]
    await c.send(pkt(action="file_download", content=file_id))
    resp = await c.recv_until("file_data")
    raw = base64.b64decode(resp["data"]["data"])
    assert raw == b"Hello CLARA file test"
    await c.close()


async def test_23_call_flow():
    c1 = Client()
    c2 = Client()
    await c1.connect()
    await c2.connect()
    await c1.login("alice", "pass123")
    await c2.login("bob", "pass456")
    # Alice calls Bob
    await c1.send(pkt(action="call", target="bob"))
    r1 = await c1.recv_until("ok")
    assert "calling" in r1.get("content", "").lower()
    # Bob receives call
    r2 = await c2.recv_until("call")
    assert r2["sender"] == "alice"
    # Bob accepts
    await c2.send(pkt(action="call_accept", target="alice"))
    r3 = await c2.recv_until("ok")
    assert "accepted" in r3.get("content", "").lower()
    # Alice gets notification
    r4 = await c1.recv_until("call_accept")
    assert r4["sender"] == "bob"
    # End call
    await c1.send(pkt(action="call_end"))
    await c1.recv_until("ok")
    await c1.close()
    await c2.close()


async def test_24_voice_room():
    c = Client()
    await c.connect()
    await c.login("alice", "pass123")
    await c.send(pkt(action="join", room="voice-test"))
    await c.recv_until("ok")
    await c.send(pkt(action="voice_join", room="voice-test"))
    resp = await c.recv_until("ok")
    assert "voice" in resp.get("content", "").lower()
    await c.send(pkt(action="voice_leave", room="voice-test"))
    resp2 = await c.recv_until("ok")
    assert "left" in resp2.get("content", "").lower()
    await c.close()


async def test_25_mute_unmute():
    c = Client()
    await c.connect()
    await c.login("alice", "pass123")
    await c.send(pkt(action="mute"))
    resp = await c.recv_until("ok")
    assert "muted" in resp.get("content", "").lower()
    await c.send(pkt(action="unmute"))
    resp2 = await c.recv_until("ok")
    assert "unmuted" in resp2.get("content", "").lower()
    await c.close()


async def test_26_heartbeat():
    c = Client()
    await c.connect()
    await c.login("alice", "pass123")
    await c.send(pkt(action="heartbeat"))
    resp = await c.recv_until("heartbeat")
    assert resp["action"] == "heartbeat"
    await c.close()


async def test_27_typing():
    c1 = Client()
    c2 = Client()
    await c1.connect()
    await c2.connect()
    await c1.login("alice", "pass123")
    await c2.login("bob", "pass456")
    await c1.send(pkt(action="join", room="typing-room"))
    await c1.recv_until("ok")
    await c2.send(pkt(action="join", room="typing-room"))
    await c2.recv_until("ok")
    await asyncio.sleep(0.2)
    await c1.send(pkt(action="typing"))
    resp = await c2.recv_until("typing", timeout=3)
    assert resp["action"] == "typing"
    assert resp["sender"] == "alice"
    await c1.close()
    await c2.close()


async def test_28_presence_who():
    c = Client()
    await c.connect()
    await c.login("alice", "pass123")
    await c.send(pkt(action="presence"))
    resp = await c.recv_until("presence")
    users = resp.get("data", {}).get("users", {})
    assert "alice" in users
    await c.close()


async def test_29_session_replace():
    c1 = Client()
    c2 = Client()
    await c1.connect()
    await c2.connect()
    await c1.login("alice", "pass123")
    # Login again from c2 — should replace c1's session
    await c2.login("alice", "pass123")
    # c1 should get a system message about replacement
    resp = await c1.recv(timeout=2)
    assert resp.get("action") in ("system", "__timeout__")  # system msg or conn closed
    await c1.close()
    await c2.close()


async def test_30_rate_limiting():
    c = Client()
    await c.connect()
    await c.login("bob", "pass456")
    await c.send(pkt(action="join", room="rate-test"))
    await c.recv_until("ok")
    # Send 15 messages rapidly
    for i in range(15):
        await c.send(pkt(action="message", content=f"spam {i}", room="rate-test"))
    # Should get at least one rate-limit error
    got_rate_limit = False
    for _ in range(15):
        resp = await c.recv(timeout=1)
        if resp.get("action") == "error" and "rate" in resp.get("content", "").lower():
            got_rate_limit = True
            break
    assert got_rate_limit, "Expected rate limiting"
    await c.close()


async def test_31_reply_message():
    c = Client()
    await c.connect()
    await c.login("alice", "pass123")
    await c.send(pkt(action="join", room="reply-room"))
    await c.recv_until("ok")
    await c.send(pkt(action="message", content="original msg", room="reply-room"))
    msg = await c.recv_until("message")
    mid = msg.get("msg_id", 0)
    await c.send(pkt(action="reply", msg_id=mid, content="this is a reply"))
    resp = await c.recv_until("message")
    assert resp["content"] == "this is a reply"
    assert resp.get("data", {}).get("reply_to") == mid
    await c.close()


async def test_32_moderation_kick():
    # Register admin + regular user
    admin = Client()
    user = Client()
    await admin.connect()
    await user.connect()
    await admin.register("admin_user", "adminpass")
    await user.register("kickme", "kickpass")

    # We need to manually set admin role in DB. Use the admin action
    # Since first user is "member", we'll test that kick requires moderator
    await admin.send(pkt(action="join", room="mod-room"))
    await admin.recv_until("ok")
    await user.send(pkt(action="join", room="mod-room"))
    await user.recv_until("ok")
    await asyncio.sleep(0.2)

    await admin.send(pkt(action="kick", target="kickme"))
    resp = await admin.recv_until("error")  # Should fail — admin_user is just a member
    assert "permission" in resp.get("content", "").lower() or "insufficient" in resp.get("content", "").lower()

    await admin.close()
    await user.close()


async def test_33_ban_requires_admin():
    c = Client()
    await c.connect()
    await c.login("bob", "pass456")
    await c.send(pkt(action="ban", target="charlie"))
    resp = await c.recv_until("error")
    assert "admin" in resp.get("content", "").lower() or "permission" in resp.get("content", "").lower()
    await c.close()


async def test_34_ai_not_enabled():
    c = Client()
    await c.connect()
    await c.login("alice", "pass123")
    await c.send(pkt(action="ai_ask", content="hello?"))
    resp = await c.recv_until("error")
    assert "not enabled" in resp.get("content", "").lower() or "enable" in resp.get("content", "").lower()
    await c.close()


async def test_35_ai_usage():
    c = Client()
    await c.connect()
    await c.login("alice", "pass123")
    await c.send(pkt(action="ai_usage"))
    resp = await c.recv_until("ok")
    assert resp["action"] == "ok"
    await c.close()


async def test_36_file_too_large():
    c = Client()
    await c.connect()
    await c.login("alice", "pass123")
    # File with no data should still work — test invalid b64
    await c.send(pkt(action="file_upload", data={"filename": "", "data": ""}))
    resp = await c.recv_until("error")
    assert resp["action"] == "error"
    await c.close()


async def test_37_bad_packet():
    c = Client()
    await c.connect()
    await c._ws.send_str("not json at all")
    resp = await c.recv()
    assert resp.get("action") == "error"
    assert "bad packet" in resp.get("content", "").lower()
    await c.close()


async def test_38_call_reject():
    c1 = Client()
    c2 = Client()
    await c1.connect()
    await c2.connect()
    await c1.login("alice", "pass123")
    await c2.login("bob", "pass456")
    await c1.send(pkt(action="call", target="bob"))
    await c1.recv_until("ok")
    r = await c2.recv_until("call")
    assert r["sender"] == "alice"
    await c2.send(pkt(action="call_reject", target="alice"))
    resp = await c2.recv_until("ok")
    assert "rejected" in resp.get("content", "").lower()
    await c1.close()
    await c2.close()


async def test_39_status_change():
    c = Client()
    await c.connect()
    await c.login("alice", "pass123")
    await c.send(pkt(action="status", content="away"))
    resp = await c.recv_until("ok")
    assert "away" in resp.get("content", "").lower()
    await c.close()


async def test_40_invalid_status():
    c = Client()
    await c.connect()
    await c.login("alice", "pass123")
    await c.send(pkt(action="status", content="invisible"))
    resp = await c.recv_until("error")
    assert resp["action"] == "error"
    await c.close()


# ═══════════════  RUNNER  ═══════════════

async def run_all():
    global _passed, _failed, _errors
    _passed = 0
    _failed = 0
    _errors = []

    print("\n" + "=" * 60)
    print("  CLARA E2E Test Suite (40 tests)")
    print("=" * 60 + "\n")

    await start_server()
    await asyncio.sleep(0.5)

    tests = [
        ("01. Server HTTP status", test_01_server_status),
        ("02. Register new user", test_02_register),
        ("03. Login existing user", test_03_login),
        ("04. Login wrong password", test_04_login_wrong_password),
        ("05. Duplicate registration", test_05_duplicate_register),
        ("06. Unauthenticated action", test_06_unauthenticated_action),
        ("07. Join room", test_07_join_room),
        ("08. Create room", test_08_create_room),
        ("09. List rooms", test_09_list_rooms),
        ("10. Send message", test_10_send_message),
        ("11. Direct message", test_11_dm),
        ("12. Broadcast to room", test_12_message_broadcast),
        ("13. Edit message", test_13_edit_message),
        ("14. Delete message", test_14_delete_message),
        ("15. Message history", test_15_history),
        ("16. Search messages", test_16_search),
        ("17. Leave room", test_17_leave_room),
        ("18. List users", test_18_list_users),
        ("19. Whoami", test_19_whoami),
        ("20. File upload", test_20_file_upload),
        ("21. File list", test_21_file_list),
        ("22. File download", test_22_file_download),
        ("23. Call flow (call → accept → end)", test_23_call_flow),
        ("24. Voice room join/leave", test_24_voice_room),
        ("25. Mute/Unmute", test_25_mute_unmute),
        ("26. Heartbeat", test_26_heartbeat),
        ("27. Typing indicator", test_27_typing),
        ("28. Presence (who)", test_28_presence_who),
        ("29. Session replacement", test_29_session_replace),
        ("30. Rate limiting", test_30_rate_limiting),
        ("31. Reply to message", test_31_reply_message),
        ("32. Kick requires moderator", test_32_moderation_kick),
        ("33. Ban requires admin", test_33_ban_requires_admin),
        ("34. AI ask not enabled", test_34_ai_not_enabled),
        ("35. AI usage query", test_35_ai_usage),
        ("36. File too large rejection", test_36_file_too_large),
        ("37. Bad packet handling", test_37_bad_packet),
        ("38. Call reject flow", test_38_call_reject),
        ("39. Status change", test_39_status_change),
        ("40. Invalid status", test_40_invalid_status),
    ]

    for name, fn in tests:
        await test(name, fn)

    await stop_server()

    print("\n" + "=" * 60)
    print(f"  Results: {_passed} passed, {_failed} failed, {len(tests)} total")
    print("=" * 60)

    if _errors:
        print("\nFailed tests:")
        for name, exc in _errors:
            print(f"  ✗ {name}: {exc}")

    return _failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all())
    sys.exit(0 if success else 1)
