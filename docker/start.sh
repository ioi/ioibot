#!/bin/bash
# Script to deploy in production

set -euo pipefail

cd "$(dirname "$0")"

# Check if Docker is installed
if ! docker info >/dev/null 2>&1; then
  echo "Please install Docker before running this script."
  exit 1
fi

SERVICE_NAME="ioibot"
IMAGE_NAME="docker-ioibot"

if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
  docker compose up --build -d "$SERVICE_NAME"
else
  docker compose up -d "$SERVICE_NAME"
fi

docker compose logs --tail=10 -f "$SERVICE_NAME"
