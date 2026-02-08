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
RED='\033[0;31m'
NC='\033[0m'

# --- Helper Functions for Logging ---
log_info() {
    echo -e "${BLUE}==> $1${NC}"
}
log_warn() {
    echo -e "${YELLOW}==> $1${NC}"
}
log_error() {
    echo -e "${RED}==> ERROR: $1${NC}" >&2
}
run_and_log() {
    echo -e "    ${GREEN}Executing: $@${NC}"
    ( "$@" 2>&1 | sed 's/^/        /' )
}

# --- Find the Project Root Directory ---
PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &> /dev/null && pwd)
log_info "Project root identified as: $PROJECT_ROOT"
cd "$PROJECT_ROOT"
log_info "Changed directory to project root"

# --- Main Execution ---
CONFIG_NAME=${1:-base}
log_info "Preparing to deploy with configuration: '$CONFIG_NAME'"
CONFIG_DIR="configs/$CONFIG_NAME"
if [ ! -d "$CONFIG_DIR" ]; then
    log_error "Configuration directory '$CONFIG_DIR' not found. Aborting."
    exit 1
fi

CONFIG_DIR="$PROJECT_ROOT/configs/$CONFIG_NAME"
BASE_COMPOSE_FILE="$PROJECT_ROOT/docker/compose/docker-compose.yml"
ENV_FILE="$CONFIG_DIR/.env"
OVERRIDE_FILE="$CONFIG_DIR/docker-compose.override.yml"
if [ ! -f "$ENV_FILE" ]; then
    log_error "Environment file '.env' not found in '$CONFIG_DIR'. Aborting."
    exit 1
fi

DOCKER_COMPOSE_ARGS=(

    "-f" "$BASE_COMPOSE_FILE"
)

log_info "Using environment file for substitution: $ENV_FILE"
DOCKER_COMPOSE_ARGS+=("--env-file" "$ENV_FILE")

if [ -f "$OVERRIDE_FILE" ]; then
    log_info "Override file found at '$OVERRIDE_FILE', adding to command."
    DOCKER_COMPOSE_ARGS+=("-f" "$OVERRIDE_FILE")
else
    log_info "No override file found for '$CONFIG_NAME' configuration, proceeding without it."
fi





log_warn "Finding base path for volume mounts..."
if [ -n "${LOCAL_WORKSPACE_FOLDER:-}" ]; then
    log_info "Detected Dev Container. Using Host Path."
    # In VS Code Dev Container, this points to the host machine's path
    HOST_ROOT="${LOCAL_WORKSPACE_FOLDER}"
    HOST_LOG_ROOT="${LOCAL_WORKSPACE_FOLDER}/logs"
else
    log_info "No Dev Container detected. Using project root."
    HOST_ROOT="$PROJECT_ROOT"
    HOST_LOG_ROOT="$PROJECT_ROOT/logs"
fi

export HOST_ROOT
export HOST_LOG_ROOT
log_info "Exported HOST_ROOT=$HOST_ROOT"
log_info "Exported HOST_LOG_ROOT=$HOST_LOG_ROOT"

export ENV_FILE_PATH="$ENV_FILE"
log_info "Exporting ENV_FILE_PATH=$ENV_FILE_PATH"

if [ -f "$ENV_FILE" ]; then
    # Grep for the line, and cut everything after the '=' sign
    PROFILE_STRING=$(grep '^COMPOSE_PROFILES=' "$ENV_FILE" | cut -d'=' -f2-)
    
    if [ -n "$PROFILE_STRING" ]; then
        log_info "Activating profiles: $PROFILE_STRING"
        # Temporarily change the separator to a comma to split the string
        IFS=',' read -r -a profiles_array <<< "$PROFILE_STRING"
        
        # Loop through the array and add a --profile flag for each item
        for profile in "${profiles_array[@]}"; do
            DOCKER_COMPOSE_ARGS+=("--profile" "$profile")
        done
    else
        log_warn "COMPOSE_PROFILES not defined in $ENV_FILE. No profiles will be activated."
    fi
fi

log_warn "Creating log folders at: $HOST_LOG_ROOT"
sudo mkdir -p "$HOST_LOG_ROOT/ingestor"
sudo mkdir -p "$HOST_LOG_ROOT/scraper/logs"
sudo mkdir -p "$HOST_LOG_ROOT/scraper/screenshots"
sudo mkdir -p "$HOST_LOG_ROOT/scraper_prioritiser"
sudo mkdir -p "$HOST_LOG_ROOT/api"
sudo mkdir -p "$HOST_LOG_ROOT/nlp_prioritiser"
sudo mkdir -p "$HOST_LOG_ROOT/nlp"

sudo mkdir -p "$HOST_ROOT/data/redis_data"
sudo mkdir -p "$HOST_ROO/data/postgres_data"

log_warn "Setting permissions of log folder"
sudo chmod -R 777 "$HOST_LOG_ROOT"
sudo chown -R 999:999 "$HOST_LOG_ROOT"

sudo chown -R 999:999 "$HOST_ROOT/data"
sudo chmod -R 644 "$HOST_ROOT/data"
echo "        Completed log directory setup"

log_warn "Forcefully removing ':latest' images, protecting the dev container's image..."
OUR_CONTAINER_ID=$(hostname)
log_info "Dev container ID is: $OUR_CONTAINER_ID"
ALL_LATEST_IMAGES=$(sudo -E docker images -q --filter "reference=*:latest")
IMAGES_TO_DELETE=""


if [ "$(sudo -E docker ps -aq -f id=$OUR_CONTAINER_ID)" ]; then
    OUR_IMAGE_ID=$(sudo -E docker inspect --format='{{.Image}}' "$OUR_CONTAINER_ID")
    log_info "Dev container is using image: $OUR_IMAGE_ID"
    OUR_IMAGE_SHORT_ID=$(sudo -E docker inspect --format='{{.Id}}' "$OUR_IMAGE_ID" | sed 's/sha256://' | cut -c1-12)
    IMAGES_TO_DELETE=$(echo "$ALL_LATEST_IMAGES" | grep -v "$OUR_IMAGE_SHORT_ID" || true)
else
    log_warn "Not running in a dev container. Will target all ':latest' images for deletion."
    IMAGES_TO_DELETE="$ALL_LATEST_IMAGES"
fi

if [ -n "$IMAGES_TO_DELETE" ]; then
    log_info "Found the following ':latest' images to delete (excluding our own):"
    echo "$IMAGES_TO_DELETE" | sed 's/^/        /'
    run_and_log sudo -E docker rmi -f $IMAGES_TO_DELETE
else
    echo "        No other ':latest' images found to remove."
fi

log_info "Changing working directory to $PROJECT_ROOT"
cd "$PROJECT_ROOT" || { echo "ERROR: Could not cd to $PROJECT_ROOT" >&2; exit 1; }

log_warn "Tearing down the docker-compose project (if it exists)..."
run_and_log sudo -E docker-compose "${DOCKER_COMPOSE_ARGS[@]}" down --remove-orphans || true


log_warn "Pruning any remaining dangling Docker images..."
run_and_log sudo -E docker image prune -f

log_warn "Building base Docker image 1..."
run_and_log sudo -E docker build --pull -t sentinel/base-image:1.0 -f "$PROJECT_ROOT/docker/base/base1/Dockerfile" "$PROJECT_ROOT"  

log_warn "Building base Docker image 2..."
run_and_log sudo -E docker build --pull -t sentinel/base-image:1.1 -f "$PROJECT_ROOT/docker/base/base2/Dockerfile" "$PROJECT_ROOT"  

log_info "Building service images for '$CONFIG_NAME' configuration..."
run_and_log sudo -E docker-compose "${DOCKER_COMPOSE_ARGS[@]}" build  || true

log_info "Deploying services with the '$CONFIG_NAME' configuration..."
run_and_log sudo -E docker-compose "${DOCKER_COMPOSE_ARGS[@]}" up --force-recreate --renew-anon-volumes -d  

echo -e "\n${GREEN}✅ Deployment complete! Configuration '$CONFIG_NAME' is running.${NC}\n"
echo -e "${YELLOW}Use './scripts/logs.sh $CONFIG_NAME' to see the output.${NC}\n"
