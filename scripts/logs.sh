#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e
# Treat unset variables as an error when substituting.
set -u
# Pipes will fail if any command in the pipe fails, not just the last one.
set -o pipefail

# Navigate to the project root
PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &> /dev/null && pwd)
cd "$PROJECT_ROOT/docker/compose"

sudo docker-compose logs -f
