#!/bin/bash
set -e

# --- Find the Project Root Directory ---
PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &> /dev/null && pwd)
echo "==> Project root identified as: $PROJECT_ROOT"


# --- Main Execution ---
cd "$PROJECT_ROOT"
echo "==> Changed directory to project root"

echo "==> Sorting imports"
isort .

echo "==> Formatting code"
black .

echo "==> Formatting complete."

echo "==> Finding errors in code"
flake8 .

echo "==> Checking type hints in code"
mypy .

echo "==> Static analysis complete."
