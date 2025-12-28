import os

# Redis
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}"

# Streams
JOB_STREAM = os.getenv("JOB_STREAM", "sentinel.jobs")

# Services
DB_SERVICE_URL = os.getenv("DB_SERVICE_URL", "http://localhost:8001")
NLP_URL = os.getenv("NLP_URL", "http://localhost:8002")
WEB_SCRAPER_URL = os.getenv("WEB_SCRAPER_URL", "http://localhost:8003")

# API
API_HOST = "0.0.0.0"
API_PORT = 8000

# Cache
CACHE_TTL = int(os.getenv("CACHE_TTL", 3600))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", 15))
