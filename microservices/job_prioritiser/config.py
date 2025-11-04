import os
import sys
from dotenv import load_dotenv

def print_env(INPUT_STREAMS, OUTPUT_STREAM):
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
    
print_env(INPUT_STREAMS, OUTPUT_STREAM)
    

