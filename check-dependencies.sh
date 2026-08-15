#!/usr/bin/env bash
set -euo pipefail

command -v docker >/dev/null || { echo "Missing dependency: Docker. Install Docker Desktop with WSL integration." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Missing dependency: Docker Compose v2." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker is installed but its daemon is unavailable. Start Docker Desktop and enable WSL integration." >&2; exit 1; }
echo "Dependencies OK: $(docker --version | cut -d, -f1); $(docker compose version --short)"
