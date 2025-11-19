import os
import sys
from typing import Dict, List, Optional

from dotenv import load_dotenv


def print_env(
    CONSUMER_NAME: str,
    INPUT_STREAMS: List[str],
    OUTPUT_STREAM: str,
    GROUP_NAME: str,
    PRIORITY_MAP: Dict[str, int],
    BATCH_SIZE: int,
    MAX_WORKERS: int,
) -> None:
    print(f"Consumer name {CONSUMER_NAME}")
    print(f"Group name: {GROUP_NAME}\n\n")
    print(f"Priority map: {PRIORITY_MAP}\n\n")
    print(f"Batch size: {BATCH_SIZE}\n\n")
    print(f"Max workers: {MAX_WORKERS}\n\n")
    print("-" * 9)
    print(INPUT_STREAMS)
    print("-" * 9)
    print("    |    \n    V    ")
    print("-" * 9)
    print(OUTPUT_STREAM)


load_dotenv()


INPUT_STREAMS_: Optional[str] = os.getenv("INPUT_STREAMS")
if not INPUT_STREAMS_:
    print("FATAL: INPUT_STREAMS environment variable is not set. Exiting.")
    sys.exit(1)
INPUT_STREAMS: List[str] = (INPUT_STREAMS_).split(", ")


OUTPUT_STREAM: Optional[str] = os.getenv("OUTPUT_STREAM")
if not OUTPUT_STREAM:
    print("FATAL: OUTPUT_STREAM environment variable is not set. Exiting.")
    sys.exit(1)

GROUP_NAME: Optional[str] = os.getenv("GROUP_NAME")
if not GROUP_NAME:
    print("FATAL: GROUP_NAME environment variable is not set. Exiting.")
    sys.exit(1)

PRIORITY_MAP = {
    "user": 1,
    "admin": 1,  # Same priority as user
    "background": 2,
    "logging": 3,
}

LOWEST_PRIORITY: Optional[float] = float("inf")

CONSUMER_NAME: Optional[str] = os.getenv("CONSUMER_NAME")
if not CONSUMER_NAME:
    print("FATAL: CONSUMER_NAME environment variable is not set. Exiting.")
    sys.exit(1)

MAX_WORKERS: Optional[int] = int(os.getenv("MAX_WORKERS"))
if not MAX_WORKERS:
    print("FATAL: MAX_WORKERS environment variable is not set. Exiting.")
    sys.exit(1)

BATCH_SIZE: Optional[int] = int(os.getenv("BATCH_SIZE"))
if not BATCH_SIZE:
    print("FATAL: BATCH_SIZE environment variable is not set. Exiting.")
    sys.exit(1)


print_env(
    CONSUMER_NAME,
    INPUT_STREAMS,
    OUTPUT_STREAM,
    GROUP_NAME,
    PRIORITY_MAP,
    BATCH_SIZE,
    MAX_WORKERS,
)
