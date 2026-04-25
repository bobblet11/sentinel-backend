#!/usr/bin/env python3
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from scripts.database.inspect_aws import inspect_redis

POSTGRES_USER:str = str(os.getenv("POSTGRES_USER", None))
POSTGRES_PASSWORD:str = str(os.getenv("POSTGRES_PASSWORD", None))
POSTGRES_HOST:str = str(os.getenv("POSTGRES_HOST", None))
POSTGRES_DB:str = str(os.getenv("POSTGRES_DB", None))
POSTGRES_PORT:int = int(os.getenv("POSTGRES_PORT", None))
POSTGRES_SSLMODE:str = str(os.getenv("POSTGRES_SSLMODE", "disable"))

# Load environment
load_dotenv(dotenv_path="configs/aws/.env")

# Redis connection
from common.redis_client.connection import redis_connection

# Streams that should be cleared (downstream only)
STREAMS_TO_DELETE = [
    "background:to.be.nlp",
    "background:to.be.retrieval",
    
    "user:to.be.scraped",
    "user:to.be.nlp",
    "user:to.be.retrieval",

    
    "all:benchmark.output",
    
    "failure:to.be.scraped",
    "failure:to.be.nlp",
    "failure:to.be.retrieval",
]

# Streams where consumer groups exist
STREAMS_WITH_GROUPS = [
    "background:to.be.scraped",
    "background:to.be.nlp",
    "background:to.be.retrieval",
    
    "user:to.be.scraped",
    "user:to.be.nlp",
    "user:to.be.retrieval",
    
    "failure:to.be.scraped",
    "failure:to.be.nlp",
    "failure:to.be.retrieval",
]

HASH_SETS_TO_DELETE = [
    "retrieval:hash.store"
]

SETS_TO_DELETE = [
    "retrieval:uid.store",
]

# Postgres setup (using your service code)
database_url: str = (
    f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}?sslmode={POSTGRES_SSLMODE}"
)
engine = create_engine(database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Redis cleanup
def delete_streams_sets_hashes():
    r = redis_connection.get_client()
    deleted_streams = 0
    deleted_sets = 0
    deleted_hashes = 0
    deleted_keys = 0

    # Delete downstream streams explicitly
    for stream in STREAMS_TO_DELETE:
        if r.exists(stream):
            r.delete(stream)
            print(f"Deleted stream {stream}")
            deleted_streams += 1

    # Delete sets explicitly
    for s in SETS_TO_DELETE:
        if r.exists(s):
            r.delete(s)
            print(f"Deleted set {s}")
            deleted_sets += 1

    # Delete hashes explicitly
    for h in HASH_SETS_TO_DELETE:
        if r.exists(h):
            r.delete(h)
            print(f"Deleted hash {h}")
            deleted_hashes += 1

    # Scan and delete everything except background:to.be.scraped
    cursor = 0
    while True:
        cursor, keys = r.scan(cursor=cursor, count=500)
        for key in keys:
            if key == "background:to.be.scraped":
                continue
            r.delete(key)
            print(f"Deleted key {key}")
            deleted_keys += 1
        if cursor == 0:
            break

    print(
        f"Redis cleanup complete: {deleted_streams} streams, "
        f"{deleted_sets} sets, {deleted_hashes} hashes, {deleted_keys} other keys deleted."
    )

# Reset consumer groups
def reset_consumer_groups():
    r = redis_connection.get_client()

    for stream in STREAMS_WITH_GROUPS:
        if not r.exists(stream):
            continue

        groups = r.xinfo_groups(stream)
        for group in groups:
            group_name = group['name']
            r.xgroup_destroy(stream, group_name)
            print(f"Destroyed consumer group {group_name} on stream {stream}")

    print("Consumer groups reset complete.")
    
# Postgres cleanup
def truncate_all_postgres_tables():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public';
            """))
            tables = [row[0] for row in result]

            for table in tables:
                conn.execute(text(f'TRUNCATE TABLE "{table}" CASCADE;'))
                print(f"Truncated table {table}")

        print("Postgres cleanup complete (all tables truncated).")

    except OperationalError as e:
        print(f"Could not connect to Postgres: {e}")

if __name__ == "__main__":
    print("--- BEFORE DELETE ---")
    inspect_redis()

    delete_streams_sets_hashes()
    truncate_all_postgres_tables()
    reset_consumer_groups()
    
    print("--- BEFORE DELETE ---")
    inspect_redis()

