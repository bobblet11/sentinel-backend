#!/bin/bash
set -e

# --- Find the Project Root Directory ---
PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &> /dev/null && pwd)
echo "==> Project root identified as: $PROJECT_ROOT"


# --- Main Execution ---
cd "$PROJECT_ROOT"
echo "==> Changed directory to project root"

# echo "==> Pruning old Docker build cache..."
# sudo -E docker system prune -f

echo -e "\n\n==> Building base image..."
# sudo -E docker build --no-cache --pull -t sentinel/base-image:1.0 -f docker/base/Dockerfile .
sudo -E docker build --pull -t sentinel/base-image:1.0 -f docker/base/Dockerfile .


echo -e "\n\n==> Building microserivce images..."
# sudo -E docker-compose build --no-cache
sudo -E docker-compose build

echo -e "\n\n==> Build complete."
