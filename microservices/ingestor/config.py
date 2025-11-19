import os
import sys
from typing import Optional

def print_env(
    REDIS_DUPLICATE_FILTER_KEY: str,
    OUTPUT_STREAM: str,
) -> None:
    print(f"Redis duplicate filter key {REDIS_DUPLICATE_FILTER_KEY}\n")
    print("-" * 9)
    print("RSS FEEDS")
    print("-" * 9)
    print("    |    \n    V    ")
    print("-" * 9)
    print(OUTPUT_STREAM)



REDIS_DUPLICATE_FILTER_KEY: Optional[str] = "ingestor:seen.articles"
if not REDIS_DUPLICATE_FILTER_KEY:
    print("FATAL: REDIS_DUPLICATE_FILTER_KEY environment variable is not set. Exiting.")
    sys.exit(1)


OUTPUT_STREAM: Optional[str] = "ingestor:to.be.scraped"
if not OUTPUT_STREAM:
    print("FATAL: OUTPUT_STREAM environment variable is not set. Exiting.")
    sys.exit(1)


print_env(REDIS_DUPLICATE_FILTER_KEY, OUTPUT_STREAM)
