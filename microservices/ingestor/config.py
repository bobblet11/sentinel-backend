import os
import sys
from typing import Optional

from dotenv import load_dotenv


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


load_dotenv()


REDIS_DUPLICATE_FILTER_KEY: Optional[str] = os.getenv("REDIS_DUPLICATE_FILTER_KEY")
if not REDIS_DUPLICATE_FILTER_KEY:
    print("FATAL: REDIS_DUPLICATE_FILTER_KEY environment variable is not set. Exiting.")
    sys.exit(1)


OUTPUT_STREAM: Optional[str] = os.getenv("OUTPUT_STREAM")
if not OUTPUT_STREAM:
    print("FATAL: OUTPUT_STREAM environment variable is not set. Exiting.")
    sys.exit(1)


print_env(REDIS_DUPLICATE_FILTER_KEY, OUTPUT_STREAM)
