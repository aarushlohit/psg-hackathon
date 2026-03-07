"""DevHub interactive shell — the main REPL loop."""

from __future__ import annotations

import logging
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from devhub.router import ModuleRouter
from devhub.services.launcher import LauncherService

logger = logging.getLogger(__name__)
console = Console()

# Modules that should be launched directly via subprocess instead of entering a module.
AI_AGENT_SHORTCUTS: set[str] = {"claude", "codex"}


class DevHubShell:
    """Interactive shell orchestrating the DevHub experience."""

    def __init__(self, router: ModuleRouter) -> None:
        self._router = router
        self._running: bool = False

    # ---- public ----

    def run(self) -> None:
        """Start the REPL loop."""
        self._running = True
        self._render_home()

        while self._running:
            prompt = self._build_prompt()
            try:
                raw = input(prompt)
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Goodbye![/dim]")
                break

            raw = raw.strip()
            if not raw:
                continue

            if raw.startswith("/"):
                self._handle_slash(raw)
            else:
                self._router.handle_input(raw)

        self._shutdown()

    # ---- home screen ----

    def _render_home(self) -> None:
        console.print()
        console.print(
            Panel(
                "[bold cyan]DevHub[/bold cyan] — Terminal Developer Worksuite\n"
                "[dim]Unify chat, git, notes, security, and AI agents in one place.[/dim]",
                border_style="cyan",
                expand=False,
            )
        )

        table = Table(show_header=True, header_style="bold", title="Modules")
        table.add_column("Module", style="cyan")
        table.add_column("Description")
        table.add_row("clara", "Secure LAN developer chat")
        table.add_row("aaru", "Simplified Git workflow")
        table.add_row("memo", "Tasks, notes & productivity")
        table.add_row("secure", "Security scanning")
        table.add_row("launcher", "AI agent launcher")
        table.add_row("[dim]claude[/dim]", "[dim]Launch Claude Code directly[/dim]")
        table.add_row("[dim]codex[/dim]", "[dim]Launch Codex directly[/dim]")
        console.print(table)

        console.print(
            "\n[dim]Commands: /switch <module>  /help  /exit[/dim]\n"
        )

    # ---- prompt ----

    def _build_prompt(self) -> str:
        current = self._router.current
        if current is not None:
            return f"DevHub {current.prompt_label} > "
        return "DevHub > "

    # ---- slash commands ----

    def _handle_slash(self, raw: str) -> None:
        parts = raw.lstrip("/").split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        args = parts[1].strip() if len(parts) > 1 else ""

        match cmd:
            case "switch":
                self._switch(args)
            case "help":
                self._show_help()
            case "home":
                self._router.exit_current()
                self._render_home()
            case "exit" | "quit" | "q":
                self._running = False
            case _:
                console.print(f"[yellow]Unknown command: /{cmd}[/yellow]")

    def _switch(self, target: str) -> None:
        if not target:
            console.print("[yellow]Usage: /switch <module>[/yellow]")
            return

        target_lower = target.lower()

        # AI agent shortcuts — launch directly
        if target_lower in AI_AGENT_SHORTCUTS:
            console.print(f"[dim]Launching {target_lower}…[/dim]")
            result = LauncherService.launch(target_lower)
            if result.success:
                console.print(f"[green]✓[/green] {result.message}")
            else:
                console.print(f"[red]✗[/red] {result.message}")
            return

        # Hub returns to home
        if target_lower == "hub":
            self._router.exit_current()
            self._render_home()
            return

        self._router.switch_module(target_lower)

    def _show_help(self) -> None:
        current = self._router.current
        if current is not None:
            current.help()
            console.print("\n[dim]Shell: /switch <module>  /home  /exit[/dim]")
        else:
            table = Table(title="DevHub Commands", show_header=True, header_style="bold")
            table.add_column("Command", style="cyan")
            table.add_column("Description")
            table.add_row("/switch <module>", "Switch to a module")
            table.add_row("/home", "Return to home screen")
            table.add_row("/help", "Show this help")
            table.add_row("/exit", "Exit DevHub")
            console.print(table)
            console.print(f"\n[dim]Available modules: {', '.join(self._router.module_names)}[/dim]")

    # ---- shutdown ----

    def _shutdown(self) -> None:
        self._router.exit_current()
        console.print("[dim]DevHub closed.[/dim]")
