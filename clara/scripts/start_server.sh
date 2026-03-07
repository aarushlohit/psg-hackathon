#!/usr/bin/env bash
# Start the CLARA server (dev mode)
set -euo pipefail

cd "$(dirname "$0")/../.."

HOST="${CLARA_HOST:-0.0.0.0}"
PORT="${CLARA_PORT:-9100}"

echo "Starting CLARA server on ${HOST}:${PORT}..."
exec python -m clara.server.main --host "$HOST" --port "$PORT"
