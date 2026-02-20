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

echo "Triggering BGSAVE..."
sudo docker exec "$REDIS_CONTAINER_NAME" redis-cli BGSAVE

# WAIT FOR COMPLETION (fixes everything)
echo "Waiting for BGSAVE completion..."
until sudo docker exec "$REDIS_CONTAINER_NAME" redis-cli INFO persistence | grep -q 'rdb_bgsave_in_progress:0.*ok'; do
    echo -n "."
    sleep 2
done
echo "BGSAVE complete!"

# Copy
sudo docker cp "${REDIS_CONTAINER_NAME}:${REDIS_DATA_DIR}/dump.rdb" "$BACKUP_PATH"

# VALIDATE
SIZE=$(stat -c%s "$BACKUP_PATH")
echo "Backup saved: ${SIZE} bytes"
if [ "$SIZE" -lt 1000000 ]; then
    echo "WARNING: Very small backup!"
fi
