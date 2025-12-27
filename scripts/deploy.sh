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
    # Using a subshell for the sed command to ensure it doesn't affect the script's stdout
    ( "$@" 2>&1 | sed 's/^/        /' )
}

# --- Find the Project Root Directory ---
PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &> /dev/null && pwd)
log_info "Project root identified as: $PROJECT_ROOT"

cd "$PROJECT_ROOT"
log_info "Changed directory to project root"

# --- Main Execution ---
log_warn "Tearing down the docker-compose project (if it exists)..."
# This will stop and remove the containers from your application, but not the dev container.
run_and_log sudo -E docker-compose down || true

# --- SELF-AWARE DELETION ---
log_warn "Forcefully removing ':latest' images, protecting the dev container's image..."

# Step 1: Get the ID of the current container (our dev environment).
# The HOSTNAME env var in a docker container is set to its container ID.
OUR_CONTAINER_ID=$(hostname)
log_info "Dev container ID is: $OUR_CONTAINER_ID"


# Step 3: Get the list of all images tagged as ':latest'.
ALL_LATEST_IMAGES=$(sudo -E docker images -q --filter "reference=*:latest")
IMAGES_TO_DELETE=""

# Check if the container exists
if [ "$(sudo -E docker ps -aq -f name=$OUR_CONTAINER_ID)" ]; then
    OUR_IMAGE_ID=$(sudo -E docker inspect --format='{{.Image}}' "$OUR_CONTAINER_ID")
    log_info "Dev container is using image: $OUR_IMAGE_ID"
    # Step 4: Filter out our own image ID from the list of images to be deleted.
    # We also need to get the short ID of our image to match what 'docker images -q' returns.
    OUR_IMAGE_SHORT_ID=$(sudo -E docker inspect --format='{{.Id}}' "$OUR_IMAGE_ID" | sed 's/sha256://' | cut -c1-12)
    IMAGES_TO_DELETE=$(echo "$ALL_LATEST_IMAGES" | grep -v "$OUR_IMAGE_SHORT_ID" || true)
else
    log_warn "No such container: $OUR_CONTAINER_ID"
fi

# Step 5: Check if there's anything left to delete and then delete it.
if [ -n "$IMAGES_TO_DELETE" ]; then
    log_info "Found the following ':latest' images to delete (excluding our own):"
    echo "$IMAGES_TO_DELETE" | sed 's/^/        /'
    run_and_log sudo -E docker rmi -f $IMAGES_TO_DELETE
else
    echo "        No other ':latest' images found to remove."
fi

log_warn "Pruning any remaining dangling Docker images..."
run_and_log sudo -E docker image prune -f

log_warn "Building base Docker image 1..."
run_and_log sudo -E docker build --pull -t sentinel/base-image:1.0 -f docker/base/base1/Dockerfile .

log_warn "Building base Docker image 2..."
run_and_log sudo -E docker build --pull -t sentinel/base-image:1.1 -f docker/base/base2/Dockerfile .

log_info "Building service images..."
run_and_log sudo -E docker-compose build

log_info "Deploying services with the newly built images..."
run_and_log sudo -E docker-compose up --force-recreate --renew-anon-volumes -d

echo -e "\n${GREEN}✅ Deployment complete! All services are running with fresh images.${NC}\n"
echo -e "${YELLOW}Use 'sudo docker-compose logs -f' to see the output.${NC}\n"
