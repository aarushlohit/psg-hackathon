---
name: devhub-module-builder
description: "Build, extend, or scaffold any DevHub module (CLARA, AARU, MEMO, SECURE, Agent Launcher). Use when implementing a new module, adding commands to an existing module, wiring a service/repository, or integrating into the DevHub router. Enforces OOP blueprint, Typer+Rich conventions, graceful degradation, and DevHub engineering principles."
argument-hint: "Module name to build or extend (e.g. 'aaru', 'memo', 'clara', 'secure', 'launcher')"
---

# DevHub Module Builder

## When to Use
- Implementing a new module from scratch
- Adding a command to CLARA, AARU, MEMO, SECURE, or Launcher
- Scaffolding a service or repository class
- Wiring a module into the router
- Ensuring a module follows all DevHub conventions before demo

## Project Overview

**DevHub** is a terminal-based developer worksuite — a single CLI workspace where developers switch between integrated modules without leaving the terminal.

**Entry point:** `devhub/main.py`  
**Tech:** Python 3.11+, Typer, Rich, SQLite, JSON, sockets, subprocess  
**Package:** `pyproject.toml` with console entrypoint `devhub=devhub.main:app`

### Module Map
| Module   | Purpose                                     | Storage         |
|----------|---------------------------------------------|-----------------|
| CLARA    | Secure LAN CLI chat, room-based             | JSON + sockets  |
| AARU     | Simplified Git wrapper (save/status/branch) | subprocess      |
| MEMO     | Tasks, notes, snippets, bugs                | SQLite          |
| SECURE   | Code/dep/secret scanning wrappers           | subprocess      |
| Launcher | Launch Claude Code / Codex from DevHub      | subprocess      |

---

## Procedure

### Step 1 — Understand the Module Contract

Every module extends `BaseModule` from `devhub/modules/base.py`:

```python
class BaseModule:
    name: str            # unique module identifier (lowercase)
    prompt_label: str    # shown in shell prompt, e.g. [aaru]

    def help(self) -> None: ...        # print available commands
    def handle(self, command: str) -> None: ...  # dispatch input string
    def enter(self) -> None: ...       # called on /switch <module>
    def exit(self) -> None: ...        # called on /switch away
```

**Rule:** Every `handle()` must catch exceptions and print a Rich error — never crash the shell.

### Step 2 — Implement the Service Layer

Create a service class in `devhub/services/` that encapsulates all I/O:

```
devhub/services/
├── git_service.py        # GitService, GitResult
├── memo_repo.py          # MemoRepository
├── security_service.py   # SecurityOrchestrator, *Scanner, SecurityFinding
└── launcher.py           # launch_claude(), launch_codex()
```

**Service rules:**
- No Rich imports inside services — return plain data types or dataclasses
- Use `subprocess.run(..., capture_output=True, text=True)` for external tools
- Check tool availability with `shutil.which("tool-name")` before calling
- Return structured results (dataclass or dict); never raise bare exceptions to the module

### Step 3 — Implement Module Commands

Follow the Internal API Spec (see `Docs/API_SPEC.md`):

| Module   | Commands                                          |
|----------|---------------------------------------------------|
| AARU     | `save <msg>`, `status`, `branch <name>`           |
| MEMO     | `task add/list/done`, `note add/list`             |
| CLARA    | `join <room>`, `send <msg>`, `list`               |
| SECURE   | `scan code`, `scan deps`, `scan secrets`, `scan all` |
| Launcher | handled via `/switch claude` / `/switch codex`    |

**Command parsing pattern inside `handle()`:**
```python
def handle(self, command: str) -> None:
    parts = command.strip().split(maxsplit=1)
    cmd = parts[0].lower() if parts else ""
    args = parts[1] if len(parts) > 1 else ""

    match cmd:
        case "status": self._status()
        case "save":   self._save(args)
        case "help":   self.help()
        case _:        console.print(f"[yellow]Unknown command: {cmd}. Type 'help'.[/yellow]")
```

### Step 4 — Wire Into the Router

In `devhub/router.py`, register the module:

```python
from devhub.modules.aaru import AaruModule

router.register(AaruModule())
```

`ModuleRouter.register(module)` adds to the internal registry keyed by `module.name`.  
`/switch <name>` calls `current.exit()` → looks up new module → calls `new.enter()`.

### Step 5 — Apply Rich UX Patterns

**Consistent output rules across all modules:**
```python
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

# Success
console.print("[green]✓[/green] Committed: init auth")

# Error (graceful, never crash)
console.print("[red]✗[/red] Not a git repository.")

# Tables for list output (tasks, notes, findings)
table = Table(title="Tasks")
table.add_column("ID", style="cyan")
table.add_column("Title")
table.add_column("Status", style="green")
```

### Step 6 — Implement Graceful Degradation

For every external tool (bandit, semgrep, pip-audit, claude, codex):

```python
import shutil

if shutil.which("bandit") is None:
    console.print("[yellow]bandit not installed. Run: pip install bandit[/yellow]")
    return
```

**Never crash** if a tool is missing. Print an actionable install hint.

### Step 7 — SQLite Initialization (MEMO only)

```python
import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".devhub" / "memo.db"

def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            priority TEXT DEFAULT 'medium',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
```

Database auto-creates on first run. Always use parameterized queries — never string-format SQL.

### Step 8 — CLARA Networking (socket-based)

For the MVP, CLARA uses a simple server + client socket model:
- `ChatServer`: `socket.socket(AF_INET, SOCK_STREAM)` bound to LAN IP, single room
- `ChatClient`: connects to server IP, sends/receives messages in a thread
- Config stored in `~/.devhub/clara.json` (room name, username, last server IP)

For demo: run server on one machine, client on another (or both on localhost).

---

## Engineering Principles Checklist

Before marking a module done, verify:

- [ ] Extends `BaseModule` with `name`, `prompt_label`, `help()`, `handle()`, `enter()`, `exit()`
- [ ] Service layer is in `devhub/services/` with no Rich imports
- [ ] All external tool calls guarded with `shutil.which()` + helpful message
- [ ] `handle()` never propagates exceptions to the shell loop
- [ ] All list output uses `rich.table.Table`
- [ ] All status output uses `[green]`, `[red]`, `[yellow]` color codes
- [ ] SQLite uses parameterized queries (no string formatting)
- [ ] Module registered in `router.py`
- [ ] `/help` inside the module lists all available commands

---

## Quick Scaffolding Template

```python
# devhub/modules/<name>.py
from rich.console import Console
from devhub.modules.base import BaseModule
from devhub.services.<name>_service import <Name>Service

console = Console()

class <Name>Module(BaseModule):
    name = "<name>"
    prompt_label = "[<name>]"

    def __init__(self):
        self._service = <Name>Service()

    def enter(self) -> None:
        console.print(Panel(f"Entering [bold]{self.name.upper()}[/bold] module. Type 'help'."))

    def exit(self) -> None:
        pass

    def help(self) -> None:
        console.print("[cyan]Commands:[/cyan] ...")

    def handle(self, command: str) -> None:
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""
        try:
            match cmd:
                case "help": self.help()
                case _: console.print(f"[yellow]Unknown: {cmd}[/yellow]")
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
```

---

## References
- [OOP Blueprint](../../../Docs/OOP_BACKEND-BLUEPRINT.md)
- [API Spec](../../../Docs/API_SPEC.md)
- [Engineering Principles](../../../Docs/ENGINEERING_PRINCIPLES.md)
- [Tech Stack](../../../Docs/TECH_STACK.md)
- [Features V1](../../../Docs/FEATURES_V1.md)
- [Build Prompts](../../../Docs/BUILD_PROMPTS.md)
