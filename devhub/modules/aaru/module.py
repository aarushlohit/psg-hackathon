"""AARU module — simplified Git workflow commands."""

from __future__ import annotations

import logging

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from devhub.modules.base import BaseModule
from devhub.services.git_service import GitService

logger = logging.getLogger(__name__)
console = Console()


class AaruModule(BaseModule):
    """Simplified Git workflow module powered by aarushlohit-git / raw git."""

    name = "aaru"
    prompt_label = "[aaru]"

    def __init__(self) -> None:
        self._git = GitService()

    # ---- lifecycle ----

    def enter(self) -> None:
        super().enter()
        if not self._git.is_available():
            console.print(
                "[yellow]⚠ Neither 'aaru' nor 'git' found on PATH.\n"
                "  Install aaru: pip install aarushlohit-git\n"
                "  Or ensure git is available.[/yellow]"
            )
        console.print(
            Panel(
                "[bold green]AARU[/bold green] — Simplified Git Workflow\n"
                "Type [bold]help[/bold] for commands.",
                title="AARU",
                border_style="green",
            )
        )

    # ---- commands ----

    def help(self) -> None:
        table = Table(title="AARU Commands", show_header=True, header_style="bold green")
        table.add_column("Command", style="cyan")
        table.add_column("Description")
        table.add_row("status", "Show current git status")
        table.add_row("save <message>", "Stage all and commit")
        table.add_row("save <message> --push", "Stage, commit, and push")
        table.add_row("branch <name>", "Create and switch to new branch")
        table.add_row("help", "Show this help")
        console.print(table)

    def handle(self, command: str) -> None:
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        try:
            match cmd:
                case "status":
                    self._status()
                case "save":
                    self._save(args)
                case "branch":
                    self._branch(args)
                case "help":
                    self.help()
                case "":
                    pass
                case _:
                    console.print(f"[yellow]Unknown command: {cmd}. Type 'help'.[/yellow]")
        except Exception as exc:
            logger.exception("Error in AARU module")
            console.print(f"[red]✗ Error:[/red] {exc}")

    # ---- internals ----

    def _status(self) -> None:
        result = self._git.status()
        if result.success:
            output = result.output or "(working tree clean)"
            console.print(Panel(output, title="Git Status", border_style="green"))
        else:
            console.print(f"[red]✗[/red] {result.error}")

    def _save(self, args: str) -> None:
        push = False
        message = args.strip()
        if message.endswith("--push"):
            push = True
            message = message[: -len("--push")].strip()
        if not message:
            console.print("[yellow]Usage: save <commit message>[/yellow]")
            return
        result = self._git.save(message, push=push)
        if result.success:
            console.print(f"[green]✓[/green] Committed: {message}")
            if push:
                console.print("[green]✓[/green] Pushed to remote.")
        else:
            console.print(f"[red]✗[/red] {result.error or result.output}")

    def _branch(self, args: str) -> None:
        name = args.strip()
        if not name:
            console.print("[yellow]Usage: branch <name>[/yellow]")
            return
        result = self._git.branch(name)
        if result.success:
            console.print(f"[green]✓[/green] Switched to new branch: [bold]{name}[/bold]")
        else:
            console.print(f"[red]✗[/red] {result.error or result.output}")
