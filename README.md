# CLARA — Terminal Communication Platform

> **CLI-native real-time communication.** Rooms, DMs, voice calls, file sharing, AI, and moderation — all from your terminal.

```
  ██████╗██╗      █████╗ ██████╗  █████╗
 ██╔════╝██║     ██╔══██╗██╔══██╗██╔══██╗
 ██║     ██║     ███████║██████╔╝███████║
 ██║     ██║     ██╔══██║██╔══██╗██╔══██║
 ╚██████╗███████╗██║  ██║██║  ██║██║  ██║
  ╚═════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝
  v2.0 · Real-Time Terminal Communication
```

---

## Features

| Feature | Description |
|---|---|
| **Chat Rooms** | Create and join named rooms; broadcast messages to all members |
| **Direct Messages** | Private encrypted DMs between any two users |
| **Voice Calls** | P2P voice calls and multi-user voice rooms via WebRTC signaling |
| **File Sharing** | Upload and download files (up to 50 MB) via base64 over WebSocket |
| **Presence** | Real-time online/offline, typing indicators, custom status |
| **Moderation** | Kick, ban, mute users; role system (owner › admin › moderator › member) |
| **AI Gateway** | Ask questions via OpenAI, Claude, or OpenRouter — right from the chat |
| **Rate Limiting** | Server-side rate limiting (10 msgs/sec per client) |
| **40 E2E Tests** | Full automated test suite covering every feature |

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  Terminal Clients                │
│   (python -m clara.client.cli)                   │
└────────────────────┬────────────────────────────┘
                     │  WebSocket  ws://host:9100/ws
┌────────────────────▼────────────────────────────┐
│              CLARA Server (FastAPI)              │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │  Rooms   │ │Messaging │ │  Voice Signaling  │ │
│  ├──────────┤ ├──────────┤ ├──────────────────┤ │
│  │  Files   │ │   Auth   │ │   AI Gateway      │ │
│  ├──────────┤ ├──────────┤ ├──────────────────┤ │
│  │Moderation│ │ Presence │ │  Rate Limiter     │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
└────────────────────┬────────────────────────────┘
          ┌──────────┴──────────┐
┌─────────▼──────┐   ┌──────────▼──────┐
│   PostgreSQL   │   │     Redis        │
│   (or SQLite)  │   │  (optional cache)│
└────────────────┘   └─────────────────┘
```

---

## Requirements

| Software | Version | Notes |
|---|---|---|
| Python | 3.11+ | For running the CLI client locally |
| Docker | 20.10+ | For the server stack |
| Docker Compose | v2.0+ | Plugin or standalone |
| Git | any | For cloning the repo |
| curl | any | For health checks |

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/your-org/psg-hackathon.git
cd psg-hackathon
```

### 2. Configure environment (optional for local dev)

```bash
cp .env.example .env
# Edit .env if you want to change ports or add AI keys
```

### 3. Start the server stack

```bash
docker compose -f clara/docker/docker-compose.yml up -d
```

Expected output:
```
✔ Container docker-redis-1          Started
✔ Container docker-postgres-1       Started
✔ Container docker-clara-server-1   Started
```

### 4. Verify the server is running

```bash
curl localhost:9100/status
```

Expected response:
```json
{"server":"CLARA","version":"2.0.0","clients":0,"status":"running"}
```

### 5. Install client dependencies

```bash
python -m venv env
source env/bin/activate        # Windows: env\Scripts\activate
pip install aiohttp rich
```

### 6. Connect as a user

```bash
python -m clara.client.cli --host localhost --port 9100
```

The CLI will prompt for a username and password. New users are auto-registered on first login.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `CLARA_HOST` | `0.0.0.0` | Server bind address |
| `CLARA_PORT` | `9100` | Server port |
| `CLARA_SQLITE_PATH` | `~/.clara/clara.db` | SQLite database path (default backend) |
| `CLARA_DATABASE_URL` | _(empty)_ | PostgreSQL URL — overrides SQLite when set |
| `CLARA_JWT_SECRET` | `clara-dev-secret-change-me` | JWT signing secret — **change in production** |
| `CLARA_JWT_EXPIRE_MINUTES` | `1440` | Token expiry (24 h) |
| `CLARA_REDIS_ENABLED` | `false` | Enable Redis session layer |
| `CLARA_REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `CLARA_UPLOAD_DIR` | `~/.clara/uploads` | File upload storage directory |
| `CLARA_TLS_CERT` | _(empty)_ | Path to TLS certificate (production) |
| `CLARA_TLS_KEY` | _(empty)_ | Path to TLS private key (production) |
| `OPENAI_API_KEY` | _(empty)_ | OpenAI API key for AI gateway |
| `ANTHROPIC_API_KEY` | _(empty)_ | Anthropic/Claude API key |
| `OPENROUTER_API_KEY` | _(empty)_ | OpenRouter API key |

---

## CLI Command Reference

Once connected, type `/help` to see all commands.

```
Connection:   /whoami   /quit
Rooms:        /join <room>          /leave           /create <room>
              /rooms                /users           /who
Chat:         <message>             /msg <user> <text>
              /reply <id> <text>    /edit <id> <text>  /delete <id>
              /search <query>       /history [room]
Voice:        /call <user>          /accept <user>   /reject <user>   /hangup
              /voicejoin [room]     /voiceleave      /mute            /unmute
Files:        /upload <path>        /download <id>   /files
AI:           /ai enable [provider] /ai ask <question>
              /ai summarize         /ai usage
Moderation:   /kick <user>          /ban <user>      /unban <user>
              /muteuser <user>      /unmuteuser <user>
              /role <user>
Status:       /status <text>
```

---

## Running the Automated Test Suite

```bash
source env/bin/activate
python -m clara.tests.e2e_tests
```

Expected: `Results: 40 passed, 0 failed, 40 total`

---

## Stopping the Server

```bash
docker compose -f clara/docker/docker-compose.yml down
```

To also delete persistent data volumes:
```bash
docker compose -f clara/docker/docker-compose.yml down -v
```

---

## Project Structure

```
clara/
├── config/          # Settings (env-driven) + logging
├── database/        # SQLite/Postgres CRUD + dataclass models
├── server/          # FastAPI app, WebSocket hub, all services
│   ├── main.py      # Entry point — build_app() + uvicorn
│   ├── websocket.py # ClaraHub + ConnectedClient dispatcher
│   ├── auth.py      # JWT create/verify
│   ├── rooms.py     # Room join/leave/broadcast
│   ├── messaging.py # Message, DM, edit, delete, history
│   ├── voice.py     # P2P calls + voice rooms
│   ├── files.py     # Upload/download (base64)
│   ├── ai_gateway.py# OpenAI/Claude/OpenRouter
│   ├── moderation.py# Kick/ban/mute + RBAC
│   └── presence.py  # Heartbeat + typing indicators
├── client/          # Terminal client
│   ├── cli.py       # Interactive entry point
│   ├── commands.py  # Slash command parser
│   ├── ui.py        # Rich terminal rendering
│   └── websocket_client.py  # aiohttp WS client
├── tests/
│   └── e2e_tests.py # 40 automated integration tests
└── docker/
    ├── Dockerfile
    └── docker-compose.yml
```

---

## License

MIT — built for the PSG Hackathon 2026.
