#!/bin/bash

CONTAINER_NAME="sentinel-redis-container"

echo -e "\n\n--- Seen Articles (from Set) ---"
sudo docker exec $CONTAINER_NAME redis-cli SMEMBERS "ingestor:seen.articles"
echo -e "\n\n"

echo -e "\n\n--- Latest 5 Articles to be Scraped (Published to Stream) ---"
sudo docker exec $CONTAINER_NAME redis-cli XRANGE "ingestor:to.be.scraped" - + COUNT 5 | awk 'NR % 3 == 0' | jq
echo -e "\n\n"
