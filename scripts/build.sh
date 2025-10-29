#!/bin/bash
set -e

# --- Find the Project Root Directory ---
PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &> /dev/null && pwd)
echo "==> Project root identified as: $PROJECT_ROOT"


# --- Main Execution ---
cd "$PROJECT_ROOT"
echo "==> Changed directory to project root"

echo "==> Building base image..."
sudo docker build -t sentinel/base-image:1.0 -f docker/base/Dockerfile .

echo "==> Building microserivce images..."
sudo docker-compose build

echo "==> Build complete."
