#!/bin/bash
PORT=6380
for d in */data/redis_data; do
  echo "Starting Redis for $d on port $PORT"
  redis-server --dir "$d" --dbfilename dump.rdb --port $PORT &
  PORT=$((PORT+1))
done
