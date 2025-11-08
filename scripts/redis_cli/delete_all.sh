#!/bin/bash
# while docker is running

CONTAINER_NAME="sentinel-redis-container"

sudo docker exec -it $CONTAINER_NAME redis-cli FLUSHDB
