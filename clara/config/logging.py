"""CLARA structured logging configuration.

Log categories:
  connections.log — connect / disconnect / auth events
  messages.log   — chat, DMs, edits, deletes
  voice.log      — call / voice-room signaling
  errors.log     — unhandled exceptions & warnings
"""

import logging
import sys
from pathlib import Path

LOG_DIR = Path.home() / ".clara" / "logs"


def setup_logging(level: str = "INFO", log_to_files: bool = True) -> None:
    """Initialise handlers for the four structured log files + console."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler — always
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    console.setLevel(logging.INFO)
    root.addHandler(console)

    if not log_to_files:
        return

    _categories = {
        "clara.connections": "connections.log",
        "clara.messages": "messages.log",
        "clara.voice": "voice.log",
    }
    for logger_name, filename in _categories.items():
        fh = logging.FileHandler(LOG_DIR / filename)
        fh.setFormatter(fmt)
        fh.setLevel(logging.DEBUG)
        logging.getLogger(logger_name).addHandler(fh)

    # Errors go to their own file
    err_handler = logging.FileHandler(LOG_DIR / "errors.log")
    err_handler.setFormatter(fmt)
    err_handler.setLevel(logging.WARNING)
    root.addHandler(err_handler)
