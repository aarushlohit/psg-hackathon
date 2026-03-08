# DEVHUB — Hackathon Presentation Demo Guide

> **Duration:** 2–3 minutes  
> **Setup:** 4 terminals on one laptop  
> **Server:** Already running via Docker

---

## 1. Demo Objective

**DEVHUB** is a unified developer collaboration platform that brings every tool a dev team needs into a single terminal interface.

| Module | Purpose |
|---|---|
| **CLARA** | Real-time chat rooms, DMs, voice calls, file sharing, AI assistant |
| **AARU** | Safety-first Git workflow — stage, commit, push in one command |
| **MEMO** | Developer knowledge memory — tasks and notes, always at your fingertips |
| **SECURE** | Security scanner — static analysis, dependency audit, secret detection |

**Demo Goal:** Show all four modules working live on one laptop using four terminals.

---

## 2. Terminal Layout

Open 4 terminal windows side by side on screen.

```
┌──────────────────┬──────────────────┬──────────────────┬──────────────────┐
│   Terminal 1     │   Terminal 2     │   Terminal 3     │   Terminal 4     │
│   SERVER         │   spider         │   alice          │   bob            │
│  (Docker logs)   │  (Admin user)    │  (Team member)   │  (Team member)   │
└──────────────────┴──────────────────┴──────────────────┴──────────────────┘
```

---

## 3. Start the Platform

**Terminal 1 — Start the server stack:**

```bash
cd /path/to/psg-hackathon
docker compose -f clara/docker/docker-compose.yml up -d
```

**Expected output:**
```
✔ Container docker-redis-1          Started
✔ Container docker-postgres-1       Started
✔ Container docker-clara-server-1   Started
```

**Verify server is healthy:**
```bash
curl localhost:9100/status
```

**Expected:**
```json
{"server":"CLARA","version":"2.0.0","clients":0,"status":"running"}
```

**Watch live server logs (keep this running in Terminal 1):**
```bash
docker logs -f docker-clara-server-1
```

---

## 4. Start DEVHUB CLI

**Terminals 2, 3, 4 — each user runs:**

```bash
source env/bin/activate
devhub
```

**Expected prompt on all three terminals:**
```
╭───────────────────────────────────────────────────╮
│ DevHub — Terminal Developer Worksuite             │
│ Unify chat, git, notes, security, and AI agents. │
╰───────────────────────────────────────────────────╯

Commands: /switch <module>  /help  /exit

DevHub >
```

---

## 5. CLARA Demo — Real-time Communication

### Switch to CLARA

All three users (Terminal 2, 3, 4):
```
DevHub > /switch clara
```

**Expected:**
```
╭──────────────────────────────────────╮
│ CLARA — Terminal Communication Platform │
│ Chat · Rooms · DMs · Voice · Files · AI │
╰──────────────────────────────────────╯
DevHub [clara] >
```

---

### ① User Connection

**Terminal 2 (spider):**
```
DevHub [clara] > connect localhost spider
```

**Terminal 3 (alice):**
```
DevHub [clara] > connect localhost alice
```

**Terminal 4 (bob):**
```
DevHub [clara] > connect localhost bob
```

**Expected** (each terminal shows):
```
✓ Logged in as spider
```

---

### ② Create Room + Join

**Terminal 2 (spider):**
```
DevHub [clara] > create-room mission
DevHub [clara] > join mission
```

**Terminal 3 (alice):**
```
DevHub [clara] > join mission
```

**Terminal 4 (bob):**
```
DevHub [clara] > join mission
```

**Expected on Terminal 2:**
```
→ Room 'mission' created.
→ alice joined mission
→ bob joined mission
```

---

### ③ Room Messaging

**Terminal 2 (spider):**
```
DevHub [clara] > send Hello team, DEVHUB demo starting.
```

**Expected on Terminal 3 & 4:**
```
spider #mission: Hello team, DEVHUB demo starting.
```

**Terminal 3 (alice):**
```
DevHub [clara] > send Ready to go!
```

---

### ④ Direct Message (Private)

**Terminal 2 (spider):**
```
DevHub [clara] > msg alice Secret — the launch code is DEVHUB2026
```

**Expected on Terminal 3 (alice only):**
```
DM spider → alice: Secret — the launch code is DEVHUB2026
```

> Terminal 4 (bob) sees nothing — DMs are private.

---

### ⑤ File Sharing

**Terminal 2 (spider) — create a demo file first:**
```bash
echo "DEVHUB mission brief - launch at 0900" > /tmp/mission.txt
```

```
DevHub [clara] > file send /tmp/mission.txt
```

**Expected:**
```
→ Uploaded mission.txt (id: a3f9c2...)
```

**Terminal 3 (alice):**
```
DevHub [clara] > file list
DevHub [clara] > file receive a3f9c2
```

**Expected:**
```
→ Downloaded mission.txt  ·  DEVHUB mission brief - launch at 0900
```

---

### ⑥ Voice Call

**Terminal 2 (spider):**
```
DevHub [clara] > call alice
```

**Expected on Terminal 3 (alice):**
```
📞 Incoming call from spider — accept or hangup
```

**Terminal 3 (alice):**
```
DevHub [clara] > call accept
```

**Expected on both:**
```
📞 Call connected: spider ↔ alice
```

**Terminal 2 (spider) ends call:**
```
DevHub [clara] > hangup
```

---

## 6. MEMO Demo — Developer Knowledge Memory

**Terminal 2 (spider):**
```
DevHub [clara] > /switch memo
```

**Expected:**
```
╭──────────────────────────────╮
│ MEMO — Tasks & Notes         │
╰──────────────────────────────╯
DevHub [memo] >
```

**Add a task:**
```
DevHub [memo] > task add Deploy DEVHUB to production VPS
```

**Expected:**
```
→ Task added: Deploy DEVHUB to production VPS
```

**Add a note:**
```
DevHub [memo] > note add Hackathon Demo Notes
```
*(CLI prompts for content — type:* `DEVHUB runs on FastAPI + SQLite + Docker` *then Enter)*

**List tasks:**
```
DevHub [memo] > task list
```

**Expected:**
```
[ ] Deploy DEVHUB to production VPS
```

> **Say verbally:** *MEMO gives every developer persistent memory — tasks and notes that stay with your project, accessible from any terminal.*

---

## 7. AARU Demo — Safe Git Workflow

**Terminal 2 (spider):**
```
DevHub [memo] > /switch aaru
```

**Expected:**
```
╭──────────────────────────────────╮
│ AARU — Simplified Git Workflow   │
╰──────────────────────────────────╯
DevHub [aaru] >
```

**Check git status:**
```
DevHub [aaru] > status
```

**Stage + commit in one command:**
```
DevHub [aaru] > save "DEVHUB hackathon demo checkpoint"
```

**Expected:**
```
→ Staged all changes
→ Committed: DEVHUB hackathon demo checkpoint
```

**Push to remote:**
```
DevHub [aaru] > save "final demo push" --push
```

> **Say verbally:** *AARU removes the three-command git dance. One command: stage, commit, push. Beginners can't break their history.*

---

## 8. SECURE Demo — Security Scanner

**Terminal 2 (spider):**
```
DevHub [aaru] > /switch secure
```

**Expected:**
```
╭──────────────────────────────────╮
│ SECURE — Security Scanner        │
╰──────────────────────────────────╯
DevHub [secure] >
```

**Scan for hardcoded secrets:**
```
DevHub [secure] > scan secrets
```

**Scan Python dependencies for known CVEs:**
```
DevHub [secure] > scan deps
```

**Run all scanners at once:**
```
DevHub [secure] > scan all
```

> **Say verbally:** *SECURE scans your code before every push — Bandit static analysis, pip-audit CVE checks, and regex-based secret detection. Catch problems before they reach production.*

---

## 9. Final Message

**Terminal 2 (spider) — return to CLARA:**
```
DevHub [secure] > /switch clara
DevHub [clara] > join mission
DevHub [clara] > send DEVHUB platform demo complete. All modules verified ✓
```

**Expected on all terminals:**
```
spider #mission: DEVHUB platform demo complete. All modules verified ✓
```

---

## 10. Features Mentioned Verbally (Not Shown Live)

These features exist and are tested (40/40 E2E tests pass) but shown in slides only:

| Feature | Where |
|---|---|
| **AI Gateway** | CLARA — `/ai ask`, `/ai summarize` via OpenAI/Claude/OpenRouter |
| **Message Search** | CLARA — full-text search across room history |
| **Rate Limiting** | Server-side — 10 messages/sec per client |
| **Presence System** | Real-time online/offline, typing indicators |
| **Moderation + RBAC** | Owner › Admin › Moderator › Member role hierarchy |
| **Voice Rooms** | Multi-user voice channels (not just P2P calls) |
| **JWT Auth** | All WebSocket connections use signed tokens |
| **Docker Deploy** | One command — `docker compose up -d` for full stack |
| **1000 Concurrent WS** | Benchmarked capacity |
| **VPS Deploy Script** | `clara/scripts/deploy_vps.sh` — full VPS setup in one script |

---

## 11. 2-Minute Demo Script

> *Read this aloud while running the commands above.*

---

**[0:00 — Introduction]**

> "This is DEVHUB — a unified developer collaboration platform that lives entirely in the terminal. One CLI. Four modules. Everything a dev team needs."

---

**[0:10 — Start the server]**

> "The backend runs on Docker. One command starts the server, Postgres, and Redis."

*Run: `docker compose up -d` → `curl localhost:9100/status`*

> "Server is healthy. Zero clients connected. Let's fix that."

---

**[0:20 — Connect three users]**

> "We have three developers — spider, alice, and bob — each in their own terminal running `devhub`. They switch to CLARA, our real-time communication module."

*All three run `/switch clara` → `connect localhost <username>`*

> "All authenticated via JWT in under a second."

---

**[0:35 — Chat + DMs + Files]**

> "Spider creates a room called mission. Everyone joins."

*`create-room mission` → `join mission`*

> "Messages broadcast instantly to the whole room. Private DMs are end-to-end isolated — bob can't see alice's message."

*`send Hello team` → `msg alice Secret message`*

> "Files upload over WebSocket — no separate server needed."

*`file send /tmp/mission.txt` → alice `file receive`*

---

**[1:00 — Voice Call]**

> "Voice calls work peer-to-peer. Spider calls alice directly."

*`call alice` → alice `call accept` → `hangup`*

> "WebRTC signaling through the CLARA server."

---

**[1:15 — MEMO]**

> "Switch to MEMO. Every developer gets persistent task and note storage."

*`/switch memo` → `task add Deploy DEVHUB` → `task list`*

---

**[1:25 — AARU]**

> "AARU fixes the most common developer mistake — forgetting to push. One command: stage, commit, and push."

*`/switch aaru` → `save "demo checkpoint" --push`*

---

**[1:35 — SECURE]**

> "Before that push goes out, SECURE scans your code. Bandit analysis, CVE dependency check, secret detection — all in one command."

*`/switch secure` → `scan all`*

---

**[1:50 — Close]**

> "Back to CLARA for the final message."

*`/switch clara` → `send DEVHUB demo complete. All modules verified ✓`*

> "DEVHUB: one CLI, real-time chat, safe git, persistent memory, and security scanning. Everything stays in the terminal. Thank you."

---

## Quick Reference Card

```
# Start server
docker compose -f clara/docker/docker-compose.yml up -d

# Start CLI (all users)
source env/bin/activate && devhub

# CLARA
DevHub > /switch clara
connect localhost <username>
create-room <name>  |  join <room>  |  send <message>
msg <user> <text>   |  file send <path>  |  file receive <id>
call <user>         |  call accept       |  hangup

# MEMO
DevHub > /switch memo
task add <title>    |  task list    |  task done <id>
note add <title>    |  note list

# AARU
DevHub > /switch aaru
status              |  save <message>    |  save <message> --push

# SECURE
DevHub > /switch secure
scan code  |  scan deps  |  scan secrets  |  scan all

# Switch modules anytime
/switch clara | /switch memo | /switch aaru | /switch secure

# Exit
/exit
```

---

*DEVHUB v1.0 · PSG Hackathon 2026*
