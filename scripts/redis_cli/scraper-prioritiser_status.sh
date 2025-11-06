#!/bin/bash

CONTAINER_NAME="sentinel-redis-container"
SCRAPER-PRIORITISER_CONTAINER_NAME="sentinel-scraper-prioritiser-service-container"

echo -e "\n\n--- Pending Background Articles (from Stream) ---"
sudo docker exec $CONTAINER_NAME redis-cli XRANGE "ingestor:to.be.scraped" - + COUNT 5 | awk 'NR % 3 == 0' | jq
echo -e "\n\n"

echo -e "\n\n--- Pending User Articles (from Stream) ---"
sudo docker exec $CONTAINER_NAME redis-cli XRANGE "user-jobs:to.be.scraped" - + COUNT 5 | awk 'NR % 3 == 0' | jq
echo -e "\n\n"

echo -e "\n\n--- Pending Prioritised Articles (from Stream) ---"
sudo docker exec $CONTAINER_NAME redis-cli XRANGE "prioritised:to.be.scraped" - + COUNT 5 | awk 'NR % 3 == 0' | jq
echo -e "\n\n"

