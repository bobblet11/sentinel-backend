#!/bin/sh

# Go to the correct directory
cd /app

# Run the python script.
# 'exec' replaces the shell process with the python process.
exec /usr/local/bin/python3 -m microservices.ingestor.main
