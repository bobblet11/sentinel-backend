#!/bin/bash
set -e

# --- Find the Project Root Directory ---
PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &> /dev/null && pwd)
EXCLUDE_REGEX="cronjob$"          # Regex for black and mypy (matches paths ending in 'cronjob')
EXCLUDE_GLOB="**/cronjob"         # Glob for isort and flake8 (matches 'cronjob' in any directory)

echo "==> Project root identified as: $PROJECT_ROOT"


# --- Main Execution ---
cd "$PROJECT_ROOT"
echo "==> Changed directory to project root"

echo "==> Removing unused imports and variables"
autoflake --in-place --recursive --remove-all-unused-imports --remove-unused-variables . --exclude "$EXCLUDE_GLOB"

echo "==> Sorting imports"
isort . --skip-glob "$EXCLUDE_GLOB"

echo "==> Formatting code"
black . --exclude "$EXCLUDE_REGEX"

echo "==> Formatting complete."

echo "==> Finding errors in code"
flake8 . --extend-exclude "$EXCLUDE_GLOB" --max-line-length=88 --ignore=E501,E203

echo "==> Checking type hints in code"
mypy . --exclude "$EXCLUDE_REGEX"

echo "==> Static analysis complete."
