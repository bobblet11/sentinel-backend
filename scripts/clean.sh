#!/bin/bash
set -e

# --- Find the Project Root Directory ---
PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &> /dev/null && pwd)

echo "==> Project root identified as: $PROJECT_ROOT"

cd "$PROJECT_ROOT"
echo "==> Changed directory to project root"

echo "==> Spinning down containers"
sudo -E docker-compose down

echo "==> Removing all unused images..."
sudo -E docker image prune -a -f

echo "==> Clean complete."
