import os
import sys
from dotenv import load_dotenv

def print_env(CONSUMER_NAME, INPUT_STREAMS, OUTPUT_STREAM, GROUP_NAME, PRIORITY_MAP):
    print(f"Consumer name {CONSUMER_NAME}")
    print(f"Group name: {GROUP_NAME}\n\n")
    print(f"Priority map: {PRIORITY_MAP}\n\n")
    print("-" * 9)
    print(INPUT_STREAMS)
    print("-" * 9)
    print("    |    \n    V    ")
    print("-" * 9)
    print(OUTPUT_STREAM)

load_dotenv()

# All the input streams separated by commars
# For example ingestor:to.be.scraped, user-jobs:to.be.scraped
INPUT_STREAMS = (os.getenv("INPUT_STREAMS")).split(", ")
if not INPUT_STREAMS:
    print("FATAL: INPUT_STREAMS environment variable is not set. Exiting.")
    sys.exit(1)
    
    
OUTPUT_STREAM = os.getenv("OUTPUT_STREAM")
if not OUTPUT_STREAM:
    print("FATAL: OUTPUT_STREAM environment variable is not set. Exiting.")
    sys.exit(1)
    
GROUP_NAME = os.getenv("GROUP_NAME")
if not GROUP_NAME:
    print("FATAL: GROUP_NAME environment variable is not set. Exiting.")
    sys.exit(1)

PRIORITY_MAP = {
    'user': 1,
    'admin': 1, # Same priority as user
    'background': 2,
    'logging': 3
}

LOWEST_PRIORITY = float('inf')

CONSUMER_NAME = os.getenv("CONSUMER_NAME")
if not CONSUMER_NAME:
    print("FATAL: CONSUMER_NAME environment variable is not set. Exiting.")
    sys.exit(1)


print_env(CONSUMER_NAME, INPUT_STREAMS, OUTPUT_STREAM, GROUP_NAME, PRIORITY_MAP)
    

