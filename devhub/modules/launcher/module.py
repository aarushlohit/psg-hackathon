"""Launcher module — launch external AI coding agents from DevHub."""

from __future__ import annotations

import logging

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from devhub.modules.base import BaseModule
from devhub.services.launcher import LauncherService

logger = logging.getLogger(__name__)
console = Console()


class LauncherModule(BaseModule):
    """Module for launching Claude Code or Codex from DevHub."""

    name = "launcher"
    prompt_label = "[launcher]"

    # ---- lifecycle ----

    def enter(self) -> None:
        super().enter()
        console.print(
            Panel(
                "[bold blue]AI Agent Launcher[/bold blue]\n"
                "Type [bold]help[/bold] for commands.",
                title="Launcher",
                border_style="blue",
            )
        )

    # ---- commands ----

    def help(self) -> None:
        table = Table(title="Launcher Commands", show_header=True, header_style="bold blue")
        table.add_column("Command", style="cyan")
        table.add_column("Description")
        table.add_row("launch claude", "Launch Claude Code")
        table.add_row("launch codex", "Launch Codex")
        table.add_row("status", "Check which tools are installed")
        table.add_row("help", "Show this help")
        console.print(table)

    def handle(self, command: str) -> None:
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        args = parts[1].strip() if len(parts) > 1 else ""

        try:
            match cmd:
                case "launch":
                    self._handle_launch(args)
                case "status":
                    self._handle_status()
                case "help":
                    self.help()
                case "":
                    pass
                case _:
                    console.print(f"[yellow]Unknown command: {cmd}. Type 'help'.[/yellow]")
        except Exception as exc:
            logger.exception("Error in Launcher module")
            console.print(f"[red]✗ Error:[/red] {exc}")

    # ---- internals ----

    def _handle_launch(self, tool: str) -> None:
        if not tool:
            console.print("[yellow]Usage: launch claude | launch codex[/yellow]")
            return
        console.print(f"[dim]Launching {tool}...[/dim]")
        result = LauncherService.launch(tool)
        if result.success:
            console.print(f"[green]✓[/green] {result.message}")
        else:
            console.print(f"[red]✗[/red] {result.message}")

    @staticmethod
    def _handle_status() -> None:
        table = Table(title="AI Agent Status", show_header=True)
        table.add_column("Tool", style="cyan")
        table.add_column("Status")
        table.add_column("Install")
        for name, info in LauncherService.TOOLS.items():
            available = LauncherService.is_available(name)
            status = "[green]✓ installed[/green]" if available else "[red]✗ not found[/red]"
            table.add_row(name, status, info["install_hint"])
        console.print(table)
