# CLARA v2.0 — Manual Test Cases

> **How to use this document**
> Each test case lists the goal, exact commands to run, and the expected output.
> Open multiple terminal windows (one per user) to test multi-user scenarios.
> All users connect to `localhost:9100` unless stated otherwise.

---

## Setup — Start the Server

```bash
# Terminal 0 (server management only)
docker compose -f clara/docker/docker-compose.yml up -d
curl localhost:9100/status
```

**Expected:**
```json
{"server":"CLARA","version":"2.0.0","clients":0,"status":"running"}
```

---

## Setup — Install Client

```bash
source env/bin/activate          # activate venv
pip install aiohttp rich          # if not already installed
```

---

## How to Open a Client Session

```bash
python -m clara.client.cli --host localhost --port 9100
```

The CLI prompts for username and password. New users are **auto-registered** on first login.

---

## Test Suite Overview

| # | Category | Test Name |
|---|---|---|
| TC-01 | Auth | Register new user |
| TC-02 | Auth | Login with wrong password |
| TC-03 | Auth | Duplicate username rejected |
| TC-04 | Rooms | Create a room |
| TC-05 | Rooms | Join an existing room |
| TC-06 | Rooms | Leave a room |
| TC-07 | Rooms | List all rooms |
| TC-08 | Rooms | List users in a room |
| TC-09 | Chat | Send a message to a room |
| TC-10 | Chat | Receive a message from another user |
| TC-11 | Chat | Edit a sent message |
| TC-12 | Chat | Delete a sent message |
| TC-13 | Chat | View message history |
| TC-14 | Chat | Search messages |
| TC-15 | DM | Send a direct message |
| TC-16 | DM | Receive a direct message |
| TC-17 | DM | Reply to a message |
| TC-18 | Files | Upload a file |
| TC-19 | Files | List uploaded files |
| TC-20 | Files | Download a file |
| TC-21 | Voice | Initiate a P2P call |
| TC-22 | Voice | Accept a call |
| TC-23 | Voice | Reject a call |
| TC-24 | Voice | End a call |
| TC-25 | Voice | Join a voice room |
| TC-26 | Voice | Mute / unmute in voice room |
| TC-27 | Voice | Leave voice room |
| TC-28 | Presence | View who is online |
| TC-29 | Presence | Set custom status |
| TC-30 | Presence | Typing indicator |
| TC-31 | Moderation | Mute a user |
| TC-32 | Moderation | Unmute a user |
| TC-33 | Moderation | Kick a user from a room |
| TC-34 | Moderation | Ban a user globally |
| TC-35 | Moderation | Role promotion |
| TC-36 | AI | AI ask with no key (disabled) |
| TC-37 | AI | AI ask with key (enabled) |
| TC-38 | AI | Check AI usage stats |
| TC-39 | Rate Limit | Trigger rate limiter |
| TC-40 | Logs | Verify Docker logs |

---

## TC-01 — Register a new user

**Goal:** A new user can connect and be auto-registered.

**Terminal 1:**
```
python -m clara.client.cli --host localhost --port 9100
# When prompted:
Username: spider
Password: spiderpass
```

**Expected:**
```
[CLARA] Logged in as spider
```

---

## TC-02 — Login with wrong password

**Goal:** Wrong password is rejected; no session token issued.

**Terminal 1 (new session):**
```
python -m clara.client.cli --host localhost --port 9100
Username: spider
Password: wrongpass
```

**Expected:**
```
[ERROR] Authentication failed
```

---

## TC-03 — Duplicate username

**Goal:** Registering a second user with the same name is rejected.

**Steps:** Try to log in as `spider` from a second terminal with a different password than used in TC-01.

**Expected:**
```
[ERROR] Authentication failed
```

---

## TC-04 — Create a room

**Goal:** A logged-in user can create a named room.

**Terminal 1 (spider, logged in):**
```
/create dev
```

**Expected:**
```
[ROOM] Room 'dev' created.
```

---

## TC-05 — Join an existing room

**Goal:** A second user can join a room that already exists.

**Terminal 2:**
```
python -m clara.client.cli --host localhost --port 9100
Username: alice
Password: alicepass
```
```
/join dev
```

**Expected (Terminal 2):**
```
[ROOM] Joined 'dev'
```

**Expected (Terminal 1 — spider):**
```
[ROOM] alice joined dev
```

---

## TC-06 — Leave a room

**Goal:** A user can leave a room without disconnecting.

**Terminal 2 (alice):**
```
/leave
```

**Expected (Terminal 2):**
```
[ROOM] Left 'dev'
```

**Expected (Terminal 1 — spider):**
```
[ROOM] alice left dev
```

---

## TC-07 — List all rooms

**Goal:** Any logged-in user can list all available rooms.

**Terminal 1 (spider):**
```
/rooms
```

**Expected:**
```
[ROOMS] dev
```

---

## TC-08 — List users in a room

**Goal:** View who is currently in the joined room.

**Setup:** Both spider and alice rejoin `dev`.

**Terminal 1 (spider, in dev):**
```
/users
```

**Expected:**
```
[USERS] spider, alice
```

---

## TC-09 — Send a message to a room

**Goal:** A message sent in a room is received by all members.

**Terminal 1 (spider, in dev):**
```
hello team
```

**Expected (Terminal 1):**
```
[dev] spider: hello team
```

**Expected (Terminal 2 — alice, in dev):**
```
[dev] spider: hello team
```

---

## TC-10 — Receive a message from another user

**Goal:** Messages from any room member are visible to all members.

**Terminal 2 (alice, in dev):**
```
hey spider, welcome!
```

**Expected (Terminal 1 — spider):**
```
[dev] alice: hey spider, welcome!
```

---

## TC-11 — Edit a sent message

**Goal:** A user can edit their own message using its ID.

**Step 1 — Note the message ID** shown after sending (e.g., `id: 3`).

**Terminal 1 (spider):**
```
/edit 3 hello team — updated
```

**Expected:**
```
[EDIT] Message 3 updated.
```

---

## TC-12 — Delete a sent message

**Goal:** A user can delete their own message.

**Terminal 1 (spider):**
```
/delete 3
```

**Expected:**
```
[DELETE] Message 3 deleted.
```

---

## TC-13 — View message history

**Goal:** Retrieve past messages in the current room.

**Terminal 1 (spider, in dev):**
```
/history dev
```

**Expected:**
```
[HISTORY] — recent messages in dev —
1 · spider: hello team
2 · alice: hey spider, welcome!
```

---

## TC-14 — Search messages

**Goal:** Search for messages matching a keyword.

**Terminal 1 (spider):**
```
/search hello
```

**Expected:**
```
[SEARCH] Found 1 result(s):
1 · [dev] spider: hello team
```

---

## TC-15 — Send a direct message

**Goal:** A user can DM another user privately.

**Terminal 1 (spider):**
```
/msg alice this is private
```

**Expected (Terminal 1):**
```
[DM → alice] this is private
```

---

## TC-16 — Receive a direct message

**Goal:** DM arrives only to the target user.

**Expected (Terminal 2 — alice only):**
```
[DM from spider] this is private
```

**Verify:** Terminal 3 (bob, if open) does NOT see this message.

---

## TC-17 — Reply to a message

**Goal:** A user can reply to a specific message by ID.

**Terminal 2 (alice):**
```
/reply 1 got it, thanks!
```

**Expected:**
```
[REPLY to 1] alice: got it, thanks!
```

---

## TC-18 — Upload a file

**Goal:** A user can upload a file from their filesystem.

**Setup — create a test file:**
```bash
echo "CLARA file transfer test" > /tmp/test.txt
```

**Terminal 1 (spider, in dev):**
```
/upload /tmp/test.txt
```

**Expected:**
```
[FILE] Uploaded test.txt (id: abc123...)
```

---

## TC-19 — List uploaded files

**Goal:** List files shared in the current room.

**Terminal 1 (spider, in dev):**
```
/files
```

**Expected:**
```
[FILES]
abc123...  test.txt  24 B  spider
```

---

## TC-20 — Download a file

**Goal:** Any room member can download a shared file by its ID.

**Terminal 2 (alice, in dev):**
```
/download abc123
```

**Expected:**
```
[FILE] Downloaded test.txt → ~/.clara/uploads/test.txt
```

Verify the file contents:
```bash
cat ~/.clara/uploads/test.txt
# CLARA file transfer test
```

---

## TC-21 — Initiate a P2P voice call

**Goal:** One user can call another.

**Terminal 1 (spider):**
```
/call alice
```

**Expected (Terminal 2 — alice):**
```
[VOICE] Incoming call from spider. /accept spider or /reject spider
```

---

## TC-22 — Accept a call

**Goal:** Target user accepts the call.

**Terminal 2 (alice):**
```
/accept spider
```

**Expected (both terminals):**
```
[VOICE] Call connected: spider ↔ alice
```

---

## TC-23 — Reject a call

**Goal:** Target user rejects an incoming call.

**Setup:** Spider calls alice again.

**Terminal 1 (spider):**
```
/call alice
```

**Terminal 2 (alice):**
```
/reject spider
```

**Expected (Terminal 1):**
```
[VOICE] alice rejected the call.
```

---

## TC-24 — End an active call

**Goal:** Either party can hang up.

**Setup:** Establish a call (TC-21 + TC-22).

**Terminal 1 (spider):**
```
/hangup
```

**Expected (both terminals):**
```
[VOICE] Call ended.
```

---

## TC-25 — Join a voice room

**Goal:** Multiple users join a shared voice room.

**Terminal 1 (spider, in dev):**
```
/voicejoin dev
```

**Terminal 2 (alice, in dev):**
```
/voicejoin dev
```

**Expected (both):**
```
[VOICE] Joined voice room 'dev'. Members: spider, alice
```

---

## TC-26 — Mute and unmute in a voice room

**Goal:** A user can toggle their microphone.

**Terminal 1 (spider, in voice room):**
```
/mute
```
**Expected:** `[VOICE] Muted.`

```
/unmute
```
**Expected:** `[VOICE] Unmuted.`

---

## TC-27 — Leave a voice room

**Goal:** A user can leave a voice room.

**Terminal 1 (spider):**
```
/voiceleave
```

**Expected:**
```
[VOICE] Left voice room 'dev'.
```

**Expected (Terminal 2 — alice):**
```
[VOICE] spider left the room.
```

---

## TC-28 — View online users (presence)

**Goal:** See who is currently online.

**Terminal 1 (spider):**
```
/who
```

**Expected:**
```
[ONLINE] spider (online), alice (online)
```

---

## TC-29 — Set a custom status

**Goal:** A user can set a descriptive status.

**Terminal 1 (spider):**
```
/status writing some code
```

**Expected:**
```
[STATUS] Set to: writing some code
```

**Terminal 2 (alice) — run /who:**
```
/who
```

**Expected:**
```
[ONLINE] spider (writing some code), alice (online)
```

---

## TC-30 — Typing indicator

**Goal:** When a user starts typing, others see a typing notification.

**Note:** The CLI automatically sends a typing packet while the user is composing input. Watch Terminal 2 while typing in Terminal 1 — you should see:

```
[TYPING] spider is typing...
```

---

## TC-31 — Mute a user (moderation)

**Goal:** An admin can silence a user.

**Setup:** Make spider an admin first (requires `owner` role — see TC-35).

**Terminal 1 (spider, admin):**
```
/muteuser alice
```

**Expected (Terminal 1):**
```
[MOD] alice has been muted.
```

**Expected:** alice can no longer send messages to the room.

---

## TC-32 — Unmute a user

**Goal:** Admin removes the mute from a user.

**Terminal 1 (spider, admin):**
```
/unmuteuser alice
```

**Expected:**
```
[MOD] alice has been unmuted.
```

---

## TC-33 — Kick a user from a room

**Goal:** An admin can remove a user from a room (they are not banned).

**Setup:** Add a third user bob.

**Terminal 3:**
```
python -m clara.client.cli --host localhost --port 9100
Username: bob
Password: bobpass
# /join dev
```

**Terminal 1 (spider, admin, in dev):**
```
/kick bob
```

**Expected (Terminal 3 — bob):**
```
[MOD] You have been kicked from 'dev'.
```

**Note:** Bob can rejoin by typing `/join dev` again.

---

## TC-34 — Ban a user globally

**Goal:** An admin can permanently ban a user from the server.

**Terminal 1 (spider, admin):**
```
/ban bob
```

**Expected:**
```
[MOD] bob has been banned.
```

**Verify:** Bob's connection is terminated. Attempting to reconnect as bob returns an auth error.

---

## TC-35 — Role promotion

**Goal:** The server owner can promote users to admin.

**Note:** The first registered user is the server owner by default.

**Terminal 1 (spider, owner):**
```
/role alice admin
```

**Expected:**
```
[MOD] alice is now admin.
```

---

## TC-36 — AI ask with no key (disabled)

**Goal:** Without an AI API key, the AI feature is gracefully disabled.

**Terminal 1 (spider):**
```
/ai ask what is 2 + 2
```

**Expected:**
```
[AI] AI is not enabled. Use /ai enable <provider> with a valid API key.
```

---

## TC-37 — AI ask with key (enabled)

**Goal:** With an API key configured, the AI responds.

**Setup:** Set `OPENAI_API_KEY` in `.env`, then restart the server:
```bash
# .env
OPENAI_API_KEY=sk-...your-key...
```
```bash
docker compose -f clara/docker/docker-compose.yml restart clara-server
```

**Terminal 1 (spider):**
```
/ai enable openai
/ai ask what is the capital of France?
```

**Expected:**
```
[AI] Paris is the capital of France.
```

---

## TC-38 — AI usage stats

**Goal:** A user can check how many tokens they have used.

**Terminal 1 (spider):**
```
/ai usage
```

**Expected:**
```
[AI USAGE] Requests: 1 / 100  Tokens: 42 / 10000  Budget used: $0.001
```

---

## TC-39 — Rate limit

**Goal:** Sending messages too fast (> 10/sec) triggers the rate limiter.

**Terminal 1 (spider, in dev):**
Paste and run quickly (or use a script):
```bash
# from a shell, send 15 messages as fast as possible using the WS client
python3 -c "
import asyncio, aiohttp

async def flood():
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect('ws://localhost:9100/ws') as ws:
            # auth first ...
            pass  # (see e2e_tests.py for the full auth handshake)

asyncio.run(flood())
"
```

Or simply type 15 messages in rapid succession in the CLI.

**Expected:**
```
[ERROR] Rate limit exceeded. Slow down.
```

---

## TC-40 — Verify Docker logs

**Goal:** Confirm the server is logging key events correctly.

```bash
docker logs docker-clara-server-1 2>&1 | tail -40
```

**Expected log events:**
```
[INFO] Database opened: /home/clara/.clara/clara.db
[INFO] Starting CLARA server on 0.0.0.0:9100
[INFO] Client connected: spider
[INFO] spider joined room: dev
[INFO] Message sent in dev by spider
[INFO] File uploaded by spider
[INFO] Voice call: spider → alice
```

---

## Multi-User Demo Scenario

This walkthrough demonstrates CLARA end-to-end using three terminal windows.

### Step 1 — Start the server
```bash
# Terminal 0
docker compose -f clara/docker/docker-compose.yml up -d
curl localhost:9100/status
```

### Step 2 — Connect three users
```bash
# Terminal 1
python -m clara.client.cli --host localhost --port 9100
# Username: spider  Password: pass1

# Terminal 2
python -m clara.client.cli --host localhost --port 9100
# Username: alice   Password: pass2

# Terminal 3
python -m clara.client.cli --host localhost --port 9100
# Username: bob     Password: pass3
```

### Step 3 — Create a room and chat
```
# Terminal 1 (spider)
/create mission-control
/join mission-control
launch sequence initiated

# Terminal 2 (alice)
/join mission-control
all systems go

# Terminal 3 (bob)
/join mission-control
ready to go!
```
→ All three users see each other's messages in `mission-control`.

### Step 4 — Direct message
```
# Terminal 1 (spider)
/msg alice meet me in voice
```
→ Only alice sees the DM.

### Step 5 — Voice call
```
# Terminal 1 (spider)
/call alice

# Terminal 2 (alice)
/accept spider
```
→ Both see `Call connected: spider ↔ alice`.

### Step 6 — Share a file
```bash
echo "mission data" > /tmp/data.txt
```
```
# Terminal 1 (spider, in mission-control)
/upload /tmp/data.txt

# Terminal 2 (alice)
/files
/download <file-id>
```

### Step 7 — Moderation
```
# Terminal 1 (spider, owner)
/kick bob
```
→ bob is removed from the room; alice and spider remain.

### Step 8 — Stop the server
```bash
docker compose -f clara/docker/docker-compose.yml down
```

---

## Automated Test Suite

To run all 40 automated E2E tests:

```bash
source env/bin/activate
python -m clara.tests.e2e_tests
```

**Expected:**
```
✓ 01 register user (spider)
✓ 02 register second user (alice)
...
✓ 40 bad packet rejected
Results: 40 passed, 0 failed, 40 total
```

---

*CLARA v2.0 · PSG Hackathon 2026*
