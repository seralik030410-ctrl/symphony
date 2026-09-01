#!/usr/bin/env bash
# Standalone runtime installation, extracted from the trusted Symphony app.
set -euo pipefail
KIT="$(cd "$(dirname "$0")" && pwd)"
cd "$KIT"
command -v docker >/dev/null 2>&1 || { echo "Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and start it." >&2; exit 2; }
docker info >/dev/null 2>&1 || { echo "Start Docker Desktop and wait for the engine, then try again." >&2; exit 2; }
command -v shasum >/dev/null 2>&1 || { echo "shasum is required to verify this kit." >&2; exit 2; }
shasum -a 256 -c SHA256SUMS || { echo "Kit integrity check failed. Download and extract a fresh kit from Symphony." >&2; exit 2; }
echo "This builds symphony-sandbox:stage3 (runtime 6.0) using Docker."
echo "The first build downloads several GB from Docker Hub, Debian and PyPI. Keep at least 12 GB free."
echo "No chat, model, volume or cache is deleted. An existing runtime tag will be updated."
read -r -p "Build the runtime now? [y/N] " answer
case "$answer" in y|Y|yes|YES) ;; *) echo "Cancelled. Nothing changed."; exit 0 ;; esac
docker build --tag symphony-sandbox:stage3 --file "$KIT/Dockerfile" "$KIT"
version="$(docker image inspect --format '{{ index .Config.Labels "com.symphony.runtime.version" }}' symphony-sandbox:stage3)"
[[ "$version" == "6.0" ]] || { echo "Unexpected runtime version: $version" >&2; exit 3; }
echo "Runtime ready. Reopen Settings > General in Symphony to refresh diagnostics."
