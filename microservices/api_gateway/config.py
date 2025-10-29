import os

from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
WEB_SCRAPER_URL = os.getenv("WEB_SCRAPER_URL", "http://web-scraper:8000")
NLP_URL = os.getenv("NLP_URL", "http://nlp:8000")
CACHE_TTL = int(os.getenv("CACHE_TTL", 3600))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", 15))
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
