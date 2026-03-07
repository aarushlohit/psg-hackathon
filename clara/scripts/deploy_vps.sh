#!/usr/bin/env bash
# Deploy CLARA on a fresh VPS (Ubuntu/Debian)
set -euo pipefail

echo "=== CLARA VPS Deployment ==="

# Install Docker if missing
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    echo "Docker installed. You may need to re-login for group changes."
fi

# Install Docker Compose plugin if missing
if ! docker compose version &> /dev/null; then
    echo "Installing Docker Compose plugin..."
    sudo apt-get update && sudo apt-get install -y docker-compose-plugin
fi

# Clone or update repo
REPO_DIR="${HOME}/clara"
REPO_URL="${CLARA_REPO_URL:-}"

if [[ -n "$REPO_URL" ]]; then
    if [[ -d "$REPO_DIR" ]]; then
        echo "Updating repository..."
        cd "$REPO_DIR" && git pull
    else
        echo "Cloning repository..."
        git clone "$REPO_URL" "$REPO_DIR"
        cd "$REPO_DIR"
    fi
else
    echo "No REPO_URL set. Using current directory."
    REPO_DIR="$(pwd)"
fi

cd "$REPO_DIR"

# Generate JWT secret if not set
if [[ -z "${CLARA_JWT_SECRET:-}" ]]; then
    export CLARA_JWT_SECRET="$(openssl rand -hex 32)"
    echo "Generated JWT secret."
fi

# Build and start
echo "Building and starting CLARA..."
docker compose -f clara/docker/docker-compose.yml up -d --build

echo ""
echo "=== CLARA deployed! ==="
echo "Server: http://$(hostname -I | awk '{print $1}'):9100"
echo "Status: curl http://localhost:9100/status"
echo "Logs:   docker compose -f clara/docker/docker-compose.yml logs -f"
