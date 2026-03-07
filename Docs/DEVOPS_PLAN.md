# DevOps Plan

## Goal
Enable fast local development, demo stability, and simple packaging.

## Local development
- Create Python virtual environment
- Install dependencies from `requirements.txt` or `pyproject.toml`
- Run `python -m devhub.main`

## Packaging
- Provide console entrypoint `devhub`
- Optional extras:
  - `[secure]` for security tools
  - `[chat]` for CLARA dependencies

## Environment variables
- `DEVHUB_DB_PATH`
- `DEVHUB_CONFIG_PATH`
- `DEVHUB_USERNAME`
- future: `CLAUDE_API_KEY`, `OPENAI_API_KEY` if needed

## Logging
- Console logs only for MVP
- Simple log file under `.devhub/logs/`

## CI suggestion
- GitHub Actions:
  - lint
  - unit tests
  - package build

## Deployment
For hackathon: local machine only.
Future:
- publish on PyPI
- optional CLARA chat relay server container
- Docker image for repeatable demos

## Backup/recovery
- SQLite DB stored locally
- export MEMO data to JSON/Markdown later
