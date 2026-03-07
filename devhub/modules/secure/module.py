"""SECURE module — security scanning orchestration."""

from __future__ import annotations

import logging

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from devhub.modules.base import BaseModule
from devhub.services.security_service import SecurityOrchestrator, ScanResult

logger = logging.getLogger(__name__)
console = Console()


class SecureModule(BaseModule):
    """Security scanning module wrapping bandit, pip-audit, semgrep, secrets."""

    name = "secure"
    prompt_label = "[secure]"

    def __init__(self) -> None:
        self._orchestrator = SecurityOrchestrator()

    # ---- lifecycle ----

    def enter(self) -> None:
        super().enter()
        console.print(
            Panel(
                "[bold red]SECURE[/bold red] — Security Scanner\n"
                "Type [bold]help[/bold] for commands.",
                title="SECURE",
                border_style="red",
            )
        )

    # ---- commands ----

    def help(self) -> None:
        table = Table(title="SECURE Commands", show_header=True, header_style="bold red")
        table.add_column("Command", style="cyan")
        table.add_column("Description")
        table.add_row("scan code", "Run bandit static analysis")
        table.add_row("scan deps", "Run pip-audit dependency check")
        table.add_row("scan secrets", "Run regex-based secret detection")
        table.add_row("scan all", "Run all available scanners")
        table.add_row("help", "Show this help")
        console.print(table)

    def handle(self, command: str) -> None:
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        args = parts[1].strip() if len(parts) > 1 else ""

        try:
            match cmd:
                case "scan":
                    self._handle_scan(args)
                case "help":
                    self.help()
                case "":
                    pass
                case _:
                    console.print(f"[yellow]Unknown command: {cmd}. Type 'help'.[/yellow]")
        except Exception as exc:
            logger.exception("Error in SECURE module")
            console.print(f"[red]✗ Error:[/red] {exc}")

    # ---- scan dispatch ----

    def _handle_scan(self, target: str) -> None:
        match target:
            case "code":
                self._print_result(self._orchestrator.scan_code())
            case "deps":
                self._print_result(self._orchestrator.scan_deps())
            case "secrets":
                self._print_result(self._orchestrator.scan_secrets())
            case "all":
                results = self._orchestrator.scan_all()
                for r in results:
                    self._print_result(r)
            case _:
                console.print("[yellow]Usage: scan code | scan deps | scan secrets | scan all[/yellow]")

    # ---- output ----

    @staticmethod
    def _print_result(result: ScanResult) -> None:
        if not result.success:
            console.print(f"[yellow]⚠ {result.scanner}:[/yellow] {result.error}")
            return

        if not result.findings:
            console.print(f"[green]✓ {result.scanner}:[/green] No issues found.")
            return

        table = Table(
            title=f"{result.scanner} ({len(result.findings)} finding{'s' if len(result.findings) != 1 else ''})",
            show_header=True,
            header_style="bold",
        )
        table.add_column("Severity", style="bold")
        table.add_column("Title")
        table.add_column("File")
        table.add_column("Line", justify="right")

        for f in result.findings:
            sev_style = {
                "critical": "[bold red]CRITICAL[/bold red]",
                "high": "[red]HIGH[/red]",
                "medium": "[yellow]MEDIUM[/yellow]",
                "low": "[dim]LOW[/dim]",
            }.get(f.severity.value, f.severity.value)
            table.add_row(sev_style, f.title, f.file, str(f.line) if f.line else "")

        console.print(table)
