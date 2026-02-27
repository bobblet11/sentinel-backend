#!/bin/bash

# View NLP output from Redis streams

CONTAINER_NAME="sentinel-redis-container"
STREAM="${1:-user:to.be.retrieval}"
COUNT="${2:-1}"

echo "=== Viewing latest $COUNT message(s) from $STREAM ==="
echo ""

# Get the raw output and parse it
docker exec $CONTAINER_NAME redis-cli XREVRANGE $STREAM + - COUNT $COUNT | \
python3 << 'PYTHON_SCRIPT'
import sys
import json

lines = sys.stdin.read().splitlines()
i = 0

while i < len(lines):
    if i + 2 < len(lines) and not lines[i].startswith('('):
        msg_id = lines[i]
        print(f"\n{'='*80}")
        print(f"Message ID: {msg_id}")
        print(f"{'='*80}\n")
        
        # Parse key-value pairs
        j = i + 1
        while j < len(lines) and not lines[j].startswith(')'):
            if j + 1 < len(lines):
                key = lines[j]
                value = lines[j + 1]
                
                if key == "payload":
                    try:
                        parsed = json.loads(value)
                        print(f"{key}:")
                        print(json.dumps(parsed, indent=2))
                    except:
                        print(f"{key}: {value}")
                else:
                    print(f"{key}: {value}")
                j += 2
            else:
                break
        i = j + 1
    else:
        i += 1
PYTHON_SCRIPT
