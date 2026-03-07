"""Centralised path management for DevHub storage."""

from pathlib import Path


HOME_DIR: Path = Path.home() / ".devhub"
PROJECT_DIR: Path = Path(".devhub")


def ensure_home_dir() -> Path:
    """Create and return the global ~/.devhub directory."""
    HOME_DIR.mkdir(parents=True, exist_ok=True)
    return HOME_DIR


def ensure_project_dir() -> Path:
    """Create and return the project-local .devhub directory."""
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    return PROJECT_DIR


def get_config_path() -> Path:
    """Return path to the global config file."""
    return ensure_home_dir() / "config.json"


def get_memo_db_path() -> Path:
    """Return path to the MEMO SQLite database."""
    return ensure_home_dir() / "memo.db"


def get_clara_config_path() -> Path:
    """Return path to CLARA configuration."""
    return ensure_home_dir() / "clara.json"
