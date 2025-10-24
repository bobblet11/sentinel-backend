#!/bin/bash

CONTAINER_NAME="sentinel-backend-ingestor-1"

echo "--- Attempting to read cron logs from container: $CONTAINER_NAME ---"

if [ "$(sudo docker ps -q -f name=$CONTAINER_NAME)" ]; then
    sudo docker exec "$CONTAINER_NAME" cat /var/log/cron.log
else
    echo "Error: Container '$CONTAINER_NAME' is not running."
fi

echo -e "\n--- Log check complete ---"
