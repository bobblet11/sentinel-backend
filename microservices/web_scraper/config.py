import os
import sys

from dotenv import load_dotenv


def print_env(PROXIFLY_API_KEY):
    print(f"Proxifly API key {PROXIFLY_API_KEY[:5]}************** ")


load_dotenv()

PROXIFLY_API_KEY = os.getenv("PROXIFLY_API_KEY")
if not PROXIFLY_API_KEY:
    print("FATAL: PROXIFLY_API_KEY environment variable is not set. Exiting.")
    sys.exit(1)


print_env(PROXIFLY_API_KEY)
