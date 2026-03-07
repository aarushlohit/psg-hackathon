"""Global configuration management for DevHub."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path

from devhub.storage.paths import get_config_path

logger = logging.getLogger(__name__)


@dataclass
class DevHubConfig:
    """Global DevHub configuration stored as JSON."""

    username: str = ""
    default_module: str = "hub"
    clara_host: str = "127.0.0.1"
    clara_port: int = 9100
    theme: str = "default"
    extras: dict[str, str] = field(default_factory=dict)

    # ---- persistence ----

    @classmethod
    def load(cls) -> DevHubConfig:
        """Load config from disk or return defaults."""
        path: Path = get_config_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning("Corrupt config at %s, using defaults: %s", path, exc)
        return cls()

    def save(self) -> None:
        """Persist config to disk."""
        path = get_config_path()
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        logger.debug("Config saved to %s", path)
