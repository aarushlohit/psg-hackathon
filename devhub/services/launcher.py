"""AI agent launcher service — subprocess wrappers for claude and codex."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LaunchResult:
    """Result of attempting to launch an external AI agent."""

    tool: str
    success: bool
    message: str


class LauncherService:
    """Detect and launch external AI coding agents (Claude Code, Codex)."""

    TOOLS: dict[str, dict[str, str]] = {
        "claude": {
            "command": "claude",
            "install_hint": "npm install -g @anthropic-ai/claude-code",
            "description": "Claude Code — AI coding agent by Anthropic",
        },
        "codex": {
            "command": "codex",
            "install_hint": "npm install -g @openai/codex",
            "description": "Codex — AI coding agent by OpenAI",
        },
    }

    @classmethod
    def is_available(cls, tool: str) -> bool:
        """Check if a tool is on PATH."""
        info = cls.TOOLS.get(tool)
        if info is None:
            return False
        return shutil.which(info["command"]) is not None

    @classmethod
    def launch(cls, tool: str) -> LaunchResult:
        """Launch an AI agent. Blocks until the agent process exits."""
        info = cls.TOOLS.get(tool)
        if info is None:
            return LaunchResult(
                tool=tool,
                success=False,
                message=f"Unknown tool: {tool}. Available: {', '.join(cls.TOOLS)}",
            )

        if not shutil.which(info["command"]):
            return LaunchResult(
                tool=tool,
                success=False,
                message=(
                    f"{info['description']} is not installed.\n"
                    f"  Install: {info['install_hint']}"
                ),
            )

        try:
            logger.info("Launching %s", info["command"])
            subprocess.run([info["command"]], env=os.environ.copy())
            return LaunchResult(tool=tool, success=True, message=f"{tool} session ended.")
        except FileNotFoundError:
            return LaunchResult(
                tool=tool,
                success=False,
                message=f"Failed to launch {tool}: command not found.",
            )
        except KeyboardInterrupt:
            return LaunchResult(tool=tool, success=True, message=f"{tool} session interrupted.")
