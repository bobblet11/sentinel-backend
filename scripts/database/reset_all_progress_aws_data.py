#!/usr/bin/env python3
from dotenv import load_dotenv
import redis
import os

# Load environment
load_dotenv(dotenv_path="configs/aws/.env")

# Configuration
from common.redis_client.connection import redis_connection

STREAMS_TO_DELETE = ["background:to.be.nlp", "background:to.be.retrieval"]

def delete_streams_and_sets():
    r = redis_connection.get_client()

    cursor = 0
    deleted_streams = 0
    deleted_sets = 0

    while True:
        cursor, keys = r.scan(cursor=cursor, count=500)
        for key in keys:
            key_type = r.type(key)
            if key_type == "stream" and key in STREAMS_TO_DELETE:
                r.delete(key)
                print(f"[INFO] Deleted stream {key}")
                deleted_streams += 1
        if cursor == 0:
            break

    print(f"[INFO] Cleanup complete: {deleted_streams} streams and {deleted_sets} sets deleted.")

if __name__ == "__main__":
    delete_streams_and_sets()
