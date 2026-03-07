"""Git service — subprocess wrapper for Git operations via aarushlohit-git (aaru)."""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GitResult:
    """Structured result from a git operation."""

    success: bool
    output: str
    error: str = ""
    command: str = ""


class GitService:
    """Subprocess-based Git/AARU wrapper.

    Prefers the ``aaru`` CLI (from ``pip install aarushlohit-git``) when available,
    falls back to raw ``git`` otherwise.
    """

    def __init__(self) -> None:
        self._aaru_available: bool = shutil.which("aaru") is not None
        self._git_available: bool = shutil.which("git") is not None

    # ---- public API ----

    def status(self) -> GitResult:
        """Return the current repo status."""
        if self._aaru_available:
            return self._run(["aaru", "status"])
        return self._run(["git", "status", "--short"])

    def save(self, message: str, push: bool = False) -> GitResult:
        """Stage all, commit, and optionally push."""
        if not message:
            return GitResult(success=False, output="", error="Commit message cannot be empty.")

        if self._aaru_available:
            cmd = ["aaru", "save", message]
            return self._run(cmd)

        # Manual git fallback
        add_result = self._run(["git", "add", "."])
        if not add_result.success:
            return add_result

        commit_result = self._run(["git", "commit", "-m", message])
        if not commit_result.success:
            return commit_result

        if push:
            push_result = self._run(["git", "push"])
            if not push_result.success:
                return push_result

        return commit_result

    def branch(self, name: str) -> GitResult:
        """Create and switch to a new branch."""
        if not name:
            return GitResult(success=False, output="", error="Branch name cannot be empty.")
        if self._aaru_available:
            return self._run(["aaru", "branch", name])
        return self._run(["git", "checkout", "-b", name])

    def is_available(self) -> bool:
        """Return True if at least one git tool is available."""
        return self._aaru_available or self._git_available

    # ---- private ----

    @staticmethod
    def _run(cmd: list[str]) -> GitResult:
        """Execute a subprocess command and return a GitResult."""
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return GitResult(
                success=proc.returncode == 0,
                output=proc.stdout.strip(),
                error=proc.stderr.strip(),
                command=" ".join(cmd),
            )
        except FileNotFoundError:
            return GitResult(
                success=False,
                output="",
                error=f"Command not found: {cmd[0]}",
                command=" ".join(cmd),
            )
        except subprocess.TimeoutExpired:
            return GitResult(
                success=False,
                output="",
                error="Command timed out.",
                command=" ".join(cmd),
            )
