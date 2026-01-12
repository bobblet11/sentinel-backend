#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Treat unset variables as an error when substituting.
set -u

# Pipes will fail if any command in the pipe fails, not just the last one.
set -o pipefail

# --- Color Definitions ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' 

# --- Helper Functions for Logging ---
log_info() {
    echo -e "${BLUE}==> $1${NC}"
}

log_warn() {
    echo -e "${YELLOW}==> $1${NC}"
}

run_and_log() {
    echo -e "    ${GREEN}Executing: $@${NC}"
    "$@" 2>&1 | sed 's/^/        /'
}

WEB_SCRAPER_CONTAINER_NAME="sentinel-web-scraper-service-container"

# --- Find the Project Root Directory ---
PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &> /dev/null && pwd)
# --- Main Execution ---
cd "$PROJECT_ROOT"
echo -e "\n${GREEN}==> Changed directory to project root${NC}"
cd "$PROJECT_ROOT"
log_info "Changed directory to project root"



# if [ "$(sudo docker ps -q -f name=^/${WEB_SCRAPER_CONTAINER_NAME}$)" ]; then
#     echo "Container is running. Copying files..."
#     run_and_log sudo -E docker cp sentinel-web-scraper-service-container:/app/microservices/web_scraper/screenshots/. ./microservices/web_scraper/screenshots/

# else
#     echo "Container is NOT running."
# fi


run_and_log sudo -E docker-compose down

echo -e "\n${GREEN}✅ Spin down complete!\n"
