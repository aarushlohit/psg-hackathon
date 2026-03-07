# API Spec

For the hackathon MVP, DevHub is primarily a CLI, but these internal interfaces define module contracts.

## Router API

### switch_module(name: str) -> Module
Changes active module context.

### handle_input(raw: str) -> Response
Parses shell input and dispatches it.

## CLARA Service

### create_room(name: str) -> dict
Create a chat room.

### join_room(name: str, username: str) -> dict
Join an existing room.

### send_message(room: str, username: str, text: str) -> dict
Send message.

### get_messages(room: str, limit: int = 50) -> list[dict]
Return latest messages.

## AARU Service

### git_status() -> str
Run git status.

### git_save(message: str, push: bool = False) -> dict
Stage all, commit, optionally push.

### git_branch(name: str) -> dict
Create and switch branch.

## MEMO Service

### add_task(text: str, priority: str = "medium") -> dict
Create task.

### list_tasks(status: str = "open") -> list[dict]
List tasks.

### complete_task(task_id: int) -> dict
Mark task done.

### add_note(title: str, content: str) -> dict
Create note.

### list_notes(query: str | None = None) -> list[dict]
List/search notes.

## SECURE Service

### scan_code(path: str = ".") -> dict
Run bandit/semgrep and summarize.

### scan_dependencies(path: str = ".") -> dict
Run pip-audit and summarize.

### scan_secrets(path: str = ".") -> dict
Regex-based secret scan.

### scan_all(path: str = ".") -> dict
Aggregate all scanners.

## Agent Launcher

### launch_claude() -> int
Launch external `claude` CLI process.

### launch_codex() -> int
Launch external `codex` CLI process.
