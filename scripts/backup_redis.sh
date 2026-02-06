#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

PROJECT_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." &> /dev/null && pwd)
echo "Project root identified as: $PROJECT_ROOT"
cd "$PROJECT_ROOT"
echo "Changed directory to project root"

# --- CONFIGURATION ---
REDIS_CONTAINER_NAME="$1"
BACKUP_DIR="$2"

if [ ! -d "$REDIS_CONTAINER_NAME" ]; then
    echo "redis_container_name not given, defaulting to sentinel-redis-container"
    echo "Usage: $0 <redis_container_name> <backup_directory>"
    REDIS_CONTAINER_NAME="sentinel-redis-container"
fi

if [ ! -d "$BACKUP_DIR" ]; then
    echo "backup_directory not given, defaulting to backups"
    echo "Usage: $0 <redis_container_name> <backup_directory>"
    BACKUP_DIR="backups"
fi



TIMESTAMP=$(date +"%Y%m%d%H%M%S")
BACKUP_FILENAME="dump-${TIMESTAMP}.rdb"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILENAME}"

# --- VALIDATION ---
if ! sudo -E docker ps -a --format '{{.Names}}' | grep -q "^${REDIS_CONTAINER_NAME}$"; then
  echo "Error: Docker container '${REDIS_CONTAINER_NAME}' not found."
  exit 1
fi



# --- BACKUP PROCESS ---
echo "Starting Redis backup for container '${REDIS_CONTAINER_NAME}'..."

# 1. Trigger a background save of the Redis data.
#    BGSAVE is preferred as it runs in the background without blocking the Redis server. [1, 5]
echo "Triggering BGSAVE on the Redis container..."
sudo -E docker exec "$REDIS_CONTAINER_NAME" redis-cli BGSAVE
echo "BGSAVE command issued. Waiting a few seconds for it to complete..."

# Give it a moment to complete the save operation. For very large databases, you might need to increase this sleep time.
sleep 10

# 2. Find the Redis data directory within the container.
#    The default is often /data, but we can query Redis to be sure. [1, 3]
REDIS_DATA_DIR=$(sudo -E docker exec "$REDIS_CONTAINER_NAME" redis-cli config get dir | tail -n 1)


# 3. Copy the backup file from the container to the specified host directory.
#    The docker cp command is used for this purpose. [2, 7, 14]
echo "Copying 'dump.rdb' from '${REDIS_CONTAINER_NAME}:${REDIS_DATA_DIR}/dump.rdb' to '${BACKUP_PATH}'..."
sudo -E docker cp "${REDIS_CONTAINER_NAME}:${REDIS_DATA_DIR}/dump.rdb" "$BACKUP_PATH"

echo "Backup successful!"
echo "Backup file created at: ${BACKUP_PATH}"
