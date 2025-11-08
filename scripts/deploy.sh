#!/bin/bash
set -e
set -o pipefail

# --- Color Definitions ---
RED='\033[0;31m'
NC='\033[0m' # No Color (to reset)

run_red() {
    "$@" 2>&1 | sed "s/^/${RED}/; s/$/${NC}/"
}

run_tab() {
    "$@" 2>&1 | sed "s/^/\t/; s/$//"
}


# --- Find the Project Root Directory ---
PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &> /dev/null && pwd)

echo -e "${RED}==> Project root identified as: $PROJECT_ROOT${NC}"

cd "$PROJECT_ROOT"
echo -e "${RED}==> Changed directory to project root${NC}"

echo -e "${RED}==> Tearing down existing services to ensure a clean start...${NC}"
run_tab sudo -E docker-compose down

echo -e "${RED}==> Starting services with newly built images...${NC}"
sudo -E docker-compose up --force-recreate --build
