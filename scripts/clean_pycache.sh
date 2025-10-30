#!/bin/bash
set -e

# --- Find the Project Root Directory ---
PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &> /dev/null && pwd)

echo "==> Project root identified as: $PROJECT_ROOT"

cd "$PROJECT_ROOT"
echo "==> Changed directory to project root"

echo "==> Deleting pyc and pycache files"
sudo find . -type f -name "*.pyc" -delete
sudo find . -type d -name "__pycache__" -delete

echo "==> Clean complete."
