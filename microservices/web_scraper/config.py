import os
import sys
from typing import Dict, Optional

from dotenv import load_dotenv


def print_env(
    INPUT_STREAM: str,
    USER_OUTPUT_STREAM: str,
    BACKGROUND_OUTPUT_STREAM: str,
    FAILURE_OUTPUT_STREAM: str,
    BATCH_SIZE: int,
    GROUP_NAME: str,
    CONSUMER_NAME: str,
    PRIORITY_MAP: Dict[str, int],
    SCRAPER_MAX_WORKERS: int,
    PROXY_VALIDATION_MAX_WORKERS,
) -> None:
    print(f"Batch size {BATCH_SIZE}")
    print(f"Consumer name {CONSUMER_NAME}")
    print(f"Group name: {GROUP_NAME}")
    print(f"Scraper Max workers: {SCRAPER_MAX_WORKERS}")
    print(f"Proxy Max workers: {PROXY_VALIDATION_MAX_WORKERS}")
    print(f"Priority map: {PRIORITY_MAP}")
    print("-" * 9)
    print(INPUT_STREAM)
    print("-" * 9)
    print("    |    \n    V    ")
    print("-" * 9)
    print(
        f"[{USER_OUTPUT_STREAM}, {BACKGROUND_OUTPUT_STREAM}, {FAILURE_OUTPUT_STREAM}]"
    )


load_dotenv()

INPUT_STREAM: Optional[str] = os.getenv("INPUT_STREAM")
if not INPUT_STREAM:
    print("FATAL: INPUT_STREAM environment variable is not set. Exiting.")
    sys.exit(1)

USER_OUTPUT_STREAM: Optional[str] = os.getenv("USER_OUTPUT_STREAM")
if not USER_OUTPUT_STREAM:
    print("FATAL: USER_OUTPUT_STREAM environment variable is not set. Exiting.")
    sys.exit(1)

BACKGROUND_OUTPUT_STREAM: Optional[str] = os.getenv("BACKGROUND_OUTPUT_STREAM")
if not BACKGROUND_OUTPUT_STREAM:
    print("FATAL: BACKGROUND_OUTPUT_STREAM environment variable is not set. Exiting.")
    sys.exit(1)

FAILURE_OUTPUT_STREAM: Optional[str] = os.getenv("FAILURE_OUTPUT_STREAM")
if not FAILURE_OUTPUT_STREAM:
    print("FATAL: FAILURE_OUTPUT_STREAM environment variable is not set. Exiting.")
    sys.exit(1)

GROUP_NAME: Optional[str] = os.getenv("GROUP_NAME")
if not GROUP_NAME:
    print("FATAL: GROUP_NAME environment variable is not set. Exiting.")
    sys.exit(1)

CONSUMER_NAME: Optional[str] = os.getenv("CONSUMER_NAME")
if not CONSUMER_NAME:
    print("FATAL: CONSUMER_NAME environment variable is not set. Exiting.")
    sys.exit(1)

PRIORITY_MAP = {
    "user": 1,
    "admin": 1,  # Same priority as user
    "background": 2,
    "logging": 3,
}

LOWEST_PRIORITY: Optional[float] = float("inf")

BATCH_SIZE: int = int(os.getenv("BATCH_SIZE"))
if not BATCH_SIZE:
    print("FATAL: BATCH_SIZE environment variable is not set. Exiting.")
    sys.exit(1)

SCRAPER_MAX_WORKERS: int = int(os.getenv("SCRAPER_MAX_WORKERS"))
if not SCRAPER_MAX_WORKERS:
    print("FATAL: SCRAPER_MAX_WORKERS environment variable is not set. Exiting.")
    sys.exit(1)

PROXY_VALIDATION_MAX_WORKERS: int = int(os.getenv("SCRAPER_MAX_WORKERS"))
if not PROXY_VALIDATION_MAX_WORKERS:
    print(
        "FATAL: PROXY_VALIDATION_MAX_WORKERS environment variable is not set. Exiting."
    )
    sys.exit(1)


print_env(
    INPUT_STREAM,
    USER_OUTPUT_STREAM,
    BACKGROUND_OUTPUT_STREAM,
    FAILURE_OUTPUT_STREAM,
    BATCH_SIZE,
    GROUP_NAME,
    CONSUMER_NAME,
    PRIORITY_MAP,
    SCRAPER_MAX_WORKERS,
    PROXY_VALIDATION_MAX_WORKERS,
)
