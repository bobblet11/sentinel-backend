#!/bin/bash

set -e
set -o pipefail

# --- Color Definitions ---
GREEN='\033[0;32m'
NC='\033[0m' 

run_green() {
    "$@" 2>&1 | sed "s/^/${GREEN}/; s/$/${NC}/"
}

run_tab() {
    "$@" 2>&1 | sed "s/^/\t/; s/$//"
}


# --- Find the Project Root Directory ---
PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &> /dev/null && pwd)
echo -e "\n${GREEN}==> Project root identified as: $PROJECT_ROOT${NC}"


# --- Main Execution ---
cd "$PROJECT_ROOT"
echo -e "\n${GREEN}==> Changed directory to project root${NC}"

echo -e "\n${GREEN}==> Pruning old Docker build cache...${NC}"
run_tab sudo -E docker system prune -f

echo -e "\n${GREEN}==> Building base image...${NC}"
# run_green sudo -E docker build --no-cache --pull -t sentinel/base-image:1.0 -f docker/base/Dockerfile .
run_tab sudo -E docker build --pull -t sentinel/base-image:1.0 -f docker/base/Dockerfile .

echo -e "\n${GREEN}==> Building microservice images...${NC}"
# run_green sudo -E docker-compose build --no-cache
run_tab sudo -E docker-compose build

echo -e "\n${GREEN}==> Build complete.${NC}\n\n\n\n"
