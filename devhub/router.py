"""Module router — registry and dispatch for DevHub modules."""

from __future__ import annotations

import logging
from typing import Optional

from rich import box
from rich.console import Console
from rich.markup import escape

from devhub.modules.base import BaseModule

logger = logging.getLogger(__name__)
console = Console()


class ModuleRouter:
    """Maintains the module registry and manages switching between modules."""

    def __init__(self) -> None:
        self._modules: dict[str, BaseModule] = {}
        self._current: Optional[BaseModule] = None

    # ---- registration ----

    def register(self, module: BaseModule) -> None:
        """Register a module by its name."""
        if not module.name:
            raise ValueError("Module must have a non-empty 'name' attribute.")
        self._modules[module.name.lower()] = module
        logger.debug("Registered module: %s", module.name)

    # ---- switching ----

    def switch_module(self, name: str) -> bool:
        """Switch to the module identified by *name*. Returns True on success."""
        key = name.lower().strip()
        target = self._modules.get(key)
        if target is None:
            console.print(f"  [bold red]✗[/bold red]  Unknown module: [bold]{escape(name)}[/bold]")
            available = "  ".join(
                f"[orange1]{m}[/orange1]" for m in sorted(self._modules)
            )
            console.print(f"  [dim]Modules:[/dim]  {available}")
            return False

        if self._current is not None:
            try:
                self._current.exit()
            except Exception as exc:
                logger.warning("Error exiting module %s: %s", self._current.name, exc)

        self._current = target
        try:
            self._current.enter()
        except Exception as exc:
            logger.warning("Error entering module %s: %s", self._current.name, exc)
            console.print(f"[red]✗[/red] Failed to enter module: {exc}")
            self._current = None
            return False

        return True

    # ---- dispatch ----

    def handle_input(self, raw: str) -> None:
        """Forward command to the current module."""
        if self._current is None:
            console.print(
                "  [yellow]No active module.[/yellow]  "
                "[dim]Use [bold]/switch <module>[/bold] to enter one.[/dim]"
            )
            return
        try:
            self._current.handle(raw)
        except Exception as exc:
            logger.exception("Unhandled error in module %s", self._current.name)
            console.print(f"  [bold red]✗[/bold red]  [red]Module error:[/red]  {escape(str(exc))}")

    # ---- accessors ----

    @property
    def current(self) -> Optional[BaseModule]:
        return self._current

    @property
    def module_names(self) -> list[str]:
        return sorted(self._modules)

    def get_module(self, name: str) -> Optional[BaseModule]:
        return self._modules.get(name.lower())

    def exit_current(self) -> None:
        """Cleanly exit the current module (if any)."""
        if self._current is not None:
            try:
                self._current.exit()
            except Exception as exc:
                logger.warning("Error exiting module %s: %s", self._current.name, exc)
            self._current = None
