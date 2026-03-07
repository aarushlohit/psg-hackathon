# 1-Hour Build Plan with Claude or Codex

This plan is for a **hackathon MVP only**.
Target: something demoable in ~1 hour with AI assistance.
Work strictly in order.

---

## Phase 0 — Repo bootstrap (5 minutes)

### Prompt 0A
Create a Python project named `devhub` using Typer and Rich. Build a modular CLI app with this structure:

- devhub/main.py
- devhub/router.py
- devhub/modules/base.py
- devhub/modules/aaru.py
- devhub/modules/clara.py
- devhub/modules/memo.py
- devhub/modules/secure.py
- devhub/modules/agents.py
- devhub/services/git_service.py
- devhub/services/memo_repo.py
- devhub/services/security_service.py
- devhub/services/launcher.py
- pyproject.toml
- README.md

Requirements:
- command `devhub`
- interactive shell loop
- supports `/help`, `/switch <module>`, `/exit`
- uses clean OOP structure
- use Typer + Rich
- include placeholders for modules
- code must run locally

Return all files completely.

### Prompt 0B
Now add a clean `pyproject.toml` with console entrypoint `devhub=devhub.main:app` or equivalent runnable entrypoint. Add minimal dependencies: typer, rich. Keep packaging simple.

---

## Phase 1 — Core shell and router (8 minutes)

### Prompt 1
Implement the DevHub interactive shell.

Requirements:
- on launch show a Rich panel with modules: clara, aaru, memo, secure, claude, codex
- shell prompt should display current module, e.g. `[hub] >`
- `/switch clara` changes active module
- `/switch hub` returns to hub
- `/help` shows available commands
- `/exit` quits
- invalid module names should print a helpful error
- keep code simple, robust, and demo-ready

Do not overengineer. Return updated files only.

---

## Phase 2 — AARU module (10 minutes)

### Prompt 2
Implement the AARU module for simplified Git commands.

Requirements:
- commands inside AARU mode:
  - `status`
  - `save <commit message>`
  - `branch <name>`
- use subprocess, not GitPython
- `save` should run:
  - git add .
  - git commit -m "<message>"
- optional push flag may be omitted for MVP
- print command results cleanly with Rich
- fail gracefully if current directory is not a git repo

Return updated files only.

---

## Phase 3 — MEMO module (10 minutes)

### Prompt 3
Implement MEMO using SQLite.

Requirements:
- create SQLite database automatically on first run
- support:
  - `task add <text>`
  - `task list`
  - `task done <id>`
  - `note add <title>` then prompt user to paste multiline content until EOF or a terminator
  - `note list`
- store tasks and notes in SQLite
- print tasks/notes in Rich tables
- keep repository/service pattern clean
- no unnecessary abstractions

Return updated files only.

---

## Phase 4 — SECURE module (8 minutes)

### Prompt 4
Implement a hackathon-friendly SECURE module.

Requirements:
- commands:
  - `scan code`
  - `scan deps`
  - `scan secrets`
  - `scan all`
- use wrapper approach:
  - bandit for code
  - pip-audit for dependencies
  - regex-based local secret detection for common patterns like API_KEY, SECRET, TOKEN
- if tools are not installed, print a clear message instead of crashing
- summarize findings in simple tables/panels
- keep implementation local-only and honest
- do not fake enterprise-grade security claims

Return updated files only.

---

## Phase 5 — CLARA module (10 minutes)

### Prompt 5
Implement a minimal CLARA prototype suitable for a hackathon demo.

Requirements:
- no full production networking
- support one of these two MVP approaches:
  1. local message board/chat room stored in SQLite or JSON, OR
  2. simple localhost socket server/client if fast to build
- commands:
  - `join <room>`
  - `send <message>`
  - `messages`
- objective is demoing the module concept inside DevHub, not perfect networking
- use Rich for output
- keep architecture extensible for future IP-based secure chat

Return updated files only.

---

## Phase 6 — Claude/Codex integration (5 minutes)

### Prompt 6
Implement launcher support for Claude Code and Codex inside DevHub.

Requirements:
- `/switch claude` and `/switch codex`
- when switched, DevHub should:
  - check whether the executable exists on PATH
  - launch `claude` or `codex` via subprocess if installed
  - otherwise print installation guidance
- after subprocess exits, return to DevHub shell
- do not require API keys inside DevHub for the MVP
- keep code cross-platform where practical

Return updated files only.

---

## Phase 7 — Demo polish (7 minutes)

### Prompt 7
Polish the CLI UX for hackathon demo quality.

Requirements:
- improve home screen
- add consistent help menus per module
- improve error messages
- add Rich panels/tables/colors tastefully
- ensure shell prompts are clear
- add a short README with install + demo commands
- keep startup flow smooth and professional

Return updated files only.

---

## Final validation prompt

### Prompt 8
Review the whole DevHub project for hackathon readiness.

Check:
- imports
- entrypoint correctness
- missing methods
- database initialization
- command routing bugs
- subprocess safety
- markdown README clarity

Fix all issues and return only the final changed files.

---

## Suggested real execution order
1. Use Claude or Codex for Prompt 0A and 0B
2. Run project
3. Prompt 1
4. Test shell
5. Prompt 2
6. Test AARU
7. Prompt 3
8. Test MEMO
9. Prompt 4
10. Test SECURE
11. Prompt 5
12. Test CLARA
13. Prompt 6
14. Prompt 7
15. Prompt 8

## Time reality
If you stay strict on MVP:
- 45–75 minutes is possible
- do not add extra modules
- do not rewrite architecture midway
- do not attempt full encrypted LAN chat today
