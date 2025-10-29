#!/bin/bash
# while docker is running

echo -e "\n\n--- Seen Articles (from Set) ---"
sudo docker exec sentinel-backend-redis-1 redis-cli SMEMBERS "ingestor:seen.articles"
echo -e "\n\n"

echo -e "\n\n--- Latest 5 Articles to be Scraped (Published to Stream) ---"
sudo docker exec sentinel-backend-redis-1 redis-cli XRANGE "ingestor:to.be.scraped" - + COUNT 5 | awk 'NR % 3 == 0' | jq
echo -e "\n\n"
