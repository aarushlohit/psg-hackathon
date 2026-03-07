"""DevHub CLI entry point — Typer application."""

from __future__ import annotations

import logging
import sys

import typer
from rich.console import Console

from devhub import __version__
from devhub.router import ModuleRouter
from devhub.shell import DevHubShell
from devhub.storage.paths import ensure_home_dir

# ---- modules ----
from devhub.modules.clara.module import ClaraModule
from devhub.modules.aaru.module import AaruModule
from devhub.modules.memo.module import MemoModule
from devhub.modules.secure.module import SecureModule
from devhub.modules.launcher.module import LauncherModule

console = Console()
app = typer.Typer(
    name="devhub",
    help="DevHub — Terminal Developer Worksuite",
    add_completion=False,
    rich_markup_mode="rich",
)


def _setup_logging(verbose: bool) -> None:
    """Configure structured logging."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _build_router() -> ModuleRouter:
    """Create the router and register all modules."""
    router = ModuleRouter()
    router.register(ClaraModule())
    router.register(AaruModule())
    router.register(MemoModule())
    router.register(SecureModule())
    router.register(LauncherModule())
    return router


@app.command()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit"),
) -> None:
    """Launch the DevHub interactive shell."""
    if version:
        console.print(f"DevHub v{__version__}")
        raise typer.Exit()

    _setup_logging(verbose)
    ensure_home_dir()

    router = _build_router()
    shell = DevHubShell(router)
    shell.run()


# Allow `python -m devhub.main`
if __name__ == "__main__":
    app()
