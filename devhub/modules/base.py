"""Abstract base module contract for all DevHub modules."""

from __future__ import annotations

import abc
import logging

logger = logging.getLogger(__name__)


class BaseModule(abc.ABC):
    """Every DevHub module must extend this base class."""

    name: str = ""
    prompt_label: str = ""

    # ---- lifecycle hooks ----

    def enter(self) -> None:
        """Called when the user switches into this module."""
        logger.debug("Entering module: %s", self.name)

    def exit(self) -> None:
        """Called when the user switches away from this module."""
        logger.debug("Exiting module: %s", self.name)

    # ---- command interface ----

    @abc.abstractmethod
    def handle(self, command: str) -> None:
        """Process a single raw command string inside the module."""

    @abc.abstractmethod
    def help(self) -> None:
        """Display available commands for this module."""
