"""MEMO module — developer tasks, notes, and productivity."""

from __future__ import annotations

import logging

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from devhub.modules.base import BaseModule
from devhub.services.memo_repo import MemoRepository

logger = logging.getLogger(__name__)
console = Console()


class MemoModule(BaseModule):
    """Developer productivity module — tasks and notes backed by SQLite."""

    name = "memo"
    prompt_label = "[memo]"

    def __init__(self) -> None:
        self._repo = MemoRepository()

    # ---- lifecycle ----

    def enter(self) -> None:
        super().enter()
        console.print(
            Panel(
                "[bold magenta]MEMO[/bold magenta] — Tasks & Notes\n"
                "Type [bold]help[/bold] for commands.",
                title="MEMO",
                border_style="magenta",
            )
        )

    def exit(self) -> None:
        super().exit()
        self._repo.close()

    # ---- commands ----

    def help(self) -> None:
        table = Table(title="MEMO Commands", show_header=True, header_style="bold magenta")
        table.add_column("Command", style="cyan")
        table.add_column("Description")
        table.add_row("task add <title>", "Add a new task")
        table.add_row("task list", "List all tasks")
        table.add_row("task list open", "List open tasks only")
        table.add_row("task done <id>", "Mark task as complete")
        table.add_row("note add <title>", "Add a note (prompts for content)")
        table.add_row("note list", "List all notes")
        table.add_row("note list <query>", "Search notes by title")
        table.add_row("help", "Show this help")
        console.print(table)

    def handle(self, command: str) -> None:
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        try:
            match cmd:
                case "task":
                    self._handle_task(args)
                case "note":
                    self._handle_note(args)
                case "help":
                    self.help()
                case "":
                    pass
                case _:
                    console.print(f"[yellow]Unknown command: {cmd}. Type 'help'.[/yellow]")
        except Exception as exc:
            logger.exception("Error in MEMO module")
            console.print(f"[red]✗ Error:[/red] {exc}")

    # ---- task subcommands ----

    def _handle_task(self, args: str) -> None:
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else ""
        rest = parts[1] if len(parts) > 1 else ""

        match sub:
            case "add":
                self._task_add(rest)
            case "list":
                self._task_list(rest)
            case "done":
                self._task_done(rest)
            case _:
                console.print("[yellow]Usage: task add|list|done[/yellow]")

    def _task_add(self, title: str) -> None:
        if not title.strip():
            console.print("[yellow]Usage: task add <title>[/yellow]")
            return
        task = self._repo.add_task(title.strip())
        console.print(f"[green]✓[/green] Task #{task.id} created: {task.title}")

    def _task_list(self, filter_arg: str) -> None:
        status_filter = filter_arg.strip().lower() if filter_arg.strip() in ("open", "done") else None
        tasks = self._repo.list_tasks(status=status_filter)
        if not tasks:
            console.print("[dim]No tasks found.[/dim]")
            return
        table = Table(title="Tasks", show_header=True)
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("Title")
        table.add_column("Status", style="green")
        table.add_column("Priority")
        table.add_column("Created", style="dim")
        for t in tasks:
            status_style = "[green]✓ done[/green]" if t.is_done else "[yellow]open[/yellow]"
            table.add_row(str(t.id), t.title, status_style, t.priority, t.created_at)
        console.print(table)

    def _task_done(self, args: str) -> None:
        try:
            task_id = int(args.strip())
        except ValueError:
            console.print("[yellow]Usage: task done <id>[/yellow]")
            return
        if self._repo.complete_task(task_id):
            console.print(f"[green]✓[/green] Task #{task_id} marked done.")
        else:
            console.print(f"[red]✗[/red] Task #{task_id} not found or already done.")

    # ---- note subcommands ----

    def _handle_note(self, args: str) -> None:
        parts = args.strip().split(maxsplit=1)
        sub = parts[0].lower() if parts else ""
        rest = parts[1] if len(parts) > 1 else ""

        match sub:
            case "add":
                self._note_add(rest)
            case "list":
                self._note_list(rest)
            case _:
                console.print("[yellow]Usage: note add|list[/yellow]")

    def _note_add(self, title: str) -> None:
        if not title.strip():
            console.print("[yellow]Usage: note add <title>[/yellow]")
            return
        console.print("[dim]Enter note content (type END on a new line to finish):[/dim]")
        lines: list[str] = []
        while True:
            try:
                line = input()
                if line.strip().upper() == "END":
                    break
                lines.append(line)
            except EOFError:
                break
        content = "\n".join(lines)
        note = self._repo.add_note(title.strip(), content)
        console.print(f"[green]✓[/green] Note #{note.id} created: {note.title}")

    def _note_list(self, query: str) -> None:
        notes = self._repo.list_notes(query=query.strip() or None)
        if not notes:
            console.print("[dim]No notes found.[/dim]")
            return
        table = Table(title="Notes", show_header=True)
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("Title")
        table.add_column("Preview")
        table.add_column("Created", style="dim")
        for n in notes:
            preview = (n.content[:60] + "…") if len(n.content) > 60 else n.content
            table.add_row(str(n.id), n.title, preview, n.created_at)
        console.print(table)
