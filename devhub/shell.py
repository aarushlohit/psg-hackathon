"""DevHub interactive shell — the main REPL loop."""

from __future__ import annotations

import logging
import sys

from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from devhub.router import ModuleRouter
from devhub.services.launcher import LauncherService

logger = logging.getLogger(__name__)
console = Console()

# Brand colour — used everywhere
_O = "bold bright_white on dark_orange3"   # primary accent: white on deep-orange bg
_OL = "bold orange1"                        # secondary: orange text
_DIM = "dim"

# Modules that should be launched directly via subprocess instead of entering a module.
AI_AGENT_SHORTCUTS: set[str] = {"claude", "codex"}

# Module catalogue
_MODULES = [
    ("clara",    "💬", "Real-time chat, rooms, DMs, voice, files, AI"),
    ("aaru",     "🌿", "Safe Git workflow — stage, commit, push in one command"),
    ("memo",     "📝", "Persistent tasks and notes for your project"),
    ("secure",   "🔒", "Static analysis, CVE scanning, secret detection"),
    ("launcher", "🚀", "AI agent launcher — Claude Code, Codex, and more"),
]
_AI_SHORTCUTS = [
    ("claude", "✨", "Launch Claude Code directly"),
    ("codex",  "⚡", "Launch OpenAI Codex directly"),
]


class DevHubShell:
    """Interactive shell orchestrating the DevHub experience."""

    def __init__(self, router: ModuleRouter) -> None:
        self._router = router
        self._running: bool = False

    # ── public ──────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Start the REPL loop."""
        self._running = True
        self._render_home()

        while self._running:
            prompt = self._build_prompt()
            try:
                raw = input(prompt)
            except (EOFError, KeyboardInterrupt):
                console.print()
                self._render_goodbye()
                break

            raw = raw.strip()
            if not raw:
                continue

            if raw.startswith("/"):
                self._handle_slash(raw)
            else:
                self._router.handle_input(raw)

        self._shutdown()

    # ── home screen ─────────────────────────────────────────────────────────

    def _render_home(self) -> None:
        console.print()

        # ── hero banner ──
        title = Text()
        title.append("  D E V H U B  ", style="bold bright_white")
        console.print(Panel(
            Align.center(
                title.markup + "\n"
                "[dim]Terminal Developer Worksuite[/dim]\n\n"
                "[dim]Chat  ·  Git  ·  Notes  ·  Security  ·  AI Agents[/dim]"
            ),
            border_style="orange1",
            padding=(1, 6),
            subtitle="[dim orange1]type [bold]/switch <module>[/bold] to start[/dim orange1]",
        ))
        console.print()

        # ── module cards ──
        mod_table = Table(
            show_header=True,
            header_style="bold dim",
            border_style="bright_black",
            box=box.SIMPLE,
            padding=(0, 2),
            expand=False,
        )
        mod_table.add_column("",        width=3,  no_wrap=True)           # emoji
        mod_table.add_column("Module",  style="bold orange1", width=10, no_wrap=True)
        mod_table.add_column("What it does")

        for name, icon, desc in _MODULES:
            mod_table.add_row(icon, name, desc)

        mod_table.add_row("", "", "")  # spacer
        for name, icon, desc in _AI_SHORTCUTS:
            mod_table.add_row(icon, f"[dim]{name}[/dim]", f"[dim]{desc}[/dim]")

        console.print(mod_table)

        # ── quick-reference bar ──
        console.print()
        console.rule(style="bright_black")
        console.print(
            "  [dim]/switch <module>[/dim]  [bright_black]·[/bright_black]  "
            "[dim]/help[/dim]  [bright_black]·[/bright_black]  "
            "[dim]/home[/dim]  [bright_black]·[/bright_black]  "
            "[dim]/exit[/dim]"
        )
        console.rule(style="bright_black")
        console.print()

    # ── prompt ───────────────────────────────────────────────────────────────

    def _build_prompt(self) -> str:
        current = self._router.current
        if current is not None:
            return f"DevHub {current.prompt_label} › "
        return "DevHub › "

    # ── slash commands ───────────────────────────────────────────────────────

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
                console.print(f"  [yellow]Unknown shell command:[/yellow] /{escape(cmd)}  "
                               "[dim](try /help)[/dim]")

    def _switch(self, target: str) -> None:
        if not target:
            console.print("  [yellow]Usage:[/yellow] /switch <module>")
            return

        target_lower = target.lower()

        if target_lower in AI_AGENT_SHORTCUTS:
            console.print(f"  [dim orange1]Launching {escape(target_lower)}…[/dim orange1]")
            result = LauncherService.launch(target_lower)
            if result.success:
                console.print(f"  [bold green]✓[/bold green]  {escape(result.message)}")
            else:
                console.print(f"  [bold red]✗[/bold red]  {escape(result.message)}")
            return

        if target_lower == "hub":
            self._router.exit_current()
            self._render_home()
            return

        self._router.switch_module(target_lower)

    def _show_help(self) -> None:
        current = self._router.current
        if current is not None:
            current.help()
            console.print()
            console.rule("[dim]shell commands[/dim]", style="bright_black")
            console.print(
                "  [dim]/switch <module>[/dim]  [bright_black]·[/bright_black]  "
                "[dim]/home[/dim]  [bright_black]·[/bright_black]  "
                "[dim]/exit[/dim]"
            )
            console.rule(style="bright_black")
            return

        console.print()
        console.rule("[bold orange1]DevHub  —  Help[/bold orange1]", style="orange1")
        table = Table(
            show_header=True,
            header_style="bold dim",
            border_style="bright_black",
            box=box.SIMPLE,
            padding=(0, 2),
            expand=False,
        )
        table.add_column("Command",     style="bold orange1", width=22, no_wrap=True)
        table.add_column("Description")
        table.add_row("/switch <module>", "Enter a module")
        table.add_row("/home",            "Return to the home screen")
        table.add_row("/help",            "Show this help (or module help when inside one)")
        table.add_row("/exit",            "Quit DevHub")
        console.print(table)
        mods = "  ".join(f"[orange1]{m}[/orange1]" for m, *_ in _MODULES)
        console.print(f"\n  [dim]Modules:[/dim]  {mods}")
        console.rule(style="bright_black")
        console.print()

    # ── shutdown ─────────────────────────────────────────────────────────────

    def _render_goodbye(self) -> None:
        console.print(Panel(
            Align.center("[dim]Thanks for using [bold orange1]DevHub[/bold orange1]  ·  goodbye[/dim]"),
            border_style="bright_black",
            padding=(0, 4),
        ))
        console.print()

    def _shutdown(self) -> None:
        self._router.exit_current()
        console.print("[dim]DevHub closed.[/dim]")
