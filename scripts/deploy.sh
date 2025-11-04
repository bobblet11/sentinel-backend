#!/bin/bash
set -e

# --- Find the Project Root Directory ---
PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &> /dev/null && pwd)

echo "==> Project root identified as: $PROJECT_ROOT"

cd "$PROJECT_ROOT"
echo "==> Changed directory to project root"

echo "==> Tearing down existing services to ensure a clean start..."
sudo -E docker-compose down

echo "==> Starting services with newly built images..."
sudo -E docker-compose up --force-recreate -d

echo "==> Deploy complete. Following logs (Ctrl+C to stop)..."
sudo -E docker-compose logs -f
