#!/usr/bin/env python3
import datetime
import json
import os

from dotenv import load_dotenv

load_dotenv(dotenv_path="configs/aws/.env")

# Configuration
from common.redis_client.connection import redis_connection

BACKUP_DIR = "./backups/aws"
timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
BACKUP_FILE = os.path.join(BACKUP_DIR, f"redis_jobs_backup_{timestamp}.json")

STREAM_KEYS = [
    "background:to.be.scraped",
    "failure:to.be.scraped",
]
SET_KEY = "ingestor:seen.articles"


def backup_stream(r, key, batch_size=500):
    """Iterate through a Redis stream in batches to avoid connection resets."""
    entries = []
    last_id = "-"
    while True:
        batch = r.xrange(key, min=last_id, max="+", count=batch_size)
        if not batch:
            break
        entries.extend(batch)
        # advance last_id to just after the last seen entry
        last_id = batch[-1][0]
        # increment the sequence part to avoid re-reading the same entry
        ms, seq = last_id.split("-")
        last_id = f"{ms}-{int(seq)+1}"
    return entries


def backup_jobs():
    r = redis_connection.get_client()
    os.makedirs(BACKUP_DIR, exist_ok=True)

    all_jobs = []
    for key in STREAM_KEYS:
        if not r.exists(key):
            print(f"[INFO] Key {key} does not exist")
            continue

        key_type = r.type(key)
        print(f"[INFO] Key {key} is type {key_type}")

        if key_type == "stream":
            entries = backup_stream(r, key, batch_size=500)
            for redis_id, fields in entries:
                job = {
                    "stream": key,
                    "redis_id": redis_id,
                    "fields": fields,
                }
                all_jobs.append(job)
            print(f"[INFO] Loaded {len(entries)} jobs from stream {key}")
        else:
            print(f"[WARN] Key {key} is not a stream, skipping")

    urls = list(r.smembers(SET_KEY))

    backup_data = {
        "jobs": all_jobs,
        "set_urls": urls,
    }

    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=2)

    print(f"[INFO] Backup complete: {len(all_jobs)} jobs, {len(urls)} URLs saved to {BACKUP_FILE}")


if __name__ == "__main__":
    backup_jobs()
