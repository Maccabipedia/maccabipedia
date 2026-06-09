#!/usr/bin/env bash
#
# Install host prerequisites for the local MaccabiPedia docker stack on a
# fresh Ubuntu / Debian / WSL Ubuntu machine. Idempotent — safe to re-run.
#
# Installs: docker.io, docker-compose-v2. Adds the invoking user to
# the `docker` group. Starts and enables the docker daemon.
#
# macOS / Windows: use Docker Desktop (with WSL 2 integration on Windows)
# instead — this script targets apt-based Linux only.

set -euo pipefail

if ! command -v apt-get >/dev/null 2>&1; then
    echo "ERROR: this script requires apt (Debian/Ubuntu). On macOS/Windows install Docker Desktop manually." >&2
    exit 1
fi

if [ "$(id -u)" -eq 0 ]; then
    echo "ERROR: run this as a regular user with sudo, not as root." >&2
    exit 1
fi

echo "==> Installing docker.io, docker-compose-v2"
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    docker.io \
    docker-compose-v2

echo "==> Ensuring docker daemon is enabled and running"
sudo systemctl enable --now docker

TARGET_USER="${SUDO_USER:-$USER}"
if id -nG "$TARGET_USER" | tr ' ' '\n' | grep -qx docker; then
    echo "==> $TARGET_USER is already in the docker group"
else
    echo "==> Adding $TARGET_USER to the docker group"
    sudo usermod -aG docker "$TARGET_USER"
    echo
    echo "NOTE: You must start a new shell (or run 'newgrp docker') before"
    echo "      'docker' works without sudo for user $TARGET_USER."
fi

echo
echo "Host prerequisites installed. Versions:"
docker --version
docker compose version
