# Tech Stack

## Core language
- **Python 3.11+**

## CLI framework
- **Typer** for command structure and command groups
- **Rich** for styled terminal output, panels, tables, status

## Storage
- **SQLite** for MEMO data
- **JSON** for simple config files

## Networking
- **Python sockets** for CLARA MVP
- Optional asyncio/WebSockets later

## Git layer
- Start with **subprocess** calling Git
- Optional later: GitPython

## Security tools
- **bandit** for Python code scanning
- **pip-audit** for Python dependency vulnerabilities
- **semgrep** for broader source scanning if available

## External integrations
- `claude` CLI via subprocess
- `codex` CLI via subprocess

## Packaging
- `pyproject.toml`
- pip installable local package

## Why this stack
- Fastest to prototype
- Easy for Claude/Codex to generate
- Strong CLI ergonomics
- Good enough for live demo
