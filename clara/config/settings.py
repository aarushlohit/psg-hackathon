"""CLARA configuration — environment-driven settings with sensible defaults.

All runtime knobs in one place. Override with environment variables or .env.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int = 0) -> int:
    return int(os.environ.get(key, str(default)))


def _env_bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class ServerSettings:
    host: str = field(default_factory=lambda: _env("CLARA_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _env_int("CLARA_PORT", 9100))
    ws_path: str = "/ws"
    heartbeat_interval: int = 30  # seconds
    max_clients: int = 1000
    rate_limit_per_sec: int = 10


@dataclass(frozen=True)
class DatabaseSettings:
    # SQLite by default; override CLARA_DATABASE_URL for Postgres
    url: str = field(default_factory=lambda: _env("CLARA_DATABASE_URL", ""))
    sqlite_path: Path = field(
        default_factory=lambda: Path(_env("CLARA_SQLITE_PATH", str(Path.home() / ".clara" / "clara.db")))
    )

    @property
    def use_postgres(self) -> bool:
        return self.url.startswith("postgresql")


@dataclass(frozen=True)
class RedisSettings:
    url: str = field(default_factory=lambda: _env("CLARA_REDIS_URL", "redis://localhost:6379/0"))
    enabled: bool = field(default_factory=lambda: _env_bool("CLARA_REDIS_ENABLED", False))


@dataclass(frozen=True)
class SecuritySettings:
    jwt_secret: str = field(default_factory=lambda: _env("CLARA_JWT_SECRET", "clara-dev-secret-change-me"))
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = field(default_factory=lambda: _env_int("CLARA_JWT_EXPIRE_MINUTES", 1440))
    tls_cert: str = field(default_factory=lambda: _env("CLARA_TLS_CERT", ""))
    tls_key: str = field(default_factory=lambda: _env("CLARA_TLS_KEY", ""))
    max_file_size: int = 50 * 1024 * 1024  # 50 MB
    password_iterations: int = 100_000


@dataclass(frozen=True)
class AISettings:
    openai_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    anthropic_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    openrouter_key: str = field(default_factory=lambda: _env("OPENROUTER_API_KEY"))
    default_budget: float = 10.0
    default_token_limit: int = 10_000
    default_request_limit: int = 100


@dataclass(frozen=True)
class StorageSettings:
    upload_dir: Path = field(
        default_factory=lambda: Path(_env("CLARA_UPLOAD_DIR", str(Path.home() / ".clara" / "uploads")))
    )


@dataclass(frozen=True)
class Settings:
    server: ServerSettings = field(default_factory=ServerSettings)
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    redis: RedisSettings = field(default_factory=RedisSettings)
    security: SecuritySettings = field(default_factory=SecuritySettings)
    ai: AISettings = field(default_factory=AISettings)
    storage: StorageSettings = field(default_factory=StorageSettings)


# Singleton
settings = Settings()
