# Architecture

## High-level architecture

```text
+----------------------+
|      DevHub CLI      |
|  (Typer + Rich TUI)  |
+----------+-----------+
           |
           +----------------------+
           | Module Router        |
           | /switch <module>     |
           +----+-----+-----+-----+
                |     |     |     |
                |     |     |     +-------------------+
                |     |     |                         |
             CLARA   AARU  MEMO                     SECURE
          chat mode  git   tasks/notes       security scan wrappers
                |
                +-----------------------------------------------+
                | External AI Agent Launchers                   |
                | Claude Code / Codex                           |
                +-----------------------------------------------+
```

## Architectural style
- Modular monolith for MVP
- Each module isolated as a Python package/folder
- Shared storage/service layer
- Shell + subcommands pattern

## Runtime flow
1. User runs `devhub`
2. Hub shell starts
3. Router interprets commands
4. `/switch <module>` changes active context
5. Module-specific commands are handled by that module
6. Optional external tools are launched via subprocess

## Data flow
- MEMO stores data in SQLite
- CLARA stores config in JSON
- AARU reads local Git repository state
- SECURE executes scanners and parses output
- Launcher module checks whether `claude` / `codex` are installed

## MVP simplifications
- CLARA can use local server + socket clients
- No full encryption required for prototype; use clear abstraction for future secure transport
- Security scanner can aggregate CLI tools rather than implementing analysis from scratch
